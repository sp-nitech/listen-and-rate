"""MOS (Mean Opinion Score, ITU-T P.800) listening test configuration."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import model_validator

from .base import (
    _DEFAULT_RATING_SHORTCUTS,
    BaseTestConfig,
    RatingLabelsConfigMixin,
    _merge_rating_shortcuts,
)

_MOS_RATING_KEYS = {"1", "2", "3", "4", "5"}


class MOSConfig(RatingLabelsConfigMixin, BaseTestConfig):
    """Top-level configuration for a MOS listening test."""

    test_type: Literal["mos"]

    _RATING_LABEL_KEYS: ClassVar[set[str]] = _MOS_RATING_KEYS

    @model_validator(mode="after")
    def merge_rating_shortcut_defaults(self) -> MOSConfig:
        """Fill unspecified shortcuts.rating values with the 1-5 defaults."""
        self.shortcuts = _merge_rating_shortcuts(
            self.shortcuts, _DEFAULT_RATING_SHORTCUTS
        )
        return self
