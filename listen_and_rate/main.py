"""FastAPI application factory and startup lifespan."""

from __future__ import annotations

import os
import secrets
import shutil
import tempfile
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .config import Config, load_sequence_or_exit
from .dependencies import Stage
from .duration import run_configured_duration_check
from .loudness import (
    run_configured_loudness_check,
    run_configured_loudness_normalization,
)
from .routers import api
from .routers import audio as audio_router
from .routers import report as report_router
from .routers.api import get_test_config, submit
from .routers.audio import serve_abx_x_php_alias
from .silence import run_configured_silence_check
from .storage import make_result_saver

# frontend/ files that only the PHP export runs: included by the PHP entry
# points, never requested by the browser.
_PHP_ONLY_HELPERS = ("x_token.php", "stage.php")


def _build_stage(config: Config, cleanup: ExitStack) -> Stage:
    """Run the startup checks for one config and build what serving it needs.

    A temp cache made for loudness normalization is registered on `cleanup`,
    so it is removed at shutdown - and also when startup dies part-way (a bad
    file, Ctrl-C), which would otherwise orphan a full copy of the stimuli
    under /tmp on every attempt.
    """
    run_configured_duration_check(config)
    run_configured_loudness_check(config)
    run_configured_silence_check(config)
    result_saver = make_result_saver(
        config.output.format,
        config.output.path,
        config.experiment_id,
        [f.key for f in config.metadata.fields],
        [f.key for f in config.survey.fields],
        config.metrics.enabled_keys(),
    )
    # With loudness_normalization configured, pre-normalize every clip into
    # a temp cache once at startup and serve from there; otherwise serve the
    # originals.
    if config.loudness_normalization is not None:
        normalized_cache = Path(tempfile.mkdtemp(prefix="lar-normalized-"))
        cleanup.callback(shutil.rmtree, normalized_cache, ignore_errors=True)
        audio_map = run_configured_loudness_normalization(
            config, lambda s: normalized_cache / f"{s.id}.wav"
        )
    else:
        all_stimuli = config.stimuli_list.entries if config.stimuli_list else []
        audio_map = {s.id: s.path for s in all_stimuli}
    return Stage(config, result_saver, audio_map)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load config and build shared state once at startup.

    Reads LISTEN_AND_RATE_CONFIG env var (default: ./config.yaml): one config
    path, or several separated by os.pathsep to run those tests back to back
    as a sequence. Each config gets one Stage (config, result_saver, and
    audio_map), shared by every request for it.
    """
    config_paths = os.environ.get("LISTEN_AND_RATE_CONFIG", "./config.yaml")
    configs = load_sequence_or_exit(config_paths.split(os.pathsep))
    with ExitStack() as cleanup:
        app.state.stages = {c.experiment_id: _build_stage(c, cleanup) for c in configs}
        # Used to blind ABX's hidden "X" reference (see x_token.py). Set
        # LISTEN_AND_RATE_X_SECRET to keep it stable across restarts/reloads
        # and multiple workers - otherwise each process mints its own random
        # secret, and tokens issued before a restart (e.g. uvicorn --reload
        # picking up a file change mid-session) stop verifying, failing that
        # listener's submit.
        x_secret_env = os.environ.get("LISTEN_AND_RATE_X_SECRET")
        app.state.x_secret = (
            x_secret_env.encode() if x_secret_env else secrets.token_bytes(32)
        )
        yield


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

    def _php_helper_not_found() -> None:
        """GET a PHP-only helper: 404, not the raw PHP source.

        Like config.php/save.php, these files live under frontend/ for the
        static-PHP export but have no FastAPI equivalent to serve (they're
        pure functions only, used by config.php/save.php/audio_x.php on the
        PHP side) - registering them here keeps StaticFiles from serving
        their source as a plain-text download.
        """
        raise HTTPException(status_code=404)

    for helper in _PHP_ONLY_HELPERS:
        app.add_api_route(
            f"/{helper}",
            _php_helper_not_found,
            methods=["GET"],
            include_in_schema=False,
        )

    frontend_dir = Path(__file__).parent.parent / "frontend"
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    return app


app = create_app()
