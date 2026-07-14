"""Tests for the report entry point: file reading, dispatch, mixed-type guard, title."""

from __future__ import annotations

import pytest

from ._helpers import (
    AB_CSV_ROWS,
    ABX_CSV_ROWS,
    CMOS_CSV_ROWS,
    CSV_ROWS,
    DMOS_CSV_ROWS,
    MUSHRA_CSV_ROWS,
    RATINGS_A_B,
    THREE_SYSTEM_CSV_ROWS,
    XAB_CSV_ROWS,
    _plotly_call_args,
    _with_session_meta,
    _write_csv,
    _write_json,
    generate_report_html,
)

# -- CSV input --------------------------------------------------------------


def test_generate_report_returns_html(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CSV_ROWS)])
    assert "<html>" in html


def test_generate_report_default_confidence(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CSV_ROWS)])
    assert "95% CI" in html


def test_generate_report_custom_confidence(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", CSV_ROWS)], confidence=0.90
    )
    assert "90% CI" in html
    assert "95% CI" not in html


# -- JSON input -------------------------------------------------------------


def test_generate_report_json_input(tmp_path):
    p1 = _write_json(tmp_path / "s1.json", "s1", "mos", RATINGS_A_B)
    p2 = _write_json(tmp_path / "s2.json", "s2", "mos", RATINGS_A_B)
    html = generate_report_html([p1, p2])
    assert "<html>" in html
    assert "95% CI" in html
    assert '"A"' in html or ">A<" in html


def test_generate_report_mixed_csv_and_json(tmp_path):
    csv_path = _write_csv(tmp_path / "s1.csv", CSV_ROWS)
    json_path = _write_json(tmp_path / "s2.json", "s2", "mos", RATINGS_A_B)
    html = generate_report_html([csv_path, json_path])
    assert "<html>" in html


# -- error cases ------------------------------------------------------------


def test_generate_report_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        generate_report_html([tmp_path / "nonexistent.csv"])


def test_generate_report_no_mos_rows(tmp_path):
    rows = [
        {
            "session_id": "s",
            "timestamp": "t",
            "test_type": "other",
            "system": "A",
            "utterance": "u",
            "rating": 4,
        }
    ]
    with pytest.raises(ValueError, match="No MOS rows"):
        generate_report_html([_write_csv(tmp_path / "s.csv", rows)])


# -- dispatch + mixed-type guard --------------------------------------------


def test_generate_report_dispatches_dmos(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "dmos.csv", DMOS_CSV_ROWS)])
    assert "p-value (t-test)" in html


def test_generate_report_dispatches_mushra(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "mushra.csv", MUSHRA_CSV_ROWS)])
    assert "p-value (t-test)" in html


def test_generate_report_mixed_mushra_and_mos_raises_error(tmp_path):
    mushra_path = _write_csv(tmp_path / "mushra.csv", MUSHRA_CSV_ROWS)
    mos_path = _write_csv(tmp_path / "mos.csv", CSV_ROWS)
    with pytest.raises(ValueError, match="Mixed test_type"):
        generate_report_html([mushra_path, mos_path])


def test_generate_report_dispatches_dmos_cmos_ab(tmp_path):
    dmos_html = generate_report_html([_write_csv(tmp_path / "dmos.csv", DMOS_CSV_ROWS)])
    cmos_html = generate_report_html([_write_csv(tmp_path / "cmos.csv", CMOS_CSV_ROWS)])
    assert "p-value (t-test)" in dmos_html
    assert "p-value (t-test" in cmos_html


def test_generate_report_mixed_dmos_and_cmos_raises_error(tmp_path):
    dmos_path = _write_csv(tmp_path / "dmos.csv", DMOS_CSV_ROWS)
    cmos_path = _write_csv(tmp_path / "cmos.csv", CMOS_CSV_ROWS)
    with pytest.raises(ValueError, match="Mixed test_type"):
        generate_report_html([dmos_path, cmos_path])


def test_generate_report_dispatches_mos_vs_ab(tmp_path):
    mos_html = generate_report_html([_write_csv(tmp_path / "mos.csv", CSV_ROWS)])
    ab_html = generate_report_html([_write_csv(tmp_path / "ab.csv", AB_CSV_ROWS)])
    assert "p-value (t-test)" in mos_html
    assert "p-value (binomial)" in ab_html


def test_generate_report_mixed_test_types_raises_error(tmp_path):
    mos_path = _write_csv(tmp_path / "mos.csv", CSV_ROWS)
    ab_path = _write_csv(tmp_path / "ab.csv", AB_CSV_ROWS)
    with pytest.raises(ValueError, match="Mixed test_type"):
        generate_report_html([mos_path, ab_path])


