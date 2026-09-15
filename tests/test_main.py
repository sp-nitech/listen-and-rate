"""Tests for the FastAPI server's startup."""

from __future__ import annotations

import asyncio

import pytest


async def _start(app) -> None:
    """Run the app's startup, as the server does before serving anything."""
    from listen_and_rate.main import lifespan

    async with lifespan(app):
        pass


def test_a_config_that_cannot_be_loaded_ends_startup_with_its_message(monkeypatch):
    # The same short message the CLIs give, not a traceback: the fix is in the
    # config, not in the code. Run directly rather than through TestClient,
    # which turns an exit during startup into a cancellation.
    from listen_and_rate.main import create_app

    monkeypatch.setenv("LISTEN_AND_RATE_CONFIG", "./missing.yaml")
    with pytest.raises(SystemExit) as excinfo:
        asyncio.run(_start(create_app()))
    assert str(excinfo.value) == "./missing.yaml: config file not found"
