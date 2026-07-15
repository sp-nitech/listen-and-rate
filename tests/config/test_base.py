"""Tests for BaseTestConfig validation: defaults, coercion, shortcuts, and more."""

from __future__ import annotations

import shutil

import pytest
from pydantic import ValidationError

from listen_and_rate.config import load_config

from ._helpers import (
    minimal_config,
    stimuli_dirs_data,
    two_system_dirs,
    write_config,
)

_ALL_TEST_TYPES = ["mos", "dmos", "cmos", "ab", "abx", "xab", "mushra"]


def test_stimuli_dirs_system_bare_number_is_coerced_to_str(tmp_path, test_audio_file):
    da = tmp_path / "sys_a"
    da.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli_dirs": {"systems": [{"path": str(da), "system": 1}]},
    }
    result = load_config(write_config(tmp_path, data))
    assert result.stimuli_dirs.systems[0].system == "1"


def test_stimulus_config_system_bare_number_is_coerced_to_str(
    tmp_path, test_audio_file
):
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli": {
            "items": [{"id": "s001", "path": str(test_audio_file), "system": 1}]
        },
    }
    result = load_config(write_config(tmp_path, data))
    assert result.stimuli.items[0].system == "1"


def test_stimulus_config_label_bare_number_is_coerced_to_str(tmp_path, test_audio_file):
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli": {
            "items": [{"id": "s001", "path": str(test_audio_file), "label": 2}]
        },
    }
    result = load_config(write_config(tmp_path, data))
    assert result.stimuli.items[0].label == "2"


def test_stimuli_dirs_system_list_value_still_rejected(tmp_path, test_audio_file):
    da = tmp_path / "sys_a"
    da.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli_dirs": {"systems": [{"path": str(da), "system": ["a", "b"]}]},
    }
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_config_defaults(tmp_path, test_audio_file):
    result = load_config(write_config(tmp_path, minimal_config(str(test_audio_file))))
    assert result.randomize is True
    assert result.output.format == "csv"
    assert result.output.path == "./results/"


def test_shortcuts_defaults(tmp_path, test_audio_file):
    s = load_config(
        write_config(tmp_path, minimal_config(str(test_audio_file)))
    ).shortcuts
    assert s.rating == {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5"}
    assert s.prev == "ArrowLeft"
    assert s.next == "ArrowRight"
    assert s.confirm == "Enter"
    assert s.play == "Space"
    assert s.choose_a == "1"
    assert s.choose_b == "2"
    assert s.tie == "3"
    assert s.rate_up == "ArrowUp"
    assert s.rate_down == "ArrowDown"


def test_rate_up_down_shortcuts_accept_bare_numeric_values(tmp_path, test_audio_file):
    """`rate_up: 1` (unquoted YAML number) should work the same as `rate_up: "1"`."""
    data = minimal_config(str(test_audio_file))
    data["shortcuts"] = {"rate_up": 1, "rate_down": 2}
    result = load_config(write_config(tmp_path, data))
    assert result.shortcuts.rate_up == "1"
    assert result.shortcuts.rate_down == "2"


@pytest.mark.parametrize("field", ["title", "instructions"])
def test_required_field_missing_raises_validation_error(
    tmp_path, test_audio_file, field
):
    data = minimal_config(str(test_audio_file))
    del data[field]
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_missing_stimuli_source_raises_validation_error(tmp_path):
    data = {"test_type": "mos", "title": "T", "instructions": "I"}
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_stimuli_and_stimuli_dirs_mutually_exclusive(tmp_path, test_audio_file):
    d = tmp_path / "sys_a"
    d.mkdir()
    shutil.copy(test_audio_file, d / "001.wav")
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli": {"items": [{"id": "s001", "path": str(test_audio_file)}]},
        "stimuli_dirs": {"systems": [{"path": str(d)}]},
    }
    with pytest.raises(ValidationError, match="mutually exclusive"):
        load_config(write_config(tmp_path, data))


def test_invalid_test_type_raises_validation_error(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["test_type"] = "unknown"
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_reference_flag_rejected_for_mos_config(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli_dirs": {
            "systems": [
                {"path": str(da), "system": "A", "reference": True},
                {"path": str(db), "system": "B"},
            ]
        },
    }
    with pytest.raises(ValidationError, match="reference"):
        load_config(write_config(tmp_path, data))


