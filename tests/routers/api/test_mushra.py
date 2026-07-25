"""Tests for the MUSHRA /api/config and /api/submit endpoints."""

from __future__ import annotations

import csv
import json

import pytest

from ._helpers import (
    _PRACTICE,
    _assert_practice_common,
    _mushra_client,
)


def test_mushra_config_returns_trials_with_reference_systems_and_anchor(
    tmp_path, test_audio_file, monkeypatch
):
    with _mushra_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        data = tc.get("/api/config").json()
        assert "trials" in data
        assert "stimuli" not in data
        trial = data["trials"][0]
        assert trial["reference"] is not None
        assert trial["anchor"] is not None
        assert len(trial["systems"]) == 2  # Test0, Test1 (anchor kept separate)


def test_mushra_config_without_reference_or_anchor(
    tmp_path, test_audio_file, monkeypatch
):
    with _mushra_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        n_items=1,
        with_reference=False,
        with_anchor=False,
    ) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        assert trial["reference"] is None
        assert trial["anchor"] is None
        assert len(trial["systems"]) == 2


def test_mushra_config_blinds_system_identity(tmp_path, test_audio_file, monkeypatch):
    with _mushra_client(tmp_path, test_audio_file, monkeypatch) as tc:
        text = json.dumps(tc.get("/api/config").json())
        assert "item" not in text
        assert '"Test0"' not in text
        assert '"Test1"' not in text
        assert '"Reference"' not in text
        assert '"Anchor"' not in text


def test_mushra_config_anchor_never_mixed_into_systems(
    tmp_path, test_audio_file, monkeypatch
):
    with _mushra_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        for _ in range(20):
            trial = tc.get("/api/config").json()["trials"][0]
            system_ids = {s["id"] for s in trial["systems"]}
            assert trial["anchor"]["id"] not in system_ids


def test_mushra_submit_happy_path(tmp_path, test_audio_file, monkeypatch):
    with _mushra_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ratings = [{"stimulus_id": s["id"], "rating": 70} for s in trial["systems"]]
        ratings.append({"stimulus_id": trial["anchor"]["id"], "rating": 20})
        res = tc.post(
            "/api/submit",
            json={"session_id": "s1", "test_type": "mushra", "ratings": ratings},
        )
        assert res.status_code == 200
        rows = list(csv.DictReader((tmp_path / "results" / "config" / "s1.csv").open()))
        assert len(rows) == 3
        systems = {r["system"] for r in rows}
        assert systems == {"Test0", "Test1", "Anchor"}
        for r in rows:
            assert r["item"] == "utt0"


@pytest.mark.parametrize("rating", [-1, 101])
def test_mushra_submit_rating_out_of_range_returns_400(
    tmp_path, test_audio_file, monkeypatch, rating
):
    with _mushra_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ratings = [{"stimulus_id": s["id"], "rating": 50} for s in trial["systems"]]
        ratings.append({"stimulus_id": trial["anchor"]["id"], "rating": rating})
        res = tc.post(
            "/api/submit",
            json={"session_id": "s1", "test_type": "mushra", "ratings": ratings},
        )
        assert res.status_code == 400


def test_mushra_submit_unknown_stimulus_id_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _mushra_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "mushra",
                "ratings": [{"stimulus_id": "nonexistent", "rating": 50}],
            },
        )
        assert res.status_code == 400


def test_mushra_submit_reference_stimulus_id_rejected(
    tmp_path, test_audio_file, monkeypatch
):
    with _mushra_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "mushra",
                "ratings": [{"stimulus_id": trial["reference"]["id"], "rating": 90}],
            },
        )
        assert res.status_code == 400


def test_mushra_submit_incomplete_item_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _mushra_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ratings = [{"stimulus_id": trial["systems"][0]["id"], "rating": 50}]
        res = tc.post(
            "/api/submit",
            json={"session_id": "s1", "test_type": "mushra", "ratings": ratings},
        )
        assert res.status_code == 400


def test_mushra_submit_empty_ratings_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _mushra_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        res = tc.post("/api/submit", json={"session_id": "s1", "test_type": "mushra"})
        assert res.status_code == 400


def test_mushra_config_includes_practice_trials(tmp_path, test_audio_file, monkeypatch):
    with _mushra_client(
        tmp_path, test_audio_file, monkeypatch, practice=_PRACTICE
    ) as tc:
        data = tc.get("/api/config").json()
        _assert_practice_common(data)
        trial = data["practice_trials"][0]
        assert set(trial) == {"reference", "systems", "anchor"}
        assert trial["reference"] is not None
        assert trial["anchor"] is not None
        assert len(trial["systems"]) == 2
