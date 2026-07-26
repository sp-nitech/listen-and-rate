"""DMOS (degradation vs a reference) test configuration and trial pairing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

from pydantic import model_validator
from pydantic_core import PydanticCustomError

from ._trials import _group_by_item, _split_reference
from .base import (
    _DEFAULT_RATING_SHORTCUTS,
    BaseTestConfig,
    RatingLabelsConfigMixin,
    StimulusConfig,
    _merge_rating_shortcuts,
)
from .mos import _MOS_RATING_KEYS


class DMOSConfig(RatingLabelsConfigMixin, BaseTestConfig):
    """Top-level configuration for a DMOS (degradation vs a reference) test.

    Unlike AB/ABX (exactly 2 systems, symmetric), DMOS compares any number
    of "test" systems against one shared "reference" system flagged via
    `reference: true` in stimuli_dirs.systems.
    """

    test_type: Literal["dmos"]

    _RATING_LABEL_KEYS: ClassVar[set[str]] = _MOS_RATING_KEYS

    @model_validator(mode="after")
    def merge_rating_shortcut_defaults(self) -> DMOSConfig:
        """Fill unspecified shortcuts.rating values with the 1-5 defaults."""
        self.shortcuts = _merge_rating_shortcuts(
            self.shortcuts, _DEFAULT_RATING_SHORTCUTS
        )
        return self

    @model_validator(mode="after")
    def check_requires_dirs_with_one_reference(self) -> DMOSConfig:
        """Require stimuli_dirs: exactly one reference and >=1 test system."""
        if self.stimuli_list is not None:
            raise PydanticCustomError(
                "dmos_requires_stimuli_dirs",
                "dmos requires 'stimuli_dirs' (explicit 'stimuli_list' lists "
                "are not supported)",
            )
        systems = self.stimuli_dirs.systems if self.stimuli_dirs else []
        refs = [s for s in systems if s.reference]
        if len(refs) != 1:
            raise PydanticCustomError(
                "dmos_reference_count",
                "dmos requires exactly one stimuli_dirs.systems entry with "
                "reference: true, got {count}",
                {"count": len(refs)},
            )
        if len(systems) < 2:
            raise PydanticCustomError(
                "dmos_too_few_systems",
                "dmos requires at least one test system besides the reference",
            )
        return self

    @property
    def reference_system(self) -> str:
        """Resolved system name of the reference entry (system: or dir basename)."""
        systems = self.stimuli_dirs.systems if self.stimuli_dirs else []
        for s in systems:
            if s.reference:
                return s.resolved_system
        return ""


@dataclass(frozen=True)
class DMOSTrial:
    """One DMOS trial: a reference paired with one test-system stimulus."""

    item: str
    reference_id: str
    test_id: str
    test_system: str


def build_dmos_trials(
    stimuli: list[StimulusConfig], reference_system: str
) -> list[DMOSTrial]:
    """Pair the reference with each non-reference system's stimulus, by item.

    One trial per (item, test system) where both the reference and
    that test system have a stimulus for that item; combinations
    missing either are silently skipped, mirroring build_ab_trials().
    """
    trials = []
    for item, group in _group_by_item(stimuli):
        reference_stimulus, test_stimuli = _split_reference(group, reference_system)
        if reference_stimulus is None:
            continue
        for test_stimulus in test_stimuli:
            trials.append(
                DMOSTrial(
                    item=item,
                    reference_id=reference_stimulus.id,
                    test_id=test_stimulus.id,
                    test_system=test_stimulus.system or "",
                )
            )
    return trials
