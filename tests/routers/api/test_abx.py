"""Tests for the ABX /api/config and /api/submit endpoints (incl. /audio/x)."""

from __future__ import annotations

import csv
import json

from fastapi.testclient import TestClient

from ._helpers import (
    _PRACTICE,
    _abx_client,
    _assert_practice_common,
)


def test_abx_config_utterances_per_session_preserves_order_when_presentation_fixed(
    tmp_path, test_audio_file, monkeypatch
):
    """With presentation_order="fixed", the sampled trial subset must keep its original
    utterance order (utt0 < utt1 < ...), not an arbitrary permutation."""
    with _abx_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        n_utterances=6,
        utterances_per_session=4,
        presentation_order="fixed",
    ) as tc:
        for _ in range(20):
            trials = tc.get("/api/config").json()["trials"]
            utt_indices = [
                int(trials[i]["stimuli"][0]["id"].split("utt")[1])
                for i in range(len(trials))
            ]
            assert utt_indices == sorted(utt_indices)


def test_x_secret_env_var_makes_secret_stable_across_restarts(
    tmp_path, test_audio_file, monkeypatch
):
    """LISTEN_AND_RATE_X_SECRET pins the ABX blinding secret, so tokens issued
    before a server restart still verify afterwards (without it, each process
    mints its own random secret and in-flight sessions would be lost)."""
    monkeypatch.setenv("LISTEN_AND_RATE_X_SECRET", "fixed-test-secret")
    with _abx_client(tmp_path, test_audio_file, monkeypatch) as tc1:
        secret1 = tc1.app.state.x_secret
    # Same config file, fresh app - simulates a server restart.
    from listen_and_rate.main import create_app

    with TestClient(create_app()) as tc2:
        secret2 = tc2.app.state.x_secret
    assert secret1 == b"fixed-test-secret"
    assert secret1 == secret2


def test_x_secret_is_random_per_process_without_env_var(
    tmp_path, test_audio_file, monkeypatch
):
    monkeypatch.delenv("LISTEN_AND_RATE_X_SECRET", raising=False)
    with _abx_client(tmp_path, test_audio_file, monkeypatch) as tc1:
        secret1 = tc1.app.state.x_secret
    from listen_and_rate.main import create_app

    with TestClient(create_app()) as tc2:
        secret2 = tc2.app.state.x_secret
    assert len(secret1) == 32
    assert secret1 != secret2


def test_abx_config_returns_trials_with_x_token(tmp_path, test_audio_file, monkeypatch):
    with _abx_client(tmp_path, test_audio_file, monkeypatch) as tc:
        data = tc.get("/api/config").json()
        assert "trials" in data
        assert "stimuli" not in data
        assert "allow_tie" not in data
        trial = data["trials"][0]
        assert len(trial["stimuli"]) == 2
        assert "token" in trial["x"]


def test_abx_config_blinds_utterance_and_system(tmp_path, test_audio_file, monkeypatch):
    with _abx_client(tmp_path, test_audio_file, monkeypatch) as tc:
        text = json.dumps(tc.get("/api/config").json())
        assert "utterance" not in text
        assert "system" not in text
        assert '"A"' not in text
        assert '"B"' not in text


def test_abx_x_token_is_not_a_real_stimulus_id(tmp_path, test_audio_file, monkeypatch):
    with _abx_client(tmp_path, test_audio_file, monkeypatch, n_utterances=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        x_token = trial["x"]["token"]
        assert x_token not in ids


def test_abx_config_utterances_per_session_samples_trial_count(
    tmp_path, test_audio_file, monkeypatch
):
    with _abx_client(
        tmp_path, test_audio_file, monkeypatch, n_utterances=3, utterances_per_session=1
    ) as tc:
        assert len(tc.get("/api/config").json()["trials"]) == 1


def test_abx_submit_missing_choices_returns_400(tmp_path, test_audio_file, monkeypatch):
    """An abx submission with no choices key must be rejected, not silently accepted."""
    with _abx_client(tmp_path, test_audio_file, monkeypatch, n_utterances=1) as tc:
        res = tc.post("/api/submit", json={"session_id": "s1", "test_type": "abx"})
        assert res.status_code == 400


def test_abx_submit_scores_exactly_one_of_two_opposite_guesses_correct(
    tmp_path, test_audio_file, monkeypatch
):
    with _abx_client(tmp_path, test_audio_file, monkeypatch, n_utterances=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        x_token = trial["x"]["token"]

        res1 = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "abx",
                "choices": [
                    {
                        "stimulus_ids": ids,
                        "selected_stimulus_id": ids[0],
                        "x_token": x_token,
                    }
                ],
            },
        )
        res2 = tc.post(
            "/api/submit",
            json={
                "session_id": "s2",
                "test_type": "abx",
                "choices": [
                    {
                        "stimulus_ids": ids,
                        "selected_stimulus_id": ids[1],
                        "x_token": x_token,
                    }
                ],
            },
        )
        assert res1.status_code == 200
        assert res2.status_code == 200
        rows1 = list(
            csv.DictReader((tmp_path / "results" / "config" / "s1.csv").open())
        )
        rows2 = list(
            csv.DictReader((tmp_path / "results" / "config" / "s2.csv").open())
        )
        correct1 = rows1[0]["correct"] == "true"
        correct2 = rows2[0]["correct"] == "true"
        assert correct1 != correct2
        # Column order matches MOS's system-first convention.
        assert list(rows1[0].keys()) == [
            "session_id",
            "timestamp",
            "test_type",
            "system_a",
            "system_b",
            "utterance",
            "correct",
        ]
        assert {rows1[0]["system_a"], rows1[0]["system_b"]} == {"A", "B"}
        assert rows1[0]["utterance"] == "utt0"


