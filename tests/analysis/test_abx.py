"""Tests for the ABX report."""

from __future__ import annotations

import re

from ._helpers import (
    ABX_CSV_ROWS,
    _plotly_call_args,
    _write_csv,
    generate_report_html,
)


def test_generate_abx_report_shows_accuracy_and_ci(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", ABX_CSV_ROWS)])
    assert "95% confidence intervals" in html


def test_generate_abx_report_annotation_shows_the_ci_as_an_interval(tmp_path):
    # The binomial CI is asymmetric, so the annotation prints its bounds
    # rather than a single "+/- CI" half-width, as in AB. Hair spaces
    # (U+200A) flank the range dash.
    html = generate_report_html([_write_csv(tmp_path / "s.csv", ABX_CSV_ROWS)])
    _, layout = _plotly_call_args(html)
    texts = [a["text"] for a in layout["annotations"]]
    pattern = r"Correct: \d+% \[\d+%\u200a\u2013\u200a\d+%\]"
    assert any(re.search(pattern, t) for t in texts)


def test_generate_abx_report_annotation_omits_the_raw_counts(tmp_path):
    """The counts chart sits directly below, so the annotation need not repeat it."""
    html = generate_report_html([_write_csv(tmp_path / "s.csv", ABX_CSV_ROWS)])
    _, layout = _plotly_call_args(html)
    texts = [a["text"] for a in layout["annotations"]]
    assert not any(re.search(r"\d+/\d+", t) for t in texts)


def test_generate_abx_report_includes_binomial_pvalue(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", ABX_CSV_ROWS)])
    assert "A vs B" in html


def test_generate_abx_report_counts_chart_is_vertical(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", ABX_CSV_ROWS)])
    traces, _ = _plotly_call_args(html, occurrence=1)
    assert traces[0].get("orientation") != "h"
    assert traces[0]["x"] == ["Correct", "Incorrect"]


def test_generate_abx_report_orders_pairs_by_system_order(tmp_path):
    rows = [
        {
            "session_id": "s1",
            "timestamp": "t",
            "test_type": "abx",
            "item": "u1",
            "system_a": "Alpha",
            "system_b": "Zebra",
            "correct": True,
        },
    ]
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", rows)], system_order=["Zebra", "Alpha"]
    )
    assert "Zebra vs Alpha" in html
