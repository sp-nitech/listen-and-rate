"""AB (paired forced-choice) listening test configuration and trial pairing.

build_ab_trials()/ABTrial are also reused by CMOS and ABX, since all three
pair stimuli the same way (2 systems, same item).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ._trials import _group_by_item, _system_of
from .base import StimulusConfig
from .two_system import TwoSystemComparisonConfig


class ABConfig(TwoSystemComparisonConfig):
    """Top-level configuration for an AB (paired forced-choice) listening test."""

    test_type: Literal["ab"]
    allow_tie: bool = True


@dataclass(frozen=True)
class ABTrial:
    """One AB comparison: the same item from two different systems."""

    item: str
    stimulus_ids: tuple[str, str]
    systems: tuple[str, str]


def build_ab_trials(stimuli: list[StimulusConfig]) -> list[ABTrial]:
    """Pair stimuli into AB trials by item.

    Items not present in exactly 2 stimuli are silently skipped - this is
    where the "drop unpaired items" behavior lives; the UserWarning about
    them was already emitted by `_expand_stimuli_dirs`.
    """
    trials = []
    for item, group in _group_by_item(stimuli):
        if len(group) != 2:
            continue
        pair = sorted(group, key=_system_of)
        trials.append(
            ABTrial(
                item=item,
                stimulus_ids=(pair[0].id, pair[1].id),
                systems=(pair[0].system or "", pair[1].system or ""),
            )
        )
    return trials
