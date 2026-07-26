"""Tests for MUSHRA (ITU-R BS.1534) test configuration and trial grouping."""

from __future__ import annotations

import shutil

import pytest
from pydantic import ValidationError

from listen_and_rate.config import build_mushra_trials, load_config

from ._helpers import (
    stimuli_dirs_data,
    three_system_dirs,
    two_system_dirs,
    write_config,
)

# -- MUSHRA config ----------------------------------------------------------


def test_load_valid_mushra_config_with_reference_and_anchor(tmp_path, test_audio_file):
    da, db, dc = three_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "Reference", "reference": True},
            {"path": str(db), "system": "B"},
            {"path": str(dc), "system": "Anchor", "anchor": True},
        ],
        test_type="mushra",
    )
    result = load_config(write_config(tmp_path, data))
    assert result.test_type == "mushra"
    assert result.reference_system == "Reference"
    assert result.anchor_system == "Anchor"


def test_load_valid_mushra_config_without_reference(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [{"path": str(da), "system": "A"}, {"path": str(db), "system": "B"}],
        test_type="mushra",
    )
    result = load_config(write_config(tmp_path, data))
    assert result.reference_system is None


def test_load_valid_mushra_config_without_anchor(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [{"path": str(da), "system": "A"}, {"path": str(db), "system": "B"}],
        test_type="mushra",
    )
    result = load_config(write_config(tmp_path, data))
    assert result.anchor_system is None


def test_mushra_rejects_two_references(tmp_path, test_audio_file):
    da, db, dc = three_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "A", "reference": True},
            {"path": str(db), "system": "B", "reference": True},
            {"path": str(dc), "system": "C"},
        ],
        test_type="mushra",
    )
    with pytest.raises(ValidationError, match="reference"):
        load_config(write_config(tmp_path, data))


def test_mushra_rejects_two_anchors(tmp_path, test_audio_file):
    da, db, dc = three_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "A", "anchor": True},
            {"path": str(db), "system": "B", "anchor": True},
            {"path": str(dc), "system": "C"},
        ],
        test_type="mushra",
    )
    with pytest.raises(ValidationError, match="anchor"):
        load_config(write_config(tmp_path, data))


def test_mushra_rejects_entry_that_is_both_reference_and_anchor(
    tmp_path, test_audio_file
):
    """A single entry flagged reference AND anchor is a config mistake: the
    reference is excluded from rating, so its anchor flag would silently do
    nothing - reject it instead of quietly ignoring it."""
    da, db, dc = three_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "Ref", "reference": True, "anchor": True},
            {"path": str(db), "system": "B"},
            {"path": str(dc), "system": "C"},
        ],
        test_type="mushra",
    )
    with pytest.raises(ValidationError, match="both"):
        load_config(write_config(tmp_path, data))


def test_mushra_reference_plus_anchor_only_is_rejected(tmp_path, test_audio_file):
    """With only a reference and an anchor (no ordinary test system), just one
    rateable system remains - below MUSHRA's minimum of two."""
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "Reference", "reference": True},
            {"path": str(db), "system": "Anchor", "anchor": True},
        ],
        test_type="mushra",
    )
    with pytest.raises(ValidationError, match="rateable"):
        load_config(write_config(tmp_path, data))


def test_mushra_requires_at_least_two_rateable_systems(tmp_path, test_audio_file):
    da = tmp_path / "sys_ref"
    da.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    db = tmp_path / "sys_b"
    db.mkdir()
    shutil.copy(test_audio_file, db / "utt1.wav")
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "Reference", "reference": True},
            {"path": str(db), "system": "B"},
        ],
        test_type="mushra",
    )
    with pytest.raises(ValidationError, match="rateable"):
        load_config(write_config(tmp_path, data))


