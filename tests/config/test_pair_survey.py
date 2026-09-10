"""Tests for pair_survey configuration and per-rater assignments."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from listen_and_rate.config import load_config

from ._helpers import stimuli_dirs_data, two_system_dirs, write_config


def _questions(**overrides):
    q = {
        "key": "similarity",
        "label": "How similar?",
        "type": "scale",
        "min": 1,
        "max": 5,
    }
    q.update(overrides)
    return [q]


def _pair_survey_data(tmp_path, test_audio_file, questions=None, **kwargs):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "A", "reference": True},
            {"path": str(db), "system": "B"},
        ],
        test_type="pair_survey",
    )
    data["questions"] = questions if questions is not None else _questions()
    data.update(kwargs)
    return data


def test_load_valid_pair_survey_config(tmp_path, test_audio_file):
    data = _pair_survey_data(
        tmp_path,
        test_audio_file,
        questions=[
            {
                "key": "naturalness",
                "label": "How natural?",
                "type": "scale",
                "min": 1,
                "max": 5,
                "labels": {1: "Bad", 5: "Excellent"},
            },
            {
                "key": "similarity",
                "label": "How similar?",
                "type": "scale",
                "min": 1,
                "max": 5,
            },
        ],
    )
    result = load_config(write_config(tmp_path, data))
    assert result.test_type == "pair_survey"
    assert result.reference_system == "A"
    assert result.source_label == "Source"
    assert result.generated_label == "Generated"
    assert [q.key for q in result.questions] == ["naturalness", "similarity"]
    # Bare int YAML keys become the strings the UI looks up by.
    assert result.questions[0].labels["1"] == "Bad"


def test_question_description_round_trips(tmp_path, test_audio_file):
    data = _pair_survey_data(
        tmp_path,
        test_audio_file,
        questions=[
            {
                "key": "naturalness",
                "label": "Naturalness",
                "description": "How natural does the speech sound?",
                "type": "scale",
                "min": 1,
                "max": 5,
            }
        ],
    )
    result = load_config(write_config(tmp_path, data))
    question = result.questions[0]
    assert question.description == "How natural does the speech sound?"
    assert question.browser_dict()["description"] == question.description


def test_question_description_defaults_to_empty(tmp_path, test_audio_file):
    data = _pair_survey_data(tmp_path, test_audio_file)
    result = load_config(write_config(tmp_path, data))
    assert result.questions[0].description == ""
    assert result.questions[0].browser_dict()["description"] == ""


def test_question_help_round_trips(tmp_path, test_audio_file):
    data = _pair_survey_data(
        tmp_path,
        test_audio_file,
        questions=[
            {
                "key": "naturalness",
                "label": "Naturalness",
                "type": "scale",
                "min": 1,
                "max": 5,
                "help": {1: "Sounds artificial", 5: "Sounds human"},
            }
        ],
    )
    result = load_config(write_config(tmp_path, data))
    question = result.questions[0]
    assert question.help["1"] == "Sounds artificial"
    assert question.browser_dict()["help"]["5"] == "Sounds human"


def test_question_help_defaults_to_empty(tmp_path, test_audio_file):
    data = _pair_survey_data(tmp_path, test_audio_file)
    result = load_config(write_config(tmp_path, data))
    assert result.questions[0].help is None
    assert result.questions[0].browser_dict()["help"] == {}


def test_custom_player_labels(tmp_path, test_audio_file):
    data = _pair_survey_data(
        tmp_path,
        test_audio_file,
        source_label="Original",
        generated_label="Converted",
    )
    result = load_config(write_config(tmp_path, data))
    assert result.source_label == "Original"
    assert result.generated_label == "Converted"


def test_scope_field_rejected(tmp_path, test_audio_file):
    data = _pair_survey_data(
        tmp_path, test_audio_file, questions=_questions(scope="pair")
    )
    with pytest.raises(ValidationError, match="scope"):
        load_config(write_config(tmp_path, data))


def test_missing_reference_rejected(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [{"path": str(da), "system": "A"}, {"path": str(db), "system": "B"}],
        test_type="pair_survey",
    )
    data["questions"] = _questions()
    with pytest.raises(ValidationError, match="reference"):
        load_config(write_config(tmp_path, data))


def test_two_references_rejected(tmp_path, test_audio_file):
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "A", "reference": True},
            {"path": str(db), "system": "B", "reference": True},
        ],
        test_type="pair_survey",
    )
    data["questions"] = _questions()
    with pytest.raises(ValidationError, match="reference"):
        load_config(write_config(tmp_path, data))


def test_choice_question_requires_options(tmp_path, test_audio_file):
    data = _pair_survey_data(
        tmp_path,
        test_audio_file,
        questions=[{"key": "pref", "label": "Which?", "type": "choice"}],
    )
    with pytest.raises(ValidationError, match="options"):
        load_config(write_config(tmp_path, data))


def test_duplicate_question_keys_rejected(tmp_path, test_audio_file):
    data = _pair_survey_data(
        tmp_path,
        test_audio_file,
        questions=_questions() + _questions(),
    )
    with pytest.raises(ValidationError, match="duplicate"):
        load_config(write_config(tmp_path, data))


def test_reserved_column_name_rejected(tmp_path, test_audio_file):
    data = _pair_survey_data(
        tmp_path,
        test_audio_file,
        questions=[
            {"key": "item", "label": "Item?", "type": "scale", "min": 1, "max": 2}
        ],
    )
    with pytest.raises(ValidationError, match="reserved"):
        load_config(write_config(tmp_path, data))


def test_reference_column_name_rejected(tmp_path, test_audio_file):
    data = _pair_survey_data(
        tmp_path,
        test_audio_file,
        questions=[
            {
                "key": "reference",
                "label": "Ref?",
                "type": "scale",
                "min": 1,
                "max": 2,
            }
        ],
    )
    with pytest.raises(ValidationError, match="reserved"):
        load_config(write_config(tmp_path, data))


def test_scale_label_outside_range_rejected(tmp_path, test_audio_file):
    data = _pair_survey_data(
        tmp_path,
        test_audio_file,
        questions=_questions(labels={9: "Nope"}),
    )
    with pytest.raises(ValidationError, match="outside the scale"):
        load_config(write_config(tmp_path, data))


def test_scale_help_outside_range_rejected(tmp_path, test_audio_file):
    data = _pair_survey_data(
        tmp_path,
        test_audio_file,
        questions=_questions(help={9: "Nope"}),
    )
    with pytest.raises(ValidationError, match="outside the scale"):
        load_config(write_config(tmp_path, data))


def test_questions_required(tmp_path, test_audio_file):
    data = _pair_survey_data(tmp_path, test_audio_file)
    data.pop("questions")
    with pytest.raises(ValidationError, match="questions"):
        load_config(write_config(tmp_path, data))


def test_assignments_loaded_and_validated(tmp_path, test_audio_file):
    assignments = tmp_path / "assignments.json"
    assignments.write_text(
        json.dumps({"alice": ["utt1"], "bob": ["utt2"]}), encoding="utf-8"
    )
    data = _pair_survey_data(
        tmp_path, test_audio_file, assignments={"path": str(assignments)}
    )
    result = load_config(write_config(tmp_path, data))
    assert result.rater_items == {"alice": ["utt1"], "bob": ["utt2"]}


def test_assignments_unknown_item_fails_at_load(tmp_path, test_audio_file):
    assignments = tmp_path / "assignments.json"
    assignments.write_text(json.dumps({"alice": ["missing"]}), encoding="utf-8")
    data = _pair_survey_data(
        tmp_path, test_audio_file, assignments={"path": str(assignments)}
    )
    with pytest.raises(ValueError, match="not paired"):
        load_config(write_config(tmp_path, data))


def test_assignments_invalid_rater_id_fails_at_load(tmp_path, test_audio_file):
    assignments = tmp_path / "assignments.json"
    assignments.write_text(json.dumps({"alice/bob": ["utt1"]}), encoding="utf-8")
    data = _pair_survey_data(
        tmp_path, test_audio_file, assignments={"path": str(assignments)}
    )
    with pytest.raises(ValueError, match="rater"):
        load_config(write_config(tmp_path, data))


def test_assignments_empty_list_fails_at_load(tmp_path, test_audio_file):
    assignments = tmp_path / "assignments.json"
    assignments.write_text(json.dumps({"alice": []}), encoding="utf-8")
    data = _pair_survey_data(
        tmp_path, test_audio_file, assignments={"path": str(assignments)}
    )
    with pytest.raises(ValueError, match="non-empty"):
        load_config(write_config(tmp_path, data))


def test_assignments_not_supported_on_mos(tmp_path, test_audio_file):
    assignments = tmp_path / "assignments.json"
    assignments.write_text(json.dumps({"alice": ["utt1"]}), encoding="utf-8")
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}], test_type="mos")
    data["assignments"] = {"path": str(assignments)}
    with pytest.raises(ValidationError, match="not supported"):
        load_config(write_config(tmp_path, data))


def test_assignments_cannot_reuse_metadata_rater_key(tmp_path, test_audio_file):
    assignments = tmp_path / "assignments.json"
    assignments.write_text(json.dumps({"alice": ["utt1"]}), encoding="utf-8")
    data = _pair_survey_data(
        tmp_path,
        test_audio_file,
        assignments={"path": str(assignments)},
        metadata={"fields": [{"key": "rater", "label": "Name", "type": "text"}]},
    )
    with pytest.raises(ValidationError, match="rater"):
        load_config(write_config(tmp_path, data))
