"""Helpers shared by every test type's /api/config and /api/submit handlers.

Metadata validation, stimulus sampling, the config-response scaffold, and pair
trial building/validation. The per-test-type modules (mos, dmos, ...) build on
these; routes.py wires the actual endpoints.
"""

from __future__ import annotations

import hashlib
import json
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
from ...config._utils import _duplicates
from ...models import SubmitRequest
from ...storage import METRIC_DECIMALS, ResultSaver

T = TypeVar("T")

# Text form values. Kept in sync with frontend/js/metadata.js and
# frontend/save.php. \Z, not $: both Python's and PCRE's $ also match before a
# trailing newline, so "alice\n" would pass here and in save.php while the
# browser's JS regex (whose $ does not) rejects it - letting a crafted request
# store a value the form itself refuses, newline and all.
_METADATA_TEXT_RE = re.compile(r"^[a-zA-Z0-9.-]+\Z")


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


def _all_stimuli(config: Config) -> list[StimulusConfig]:
    """Return the config's full stimulus list ([] when none is resolved)."""
    return config.stimuli_list.entries if config.stimuli_list else []


def _id_to_meta(all_stimuli: list[StimulusConfig]) -> dict[str, dict[str, str]]:
    """Build the id → {system, item} lookup shared by every _submit_* validator."""
    return {
        s.id: {"system": s.system or "", "item": s.item or s.id} for s in all_stimuli
    }


def _sample_keep_order(values: list[T], n: int) -> list[T]:
    """Randomly select n values, preserving their original relative order.

    random.sample() alone returns values in random order, which would ignore
    presentation_order="fixed"'s "keep the configured order" contract (the
    later shuffle applies it for "random"); mirrors frontend/config.php's
    sample_keep_order().
    """
    n = min(n, len(values))
    indices = sorted(random.sample(range(len(values)), n))
    return [values[i] for i in indices]


class _ItemTrial(Protocol):
    """Structural type for whole-item-sampled trials (DMOSTrial, MUSHRATrial)."""

    @property
    def item(self) -> str:
        """The item this trial belongs to."""
        ...


TrialT = TypeVar("TrialT", bound=_ItemTrial)


def _sample_trials_by_item(trials: list[TrialT], n: int) -> list[TrialT]:
    """Randomly select n whole items, keeping every trial of each chosen one.

    Shared by DMOS and MUSHRA, whose items_per_session samples items
    rather than individual trials; relative trial order is preserved
    (see _sample_keep_order).
    """
    items = list(dict.fromkeys(t.item for t in trials))
    selected = set(_sample_keep_order(items, n))
    return [t for t in trials if t.item in selected]


def _config_version(config: Config) -> str:
    """Stateless fingerprint of the loaded config, for client-side resume.

    Hashes the resolved config, which is stable across requests and process
    restarts (the per-request stimulus shuffle/sampling happens later, in the
    route handlers, not here) and changes whenever the admin edits the config -
    so a saved in-progress session can tell whether it still matches. Computed
    fresh per request, holding no server state. The PHP deployment computes its
    own fingerprint over config_data.php; the two need not agree, since a
    session only ever resumes against the same deployment that saved it.

    durations is hashed alongside the model because it is a private attribute
    and so absent from model_dump_json(), yet it is measured from the audio and
    served to the browser: replacing a clip with one of a different length
    without renaming it changes what the listener gets while leaving the model
    byte-identical. config_data.php carries durations inline, so the PHP
    fingerprint already covers this; including it here keeps the two backends
    invalidating a saved session under the same circumstances.
    """
    fingerprinted = config.model_dump_json() + json.dumps(
        config.durations, sort_keys=True
    )
    return hashlib.sha256(fingerprinted.encode()).hexdigest()[:16]


