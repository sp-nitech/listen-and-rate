"""Shared fixtures, builders, and row constants for the analysis report tests.

Importing this module runs the optional-dependency guard, so every analysis
test module is skipped as a group when plotly/pandas/scipy aren't installed.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

pytest.importorskip("plotly")
pytest.importorskip("pandas")
pytest.importorskip("scipy")

from listen_and_rate.analysis import generate_report_html  # noqa: E402

__all__ = [
    "ABX_CSV_ROWS",
    "ABX_ROWS",
    "AB_CSV_ROWS",
    "AB_ROWS",
    "CMOS_CSV_ROWS",
    "CMOS_ROWS",
    "CSV_ROWS",
    "DMOS_CSV_ROWS",
    "MUSHRA_CSV_ROWS",
    "MUSHRA_ROWS",
    "RATINGS_A_B",
    "THREE_SYSTEM_CSV_ROWS",
    "THREE_SYSTEM_RATINGS",
    "XAB_CSV_ROWS",
    "XAB_ROWS",
    "_mos_rows",
    "_plotly_call_args",
    "_plotly_config",
    "_with_session_meta",
    "_write_csv",
    "_write_json",
    "generate_report_html",
]


def _write_csv(path: Path, rows: list[dict]) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return path


def _plotly_call_args(html: str, occurrence: int = 0) -> tuple[list, dict]:
    """Extract the (traces, layout) args of the Nth Plotly.newPlot(...) call.

    Uses JSONDecoder.raw_decode (not a greedy regex) so brace/bracket nesting
    inside the trace/layout objects themselves doesn't break the split.
    """
    matches = list(re.finditer(r'Plotly\.newPlot\(\s*"[^"]+",\s*', html, re.DOTALL))
    assert len(matches) > occurrence, (
        f"could not find Plotly.newPlot(...) call #{occurrence} in HTML"
    )
    m = matches[occurrence]
    decoder = json.JSONDecoder()
    traces, idx = decoder.raw_decode(html, m.end())
    comma = re.match(r"\s*,\s*", html[idx:])
    assert comma, "could not find layout argument after traces"
    layout, _ = decoder.raw_decode(html, idx + comma.end())
    return traces, layout


def _plotly_config(html: str, occurrence: int = 0) -> dict:
    """Extract the config arg (4th) of the Nth Plotly.newPlot(...) call.

    Companion to _plotly_call_args: the config object carries modebar and
    export options (e.g. toImageButtonOptions) rather than data or layout.
    """
    matches = list(re.finditer(r'Plotly\.newPlot\(\s*"[^"]+",\s*', html, re.DOTALL))
    assert len(matches) > occurrence, (
        f"could not find Plotly.newPlot(...) call #{occurrence} in HTML"
    )
    decoder = json.JSONDecoder()
    idx = matches[occurrence].end()
    value: dict = {}
    for arg in ("traces", "layout", "config"):
        value, idx = decoder.raw_decode(html, idx)
        comma = re.match(r"\s*,\s*", html[idx:])
        assert comma or arg == "config", f"could not find argument after {arg}"
        idx += comma.end() if comma else 0
    return value


def _write_json(
    path: Path,
    session_id: str,
    test_type: str,
    ratings: list[dict],
    metadata: dict | None = None,
    survey: dict | None = None,
) -> Path:
    data = {
        "session_id": session_id,
        "timestamp": "2026-01-01T00:00:00",
        "test_type": test_type,
        "metadata": metadata or {},
        "survey": survey or {},
        "ratings": ratings,
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _with_session_meta(
    test_type: str,
    rows: list[dict],
    session_id: str = "s1",
    timestamp: str = "2026-01-01",
) -> list[dict]:
    """Prefix each row with the session_id/timestamp/test_type result columns."""
    return [
        {"session_id": session_id, "timestamp": timestamp, "test_type": test_type, **r}
        for r in rows
    ]


def _mos_rows(
    entries: list[tuple[str, str, str, int]], timestamp: str = "t"
) -> list[dict]:
    """Build MOS CSV rows from (session_id, system, item, rating) tuples."""
    return [
        {
            "session_id": sid,
            "timestamp": timestamp,
            "test_type": "mos",
            "system": system,
            "item": item,
            "rating": rating,
        }
        for sid, system, item, rating in entries
    ]


RATINGS_A_B = [
    {"system": "A", "item": "u1", "rating": 4},
    {"system": "A", "item": "u2", "rating": 5},
    {"system": "B", "item": "u1", "rating": 2},
    {"system": "B", "item": "u2", "rating": 3},
]

CSV_ROWS = _with_session_meta("mos", RATINGS_A_B)

DMOS_CSV_ROWS = _with_session_meta("dmos", RATINGS_A_B)

MUSHRA_ROWS = [
    {"system": "A", "item": "u1", "rating": 80},
    {"system": "A", "item": "u2", "rating": 90},
    {"system": "B", "item": "u1", "rating": 30},
    {"system": "B", "item": "u2", "rating": 40},
]

MUSHRA_CSV_ROWS = _with_session_meta("mushra", MUSHRA_ROWS)

CMOS_ROWS = [
    {"item": "u1", "system_a": "A", "system_b": "B", "rating": 2},
    {"item": "u2", "system_a": "A", "system_b": "B", "rating": 1},
    {"item": "u3", "system_a": "A", "system_b": "B", "rating": -1},
    {"item": "u4", "system_a": "A", "system_b": "B", "rating": 0},
]

CMOS_CSV_ROWS = _with_session_meta("cmos", CMOS_ROWS)

# winner/closer are positional tokens (a = system_a, b = system_b, = tie),
# not system names - see storage.OUTCOME_*. The lowercase a/b mirror the
# system_a/system_b column names and encode the pair SIDE regardless of what
# the systems are actually called.
AB_ROWS = [
    {"system_a": "A", "system_b": "B", "item": "u1", "winner": "a"},
    {"system_a": "A", "system_b": "B", "item": "u2", "winner": "a"},
    {"system_a": "A", "system_b": "B", "item": "u3", "winner": "b"},
    {"system_a": "A", "system_b": "B", "item": "u4", "winner": "="},
]

AB_CSV_ROWS = _with_session_meta("ab", AB_ROWS)

ABX_ROWS = [
    {"system_a": "A", "system_b": "B", "item": "u1", "correct": True},
    {"system_a": "A", "system_b": "B", "item": "u2", "correct": True},
    {"system_a": "A", "system_b": "B", "item": "u3", "correct": False},
    {"system_a": "A", "system_b": "B", "item": "u4", "correct": False},
]

ABX_CSV_ROWS = _with_session_meta("abx", ABX_ROWS)

XAB_ROWS = [
    {"system_a": "A", "system_b": "B", "item": "u1", "closer": "a"},
    {"system_a": "A", "system_b": "B", "item": "u2", "closer": "a"},
    {"system_a": "A", "system_b": "B", "item": "u3", "closer": "a"},
    {"system_a": "A", "system_b": "B", "item": "u4", "closer": "b"},
]

XAB_CSV_ROWS = _with_session_meta("xab", XAB_ROWS)

THREE_SYSTEM_RATINGS = [
    {"system": "A", "item": "u1", "rating": 4},
    {"system": "A", "item": "u2", "rating": 5},
    {"system": "B", "item": "u1", "rating": 2},
    {"system": "B", "item": "u2", "rating": 3},
    {"system": "C", "item": "u1", "rating": 3},
    {"system": "C", "item": "u2", "rating": 4},
]

THREE_SYSTEM_CSV_ROWS = _with_session_meta("mos", THREE_SYSTEM_RATINGS)
