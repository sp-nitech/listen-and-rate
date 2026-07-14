"""DMOS /api/config and /api/submit handlers."""

from __future__ import annotations

import random

from fastapi import HTTPException

from ...config import DMOSConfig, DMOSTrial, StimulusConfig, build_dmos_trials
from ...models import SubmitRequest
from ...storage import ResultSaver
from ._shared import (
    _all_items,
    _id_to_meta,
    _practice_extras,
    _require_non_empty,
    _sample_trials_by_utterance,
    _save_and_ok,
    _test_config_response,
)


def _build_dmos_response_trials(
    config: DMOSConfig, all_items: list[StimulusConfig]
) -> list[DMOSTrial]:
    """Pair and sample the trial list for DMOS's /api/config.

    Unlike CMOS/AB/ABX (one trial per utterance), a DMOS utterance can have
    several trials (one per test system) - utterances_per_session samples
    whole utterances, keeping every test system's trial for each chosen one.
    """
    trials = build_dmos_trials(all_items, config.reference_system)

    n = config.stimuli_dirs.utterances_per_session if config.stimuli_dirs else None
    if n is not None:
        trials = _sample_trials_by_utterance(trials, n)
    if config.randomize:
        trials = random.sample(trials, len(trials))
    return trials


def _dmos_trials_to_response(
    trials: list[DMOSTrial], id_to_label: dict[str, str | None]
) -> list[dict]:
    """Map DMOS trials to their blinded {"reference", "test"} response shape."""
    return [
        {
            "reference": {
                "id": t.reference_id,
                "label": id_to_label.get(t.reference_id),
            },
            "test": {"id": t.test_id, "label": id_to_label.get(t.test_id)},
        }
        for t in trials
    ]


def _get_dmos_test_config(config: DMOSConfig) -> dict:
    all_items = _all_items(config)
    id_to_label = {s.id: s.label for s in all_items}
    response_trials = _dmos_trials_to_response(
        _build_dmos_response_trials(config, all_items), id_to_label
    )

    extras = _practice_extras(
        config,
        build_dmos_trials(all_items, config.reference_system),
        lambda ts: _dmos_trials_to_response(ts, id_to_label),
    )
    return _test_config_response(
        config,
        trials=response_trials,
        rating_labels=config.rating_labels,
        **extras,
    )


def _submit_dmos(body: SubmitRequest, config: DMOSConfig, saver: ResultSaver) -> dict:
    """Validate and persist DMOS ratings.

    400 if empty, a pair is invalid/unknown, or a rating is outside 1-5.
    """
    _require_non_empty(body.ratings, "ratings")
    id_to_meta = _id_to_meta(_all_items(config))
    reference_system = config.reference_system

    rows = []
    for item in body.ratings:
        if item.reference_id is None:
            raise HTTPException(
                status_code=400, detail="reference_id is required for DMOS ratings"
            )
        test_meta = id_to_meta.get(item.stimulus_id)
        ref_meta = id_to_meta.get(item.reference_id)
        if test_meta is None or ref_meta is None:
            unknown = sorted(
                i for i in (item.stimulus_id, item.reference_id) if i not in id_to_meta
            )
            raise HTTPException(
                status_code=400, detail=f"Unknown stimulus IDs: {unknown}"
            )
        if test_meta["utterance"] != ref_meta["utterance"]:
            raise HTTPException(
                status_code=400,
                detail="stimulus_id/reference_id do not share the same utterance",
            )
        if ref_meta["system"] != reference_system:
            raise HTTPException(
                status_code=400,
                detail="reference_id must belong to the reference system",
            )
        if test_meta["system"] == reference_system:
            raise HTTPException(
                status_code=400,
                detail="stimulus_id must not be the reference system's own stimulus",
            )
        if not (1 <= item.rating <= 5):
            raise HTTPException(
                status_code=400,
                detail=f"DMOS rating must be 1-5, got {item.rating}",
            )
        rows.append(
            {
                "system": test_meta["system"],
                "utterance": test_meta["utterance"],
                "rating": item.rating,
            }
        )

    return _save_and_ok(body, config, saver, rows)
