"""CMOS (comparative MOS / ITU-T P.800 CCR) listening test configuration."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import field_validator, model_validator

from ._utils import _coerce_dict_keys_and_values_to_str
from .base import (
    _DEFAULT_RATING_SHORTCUTS,
    RatingLabelsConfigMixin,
    _merge_rating_shortcuts,
)
from .two_system import TwoSystemComparisonConfig

_CMOS_RATING_KEYS = {"-3", "-2", "-1", "0", "1", "2", "3"}

_CMOS_DEFAULT_RATING_SHORTCUTS = {
    "-3": "1",
    "-2": "2",
    "-1": "3",
    "0": "4",
    "1": "5",
    "2": "6",
    "3": "7",
}


class CMOSConfig(RatingLabelsConfigMixin, TwoSystemComparisonConfig):
    """Top-level configuration for a CMOS (comparative MOS, P.800 CCR) test.

    Like AB, compares exactly 2 systems symmetrically (no reference flag):
    a signed -3..3 rating of one stimulus relative to the other, with which
    system plays in which on-screen position blinded per trial.
    """

    test_type: Literal["cmos"]

    _RATING_LABEL_KEYS: ClassVar[set[str]] = _CMOS_RATING_KEYS

    @field_validator("rating_labels", mode="before")
    @classmethod
    def normalize_rating_labels_keys(cls, v: object) -> object:
        """Coerce bare int keys to str, and strip a leading '+' from positive ones.

        Overrides RatingLabelsConfigMixin's coerce-only normalization: on top
        of turning bare int/float YAML keys (e.g. `-3: "Much worse"`) into
        their string form, a leading '+' (e.g. "+3", the form positive scores
        are shown in in the UI via cmos.js's formatScore()) is stripped to
        the bare digit form ("3") actually used for lookups and by the
        mixin's check_rating_labels_keys.
        """
        v = _coerce_dict_keys_and_values_to_str(v)
        if isinstance(v, dict):
            return {
                (k[1:] if isinstance(k, str) and k.startswith("+") else k): label
                for k, label in v.items()
            }
        return v

    @model_validator(mode="after")
    def apply_cmos_default_shortcuts(self) -> CMOSConfig:
        """Resolve shortcuts.rating against CMOS's -3..3 default mapping.

        An untouched field (still BaseTestConfig's generic 1-5 default) is
        replaced wholesale with CMOS's own defaults; a customized mapping is
        merged over them, so rating values the user didn't mention keep
        their default key (see _merge_rating_shortcuts).
        """
        if self.shortcuts.rating == _DEFAULT_RATING_SHORTCUTS:
            self.shortcuts = self.shortcuts.model_copy(
                update={"rating": dict(_CMOS_DEFAULT_RATING_SHORTCUTS)}
            )
        else:
            self.shortcuts = _merge_rating_shortcuts(
                self.shortcuts, _CMOS_DEFAULT_RATING_SHORTCUTS
            )
        return self
