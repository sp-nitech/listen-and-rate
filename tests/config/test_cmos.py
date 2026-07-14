"""Tests for CMOS (comparative MOS / ITU-T P.800 CCR) test configuration."""

from __future__ import annotations

import shutil

import pytest
from pydantic import ValidationError

from listen_and_rate.config import load_config

from ._helpers import stimuli_dirs_data, two_system_dirs, write_config

# -- CMOS config ------------------------------------------------------------


def test_load_valid_cmos_config(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="cmos")
    result = load_config(write_config(tmp_path, data))
    assert result.test_type == "cmos"


def test_cmos_default_shortcuts_use_signed_seven_point_scale(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="cmos")
    result = load_config(write_config(tmp_path, data))
    assert result.shortcuts.rating == {
        "-3": "1",
        "-2": "2",
        "-1": "3",
        "0": "4",
        "1": "5",
        "2": "6",
        "3": "7",
    }


def test_cmos_partial_rating_shortcuts_merge_over_cmos_defaults(
    tmp_path, test_audio_file
):
    """Rating values not mentioned in a partial shortcuts.rating keep their
    CMOS default key instead of losing their shortcut entirely."""
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="cmos")
    data["shortcuts"] = {"rating": {"-3": "0", "-2": "2"}}
    result = load_config(write_config(tmp_path, data))
    assert result.shortcuts.rating == {
        "-3": "0",  # overridden
        "-2": "2",  # overridden (same as default)
        "-1": "3",  # defaults below
        "0": "4",
        "1": "5",
        "2": "6",
        "3": "7",
    }


def test_cmos_partial_rating_shortcut_colliding_with_default_key_is_rejected(
    tmp_path, test_audio_file
):
    """Binding -3 to key "4" without also remapping 0 (whose default key is
    "4") would leave one of them unreachable - reject instead of silently
    dropping one side in the inverted browser map."""
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="cmos")
    data["shortcuts"] = {"rating": {"-3": "4"}}
    with pytest.raises(ValidationError, match="same keyboard key"):
        load_config(write_config(tmp_path, data))


def test_cmos_rating_shortcut_value_outside_range_is_rejected(
    tmp_path, test_audio_file
):
    """A typo'd rating value (e.g. "5" on CMOS's -3..3 scale) would otherwise
    silently add a dead entry alongside the merged defaults."""
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="cmos")
    data["shortcuts"] = {"rating": {"5": "9"}}
    with pytest.raises(ValidationError, match="rating"):
        load_config(write_config(tmp_path, data))


def test_cmos_shortcuts_rating_accepts_bare_numeric_keys_and_values(
    tmp_path, test_audio_file
):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="cmos")
    data["shortcuts"] = {"rating": {-3: 1, -2: 2, -1: 3, 0: 4, 1: 5, 2: 6, 3: 7}}
    result = load_config(write_config(tmp_path, data))
    assert result.shortcuts.rating == {
        "-3": "1",
        "-2": "2",
        "-1": "3",
        "0": "4",
        "1": "5",
        "2": "6",
        "3": "7",
    }


def test_cmos_shortcuts_rating_rejects_duplicate_key_binding(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="cmos")
    data["shortcuts"] = {
        "rating": {
            "-3": "1",
            "-2": "1",
            "-1": "3",
            "0": "4",
            "1": "5",
            "2": "6",
            "3": "7",
        }
    }
    with pytest.raises(ValidationError, match="duplicate"):
        load_config(write_config(tmp_path, data))


def test_cmos_rating_labels_rejects_key_outside_minus_3_to_3(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="cmos")
    data["rating_labels"] = {"33": "Much better"}
    with pytest.raises(ValidationError, match="rating_labels"):
        load_config(write_config(tmp_path, data))


def test_cmos_rating_labels_accepts_plus_prefixed_positive_keys(
    tmp_path, test_audio_file
):
    """ "+3" is how a positive score is displayed in the UI (see cmos.js's
    formatScore()), so it's a natural thing to write in rating_labels too -
    normalize it to the bare "3" form actually used for lookups."""
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="cmos")
    data["rating_labels"] = {"+3": "Much better", "+1": "Slightly better"}
    result = load_config(write_config(tmp_path, data))
    assert result.rating_labels == {"3": "Much better", "1": "Slightly better"}


def test_cmos_rating_labels_accepts_valid_keys(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="cmos")
    data["rating_labels"] = {"-3": "Much worse", "3": "Much better"}
    result = load_config(write_config(tmp_path, data))
    assert result.rating_labels == {"-3": "Much worse", "3": "Much better"}


def test_cmos_rating_labels_accepts_bare_numeric_keys(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="cmos")
    data["rating_labels"] = {-3: "Much worse", 0: "About the same", 3: "Much better"}
    result = load_config(write_config(tmp_path, data))
    assert result.rating_labels == {
        "-3": "Much worse",
        "0": "About the same",
        "3": "Much better",
    }


def test_cmos_requires_stimuli_dirs_not_explicit_stimuli(tmp_path, test_audio_file):
    data = {
        "test_type": "cmos",
        "title": "T",
        "instructions": "I",
        "stimuli": {"items": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_cmos_requires_exactly_two_systems(tmp_path, test_audio_file):
    d = tmp_path / "sys_a"
    d.mkdir()
    shutil.copy(test_audio_file, d / "utt1.wav")
    data = stimuli_dirs_data([{"path": str(d)}], test_type="cmos")
    with pytest.raises(ValidationError, match="2"):
        load_config(write_config(tmp_path, data))
