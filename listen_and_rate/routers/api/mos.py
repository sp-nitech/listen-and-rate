"""MOS /api/config and /api/submit handlers."""

from __future__ import annotations

import random

from fastapi import HTTPException

from ...config import MOSConfig, StimulusConfig
from ...models import SubmitRequest
from ...storage import ResultSaver
from ._shared import (
    _all_items,
    _id_to_meta,
    _practice_extras,
    _require_non_empty,
    _sample_keep_order,
    _save_and_ok,
    _test_config_response,
)


def _stimuli_to_response(items: list[StimulusConfig]) -> list[dict]:
    """Map stimuli to their blinded (id/label only) response shape."""
    return [{"id": s.id, "label": s.label} for s in items]


def _get_mos_test_config(config: MOSConfig) -> dict:
    all_items = _all_items(config)

    # Per-session sampling
    if config.stimuli_dirs and config.stimuli_dirs.utterances_per_session is not None:
        n = config.stimuli_dirs.utterances_per_session
        utterances = list({s.utterance for s in all_items if s.utterance})
        selected = set(random.sample(utterances, n))
        items = [s for s in all_items if s.utterance in selected]
    elif config.stimuli and config.stimuli.stimuli_per_session is not None:
        n = config.stimuli.stimuli_per_session
        items = _sample_keep_order(all_items, n)
    else:
        items = list(all_items)

    if config.shuffle_order:
        items = random.sample(items, len(items))

    stimuli = _stimuli_to_response(items)

    extras = _practice_extras(
        config, all_items, _stimuli_to_response, key="practice_stimuli"
    )
    return _test_config_response(
        config, stimuli=stimuli, rating_labels=config.rating_labels, **extras
    )


def _submit_mos(body: SubmitRequest, config: MOSConfig, saver: ResultSaver) -> dict:
    """Validate and persist MOS ratings.

    400 if empty, a stimulus ID is unknown, or a rating is outside 1-5.
    """
    _require_non_empty(body.ratings, "ratings")
    id_to_meta = _id_to_meta(_all_items(config))

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

    rows = [{**id_to_meta[r.stimulus_id], "rating": r.rating} for r in body.ratings]
    return _save_and_ok(body, config, saver, rows)
