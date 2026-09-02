"""CMOS /api/config and /api/submit handlers."""

from __future__ import annotations

from fastapi import HTTPException

from ...config import CMOSConfig
from ...models import SubmitRequest
from ...storage import ResultSaver
from ._shared import (
    _all_stimuli,
    _id_to_meta,
    _metrics_row,
    _pair_config_response,
    _pair_row,
    _require_answered_once,
    _require_non_empty,
    _save_and_ok,
    _validate_pair,
)


def _get_cmos_test_config(config: CMOSConfig) -> dict:
    return _pair_config_response(config, rating_labels=config.rating_labels)


def _submit_cmos(body: SubmitRequest, config: CMOSConfig, saver: ResultSaver) -> dict:
    """Validate and persist CMOS choices.

    400 if empty, a pair is invalid/unknown, the rating is missing, or it is
    outside -3..3.
    """
    _require_non_empty(body.choices, "choices")
    # A trial is its pair, whichever order the client echoes the ids back in.
    _require_answered_once(
        ["+".join(sorted(c.stimulus_ids)) for c in body.choices], "choices", "trial"
    )
    id_to_meta = _id_to_meta(_all_stimuli(config))

    rows = []
    for choice in body.choices:
        meta1, meta2 = _validate_pair(id_to_meta, choice.stimulus_ids, "CMOS")
        if choice.rating is None:
            raise HTTPException(
                status_code=400, detail="rating is required for CMOS choices"
            )
        if not (-3 <= choice.rating <= 3):
            raise HTTPException(
                status_code=400,
                detail=f"CMOS rating must be -3 to 3, got {choice.rating}",
            )

        pair = _pair_row(meta1, meta2)
        # choice.rating means "stimulus_ids[1] relative to stimulus_ids[0]".
        # Flip its sign when stimulus_ids[0] isn't the canonical (system_a)
        # side; presented_first records which way round that was.
        canonical = meta1["system"] == pair["system_a"]
        rating = choice.rating if canonical else -choice.rating
        pair["rating"] = rating
        pair.update(_metrics_row(choice, config))
        rows.append(pair)

    return _save_and_ok(body, config, saver, rows)
