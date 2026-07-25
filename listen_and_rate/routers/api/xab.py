"""XAB /api/config and /api/submit handlers."""

from __future__ import annotations

import random

from fastapi import HTTPException

from ...config import StimulusConfig, XABConfig, XABTrial, build_xab_trials
from ...models import SubmitRequest
from ...storage import OUTCOME_A, OUTCOME_B, ResultSaver
from ._shared import (
    _all_stimuli,
    _id_to_meta,
    _practice_extras,
    _require_non_empty,
    _sample_keep_order,
    _save_and_ok,
    _test_config_response,
    _validate_pair,
)


def _build_xab_response_trials(
    config: XABConfig, all_stimuli: list[StimulusConfig]
) -> list[XABTrial]:
    """Pair and sample the trial list for XAB's /api/config (one per item)."""
    trials = build_xab_trials(all_stimuli, config.reference_system)

    n = config.stimuli_dirs.items_per_session if config.stimuli_dirs else None
    if n is not None:
        trials = _sample_keep_order(trials, n)
    if config.shuffle_order:
        trials = random.sample(trials, len(trials))
    return trials


def _xab_trials_to_response(
    trials: list[XABTrial], id_to_label: dict[str, str | None]
) -> list[dict]:
    """Map XAB trials to their blinded {"reference", "stimuli"} response shape."""
    response_trials = []
    for t in trials:
        ids = list(t.stimulus_ids)
        random.shuffle(ids)  # blind position: don't always show system A first
        response_trials.append(
            {
                "reference": {
                    "id": t.reference_id,
                    "label": id_to_label.get(t.reference_id),
                },
                "stimuli": [{"id": i, "label": id_to_label.get(i)} for i in ids],
            }
        )
    return response_trials


def _get_xab_test_config(config: XABConfig) -> dict:
    all_stimuli = _all_stimuli(config)
    id_to_label = {s.id: s.label for s in all_stimuli}
    response_trials = _xab_trials_to_response(
        _build_xab_response_trials(config, all_stimuli), id_to_label
    )

    extras = _practice_extras(
        config,
        build_xab_trials(all_stimuli, config.reference_system),
        lambda ts: _xab_trials_to_response(ts, id_to_label),
    )
    return _test_config_response(config, trials=response_trials, **extras)


def _submit_xab(body: SubmitRequest, config: XABConfig, saver: ResultSaver) -> dict:
    """Validate and persist XAB choices.

    400 if empty, a pair is invalid/unknown, includes the reference, or lacks
    a selection.
    """
    _require_non_empty(body.choices, "choices")
    id_to_meta = _id_to_meta(_all_stimuli(config))
    reference_system = config.reference_system

    rows = []
    for choice in body.choices:
        meta1, meta2 = _validate_pair(id_to_meta, choice.stimulus_ids, "XAB")
        if reference_system in (meta1["system"], meta2["system"]):
            raise HTTPException(
                status_code=400,
                detail="stimulus_ids must not include the reference system's stimulus",
            )
        if choice.selected_stimulus_id is None:
            # XAB is forced-choice; unlike AB, None isn't a valid tie response.
            raise HTTPException(
                status_code=400, detail="selected_stimulus_id is required for XAB"
            )
        if choice.selected_stimulus_id not in choice.stimulus_ids:
            raise HTTPException(
                status_code=400,
                detail="selected_stimulus_id must be one of stimulus_ids",
            )

        system_a, system_b = sorted([meta1["system"], meta2["system"]])
        # Positional token (which side is closer to the reference), not the
        # system name - matches AB's winner encoding; XAB has no tie.
        chosen = id_to_meta[choice.selected_stimulus_id]["system"]
        closer = OUTCOME_A if chosen == system_a else OUTCOME_B
        rows.append(
            {
                "system_a": system_a,
                "system_b": system_b,
                "item": meta1["item"],
                "closer": closer,
            }
        )

    return _save_and_ok(body, config, saver, rows)
