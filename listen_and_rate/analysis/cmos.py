"""CMOS report: horizontal mean-CI bar, 7-category count chart, one-sample t-test."""

from __future__ import annotations

from ._render import (
    _bar_gap,
    _display_namer,
    _fig_to_html,
    _ordered_pairs,
    _render_ci_bar_chart,
    _render_trailing_tables_html,
)

_CMOS_CATEGORIES = [-3, -2, -1, 0, 1, 2, 3]
_CMOS_CATEGORY_LABELS = [
    "Much worse",
    "Worse",
    "Slightly worse",
    "About the same",
    "Slightly better",
    "Better",
    "Much better",
]


def _render_cmos_category_chart(
    pair_labels: list[str],
    counts_per_pair: list[list[int]],
    font_family: str,
    font_size: int,
    height_scale: float = 1.0,
    bar_width_scale: float = 1.0,
    png_scale: float = 2.0,
    bar_color: str = "#cd5c5c",
) -> str:
    """Render the 7-category (much worse..much better) response-count bar chart.

    One go.Bar trace per pair; a report combining more than one system pair
    groups the pairs' bars side by side per category (barmode="group") and
    shows a legend, while the common single-pair case renders as a plain,
    legend-free 7-bar chart.
    """
    import plotly.graph_objects as go

    x_labels = [
        f"{'+' if v > 0 else ''}{v} ({label})"
        for v, label in zip(_CMOS_CATEGORIES, _CMOS_CATEGORY_LABELS, strict=True)
    ]
    fig = go.Figure()
    for label, counts in zip(pair_labels, counts_per_pair, strict=True):
        fig.add_trace(go.Bar(x=x_labels, y=counts, name=label, marker_color=bar_color))
    fig.update_yaxes(title_text="Count")
    fig.update_layout(
        barmode="group",
        showlegend=len(pair_labels) > 1,
        height=round(320 * height_scale),
        bargap=_bar_gap(bar_width_scale),
        margin=dict(t=30, b=80),
        font=dict(family=font_family, size=font_size),
    )
    return _fig_to_html(fig, png_scale)


def _generate_cmos_report(
    df,
    confidence: float,
    font_family: str,
    font_size: int,
    system_order: list[str] | None = None,
    system_labels: dict[str, str] | None = None,
    height_scale: float = 1.0,
    bar_width_scale: float = 1.0,
    png_scale: float = 2.0,
    mean_bar_color: str = "#72b7b2",
    count_bar_color: str = "#cd5c5c",
) -> str:
    """Build the CMOS report: mean-CI bar, 7-category counts, one-sample t-test.

    Mean/CI use the same t-distribution approach as _generate_mos_report
    (continuous ratings), rendered with _render_ci_bar_chart's AB-style
    horizontal layout instead of MOS's vertical one, since CMOS is
    fundamentally a per-pair comparison like AB rather than a per-system one.
    """
    import math

    from scipy import stats

    _disp = _display_namer(system_labels)
    alpha = 1 - confidence

    pair_labels: list[str] = []
    means: list[float] = []
    mean_errors: list[float] = []
    hover_text: list[str] = []
    counts_per_pair: list[list[int]] = []
    table_rows: list[list[str]] = []

    for orig_a, orig_b, system_a, system_b in _ordered_pairs(df, system_order):
        sub = df[(df["system_a"] == orig_a) & (df["system_b"] == orig_b)]
        ratings = sub["rating"].astype(float)
        n = len(ratings)
        mean = float(ratings.mean()) if n else 0.0
        sem = float(stats.sem(ratings)) if n >= 2 else 0.0
        if n >= 2 and sem > 0:
            lo, _ = stats.t.interval(confidence, df=n - 1, loc=mean, scale=sem)
            err = float(mean - lo)
            p_value = float(stats.ttest_1samp(ratings, popmean=0).pvalue)  # type: ignore[arg-type]
        else:
            err = 0.0
            p_value = float("nan")

        pair = f"{_disp(system_a)} vs {_disp(system_b)}"
        pair_labels.append(pair)
        means.append(mean)
        mean_errors.append(err)
        hover_text.append(f"{pair}: {mean:.2f}±{err:.2f}")
        counts_per_pair.append([int((ratings == v).sum()) for v in _CMOS_CATEGORIES])
        table_rows.append(
            [
                pair,
                "N/A" if math.isnan(p_value) else f"{p_value:.4f}",
                "" if math.isnan(p_value) else ("*" if p_value < alpha else ""),
            ]
        )

    ci_html = _render_ci_bar_chart(
        pair_labels,
        means,
        mean_errors,
        hover_text,
        "Mean CMOS rating",
        x_range=(-3, 3),
        reference_x=0,
        confidence=confidence,
        font_family=font_family,
        font_size=font_size,
        height_scale=height_scale,
        bar_width_scale=bar_width_scale,
        png_scale=png_scale,
        bar_color=mean_bar_color,
    )
    category_html = _render_cmos_category_chart(
        pair_labels,
        counts_per_pair,
        font_family,
        font_size,
        height_scale,
        bar_width_scale,
        png_scale,
        count_bar_color,
    )
    trailing_tables = _render_trailing_tables_html(
        [
            "Pair",
            "p-value (t-test vs. 0)",
            f"Significant (α={alpha:.2f})",
        ],
        table_rows,
        df,
    )
    return f"{ci_html}{category_html}{trailing_tables}"
