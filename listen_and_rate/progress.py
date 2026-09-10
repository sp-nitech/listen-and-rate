"""Aggregate per-rater progress from assignments and saved result files."""

from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from .config.base import RATER_METADATA_KEY

# Keys that describe the trial, not the listener's answers.
_RECORD_META_KEYS = frozenset({"system", "item", "reference", "metrics"})


def collect_progress(config: Config) -> dict:
    """Build the progress payload for GET /api/progress and GET /progress.

    Assigned raters come from the loaded assignments file (order preserved).
    Raters who only appear in result files are appended afterwards.
    """
    results_dir = Path(config.output.path) / config.experiment_id
    sessions = _load_sessions(results_dir)
    assigned = dict(config.rater_items)
    by_rater = _index_sessions(sessions)
    raters: list[dict] = []
    seen: set[str] = set()
    for rater, items in assigned.items():
        raters.append(_rater_row(rater, items, by_rater.get(rater, []), True))
        seen.add(rater)
    extras = sorted(k for k in by_rater if k not in seen)
    for rater in extras:
        rated_items = _latest_items(by_rater[rater])
        raters.append(_rater_row(rater, list(rated_items), by_rater[rater], False))
    return {
        "experiment_id": config.experiment_id,
        "title": config.title,
        "results_dir": str(results_dir),
        "raters": raters,
    }


def _load_sessions(results_dir: Path) -> list[dict]:
    if not results_dir.is_dir():
        return []
    sessions: list[dict] = []
    for path in sorted(results_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(data, dict):
            sessions.append(data)
    return sessions


def _index_sessions(sessions: list[dict]) -> dict[str, list[dict]]:
    by_rater: dict[str, list[dict]] = {}
    for session in sessions:
        metadata = session.get("metadata")
        rater = ""
        if isinstance(metadata, dict):
            value = metadata.get(RATER_METADATA_KEY)
            rater = value if isinstance(value, str) else ""
        by_rater.setdefault(rater, []).append(session)
    return by_rater


def _latest_items(sessions: list[dict]) -> dict[str, dict]:
    """Map each item to its latest answers, session_id, and timestamp."""
    latest: dict[str, dict] = {}
    for session in sessions:
        timestamp = session.get("timestamp") or ""
        session_id = session.get("session_id") or ""
        for record in session.get("records") or []:
            if not isinstance(record, dict):
                continue
            item = record.get("item")
            if not item:
                continue
            prev = latest.get(item)
            if prev is not None and prev["timestamp"] > timestamp:
                continue
            latest[item] = {
                "item": item,
                "status": "done",
                "answers": {
                    k: v for k, v in record.items() if k not in _RECORD_META_KEYS
                },
                "session_id": session_id,
                "timestamp": timestamp,
            }
    return latest


def _rater_row(
    rater: str,
    assigned: list[str],
    sessions: list[dict],
    in_assignments: bool,
) -> dict:
    latest = _latest_items(sessions)
    assigned_set = set(assigned)
    items: list[dict] = []
    for item in assigned:
        if item in latest:
            items.append(latest[item])
        else:
            items.append(
                {
                    "item": item,
                    "status": "pending",
                    "answers": None,
                    "session_id": None,
                    "timestamp": None,
                }
            )
    for item, row in latest.items():
        if item not in assigned_set:
            items.append(row)
    done_assigned = sum(
        1 for it in items if it["item"] in assigned_set and it["status"] == "done"
    )
    assigned_count = len(assigned)
    any_complete = any(_session_complete(s) for s in sessions)
    if assigned_count == 0:
        if any_complete:
            status = "complete"
        elif latest:
            status = "in_progress"
        else:
            status = "not_started"
        awaiting_finish = bool(latest) and not any_complete
    elif done_assigned == 0:
        status = "not_started"
        awaiting_finish = False
    elif done_assigned >= assigned_count:
        status = "complete"
        awaiting_finish = not any_complete
    else:
        status = "in_progress"
        awaiting_finish = False
    timestamps = [s.get("timestamp") or "" for s in sessions if s.get("timestamp")]
    return {
        "rater": rater,
        "in_assignments": in_assignments,
        "assigned": assigned,
        "assigned_count": assigned_count,
        "completed_count": done_assigned if assigned_count else len(latest),
        "status": status,
        "awaiting_finish": awaiting_finish,
        "last_updated": max(timestamps) if timestamps else None,
        "sessions": [s.get("session_id") or "" for s in sessions],
        "items": items,
    }


def _session_complete(session: dict) -> bool:
    """Files written before the complete flag existed were Finish-only."""
    if "complete" not in session:
        return True
    return bool(session["complete"])
