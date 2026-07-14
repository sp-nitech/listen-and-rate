"""Tests for /api/status, /api/config, and the config.php/save.php aliases."""

from __future__ import annotations

import json

from ._helpers import (
    _create_app_client,
)


def test_config_php_alias(client):
    res = client.get("/config.php")
    assert res.status_code == 200
    assert res.json()["title"] == "Test Evaluation"


def test_save_php_alias(client):
    res = client.post(
        "/save.php",
        json={
            "session_id": "alias-test",
            "test_type": "mos",
            "ratings": [
                {"stimulus_id": "s001", "rating": 3},
                {"stimulus_id": "s002", "rating": 4},
            ],
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_status_endpoint(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["test_type"] == "mos"


def test_config_endpoint(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Test Evaluation"
    assert "instructions" in data
    assert len(data["stimuli"]) == 2


def test_config_blinds_sensitive_fields(client):
    text = json.dumps(client.get("/api/config").json())
    assert "path" not in text
    assert "system" not in text


def test_config_includes_preload_audio_default_false(client):
    assert client.get("/api/config").json()["preload_audio"] is False


def test_config_includes_preload_audio_true(tmp_path, test_audio_file, monkeypatch):
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "preload_audio": True,
        "stimuli": {"items": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    with _create_app_client(tmp_path, config, monkeypatch) as tc:
        assert tc.get("/api/config").json()["preload_audio"] is True


def test_config_shortcuts(client):
    shortcuts = client.get("/api/config").json()["shortcuts"]
    assert shortcuts["rating"]["1"] == 1
    assert shortcuts["rating"]["5"] == 5
    assert shortcuts["prev"] == "ArrowLeft"
    assert shortcuts["next"] == "ArrowRight"
    assert shortcuts["confirm"] == "Enter"


def test_config_includes_config_version(client):
    """The response carries a non-empty config_version fingerprint for resume."""
    version = client.get("/api/config").json()["config_version"]
    assert isinstance(version, str) and version


def test_config_version_stable_across_requests(client):
    """The fingerprint is derived from the (unchanging) config, so it never varies.

    It must not pick up the per-request stimulus shuffle/sampling - otherwise
    resume could never match a saved session.
    """
    v1 = client.get("/api/config").json()["config_version"]
    v2 = client.get("/api/config").json()["config_version"]
    assert v1 == v2


def test_config_version_changes_when_config_changes(
    tmp_path, test_audio_file, monkeypatch
):
    """Editing the config (here: the instructions) changes the fingerprint."""
    base = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "stimuli": {"items": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    with _create_app_client(tmp_path, base, monkeypatch) as tc:
        v1 = tc.get("/api/config").json()["config_version"]

    changed = {**base, "instructions": "DIFFERENT"}
    with _create_app_client(tmp_path, changed, monkeypatch) as tc:
        v2 = tc.get("/api/config").json()["config_version"]

    assert v1 != v2
