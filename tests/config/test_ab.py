"""Tests for AB (paired forced-choice) test configuration and trial pairing."""

from __future__ import annotations

import shutil

import pytest
from pydantic import ValidationError

from listen_and_rate.config import build_ab_trials, load_config

from ._helpers import stimuli_dirs_data, two_system_dirs, write_config

# -- AB config --------------------------------------------------------------


def test_load_valid_ab_config(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="ab")
    result = load_config(write_config(tmp_path, data))
    assert result.test_type == "ab"
    assert result.allow_tie is True


def test_ab_allow_tie_can_be_disabled(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="ab")
    data["allow_tie"] = False
    result = load_config(write_config(tmp_path, data))
    assert result.allow_tie is False


def test_ab_requires_stimuli_dirs_not_explicit_stimuli(tmp_path, test_audio_file):
    data = {
        "test_type": "ab",
        "title": "T",
        "instructions": "I",
        "stimuli": {"entries": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_ab_requires_exactly_two_systems(tmp_path, test_audio_file):
    d = tmp_path / "sys_a"
    d.mkdir()
    shutil.copy(test_audio_file, d / "utt1.wav")
    data = stimuli_dirs_data([{"path": str(d)}], test_type="ab")
    with pytest.raises(ValidationError, match="2"):
        load_config(write_config(tmp_path, data))


def test_ab_requires_exactly_two_systems_not_three(tmp_path, test_audio_file):
    dirs = []
    for name in ("sys_a", "sys_b", "sys_c"):
        d = tmp_path / name
        d.mkdir()
        shutil.copy(test_audio_file, d / "utt1.wav")
        dirs.append({"path": str(d)})
    data = stimuli_dirs_data(dirs, test_type="ab")
    with pytest.raises(ValidationError, match="2"):
        load_config(write_config(tmp_path, data))


def test_ab_unpaired_item_is_dropped_with_warning(tmp_path, test_audio_file):
    da = tmp_path / "sys_a"
    db = tmp_path / "sys_b"
    da.mkdir()
    db.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    shutil.copy(test_audio_file, da / "utt2.wav")
    shutil.copy(test_audio_file, db / "utt1.wav")
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="ab")
    with pytest.warns(UserWarning, match="not present in all systems"):
        result = load_config(write_config(tmp_path, data))
    trials = build_ab_trials(result.stimuli.entries)
    assert len(trials) == 1
    assert trials[0].item == "utt1"


def test_build_ab_trials_pairs_by_item_with_deterministic_system_order(
    tmp_path, test_audio_file
):
    da, db = two_system_dirs(tmp_path, test_audio_file, items=("utt1", "utt2"))
    data = stimuli_dirs_data(
        [{"path": str(db), "system": "B"}, {"path": str(da), "system": "A"}],
        test_type="ab",
    )
    result = load_config(write_config(tmp_path, data))
    trials = build_ab_trials(result.stimuli.entries)
    assert len(trials) == 2
    assert [t.item for t in trials] == ["utt1", "utt2"]
    for t in trials:
        assert t.systems == ("A", "B")


def test_ab_shortcuts_accept_bare_numeric_values(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="ab")
    data["shortcuts"] = {"choose_a": 1, "choose_b": 2, "tie": 3}
    result = load_config(write_config(tmp_path, data))
    assert result.shortcuts.choose_a == "1"
    assert result.shortcuts.choose_b == "2"
    assert result.shortcuts.tie == "3"
