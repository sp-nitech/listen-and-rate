"""Report (figure) config: presentation options for lar-analyze-results.

Separate from the experiment config (which locates results and defines the
default system order): this file only controls how the report figures look -
scale, font, confidence level, and system display order/labels. All fields
are optional; an empty file yields the defaults.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field, ValidationError

from .base import _StrictModel
from .errors import format_config_error


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
