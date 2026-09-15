"""Tests for ABX (discrimination) test configuration and trial pairing."""

from __future__ import annotations

from listen_and_rate.config import load_config

from ._helpers import stimuli_dirs_data, two_system_dirs, write_config

# -- ABX config -------------------------------------------------------------


def test_abx_has_no_allow_tie_field(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="abx")
    result = load_config(write_config(tmp_path, data))
    assert not hasattr(result, "allow_tie")