def test_generate_report_dispatches_mos_ab_abx(tmp_path):
    mos_html = generate_report_html([_write_csv(tmp_path / "mos.csv", CSV_ROWS)])
    ab_html = generate_report_html([_write_csv(tmp_path / "ab.csv", AB_CSV_ROWS)])
    abx_html = generate_report_html([_write_csv(tmp_path / "abx.csv", ABX_CSV_ROWS)])
    assert "p-value (t-test)" in mos_html
    assert "p-value (binomial)" in ab_html
    assert "p-value (binomial)" in abx_html


def test_generate_report_mixed_ab_and_abx_raises_error(tmp_path):
    ab_path = _write_csv(tmp_path / "ab.csv", AB_CSV_ROWS)
    abx_path = _write_csv(tmp_path / "abx.csv", ABX_CSV_ROWS)
    with pytest.raises(ValueError, match="Mixed test_type"):
        generate_report_html([ab_path, abx_path])


def test_generate_report_mixed_abx_and_xab_raises_error(tmp_path):
    abx_path = _write_csv(tmp_path / "abx.csv", ABX_CSV_ROWS)
    xab_path = _write_csv(tmp_path / "xab.csv", XAB_CSV_ROWS)
    with pytest.raises(ValueError, match="Mixed test_type"):
        generate_report_html([abx_path, xab_path])


# -- browser tab title ------------------------------------------------------


def test_generate_report_sets_browser_tab_title_mos(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", CSV_ROWS)], title="My MOS Experiment"
    )
    assert "<title>My MOS Experiment</title>" in html


def test_generate_report_sets_browser_tab_title_ab(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)], title="My AB Experiment"
    )
    assert "<title>My AB Experiment</title>" in html


def test_generate_report_escapes_title_in_tab_title(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", CSV_ROWS)], title="A <script> & B"
    )
    assert "<title>A &lt;script&gt; &amp; B</title>" in html


def test_generate_report_escapes_system_name_in_pvalue_table(tmp_path):
    # System names come from the (admin-controlled) config, but the p-value
    # table must still HTML-escape them - the browser-tab title already does,
    # and the table shouldn't be the one place a stray '<' breaks the page.
    rows = _with_session_meta(
        "ab",
        [
            {"system_a": "A<b>", "system_b": "B", "utterance": "u1", "winner": "A<b>"},
            {"system_a": "A<b>", "system_b": "B", "utterance": "u2", "winner": "B"},
        ],
    )
    html = generate_report_html([_write_csv(tmp_path / "s.csv", rows)])
    # The escaped form only ever comes from the table cell; the Plotly chart
    # embeds the same pair label as JSON (raw '<'), so asserting the escaped
    # string is present is unambiguous evidence the table cell was escaped.
    assert "A&lt;b&gt; vs B" in html


# -- system_labels (rename) -------------------------------------------------


def test_rename_applied_to_mos_system_labels(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", CSV_ROWS)],
        system_labels={"A": "Proposed", "B": "Baseline"},
    )
    traces, _ = _plotly_call_args(html)
    assert traces[0]["x"] == ["Proposed", "Baseline"]


def test_rename_applied_to_ab_pair_label(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)],
        system_labels={"A": "Proposed", "B": "Baseline"},
    )
    assert "Proposed vs Baseline" in html
    assert "A vs B" not in html


def test_rename_is_optional(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CSV_ROWS)])
    traces, _ = _plotly_call_args(html)
    assert traces[0]["x"] == ["A", "B"]


# -- height_scale -----------------------------------------------------------


def test_height_scale_scales_chart_height(tmp_path):
    path = _write_csv(tmp_path / "s.csv", CSV_ROWS)
    _, base = _plotly_call_args(generate_report_html([path]))
    _, scaled = _plotly_call_args(generate_report_html([path], height_scale=2.0))
    assert scaled["height"] == base["height"] * 2


# -- alpha derived from confidence ------------------------------------------


def test_significance_alpha_defaults_to_005(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", THREE_SYSTEM_CSV_ROWS)])
    assert "α=0.05" in html


def test_significance_alpha_follows_confidence(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", THREE_SYSTEM_CSV_ROWS)], confidence=0.99
    )
    assert "α=0.01" in html
    assert "α=0.05" not in html


# -- require_full_order -----------------------------------------------------


def test_require_full_order_rejects_incomplete_order(tmp_path):
    with pytest.raises(ValueError, match="B"):
        generate_report_html(
            [_write_csv(tmp_path / "s.csv", CSV_ROWS)],
            system_order=["A"],
            require_full_order=True,
        )


def test_require_full_order_accepts_complete_order(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", CSV_ROWS)],
        system_order=["B", "A"],
        require_full_order=True,
    )
    traces, _ = _plotly_call_args(html)
    assert traces[0]["x"] == ["B", "A"]


def test_require_full_order_rejects_incomplete_pair_order(tmp_path):
    with pytest.raises(ValueError, match="B"):
        generate_report_html(
            [_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)],
            system_order=["A"],
            require_full_order=True,
        )
