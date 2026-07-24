"""Result persistence: per-session CSV/JSON under output_dir/experiment_id/."""

from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

# Column-name prefixes namespacing per-session form answers in CSV results.
# The prefix makes a form key structurally unable to collide with the
# saver-written result columns (a metadata field literally named 'system'
# lands in metadata_system), keeps metadata and survey answers
# distinguishable in the flat CSV, and is what analysis/report.py's
# metadata_filter/survey_filter validation keys on. JSON results don't need
# them (metadata/survey are separate nested objects there); the analysis
# reader flattens JSON into the same prefixed columns. Mirrored by
# frontend/save.php for the PHP deployment.
METADATA_COLUMN_PREFIX = "metadata_"
SURVEY_COLUMN_PREFIX = "survey_"

# AB/XAB outcome tokens: the winner/closer column records which SIDE of the
# stored pair was chosen (system_a / system_b), or a tie, as a fixed
# positional token rather than a system name. Keeping names out of the
# outcome column means any system name - "tie", "A", "=" included - is
# collision-free, since the identities live only in the system_a/system_b
# columns. Mirrored by frontend/save.php for the PHP deployment.
OUTCOME_A = "A"
OUTCOME_B = "B"
OUTCOME_TIE = "="


class ResultExistsError(Exception):
    """Raised when a result file for the session already exists.

    Collected listener data must never be silently overwritten - a duplicate
    session_id (a resubmission, a retry, or a crafted request) is refused
    instead, and the caller decides how to report it (the API maps it to 409).
    """

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Results for session {session_id!r} already exist")
        self.session_id = session_id


class ResultSaver(ABC):
    """Abstract base for result persistence backends."""

    @abstractmethod
    def save(
        self,
        session_id: str,
        test_type: str,
        ratings: list[dict],
        metadata: dict[str, str] | None = None,
        survey: dict[str, str] | None = None,
    ) -> None:
        """Persist one session's ratings; called once per POST /api/submit."""
        ...


class CSVResultSaver(ResultSaver):
    """Write each session to its own output_dir/experiment_id/{session_id}.csv file.

    Column layout: session_id, timestamp, test_type, [metadata_* keys...],
    [survey_* keys...], then whatever keys the row dicts themselves carry
    (e.g. system/utterance/rating for MOS, utterance/system_a/system_b/winner
    for AB) - the tail columns are inferred from the first row rather than
    hardcoded, so this saver works for any test type's row shape. Form
    columns are inserted in the order given by metadata_keys/survey_keys and
    namespaced with METADATA_COLUMN_PREFIX/SURVEY_COLUMN_PREFIX.
    """

    _BASE_FIELDS = ["session_id", "timestamp", "test_type"]

    def __init__(
        self,
        output_dir: Path,
        experiment_id: str,
        metadata_keys: list[str] | None = None,
        survey_keys: list[str] | None = None,
    ) -> None:
        self._dir = output_dir / experiment_id
        self._metadata_keys = list(metadata_keys or [])
        self._survey_keys = list(survey_keys or [])

    def save(
        self,
        session_id: str,
        test_type: str,
        ratings: list[dict],
        metadata: dict[str, str] | None = None,
        survey: dict[str, str] | None = None,
    ) -> None:
        """Write one row per rating to {experiment_id}/{session_id}.csv."""
        path = self._dir / f"{session_id}.csv"
        ts = datetime.now().astimezone().isoformat(timespec="seconds")
        meta = metadata or {}
        answers = survey or {}
        meta_fields = [METADATA_COLUMN_PREFIX + k for k in self._metadata_keys]
        survey_fields = [SURVEY_COLUMN_PREFIX + k for k in self._survey_keys]
        row_fields = list(ratings[0].keys()) if ratings else []
        fields = self._BASE_FIELDS + meta_fields + survey_fields + row_fields
        self._dir.mkdir(parents=True, exist_ok=True)
        try:
            f = open(path, "x", newline="", encoding="utf-8")
        except FileExistsError:
            raise ResultExistsError(session_id) from None
        with f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for r in ratings:
                writer.writerow(
                    {
                        "session_id": session_id,
                        "timestamp": ts,
                        "test_type": test_type,
                        **{
                            METADATA_COLUMN_PREFIX + k: meta.get(k, "")
                            for k in self._metadata_keys
                        },
                        **{
                            SURVEY_COLUMN_PREFIX + k: answers.get(k, "")
                            for k in self._survey_keys
                        },
                        **r,
                    }
                )


class JSONResultSaver(ResultSaver):
    """Write each session to output_dir/experiment_id/{session_id}.json."""

    def __init__(self, output_dir: Path, experiment_id: str) -> None:
        self._dir = output_dir / experiment_id

    def save(
        self,
        session_id: str,
        test_type: str,
        ratings: list[dict],
        metadata: dict[str, str] | None = None,
        survey: dict[str, str] | None = None,
    ) -> None:
        """Write this session's ratings to {experiment_id}/{session_id}.json."""
        self._dir.mkdir(parents=True, exist_ok=True)
        data = {
            "session_id": session_id,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "test_type": test_type,
            "metadata": metadata or {},
            "survey": survey or {},
            "ratings": ratings,
        }
        try:
            f = open(self._dir / f"{session_id}.json", "x", encoding="utf-8")
        except FileExistsError:
            raise ResultExistsError(session_id) from None
        with f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def make_result_saver(
    fmt: str,
    output_dir: str,
    experiment_id: str,
    metadata_keys: list[str] | None = None,
    survey_keys: list[str] | None = None,
) -> ResultSaver:
    """Instantiate the appropriate ResultSaver for the given format string."""
    p = Path(output_dir)
    if fmt == "csv":
        return CSVResultSaver(p, experiment_id, metadata_keys, survey_keys)
    if fmt == "json":
        return JSONResultSaver(p, experiment_id)
    raise ValueError(f"Unknown output format: {fmt!r}")