def test_reference_flag_rejected_for_ab_config(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "A", "reference": True},
            {"path": str(db), "system": "B"},
        ],
        test_type="ab",
    )
    with pytest.raises(ValidationError, match="reference"):
        load_config(write_config(tmp_path, data))


def test_reference_flag_rejected_for_abx_config(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "A", "reference": True},
            {"path": str(db), "system": "B"},
        ],
        test_type="abx",
    )
    with pytest.raises(ValidationError, match="reference"):
        load_config(write_config(tmp_path, data))


@pytest.mark.parametrize("test_type", ["mos", "dmos", "cmos", "ab", "abx"])
def test_anchor_flag_rejected_for_non_mushra_configs(
    tmp_path, test_audio_file, test_type
):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    dirs = [
        {"path": str(da), "system": "A", "anchor": True},
        {"path": str(db), "system": "B"},
    ]
    if test_type == "dmos":
        dirs[1]["reference"] = True
        dirs[0]["reference"] = False
    data = stimuli_dirs_data(dirs, test_type=test_type)
    with pytest.raises(ValidationError, match="anchor"):
        load_config(write_config(tmp_path, data))


def _practice_config_data(tmp_path, test_audio_file, test_type):
    """Minimal valid stimuli_dirs config for `test_type`, ready for practice."""
    da, db = two_system_dirs(tmp_path, test_audio_file)
    dirs = [
        {"path": str(da), "system": "A"},
        {"path": str(db), "system": "B"},
    ]
    if test_type in ("dmos", "xab", "mushra"):
        dirs[0]["reference"] = True
    if test_type in ("xab", "mushra"):  # both need 2 non-reference systems
        dc = tmp_path / "sys_c"
        dc.mkdir()
        shutil.copy(test_audio_file, dc / "utt1.wav")
        shutil.copy(test_audio_file, dc / "utt2.wav")
        dirs.append({"path": str(dc), "system": "C"})
    return stimuli_dirs_data(dirs, test_type=test_type)


@pytest.mark.parametrize("test_type", _ALL_TEST_TYPES)
def test_practice_accepted_for_every_test_type(tmp_path, test_audio_file, test_type):
    data = _practice_config_data(tmp_path, test_audio_file, test_type)
    data["practice"] = {"count": 1}
    result = load_config(write_config(tmp_path, data))
    assert result.practice.count == 1


@pytest.mark.parametrize("test_type", _ALL_TEST_TYPES)
def test_practice_count_exceeding_pool_is_rejected_for_every_test_type(
    tmp_path, test_audio_file, test_type
):
    """count is bounded by the practice pool: stimuli for MOS, trials otherwise."""
    data = _practice_config_data(tmp_path, test_audio_file, test_type)
    data["practice"] = {"count": 99}
    with pytest.raises(ValueError, match="practice.count"):
        load_config(write_config(tmp_path, data))


