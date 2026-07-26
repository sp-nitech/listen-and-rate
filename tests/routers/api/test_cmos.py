"""Tests for the CMOS /api/config and /api/submit endpoints."""

from __future__ import annotations

import csv
import json

import pytest

from ._helpers import (
    _PRACTICE,
    _assert_practice_common,
    _cmos_client,
)


def test_cmos_config_returns_trials_not_stimuli(tmp_path, test_audio_file, monkeypatch):
    with _cmos_client(tmp_path, test_audio_file, monkeypatch) as tc:
        data = tc.get("/api/config").json()
        assert "trials" in data
        assert "stimuli" not in data
        assert len(data["trials"][0]["stimuli"]) == 2


def test_cmos_config_blinds_item_and_system(tmp_path, test_audio_file, monkeypatch):
    with _cmos_client(tmp_path, test_audio_file, monkeypatch) as tc:
        text = json.dumps(tc.get("/api/config").json())
        assert "item" not in text
        assert "system" not in text
        assert '"A"' not in text
        assert '"B"' not in text


def test_cmos_config_items_per_session_samples_trial_count(
    tmp_path, test_audio_file, monkeypatch
):
    with _cmos_client(
        tmp_path, test_audio_file, monkeypatch, n_items=3, items_per_session=1
    ) as tc:
        assert len(tc.get("/api/config").json()["trials"]) == 1


def test_cmos_submit_missing_choices_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _cmos_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        res = tc.post("/api/submit", json={"session_id": "s1", "test_type": "cmos"})
        assert res.status_code == 400


def test_cmos_submit_happy_path(tmp_path, test_audio_file, monkeypatch):
    with _cmos_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "cmos",
                "choices": [{"stimulus_ids": ids, "rating": 2}],
            },
        )
        assert res.status_code == 200
        rows = list(csv.DictReader((tmp_path / "results" / "config" / "s1.csv").open()))
        assert {rows[0]["system_a"], rows[0]["system_b"]} == {"A", "B"}
        assert rows[0]["item"] == "utt0"
        assert rows[0]["rating"] in ("2", "-2")
        # Column order matches MOS's system-first convention.
        assert list(rows[0].keys()) == [
            "tool_version",
            "session_id",
            "timestamp",
            "test_type",
            "system_a",
            "system_b",
            "item",
            "rating",
        ]


def test_cmos_submit_rating_sign_matches_canonical_system_order(
    tmp_path, test_audio_file, monkeypatch
):
    """rating is 'stimulus_ids[1] relative to stimulus_ids[0]'; the stored
    rating must be flipped when stimulus_ids[0] isn't the canonical
    (alphabetically-first) system."""
    with _cmos_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        id_a = next(i for i in ids if i.startswith("A__"))
        id_b = next(i for i in ids if i.startswith("B__"))
        # Submitted as [B, A] with rating=2 ("A is 2 better than B"); stored
        # rows are always canonical system_a(=A)/system_b(=B), so the stored
        # rating must be flipped to -2 ("B is 2 worse than A").
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "cmos",
                "choices": [{"stimulus_ids": [id_b, id_a], "rating": 2}],
            },
        )
        assert res.status_code == 200
        rows = list(csv.DictReader((tmp_path / "results" / "config" / "s1.csv").open()))
        assert rows[0]["system_a"] == "A"
        assert rows[0]["system_b"] == "B"
        assert rows[0]["rating"] == "-2"


def test_cmos_submit_rating_missing_returns_400(tmp_path, test_audio_file, monkeypatch):
    with _cmos_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "cmos",
                "choices": [{"stimulus_ids": ids}],
            },
        )
        assert res.status_code == 400


@pytest.mark.parametrize("rating", [-4, 4])
def test_cmos_submit_rating_out_of_range_returns_400(
    tmp_path, test_audio_file, monkeypatch, rating
):
    with _cmos_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "cmos",
                "choices": [{"stimulus_ids": ids, "rating": rating}],
            },
        )
        assert res.status_code == 400


def test_cmos_submit_mismatched_item_pair_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _cmos_client(tmp_path, test_audio_file, monkeypatch, n_items=2) as tc:
        trials = tc.get("/api/config").json()["trials"]
        id1 = trials[0]["stimuli"][0]["id"]
        id2 = trials[1]["stimuli"][0]["id"]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "cmos",
                "choices": [{"stimulus_ids": [id1, id2], "rating": 1}],
            },
        )
        assert res.status_code == 400


def test_cmos_submit_same_system_pair_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _cmos_client(tmp_path, test_audio_file, monkeypatch, n_items=2) as tc:
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "cmos",
                "choices": [{"stimulus_ids": ["A__utt0", "A__utt1"], "rating": 1}],
            },
        )
        assert res.status_code == 400


def test_cmos_submit_unknown_stimulus_id_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _cmos_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        good_id = trial["stimuli"][0]["id"]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "cmos",
                "choices": [{"stimulus_ids": [good_id, "nonexistent"], "rating": 1}],
            },
        )
        assert res.status_code == 400


def test_cmos_config_includes_practice_trials(tmp_path, test_audio_file, monkeypatch):
    with _cmos_client(tmp_path, test_audio_file, monkeypatch, practice=_PRACTICE) as tc:
        data = tc.get("/api/config").json()
        _assert_practice_common(data)
        trial = data["practice_trials"][0]
        assert set(trial) == {"stimuli"}
        assert len(trial["stimuli"]) == 2
        assert all(set(s) == {"id", "label"} for s in trial["stimuli"])
