"""Tests for the XAB /api/config and /api/submit endpoints."""

from __future__ import annotations

import csv
import json

from ._helpers import (
    _PRACTICE,
    _assert_practice_common,
    _xab_client,
)


def _closer_token(stimulus_id: str) -> str:
    """Map an id like sys_a__utt0 to its positional closer token (a/b)."""
    return "a" if stimulus_id.startswith("sys_a__") else "b"


def test_xab_config_returns_trials_with_reference_and_pair(
    tmp_path, test_audio_file, monkeypatch
):
    with _xab_client(tmp_path, test_audio_file, monkeypatch) as tc:
        data = tc.get("/api/config").json()
        assert "trials" in data
        assert "stimuli" not in data
        assert "allow_tie" not in data
        for trial in data["trials"]:
            assert trial["reference"]["id"].startswith("ref__")
            assert len(trial["stimuli"]) == 2
            assert "x" not in trial  # no hidden-duplicate token machinery


def test_xab_config_blinds_utterance_and_system(tmp_path, test_audio_file, monkeypatch):
    with _xab_client(tmp_path, test_audio_file, monkeypatch) as tc:
        text = json.dumps(tc.get("/api/config").json())
        assert '"path"' not in text
        assert '"system"' not in text
        assert '"utterance"' not in text


def test_xab_config_utterances_per_session_samples_trial_count(
    tmp_path, test_audio_file, monkeypatch
):
    with _xab_client(
        tmp_path, test_audio_file, monkeypatch, n_utterances=5, utterances_per_session=2
    ) as tc:
        assert len(tc.get("/api/config").json()["trials"]) == 2


def test_xab_config_utterances_per_session_preserves_order_when_presentation_fixed(
    tmp_path, test_audio_file, monkeypatch
):
    """With presentation_order="fixed", the sampled trial subset must keep its original
    utterance order (utt0 < utt1 < ...), not an arbitrary permutation."""
    with _xab_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        n_utterances=6,
        utterances_per_session=4,
        presentation_order="fixed",
    ) as tc:
        for _ in range(20):
            trials = tc.get("/api/config").json()["trials"]
            utt_indices = [int(t["reference"]["id"].split("utt")[1]) for t in trials]
            assert utt_indices == sorted(utt_indices)


def test_xab_submit_happy_path(tmp_path, test_audio_file, monkeypatch):
    with _xab_client(tmp_path, test_audio_file, monkeypatch) as tc:
        trials = tc.get("/api/config").json()["trials"]
        choices = [
            {
                "stimulus_ids": [s["id"] for s in t["stimuli"]],
                "selected_stimulus_id": t["stimuli"][0]["id"],
            }
            for t in trials
        ]
        res = tc.post(
            "/api/submit",
            json={"session_id": "xab-ok", "test_type": "xab", "choices": choices},
        )
        assert res.status_code == 200

        rows = list(
            csv.DictReader((tmp_path / "results" / "config" / "xab-ok.csv").open())
        )
        assert len(rows) == len(trials)
        for row, trial in zip(rows, trials, strict=True):
            assert row["system_a"] == "A"
            assert row["system_b"] == "B"
            assert row["closer"] == _closer_token(trial["stimuli"][0]["id"])
            assert "winner" not in row
        # Column order matches MOS's system-first convention.
        assert list(rows[0].keys()) == [
            "session_id",
            "timestamp",
            "test_type",
            "system_a",
            "system_b",
            "utterance",
            "closer",
        ]


def test_xab_submit_missing_choices_returns_400(tmp_path, test_audio_file, monkeypatch):
    with _xab_client(tmp_path, test_audio_file, monkeypatch, n_utterances=1) as tc:
        res = tc.post("/api/submit", json={"session_id": "s1", "test_type": "xab"})
        assert res.status_code == 400


def test_xab_submit_tie_returns_400(tmp_path, test_audio_file, monkeypatch):
    """XAB is forced-choice: selected_stimulus_id=None (AB's tie) is rejected."""
    with _xab_client(tmp_path, test_audio_file, monkeypatch, n_utterances=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "xab",
                "choices": [
                    {
                        "stimulus_ids": [s["id"] for s in trial["stimuli"]],
                        "selected_stimulus_id": None,
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_xab_submit_selected_not_in_pair_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _xab_client(tmp_path, test_audio_file, monkeypatch, n_utterances=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "xab",
                "choices": [
                    {
                        "stimulus_ids": [s["id"] for s in trial["stimuli"]],
                        "selected_stimulus_id": trial["reference"]["id"],
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_xab_submit_reference_in_pair_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    """The rated pair must be the two test systems - the reference stimulus
    cannot stand in for either of them."""
    with _xab_client(tmp_path, test_audio_file, monkeypatch, n_utterances=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        pair = [trial["reference"]["id"], trial["stimuli"][0]["id"]]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "xab",
                "choices": [{"stimulus_ids": pair, "selected_stimulus_id": pair[1]}],
            },
        )
        assert res.status_code == 400


def test_xab_submit_unknown_stimulus_id_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _xab_client(tmp_path, test_audio_file, monkeypatch, n_utterances=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        good_id = trial["stimuli"][0]["id"]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "xab",
                "choices": [
                    {
                        "stimulus_ids": [good_id, "nonexistent"],
                        "selected_stimulus_id": good_id,
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_xab_config_includes_practice_trials(tmp_path, test_audio_file, monkeypatch):
    with _xab_client(tmp_path, test_audio_file, monkeypatch, practice=_PRACTICE) as tc:
        data = tc.get("/api/config").json()
        _assert_practice_common(data)
        trial = data["practice_trials"][0]
        assert set(trial) == {"reference", "stimuli"}
        assert trial["reference"]["id"].startswith("ref__")
        assert len(trial["stimuli"]) == 2
