"""Tests for DMOS (degradation vs a reference) config and trial pairing."""

from __future__ import annotations

import shutil

import pytest
from pydantic import ValidationError

from listen_and_rate.config import build_dmos_trials, load_config

from ._helpers import (
    stimuli_dirs_data,
    three_system_dirs,
    two_system_dirs,
    write_config,
)

# -- rating_labels validation ------------------------------------------------


def test_dmos_rating_labels_rejects_key_outside_1_to_5(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [{"path": str(da), "reference": True}, {"path": str(db)}], test_type="dmos"
    )
    data["rating_labels"] = {"0": "Out of range"}
    with pytest.raises(ValidationError, match="rating_labels"):
        load_config(write_config(tmp_path, data))


# -- DMOS config ----------------------------------------------------------


def test_load_valid_dmos_config(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "Reference", "reference": True},
            {"path": str(db), "system": "Test"},
        ],
        test_type="dmos",
    )
    result = load_config(write_config(tmp_path, data))
    assert result.test_type == "dmos"
    assert result.reference_system == "Reference"


def test_dmos_requires_exactly_one_reference_zero(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [{"path": str(da), "system": "A"}, {"path": str(db), "system": "B"}],
        test_type="dmos",
    )
    with pytest.raises(ValidationError, match="reference"):
        load_config(write_config(tmp_path, data))


def test_dmos_requires_exactly_one_reference_two(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "A", "reference": True},
            {"path": str(db), "system": "B", "reference": True},
        ],
        test_type="dmos",
    )
    with pytest.raises(ValidationError, match="reference"):
        load_config(write_config(tmp_path, data))


def test_dmos_requires_at_least_one_test_system(tmp_path, test_audio_file):
    da = tmp_path / "sys_ref"
    da.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    data = stimuli_dirs_data(
        [{"path": str(da), "system": "Reference", "reference": True}], test_type="dmos"
    )
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_dmos_requires_stimuli_dirs_not_explicit_stimuli(tmp_path, test_audio_file):
    data = {
        "test_type": "dmos",
        "title": "T",
        "instructions": "I",
        "stimuli_list": {"entries": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_dmos_reference_defaults_to_dir_name_when_system_unset(
    tmp_path, test_audio_file
):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [{"path": str(da), "reference": True}, {"path": str(db)}], test_type="dmos"
    )
    result = load_config(write_config(tmp_path, data))
    assert result.reference_system == "sys_a"


def test_dmos_supports_multiple_test_systems(tmp_path, test_audio_file):
    da, db, dc = three_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "Reference", "reference": True},
            {"path": str(db), "system": "B"},
            {"path": str(dc), "system": "C"},
        ],
        test_type="dmos",
    )
    result = load_config(write_config(tmp_path, data))
    assert result.reference_system == "Reference"


def test_build_dmos_trials_pairs_reference_with_each_test_system(
    tmp_path, test_audio_file
):
    da, db, dc = three_system_dirs(tmp_path, test_audio_file, items=("utt1", "utt2"))
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "Reference", "reference": True},
            {"path": str(db), "system": "B"},
            {"path": str(dc), "system": "C"},
        ],
        test_type="dmos",
    )
    result = load_config(write_config(tmp_path, data))
    stimuli = result.stimuli_list.entries
    trials = build_dmos_trials(stimuli, result.reference_system)
    # 2 items x 2 test systems = 4 trials
    assert len(trials) == 4
    test_systems = {t.test_system for t in trials}
    assert test_systems == {"B", "C"}
    reference_ids = {s.id for s in stimuli if s.system == "Reference"}
    for t in trials:
        assert t.reference_id in reference_ids


def test_build_dmos_trials_skips_item_missing_from_a_system(tmp_path, test_audio_file):
    da = tmp_path / "sys_ref"
    db = tmp_path / "sys_b"
    da.mkdir()
    db.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    shutil.copy(test_audio_file, da / "utt2.wav")
    shutil.copy(test_audio_file, db / "utt1.wav")  # utt2 missing from test system B
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "Reference", "reference": True},
            {"path": str(db), "system": "B"},
        ],
        test_type="dmos",
    )
    with pytest.warns(UserWarning, match="not present in all systems"):
        result = load_config(write_config(tmp_path, data))
    stimuli = result.stimuli_list.entries
    trials = build_dmos_trials(stimuli, result.reference_system)
    assert len(trials) == 1
    assert trials[0].item == "utt1"
