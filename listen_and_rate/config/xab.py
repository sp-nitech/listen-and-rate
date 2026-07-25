"""XAB (similarity to a reference) listening test configuration and trial pairing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import model_validator
from pydantic_core import PydanticCustomError

from .base import BaseTestConfig, StimulusConfig


class XABConfig(BaseTestConfig):
    """Top-level configuration for an XAB (similarity to a reference) listening test.

    The listener first hears a disclosed reference X, then chooses which of
    two blinded test-system stimuli (A/B) sounds closer to it - a forced
    two-way choice (no tie). Unlike ABX, X is an independent reference
    recording (flagged via `reference: true` in stimuli_dirs.systems, like
    DMOS's), not a hidden duplicate of A or B, so no commitment-token
    blinding is involved.
    """

    test_type: Literal["xab"]

    @model_validator(mode="after")
    def check_requires_dirs_with_reference_and_two_systems(self) -> XABConfig:
        """Require stimuli_dirs: exactly one reference and two test systems."""
        if self.stimuli is not None:
            raise PydanticCustomError(
                "xab_requires_stimuli_dirs",
                "xab requires 'stimuli_dirs' (explicit 'stimuli' lists "
                "are not supported)",
            )
        systems = self.stimuli_dirs.systems if self.stimuli_dirs else []
        refs = [s for s in systems if s.reference]
        if len(refs) != 1:
            raise PydanticCustomError(
                "xab_reference_count",
                "xab requires exactly one stimuli_dirs.systems entry with "
                "reference: true, got {count}",
                {"count": len(refs)},
            )
        tests = [s for s in systems if not s.reference]
        if len(tests) != 2:
            raise PydanticCustomError(
                "xab_test_system_count",
                "xab requires exactly 2 non-reference stimuli_dirs.systems "
                "entries, got {count}",
                {"count": len(tests)},
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
class XABTrial:
    """One XAB trial: a reference plus the same item from both test systems."""

    item: str
    reference_id: str
    stimulus_ids: tuple[str, str]
    systems: tuple[str, str]


def build_xab_trials(
    stimuli: list[StimulusConfig], reference_system: str
) -> list[XABTrial]:
    """Group stimuli into one XAB trial per item.

    A trial requires the reference and exactly 2 test-system stimuli for the
    same item; items missing any of the three are silently skipped,
    mirroring build_ab_trials()/build_dmos_trials(). Test stimuli are ordered
    by system name, matching build_ab_trials()'s canonical pair order.
    """
    by_item: dict[str, list[StimulusConfig]] = {}
    for s in stimuli:
        if s.item:
            by_item.setdefault(s.item, []).append(s)

    trials = []
    for item, group in sorted(by_item.items()):
        reference_stimulus = next(
            (s for s in group if (s.system or "") == reference_system), None
        )
        if reference_stimulus is None:
            continue
        test_stimuli = sorted(
            (s for s in group if (s.system or "") != reference_system),
            key=lambda s: s.system or "",
        )
        if len(test_stimuli) != 2:
            continue
        trials.append(
            XABTrial(
                item=item,
                reference_id=reference_stimulus.id,
                stimulus_ids=(test_stimuli[0].id, test_stimuli[1].id),
                systems=(test_stimuli[0].system or "", test_stimuli[1].system or ""),
            )
        )
    return trials
