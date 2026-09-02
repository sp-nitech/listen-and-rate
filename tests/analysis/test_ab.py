"""Tests for the AB report (also covers XAB, which reuses the AB generator)."""

from __future__ import annotations

import re

from ._helpers import (
    AB_CSV_ROWS,
    AB_ROWS,
    XAB_CSV_ROWS,
    XAB_ROWS,
    _plotly_call_args,
    _with_session_meta,
    _write_csv,
    _write_json,
    generate_report_html,
)

# -- AB ---------------------------------------------------------------------


def test_generate_ab_report_returns_html(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)])
    assert "<html>" in html


def test_generate_ab_report_shows_preference_rate_and_ci(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)])
    assert "95% confidence intervals" in html


def test_generate_ab_report_annotation_shows_the_ci_as_an_interval(tmp_path):
    # The binomial CI is asymmetric, so the annotation prints its bounds
    # rather than MOS/CMOS's "value +/- CI" - a single half-width would have
    # to pick a side, and the error whisker draws both.
    html = generate_report_html([_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)])
    _, layout = _plotly_call_args(html)
    texts = [a["text"] for a in layout["annotations"]]
    # Hair spaces (U+200A) flank the range dash: at the chart's 13px the
    # percent signs otherwise touch it, while a wider space would read as
    # two separate values rather than one interval.
    pattern = r"A: \d+% \[\d+%\u200a\u2013\u200a\d+%\]"
    assert any(re.search(pattern, t) for t in texts)


def test_generate_ab_report_annotation_omits_the_mirror_rate(tmp_path):
    """The other side is 1 - this one, so naming it only repeats a number."""
    html = generate_report_html([_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)])
    _, layout = _plotly_call_args(html)
    texts = [a["text"] for a in layout["annotations"]]
    assert any(t.startswith("A: ") for t in texts)
    assert not any("B: " in t for t in texts)


def test_generate_ab_report_error_bars_are_asymmetric(tmp_path):
    """Both bounds reach plotly, so no whisker is drawn past the true CI."""
    html = generate_report_html([_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)])
    data, _ = _plotly_call_args(html)
    err = data[0]["error_x"]
    assert err["symmetric"] is False
    assert err["arrayminus"] is not None


def test_generate_ab_report_counts_ties_separately(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)])
    assert "No preference" in html  # the default tie label


def test_generate_ab_report_includes_binomial_pvalue(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)])
    assert "A vs B" in html


def test_generate_ab_report_json_input(tmp_path):
    p1 = _write_json(tmp_path / "s1.json", "s1", "ab", AB_ROWS)
    html = generate_report_html([p1])
    assert "<html>" in html
    assert "A vs B" in html


def test_generate_ab_report_shows_summary_stats(tmp_path):
    csv_path = _write_csv(tmp_path / "s1.csv", AB_CSV_ROWS)
    json_path = _write_json(tmp_path / "s2.json", "s2", "ab", AB_ROWS)
    html = generate_report_html([csv_path, json_path])
    assert ">2<" in html  # 2 participants (s1, s2)
    assert ">8<" in html  # 8 choices collected (4 rows each)


def test_generate_ab_report_preference_chart_has_one_bar_per_pair(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)])
    traces, _ = _plotly_call_args(html)
    # One pair (A vs B) → exactly one bar (not two separate A/B bars).
    assert traces[0]["y"] == ["A vs B"]


def test_generate_ab_report_preference_bar_is_horizontal(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)])
    traces, _ = _plotly_call_args(html)
    assert traces[0]["orientation"] == "h"
    assert isinstance(traces[0]["x"][0], float)  # the rate value, not the pair label


def test_generate_ab_report_counts_chart_is_vertical_with_tie_centered(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)])
    traces, _ = _plotly_call_args(html, occurrence=1)
    assert traces[0].get("orientation") != "h"
    assert traces[0]["x"] == ["A", "No preference", "B"]


def test_generate_ab_report_custom_tie_label(tmp_path):
    # The centered tie bar's name is configurable (report-config tie_label);
    # position stays centered between the two systems.
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)], tie_label="Equal"
    )
    traces, _ = _plotly_call_args(html, occurrence=1)
    assert traces[0]["x"] == ["A", "Equal", "B"]


def test_generate_ab_report_tie_label_matches_system_name_formatting(tmp_path):
    # The tie bar sits on the same category axis as the system names, so it
    # must be HTML-escaped and (when enabled) bolded the same way they are -
    # otherwise the two system bars would render escaped/bold while the tie
    # bar renders raw beside them.
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)],
        tie_label="A & B tie",
        bold_system_names=True,
    )
    traces, _ = _plotly_call_args(html, occurrence=1)
    assert traces[0]["x"] == ["<b>A</b>", "<b>A &amp; B tie</b>", "<b>B</b>"]


def test_generate_ab_report_tie_label_is_not_renamed_by_system_labels(tmp_path):
    # tie_label and system_labels are unrelated config knobs. A tie_label that
    # happens to collide with a raw system name in system_labels must still
    # render as the configured tie label, not silently swapped for that
    # system's rename.
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)],
        tie_label="A",
        system_labels={"A": "Renamed"},
    )
    traces, _ = _plotly_call_args(html, occurrence=1)
    assert traces[0]["x"] == ["Renamed", "A", "B"]


