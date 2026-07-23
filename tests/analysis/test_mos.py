"""Tests for the MOS-family report (MOS/DMOS/MUSHRA)."""

from __future__ import annotations

from ._helpers import (
    CSV_ROWS,
    DMOS_CSV_ROWS,
    MUSHRA_CSV_ROWS,
    THREE_SYSTEM_CSV_ROWS,
    _mos_rows,
    _plotly_call_args,
    _with_session_meta,
    _write_csv,
    generate_report_html,
)

# -- MOS --------------------------------------------------------------------


def test_generate_mos_report_shows_summary_stats(tmp_path):
    from ._helpers import RATINGS_A_B, _write_json

    csv_path = _write_csv(tmp_path / "s1.csv", CSV_ROWS)
    json_path = _write_json(tmp_path / "s2.json", "s2", "mos", RATINGS_A_B)
    html = generate_report_html([csv_path, json_path])
    assert ">2<" in html  # 2 participants (s1, s2)
    assert ">8<" in html  # 8 ratings collected (4 rows each)


def test_generate_mos_report_zero_variance_system_has_no_nan(tmp_path):
    """A system whose ratings are all identical has zero variance, which made
    scipy's t.interval() return NaN before this was guarded against."""
    rows = _mos_rows(
        [
            ("s1", "A", "u1", 5),
            ("s2", "A", "u1", 5),
            ("s1", "B", "u1", 3),
            ("s2", "B", "u1", 4),
        ]
    )
    html = generate_report_html([_write_csv(tmp_path / "s.csv", rows)])
    # The value±CI annotation text (e.g. "5.00±0.00") must not contain NaN;
    # Plotly's to_html() JSON-encodes "±" as the ± escape sequence, and
    # plain "nan" alone also matches unrelated minified JS in the embedded
    # Plotly bundle, so check both forms of the specific "±..." pattern this
    # annotation produces.
    lowered = html.lower()
    assert "±nan" not in lowered
    assert "u00b1nan" not in lowered


def test_generate_mos_report_both_systems_zero_variance_pvalue_is_na(tmp_path):
    """Two systems with the exact same identical ratings (zero variance and
    zero difference - a true 0/0 case) make scipy's ttest_ind() return a NaN
    p-value - must show "N/A" like the too-few-samples case does, not a bare
    "nan" or a misleading blank significance marker (nan < 0.05 is False,
    which would read as "not significant" instead of "indeterminate")."""
    rows = _mos_rows(
        [
            ("s1", "A", "u1", 5),
            ("s2", "A", "u1", 5),
            ("s1", "B", "u1", 5),
            ("s2", "B", "u1", 5),
        ]
    )
    html = generate_report_html([_write_csv(tmp_path / "s.csv", rows)])
    assert "N/A" in html
    # ">nan<" would only appear as a table cell's own content (e.g.
    # "<td ...>nan</td>"), unlike a bare "nan" substring match which also
    # hits unrelated minified JS in the embedded Plotly bundle.
    assert ">nan<" not in html.lower()


def test_generate_mos_report_handles_empty_system_values(tmp_path):
    """Explicit stimuli without system: fields store rows with an empty
    system column; pandas reads those as NaN, and groupby would silently
    drop every row - crashing the axis-range code on an empty sequence."""
    rows = _with_session_meta(
        "mos",
        [
            {"system": "", "utterance": "u1", "rating": 4},
            {"system": "", "utterance": "u2", "rating": 3},
        ],
    )
    html = generate_report_html([_write_csv(tmp_path / "s.csv", rows)])
    assert "<html>" in html


