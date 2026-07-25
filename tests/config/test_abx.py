"""Tests for ABX (discrimination) test configuration and trial pairing."""

from __future__ import annotations

import shutil

import pytest
from pydantic import ValidationError

from listen_and_rate.config import load_config

from ._helpers import stimuli_dirs_data, two_system_dirs, write_config

# -- ABX config -------------------------------------------------------------


def test_load_valid_abx_config(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="abx")
    result = load_config(write_config(tmp_path, data))
    assert result.test_type == "abx"


def test_abx_has_no_allow_tie_field(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="abx")
    result = load_config(write_config(tmp_path, data))
    assert not hasattr(result, "allow_tie")


def test_abx_requires_stimuli_dirs_not_explicit_stimuli(tmp_path, test_audio_file):
    data = {
        "test_type": "abx",
        "title": "T",
        "instructions": "I",
        "stimuli": {"entries": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_abx_requires_exactly_two_systems(tmp_path, test_audio_file):
    d = tmp_path / "sys_a"
    d.mkdir()
    shutil.copy(test_audio_file, d / "utt1.wav")
    data = stimuli_dirs_data([{"path": str(d)}], test_type="abx")
    with pytest.raises(ValidationError, match="2"):
        load_config(write_config(tmp_path, data))
