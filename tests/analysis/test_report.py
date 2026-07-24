"""Tests for the report entry point: file reading, dispatch, mixed-type guard, title."""

from __future__ import annotations

import re

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
    _plotly_config,
    _with_session_meta,
    _write_csv,
    _write_json,
    generate_report_html,
)

# -- CSV input --------------------------------------------------------------


def test_generate_report_returns_html(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CSV_ROWS)])
    assert "<html>" in html


def test_mos_report_labels_main_tables(tmp_path):
    # The two main tables (pairwise significance, data counts) carry headings.
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CSV_ROWS)])
    assert ">Significance tests</h3>" in html
    assert ">Data summary</h3>" in html


def test_report_mean_bar_color_applies_to_mean_bars(tmp_path):
    # mean_bar_color colors the mean/rate bar (MOS mean here, AB/CMOS CI bar).
    for rows in (CSV_ROWS, CMOS_CSV_ROWS):
        html = generate_report_html(
            [_write_csv(tmp_path / "s.csv", rows)], mean_bar_color="#123456"
        )
        traces, _ = _plotly_call_args(html)
        assert traces[0]["marker"]["color"] == "#123456"


def test_report_bar_colors_default(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)])
    mean_traces, _ = _plotly_call_args(html)  # first figure: the rate/CI bar
    count_traces, _ = _plotly_call_args(html, occurrence=1)  # counts figure
    assert mean_traces[0]["marker"]["color"] == "#72b7b2"
    assert count_traces[0]["marker"]["color"] == "#cd5c5c"


def test_report_count_bar_color_applies_to_count_bars(tmp_path):
    # count_bar_color colors the raw-count bars (AB/ABX counts, CMOS categories).
    for rows in (AB_CSV_ROWS, CMOS_CSV_ROWS):
        html = generate_report_html(
            [_write_csv(tmp_path / "s.csv", rows)], count_bar_color="#654321"
        )
        count_traces, _ = _plotly_call_args(html, occurrence=1)
        assert count_traces[0]["marker"]["color"] == "#654321"


def test_report_config_font_styles_charts_only_not_html(tmp_path):
    # The report-config font (family + size) styles the Plotly charts only; the
    # HTML page chrome (title, headings, tables) keeps a fixed font.
    path = _write_csv(tmp_path / "s.csv", CSV_ROWS)
    big = generate_report_html([path], font_family="Georgia", font_size=20)
    small = generate_report_html([path], font_family="Courier", font_size=8)

    def html_chrome(html):
        # The HTML CSS font-* declarations (chart fonts live in the plotly JSON).
        return sorted(re.findall(r"font-(?:family|size):[^;\"]+", html))

    assert html_chrome(big) == html_chrome(small)  # HTML unaffected by config font
    assert "font-family:sans-serif" in big
    assert "font-family:Georgia" not in big
    assert "font-size:24px" in big  # fixed title size, not 20-derived


def test_report_table_width_is_decoupled_from_config_width(tmp_path):
    # Tables keep their natural content width (width:max-content) and break out
    # of the width-capped page container (full-bleed translateX centering), so
    # the report-config `width` - which scales the charts - neither stretches
    # nor squeezes them.
    path = _write_csv(tmp_path / "s.csv", CSV_ROWS)
    for width in (500, 1200):
        html = generate_report_html([path], width=width)
        assert "width:max-content" in html
        assert "translateX(-50%)" in html


def test_ab_report_labels_main_tables(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "ab.csv", AB_CSV_ROWS)])
    assert ">Significance tests</h3>" in html
    assert ">Data summary</h3>" in html


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
    # Both p-value columns follow the "p-value (X)"/"... (X)" form.
    assert "Adjusted p-value (Bonferroni)" in mos_html
    assert "p-value (binomial test)" in ab_html


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
    assert "p-value (binomial test)" in ab_html
    assert "p-value (binomial test)" in abx_html


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
            {"system_a": "A<b>", "system_b": "B", "utterance": "u1", "winner": "A"},
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


# -- bar_width_scale --------------------------------------------------------


