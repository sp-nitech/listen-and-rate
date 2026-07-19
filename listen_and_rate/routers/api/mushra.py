"""MUSHRA /api/config and /api/submit handlers."""

from __future__ import annotations

import random

from fastapi import HTTPException

from ...config import MUSHRAConfig, MUSHRATrial, StimulusConfig, build_mushra_trials
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


def _mushra_rateable_systems(
    config: MUSHRAConfig, all_items: list[StimulusConfig]
) -> set[str]:
    """Every system name present in `all_items` except the reference's own."""
    reference_system = config.reference_system
    return {s.system for s in all_items if s.system and s.system != reference_system}


def _build_mushra_response_trials(
    config: MUSHRAConfig, all_items: list[StimulusConfig]
) -> list[MUSHRATrial]:
    """Pair and sample the trial list for MUSHRA's /api/config."""
    trials = build_mushra_trials(
        all_items, config.reference_system, _mushra_rateable_systems(config, all_items)
    )

    n = config.stimuli_dirs.utterances_per_session if config.stimuli_dirs else None
    if n is not None:
        trials = _sample_trials_by_utterance(trials, n)
    if config.shuffle_order:
        trials = random.sample(trials, len(trials))
    return trials


def _mushra_trials_to_response(
    trials: list[MUSHRATrial],
    anchor_system: str | None,
    id_to_label: dict[str, str | None],
) -> list[dict]:
    """Map MUSHRA trials to their blinded {reference, systems, anchor} shape."""
    response_trials = []
    for t in trials:
        anchor_entry = next((e for e in t.system_ids if e[0] == anchor_system), None)
        blind_entries = [e for e in t.system_ids if e is not anchor_entry]
        random.shuffle(
            blind_entries
        )  # blind position: don't leak system identity via order
        response_trials.append(
            {
                "reference": (
                    {
                        "id": t.reference_id,
                        "label": id_to_label.get(t.reference_id),
                    }
                    if t.reference_id
                    else None
                ),
                "systems": [
                    {"id": sid, "label": id_to_label.get(sid)}
                    for _, sid in blind_entries
                ],
                "anchor": (
                    {"id": anchor_entry[1], "label": id_to_label.get(anchor_entry[1])}
                    if anchor_entry
                    else None
                ),
            }
        )
    return response_trials


def _get_mushra_test_config(config: MUSHRAConfig) -> dict:
    all_items = _all_items(config)
    anchor_system = config.anchor_system
    id_to_label = {s.id: s.label for s in all_items}
    response_trials = _mushra_trials_to_response(
        _build_mushra_response_trials(config, all_items), anchor_system, id_to_label
    )

    extras = _practice_extras(
        config,
        build_mushra_trials(
            all_items,
            config.reference_system,
            _mushra_rateable_systems(config, all_items),
        ),
        lambda ts: _mushra_trials_to_response(ts, anchor_system, id_to_label),
    )
    return _test_config_response(
        config,
        trials=response_trials,
        rating_labels=config.rating_labels,
        **extras,
    )


def _submit_mushra(
    body: SubmitRequest, config: MUSHRAConfig, saver: ResultSaver
) -> dict:
    """Validate and persist MUSHRA ratings.

    400 if empty, an id is unknown/reference, a rating is outside 0-100, or an
    utterance is incomplete.
    """
    _require_non_empty(body.ratings, "ratings")
    all_items = _all_items(config)
    id_to_meta = _id_to_meta(all_items)
    rateable_systems = _mushra_rateable_systems(config, all_items)

    rows = []
    by_utterance: dict[str, set[str]] = {}
    for item in body.ratings:
        meta = id_to_meta.get(item.stimulus_id)
        if meta is None:
            raise HTTPException(
                status_code=400, detail=f"Unknown stimulus ID: {item.stimulus_id}"
            )
        if meta["system"] not in rateable_systems:
            raise HTTPException(
                status_code=400,
                detail="stimulus_id must not be the reference system's own stimulus",
            )
        if not (0 <= item.rating <= 100):
            raise HTTPException(
                status_code=400,
                detail=f"MUSHRA rating must be 0-100, got {item.rating}",
            )
        by_utterance.setdefault(meta["utterance"], set()).add(meta["system"])
        rows.append(
            {
                "system": meta["system"],
                "utterance": meta["utterance"],
                "rating": item.rating,
            }
        )

    incomplete = [
        u for u, systems in by_utterance.items() if systems != rateable_systems
    ]
    if incomplete:
        raise HTTPException(
            status_code=400,
            detail=f"Each utterance must rate every system exactly once: "
            f"{sorted(incomplete)}",
        )

    return _save_and_ok(body, config, saver, rows)
