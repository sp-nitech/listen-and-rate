"""FastAPI application factory and startup lifespan."""

from __future__ import annotations

import os
import secrets
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .config import load_config_or_exit
from .config.base import RATER_METADATA_KEY
from .duration import run_configured_duration_check
from .loudness import (
    run_configured_loudness_check,
    run_configured_loudness_normalization,
)
from .routers import api
from .routers import audio as audio_router
from .routers import progress as progress_router
from .routers import report as report_router
from .routers.api import get_test_config, submit
from .routers.audio import serve_abx_x_php_alias
from .silence import run_configured_silence_check
from .storage import make_result_saver


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load config and build shared state once at startup.

    Reads LISTEN_AND_RATE_CONFIG env var (default: ./config.yaml). All
    subsequent requests share the same config, result_saver, and audio_map
    objects.
    """
    config_path = os.environ.get("LISTEN_AND_RATE_CONFIG", "./config.yaml")
    config = load_config_or_exit(config_path)
    run_configured_duration_check(config)
    run_configured_loudness_check(config)
    run_configured_silence_check(config)
    app.state.config = config
    # The rater id rides along as a metadata answer (see _save_and_ok), so the
    # CSV saver has to know about the column up front - it writes only the
    # keys it was given, and would otherwise drop it.
    metadata_keys = [f.key for f in config.metadata.fields]
    if config.assignments is not None:
        metadata_keys = [RATER_METADATA_KEY, *metadata_keys]
    app.state.result_saver = make_result_saver(
        config.output.format,
        config.output.path,
        config.experiment_id,
        metadata_keys,
        [f.key for f in config.survey.fields],
        config.metrics.enabled_keys(),
    )
    all_stimuli = config.stimuli_list.entries if config.stimuli_list else []
    # With loudness_normalization configured, pre-normalize every clip into
    # a temp cache once at startup and serve from there; otherwise serve the
    # originals.
    normalized_cache: Path | None = None
    if config.loudness_normalization is not None:
        normalized_cache = Path(tempfile.mkdtemp(prefix="lar-normalized-"))
        try:
            app.state.audio_map = run_configured_loudness_normalization(
                config, lambda s: normalized_cache / f"{s.id}.wav"
            )
        except BaseException:
            # Startup died mid-normalization (bad file, Ctrl-C): the shutdown
            # cleanup below never runs, so drop the fresh cache here instead of
            # orphaning a full copy of the stimuli under /tmp on every attempt.
            shutil.rmtree(normalized_cache, ignore_errors=True)
            raise
    else:
        app.state.audio_map = {s.id: s.path for s in all_stimuli}
    # Used to blind ABX's hidden "X" reference (see x_token.py). Set
    # LISTEN_AND_RATE_X_SECRET to keep it stable across restarts/reloads and
    # multiple workers - otherwise each process mints its own random secret,
    # and tokens issued before a restart (e.g. uvicorn --reload picking up a
    # file change mid-session) stop verifying, failing that listener's submit.
    x_secret_env = os.environ.get("LISTEN_AND_RATE_X_SECRET")
    app.state.x_secret = (
        x_secret_env.encode() if x_secret_env else secrets.token_bytes(32)
    )
    yield
    if normalized_cache is not None:
        shutil.rmtree(normalized_cache, ignore_errors=True)


class NoStoreStaticFiles(StaticFiles):
    """Serve the frontend without letting browsers keep a stale module graph.

    CSS and ES modules are cached aggressively from Last-Modified/ETag alone.
    After a JS change the rating page can keep rendering an older script, so
    new markup (question descriptions, help) never appears until cache is
    cleared. no-store makes a normal refresh pick up the files on disk.
    """

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


def create_app() -> FastAPI:
    """Construct and return the FastAPI application.

    Registers /api and /audio routers, then mounts the frontend/ directory
    as a catch-all static file handler so index.html is served at /.
    """
    app = FastAPI(title="Listen and Rate", lifespan=lifespan)
    app.include_router(api.router, prefix="/api")
    app.include_router(audio_router.router)
    app.include_router(report_router.router)
    app.include_router(progress_router.router)

    # PHP-compatible aliases at root level so the same frontend JS (which calls
    # "config.php" and "save.php" as relative URLs) works with both FastAPI and
    # a static PHP deployment. Must be registered before StaticFiles so FastAPI
    # handles them rather than serving the raw .php source or returning 404.
    # HEAD is listed alongside GET for the same reason it is in routers/audio.py:
    # a GET-only route does not answer HEAD, so the request would fall through
    # to the StaticFiles catch-all and describe the raw .php source instead.
    app.add_api_route(
        "/config.php",
        get_test_config,
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    app.add_api_route("/save.php", submit, methods=["POST"], include_in_schema=False)

    def _save_php_check() -> dict:
        """GET /save.php: always OK in FastAPI (saving is handled server-side)."""
        return {"status": "ok"}

    app.add_api_route(
        "/save.php", _save_php_check, methods=["GET", "HEAD"], include_in_schema=False
    )
    app.add_api_route(
        "/audio_x.php",
        serve_abx_x_php_alias,
        # HEAD included for the frontend's preflight check, matching the
        # /audio/{stimulus_id} route (see routers/audio.py).
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )

    def _x_token_php_not_found() -> None:
        """GET /x_token.php: 404, not the raw PHP source.

        Like config.php/save.php, this file lives under frontend/ for the
        static-PHP export but has no FastAPI equivalent to serve (it's
        pure functions only, used by config.php/save.php/audio_x.php on the
        PHP side) - registering it here keeps StaticFiles from serving its
        source as a plain-text download.
        """
        raise HTTPException(status_code=404)

    app.add_api_route(
        "/x_token.php",
        _x_token_php_not_found,
        methods=["GET"],
        include_in_schema=False,
    )

    frontend_dir = Path(__file__).parent.parent / "frontend"
    app.mount(
        "/",
        NoStoreStaticFiles(directory=str(frontend_dir), html=True),
        name="frontend",
    )
    return app


app = create_app()
