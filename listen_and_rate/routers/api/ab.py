"""AB /api/config and /api/submit handlers."""

from __future__ import annotations

from fastapi import HTTPException

from ...config import ABConfig
from ...models import SubmitRequest
from ...storage import OUTCOME_A, OUTCOME_B, OUTCOME_TIE, ResultSaver
from ._shared import (
    _all_stimuli,
    _id_to_meta,
    _metrics_row,
    _pair_config_response,
    _require_answered_once,
    _require_non_empty,
    _save_and_ok,
    _validate_pair,
)


def _get_ab_test_config(config: ABConfig) -> dict:
    return _pair_config_response(config, allow_tie=config.allow_tie)


def _submit_ab(body: SubmitRequest, config: ABConfig, saver: ResultSaver) -> dict:
    """Validate and persist AB choices.

    400 if empty, a pair is invalid/unknown, or a disallowed tie.
    """
    _require_non_empty(body.choices, "choices")
    # A trial is its pair, whichever order the client echoes the ids back in.
    _require_answered_once(
        ["+".join(sorted(c.stimulus_ids)) for c in body.choices], "choices", "trial"
    )
    id_to_meta = _id_to_meta(_all_stimuli(config))

    rows = []
    for choice in body.choices:
        meta1, meta2 = _validate_pair(id_to_meta, choice.stimulus_ids, "AB")
        if (
            choice.selected_stimulus_id is not None
            and choice.selected_stimulus_id not in choice.stimulus_ids
        ):
            raise HTTPException(
                status_code=400,
                detail="selected_stimulus_id must be one of stimulus_ids",
            )
        if choice.selected_stimulus_id is None and not config.allow_tie:
            raise HTTPException(
                status_code=400, detail="Ties are not allowed for this test"
            )

        system_a, system_b = sorted([meta1["system"], meta2["system"]])
        # Record which SIDE of the pair won as a positional token, not the
        # system name, so any name (including "tie") is collision-free.
        if choice.selected_stimulus_id is None:
            winner = OUTCOME_TIE
        else:
            chosen = id_to_meta[choice.selected_stimulus_id]["system"]
            winner = OUTCOME_A if chosen == system_a else OUTCOME_B
        rows.append(
            {
                "system_a": system_a,
                "system_b": system_b,
                "item": meta1["item"],
                "winner": winner,
                **_metrics_row(choice, config),
            }
        )

    return _save_and_ok(body, config, saver, rows)