def test_generate_mos_report_zooms_yaxis_for_close_scores(tmp_path):
    """When all systems' MOS values cluster tightly, the y-axis should zoom
    in around that cluster (snapped to 0.5 increments, with a minimum span
    so trivial differences aren't visually exaggerated) instead of always
    showing the full 0.5-5.5 scale, so differences remain visible. Tick
    spacing within that range is left to Plotly (no fixed dtick)."""
    rows = _mos_rows(
        [
            ("s1", "A", "u1", 4),
            ("s2", "A", "u1", 4),
            ("s1", "B", "u1", 4),
            ("s2", "B", "u1", 4),
        ]
    )
    html = generate_report_html([_write_csv(tmp_path / "s.csv", rows)])
    _, layout = _plotly_call_args(html)
    lo, hi = layout["yaxis"]["range"]
    assert hi - lo < 5.0  # narrower than the old fixed [0.5, 5.5] span
    assert (lo * 2) == int(lo * 2)  # snapped to a 0.5 multiple
    assert (hi * 2) == int(hi * 2)
    assert "dtick" not in layout["yaxis"]  # ticks are auto, not fixed


def test_generate_mushra_report_labels_yaxis_as_score(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "m.csv", MUSHRA_CSV_ROWS)])
    _, layout = _plotly_call_args(html)
    assert layout["yaxis"]["title"]["text"] == "MUSHRA score"


def _annotation_decimals(html):
    """Digits after the decimal point in each bar's "mean±CI" annotation."""
    _, layout = _plotly_call_args(html)
    texts = [a["text"] for a in layout.get("annotations", [])]
    assert texts, "expected per-bar value annotations"
    return [(len(part.split(".")[1]) for part in t.split("±")) for t in texts]


def test_generate_mushra_report_bar_annotation_one_decimal(tmp_path):
    # 0-100 scale: "62.3±5.1" - 2 decimals would be spurious precision.
    html = generate_report_html([_write_csv(tmp_path / "m.csv", MUSHRA_CSV_ROWS)])
    for mean_dec, err_dec in _annotation_decimals(html):
        assert mean_dec == 1 and err_dec == 1


def test_generate_mos_report_bar_annotation_two_decimals(tmp_path):
    # 1-5 scale keeps 2 decimals (e.g. "3.82±0.14").
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CSV_ROWS)])
    for mean_dec, err_dec in _annotation_decimals(html):
        assert mean_dec == 2 and err_dec == 2


def test_generate_mushra_report_mean_axis_ticks_are_integers(tmp_path):
    # The 0-100 integer scale uses no forced 1-decimal format, so ticks read
    # "60" not "60.0" (MOS/DMOS keep ".1f" for their fractional 1-5 scale).
    html = generate_report_html([_write_csv(tmp_path / "m.csv", MUSHRA_CSV_ROWS)])
    _, layout = _plotly_call_args(html)
    assert "tickformat" not in layout["yaxis"]


def test_generate_mos_report_yaxis_never_goes_below_zero(tmp_path):
    """A wide confidence interval (e.g. from a small, high-variance sample)
    must not push the zoomed y-axis's lower bound below 0 - a MOS/DMOS/MUSHRA
    rating can never be negative, so the axis shouldn't imply otherwise."""
    rows = _mos_rows(
        [
            # Only 2 samples with maximally spread ratings (1 and 5) gives a
            # very wide t-distribution CI (df=1), pushing mean-err well below 0
            # before the fix.
            ("s1", "A", "u1", 1),
            ("s2", "A", "u1", 5),
        ]
    )
    html = generate_report_html([_write_csv(tmp_path / "s.csv", rows)])
    _, layout = _plotly_call_args(html)
    lo, _hi = layout["yaxis"]["range"]
    assert lo >= 0.0


def test_generate_mos_report_uses_full_range_for_spread_out_scores(tmp_path):
    """Systems spanning most of the 1-5 scale should still show a wide range."""
    rows = _mos_rows(
        [
            ("s1", "A", "u1", 1),
            ("s2", "A", "u1", 1),
            ("s1", "B", "u1", 5),
            ("s2", "B", "u1", 5),
        ]
    )
    html = generate_report_html([_write_csv(tmp_path / "s.csv", rows)])
    _, layout = _plotly_call_args(html)
    lo, hi = layout["yaxis"]["range"]
    assert lo <= 1.0
    assert hi >= 5.0


