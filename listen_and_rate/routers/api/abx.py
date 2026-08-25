"""ABX /api/config and /api/submit handlers."""

from __future__ import annotations

from fastapi import HTTPException

from ...config import ABTrial, ABXConfig, build_ab_trials
from ...models import SubmitRequest
from ...rng import rng
from ...storage import ResultSaver
from ...x_token import commit, resolve
from ._shared import (
    _all_stimuli,
    _build_response_trials,
    _id_to_meta,
    _metrics_row,
    _practice_extras,
    _require_answered_once,
    _require_non_empty,
    _save_and_ok,
    _test_config_response,
    _validate_pair,
)


def _abx_trials_to_response(
    trials: list[ABTrial], id_to_label: dict[str, str | None], x_secret: bytes
) -> list[dict]:
    """Map AB trials to ABX's blinded {"stimuli", "x"} response shape."""
    response_trials = []
    for t in trials:
        ids = list(t.stimulus_ids)
        rng.shuffle(ids)  # blind position: don't always show system A first
        id_a, id_b = ids
        matched_id = rng.choice(ids)  # ground truth: which stimulus X duplicates
        x_token = commit(id_a, id_b, matched_id, x_secret)
        response_trials.append(
            {
                "stimuli": [{"id": i, "label": id_to_label.get(i)} for i in ids],
                "x": {"token": x_token},
            }
        )
    return response_trials


def _get_abx_test_config(config: ABXConfig, x_secret: bytes) -> dict:
    all_stimuli = _all_stimuli(config)
    id_to_label = {s.id: s.label for s in all_stimuli}
    response_trials = _abx_trials_to_response(
        _build_response_trials(config, all_stimuli), id_to_label, x_secret
    )

    extras = _practice_extras(
        config,
        build_ab_trials(all_stimuli),
        lambda ts: _abx_trials_to_response(ts, id_to_label, x_secret),
    )
    return _test_config_response(config, trials=response_trials, **extras)


def _submit_abx(
    body: SubmitRequest, config: ABXConfig, saver: ResultSaver, x_secret: bytes
) -> dict:
    """Validate and score ABX guesses.

    400 if empty, a pair is invalid/unknown, or the x_token doesn't verify.
    """
    _require_non_empty(body.choices, "choices")
    # A trial is its pair, whichever order the client echoes the ids back in.
    _require_answered_once(
        ["+".join(sorted(c.stimulus_ids)) for c in body.choices], "choices", "trial"
    )
    id_to_meta = _id_to_meta(_all_stimuli(config))

    rows = []
    for choice in body.choices:
        meta1, meta2 = _validate_pair(id_to_meta, choice.stimulus_ids, "ABX")
        id1, id2 = choice.stimulus_ids
        if choice.selected_stimulus_id is None:
            # ABX is forced-choice today; unlike AB, None isn't a valid tie
            # response.
            raise HTTPException(
                status_code=400, detail="selected_stimulus_id is required for ABX"
            )
        if choice.selected_stimulus_id not in choice.stimulus_ids:
            raise HTTPException(
                status_code=400,
                detail="selected_stimulus_id must be one of stimulus_ids",
            )
        if choice.x_token is None:
            raise HTTPException(status_code=400, detail="x_token is required for ABX")

        ground_truth = resolve(id1, id2, choice.x_token, x_secret)
        if ground_truth is None:
            raise HTTPException(status_code=400, detail="Invalid or expired x_token")

        system_a, system_b = sorted([meta1["system"], meta2["system"]])
        rows.append(
            {
                "system_a": system_a,
                "system_b": system_b,
                "presented_first": meta1["system"],
                "x_matched": id_to_meta[ground_truth]["system"],
                "item": meta1["item"],
                "correct": choice.selected_stimulus_id == ground_truth,
                **_metrics_row(choice, config),
            }
        )

    return _save_and_ok(body, config, saver, rows)
