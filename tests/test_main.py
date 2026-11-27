"""Tests for the FastAPI server's startup."""

from __future__ import annotations

import asyncio
import os

import pytest

from ._helpers import write_config


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


def _config_with_forms(tmp_path, test_audio_file, **forms) -> dict:
    return {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "stimuli_list": {"entries": [{"id": "s001", "path": str(test_audio_file)}]},
        **forms,
    }


def _text_field(key: str, default_from: str) -> dict:
    return {"key": key, "label": key, "type": "text", "default_from": default_from}


def _remote_user_warnings(record) -> list[str]:
    return [str(w.message) for w in record if "remote_user" in str(w.message)]


def test_default_from_remote_user_warns_at_startup(
    tmp_path, test_audio_file, monkeypatch
):
    # Only the PHP deployment fills it in, but the config is still served, so
    # the one written for that deployment can be tried here as is.
    from listen_and_rate.main import create_app

    form = {
        "fields": [
            _text_field("listener", "remote_user"),
            _text_field("device", "none"),
        ]
    }
    config = _config_with_forms(tmp_path, test_audio_file, metadata=form)
    monkeypatch.setenv("LISTEN_AND_RATE_CONFIG", str(write_config(tmp_path, config)))
    with pytest.warns(UserWarning) as record:
        asyncio.run(_start(create_app()))
    assert _remote_user_warnings(record) == [
        "Config 'config': default_from 'remote_user' of metadata field "
        "'listener' has no effect on this server. Only the PHP deployment "
        "fills it in."
    ]


def test_default_from_remote_user_in_a_sequence_warns_once_per_field(
    tmp_path, test_audio_file, monkeypatch
):
    # Every stage carries the first config's metadata form, which is asked
    # once, so it is warned about once. Each stage asks its own survey.
    from listen_and_rate.main import create_app

    metadata = {"fields": [_text_field("listener", "remote_user")]}
    survey = {"fields": [_text_field("login", "remote_user")]}
    paths = [
        write_config(
            tmp_path,
            _config_with_forms(tmp_path, test_audio_file, metadata=metadata),
            "a.yaml",
        ),
        write_config(
            tmp_path,
            _config_with_forms(tmp_path, test_audio_file, survey=survey),
            "b.yaml",
        ),
    ]
    monkeypatch.setenv("LISTEN_AND_RATE_CONFIG", os.pathsep.join(map(str, paths)))
    with pytest.warns(UserWarning) as record:
        asyncio.run(_start(create_app()))
    warned = _remote_user_warnings(record)
    assert len(warned) == 2
    assert "Config 'a'" in warned[0] and "metadata field 'listener'" in warned[0]
    assert "Config 'b'" in warned[1] and "survey field 'login'" in warned[1]
