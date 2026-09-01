"""XAB /api/config and /api/submit handlers."""

from __future__ import annotations

from fastapi import HTTPException

from ...config import StimulusConfig, XABConfig, XABTrial, build_xab_trials
from ...models import SubmitRequest
from ...rng import rng
from ...storage import OUTCOME_A, OUTCOME_B, ResultSaver
from ._shared import (
    _all_stimuli,
    _id_to_meta,
    _metrics_row,
    _pair_row,
    _practice_extras,
    _require_answered_once,
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
        trials = rng.sample(trials, len(trials))
    return trials


def _xab_trials_to_response(
    trials: list[XABTrial], id_to_label: dict[str, str | None]
) -> list[dict]:
    """Map XAB trials to their blinded {"reference", "stimuli"} response shape."""
    response_trials = []
    for t in trials:
        ids = list(t.stimulus_ids)
        rng.shuffle(ids)  # blind position: don't always show system A first
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
    # A trial is its pair, whichever order the client echoes the ids back in.
    _require_answered_once(
        ["+".join(sorted(c.stimulus_ids)) for c in body.choices], "choices", "trial"
    )
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

        pair = _pair_row(meta1, meta2)
        # Positional token (which side is closer to the reference), not the
        # system name - matches AB's winner encoding. XAB has no tie.
        chosen = id_to_meta[choice.selected_stimulus_id]["system"]
        closer = OUTCOME_A if chosen == pair["system_a"] else OUTCOME_B
        rows.append({**pair, "closer": closer, **_metrics_row(choice, config)})

    return _save_and_ok(body, config, saver, rows)