def _test_config_response(config: Config, **extras: object) -> dict:
    """Build the /api/config response fields shared by every test type.

    Type-specific fields (stimuli/trials, rating_labels, allow_tie, ...) are
    passed as keyword arguments. The stimuli/trials are already in final
    order (presentation_order is applied server-side), so nothing about
    ordering is echoed to the browser.
    """
    return {
        "experiment_id": config.experiment_id,
        "config_version": _config_version(config),
        "test_type": config.test_type,
        "title": config.title,
        "instructions": config.instructions,
        "audio_preload": config.audio_preload,
        # {stimulus_id: seconds}, so the player's time bar shows clip length
        # immediately instead of flickering from "--" once metadata loads.
        # Deliberately covers EVERY stimulus, not just this session's sample:
        # practice clips are drawn from the full pool (_practice_extras).
        "durations": config.durations,
        # Each form is one {title, description, fields} block, the same shape
        # as the YAML, so the concept keeps a single shape across every layer.
        "metadata": {
            "title": config.metadata.title,
            "description": config.metadata.description,
            "fields": [f.model_dump() for f in config.metadata.fields],
        },
        "survey": {
            "title": config.survey.title,
            "description": config.survey.description,
            "fields": [f.model_dump() for f in config.survey.fields],
        },
        # Which per-answer measurements to take; the frontend measures only
        # what is enabled here, and the submit handlers store only that too.
        "metrics": config.metrics.model_dump(),
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
    extras: dict[str, object] = {key: to_response(sampled)}
    # Omitted rather than sent empty when unset, so the frontend can tell
    # "no banner" from "an empty one"; mirrors config.php's practice_extras().
    if config.practice.instructions is not None:
        extras["practice_instructions"] = config.practice.instructions
    return extras


def _require_non_empty(values: list, name: str) -> None:
    """Raise HTTPException(400) if the submitted ratings/choices list is empty."""
    if not values:
        raise HTTPException(status_code=400, detail=f"{name} must be a non-empty list")


def _metrics_row(entry: object, config: Config) -> dict:
    """Build the `metrics` sub-dict for one answer, or {} to store none.

    Only the metrics the config opts into are kept, so a client that sends a
    value the experiment did not ask for cannot slip it into the results. The
    key is omitted entirely when nothing is collected, which keeps the stored
    shape (and the CSV header) identical to before this existed.

    Rounded to METRIC_DECIMALS: the browser reports sub-microsecond floats,
    and the digits below that are noise rather than measurement.
    """
    measured = {}
    for key in config.metrics.enabled_keys():
        value = getattr(entry, key, None)
        if value is not None:
            measured[key] = round(float(value), METRIC_DECIMALS)
    return {"metrics": measured} if measured else {}


def _require_answered_once(keys: list[str], name: str, unit: str) -> None:
    """Raise HTTPException(400) if any of `keys` appears more than once.

    Each key names what one answer is about - the stimulus for the MOS-family
    types, the trial for the pair-based ones - so a listener cannot answer the
    same thing twice in a single submission. The frontend keys its answers by
    exactly this, so it never produces a repeat; one therefore means a broken
    client rather than a correction to merge. Storing both would double that
    listener's weight in every mean and narrow the confidence interval with an
    observation that is not independent, silently and with nothing in the
    saved results to show for it.
    """
    duplicated = _duplicates(keys)
    if duplicated:
        raise HTTPException(
            status_code=400,
            detail=f"{name} must answer each {unit} once; repeated: {duplicated}",
        )


def _save_and_ok(
    body: SubmitRequest, config: Config, saver: ResultSaver, rows: list[dict]
) -> dict:
    """Validate form answers, persist one session's rows, and return ok.

    The shared tail of every _submit_* handler - rows are the already
    validated, storage-shaped dicts built by the type-specific validator.
    The metadata and survey forms share one validator (same field schema,
    different collection timing).
    """
    metadata = _validate_metadata(config.metadata.fields, body.metadata)
    survey = _validate_metadata(config.survey.fields, body.survey)
    saver.save(
        session_id=body.session_id,
        test_type=config.test_type,
        records=rows,
        metadata=metadata,
        survey=survey,
    )
    return {"status": "ok", "session_id": body.session_id}


def _validate_pair(
    id_to_meta: dict[str, dict[str, str]], stimulus_ids: list[str], type_label: str
) -> tuple[dict[str, str], dict[str, str]]:
    """Validate a submitted stimulus_ids pair.

    Exactly 2 known ids, same item, different system.
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
    if meta1["item"] != meta2["item"] or meta1["system"] == meta2["system"]:
        raise HTTPException(
            status_code=400,
            detail=f"stimulus_ids do not form a valid {type_label} trial "
            f"pair: {stimulus_ids}",
        )
    return meta1, meta2


def _build_response_trials(
    config: CMOSConfig | ABConfig | ABXConfig, all_stimuli: list[StimulusConfig]
) -> list[ABTrial]:
    """Pair and sample the trial list shared by CMOS's, AB's, and ABX's /api/config."""
    trials = build_ab_trials(all_stimuli)

    # Per-session sampling (trial = one item's pair of stimuli)
    n = config.stimuli_dirs.items_per_session if config.stimuli_dirs else None
    if n is not None:
        trials = _sample_keep_order(trials, n)
    if config.shuffle_order:
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
    all_stimuli = _all_stimuli(config)
    id_to_label = {s.id: s.label for s in all_stimuli}
    trials = _pair_trials_to_response(
        _build_response_trials(config, all_stimuli), id_to_label
    )
    extras = _practice_extras(
        config,
        build_ab_trials(all_stimuli),
        lambda ts: _pair_trials_to_response(ts, id_to_label),
    )
    return _test_config_response(config, trials=trials, **type_extras, **extras)
