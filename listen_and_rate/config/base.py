"""Shared building blocks for every test type: stimuli, shortcuts, BaseTestConfig."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Literal, Self

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator
from pydantic_core import PydanticCustomError

from ._utils import (
    _KEY_RE,
    _check_rating_labels_keys,
    _coerce_dict_keys_and_values_to_str,
    _coerce_scalar_to_str,
    _duplicates,
)


class _StrictModel(BaseModel):
    """Shared base for every config model: rejects unknown/typo'd fields.

    Pydantic's built-in `extra="forbid"` would do this too, but its
    `extra_forbidden` error is a *built-in* pydantic-core error type, so
    printing it always appends a "For further information visit
    https://errors.pydantic.dev/..." line - noise for what's just a config
    file typo. Every other validation error in this package is raised via
    PydanticCustomError specifically to avoid that; this does the same,
    checking the raw input dict before Pydantic's own field-by-field
    validation runs.
    """

    @model_validator(mode="before")
    @classmethod
    def _reject_unknown_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            unknown = sorted(set(data) - set(cls.model_fields))
            if unknown:
                raise PydanticCustomError(
                    "unknown_field",
                    "Unknown field(s): {unknown}",
                    {"unknown": unknown},
                )
        return data


class MetadataFieldConfig(_StrictModel):
    """One field of the pre-test metadata form or the post-test survey.

    The two forms share this schema; only the collection timing differs.
    Field keys need no reserved-name restriction: stored answers are
    namespaced with a metadata_/survey_ column prefix (see storage.py), so
    even a key literally named 'system' can never collide with a result
    column.
    """

    key: str
    label: str
    type: Literal["text", "select"] = "text"
    options: list[str] | None = None
    required: bool = False
    default: str | None = None

    @model_validator(mode="after")
    def check_key_and_options(self) -> MetadataFieldConfig:
        """Validate key format, options presence, and default validity."""
        if not _KEY_RE.match(self.key):
            raise PydanticCustomError(
                "metadata_key_format",
                "metadata key must start with a letter and contain only letters, "
                "digits, or underscores; got: {key}",
                {"key": repr(self.key)},
            )
        if self.type == "select" and not self.options:
            raise PydanticCustomError(
                "metadata_select_missing_options",
                "metadata field {key}: select type requires options",
                {"key": repr(self.key)},
            )
        if self.default is not None and self.type == "select":
            if self.options and self.default not in self.options:
                raise PydanticCustomError(
                    "metadata_default_not_in_options",
                    "metadata field {key}: default {default} is not in "
                    "options {options}",
                    {
                        "key": repr(self.key),
                        "default": repr(self.default),
                        "options": self.options,
                    },
                )
        return self


class FormPageConfig(_StrictModel):
    """One form page: a heading plus the fields shown on it.

    Two instances exist per experiment - the pre-test metadata form and the
    post-test survey (see the subclasses below) - sharing this schema and
    differing only in their default title and collection timing. No fields
    (the default) means the page is skipped entirely.
    """

    title: str
    fields: list[MetadataFieldConfig] = Field(default_factory=list)


class MetadataFormConfig(FormPageConfig):
    """The pre-test listener-information form."""

    title: str = "Listener Information"


class SurveyFormConfig(FormPageConfig):
    """The post-test survey form."""

    title: str = "Questionnaire"


class OutputConfig(_StrictModel):
    """Result output settings."""

    format: Literal["csv", "json"] = "csv"
    path: str = "./results/"


class PracticeConfig(_StrictModel):
    """Practice stage settings.

    count practice pages (stimuli for MOS, trials for the other test types)
    are sampled from the full pool independently of the real session's
    sampling (overlap with the real session is allowed); practice ratings
    are never submitted or saved.
    """

    count: int = Field(default=0, ge=0)
    instructions: str = "This is a practice session. Your ratings will not be recorded."


class LoudnessCriterion(_StrictModel):
    """One loudness-check criterion (`per_system` or `per_stimulus`).

    The check exceeds when the relevant loudness difference (in LU) is greater
    than `threshold`; `verbose` prints the loudness figures every run,
    regardless of whether the threshold was exceeded.
    """

    threshold: float = Field(default=1.0, gt=0)
    verbose: bool = False


class LoudnessCheckConfig(_StrictModel):
    """Optional pre-test loudness check (runs at serve/export when configured).

    Each criterion, when present, is enabled: `per_system` compares the range
    (max-min) of per-system mean loudness; `per_stimulus` compares, per
    utterance, the loudness spread across systems. See listen_and_rate/loudness.py.
    """

    per_system: LoudnessCriterion | None = None
    per_stimulus: LoudnessCriterion | None = None


class LoudnessNormalizationConfig(_StrictModel):
    """Optional loudness normalization applied to stimuli before the test.

    The `scope` selects the unit over which one gain is computed (mutually
    exclusive strategies, unlike LoudnessCheckConfig's independent criteria):
    `stimulus` normalizes each clip individually to `target` (flattening every
    clip to the same loudness); `system` applies one gain per system so that
    system's mean loudness reaches `target`, preserving the natural loudness
    differences between utterances within a system. See listen_and_rate/loudness.py.
    """

    target: float = Field(default=-23.0, lt=0)  # integrated loudness, LUFS (EBU R128)
    scope: Literal["stimulus", "system"] = "stimulus"


class StimulusConfig(_StrictModel):
    """A single audio stimulus."""

    id: str
    path: str
    system: str | None = None
    utterance: str | None = None
    label: str | None = None

    @field_validator("system", "label", mode="before")
    @classmethod
    def coerce_system_and_label_to_str(cls, v: object) -> object:
        """Coerce a bare numeric YAML scalar (e.g. `system: 1`) to a string."""
        return _coerce_scalar_to_str(v)


class SystemDirEntry(_StrictModel):
    """One system's audio directory in stimuli_dirs."""

    path: str
    system: str | None = None
    reference: bool = False
    anchor: bool = False

    @field_validator("system", mode="before")
    @classmethod
    def coerce_system_to_str(cls, v: object) -> object:
        """Coerce a bare numeric YAML scalar (e.g. `system: 1`) to a string."""
        return _coerce_scalar_to_str(v)

    @property
    def resolved_system(self) -> str:
        """The entry's system name: explicit `system:`, or the directory basename."""
        return self.system or Path(self.path).name


class StimuliDirsConfig(_StrictModel):
    """Directory-based multi-system stimulus definition."""

    utterances_per_session: int | None = Field(default=None, ge=1)
    systems: list[SystemDirEntry]


class StimuliConfig(_StrictModel):
    """Explicit stimulus list."""

    stimuli_per_session: int | None = Field(default=None, ge=1)
    items: list[StimulusConfig]

    @field_validator("items")
    @classmethod
    def ids_must_be_unique(cls, v: list[StimulusConfig]) -> list[StimulusConfig]:
        """Reject configs where two items share the same id."""
        ids = [s.id for s in v]
        if len(ids) != len(set(ids)):
            raise PydanticCustomError(
                "duplicate_stimulus_id", "stimulus IDs must be unique"
            )
        return v


# Default rating shortcuts for the 1-5 scale tests (MOS, DMOS); also the
# untouched-field marker CMOSConfig checks before swapping in its own -3..3
# defaults. A partially specified `shortcuts.rating` is merged over the test
# type's defaults (see _merge_rating_shortcuts), so users can override single
# keys without retyping the whole mapping.
_DEFAULT_RATING_SHORTCUTS = {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5"}


# A shortcut value is compared against the browser's KeyboardEvent.key at
# keydown time, so it must be a value that key can actually take: a single
# character (letters, digits, punctuation, or a literal space), or one of
# these named keys. Anything else (e.g. "Spa", "space", "ShiftTab") would
# silently never fire, so it's rejected at config-load time. "Space" is the
# one spelled-out alias the frontend maps to the space character.
_NAMED_KEYS = frozenset(
    {
        "ArrowDown",
        "ArrowLeft",
        "ArrowRight",
        "ArrowUp",
        "Backspace",
        "Delete",
        "End",
        "Enter",
        "Escape",
        "Home",
        "PageDown",
        "PageUp",
        "Space",
        "Tab",
    }
)


def _is_valid_shortcut_key(value: str) -> bool:
    """Whether value can occur as a KeyboardEvent.key (single char or named key)."""
    return len(value) == 1 or value in _NAMED_KEYS


class KeyboardShortcuts(_StrictModel):
    """Keyboard shortcut bindings; all fields have sensible defaults.

    Every field reads "name: key" (e.g. choose_a: "1") - the config-authoring
    direction, matching how a human thinks about a shortcut ("which key does
    X?"). `rating` follows the same convention: {rating value: key}, e.g.
    "-3": "1". This is the opposite direction from what the frontend actually
    needs at keydown time (key -> rating value, for an O(1) lookup rather
    than a linear scan) - that inversion is a browser-response-serialization
    concern, not a config-shape concern, so it happens once server-side via
    browser_dict() below rather than leaking into this model or the YAML file.
    """

    rating: dict[str, str] = Field(
        default_factory=lambda: dict(_DEFAULT_RATING_SHORTCUTS)
    )
    prev: str = "ArrowLeft"
    next: str = "ArrowRight"
    confirm: str = "Enter"
    play: str = "Space"
    # Rewind the current clip to its start (keeps playing/paused state).
    # Gate-safe: unlike seeking forward, jumping to 0 can never skip content,
    # so the play-to-completion gate is unaffected.
    rewind: str = "r"
    # Paired-choice tests (AB, ABX, XAB): select the 1st/2nd sample of the
    # pair - one shared name regardless of what the choice means per test
    # (preferred / matches X / closer to X).
    choose_a: str = "1"
    choose_b: str = "2"
    # AB only: the tie/no-preference response
    tie: str = "3"
    # MUSHRA only: adjusts the currently-focused slider's value
    rate_up: str = "ArrowUp"
    rate_down: str = "ArrowDown"

    @field_validator(
        "prev",
        "next",
        "confirm",
        "play",
        "rewind",
        "choose_a",
        "choose_b",
        "tie",
        "rate_up",
        "rate_down",
        mode="before",
    )
    @classmethod
    def coerce_key_fields_to_str(cls, v: object) -> object:
        """Coerce a bare int/float YAML key (e.g. `choose_a: 1`) to its string form."""
        return _coerce_scalar_to_str(v)

    @field_validator(
        "prev",
        "next",
        "confirm",
        "play",
        "rewind",
        "choose_a",
        "choose_b",
        "tie",
        "rate_up",
        "rate_down",
    )
    @classmethod
    def check_key_field_is_valid(cls, v: str) -> str:
        """Reject a key the browser could never match (see _is_valid_shortcut_key)."""
        if not _is_valid_shortcut_key(v):
            raise PydanticCustomError(
                "shortcuts_invalid_key",
                "{value} is not a valid key; use a single character or one of {valid}",
                {"value": repr(v), "valid": sorted(_NAMED_KEYS)},
            )
        return v

    @field_validator("rating", mode="before")
    @classmethod
    def coerce_rating_keys_and_values_to_str(cls, v: object) -> object:
        """Coerce bare int YAML keys/values (e.g. `1: 1`) to string form."""
        return _coerce_dict_keys_and_values_to_str(v)

    @field_validator("rating")
    @classmethod
    def check_rating_keys_are_valid(cls, v: dict[str, str]) -> dict[str, str]:
        """Reject a rating binding whose keyboard key the browser could never match."""
        invalid = sorted({key for key in v.values() if not _is_valid_shortcut_key(key)})
        if invalid:
            raise PydanticCustomError(
                "shortcuts_rating_invalid_key",
                "{invalid} is not a valid key; use a single character "
                "or one of {valid}",
                {"invalid": invalid, "valid": sorted(_NAMED_KEYS)},
            )
        return v

    @field_validator("rating")
    @classmethod
    def check_rating_keys_are_unique(cls, v: dict[str, str]) -> dict[str, str]:
        """Reject two different rating values assigned the same keyboard key.

        rating's own dict keys (rating values) can't collide - a YAML/JSON
        mapping can't have two entries with the same key - but nothing stops
        two different rating values from being bound to the same keyboard
        key, which would leave one of them unreachable from the keyboard.
        """
        keys_pressed = list(v.values())
        duplicates = _duplicates(keys_pressed)
        if duplicates:
            raise PydanticCustomError(
                "shortcuts_rating_duplicate_key",
                "shortcuts.rating assigns more than one rating value to the "
                "same keyboard key: {duplicates}",
                {"duplicates": duplicates},
            )
        return v

    def browser_dict(self) -> dict:
        """Return the browser-facing shortcuts dict for /api/config and config.php.

        Identical to model_dump() except `rating` is inverted from this
        model's "rating value: key" direction to the "key: rating value"
        direction the frontend's keydown handler needs (see the class
        docstring above).
        """
        data = self.model_dump()
        data["rating"] = {key: int(value) for value, key in self.rating.items()}
        return data


def _merge_rating_shortcuts(
    shortcuts: KeyboardShortcuts, defaults: dict[str, str]
) -> KeyboardShortcuts:
    """Merge a (possibly partial) shortcuts.rating over a test type's defaults.

    Rating values the user didn't mention keep their default key, so
    overriding one key doesn't silently unbind every other rating. `defaults`
    doubles as the test type's valid rating range: values outside it are
    rejected (a typo'd value would otherwise add a dead entry alongside the
    merged defaults), as is a merged mapping that binds two rating values to
    the same keyboard key (one of them would be unreachable).
    """
    rating = shortcuts.rating
    unknown = sorted(set(rating) - set(defaults))
    if unknown:
        raise PydanticCustomError(
            "shortcuts_rating_unknown_value",
            "shortcuts.rating has rating value(s) outside the valid range "
            "{valid}: {unknown}",
            {"valid": sorted(defaults), "unknown": unknown},
        )
    merged = {**defaults, **rating}
    keys_pressed = list(merged.values())
    duplicates = _duplicates(keys_pressed)
    if duplicates:
        raise PydanticCustomError(
            "shortcuts_rating_duplicate_key",
            "shortcuts.rating assigns more than one rating value to the "
            "same keyboard key (after filling unspecified values with "
            "defaults): {duplicates}",
            {"duplicates": duplicates},
        )
    if merged == rating:
        return shortcuts
    return shortcuts.model_copy(update={"rating": merged})


# Test types where a stimuli_dirs.systems entry's 'reference: true' flag is
# meaningful (the system is compared against a designated reference
# stimulus).
_REFERENCE_AWARE_TEST_TYPES = {"dmos", "xab", "mushra"}

# Test types where a stimuli_dirs.systems entry's 'anchor: true' flag is
# meaningful (the system is rated like a normal system but disclosed to the
# listener as the anchor, always shown last).
_ANCHOR_AWARE_TEST_TYPES = {"mushra"}


class BaseTestConfig(_StrictModel):
    """Fields shared by every listening test type (MOS, AB, ...)."""

    title: str
    instructions: str
    output: OutputConfig = Field(default_factory=OutputConfig)
    # How the per-session stimuli/trials are ordered. "random" (default)
    # shuffles the presentation order per listener to cancel order effects;
    # "fixed" keeps the configured order (systems as listed, files by name).
    # This governs ordering ONLY - which subset a listener is sampled and the
    # within-trial A/B position blinding are always randomized regardless.
    presentation_order: Literal["random", "fixed"] = "random"
    # Fetch each page's audio as soon as the page is shown instead of on the
    # listener's first play click - trades bandwidth for less waiting on slow
    # connections.
    preload_audio: bool = False
    stimuli: StimuliConfig | None = None
    stimuli_dirs: StimuliDirsConfig | None = None
    shortcuts: KeyboardShortcuts = Field(default_factory=KeyboardShortcuts)
    # Pre-test listener-information form ({title, fields}); no fields (the
    # default) means the page is skipped.
    metadata: MetadataFormConfig = Field(default_factory=MetadataFormConfig)
    # Post-test survey form, shown after the last trial (the final trial
    # button then reads "Finish" and submission happens from the survey
    # page). Same shape as metadata; no fields (the default) means no
    # survey page.
    survey: SurveyFormConfig = Field(default_factory=SurveyFormConfig)
    practice: PracticeConfig | None = None
    loudness_check: LoudnessCheckConfig | None = None
    loudness_normalization: LoudnessNormalizationConfig | None = None

    # Not user-configurable: always derived from the config file's stem by
    # load_config(). Kept as a private attribute so it cannot be set via YAML.
    _experiment_id: str = PrivateAttr(default="")

    @property
    def experiment_id(self) -> str:
        """Experiment identifier derived from the config file's stem."""
        return self._experiment_id

    @property
    def shuffle_order(self) -> bool:
        """Whether the presentation order should be shuffled per session."""
        return self.presentation_order == "random"

    @model_validator(mode="after")
    def check_stimuli_source(self) -> BaseTestConfig:
        """Require exactly one stimulus source."""
        has_stimuli = self.stimuli is not None
        has_dirs = self.stimuli_dirs is not None
        if not has_stimuli and not has_dirs:
            raise PydanticCustomError(
                "missing_stimuli_source",
                "Either 'stimuli' or 'stimuli_dirs' must be specified",
            )
        if has_stimuli and has_dirs:
            raise PydanticCustomError(
                "stimuli_source_conflict",
                "'stimuli' and 'stimuli_dirs' are mutually exclusive",
            )
        return self

    @model_validator(mode="after")
    def check_form_keys_unique(self) -> BaseTestConfig:
        """Reject duplicate field keys within the metadata form or the survey.

        Duplicates within one form would collide on a single stored column.
        The SAME key in metadata and survey is fine - the storage prefixes
        (metadata_x vs survey_x) keep them distinct, which even allows asking
        the same question before and after the test.
        """
        for form_name, form in (("metadata", self.metadata), ("survey", self.survey)):
            keys = [f.key for f in form.fields]
            duplicates = _duplicates(keys)
            if duplicates:
                raise PydanticCustomError(
                    "form_duplicate_key",
                    "{form} has duplicate field key(s): {duplicates}",
                    {"form": form_name, "duplicates": duplicates},
                )
        return self

    @model_validator(mode="after")
    def check_loudness_check_and_normalization_exclusive(self) -> BaseTestConfig:
        """Reject configuring both loudness_check and loudness_normalization.

        Normalization already brings the stimuli into loudness agreement, so a
        loudness_check alongside it is redundant (and would run against the
        un-normalized originals); require choosing one.
        """
        if self.loudness_check is not None and self.loudness_normalization is not None:
            raise PydanticCustomError(
                "loudness_check_normalization_conflict",
                "set only one of 'loudness_check' / 'loudness_normalization'; "
                "normalization makes the check redundant",
            )
        return self

    @model_validator(mode="after")
    def check_reference_and_anchor_flag_usage(self) -> BaseTestConfig:
        """Reject 'reference'/'anchor' flags for test types that don't use them."""
        if self.stimuli_dirs is None:
            return self
        test_type = getattr(self, "test_type", None)
        if test_type not in _REFERENCE_AWARE_TEST_TYPES:
            flagged = [
                s.system or s.path for s in self.stimuli_dirs.systems if s.reference
            ]
            if flagged:
                raise PydanticCustomError(
                    "reference_flag_unsupported",
                    "'reference: true' is not used by this test type; "
                    "found on: {flagged}",
                    {"flagged": flagged},
                )
        if test_type not in _ANCHOR_AWARE_TEST_TYPES:
            flagged = [
                s.system or s.path for s in self.stimuli_dirs.systems if s.anchor
            ]
            if flagged:
                raise PydanticCustomError(
                    "anchor_flag_unsupported",
                    "'anchor: true' is not used by this test type; found on: {flagged}",
                    {"flagged": flagged},
                )
        return self


class RatingLabelsConfigMixin(_StrictModel):
    """Shared `rating_labels` field and validation for MOS/DMOS/CMOS/MUSHRA.

    Subclasses set _RATING_LABEL_KEYS to their test type's valid rating-value
    keys; CMOS additionally overrides normalize_rating_labels_keys to strip a
    leading '+' from positive keys.
    """

    rating_labels: dict[str, str] | None = None

    _RATING_LABEL_KEYS: ClassVar[set[str]] = set()

    @field_validator("rating_labels", mode="before")
    @classmethod
    def normalize_rating_labels_keys(cls, v: object) -> object:
        """Coerce bare int YAML keys (e.g. `5: "Excellent"`) to their string form."""
        return _coerce_dict_keys_and_values_to_str(v)

    @model_validator(mode="after")
    def check_rating_labels_keys(self) -> Self:
        """Reject rating_labels keys outside this test type's rating range."""
        _check_rating_labels_keys(self.rating_labels, self._RATING_LABEL_KEYS)
        return self
