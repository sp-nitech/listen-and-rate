"""Report (figure) config: presentation options for lar-analyze-results.

Separate from the experiment config (which locates results and defines the
default system order): this file only controls how the report figures look -
scale, font, confidence level, and system display order/labels. All fields
are optional; an empty file yields the defaults.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field, ValidationError, field_validator
from pydantic_core import PydanticCustomError

from ._utils import _coerce_scalar_to_str
from .base import _StrictModel
from .errors import format_config_error

# stimuli_filter's fixed key allowlist: the stimulus-side result columns. This
# is what keeps outcome columns (rating/winner/...) structurally unfilterable.
_STIMULI_FILTER_KEYS = {"utterance", "system"}


def _coerce_filter_values_to_str(v: object) -> object:
    """Coerce bare numeric YAML filter values (scalars or list items) to str."""
    if not isinstance(v, dict):
        return v
    return {
        key: (
            [_coerce_scalar_to_str(item) for item in value]
            if isinstance(value, list)
            else _coerce_scalar_to_str(value)
        )
        for key, value in v.items()
    }


class ReportGroupConfig(_StrictModel):
    """One vertically stacked report section: a heading label plus row filters.

    Both filters are optional and combine with AND; a group with neither
    filter covers every session (an "All" section). Values are glob patterns
    (fnmatch: `*`/`?`; a value without metacharacters is an exact match) and a
    list of patterns is OR. metadata_filter keys name listener-metadata fields
    (session-level: a non-matching session's rows all drop); stimuli_filter
    keys name stimulus-side columns - utterance or system - and drop
    individual trial rows.
    """

    label: str
    metadata_filter: dict[str, str | list[str]] | None = None
    stimuli_filter: dict[str, str | list[str]] | None = None

    @field_validator("metadata_filter", "stimuli_filter", mode="before")
    @classmethod
    def coerce_values_to_str(cls, v: object) -> object:
        """Coerce bare numeric YAML values (e.g. `age: 30`) to their string form."""
        return _coerce_filter_values_to_str(v)

    @field_validator("stimuli_filter")
    @classmethod
    def check_stimuli_filter_keys(
        cls, v: dict[str, str | list[str]] | None
    ) -> dict[str, str | list[str]] | None:
        """Reject stimuli_filter keys outside the stimulus-side columns."""
        if v is None:
            return v
        unknown = sorted(set(v) - _STIMULI_FILTER_KEYS)
        if unknown:
            raise PydanticCustomError(
                "stimuli_filter_unknown_key",
                "stimuli_filter keys must be one of {valid}; got: {unknown}",
                {"valid": sorted(_STIMULI_FILTER_KEYS), "unknown": unknown},
            )
        return v


class ScaleConfig(_StrictModel):
    """Multipliers on the report's base figure dimensions (not absolute pixels)."""

    width: float = Field(default=1.0, gt=0)
    height: float = Field(default=1.0, gt=0)


class FontConfig(_StrictModel):
    """Chart/table font."""

    family: str = "sans-serif"
    size: int = Field(default=13, gt=0)


class ReportConfig(_StrictModel):
    """Presentation options for the generated report.

    order/labels key on the *raw* system names stored in the results. When
    order is given it must list every system present in the data (enforced at
    report-generation time, since the data isn't known here). labels maps a
    raw name to its display name (charts/tables only; the stored data keeps
    its raw names).
    """

    scale: ScaleConfig = Field(default_factory=ScaleConfig)
    confidence: float = Field(default=0.95, gt=0, lt=1)
    font: FontConfig = Field(default_factory=FontConfig)
    order: list[str] | None = None
    labels: dict[str, str] | None = None
    groups: list[ReportGroupConfig] | None = None

    @field_validator("groups")
    @classmethod
    def check_group_labels_unique(
        cls, v: list[ReportGroupConfig] | None
    ) -> list[ReportGroupConfig] | None:
        """Reject duplicate labels - their sections would be indistinguishable."""
        if v is None:
            return v
        seen = [g.label for g in v]
        duplicates = sorted({x for x in seen if seen.count(x) > 1})
        if duplicates:
            raise PydanticCustomError(
                "groups_duplicate_label",
                "groups have duplicate label(s): {duplicates}",
                {"duplicates": duplicates},
            )
        return v


def load_report_config_or_exit(config_path: str | Path) -> ReportConfig:
    """Load and validate a report config YAML; clean-exit on a bad file.

    Mirrors config.loader.load_config_or_exit: a typo in this hand-written file
    prints a short, URL-free message (see format_config_error) and exits rather
    than a stack trace. An empty file yields the defaults.
    """
    with open(Path(config_path)) as f:
        data = yaml.safe_load(f) or {}
    try:
        return ReportConfig.model_validate(data)
    except ValidationError as exc:
        raise SystemExit(format_config_error(exc)) from None
