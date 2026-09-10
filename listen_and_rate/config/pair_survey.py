"""Pair-survey listening test: N configurable questions about the generated clip.

Each trial shows a labeled source clip next to a generated clip of the same
item. The source is the `reference: true` system; the other system is the
one being rated. Every question is about the generated clip (naturalness,
similarity to the source, and so on) - the source is there to listen to,
not to rate.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from ._utils import (
    _KEY_RE,
    _coerce_dict_keys_and_values_to_str,
    _duplicates,
)
from .base import _StrictModel
from .two_system import TwoSystemComparisonConfig

# Row columns the stored result already occupies. A question whose key
# landed on one of these would overwrite it, so the clash is a config error
# rather than something to silently rename around.
_RESERVED_COLUMNS = frozenset({"system", "item", "reference", "metrics"})


class QuestionConfig(_StrictModel):
    """One question asked about the generated clip on every trial.

    `scale` renders min..max as a row of buttons (optionally labelled at any
    subset of the values); `choice` renders one button per option.
    """

    key: str
    label: str
    # Optional core-question text shown under the dimension title.
    description: str = ""
    type: Literal["scale", "choice"] = "scale"
    # scale only
    min: int = 1
    max: int = 5
    labels: dict[str, str] | None = None
    # Longer per-point explanations shown in the help popover (scale only).
    help: dict[str, str] | None = None
    # choice only
    options: list[str] | None = None
    required: bool = True

    @model_validator(mode="before")
    @classmethod
    def coerce_label_keys(cls, data: object) -> object:
        """Coerce bare int YAML keys in `labels`/`help` to str.

        Same motivation as RatingLabelsConfigMixin's normalization: a scale
        point written unquoted parses as a number, and would then never match
        the string key the UI and the validator look it up by.
        """
        if not isinstance(data, dict):
            return data
        for field in ("labels", "help"):
            if field in data:
                data = {
                    **data,
                    field: _coerce_dict_keys_and_values_to_str(data[field]),
                }
        return data

    @property
    def scale_values(self) -> list[int]:
        """The integer points of a `scale` question, low to high."""
        return list(range(self.min, self.max + 1))

    @property
    def allowed(self) -> list[str]:
        """Every accepted answer, as the strings the browser submits."""
        if self.type == "scale":
            return [str(v) for v in self.scale_values]
        return list(self.options or [])

    @model_validator(mode="after")
    def check_question(self) -> QuestionConfig:
        """Validate the key format and that the fields match the question type."""
        if not _KEY_RE.match(self.key):
            raise PydanticCustomError(
                "question_key_format",
                "question key must start with a letter and contain only letters, "
                "digits, or underscores. Got: {key}",
                {"key": repr(self.key)},
            )
        if self.type == "choice":
            if not self.options:
                raise PydanticCustomError(
                    "question_choice_missing_options",
                    "question {key}: choice type requires options",
                    {"key": repr(self.key)},
                )
            duplicated = _duplicates(self.options)
            if duplicated:
                raise PydanticCustomError(
                    "question_duplicate_option",
                    "question {key} has duplicate option(s): {duplicated}",
                    {"key": repr(self.key), "duplicated": duplicated},
                )
            if self.labels:
                raise PydanticCustomError(
                    "question_labels_unsupported",
                    "question {key}: 'labels' applies to scale questions; a "
                    "choice question's options are their own labels",
                    {"key": repr(self.key)},
                )
            if self.help:
                raise PydanticCustomError(
                    "question_help_unsupported",
                    "question {key}: 'help' applies to scale questions",
                    {"key": repr(self.key)},
                )
        else:
            if self.options:
                raise PydanticCustomError(
                    "question_options_unsupported",
                    "question {key}: 'options' applies to choice questions; a "
                    "scale question is defined by its min/max",
                    {"key": repr(self.key)},
                )
            if self.min >= self.max:
                raise PydanticCustomError(
                    "question_scale_range",
                    "question {key}: min ({min}) must be less than max ({max})",
                    {"key": repr(self.key), "min": self.min, "max": self.max},
                )
            # A typo'd label key would otherwise do nothing visible except
            # leave a scale point unlabelled - the same reason
            # _check_rating_labels_keys exists for the built-in types.
            unknown = sorted(set(self.labels or {}) - set(self.allowed))
            if unknown:
                raise PydanticCustomError(
                    "question_labels_unknown_key",
                    "question {key}: labels has key(s) outside the scale "
                    "{valid}: {unknown}",
                    {"key": repr(self.key), "valid": self.allowed, "unknown": unknown},
                )
            unknown_help = sorted(set(self.help or {}) - set(self.allowed))
            if unknown_help:
                raise PydanticCustomError(
                    "question_help_unknown_key",
                    "question {key}: help has key(s) outside the scale "
                    "{valid}: {unknown}",
                    {
                        "key": repr(self.key),
                        "valid": self.allowed,
                        "unknown": unknown_help,
                    },
                )
        return self

    def browser_dict(self) -> dict:
        """Return the question as the frontend needs it, type fields only.

        Sending a scale question's empty `options` (or a choice question's
        irrelevant min/max) would invite the UI to branch on the wrong field,
        so each type carries exactly what it renders from.
        """
        common = {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "type": self.type,
            "required": self.required,
        }
        if self.type == "scale":
            return {
                **common,
                "values": self.scale_values,
                "labels": self.labels or {},
                "help": self.help or {},
            }
        return {**common, "options": list(self.options or [])}


class PairSurveyConfig(TwoSystemComparisonConfig):
    """Top-level configuration for a pair_survey test.

    Exactly 2 systems: the source (`reference: true`) and the generated
    system being rated. Player roles are disclosed (source_label /
    generated_label); answers are stored against the generated system.
    """

    test_type: Literal["pair_survey"]
    questions: list[QuestionConfig] = Field(min_length=1)
    source_label: str = "Source"
    generated_label: str = "Generated"

    @model_validator(mode="after")
    def check_requires_one_reference(self) -> PairSurveyConfig:
        """Require exactly one source system flagged `reference: true`."""
        systems = self.stimuli_dirs.systems if self.stimuli_dirs else []
        refs = [s for s in systems if s.reference]
        if len(refs) != 1:
            raise PydanticCustomError(
                "pair_survey_reference_count",
                "pair_survey requires exactly one stimuli_dirs.systems entry "
                "with reference: true (the source), got {count}",
                {"count": len(refs)},
            )
        return self

    @model_validator(mode="after")
    def check_question_keys_unique(self) -> PairSurveyConfig:
        """Reject duplicate question keys, which would collide when stored."""
        duplicated = _duplicates([q.key for q in self.questions])
        if duplicated:
            raise PydanticCustomError(
                "question_duplicate_key",
                "questions has duplicate key(s): {duplicated}",
                {"duplicated": duplicated},
            )
        return self

    @model_validator(mode="after")
    def check_stored_columns_free(self) -> PairSurveyConfig:
        """Reject question keys whose stored column would clash with row fields."""
        produced = [question.key for question in self.questions]
        reserved = sorted(set(produced) & _RESERVED_COLUMNS)
        if reserved:
            raise PydanticCustomError(
                "question_reserved_column",
                "questions produce result column(s) reserved by the tool: "
                "{reserved}. Rename the question key(s)",
                {"reserved": reserved},
            )
        return self

    @property
    def reference_system(self) -> str:
        """Resolved system name of the source entry (`reference: true`)."""
        systems = self.stimuli_dirs.systems if self.stimuli_dirs else []
        for s in systems:
            if s.reference:
                return s.resolved_system
        return ""
