"""Shared rendering and statistics helpers for the report generators.

HTML table/page shells, Plotly chart builders, system ordering, and the
binomial statistics reused across the MOS/DMOS/MUSHRA, CMOS, AB/XAB, and ABX
reports. Heavy optional dependencies (plotly, scipy) are imported lazily
inside the functions that need them, so importing this module stays cheap.
"""

from __future__ import annotations

from html import escape as _escape_html

_TH_STYLE = "border:1px solid #999;padding:6px 12px;background:#f0f0f0;text-align:left"
_TD_STYLE = "border:1px solid #999;padding:6px 12px"


def _system_sort_key(name: str, system_order: list[str] | None) -> tuple[int, int, str]:
    """Position `name` per system_order; shared by all report generators.

    Falls back to alphabetical order for names system_order doesn't mention
    (or when system_order is None).
    """
    if system_order and name in system_order:
        return (0, system_order.index(name), name)
    return (1, 0, name)


def _reorder_pair(a: str, b: str, system_order: list[str] | None) -> tuple[str, str]:
    """Return (a, b) or (b, a), whichever matches system_order's relative order."""
    if _system_sort_key(b, system_order) < _system_sort_key(a, system_order):
        return b, a
    return a, b


def _table_heading_html(label: str, font_size: int) -> str:
    """Render a centered h3 heading sitting just above a report table.

    Shared by the per-test-type main tables (significance, data summary) and
    the Participants section's per-form (Metadata/Survey) subsections, so
    every table heading looks the same.
    """
    return (
        f'<h3 style="text-align:center;font-size:{font_size + 2}px;'
        f'margin:24px 0 0">{_escape_html(label)}</h3>'
    )


def _render_table_html(
    headers: list[str], rows: list[list[str]], font_family: str, font_size: int
) -> str:
    """Render a headers+rows grid as a standalone, bordered HTML <table>.

    The generic table painter shared by every report table (significance,
    data summary, participant distributions). Headers/cells are HTML-escaped:
    they carry system names (and rename labels) straight from the admin's
    config, so a stray '<' shouldn't be able to break the page - matching the
    browser-tab title's own escaping.
    """
    thead = "".join(f'<th style="{_TH_STYLE}">{_escape_html(h)}</th>' for h in headers)
    tbody = "".join(
        "<tr>"
        + "".join(f'<td style="{_TD_STYLE}">{_escape_html(cell)}</td>' for cell in row)
        + "</tr>"
        for row in rows
    )
    return (
        f'<table style="margin:16px auto;border-collapse:collapse;'
        f'font-family:{font_family};font-size:{font_size}px">'
        f"<thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>"
    )


def _render_data_summary_table_html(df, font_family: str, font_size: int) -> str:
    """Render the session/record-count data summary table shared by all reports."""
    n_participants = df["session_id"].nunique() if "session_id" in df.columns else 0
    n_rows = len(df)
    return _render_table_html(
        ["Session count", "Record count"],
        [[str(n_participants), str(n_rows)]],
        font_family,
        font_size,
    )


def _wrap_report_html(
    title: str, body_html: str, font_family: str, font_size: int, width: int
) -> str:
    """Wrap chart/table HTML in the report page shell shared by all reports.

    plotly.js is embedded here, exactly once, rather than by the first chart's
    to_html(include_plotlyjs=True) - the generators return composable body
    fragments (every chart uses include_plotlyjs=False), so a report stacking
    several sections doesn't embed the ~3MB bundle per section.
    """
    from plotly.offline import get_plotlyjs

    body = (
        f'<div style="max-width:{width}px;margin:0 auto;font-family:{font_family}">'
        f'<h1 style="text-align:center;font-size:{font_size + 11}px">'
        f"{_escape_html(title)}</h1>"
        f"{body_html}"
        "</div>"
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f'<script type="text/javascript">{get_plotlyjs()}</script></head><body>'
        f"{body}</body></html>"
    )


def _ordered_pairs(
    df, system_order: list[str] | None
) -> list[tuple[str, str, str, str]]:
    """Return each distinct system pair in df, ordered by system_order.

    orig_a/orig_b are the pair exactly as stored (always alphabetical, per
    submission-time canonicalization); system_a/system_b are the same pair
    reordered via _reorder_pair() to match system_order's relative order -
    used both for display (which side a pair's stats are computed against)
    and, via the sort below, for which pair comes first when a report
    combines results spanning more than one system pair. Falls back to
    alphabetical order (both within a pair and across pairs) when
    system_order is None, matching the pre-existing single-pair behavior.
    """
    raw_pairs = df[["system_a", "system_b"]].drop_duplicates()
    ordered = [
        (
            row["system_a"],
            row["system_b"],
            *_reorder_pair(row["system_a"], row["system_b"], system_order),
        )
        for _, row in raw_pairs.iterrows()
    ]
    ordered.sort(
        key=lambda t: (
            _system_sort_key(t[2], system_order),
            _system_sort_key(t[3], system_order),
        )
    )
    return ordered