def test_bar_width_scale_default_matches_plotly_look(tmp_path):
    # Scale 1.0 sets bargap to Plotly's own 0.2 default (bars fill 80% of
    # their category slot), so the default report look is unchanged.
    html = generate_report_html([_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)])
    _, mean_layout = _plotly_call_args(html)
    _, count_layout = _plotly_call_args(html, occurrence=1)
    assert mean_layout["bargap"] == pytest.approx(0.2)
    assert count_layout["bargap"] == pytest.approx(0.2)


def test_bar_width_scale_thins_bars_in_all_bar_charts(tmp_path):
    # Scale 0.5 halves the bars' slot fraction (0.8 -> 0.4, i.e. bargap 0.6)
    # in the mean/rate chart and the count chart of every bar-based report.
    for rows in (AB_CSV_ROWS, CMOS_CSV_ROWS):
        html = generate_report_html(
            [_write_csv(tmp_path / "s.csv", rows)], bar_width_scale=0.5
        )
        _, mean_layout = _plotly_call_args(html)
        _, count_layout = _plotly_call_args(html, occurrence=1)
        assert mean_layout["bargap"] == pytest.approx(0.6)
        assert count_layout["bargap"] == pytest.approx(0.6)


def test_bar_width_scale_applies_to_mos_mean_chart_not_boxplot(tmp_path):
    # MOS's second figure is a boxplot, not a bar chart - the scale must
    # not leak a bargap into it.
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", CSV_ROWS)], bar_width_scale=0.5
    )
    _, mean_layout = _plotly_call_args(html)
    _, box_layout = _plotly_call_args(html, occurrence=1)
    assert mean_layout["bargap"] == pytest.approx(0.6)
    assert "bargap" not in box_layout


def test_bar_width_scale_gap_floors_at_zero(tmp_path):
    # Bars cannot exceed their category slot: scales >= 1.25 clamp to
    # touching bars (bargap 0) instead of a negative gap Plotly rejects.
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", CSV_ROWS)], bar_width_scale=2.0
    )
    _, mean_layout = _plotly_call_args(html)
    assert mean_layout["bargap"] == 0


# -- png_scale --------------------------------------------------------------


def test_png_download_defaults_to_double_resolution(tmp_path):
    # The modebar's PNG download renders at 2x resolution out of the box -
    # every figure gets it, the boxplot (occurrence 1 here) included.
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CSV_ROWS)])
    for occurrence in (0, 1):
        config = _plotly_config(html, occurrence=occurrence)
        assert config["toImageButtonOptions"]["scale"] == 2.0


def test_png_scale_is_configurable(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)], png_scale=4.0
    )
    for occurrence in (0, 1):
        config = _plotly_config(html, occurrence=occurrence)
        assert config["toImageButtonOptions"]["scale"] == 4.0


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


# -- groups (stacked filtered sections) ---------------------------------------


def _mos_row(session_id, device, system, utterance, rating, trial_count="Appropriate"):
    # Form answers live under the metadata_/survey_ column prefixes in stored
    # CSVs (see storage.py); filter keys in report configs stay unprefixed.
    return {
        "session_id": session_id,
        "timestamp": "t",
        "test_type": "mos",
        "metadata_device": device,
        "survey_trial_count": trial_count,
        "system": system,
        "utterance": utterance,
        "rating": rating,
    }


_GROUPED_ROWS = [
    _mos_row("s1", "Headphones", "A", "F01_a", 4),
    _mos_row("s1", "Headphones", "B", "F01_a", 2),
    _mos_row("s2", "Speakers", "A", "F02_a", 5, trial_count="TooMany"),
    _mos_row("s2", "Speakers", "B", "F02_a", 1, trial_count="TooMany"),
]


def _section_chunks(html: str) -> list[str]:
    """Split the report at its <h2 section headings; chunk 0 is the preamble."""
    return html.split("<h2")