def test_generate_ab_report_positional_tokens_are_name_agnostic(tmp_path):
    # winner is a positional token (A/B/=), never a system name, so systems
    # named "tie"/"=" - which used to collide with the old "tie" sentinel -
    # are counted correctly from the token alone.
    rows = _with_session_meta(
        "ab",
        [
            {"system_a": "=", "system_b": "tie", "item": "u1", "winner": "a"},
            {"system_a": "=", "system_b": "tie", "item": "u2", "winner": "a"},
            {"system_a": "=", "system_b": "tie", "item": "u3", "winner": "b"},
            {"system_a": "=", "system_b": "tie", "item": "u4", "winner": "="},
        ],
    )
    html = generate_report_html([_write_csv(tmp_path / "s.csv", rows)])
    traces, _ = _plotly_call_args(html, occurrence=1)
    # counts chart: [system_a, tie_label, system_b] with the token-derived
    # counts (system_a "=" won 2, tie 1, system_b "tie" won 1).
    assert traces[0]["x"] == ["=", "No preference", "tie"]
    assert traces[0]["y"] == [2, 1, 1]


def test_generate_ab_report_rate_follows_positional_token_under_swap(tmp_path):
    # system_order swaps the display sides (stored Mid,Zebra shown as
    # Zebra,Mid); the rate must still follow the positional token - Mid (the
    # stored system_a, winner="A") won both, so displayed Zebra's rate is 0.
    rows = _with_session_meta(
        "ab",
        [
            {"system_a": "Mid", "system_b": "Zebra", "item": "u1", "winner": "a"},
            {"system_a": "Mid", "system_b": "Zebra", "item": "u2", "winner": "a"},
        ],
    )
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", rows)], system_order=["Zebra", "Mid"]
    )
    traces, _ = _plotly_call_args(html)
    assert traces[0]["y"] == ["Zebra vs Mid"]
    assert traces[0]["x"][0] == 0.0  # Zebra won 0 of 2


def test_generate_ab_report_title_is_centered_heading(tmp_path):
    # AB report has no per-chart title (removed to avoid clutter); the overall
    # experiment title is a centered <h1> above the charts instead.
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)], title="My AB Experiment"
    )
    assert "text-align:center" in html
    assert ">My AB Experiment</h1>" in html


def test_generate_ab_report_custom_font(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)],
        font_family="Georgia",
        font_size=20,
    )
    _, layout = _plotly_call_args(html)
    # The report-config font styles the CHART only...
    assert layout["font"]["family"] == "Georgia"
    assert layout["font"]["size"] == 20
    # ...not the HTML page chrome, which keeps its fixed font.
    assert "font-family:Georgia" not in html
    assert "font-family:sans-serif" in html


def test_generate_ab_report_custom_width(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)], width=600
    )
    assert "max-width:600px" in html


def test_generate_ab_report_orders_pairs_by_system_order(tmp_path):
    rows = [
        {
            "session_id": "s1",
            "timestamp": "t",
            "test_type": "ab",
            "item": "u1",
            "system_a": "Alpha",
            "system_b": "Zebra",
            "winner": "a",  # Alpha (system_a) won
        },
    ]
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", rows)], system_order=["Zebra", "Alpha"]
    )
    assert "Zebra vs Alpha" in html


def test_generate_ab_report_orders_multiple_pairs_by_system_order(tmp_path):
    """With 3+ systems (multiple distinct pairs combined in one report), the
    pairs themselves - not just each pair's internal A/B order - must be
    listed in system_order, not in the data's appearance order."""
    rows = [
        {
            "session_id": "s1",
            "timestamp": "t",
            "test_type": "ab",
            "item": "u1",
            "system_a": "Mid",
            "system_b": "Zebra",
            "winner": "a",  # Mid (system_a) won
        },
        {
            "session_id": "s1",
            "timestamp": "t",
            "test_type": "ab",
            "item": "u2",
            "system_a": "Alpha",
            "system_b": "Zebra",
            "winner": "a",  # Alpha (system_a) won
        },
        {
            "session_id": "s1",
            "timestamp": "t",
            "test_type": "ab",
            "item": "u3",
            "system_a": "Alpha",
            "system_b": "Mid",
            "winner": "a",  # Alpha (system_a) won
        },
    ]
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", rows)], system_order=["Zebra", "Alpha", "Mid"]
    )
    traces, _ = _plotly_call_args(html)
    assert traces[0]["y"] == ["Zebra vs Alpha", "Zebra vs Mid", "Alpha vs Mid"]


# -- XAB (reuses the AB generator) ------------------------------------------


def test_generate_xab_report_returns_html(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", XAB_CSV_ROWS)])
    assert "<html>" in html


def test_generate_xab_report_shows_closer_rate_and_ci(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", XAB_CSV_ROWS)])
    assert "Closer-to-reference rate" in html
    assert "95% confidence intervals" in html


def test_generate_xab_report_has_no_tie_category(tmp_path):
    """XAB is forced-choice, so the counts chart must not show a Tie bar."""
    html = generate_report_html([_write_csv(tmp_path / "s.csv", XAB_CSV_ROWS)])
    # The counts chart is the second Plotly.newPlot call (after the rate
    # chart).
    traces, _ = _plotly_call_args(html, occurrence=1)
    assert traces[0]["x"] == ["A", "B"]
    assert traces[0]["y"] == [3, 1]


def test_generate_xab_report_includes_binomial_pvalue(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", XAB_CSV_ROWS)])
    assert "A vs B" in html
    assert "p-value (binomial test)" in html


def test_generate_xab_report_json_input(tmp_path):
    p1 = _write_json(tmp_path / "s1.json", "s1", "xab", XAB_ROWS)
    html = generate_report_html([p1])
    assert "<html>" in html
    assert "A vs B" in html


def test_generate_xab_report_shows_summary_stats(tmp_path):
    csv_path = _write_csv(tmp_path / "s1.csv", XAB_CSV_ROWS)
    json_path = _write_json(tmp_path / "s2.json", "s2", "xab", XAB_ROWS)
    html = generate_report_html([csv_path, json_path])
    assert ">2<" in html  # 2 participants (s1, s2)
    assert ">8<" in html  # 8 choices collected (4 rows each)
