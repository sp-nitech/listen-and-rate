"""Tests for the CMOS report."""

from __future__ import annotations

from ._helpers import (
    CMOS_CSV_ROWS,
    CMOS_ROWS,
    _plotly_call_args,
    _write_csv,
    _write_json,
    generate_report_html,
)


def test_generate_cmos_report_returns_html(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CMOS_CSV_ROWS)])
    assert "<html>" in html


def test_generate_cmos_report_hover_thin_spaces_around_plus_minus(tmp_path):
    # The "mean±CI" hover reads "0.75 ± 1.16" with thin spaces (U+2009),
    # matching the MOS annotations' binary-operator spacing.
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CMOS_CSV_ROWS)])
    traces, _ = _plotly_call_args(html)
    assert "\u2009±\u2009" in traces[0]["hovertext"][0]


def test_generate_cmos_report_shows_ci_and_pair_label(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CMOS_CSV_ROWS)])
    assert "95% confidence intervals" in html
    assert "A vs B" in html


def test_generate_cmos_report_ci_bar_is_horizontal(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CMOS_CSV_ROWS)])
    traces, _ = _plotly_call_args(html)
    assert traces[0]["orientation"] == "h"
    assert traces[0]["y"] == ["A vs B"]


def test_generate_cmos_report_ci_axis_range_is_symmetric(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CMOS_CSV_ROWS)])
    _, layout = _plotly_call_args(html)
    assert layout["xaxis"]["range"] == [-3, 3]


def test_generate_cmos_report_category_chart_has_seven_bars(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CMOS_CSV_ROWS)])
    traces, _ = _plotly_call_args(html, occurrence=1)
    assert len(traces[0]["x"]) == 7
    assert sum(traces[0]["y"]) == len(CMOS_ROWS)


def test_generate_cmos_report_includes_ttest_pvalue(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CMOS_CSV_ROWS)])
    assert "p-value (t-test" in html


def test_generate_cmos_report_json_input(tmp_path):
    p1 = _write_json(tmp_path / "s1.json", "s1", "cmos", CMOS_ROWS)
    html = generate_report_html([p1])
    assert "<html>" in html
    assert "A vs B" in html


def test_generate_cmos_report_shows_summary_stats(tmp_path):
    csv_path = _write_csv(tmp_path / "s1.csv", CMOS_CSV_ROWS)
    json_path = _write_json(tmp_path / "s2.json", "s2", "cmos", CMOS_ROWS)
    html = generate_report_html([csv_path, json_path])
    assert ">2<" in html  # 2 participants (s1, s2)
    assert ">8<" in html  # 8 ratings collected (4 rows each)
    assert ">Significance tests</h3>" in html
    assert ">Data summary</h3>" in html


def test_generate_cmos_report_orders_pairs_by_system_order(tmp_path):
    rows = [
        {
            "session_id": "s1",
            "timestamp": "t",
            "test_type": "cmos",
            "item": "u1",
            "system_a": "Alpha",
            "system_b": "Zebra",
            "rating": 1,
        },
    ]
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", rows)], system_order=["Zebra", "Alpha"]
    )
    assert "Zebra vs Alpha" in html


def test_generate_cmos_report_orders_multiple_pairs_by_system_order(tmp_path):
    rows = [
        {
            "session_id": "s1",
            "timestamp": "t",
            "test_type": "cmos",
            "item": "u1",
            "system_a": "Mid",
            "system_b": "Zebra",
            "rating": 1,
        },
        {
            "session_id": "s1",
            "timestamp": "t",
            "test_type": "cmos",
            "item": "u2",
            "system_a": "Alpha",
            "system_b": "Zebra",
            "rating": 1,
        },
        {
            "session_id": "s1",
            "timestamp": "t",
            "test_type": "cmos",
            "item": "u3",
            "system_a": "Alpha",
            "system_b": "Mid",
            "rating": 1,
        },
    ]
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", rows)], system_order=["Zebra", "Alpha", "Mid"]
    )
    traces, _ = _plotly_call_args(html)
    assert traces[0]["y"] == ["Zebra vs Alpha", "Zebra vs Mid", "Alpha vs Mid"]