def test_groups_render_labeled_sections_in_order(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", _GROUPED_ROWS)],
        groups=[
            {"label": "All listeners"},
            {"label": "Headphones", "metadata_filter": {"device": "Headphones"}},
        ],
    )
    chunks = _section_chunks(html)
    assert len(chunks) == 4  # preamble + 2 group sections + Participants
    assert "All listeners" in chunks[1]
    assert "Headphones" in chunks[2]
    assert "Participants" in chunks[3]
    # Session/record counts per section: all = 2/4, filtered = 1/2.
    assert ">2</td>" in chunks[1] and ">4</td>" in chunks[1]
    assert ">1</td>" in chunks[2] and ">2</td>" in chunks[2]


def test_groups_stimuli_filter_globs_on_utterance(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", _GROUPED_ROWS)],
        groups=[{"label": "Speaker F01", "stimuli_filter": {"utterance": "F01_*"}}],
    )
    section = _section_chunks(html)[1]
    assert ">2</td>" in section  # 2 of the 4 records match F01_*


def test_groups_filters_combine_with_and(tmp_path):
    rows = _GROUPED_ROWS + [
        _mos_row("s3", "Headphones", "A", "F02_b", 3),
    ]
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", rows)],
        groups=[
            {
                "label": "F01 on headphones",
                "metadata_filter": {"device": "Headphones"},
                "stimuli_filter": {"utterance": "F01_*"},
            }
        ],
    )
    section = _section_chunks(html)[1]
    # s1's two F01 rows survive; s2 (Speakers) and s3's F02_b row do not.
    assert ">1</td>" in section and ">2</td>" in section


def test_groups_unknown_metadata_key_raises_with_label(tmp_path):
    with pytest.raises(ValueError, match="Headphones group"):
        generate_report_html(
            [_write_csv(tmp_path / "s.csv", _GROUPED_ROWS)],
            groups=[{"label": "Headphones group", "metadata_filter": {"devise": "x"}}],
        )


def test_groups_outcome_column_in_metadata_filter_raises(tmp_path):
    # 'rating' exists as a column but is an outcome, not a metadata field:
    # metadata_filter looks up metadata_rating, which doesn't exist, so
    # self-serving outcome filtering is unreachable by construction.
    with pytest.raises(ValueError, match="rating"):
        generate_report_html(
            [_write_csv(tmp_path / "s.csv", _GROUPED_ROWS)],
            groups=[{"label": "g", "metadata_filter": {"rating": "5"}}],
        )


def test_groups_survey_filter_selects_sessions(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", _GROUPED_ROWS)],
        groups=[
            {"label": "Comfortable", "survey_filter": {"trial_count": "Appropriate"}}
        ],
    )
    section = _section_chunks(html)[1]
    # Only s1 answered "Appropriate": 1 session, 2 records.
    assert ">1</td>" in section and ">2</td>" in section


def test_groups_metadata_filter_does_not_see_survey_columns(tmp_path):
    # The prefixes make the two filter blocks strictly checkable: a survey
    # key inside metadata_filter must fail instead of silently matching.
    with pytest.raises(ValueError, match="trial_count"):
        generate_report_html(
            [_write_csv(tmp_path / "s.csv", _GROUPED_ROWS)],
            groups=[{"label": "g", "metadata_filter": {"trial_count": "Appropriate"}}],
        )


def test_groups_no_match_raises_with_label(tmp_path):
    with pytest.raises(ValueError, match="Bone conduction"):
        generate_report_html(
            [_write_csv(tmp_path / "s.csv", _GROUPED_ROWS)],
            groups=[
                {
                    "label": "Bone conduction",
                    "metadata_filter": {"device": "BoneConduction"},
                }
            ],
        )


def test_groups_stimuli_filter_system_on_pair_results_raises(tmp_path):
    # Pair-based results carry system_a/system_b, not a 'system' column, so a
    # system stimuli_filter cannot apply and must fail loudly.
    with pytest.raises(ValueError, match="system"):
        generate_report_html(
            [_write_csv(tmp_path / "s.csv", AB_CSV_ROWS)],
            groups=[{"label": "g", "stimuli_filter": {"system": "A"}}],
        )


