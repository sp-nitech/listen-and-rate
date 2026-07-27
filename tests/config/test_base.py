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
        "stimuli_list": {
            "entries": [{"id": "s001", "path": str(test_audio_file), "system": 1}]
        },
    }
    result = load_config(write_config(tmp_path, data))
    assert result.stimuli_list.entries[0].system == "1"


def test_stimulus_config_label_bare_number_is_coerced_to_str(tmp_path, test_audio_file):
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli_list": {
            "entries": [{"id": "s001", "path": str(test_audio_file), "label": 2}]
        },
    }
    result = load_config(write_config(tmp_path, data))
    assert result.stimuli_list.entries[0].label == "2"


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
    assert result.presentation_order == "random"
    assert result.shuffle_order is True
    assert result.output.format == "csv"
    assert result.output.path == "./results/"


def test_presentation_order_fixed_disables_shuffle(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["presentation_order"] = "fixed"
    result = load_config(write_config(tmp_path, data))
    assert result.presentation_order == "fixed"
    assert result.shuffle_order is False


def test_presentation_order_rejects_unknown_value(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["presentation_order"] = "sorted"
    with pytest.raises(ValidationError, match="presentation_order"):
        load_config(write_config(tmp_path, data))


def test_shortcuts_defaults(tmp_path, test_audio_file):
    s = load_config(
        write_config(tmp_path, minimal_config(str(test_audio_file)))
    ).shortcuts
    assert s.rating == {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5"}
    assert s.prev == "ArrowLeft"
    assert s.next == "ArrowRight"
    assert s.confirm == "Enter"
    assert s.play == "Space"
    assert s.rewind == "r"
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
        "stimuli_list": {"entries": [{"id": "s001", "path": str(test_audio_file)}]},
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
        "rewind",
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


def test_metadata_key_named_like_result_column_is_allowed(tmp_path, test_audio_file):
    # Form answers are stored under a metadata_/survey_ column-name prefix
    # (see storage.py), so a key literally named 'system' lands in
    # metadata_system and can never collide with a result column - no
    # reserved-name list needed.
    data = minimal_config(str(test_audio_file))
    data["metadata"] = {"fields": [{"key": "system", "label": "x", "type": "text"}]}
    result = load_config(write_config(tmp_path, data))
    assert result.metadata.fields[0].key == "system"


def test_forms_default_to_empty(tmp_path, test_audio_file):
    result = load_config(write_config(tmp_path, minimal_config(str(test_audio_file))))
    assert result.metadata.fields == []
    assert result.survey.fields == []


def test_form_page_titles_have_defaults(tmp_path, test_audio_file):
    result = load_config(write_config(tmp_path, minimal_config(str(test_audio_file))))
    assert result.metadata.title == "Listener Information"
    assert result.survey.title == "Questionnaire"


def test_form_page_titles_are_configurable(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["metadata"] = {"title": "参加者情報"}
    data["survey"] = {"title": "アンケート"}
    result = load_config(write_config(tmp_path, data))
    assert result.metadata.title == "参加者情報"
    assert result.survey.title == "アンケート"


def test_survey_parses_fields(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["survey"] = {
        "fields": [
            {
                "key": "trial_count",
                "label": "Was the number of trials appropriate?",
                "type": "select",
                "options": ["TooFew", "Appropriate", "TooMany"],
                "required": True,
            }
        ]
    }
    result = load_config(write_config(tmp_path, data))
    # A form block giving only fields still gets its default title.
    assert result.survey.title == "Questionnaire"
    assert result.survey.fields[0].key == "trial_count"
    assert result.survey.fields[0].options == ["TooFew", "Appropriate", "TooMany"]


@pytest.mark.parametrize("form", ["metadata", "survey"])
def test_duplicate_keys_within_a_form_rejected(tmp_path, test_audio_file, form):
    # Two fields with the same key in ONE form would collide on a single
    # stored column; the same key in metadata AND survey is fine (the
    # prefixes keep metadata_x and survey_x distinct).
    data = minimal_config(str(test_audio_file))
    data[form] = {
        "fields": [
            {"key": "dup", "label": "a", "type": "text"},
            {"key": "dup", "label": "b", "type": "text"},
        ]
    }
    with pytest.raises(ValidationError, match="dup"):
        load_config(write_config(tmp_path, data))


def test_same_key_in_metadata_and_survey_allowed(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["metadata"] = {
        "fields": [{"key": "expectation", "label": "before", "type": "text"}]
    }
    data["survey"] = {
        "fields": [{"key": "expectation", "label": "after", "type": "text"}]
    }
    result = load_config(write_config(tmp_path, data))
    assert result.metadata.fields[0].key == result.survey.fields[0].key == "expectation"


def test_unknown_form_block_field_rejected(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["survey"] = {"titel": "Questionnaire"}
    with pytest.raises(ValidationError, match="titel"):
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
    assert result.loudness_check.per_item is None


def test_loudness_check_parses_both_criteria(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["loudness_check"] = {
        "per_system": {"threshold": 2.0, "verbose": True},
        "per_item": {"threshold": 0.5},
    }
    result = load_config(write_config(tmp_path, data))
    assert result.loudness_check.per_system.threshold == 2.0
    assert result.loudness_check.per_system.verbose is True
    assert result.loudness_check.per_item.threshold == 0.5
    assert result.loudness_check.per_item.verbose is False


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


def test_silence_check_defaults_to_none(tmp_path, test_audio_file):
    result = load_config(write_config(tmp_path, minimal_config(str(test_audio_file))))
    assert result.silence_check is None


def test_silence_check_sides_are_independent(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["silence_check"] = {"leading": {"per_stimulus": {}}}
    result = load_config(write_config(tmp_path, data))
    assert result.silence_check.leading.per_stimulus.threshold == 0.3
    assert result.silence_check.leading.per_item is None
    assert result.silence_check.trailing is None
    assert result.silence_check.floor_db == -50.0


def test_silence_check_parses_both_criteria_on_both_sides(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["silence_check"] = {
        "floor_db": -50.0,
        "leading": {
            "per_stimulus": {"threshold": 0.2, "verbose": True},
            "per_item": {"threshold": 0.1},
        },
        "trailing": {"per_stimulus": {"threshold": 1.0}},
    }
    result = load_config(write_config(tmp_path, data))
    assert result.silence_check.floor_db == -50.0
    assert result.silence_check.leading.per_stimulus.verbose is True
    assert result.silence_check.leading.per_item.threshold == 0.1
    assert result.silence_check.trailing.per_stimulus.threshold == 1.0


def test_silence_check_accepts_a_zero_threshold(tmp_path, test_audio_file):
    # Unlike a loudness difference, "no leading silence at all" is a
    # requirement someone may actually want to state.
    data = minimal_config(str(test_audio_file))
    data["silence_check"] = {"leading": {"per_stimulus": {"threshold": 0}}}
    result = load_config(write_config(tmp_path, data))
    assert result.silence_check.leading.per_stimulus.threshold == 0


def test_silence_check_window_and_hop_defaults(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["silence_check"] = {"leading": {"per_stimulus": {}}}
    result = load_config(write_config(tmp_path, data))
    assert result.silence_check.window_ms == 25.0
    assert result.silence_check.hop_ms == 10.0


def test_silence_check_rejects_a_hop_longer_than_the_window(tmp_path, test_audio_file):
    # Audio between readings would never be looked at.
    data = minimal_config(str(test_audio_file))
    data["silence_check"] = {
        "window_ms": 20.0,
        "hop_ms": 30.0,
        "leading": {"per_stimulus": {}},
    }
    with pytest.raises(ValidationError, match="hop_ms"):
        load_config(write_config(tmp_path, data))


def test_silence_check_allows_a_hop_equal_to_the_window(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["silence_check"] = {
        "window_ms": 20.0,
        "hop_ms": 20.0,
        "leading": {"per_stimulus": {}},
    }
    assert load_config(write_config(tmp_path, data)).silence_check.hop_ms == 20.0


def test_silence_check_rejects_a_non_negative_floor(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["silence_check"] = {"floor_db": 0.0, "leading": {"per_stimulus": {}}}
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_silence_check_rejects_unknown_field(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["silence_check"] = {"leading": {"bogus": 1}}
    with pytest.raises(ValidationError, match="bogus"):
        load_config(write_config(tmp_path, data))


def test_silence_check_can_be_combined_with_loudness_check(tmp_path, test_audio_file):
    # Pure observation, so unlike loudness_check/loudness_normalization there
    # is nothing for it to conflict with.
    data = minimal_config(str(test_audio_file))
    data["loudness_check"] = {"per_system": {}}
    data["silence_check"] = {"leading": {"per_stimulus": {}}}
    result = load_config(write_config(tmp_path, data))
    assert result.loudness_check is not None and result.silence_check is not None


def test_silence_check_can_be_combined_with_loudness_normalization(
    tmp_path, test_audio_file
):
    data = minimal_config(str(test_audio_file))
    data["loudness_normalization"] = {"target": -23.0}
    data["silence_check"] = {"leading": {"per_stimulus": {}}}
    result = load_config(write_config(tmp_path, data))
    assert result.loudness_normalization is not None
    assert result.silence_check is not None


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
    data["loudness_normalization"] = {"scope": "item"}
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


def test_audio_preload_defaults_to_auto(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    result = load_config(write_config(tmp_path, data))
    assert result.audio_preload == "auto"


def test_audio_preload_accepts_each_level(tmp_path, test_audio_file):
    for level in ("none", "auto"):
        data = minimal_config(str(test_audio_file))
        data["audio_preload"] = level
        result = load_config(write_config(tmp_path, data))
        assert result.audio_preload == level


def test_audio_preload_rejects_dropped_metadata_value(tmp_path, test_audio_file):
    # "metadata" was removed once the clip duration is served directly (the
    # time bar no longer needs a client-side metadata fetch to show length).
    data = minimal_config(str(test_audio_file))
    data["audio_preload"] = "metadata"
    with pytest.raises(ValidationError, match="audio_preload"):
        load_config(write_config(tmp_path, data))


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
    data["metadata"] = {
        "fields": [{"key": "listener", "label": "Listener", "requird": True}]
    }
    with pytest.raises(ValidationError, match="requird"):
        load_config(write_config(tmp_path, data))


def test_unknown_output_field_rejected(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["output"] = {"format": "csv", "directory": "./out/"}
    with pytest.raises(ValidationError, match="directory"):
        load_config(write_config(tmp_path, data))


# -- experiment_id ----------------------------------------------------------


def test_experiment_id_defaults_to_the_config_filename(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    result = load_config(write_config(tmp_path, data, name="study-a.yaml"))
    assert result.experiment_id == "study-a"


def test_experiment_id_can_be_set_explicitly(tmp_path, test_audio_file):
    # The escape hatch for a filename that is not path-safe: the results
    # subdirectory is named by this instead.
    data = minimal_config(str(test_audio_file))
    data["experiment_id"] = "my-study"
    result = load_config(write_config(tmp_path, data, name="実験1.yaml"))
    assert result.experiment_id == "my-study"


def test_experiment_id_null_means_unset(tmp_path, test_audio_file):
    """`experiment_id:` written as null is how YAML says "not set".

    Every other optional block in this config takes null that way, and the
    empty-string sentinel this field stores would otherwise reject it with a
    bare type error that explains nothing.
    """
    data = minimal_config(str(test_audio_file))
    data["experiment_id"] = None
    result = load_config(write_config(tmp_path, data, name="study-a.yaml"))
    assert result.experiment_id == "study-a"


def test_experiment_id_rejects_a_path_unsafe_value(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["experiment_id"] = "../escape"
    with pytest.raises(ValidationError, match="experiment_id"):
        load_config(write_config(tmp_path, data))


def test_path_unsafe_config_filename_is_rejected_naming_the_escape_hatch(
    tmp_path, test_audio_file
):
    # Silently rewriting it would let two differently-named experiments pool
    # their results, so the load fails and points at the explicit key.
    data = minimal_config(str(test_audio_file))
    with pytest.raises(ValueError, match="experiment_id"):
        load_config(write_config(tmp_path, data, name="実験1.yaml"))


# -- metrics ----------------------------------------------------------------


def test_metrics_defaults_to_collecting_nothing(tmp_path, test_audio_file):
    """Opt-in, like the metadata and survey forms."""
    data = minimal_config(str(test_audio_file))
    result = load_config(write_config(tmp_path, data))
    assert result.metrics.response_time is False


def test_metrics_response_time_can_be_enabled(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["metrics"] = {"response_time": True}
    result = load_config(write_config(tmp_path, data))
    assert result.metrics.response_time is True


def test_metrics_rejects_an_unknown_key(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["metrics"] = {"respones_time": True}  # typo
    with pytest.raises(ValidationError, match="Unknown field"):
        load_config(write_config(tmp_path, data))


# -- form page description --------------------------------------------------


def test_form_page_description_defaults_to_none(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    result = load_config(write_config(tmp_path, data))
    assert result.metadata.description is None
    assert result.survey.description is None


def test_form_page_description_is_configurable(tmp_path, test_audio_file):
    """Somewhere to state what the collected data is used for.

    Not `instructions`: that word is taken by how to perform the task (and by
    practice's own stage-specific version of it), while this is prose on the
    form page - typically a statement rather than a direction.
    """
    data = minimal_config(str(test_audio_file))
    disclaimer = "Data collected here is used for research only."
    data["metadata"] = {
        "title": "About you",
        "description": disclaimer,
        "fields": [{"key": "listener", "label": "Name"}],
    }
    result = load_config(write_config(tmp_path, data))
    assert result.metadata.title == "About you"
    assert result.metadata.description == disclaimer


def test_form_page_may_carry_a_description_with_no_fields(tmp_path, test_audio_file):
    """A disclaimer alone is a valid use of the page - nothing to collect."""
    data = minimal_config(str(test_audio_file))
    data["metadata"] = {"description": "Research use only."}
    result = load_config(write_config(tmp_path, data))
    assert result.metadata.description == "Research use only."
    assert result.metadata.fields == []
