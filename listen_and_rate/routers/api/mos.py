"""MOS /api/config and /api/submit handlers."""

from __future__ import annotations

import random

from fastapi import HTTPException

from ...config import MOSConfig, StimulusConfig
from ...models import SubmitRequest
from ...storage import ResultSaver
from ._shared import (
    _all_stimuli,
    _id_to_meta,
    _metrics_row,
    _practice_extras,
    _require_answered_once,
    _require_non_empty,
    _sample_keep_order,
    _save_and_ok,
    _test_config_response,
)


def _stimuli_to_response(stimuli: list[StimulusConfig]) -> list[dict]:
    """Map stimuli to their blinded (id/label only) response shape."""
    return [{"id": s.id, "label": s.label} for s in stimuli]


def _get_mos_test_config(config: MOSConfig) -> dict:
    all_stimuli = _all_stimuli(config)

    # Per-session sampling
    if config.stimuli_dirs and config.stimuli_dirs.items_per_session is not None:
        n = config.stimuli_dirs.items_per_session
        items = list({s.item for s in all_stimuli if s.item})
        selected = set(random.sample(items, n))
        selected_stimuli = [s for s in all_stimuli if s.item in selected]
    elif config.stimuli and config.stimuli.stimuli_per_session is not None:
        n = config.stimuli.stimuli_per_session
        selected_stimuli = _sample_keep_order(all_stimuli, n)
    else:
        selected_stimuli = list(all_stimuli)

    if config.shuffle_order:
        selected_stimuli = random.sample(selected_stimuli, len(selected_stimuli))

    stimuli = _stimuli_to_response(selected_stimuli)

    extras = _practice_extras(
        config, all_stimuli, _stimuli_to_response, key="practice_stimuli"
    )
    return _test_config_response(
        config, stimuli=stimuli, rating_labels=config.rating_labels, **extras
    )


def _submit_mos(body: SubmitRequest, config: MOSConfig, saver: ResultSaver) -> dict:
    """Validate and persist MOS ratings.

    400 if empty, a stimulus ID is unknown, or a rating is outside 1-5.
    """
    _require_non_empty(body.ratings, "ratings")
    _require_answered_once([r.stimulus_id for r in body.ratings], "ratings", "stimulus")
    id_to_meta = _id_to_meta(_all_stimuli(config))

    unknown = {r.stimulus_id for r in body.ratings} - id_to_meta.keys()
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"Unknown stimulus IDs: {sorted(unknown)}"
        )

    for r in body.ratings:
        if not (1 <= r.rating <= 5):
            raise HTTPException(
                status_code=400,
                detail=f"MOS rating must be 1-5, got {r.rating} for {r.stimulus_id}",
            )

    rows = [
        {**id_to_meta[r.stimulus_id], "rating": r.rating, **_metrics_row(r, config)}
        for r in body.ratings
    ]
    return _save_and_ok(body, config, saver, rows)
