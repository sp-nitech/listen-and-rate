"""FastAPI dependency functions that expose app.state to route handlers."""

from __future__ import annotations

from fastapi import Request

from .config import Config
from .storage import ResultSaver


def get_config(request: Request) -> Config:
    """Return the loaded test configuration stored at startup."""
    return request.app.state.config


def get_result_saver(request: Request) -> ResultSaver:
    """Return the shared ResultSaver instance stored at startup."""
    return request.app.state.result_saver


def get_audio_map(request: Request) -> dict[str, str]:
    """Return the stimulus-id → absolute-audio-path mapping built at startup."""
    return request.app.state.audio_map


def get_x_secret(request: Request) -> bytes:
    """Return the process-lifetime secret used to blind ABX's hidden "X" reference."""
    return request.app.state.x_secret
