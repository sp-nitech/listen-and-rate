"""Report (figure) config: presentation options for lar-report.

Separate from the experiment config (which locates results and defines the
default system order): this file only controls the generated report - scale,
font, confidence level, system display order/labels, and the optional
stacked filtered sections (groups). All fields are optional; an empty file
yields the defaults.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field, ValidationError, field_validator
from pydantic_core import PydanticCustomError

from ._utils import _coerce_scalar_to_str, _duplicates
from .base import _StrictModel
from .errors import format_config_error

# stimuli_filter's fixed key allowlist: the stimulus-side result columns. This
# is what keeps outcome columns (rating/winner/...) structurally unfilterable.
_STIMULI_FILTER_KEYS = {"item", "system"}


def _coerce_filter_values_to_str(v: object) -> object:
    """Coerce bare numeric YAML filter values (scalars or list elements) to str."""
    if not isinstance(v, dict):
        return v
    return {
        key: (
            [_coerce_scalar_to_str(x) for x in value]
            if isinstance(value, list)
            else _coerce_scalar_to_str(value)
        )
        for key, value in v.items()
    }


class MetricRange(_StrictModel):
    """Inclusive bounds one recorded metric must fall within to keep a row.

    Either end may be omitted for a one-sided bound. Inclusive on both ends so
    a whole-number threshold reads as written: `min: 1` keeps a trial that took
    exactly one second.
    """

    min: float | None = None
    max: float | None = None


class ReportGroupConfig(_StrictModel):
    """One vertically stacked report section: a heading label plus row filters.

    All filters are optional and combine with AND; a group with none covers
    every session (an "All" section). Values are glob patterns (fnmatch:
    `*`/`?`; a value without metacharacters is an exact match) and a list of
    patterns is OR. metadata_filter keys name pre-test metadata fields and
    survey_filter keys name post-test survey fields (both session-level: a
    non-matching session's rows all drop; the blocks are kept strictly apart
    via the stored metadata_/survey_ column prefixes); stimuli_filter keys
    name stimulus-side columns - item or system - and drop individual
    trial rows.

    metrics_filter is the one numeric filter: its keys name recorded metrics
    (see MetricsConfig) and its values are inclusive {min, max} bounds rather
    than patterns, because a glob over a duration means nothing. Like
    stimuli_filter it drops individual rows, since a metric is measured per
    answer rather than per session - excluding a whole listener is a different
    decision, and one this tool leaves to the analyst.
    """

    label: str
    metadata_filter: dict[str, str | list[str]] | None = None
    survey_filter: dict[str, str | list[str]] | None = None
    stimuli_filter: dict[str, str | list[str]] | None = None
    metrics_filter: dict[str, MetricRange] | None = None

    @field_validator(
        "metadata_filter", "survey_filter", "stimuli_filter", mode="before"
    )
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
    """Dimensionless rendering multipliers (not absolute pixels).

    width/height scale the figures' canvas, bar_width the bars' thickness
    within their category slot (boxplots unaffected), and png the resolution
    of the modebar's PNG download (on-screen display unaffected).
    """

    width: float = Field(default=1.0, gt=0)
    height: float = Field(default=1.0, gt=0)
    bar_width: float = Field(default=1.0, gt=0)
    png: float = Field(default=2.0, gt=0)


class FontConfig(_StrictModel):
    """Chart/table font."""

    family: str = "sans-serif"
    size: int = Field(default=13, gt=0)


class ColorConfig(_StrictModel):
    """Bar fill colors (any CSS color).

    mean_bar fills the mean/rate bars (MOS means, AB/CMOS CI bars); count_bar
    fills the raw-count bars (AB/ABX counts, CMOS categories).
    """

    mean_bar: str = "#72b7b2"
    count_bar: str = "#cd5c5c"


class ReportConfig(_StrictModel):
    """Presentation options for the generated report.

    order/labels key on the *raw* system names stored in the results. When
    order is given it must list every system present in the data (enforced at
    report-generation time, since the data isn't known here). labels maps a
    raw name to its display name (charts/tables only; the stored data keeps
    its raw names). groups, when given, stacks one labeled, filtered report
    section per entry (see ReportGroupConfig) instead of the single
    unlabeled report.
    """

    scale: ScaleConfig = Field(default_factory=ScaleConfig)
    confidence: float = Field(default=0.95, gt=0, lt=1)
    font: FontConfig = Field(default_factory=FontConfig)
    order: list[str] | None = None
    labels: dict[str, str] | None = None
    tie_label: str = "No preference"
    color: ColorConfig = Field(default_factory=ColorConfig)
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
        duplicates = _duplicates(seen)
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
    with open(Path(config_path), encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    try:
        return ReportConfig.model_validate(data)
    except ValidationError as exc:
        raise SystemExit(format_config_error(exc)) from None
