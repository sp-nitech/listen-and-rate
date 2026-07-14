"""Audio file serving routes: GET /audio/{stimulus_id}, GET /audio/x/{x_token}."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..dependencies import get_audio_map, get_x_secret
from ..x_token import resolve

router = APIRouter()

_MEDIA_TYPES: dict[str, str] = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
}


def _serve(stimulus_id: str, audio_map: dict[str, str]) -> FileResponse:
    file_path = audio_map.get(stimulus_id)
    if file_path is None:
        raise HTTPException(
            status_code=404, detail=f"Stimulus not found: {stimulus_id}"
        )
    path = Path(file_path)
    media_type = _MEDIA_TYPES.get(path.suffix.lower(), "audio/wav")
    return FileResponse(str(path), media_type=media_type)


# HEAD is registered explicitly (FastAPI's .get() covers GET only): the
# frontend's preflight check HEAD-requests every audio URL, and without
# this the request would fall through to the StaticFiles catch-all
# mounted at / and 404. FileResponse itself already handles HEAD
# correctly (headers only, no body).
@router.api_route("/audio/{stimulus_id}", methods=["GET", "HEAD"])
def serve_audio(stimulus_id: str, audio_map: dict[str, str] = Depends(get_audio_map)):
    """Stream an audio file by stimulus ID.

    FileResponse handles Range requests automatically, enabling seek-ahead
    in the browser's native audio player without buffering the full file.
    Returns 404 if the ID is not in the audio map.
    """
    return _serve(stimulus_id, audio_map)


@router.api_route("/audio/x/{x_token}", methods=["GET", "HEAD"])
def serve_abx_x(
    x_token: str,
    a: str,
    b: str,
    audio_map: dict[str, str] = Depends(get_audio_map),
    x_secret: bytes = Depends(get_x_secret),
):
    """Stream ABX's hidden "X" reference by resolving its opaque commitment token.

    x_token never appears in the audio_map directly - it's an HMAC commitment
    to whichever of a/b it actually equals (see x_token.py). Returns 404
    for a forged/mismatched token, same as an unknown stimulus_id would.
    """
    stimulus_id = resolve(a, b, x_token, x_secret)
    if stimulus_id is None:
        raise HTTPException(status_code=404, detail="Invalid or expired x_token")
    return _serve(stimulus_id, audio_map)


def serve_abx_x_php_alias(
    token: str,
    a: str,
    b: str,
    audio_map: dict[str, str] = Depends(get_audio_map),
    x_secret: bytes = Depends(get_x_secret),
):
    """GET /audio_x.php?token=&a=&b= - same handler as /audio/x/{x_token}.

    Registered as a plain function (not @router.get) so main.py can bind it
    at root level, matching the config.php/save.php alias pattern: one
    relative URL the frontend JS can use unchanged in both deployment modes.
    """
    return serve_abx_x(token, a, b, audio_map, x_secret)