def test_groups_label_is_escaped(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", _GROUPED_ROWS)],
        groups=[{"label": "A <b>& B"}],
    )
    assert "A &lt;b&gt;&amp; B" in html


def test_no_groups_renders_no_section_headings(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CSV_ROWS)])
    assert "<h2" not in html


def test_groups_underline_each_label(tmp_path):
    # Each section label reads as a title: an underline below the text (not a
    # separate rule above it), with sections separated by whitespace alone.
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", _GROUPED_ROWS)],
        groups=[
            {"label": "All listeners"},
            {"label": "Headphones", "metadata_filter": {"device": "Headphones"}},
        ],
    )
    h2_tags = re.findall(r"<h2[^>]*>", html)
    assert len(h2_tags) == 3  # 2 groups + the trailing Participants section
    assert all("border-bottom" in tag for tag in h2_tags)


def test_json_form_answers_flattened_with_prefixes(tmp_path):
    # JSON results keep metadata/survey as nested objects; the reader must
    # flatten them into the same prefixed columns CSVs carry, so filters and
    # the Participants section behave identically for both formats.
    p = _write_json(
        tmp_path / "s1.json",
        "s1",
        "mos",
        RATINGS_A_B,
        metadata={"device": "Headphones"},
        survey={"trial_count": "Appropriate"},
    )
    html = generate_report_html(
        [p],
        groups=[
            {"label": "HP", "metadata_filter": {"device": "Headphones"}},
            {"label": "OK", "survey_filter": {"trial_count": "Appropriate"}},
        ],
    )
    assert "HP" in html and "OK" in html


# -- Participants section -----------------------------------------------------


def test_participants_section_shows_per_session_distributions(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", _GROUPED_ROWS)])
    assert "Participants" in html
    # Per-session dedupe: s1 has two rows but its answers count as ONE session.
    assert re.search(r"Headphones</td><td[^>]*>1</td>", html)
    assert re.search(r"TooMany</td><td[^>]*>1</td>", html)
    # Field names are shown without the storage prefix, split by form.
    assert ">device</td>" in html
    assert ">trial_count</td>" in html
    assert ">Metadata<" in html and ">Survey<" in html


def test_participants_section_uses_field_labels_when_given(tmp_path):
    # With form_labels (from --config), the Field column shows the human
    # label, not the storage key.
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", _GROUPED_ROWS)],
        form_labels={
            "metadata_device": "Playback device",
            "survey_trial_count": "Was the number of trials appropriate?",
        },
    )
    assert ">Playback device</td>" in html
    assert ">Was the number of trials appropriate?</td>" in html
    # The raw keys must not leak into the Field column.
    assert ">device</td>" not in html
    assert ">trial_count</td>" not in html


def test_participants_section_falls_back_to_key_without_label(tmp_path):
    # A column with no matching label (or no form_labels at all) still shows
    # the bare key, so config-less reports are unchanged.
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", _GROUPED_ROWS)],
        form_labels={"metadata_device": "Playback device"},
    )
    assert ">Playback device</td>" in html
    assert ">trial_count</td>" in html


def test_participants_section_absent_without_form_columns(tmp_path):
    html = generate_report_html([_write_csv(tmp_path / "s.csv", CSV_ROWS)])
    assert "Participants" not in html


def test_participants_section_appears_once_after_group_sections(tmp_path):
    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", _GROUPED_ROWS)],
        groups=[
            {"label": "All listeners"},
            {"label": "HeadphonesOnly", "metadata_filter": {"device": "Headphones"}},
        ],
    )
    assert html.count("Participants") == 1
    assert html.rfind("Participants") > html.rfind("HeadphonesOnly")


def test_plotlyjs_embedded_once_across_sections(tmp_path):
    from plotly.offline import get_plotlyjs

    html = generate_report_html(
        [_write_csv(tmp_path / "s.csv", _GROUPED_ROWS)],
        groups=[
            {"label": "All"},
            {"label": "Headphones", "metadata_filter": {"device": "Headphones"}},
        ],
    )
    assert html.count(get_plotlyjs()[:200]) == 1


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
