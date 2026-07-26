"""How every test type turns a flat stimulus list into per-page trials.

Each `build_*_trials` differs only in what it needs from one item's group of
stimuli - a pair (AB), the reference against each test system (DMOS), the
reference plus exactly two (XAB), every rateable system (MUSHRA) - but they
all start from the same two steps, which live here so the rules are stated
once:

- an item's group is every stimulus sharing that item, and stimuli with no
  item belong to no trial;
- where a reference system exists, it is separated out and the remaining test
  stimuli are ordered by system name. That order is the canonical one the
  stored results are keyed to (system_a is the alphabetically first), so it
  must be the same in every test type.
"""

from __future__ import annotations

from .base import StimulusConfig


def _system_of(stimulus: StimulusConfig) -> str:
    """Return the stimulus's system name; '' when it has none (sorts first)."""
    return stimulus.system or ""


def _group_by_item(
    stimuli: list[StimulusConfig],
) -> list[tuple[str, list[StimulusConfig]]]:
    """(item, its stimuli) pairs in item order, skipping stimuli with no item.

    An explicit `stimuli:` list may leave `item` unset, and a stimulus with no
    item cannot be paired with anything, so it takes part in no trial.
    """
    by_item: dict[str, list[StimulusConfig]] = {}
    for s in stimuli:
        if s.item:
            by_item.setdefault(s.item, []).append(s)
    return sorted(by_item.items())


def _split_reference(
    group: list[StimulusConfig], reference_system: str
) -> tuple[StimulusConfig | None, list[StimulusConfig]]:
    """Split one item's group into its reference stimulus and the test ones.

    Returns (None, ...) when this item has no stimulus for the reference
    system; the reference-based test types skip such an item. The test
    stimuli come back in canonical (system name) order.
    """
    reference = next((s for s in group if _system_of(s) == reference_system), None)
    test_stimuli = sorted(
        (s for s in group if _system_of(s) != reference_system), key=_system_of
    )
    return reference, test_stimuli