def test_generate_mos_report_yaxis_still_says_mos(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CSV_ROWS)])
    _, layout = _plotly_call_args(html)
    assert layout["yaxis"]["title"]["text"] == "MOS"


# -- DMOS -------------------------------------------------------------------


def test_generate_dmos_report_returns_html(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", DMOS_CSV_ROWS)])
    assert "<html>" in html


def test_generate_dmos_report_yaxis_says_dmos(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", DMOS_CSV_ROWS)])
    _, layout = _plotly_call_args(html)
    assert layout["yaxis"]["title"]["text"] == "DMOS"


# -- MUSHRA -----------------------------------------------------------------


def test_generate_mushra_report_returns_html(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", MUSHRA_CSV_ROWS)])
    assert "<html>" in html


def test_generate_mushra_report_boxplot_range_is_0_100(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", MUSHRA_CSV_ROWS)])
    _, layout = _plotly_call_args(html, occurrence=1)
    assert layout["yaxis"]["range"] == [0, 100]
    assert layout["yaxis"]["dtick"] == 20  # matches the slider's 20-step labels
    # 0-100 integer scale: the Rating axis reads "10" not "10.0" too.
    assert "tickformat" not in layout["yaxis"]


# -- significance -----------------------------------------------------------


def test_generate_mos_report_includes_pairwise_pvalue_table(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", THREE_SYSTEM_CSV_ROWS)])
    for pair in ("A vs B", "A vs C", "B vs C"):
        assert pair in html


def test_generate_mos_report_two_systems_single_pairwise_row(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CSV_ROWS)])
    assert html.count(" vs ") == 1
    assert "A vs B" in html


# -- chart title / font / width ---------------------------------------------


def test_generate_mos_report_title_is_centered_heading(tmp_path):
    # MOS report has no per-chart title (removed to avoid clutter); the overall
    # experiment title is a centered <h1> above the charts instead.
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", CSV_ROWS)], title="My MOS Experiment"
    )
    assert "text-align:center" in html
    assert ">My MOS Experiment</h1>" in html


def test_generate_mos_report_custom_font(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", CSV_ROWS)], font_family="Georgia", font_size=20
    )
    _, layout = _plotly_call_args(html)
    assert layout["font"]["family"] == "Georgia"
    assert layout["font"]["size"] == 20


def test_generate_mos_report_custom_width(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CSV_ROWS)], width=600)
    assert "max-width:600px" in html


# -- system_order -----------------------------------------------------------


def test_generate_mos_report_uses_given_system_order(tmp_path):
    """Systems should appear in the given system_order, not alphabetically."""
    rows = _mos_rows([("s1", "Zebra", "u1", 4), ("s1", "Alpha", "u1", 3)])
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", rows)], system_order=["Zebra", "Alpha"]
    )
    traces, _ = _plotly_call_args(html)
    assert traces[0]["x"] == ["Zebra", "Alpha"]


def test_generate_mos_report_defaults_to_alphabetical_without_system_order(tmp_path):
    rows = _mos_rows([("s1", "Zebra", "u1", 4), ("s1", "Alpha", "u1", 3)])
    html = generate_report_html([_write_csv(tmp_path / "s.csv", rows)])
    traces, _ = _plotly_call_args(html)
    assert traces[0]["x"] == ["Alpha", "Zebra"]


def test_generate_mos_report_system_order_ignores_unknown_systems(tmp_path):
    """A system_order that omits a system present in the data must not crash -
    that system falls back to appearing after the ordered ones, alphabetically."""
    rows = _mos_rows(
        [("s1", "Zebra", "u1", 4), ("s1", "Alpha", "u1", 3), ("s1", "Mid", "u1", 2)]
    )
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", rows)], system_order=["Zebra"]
    )
    traces, _ = _plotly_call_args(html)
    assert traces[0]["x"] == ["Zebra", "Alpha", "Mid"]