def test_abx_submit_forged_x_token_returns_400(tmp_path, test_audio_file, monkeypatch):
    with _abx_client(tmp_path, test_audio_file, monkeypatch, n_utterances=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "abx",
                "choices": [
                    {
                        "stimulus_ids": ids,
                        "selected_stimulus_id": ids[0],
                        "x_token": "0" * 20,
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_abx_submit_matched_not_in_pair_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _abx_client(tmp_path, test_audio_file, monkeypatch, n_utterances=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        x_token = trial["x"]["token"]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "abx",
                "choices": [
                    {
                        "stimulus_ids": ids,
                        "selected_stimulus_id": "unknown-id",
                        "x_token": x_token,
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_abx_submit_mismatched_utterance_pair_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _abx_client(tmp_path, test_audio_file, monkeypatch, n_utterances=2) as tc:
        trials = tc.get("/api/config").json()["trials"]
        id1 = trials[0]["stimuli"][0]["id"]
        id2 = trials[1]["stimuli"][0]["id"]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "abx",
                "choices": [
                    {
                        "stimulus_ids": [id1, id2],
                        "selected_stimulus_id": id1,
                        "x_token": "0" * 20,
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_abx_submit_same_system_pair_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _abx_client(tmp_path, test_audio_file, monkeypatch, n_utterances=2) as tc:
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "abx",
                "choices": [
                    {
                        "stimulus_ids": ["sys_a__utt0", "sys_a__utt1"],
                        "selected_stimulus_id": "sys_a__utt0",
                        "x_token": "0" * 20,
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_abx_submit_unknown_stimulus_id_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _abx_client(tmp_path, test_audio_file, monkeypatch, n_utterances=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        good_id = trial["stimuli"][0]["id"]
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "abx",
                "choices": [
                    {
                        "stimulus_ids": [good_id, "nonexistent"],
                        "selected_stimulus_id": good_id,
                        "x_token": "0" * 20,
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_abx_audio_x_resolves_to_real_file(tmp_path, test_audio_file, monkeypatch):
    with _abx_client(tmp_path, test_audio_file, monkeypatch, n_utterances=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        x_token = trial["x"]["token"]
        res = tc.get(f"/audio/x/{x_token}", params={"a": ids[0], "b": ids[1]})
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("audio/")


def test_abx_audio_x_forged_token_returns_404(tmp_path, test_audio_file, monkeypatch):
    with _abx_client(tmp_path, test_audio_file, monkeypatch, n_utterances=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        res = tc.get("/audio/x/" + "0" * 20, params={"a": ids[0], "b": ids[1]})
        assert res.status_code == 404


def test_audio_x_php_alias(tmp_path, test_audio_file, monkeypatch):
    """The frontend uses one relative URL (audio_x.php?token=&a=&b=) in both
    deployment modes, matching the config.php/save.php alias pattern."""
    with _abx_client(tmp_path, test_audio_file, monkeypatch, n_utterances=1) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        ids = [s["id"] for s in trial["stimuli"]]
        x_token = trial["x"]["token"]
        res = tc.get(
            "/audio_x.php", params={"token": x_token, "a": ids[0], "b": ids[1]}
        )
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("audio/")


def test_abx_config_includes_practice_trials_with_x_token(
    tmp_path, test_audio_file, monkeypatch
):
    with _abx_client(tmp_path, test_audio_file, monkeypatch, practice=_PRACTICE) as tc:
        data = tc.get("/api/config").json()
        _assert_practice_common(data)
        trial = data["practice_trials"][0]
        assert set(trial) == {"stimuli", "x"}
        assert len(trial["stimuli"]) == 2
        assert trial["x"]["token"]
