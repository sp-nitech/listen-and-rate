"""FastAPI dependency functions that expose app.state to route handlers."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request

from .config import Config
from .storage import ResultSaver

# Query parameter naming which config of a sequence a request is for; its
# value is that config's experiment_id. Mirrored by frontend/stage.php and
# frontend/js/stage.js.
STAGE_PARAM = "stage"


@dataclass(frozen=True)
class Stage:
    """Everything the server holds for one config, built once at startup."""

    config: Config
    result_saver: ResultSaver
    # stimulus id -> absolute path of the audio file served for it.
    audio_map: dict[str, str]


@dataclass(frozen=True)
class SequenceManifest:
    """The stages of a sequence, by experiment_id, in the order they run."""

    stage_ids: list[str]


def get_stage_or_manifest(request: Request) -> Stage | SequenceManifest:
    """Return the Stage a request is for, or the sequence's manifest.

    The manifest answers a request naming no stage while several configs are
    served: the browser fetches it first to learn which stages to run, and a
    health check or the report page asks about the server as a whole. Every
    other request is for one stage (see get_stage).
    """
    stages = request.app.state.stages
    if len(stages) > 1 and STAGE_PARAM not in request.query_params:
        return SequenceManifest(list(stages))
    return get_stage(request)


def get_stage(request: Request) -> Stage:
    """Return the Stage named by the request's `stage` query parameter.

    The parameter chooses between the stages of a sequence, so a lone config
    - with nothing to choose between - ignores it. When several are served, a
    request that names no stage, or one that is not served, gets a 404, as an
    unknown stimulus id does.
    """
    stages = request.app.state.stages
    if len(stages) == 1:
        (stage,) = stages.values()
        return stage
    stage_id = request.query_params.get(STAGE_PARAM)
    if stage_id not in stages:
        raise HTTPException(status_code=404, detail=f"Stage not found: {stage_id}")
    return stages[stage_id]


def get_config(request: Request) -> Config:
    """Return the loaded test configuration stored at startup."""
    return get_stage(request).config


def get_result_saver(request: Request) -> ResultSaver:
    """Return the shared ResultSaver instance stored at startup."""
    return get_stage(request).result_saver


def get_audio_map(request: Request) -> dict[str, str]:
    """Return the stimulus-id → absolute-audio-path mapping built at startup."""
    return get_stage(request).audio_map


def get_x_secret(request: Request) -> bytes:
    """Return the process-lifetime secret used to blind ABX's hidden "X" reference."""
    return request.app.state.x_secret
