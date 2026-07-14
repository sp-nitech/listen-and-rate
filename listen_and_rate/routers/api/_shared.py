"""Helpers shared by every test type's /api/config and /api/submit handlers.

Metadata validation, stimulus sampling, the config-response scaffold, and pair
trial building/validation. The per-test-type modules (mos, dmos, ...) build on
these; routes.py wires the actual endpoints.
"""

from __future__ import annotations

import hashlib
import random
import re
from collections.abc import Callable
from typing import Protocol, TypeVar

from fastapi import HTTPException

from ...config import (
    ABConfig,
    ABTrial,
    ABXConfig,
    CMOSConfig,
    Config,
    MetadataFieldConfig,
    StimulusConfig,
    build_ab_trials,
)
from ...models import SubmitRequest
from ...storage import ResultSaver

T = TypeVar("T")

_METADATA_TEXT_RE = re.compile(r"^[a-zA-Z0-9-]+$")


def _validate_metadata(
    fields: list[MetadataFieldConfig], metadata: dict[str, str]
) -> dict[str, str]:
    """Validate submitted metadata against the configured field definitions.

    Raises HTTPException(400) on a missing required field, a text field that
    doesn't match the client's input pattern, or a select value outside its
    configured options. Returns a sanitized dict containing only keys that
    are declared in `fields`, so undeclared keys never reach storage.
    """
    sanitized: dict[str, str] = {}
    for field in fields:
        value = metadata.get(field.key)
        if not value:
            if field.required:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required metadata field: {field.key!r}",
                )
            continue
        if field.type == "text" and not _METADATA_TEXT_RE.match(value):
            raise HTTPException(
                status_code=400,
                detail=f"Metadata field {field.key!r} contains invalid characters",
            )
        if field.type == "select" and field.options and value not in field.options:
            raise HTTPException(
                status_code=400,
                detail=f"Metadata field {field.key!r}: {value!r} is not one "
                f"of {field.options}",
            )
        sanitized[field.key] = value
    return sanitized


def _all_items(config: Config) -> list[StimulusConfig]:
    """Return the config's full stimulus list ([] when none is resolved)."""
    return config.stimuli.items if config.stimuli else []


def _id_to_meta(all_items: list[StimulusConfig]) -> dict[str, dict[str, str]]:
    """Build the id → {system, utterance} lookup shared by every _submit_* validator."""
    return {
        s.id: {"system": s.system or "", "utterance": s.utterance or s.id}
        for s in all_items
    }


def _sample_keep_order(items: list[T], n: int) -> list[T]:
    """Randomly select n items, preserving their original relative order.

    random.sample() alone returns items in random order, which would ignore
    randomize=False's "keep the fixed/deterministic order" contract; mirrors
    frontend/config.php's sample_keep_order().
    """
    n = min(n, len(items))
    indices = sorted(random.sample(range(len(items)), n))
    return [items[i] for i in indices]


class _UtteranceTrial(Protocol):
    """Structural type for whole-utterance-sampled trials (DMOSTrial, MUSHRATrial)."""

    @property
    def utterance(self) -> str:
        """The utterance this trial belongs to."""
        ...


TrialT = TypeVar("TrialT", bound=_UtteranceTrial)


def _sample_trials_by_utterance(trials: list[TrialT], n: int) -> list[TrialT]:
    """Randomly select n whole utterances, keeping every trial of each chosen one.

    Shared by DMOS and MUSHRA, whose utterances_per_session samples utterances
    rather than individual trials; relative trial order is preserved
    (see _sample_keep_order).
    """
    utterances = list(dict.fromkeys(t.utterance for t in trials))
    selected = set(_sample_keep_order(utterances, n))
    return [t for t in trials if t.utterance in selected]


def _config_version(config: Config) -> str:
    """Stateless fingerprint of the loaded config, for client-side resume.

    Hashes the resolved config, which is stable across requests and process
    restarts (the per-request stimulus shuffle/sampling happens later, in the
    route handlers, not here) and changes whenever the admin edits the config -
    so a saved in-progress session can tell whether it still matches. Computed
    fresh per request, holding no server state. The PHP deployment computes its
    own fingerprint over config_data.php; the two need not agree, since a
    session only ever resumes against the same deployment that saved it.
    """
    return hashlib.sha256(config.model_dump_json().encode()).hexdigest()[:16]


def _test_config_response(config: Config, **extras: object) -> dict:
    """Build the /api/config response fields shared by every test type.

    Type-specific fields (stimuli/trials, rating_labels, allow_tie, ...) are
    passed as keyword arguments. randomize is always False in the response
    because shuffling already happened server-side.
    """
    return {
        "experiment_id": config.experiment_id,
        "config_version": _config_version(config),
        "test_type": config.test_type,
        "title": config.title,
        "instructions": config.instructions,
        "randomize": False,
        "preload_audio": config.preload_audio,
        "metadata": [f.model_dump() for f in config.metadata],
        "shortcuts": config.shortcuts.browser_dict(),
        **extras,
    }