def _render_ci_bar_chart(
    pair_labels: list[str],
    values: list[float],
    errors: list[float],
    hover_text: list[str],
    axis_title: str,
    x_range: tuple[float, float],
    reference_x: float,
    confidence: float,
    font_family: str,
    font_size: int,
    height_scale: float = 1.0,
) -> str:
    """Render a horizontal bar chart with CI error whiskers, one bar per system pair.

    Shared by AB/ABX (proportion, x_range=(0,1), reference_x=0.5 for chance
    level) and CMOS (signed mean rating, x_range=(-3,3), reference_x=0 for
    "no difference"). Both outcomes are called out as an annotation shifted
    above the bar's own row (not as on-bar text, which would overlap the CI
    whiskers). The pair's own y-tick label is hidden since it's redundant
    with the annotation and the significance table below.
    """
    import plotly.graph_objects as go

    rate_fig = go.Figure(
        go.Bar(
            y=pair_labels,
            x=values,
            orientation="h",
            error_x=dict(
                type="data",
                array=errors,
                visible=True,
                thickness=2,
                width=6,
                color="black",
            ),
            marker_color="steelblue",
            showlegend=False,
            hovertext=hover_text,
            hovertemplate="%{hovertext}<extra></extra>",
        )
    )
    rate_fig.add_vline(x=reference_x, line_dash="dash", line_color="gray")
    # Annotation is positioned in paper-relative x (independent of the bar's
    # own data value) so it's always fully within the visible plot area,
    # regardless of how long or short the bar is - a data-relative position
    # would run off the right edge and get clipped for long bars.
    for label, txt in zip(pair_labels, hover_text, strict=True):
        rate_fig.add_annotation(
            x=0.5,
            xref="paper",
            y=label,
            yshift=22,
            text=txt,
            showarrow=False,
            xanchor="center",
            font=dict(size=font_size),
            # A high rate/accuracy pushes the bar past the annotation's fixed
            # x=0.5 position, putting dark text directly over the dark bar
            # fill; an opaque backing box keeps it readable there without
            # making it unreadable over the plain white background that's
            # behind it for low values instead.
            bgcolor="rgba(255,255,255,0.85)",
            borderpad=2,
        )
    # A phantom line-only trace purely to give the (black) error bars their
    # own legend entry - mirrors _generate_mos_report's CI legend, rather
    # than baking "(XX% CI)" into the axis title text.
    rate_fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode="lines",
            line=dict(color="black", width=2),
            name=f"{int(confidence * 100)}% confidence intervals",
        )
    )
    rate_fig.update_xaxes(range=list(x_range), tickformat=".1f", title_text=axis_title)
    rate_fig.update_yaxes(showticklabels=False)
    rate_fig.update_layout(
        showlegend=True,
        # Above the plot area (not overlaid on it) so it never covers bars,
        # error whiskers, or annotations regardless of how many pairs there are.
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=round(260 * height_scale),
        margin=dict(t=50, b=50),
        font=dict(family=font_family, size=font_size),
    )

    return rate_fig.to_html(include_plotlyjs=False, full_html=False)


def _render_counts_bar_chart(
    count_labels: list[str],
    count_values: list[int],
    font_family: str,
    font_size: int,
    height_scale: float = 1.0,
) -> str:
    """Render a vertical bar chart of raw outcome counts (AB/ABX/CMOS reports).

    Categories are laid out left-to-right in the exact order given by
    count_labels/count_values (e.g. AB centers "Tie" between its two
    systems), matching the vertical style of CMOS's 7-category chart.
    """
    import plotly.graph_objects as go

    counts_fig = go.Figure(
        go.Bar(x=count_labels, y=count_values, marker_color="indianred")
    )
    counts_fig.update_yaxes(title_text="Count")
    counts_fig.update_layout(
        showlegend=False,
        height=round(260 * height_scale),
        margin=dict(t=30, b=50),
        font=dict(family=font_family, size=font_size),
    )
    return counts_fig.to_html(include_plotlyjs=False, full_html=False)


def _binomial_pair_stats(
    n_success: int, n_total: int, confidence: float
) -> tuple[float, float, float]:
    """Compute (rate, CI half-width, p-value) for one pair's binomial outcome.

    Shared by AB (successes = wins for system_a among decisive choices) and
    ABX (successes = correct guesses among all guesses); the test is always
    against the 0.5 chance level. A pair with no data at all renders as a
    bar at 0.5 with no CI and p=1.
    """
    from scipy import stats

    if n_total > 0:
        result = stats.binomtest(n_success, n_total)
        rate = n_success / n_total
        lo, hi = result.proportion_ci(confidence_level=confidence)
        return rate, max(rate - lo, hi - rate), float(result.pvalue)
    return 0.5, 0.0, 1.0


def _render_binary_outcome_charts(
    pair_labels: list[str],
    rate: list[float],
    errors: list[float],
    hover_text: list[str],
    count_labels: list[str],
    count_values: list[int],
    rate_axis_title: str,
    confidence: float,
    font_family: str,
    font_size: int,
    height_scale: float = 1.0,
) -> tuple[str, str]:
    """Render the rate-vs-chance + raw-counts chart pair for AB and ABX reports.

    One bar per system pair (not one bar per system): the bar's length is
    `rate` - the dashed line at 0.5 marks "no preference"/"chance level".
    """
    rate_html = _render_ci_bar_chart(
        pair_labels,
        rate,
        errors,
        hover_text,
        rate_axis_title,
        x_range=(0, 1),
        reference_x=0.5,
        confidence=confidence,
        font_family=font_family,
        font_size=font_size,
        height_scale=height_scale,
    )
    counts_html = _render_counts_bar_chart(
        count_labels, count_values, font_family, font_size, height_scale
    )
    return rate_html, counts_html
