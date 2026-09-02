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


def test_config_includes_audio_preload_default_auto(client):
    assert client.get("/api/config").json()["audio_preload"] == "auto"


def test_config_includes_clip_durations(client):
    # Served so the player's time bar shows length without a metadata fetch.
    # The fixture clip is 1600 frames at 16 kHz = 0.1 s.
    durations = client.get("/api/config").json()["durations"]
    assert durations["s001"] == 0.1
    assert durations["s002"] == 0.1


def test_config_includes_ui_language_default_en(client):
    assert client.get("/api/config").json()["ui_language"] == "en"


def test_config_reflects_the_configured_ui_language(
    tmp_path, test_audio_file, monkeypatch
):
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "ui_language": "ja",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "stimuli_list": {"entries": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    with _create_app_client(tmp_path, config, monkeypatch) as tc:
        assert tc.get("/api/config").json()["ui_language"] == "ja"


def test_config_includes_resume_window_in_milliseconds(client):
    # The browser compares it against Date.now(), so the hours the config is
    # written in are converted before they reach it.
    assert client.get("/api/config").json()["resume"]["max_age_ms"] == 7_200_000


def test_config_resume_window_reflects_the_configured_hours(
    tmp_path, test_audio_file, monkeypatch
):
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "resume": {"max_age_hours": 0.5},
        "stimuli_list": {"entries": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    with _create_app_client(tmp_path, config, monkeypatch) as tc:
        assert tc.get("/api/config").json()["resume"]["max_age_ms"] == 1_800_000


def test_config_includes_audio_preload_level(tmp_path, test_audio_file, monkeypatch):
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "audio_preload": "none",
        "stimuli_list": {"entries": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    with _create_app_client(tmp_path, config, monkeypatch) as tc:
        assert tc.get("/api/config").json()["audio_preload"] == "none"


def test_config_includes_survey_fields(tmp_path, test_audio_file, monkeypatch):
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "survey": {
            "fields": [
                {
                    "key": "trial_count",
                    "label": "Was the number of trials appropriate?",
                    "type": "select",
                    "options": ["TooFew", "Appropriate", "TooMany"],
                    "required": True,
                }
            ]
        },
        "stimuli_list": {"entries": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    with _create_app_client(tmp_path, config, monkeypatch) as tc:
        survey = tc.get("/api/config").json()["survey"]
        assert survey["title"] == "Questionnaire"
        assert survey["fields"][0]["key"] == "trial_count"
        assert survey["fields"][0]["options"] == ["TooFew", "Appropriate", "TooMany"]


def test_config_survey_defaults_to_empty_form(client):
    assert client.get("/api/config").json()["survey"] == {
        "title": "Questionnaire",
        "description": None,
        "fields": [],
    }


def test_config_includes_form_page_titles(client):
    data = client.get("/api/config").json()
    assert data["metadata"]["title"] == "Listener Information"
    assert data["survey"]["title"] == "Questionnaire"


def test_config_shortcuts(client):
    shortcuts = client.get("/api/config").json()["shortcuts"]
    assert shortcuts["rewind"] == "r"
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
        "stimuli_list": {"entries": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    with _create_app_client(tmp_path, base, monkeypatch) as tc:
        v1 = tc.get("/api/config").json()["config_version"]

    changed = {**base, "instructions": "DIFFERENT"}
    with _create_app_client(tmp_path, changed, monkeypatch) as tc:
        v2 = tc.get("/api/config").json()["config_version"]

    assert v1 != v2


def test_config_version_changes_when_only_the_clip_durations_do(client, config_yaml):
    """Swapping the audio behind unchanged paths must invalidate a resume.

    durations is measured at load time, not written in the YAML, so replacing
    a clip with one of a different length leaves the config model identical.
    It still reaches the browser (the time bar shows it), so a session frozen
    against the old lengths no longer matches. The PHP deployment hashes its
    whole config_data.php, durations included, so this keeps the two agreeing.
    """
    from listen_and_rate.config import load_config
    from listen_and_rate.routers.api._shared import _config_version

    config = load_config(config_yaml)
    before = _config_version(config)
    config._durations = {k: v + 1.0 for k, v in config.durations.items()}
    assert _config_version(config) != before


def test_head_config_php_does_not_fall_through_to_the_php_source(client):
    """HEAD must hit the alias, not the StaticFiles mount behind it.

    FastAPI's methods=["GET"] does not cover HEAD, so without it registered
    the request reaches the catch-all that serves frontend/ and returns the
    raw config.php source instead of the JSON route's headers.
    """
    res = client.head("/config.php")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")


def test_head_save_php_does_not_fall_through_to_the_php_source(client):
    res = client.head("/save.php")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")


def test_config_carries_the_form_page_descriptions(
    tmp_path, test_audio_file, monkeypatch
):
    """The page's prose reaches the browser alongside its title and fields."""
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "metadata": {"description": "Research use only."},
        "survey": {"description": "Thank you."},
        "stimuli_list": {"entries": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    with _create_app_client(tmp_path, config, monkeypatch) as tc:
        data = tc.get("/api/config").json()
        assert data["metadata"]["description"] == "Research use only."
        assert data["survey"]["description"] == "Thank you."