def _practice_extras(
    config: Config,
    pool: list[T],
    to_response: Callable[[list[T]], list[dict]],
    key: str = "practice_trials",
) -> dict:
    """Build the practice_* response fields shared by every test type.

    Practice pages are drawn from the full `pool` (all stimuli/trials)
    independently of the session sampling, so overlap with the real session
    is allowed; random.sample also randomizes their order. Returns {} when no
    practice stage is configured, keeping the response unchanged.
    load_config guarantees practice.count <= len(pool).
    """
    if config.practice is None or config.practice.count == 0:
        return {}
    sampled = random.sample(pool, config.practice.count)
    return {
        key: to_response(sampled),
        "practice_instructions": config.practice.instructions,
    }


def _require_non_empty(items: list, name: str) -> None:
    """Raise HTTPException(400) if the submitted ratings/choices list is empty."""
    if not items:
        raise HTTPException(status_code=400, detail=f"{name} must be a non-empty list")


def _save_and_ok(
    body: SubmitRequest, config: Config, saver: ResultSaver, rows: list[dict]
) -> dict:
    """Validate metadata, persist one session's rows, and return the ok response.

    The shared tail of every _submit_* handler - rows are the already
    validated, storage-shaped dicts built by the type-specific validator.
    """
    metadata = _validate_metadata(config.metadata, body.metadata)
    saver.save(
        session_id=body.session_id,
        test_type=config.test_type,
        ratings=rows,
        metadata=metadata,
    )
    return {"status": "ok", "session_id": body.session_id}


def _validate_pair(
    id_to_meta: dict[str, dict[str, str]], stimulus_ids: list[str], type_label: str
) -> tuple[dict[str, str], dict[str, str]]:
    """Validate a submitted stimulus_ids pair.

    Exactly 2 known ids, same utterance, different system.
    """
    if len(stimulus_ids) != 2:
        raise HTTPException(
            status_code=400,
            detail=f"Each {type_label} choice must reference exactly 2 stimulus_ids",
        )
    id1, id2 = stimulus_ids
    meta1 = id_to_meta.get(id1)
    meta2 = id_to_meta.get(id2)
    if meta1 is None or meta2 is None:
        unknown = sorted(i for i in (id1, id2) if i not in id_to_meta)
        raise HTTPException(status_code=400, detail=f"Unknown stimulus IDs: {unknown}")
    if meta1["utterance"] != meta2["utterance"] or meta1["system"] == meta2["system"]:
        raise HTTPException(
            status_code=400,
            detail=f"stimulus_ids do not form a valid {type_label} trial "
            f"pair: {stimulus_ids}",
        )
    return meta1, meta2


def _build_response_trials(
    config: CMOSConfig | ABConfig | ABXConfig, all_items: list[StimulusConfig]
) -> list[ABTrial]:
    """Pair and sample the trial list shared by CMOS's, AB's, and ABX's /api/config."""
    trials = build_ab_trials(all_items)

    # Per-session sampling (trial = one utterance's pair of stimuli)
    n = config.stimuli_dirs.utterances_per_session if config.stimuli_dirs else None
    if n is not None:
        trials = _sample_keep_order(trials, n)
    if config.randomize:
        trials = random.sample(trials, len(trials))
    return trials


def _pair_trials_to_response(
    trials: list[ABTrial], id_to_label: dict[str, str | None]
) -> list[dict]:
    """Map AB trials to the blinded {"stimuli": [...]} shape shared by CMOS and AB.

    Each trial's pair is shuffled so system A doesn't always appear first
    (ABX needs the shuffled ids for its x token, so it keeps its own loop).
    """
    response_trials = []
    for t in trials:
        ids = list(t.stimulus_ids)
        random.shuffle(ids)  # blind position: don't always show system A first
        response_trials.append(
            {"stimuli": [{"id": i, "label": id_to_label.get(i)} for i in ids]}
        )
    return response_trials


def _pair_config_response(config: CMOSConfig | ABConfig, **type_extras: object) -> dict:
    """Build the full /api/config response shared by CMOS and AB."""
    all_items = _all_items(config)
    id_to_label = {s.id: s.label for s in all_items}
    trials = _pair_trials_to_response(
        _build_response_trials(config, all_items), id_to_label
    )
    extras = _practice_extras(
        config,
        build_ab_trials(all_items),
        lambda ts: _pair_trials_to_response(ts, id_to_label),
    )
    return _test_config_response(config, trials=trials, **type_extras, **extras)
