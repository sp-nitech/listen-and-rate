"""AB (paired forced-choice) listening test configuration and trial pairing.

build_ab_trials()/ABTrial are also reused by CMOS and ABX, since all three
pair stimuli the same way (2 systems, same utterance).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .base import StimulusConfig
from .two_system import TwoSystemComparisonConfig


class ABConfig(TwoSystemComparisonConfig):
    """Top-level configuration for an AB (paired forced-choice) listening test."""

    test_type: Literal["ab"]
    allow_tie: bool = True


@dataclass(frozen=True)
class ABTrial:
    """One AB comparison: the same utterance from two different systems."""

    utterance: str
    stimulus_ids: tuple[str, str]
    systems: tuple[str, str]


def build_ab_trials(items: list[StimulusConfig]) -> list[ABTrial]:
    """Pair stimuli into AB trials by utterance.

    Utterances not present in exactly 2 stimuli are silently skipped - this is
    where the "drop unpaired utterances" behavior lives; the UserWarning about
    them was already emitted by `_expand_stimuli_dirs`.
    """
    by_utterance: dict[str, list[StimulusConfig]] = {}
    for s in items:
        if s.utterance:
            by_utterance.setdefault(s.utterance, []).append(s)

    trials = []
    for utterance, group in sorted(by_utterance.items()):
        if len(group) != 2:
            continue
        pair = sorted(group, key=lambda s: s.system or "")
        trials.append(
            ABTrial(
                utterance=utterance,
                stimulus_ids=(pair[0].id, pair[1].id),
                systems=(pair[0].system or "", pair[1].system or ""),
            )
        )
    return trials
