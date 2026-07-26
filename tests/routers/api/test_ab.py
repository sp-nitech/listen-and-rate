"""Tests for the AB /api/config and /api/submit endpoints."""

from __future__ import annotations

import csv
import json

from ._helpers import (
    _PRACTICE,
    _ab_client,
    _assert_practice_common,
)


def test_ab_config_items_per_session_preserves_order_when_presentation_fixed(
    tmp_path, test_audio_file, monkeypatch
):
    """With presentation_order="fixed", the sampled trial subset must keep its original
    item order (utt0 < utt1 < ...), not an arbitrary permutation."""
    with _ab_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        n_items=6,
        items_per_session=4,
        presentation_order="fixed",
    ) as tc:
        for _ in range(20):
            trials = tc.get("/api/config").json()["trials"]
            # stimulus ids look like "A__utt2"; extract the item index.
            utt_indices = [
                int(trials[i]["stimuli"][0]["id"].split("utt")[1])
                for i in range(len(trials))
            ]
            assert utt_indices == sorted(utt_indices)


def test_ab_config_returns_trials_not_stimuli(tmp_path, test_audio_file, monkeypatch):
    with _ab_client(tmp_path, test_audio_file, monkeypatch) as tc:
        data = tc.get("/api/config").json()
        assert "trials" in data
        assert "stimuli" not in data
        assert len(data["trials"][0]["stimuli"]) == 2


def test_ab_config_blinds_item_and_system(tmp_path, test_audio_file, monkeypatch):
    with _ab_client(tmp_path, test_audio_file, monkeypatch) as tc:
        text = json.dumps(tc.get("/api/config").json())
        assert "item" not in text
        assert "system" not in text
        assert '"A"' not in text
        assert '"B"' not in text


def test_ab_config_exposes_allow_tie(tmp_path, test_audio_file, monkeypatch):
    with _ab_client(tmp_path, test_audio_file, monkeypatch, allow_tie=False) as tc:
        assert tc.get("/api/config").json()["allow_tie"] is False


def test_ab_config_items_per_session_samples_trial_count(
    tmp_path, test_audio_file, monkeypatch
):
    with _ab_client(
        tmp_path, test_audio_file, monkeypatch, n_items=3, items_per_session=1
    ) as tc:
        assert len(tc.get("/api/config").json()["trials"]) == 1


def test_ab_submit_missing_choices_returns_400(tmp_path, test_audio_file, monkeypatch):
    """An ab submission with no choices key must be rejected, not silently accepted."""
    with _ab_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        res = tc.post("/api/submit", json={"session_id": "s1", "test_type": "ab"})
        assert res.status_code == 400


def test_ab_submit_happy_path_preference(tmp_path, test_audio_file, monkeypatch):
    with _ab_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "ab",
                "choices": [{"stimulus_ids": ids, "selected_stimulus_id": ids[0]}],
            },
        )
        assert res.status_code == 200
        rows = list(csv.DictReader((tmp_path / "results" / "config" / "s1.csv").open()))
        assert rows[0]["winner"] in ("a", "b")
        assert {rows[0]["system_a"], rows[0]["system_b"]} == {"A", "B"}
        assert rows[0]["item"] == "utt0"
        # Column order matches MOS's system-first convention.
        assert list(rows[0].keys()) == [
            "tool_version",
            "session_id",
            "timestamp",
            "test_type",
            "system_a",
            "system_b",
            "item",
            "winner",
        ]


def test_ab_submit_tie_recorded_as_tie(tmp_path, test_audio_file, monkeypatch):
    with _ab_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "ab",
                "choices": [{"stimulus_ids": ids, "selected_stimulus_id": None}],
            },
        )
        assert res.status_code == 200
        rows = list(csv.DictReader((tmp_path / "results" / "config" / "s1.csv").open()))
        assert rows[0]["winner"] == "="  # OUTCOME_TIE positional token


def test_ab_submit_tie_rejected_when_allow_tie_false(
    tmp_path, test_audio_file, monkeypatch
):
    with _ab_client(
        tmp_path, test_audio_file, monkeypatch, n_items=1, allow_tie=False
    ) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "ab",
                "choices": [{"stimulus_ids": ids, "selected_stimulus_id": None}],
            },
        )
        assert res.status_code == 400


def test_ab_submit_mismatched_item_pair_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _ab_client(tmp_path, test_audio_file, monkeypatch, n_items=2) as tc:
        trials = tc.get("/api/config").json()["trials"]
        id1 = trials[0]["stimuli"][0]["id"]
        id2 = trials[1]["stimuli"][0]["id"]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "ab",
                "choices": [{"stimulus_ids": [id1, id2], "selected_stimulus_id": id1}],
            },
        )
        assert res.status_code == 400


def test_ab_submit_same_system_pair_returns_400(tmp_path, test_audio_file, monkeypatch):
    with _ab_client(tmp_path, test_audio_file, monkeypatch, n_items=2) as tc:
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "ab",
                "choices": [
                    {
                        "stimulus_ids": ["A__utt0", "A__utt1"],
                        "selected_stimulus_id": "A__utt0",
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_ab_submit_preferred_not_in_pair_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _ab_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "ab",
                "choices": [
                    {"stimulus_ids": ids, "selected_stimulus_id": "unknown-id"}
                ],
            },
        )
        assert res.status_code == 400


def test_ab_submit_unknown_stimulus_id_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _ab_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        good_id = trial["stimuli"][0]["id"]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "ab",
                "choices": [
                    {
                        "stimulus_ids": [good_id, "nonexistent"],
                        "selected_stimulus_id": good_id,
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_ab_config_includes_practice_trials(tmp_path, test_audio_file, monkeypatch):
    with _ab_client(tmp_path, test_audio_file, monkeypatch, practice=_PRACTICE) as tc:
        data = tc.get("/api/config").json()
        _assert_practice_common(data)
        trial = data["practice_trials"][0]
        assert set(trial) == {"stimuli"}
        assert len(trial["stimuli"]) == 2


def test_practice_trials_sampled_independently_of_session(
    tmp_path, test_audio_file, monkeypatch
):
    """Practice draws from the full trial pool, unaffected by items_per_session."""
    with _ab_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        n_items=6,
        items_per_session=2,
        practice={"count": 3, "instructions": "W."},
    ) as tc:
        seen = set()
        for _ in range(30):
            data = tc.get("/api/config").json()
            assert len(data["trials"]) == 2
            assert len(data["practice_trials"]) == 3
            for t in data["practice_trials"]:
                seen.add(t["stimuli"][0]["id"].split("__")[1])
        # Across 30 draws of 3-of-6 items, practice must not be locked
        # to one fixed subset (e.g. the session's own sample).
        assert len(seen) > 3
