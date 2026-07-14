"""Result persistence: per-session CSV/JSON under output_dir/experiment_id/."""

from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path


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
    ) -> None:
        """Persist one session's ratings; called once per POST /api/submit."""
        ...


class CSVResultSaver(ResultSaver):
    """Write each session to its own output_dir/experiment_id/{session_id}.csv file.

    Column layout: session_id, timestamp, test_type, [metadata keys...], then
    whatever keys the row dicts themselves carry (e.g. system/utterance/rating
    for MOS, utterance/system_a/system_b/winner for AB) - the tail columns are
    inferred from the first row rather than hardcoded, so this saver works for
    any test type's row shape. Metadata columns are inserted in the order
    given by metadata_keys.
    """

    _BASE_FIELDS = ["session_id", "timestamp", "test_type"]

    def __init__(
        self,
        output_dir: Path,
        experiment_id: str,
        metadata_keys: list[str] | None = None,
    ) -> None:
        self._dir = output_dir / experiment_id
        self._metadata_keys = list(metadata_keys or [])

    def save(
        self,
        session_id: str,
        test_type: str,
        ratings: list[dict],
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Write one row per rating to {experiment_id}/{session_id}.csv."""
        path = self._dir / f"{session_id}.csv"
        ts = datetime.now().astimezone().isoformat(timespec="seconds")
        meta = metadata or {}
        row_fields = list(ratings[0].keys()) if ratings else []
        fields = self._BASE_FIELDS + self._metadata_keys + row_fields
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
                        **{k: meta.get(k, "") for k in self._metadata_keys},
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
    ) -> None:
        """Write this session's ratings to {experiment_id}/{session_id}.json."""
        self._dir.mkdir(parents=True, exist_ok=True)
        data = {
            "session_id": session_id,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "test_type": test_type,
            "metadata": metadata or {},
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
) -> ResultSaver:
    """Instantiate the appropriate ResultSaver for the given format string."""
    p = Path(output_dir)
    if fmt == "csv":
        return CSVResultSaver(p, experiment_id, metadata_keys)
    if fmt == "json":
        return JSONResultSaver(p, experiment_id)
    raise ValueError(f"Unknown output format: {fmt!r}")
