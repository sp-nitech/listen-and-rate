"""Tests for the ABX report."""

from __future__ import annotations

from ._helpers import (
    ABX_CSV_ROWS,
    ABX_ROWS,
    _plotly_call_args,
    _write_csv,
    _write_json,
    generate_report_html,
)


def test_generate_abx_report_returns_html(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", ABX_CSV_ROWS)])
    assert "<html>" in html


def test_generate_abx_report_shows_accuracy_and_ci(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", ABX_CSV_ROWS)])
    assert "95% confidence intervals" in html


def test_generate_abx_report_includes_binomial_pvalue(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", ABX_CSV_ROWS)])
    assert "A vs B" in html


def test_generate_abx_report_json_input(tmp_path):
    p1 = _write_json(tmp_path / "s1.json", "s1", "abx", ABX_ROWS)
    html = generate_report_html([p1])
    assert "<html>" in html
    assert "A vs B" in html


def test_generate_abx_report_shows_summary_stats(tmp_path):
    csv_path = _write_csv(tmp_path / "s1.csv", ABX_CSV_ROWS)
    json_path = _write_json(tmp_path / "s2.json", "s2", "abx", ABX_ROWS)
    html = generate_report_html([csv_path, json_path])
    assert ">2<" in html  # 2 participants (s1, s2)
    assert ">8<" in html  # 8 guesses collected (4 rows each)


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
            "utterance": "u1",
            "system_a": "Alpha",
            "system_b": "Zebra",
            "correct": True,
        },
    ]
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", rows)], system_order=["Zebra", "Alpha"]
    )
    assert "Zebra vs Alpha" in html
