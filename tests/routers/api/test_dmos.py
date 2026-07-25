"""Tests for the DMOS /api/config and /api/submit endpoints."""

from __future__ import annotations

import csv
import json

from ._helpers import (
    _PRACTICE,
    _assert_practice_common,
    _dmos_client,
)


def test_dmos_config_returns_trials_not_stimuli(tmp_path, test_audio_file, monkeypatch):
    with _dmos_client(tmp_path, test_audio_file, monkeypatch) as tc:
        data = tc.get("/api/config").json()
        assert "trials" in data
        assert "stimuli" not in data
        assert "reference" in data["trials"][0]
        assert "test" in data["trials"][0]


def test_dmos_config_blinds_item_and_system(tmp_path, test_audio_file, monkeypatch):
    with _dmos_client(tmp_path, test_audio_file, monkeypatch) as tc:
        text = json.dumps(tc.get("/api/config").json())
        assert "item" not in text
        assert '"Test0"' not in text
        assert '"Reference"' not in text


def test_dmos_config_multiple_test_systems_produces_multiple_trials(
    tmp_path, test_audio_file, monkeypatch
):
    with _dmos_client(
        tmp_path, test_audio_file, monkeypatch, n_items=1, n_test_systems=2
    ) as tc:
        trials = tc.get("/api/config").json()["trials"]
        assert len(trials) == 2  # 1 item x 2 test systems


def test_dmos_submit_happy_path(tmp_path, test_audio_file, monkeypatch):
    with _dmos_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "dmos",
                "ratings": [
                    {
                        "stimulus_id": trial["test"]["id"],
                        "reference_id": trial["reference"]["id"],
                        "rating": 4,
                    }
                ],
            },
        )
        assert res.status_code == 200
        rows = list(csv.DictReader((tmp_path / "results" / "config" / "s1.csv").open()))
        assert rows[0]["system"] == "Test0"
        assert rows[0]["item"] == "utt0"
        assert rows[0]["rating"] == "4"


def test_dmos_submit_missing_reference_id_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _dmos_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "dmos",
                "ratings": [{"stimulus_id": trial["test"]["id"], "rating": 4}],
            },
        )
        assert res.status_code == 400


def test_dmos_submit_rating_out_of_range_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _dmos_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "dmos",
                "ratings": [
                    {
                        "stimulus_id": trial["test"]["id"],
                        "reference_id": trial["reference"]["id"],
                        "rating": 6,
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_dmos_submit_reference_id_not_actually_reference_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _dmos_client(
        tmp_path, test_audio_file, monkeypatch, n_items=1, n_test_systems=2
    ) as tc:
        trials = tc.get("/api/config").json()["trials"]
        # Use two test-system stimuli as if one were the reference - invalid.
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "dmos",
                "ratings": [
                    {
                        "stimulus_id": trials[0]["test"]["id"],
                        "reference_id": trials[1]["test"]["id"],
                        "rating": 3,
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_dmos_submit_stimulus_id_is_reference_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _dmos_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "dmos",
                "ratings": [
                    {
                        "stimulus_id": trial["reference"]["id"],
                        "reference_id": trial["reference"]["id"],
                        "rating": 3,
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_dmos_submit_mismatched_item_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _dmos_client(tmp_path, test_audio_file, monkeypatch, n_items=2) as tc:
        trials = tc.get("/api/config").json()["trials"]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "dmos",
                "ratings": [
                    {
                        "stimulus_id": trials[0]["test"]["id"],
                        "reference_id": trials[1]["reference"]["id"],
                        "rating": 3,
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_dmos_submit_empty_ratings_returns_400(tmp_path, test_audio_file, monkeypatch):
    with _dmos_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        res = tc.post("/api/submit", json={"session_id": "s1", "test_type": "dmos"})
        assert res.status_code == 400


def test_dmos_submit_unknown_stimulus_id_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _dmos_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "dmos",
                "ratings": [
                    {
                        "stimulus_id": "nonexistent",
                        "reference_id": trial["reference"]["id"],
                        "rating": 3,
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_dmos_config_includes_practice_trials(tmp_path, test_audio_file, monkeypatch):
    with _dmos_client(tmp_path, test_audio_file, monkeypatch, practice=_PRACTICE) as tc:
        data = tc.get("/api/config").json()
        _assert_practice_common(data)
        trial = data["practice_trials"][0]
        assert set(trial) == {"reference", "test"}
        assert set(trial["reference"]) == {"id", "label"}
        assert set(trial["test"]) == {"id", "label"}


def test_dmos_config_omits_practice_fields_when_not_configured(
    tmp_path, test_audio_file, monkeypatch
):
    with _dmos_client(tmp_path, test_audio_file, monkeypatch) as tc:
        data = tc.get("/api/config").json()
        assert "practice_trials" not in data
        assert "practice_instructions" not in data


def test_practice_trials_blind_sensitive_fields(tmp_path, test_audio_file, monkeypatch):
    with _dmos_client(tmp_path, test_audio_file, monkeypatch, practice=_PRACTICE) as tc:
        text = json.dumps(tc.get("/api/config").json())
        assert "item" not in text
        assert '"Test0"' not in text
        assert '"Reference"' not in text