def test_mushra_requires_stimuli_dirs_not_explicit_stimuli(tmp_path, test_audio_file):
    data = {
        "test_type": "mushra",
        "title": "T",
        "instructions": "I",
        "stimuli_list": {"entries": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


# -- rating_labels validation ------------------------------------------------


def test_mushra_rating_labels_rejects_key_outside_bands(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [{"path": str(da), "system": "A"}, {"path": str(db), "system": "B"}],
        test_type="mushra",
    )
    data["rating_labels"] = {"10": "Not a band boundary"}
    with pytest.raises(ValidationError, match="rating_labels"):
        load_config(write_config(tmp_path, data))


def test_mushra_rating_labels_accepts_valid_keys(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [{"path": str(da), "system": "A"}, {"path": str(db), "system": "B"}],
        test_type="mushra",
    )
    data["rating_labels"] = {"0": "Bad", "80": "Excellent"}
    result = load_config(write_config(tmp_path, data))
    assert result.rating_labels == {"0": "Bad", "80": "Excellent"}


def test_mushra_rating_labels_accepts_bare_numeric_keys(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [{"path": str(da), "system": "A"}, {"path": str(db), "system": "B"}],
        test_type="mushra",
    )
    data["rating_labels"] = {
        0: "Bad",
        20: "Poor",
        40: "Fair",
        60: "Good",
        80: "Excellent",
    }
    result = load_config(write_config(tmp_path, data))
    assert result.rating_labels == {
        "0": "Bad",
        "20": "Poor",
        "40": "Fair",
        "60": "Good",
        "80": "Excellent",
    }


# -- build_mushra_trials --------------------------------------------------


def test_build_mushra_trials_pairs_reference_and_anchor_with_all_systems(
    tmp_path, test_audio_file
):
    da, db, dc = three_system_dirs(tmp_path, test_audio_file, items=("utt1", "utt2"))
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "Reference", "reference": True},
            {"path": str(db), "system": "B"},
            {"path": str(dc), "system": "Anchor", "anchor": True},
        ],
        test_type="mushra",
    )
    result = load_config(write_config(tmp_path, data))
    stimuli = result.stimuli_list.entries
    rateable = {"B", "Anchor"}
    trials = build_mushra_trials(stimuli, result.reference_system, rateable)
    assert len(trials) == 2
    for t in trials:
        assert t.reference_id is not None
        assert {system for system, _ in t.system_ids} == rateable


def test_build_mushra_trials_without_reference(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file, items=("utt1",))
    data = stimuli_dirs_data(
        [{"path": str(da), "system": "A"}, {"path": str(db), "system": "B"}],
        test_type="mushra",
    )
    result = load_config(write_config(tmp_path, data))
    stimuli = result.stimuli_list.entries
    trials = build_mushra_trials(stimuli, result.reference_system, {"A", "B"})
    assert len(trials) == 1
    assert trials[0].reference_id is None


def test_build_mushra_trials_skips_item_missing_from_a_system(
    tmp_path, test_audio_file
):
    da = tmp_path / "sys_ref"
    db = tmp_path / "sys_b"
    dc = tmp_path / "sys_c"
    da.mkdir()
    db.mkdir()
    dc.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    shutil.copy(test_audio_file, da / "utt2.wav")
    shutil.copy(test_audio_file, db / "utt1.wav")
    shutil.copy(test_audio_file, db / "utt2.wav")
    shutil.copy(test_audio_file, dc / "utt1.wav")  # utt2 missing from system C
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "Reference", "reference": True},
            {"path": str(db), "system": "B"},
            {"path": str(dc), "system": "C"},
        ],
        test_type="mushra",
    )
    with pytest.warns(UserWarning, match="not present in all systems"):
        result = load_config(write_config(tmp_path, data))
    stimuli = result.stimuli_list.entries
    trials = build_mushra_trials(stimuli, result.reference_system, {"B", "C"})
    assert len(trials) == 1
    assert trials[0].item == "utt1"


def test_mushra_items_per_session_exceeds_trial_count_raises(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file, items=("utt1",))
    data = stimuli_dirs_data(
        [{"path": str(da), "system": "A"}, {"path": str(db), "system": "B"}],
        test_type="mushra",
        items_per_session=5,
    )
    with pytest.raises(ValueError, match="items_per_session"):
        load_config(write_config(tmp_path, data))
