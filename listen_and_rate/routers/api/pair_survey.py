"""pair_survey /api/config and /api/submit handlers."""

from __future__ import annotations

from fastapi import HTTPException

from ...config import (
    DMOSTrial,
    PairSurveyConfig,
    QuestionConfig,
    StimulusConfig,
    build_dmos_trials,
)
from ...models import ChoiceEntry, SubmitRequest
from ...rng import rng
from ...storage import ResultSaver
from ._shared import (
    _all_stimuli,
    _assigned_items,
    _filter_assigned,
    _id_to_meta,
    _metrics_row,
    _practice_extras,
    _require_answered_once,
    _require_non_empty,
    _sample_keep_order,
    _save_and_ok,
    _test_config_response,
    _validate_pair,
)


def _build_pair_survey_response_trials(
    config: PairSurveyConfig,
    all_stimuli: list[StimulusConfig],
    assigned: set[str] | None = None,
) -> list[DMOSTrial]:
    """Pair, filter, and sample the trial list for pair_survey's /api/config.

    Roles are fixed (source = reference system, generated = the other), so
    the pair is never shuffled the way CMOS/AB blinds A/B position.
    """
    trials = _filter_assigned(
        build_dmos_trials(all_stimuli, config.reference_system), assigned
    )

    n = config.stimuli_dirs.items_per_session if config.stimuli_dirs else None
    if n is not None:
        trials = _sample_keep_order(trials, n)
    if config.shuffle_order:
        trials = rng.sample(trials, len(trials))
    return trials


def _pair_survey_trials_to_response(
    trials: list[DMOSTrial], id_to_label: dict[str, str | None]
) -> list[dict]:
    """Map trials to the disclosed {"source", "generated"} response shape."""
    return [
        {
            "source": {
                "id": t.reference_id,
                "label": id_to_label.get(t.reference_id),
            },
            "generated": {
                "id": t.test_id,
                "label": id_to_label.get(t.test_id),
            },
        }
        for t in trials
    ]


def _get_pair_survey_test_config(
    config: PairSurveyConfig, rater: str | None = None
) -> dict:
    all_stimuli = _all_stimuli(config)
    id_to_label = {s.id: s.label for s in all_stimuli}
    assigned = _assigned_items(config, rater)
    trials = _pair_survey_trials_to_response(
        _build_pair_survey_response_trials(config, all_stimuli, assigned),
        id_to_label,
    )
    if not trials:
        raise HTTPException(
            status_code=400,
            detail=f"No trials are assigned to rater {rater!r}",
        )
    extras = _practice_extras(
        config,
        _filter_assigned(
            build_dmos_trials(all_stimuli, config.reference_system), assigned
        ),
        lambda ts: _pair_survey_trials_to_response(ts, id_to_label),
    )
    return _test_config_response(
        config,
        trials=trials,
        questions=[q.browser_dict() for q in config.questions],
        source_label=config.source_label,
        generated_label=config.generated_label,
        **extras,
    )


def _validate_answer(question: QuestionConfig, value: object, where: str) -> str | int:
    """Check one answer against its question, returning it in stored form.

    A scale answer is stored as the integer it names rather than the string
    the browser submits, so analysis can average it without re-parsing.
    """
    if not isinstance(value, str) or value not in question.allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{where}: {value!r} is not a valid answer for question "
                f"{question.key!r}; expected one of {question.allowed}"
            ),
        )
    return int(value) if question.type == "scale" else value


def _collect(
    questions: list[QuestionConfig], submitted: dict[str, str], where: str
) -> dict[str, str | int]:
    """Validate one question group's answers, keyed by question key.

    Every declared question appears in the result, an unanswered optional one
    as the empty string: the CSV saver infers its header from the first row
    (see storage.CSVResultSaver), so a row whose columns depend on what this
    listener chose to skip would either lose answers or fail to write. Keys
    the config never declared are dropped rather than stored, so a crafted
    request cannot add columns of its own.
    """
    collected: dict[str, str | int] = {}
    for question in questions:
        value = submitted.get(question.key)
        if value is None or value == "":
            if question.required:
                raise HTTPException(
                    status_code=400,
                    detail=f"{where}: missing answer for required question "
                    f"{question.key!r}",
                )
            collected[question.key] = ""
            continue
        collected[question.key] = _validate_answer(question, value, where)
    return collected


def _submit_pair_survey(
    body: SubmitRequest, config: PairSurveyConfig, saver: ResultSaver
) -> dict:
    """Validate and persist pair_survey answers.

    400 if empty, a pair is invalid/unknown, the ids are not source-then-
    generated, or any required question is unanswered or outside its range.
    """
    _require_non_empty(body.choices, "choices")
    _require_answered_once(
        ["+".join(c.stimulus_ids) for c in body.choices], "choices", "trial"
    )
    id_to_meta = _id_to_meta(_all_stimuli(config))
    reference_system = config.reference_system

    rows = []
    for choice in body.choices:
        source_meta, generated_meta = _source_generated_meta(
            choice, id_to_meta, reference_system
        )
        where = f"trial {generated_meta['item']!r}"
        rows.append(
            {
                "system": generated_meta["system"],
                "item": generated_meta["item"],
                "reference": source_meta["system"],
                **_collect(config.questions, choice.answers, where),
                **_metrics_row(choice, config),
            }
        )

    # pair_survey writes on every Next as well as Finish, so the same
    # session_id must be allowed to replace the file. Finish still overwrites
    # so the last trial is included and complete flips to true.
    return _save_and_ok(
        body, config, saver, rows, overwrite=True, complete=body.complete
    )


def _source_generated_meta(
    choice: ChoiceEntry,
    id_to_meta: dict[str, dict[str, str]],
    reference_system: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Validate stimulus_ids as [source, generated] for one submitted trial."""
    source_meta, generated_meta = _validate_pair(
        id_to_meta, choice.stimulus_ids, "pair_survey"
    )
    if source_meta["system"] != reference_system:
        raise HTTPException(
            status_code=400,
            detail="stimulus_ids[0] must be the source (reference) system's clip",
        )
    if generated_meta["system"] == reference_system:
        raise HTTPException(
            status_code=400,
            detail="stimulus_ids[1] must be the generated system's clip",
        )
    return source_meta, generated_meta