def test_invalid_output_format_raises_validation_error(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["output"] = {"format": "xml"}
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


@pytest.mark.parametrize("raw", ["MOS", "Mos", "mOS"])
def test_test_type_is_case_insensitive(tmp_path, test_audio_file, raw):
    data = minimal_config(str(test_audio_file))
    data["test_type"] = raw
    result = load_config(write_config(tmp_path, data))
    assert result.test_type == "mos"


@pytest.mark.parametrize("raw", ["JSON", "Json"])
def test_output_format_is_case_insensitive(tmp_path, test_audio_file, raw):
    data = minimal_config(str(test_audio_file))
    data["output"] = {"format": raw}
    result = load_config(write_config(tmp_path, data))
    assert result.output.format == "json"


def test_custom_shortcuts_loaded(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["shortcuts"] = {
        "rating": {"1": "a", "2": "b", "3": "c", "4": "d", "5": "e"},
        "prev": "Backspace",
        "next": "Tab",
        "confirm": "Space",
    }
    result = load_config(write_config(tmp_path, data))
    assert result.shortcuts.rating == {"1": "a", "2": "b", "3": "c", "4": "d", "5": "e"}
    assert result.shortcuts.prev == "Backspace"
    assert result.shortcuts.next == "Tab"
    assert result.shortcuts.confirm == "Space"


@pytest.mark.parametrize(
    "field",
    [
        "play",
        "prev",
        "next",
        "confirm",
        "choose_a",
        "choose_b",
        "tie",
        "rate_up",
        "rate_down",
    ],
)
def test_shortcuts_reject_invalid_key_name(tmp_path, test_audio_file, field):
    data = minimal_config(str(test_audio_file))
    data["shortcuts"] = {field: "Spa"}
    with pytest.raises(ValidationError, match="not a valid key"):
        load_config(write_config(tmp_path, data))


def test_shortcuts_accept_single_char_and_named_keys(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["shortcuts"] = {
        "play": "Space",
        "prev": "Backspace",
        "next": "X",
        "confirm": "x",
    }
    result = load_config(write_config(tmp_path, data))
    assert result.shortcuts.play == "Space"
    assert result.shortcuts.next == "X"
    assert result.shortcuts.confirm == "x"


def test_shortcuts_reject_lowercase_named_key(tmp_path, test_audio_file):
    """Case matters: the frontend compares against KeyboardEvent.key exactly."""
    data = minimal_config(str(test_audio_file))
    data["shortcuts"] = {"play": "space"}
    with pytest.raises(ValidationError, match="not a valid key"):
        load_config(write_config(tmp_path, data))


def test_shortcuts_rating_rejects_invalid_key_value(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["shortcuts"] = {"rating": {"1": "Spa"}}
    with pytest.raises(ValidationError, match="not a valid key"):
        load_config(write_config(tmp_path, data))


def test_loudness_check_defaults_to_none(tmp_path, test_audio_file):
    result = load_config(write_config(tmp_path, minimal_config(str(test_audio_file))))
    assert result.loudness_check is None


def test_loudness_check_empty_subblock_enables_with_defaults(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["loudness_check"] = {"per_system": {}}
    result = load_config(write_config(tmp_path, data))
    assert result.loudness_check.per_system is not None
    assert result.loudness_check.per_system.threshold == 1.0
    assert result.loudness_check.per_system.verbose is False
    assert result.loudness_check.per_stimulus is None


def test_loudness_check_parses_both_criteria(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["loudness_check"] = {
        "per_system": {"threshold": 2.0, "verbose": True},
        "per_stimulus": {"threshold": 0.5},
    }
    result = load_config(write_config(tmp_path, data))
    assert result.loudness_check.per_system.threshold == 2.0
    assert result.loudness_check.per_system.verbose is True
    assert result.loudness_check.per_stimulus.threshold == 0.5
    assert result.loudness_check.per_stimulus.verbose is False


def test_loudness_check_rejects_non_positive_threshold(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["loudness_check"] = {"per_system": {"threshold": 0}}
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_loudness_check_rejects_unknown_field(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["loudness_check"] = {"per_system": {"bogus": 1}}
    with pytest.raises(ValidationError, match="bogus"):
        load_config(write_config(tmp_path, data))


def test_loudness_normalization_defaults_to_none(tmp_path, test_audio_file):
    result = load_config(write_config(tmp_path, minimal_config(str(test_audio_file))))
    assert result.loudness_normalization is None


def test_loudness_normalization_empty_subblock_uses_defaults(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["loudness_normalization"] = {}
    result = load_config(write_config(tmp_path, data))
    assert result.loudness_normalization is not None
    assert result.loudness_normalization.target == -23.0
    assert result.loudness_normalization.scope == "stimulus"


def test_loudness_normalization_parses_target_and_scope(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["loudness_normalization"] = {"target": -18.0, "scope": "system"}
    result = load_config(write_config(tmp_path, data))
    assert result.loudness_normalization.target == -18.0
    assert result.loudness_normalization.scope == "system"


@pytest.mark.parametrize("bad_target", [0, 3.0])
def test_loudness_normalization_rejects_non_negative_target(
    tmp_path, test_audio_file, bad_target
):
    data = minimal_config(str(test_audio_file))
    data["loudness_normalization"] = {"target": bad_target}
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_loudness_normalization_rejects_invalid_scope(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["loudness_normalization"] = {"scope": "utterance"}
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_loudness_normalization_rejects_unknown_field(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["loudness_normalization"] = {"bogus": 1}
    with pytest.raises(ValidationError, match="bogus"):
        load_config(write_config(tmp_path, data))


def test_loudness_check_and_normalization_are_mutually_exclusive(
    tmp_path, test_audio_file
):
    data = minimal_config(str(test_audio_file))
    data["loudness_check"] = {"per_system": {}}
    data["loudness_normalization"] = {}
    with pytest.raises(ValidationError, match="loudness_normalization"):
        load_config(write_config(tmp_path, data))


def test_preload_audio_defaults_to_false(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    result = load_config(write_config(tmp_path, data))
    assert result.preload_audio is False


def test_preload_audio_accepts_true(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["preload_audio"] = True
    result = load_config(write_config(tmp_path, data))
    assert result.preload_audio is True


def test_partial_rating_shortcuts_merge_over_defaults(tmp_path, test_audio_file):
    """Rating values not mentioned in a partial shortcuts.rating keep their
    default key instead of losing their shortcut entirely."""
    data = minimal_config(str(test_audio_file))
    data["shortcuts"] = {"rating": {"2": "w"}}
    result = load_config(write_config(tmp_path, data))
    assert result.shortcuts.rating == {"1": "1", "2": "w", "3": "3", "4": "4", "5": "5"}


def test_partial_rating_shortcut_colliding_with_default_key_is_rejected(
    tmp_path, test_audio_file
):
    """Binding rating 2 to key "5" without remapping rating 5 (default key
    "5") would leave one of them unreachable - reject the collision."""
    data = minimal_config(str(test_audio_file))
    data["shortcuts"] = {"rating": {"2": "5"}}
    with pytest.raises(ValidationError, match="same keyboard key"):
        load_config(write_config(tmp_path, data))


def test_rating_shortcut_value_outside_range_is_rejected(tmp_path, test_audio_file):
    """A typo'd rating value (e.g. "7" on MOS's 1-5 scale) would otherwise
    silently add a dead entry alongside the merged defaults."""
    data = minimal_config(str(test_audio_file))
    data["shortcuts"] = {"rating": {"7": "9"}}
    with pytest.raises(ValidationError, match="rating"):
        load_config(write_config(tmp_path, data))


def test_shortcuts_rating_accepts_bare_numeric_keys_and_values(
    tmp_path, test_audio_file
):
    """`1: 1` (unquoted YAML numbers) should work the same as `"1": "1"` -
    users shouldn't need to know quoting matters here."""
    data = minimal_config(str(test_audio_file))
    data["shortcuts"] = {"rating": {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}}
    result = load_config(write_config(tmp_path, data))
    assert result.shortcuts.rating == {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5"}


def test_shortcuts_rating_rejects_duplicate_key_binding(tmp_path, test_audio_file):
    """Two different rating values assigned the same keyboard key would leave
    one of them unreachable from the keyboard - must be rejected."""
    data = minimal_config(str(test_audio_file))
    data["shortcuts"] = {"rating": {"1": "a", "2": "a", "3": "c", "4": "d", "5": "e"}}
    with pytest.raises(ValidationError, match="duplicate"):
        load_config(write_config(tmp_path, data))


def test_unknown_shortcuts_field_rejected(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["shortcuts"] = {"rateup": "ArrowUp"}
    with pytest.raises(ValidationError, match="rateup"):
        load_config(write_config(tmp_path, data))


def test_unknown_top_level_field_rejected(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["titel"] = "typo'd title key"
    with pytest.raises(ValidationError, match="titel"):
        load_config(write_config(tmp_path, data))


def test_unknown_stimuli_dirs_systems_field_rejected(tmp_path, test_audio_file):
    da = tmp_path / "sys_a"
    da.mkdir()
    shutil.copy(test_audio_file, da / "001.wav")
    data = stimuli_dirs_data([{"path": str(da), "referance": True}])
    with pytest.raises(ValidationError, match="referance"):
        load_config(write_config(tmp_path, data))


def test_unknown_metadata_field_rejected(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["metadata"] = [{"key": "listener", "label": "Listener", "requird": True}]
    with pytest.raises(ValidationError, match="requird"):
        load_config(write_config(tmp_path, data))


def test_unknown_output_field_rejected(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["output"] = {"format": "csv", "directory": "./out/"}
    with pytest.raises(ValidationError, match="directory"):
        load_config(write_config(tmp_path, data))
