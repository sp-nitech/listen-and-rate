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
from .loudness import (
    run_configured_loudness_check,
    run_configured_loudness_normalization,
)
from .routers import api
from .routers import audio as audio_router
from .routers import report as report_router
from .routers.api import get_test_config, submit
from .routers.audio import serve_abx_x_php_alias
from .storage import make_result_saver


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load config and build shared state once at startup.

    Reads LISTEN_AND_RATE_CONFIG env var (default: ./config.yaml). All subsequent
    requests share the same config, result_saver, and audio_map objects.
    """
    config_path = os.environ.get("LISTEN_AND_RATE_CONFIG", "./config.yaml")
    config = load_config_or_exit(config_path)
    run_configured_loudness_check(config)
    app.state.config = config
    app.state.result_saver = make_result_saver(
        config.output.format,
        config.output.path,
        config.experiment_id,
        [f.key for f in config.metadata],
    )
    all_stimuli = config.stimuli.items if config.stimuli else []
    # With loudness_normalization configured, pre-normalize every clip into a temp
    # cache once at startup and serve from there; otherwise serve the originals.
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


def create_app() -> FastAPI:
    """Construct and return the FastAPI application.

    Registers /api and /audio routers, then mounts the frontend/ directory
    as a catch-all static file handler so index.html is served at /.
    """
    app = FastAPI(title="Listen and Rate", lifespan=lifespan)
    app.include_router(api.router, prefix="/api")
    app.include_router(audio_router.router)
    app.include_router(report_router.router)

    # PHP-compatible aliases at root level so the same frontend JS (which calls
    # "config.php" and "save.php" as relative URLs) works with both FastAPI and
    # a static PHP deployment.  Must be registered before StaticFiles so FastAPI
    # handles them rather than serving the raw .php source or returning 404.
    app.add_api_route(
        "/config.php", get_test_config, methods=["GET"], include_in_schema=False
    )
    app.add_api_route("/save.php", submit, methods=["POST"], include_in_schema=False)

    def _save_php_check() -> dict:
        """GET /save.php: always OK in FastAPI (saving is handled server-side)."""
        return {"status": "ok"}

    app.add_api_route(
        "/save.php", _save_php_check, methods=["GET"], include_in_schema=False
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
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    return app


app = create_app()
