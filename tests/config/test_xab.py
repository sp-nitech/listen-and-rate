"""Tests for XAB (similarity to a reference) test configuration and trial pairing."""

from __future__ import annotations

import shutil

import pytest
from pydantic import ValidationError

from listen_and_rate.config import build_xab_trials, load_config

from ._helpers import stimuli_dirs_data, three_system_dirs, write_config


def _xab_dirs_data(dref, da, db, **kwargs) -> dict:
    return stimuli_dirs_data(
        [
            {"path": str(dref), "reference": True},
            {"path": str(da)},
            {"path": str(db)},
        ],
        test_type="xab",
        **kwargs,
    )


# -- XAB config -------------------------------------------------------------


def test_load_valid_xab_config(tmp_path, test_audio_file):
    dref, da, db = three_system_dirs(tmp_path, test_audio_file)
    result = load_config(write_config(tmp_path, _xab_dirs_data(dref, da, db)))
    assert result.test_type == "xab"
    assert result.reference_system == "sys_ref"


def test_xab_has_no_allow_tie_field(tmp_path, test_audio_file):
    dref, da, db = three_system_dirs(tmp_path, test_audio_file)
    result = load_config(write_config(tmp_path, _xab_dirs_data(dref, da, db)))
    assert not hasattr(result, "allow_tie")


def test_xab_requires_stimuli_dirs_not_explicit_stimuli(tmp_path, test_audio_file):
    data = {
        "test_type": "xab",
        "title": "T",
        "instructions": "I",
        "stimuli_list": {"entries": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_xab_requires_exactly_one_reference(tmp_path, test_audio_file):
    dref, da, db = three_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [{"path": str(dref)}, {"path": str(da)}, {"path": str(db)}],
        test_type="xab",
    )
    with pytest.raises(ValidationError, match="reference"):
        load_config(write_config(tmp_path, data))


def test_xab_rejects_two_references(tmp_path, test_audio_file):
    dref, da, db = three_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [
            {"path": str(dref), "reference": True},
            {"path": str(da), "reference": True},
            {"path": str(db)},
        ],
        test_type="xab",
    )
    with pytest.raises(ValidationError, match="reference"):
        load_config(write_config(tmp_path, data))


def test_xab_requires_exactly_two_test_systems(tmp_path, test_audio_file):
    dref, da, _db = three_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [{"path": str(dref), "reference": True}, {"path": str(da)}],
        test_type="xab",
    )
    with pytest.raises(ValidationError, match="2"):
        load_config(write_config(tmp_path, data))


def test_xab_rejects_three_test_systems(tmp_path, test_audio_file):
    dref, da, db = three_system_dirs(tmp_path, test_audio_file)
    dc = tmp_path / "sys_d"
    dc.mkdir()
    shutil.copy(test_audio_file, dc / "utt1.wav")
    data = stimuli_dirs_data(
        [
            {"path": str(dref), "reference": True},
            {"path": str(da)},
            {"path": str(db)},
            {"path": str(dc)},
        ],
        test_type="xab",
    )
    with pytest.raises(ValidationError, match="2"):
        load_config(write_config(tmp_path, data))


# -- build_xab_trials -------------------------------------------------------


def test_build_xab_trials_pairs_by_item(tmp_path, test_audio_file):
    dref, da, db = three_system_dirs(tmp_path, test_audio_file)
    result = load_config(write_config(tmp_path, _xab_dirs_data(dref, da, db)))
    trials = build_xab_trials(result.stimuli_list.entries, result.reference_system)
    assert len(trials) == 2  # utt1, utt2
    for t in trials:
        assert t.reference_id.startswith("sys_ref__")
        assert t.systems == ("sys_b", "sys_c")
        assert t.stimulus_ids[0].startswith("sys_b__")
        assert t.stimulus_ids[1].startswith("sys_c__")


def test_xab_item_missing_from_one_test_system_is_dropped(tmp_path, test_audio_file):
    dref, da, db = three_system_dirs(tmp_path, test_audio_file)
    (db / "utt2.wav").unlink()
    with pytest.warns(UserWarning, match="not present in all systems"):
        result = load_config(write_config(tmp_path, _xab_dirs_data(dref, da, db)))
    trials = build_xab_trials(result.stimuli_list.entries, result.reference_system)
    assert len(trials) == 1
    assert trials[0].item == "utt1"


def test_xab_item_missing_reference_is_dropped(tmp_path, test_audio_file):
    dref, da, db = three_system_dirs(tmp_path, test_audio_file)
    (dref / "utt2.wav").unlink()
    with pytest.warns(UserWarning, match="not present in all systems"):
        result = load_config(write_config(tmp_path, _xab_dirs_data(dref, da, db)))
    trials = build_xab_trials(result.stimuli_list.entries, result.reference_system)
    assert len(trials) == 1
    assert trials[0].item == "utt1"


def test_xab_no_complete_item_fails_at_load(tmp_path, test_audio_file):
    """A config where no item exists in all three directories fails at load
    (the shared no-common-files check fires before the XAB-specific one)."""
    dref, da, db = three_system_dirs(tmp_path, test_audio_file, items=("utt1",))
    (dref / "utt1.wav").unlink()
    shutil.copy(test_audio_file, dref / "other.wav")
    with pytest.raises(ValueError, match="No common audio files"):
        load_config(write_config(tmp_path, _xab_dirs_data(dref, da, db)))


def test_xab_items_per_session_bound(tmp_path, test_audio_file):
    dref, da, db = three_system_dirs(tmp_path, test_audio_file)
    data = _xab_dirs_data(dref, da, db, items_per_session=3)
    with pytest.raises(ValueError, match="items_per_session"):
        load_config(write_config(tmp_path, data))
