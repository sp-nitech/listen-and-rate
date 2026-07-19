"""Tests for MOS stimulus sampling and the MOS practice stage."""

from __future__ import annotations

from ._helpers import (
    _create_app_client,
    _make_stimuli_dirs_config,
    _mos_practice_config,
)


def test_utterances_per_session_samples_correctly(
    tmp_path, test_audio_file, monkeypatch
):
    """Select N utterances, include every system for each, no duplicate ids."""
    config = _make_stimuli_dirs_config(
        tmp_path, test_audio_file, n_utterances=5, n_systems=3, utterances_per_session=2
    )
    with _create_app_client(tmp_path, config, monkeypatch) as tc:
        stimuli = tc.get("/api/config").json()["stimuli"]
        assert len(stimuli) == 6  # 2 utterances × 3 systems

        ids = [s["id"] for s in stimuli]
        assert len(ids) == len(set(ids))

        # Extract utterance index from IDs like "sys_0__utt2"
        from collections import Counter

        utt_counts = Counter(id_.split("__")[1] for id_ in ids)
        # Every selected utterance must appear exactly once per system (3 times)
        assert all(count == 3 for count in utt_counts.values())


def test_stimuli_per_session_samples_correctly(tmp_path, test_audio_file, monkeypatch):
    """Returns a subset of the requested size with no duplicate ids."""
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "stimuli": {
            "stimuli_per_session": 3,
            "items": [
                {"id": f"s{i:03d}", "path": str(test_audio_file)} for i in range(10)
            ],
        },
    }
    with _create_app_client(tmp_path, config, monkeypatch) as tc:
        stimuli = tc.get("/api/config").json()["stimuli"]
        assert len(stimuli) == 3

        ids = [s["id"] for s in stimuli]
        assert len(ids) == len(set(ids))


def test_stimuli_per_session_keeps_order_when_presentation_fixed(
    tmp_path, test_audio_file, monkeypatch
):
    """presentation_order:fixed means the sampled subset keeps the configured order.

    Mirrors frontend/config.php's sample_keep_order(); random.sample() alone
    would return the subset in random order.
    """
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "presentation_order": "fixed",
        "stimuli": {
            "stimuli_per_session": 3,
            "items": [
                {"id": f"s{i:03d}", "path": str(test_audio_file)} for i in range(10)
            ],
        },
    }
    with _create_app_client(tmp_path, config, monkeypatch) as tc:
        # The subset is random, so check ordering across many draws: a random
        # permutation of 3 items is already sorted only 1/6 of the time.
        for _ in range(30):
            ids = [s["id"] for s in tc.get("/api/config").json()["stimuli"]]
            assert ids == sorted(ids)


def test_config_omits_practice_fields_when_not_configured(client):
    data = client.get("/api/config").json()
    assert "practice_stimuli" not in data
    assert "practice_instructions" not in data


def test_config_omits_practice_fields_when_count_is_zero(
    tmp_path, test_audio_file, monkeypatch
):
    config = _mos_practice_config(tmp_path, test_audio_file, 4, {"count": 0})
    with _create_app_client(tmp_path, config, monkeypatch) as tc:
        data = tc.get("/api/config").json()
        assert "practice_stimuli" not in data
        assert "practice_instructions" not in data


def test_config_includes_practice_stimuli_and_instructions(
    tmp_path, test_audio_file, monkeypatch
):
    config = _mos_practice_config(
        tmp_path, test_audio_file, 4, {"count": 2, "instructions": "Warm-up."}
    )
    with _create_app_client(tmp_path, config, monkeypatch) as tc:
        data = tc.get("/api/config").json()
        assert data["practice_instructions"] == "Warm-up."
        assert len(data["practice_stimuli"]) == 2
        pool_ids = {f"s{i:03d}" for i in range(4)}
        for s in data["practice_stimuli"]:
            assert set(s) == {"id", "label"}  # blinded: no path/system/utterance
            assert s["id"] in pool_ids


def test_practice_sampling_is_independent_of_session_sampling(
    tmp_path, test_audio_file, monkeypatch
):
    """Practice draws from the full pool, unaffected by stimuli_per_session."""
    config = _mos_practice_config(tmp_path, test_audio_file, 10, {"count": 3})
    config["stimuli"]["stimuli_per_session"] = 2
    with _create_app_client(tmp_path, config, monkeypatch) as tc:
        seen_practice_ids = set()
        for _ in range(30):
            data = tc.get("/api/config").json()
            assert len(data["stimuli"]) == 2
            assert len(data["practice_stimuli"]) == 3
            practice_ids = [s["id"] for s in data["practice_stimuli"]]
            assert len(practice_ids) == len(set(practice_ids))
            seen_practice_ids.update(practice_ids)
        # Across 30 draws of 3-of-10, practice must not be locked to one
        # fixed subset (e.g. the session's own sample).
        assert len(seen_practice_ids) > 3
