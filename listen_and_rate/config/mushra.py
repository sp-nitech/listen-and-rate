"""MUSHRA (ITU-R BS.1534) listening test configuration and trial grouping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

from pydantic import model_validator
from pydantic_core import PydanticCustomError

from .base import BaseTestConfig, RatingLabelsConfigMixin, StimulusConfig

_MUSHRA_RATING_LABEL_KEYS = {"0", "20", "40", "60", "80"}


class MUSHRAConfig(RatingLabelsConfigMixin, BaseTestConfig):
    """Top-level configuration for a MUSHRA (ITU-R BS.1534) listening test.

    Rates every non-reference system (test systems and, optionally, one
    disclosed anchor) on a single 0-100 slider per system, in one trial per
    utterance. Unlike DMOS, both the reference and the anchor are optional
    (0 or 1 each) rather than mandatory, and every non-reference system is
    rated together in one trial instead of pairing the reference against one
    test system at a time.

    There is no automatic hidden-reference re-injection: an entry flagged
    `reference: true` is only ever a non-rateable playback clip. A
    BS.1534-style hidden reference needs no dedicated feature, though - add
    the reference audio as an ordinary (non-flagged) systems entry and it is
    blinded, shuffled, and rated like any other system. To have both the
    disclosed clip and a hidden copy, list the same audio under a second
    directory name (e.g. a symlink), since stimulus ids derive from the
    directory basename.
    """

    test_type: Literal["mushra"]

    _RATING_LABEL_KEYS: ClassVar[set[str]] = _MUSHRA_RATING_LABEL_KEYS

    @model_validator(mode="after")
    def check_requires_dirs_with_optional_reference_and_anchor(self) -> MUSHRAConfig:
        """Require stimuli_dirs: 0/1 reference, 0/1 anchor, >=2 rateable systems."""
        if self.stimuli is not None:
            raise PydanticCustomError(
                "mushra_requires_stimuli_dirs",
                "mushra requires 'stimuli_dirs' (explicit 'stimuli' lists "
                "are not supported)",
            )
        systems = self.stimuli_dirs.systems if self.stimuli_dirs else []
        refs = [s for s in systems if s.reference]
        if len(refs) > 1:
            raise PydanticCustomError(
                "mushra_reference_count",
                "mushra allows at most one stimuli_dirs.systems entry with "
                "reference: true, got {count}",
                {"count": len(refs)},
            )
        anchors = [s for s in systems if s.anchor]
        if len(anchors) > 1:
            raise PydanticCustomError(
                "mushra_anchor_count",
                "mushra allows at most one stimuli_dirs.systems entry with "
                "anchor: true, got {count}",
                {"count": len(anchors)},
            )
        conflicted = [s.resolved_system for s in systems if s.reference and s.anchor]
        if conflicted:
            # The reference is excluded from rating, so an anchor flag on the
            # same entry would silently do nothing - reject the contradiction.
            raise PydanticCustomError(
                "mushra_reference_anchor_conflict",
                "a stimuli_dirs.systems entry cannot be both reference and "
                "anchor: {conflicted}",
                {"conflicted": conflicted},
            )
        rateable = [s for s in systems if not s.reference]
        if len(rateable) < 2:
            raise PydanticCustomError(
                "mushra_too_few_rateable_systems",
                "mushra requires at least 2 non-reference systems to rate "
                "(test systems and/or an anchor)",
            )
        return self

    @property
    def reference_system(self) -> str | None:
        """Resolved system name of the reference entry, or None if unconfigured."""
        systems = self.stimuli_dirs.systems if self.stimuli_dirs else []
        for s in systems:
            if s.reference:
                return s.resolved_system
        return None

    @property
    def anchor_system(self) -> str | None:
        """Resolved system name of the anchor entry, or None if unconfigured."""
        systems = self.stimuli_dirs.systems if self.stimuli_dirs else []
        for s in systems:
            if s.anchor:
                return s.resolved_system
        return None


@dataclass(frozen=True)
class MUSHRATrial:
    """One MUSHRA trial: all rateable systems' clips for one utterance."""

    utterance: str
    reference_id: str | None
    system_ids: tuple[tuple[str, str], ...]  # ((system, stimulus_id), ...)


def build_mushra_trials(
    items: list[StimulusConfig],
    reference_system: str | None,
    rateable_systems: set[str],
) -> list[MUSHRATrial]:
    """Group stimuli into one MUSHRA trial per utterance.

    A trial requires every system in `rateable_systems` to have a stimulus
    for that utterance; utterances missing one are silently skipped,
    mirroring build_ab_trials()/build_dmos_trials(). The reference's
    stimulus, if `reference_system` is set and present for that utterance,
    is attached as reference_id; its absence does not skip the trial.
    """
    by_utterance: dict[str, list[StimulusConfig]] = {}
    for s in items:
        if s.utterance:
            by_utterance.setdefault(s.utterance, []).append(s)

    trials = []
    for utterance, group in sorted(by_utterance.items()):
        by_system = {s.system or "": s for s in group}
        if not rateable_systems <= by_system.keys():
            continue
        reference_stimulus = (
            by_system.get(reference_system) if reference_system else None
        )
        system_ids = tuple(
            (system, by_system[system].id) for system in sorted(rateable_systems)
        )
        trials.append(
            MUSHRATrial(
                utterance=utterance,
                reference_id=reference_stimulus.id if reference_stimulus else None,
                system_ids=system_ids,
            )
        )
    return trials
