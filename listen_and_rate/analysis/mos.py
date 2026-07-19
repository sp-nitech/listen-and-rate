"""MOS-family report (MOS/DMOS/MUSHRA): mean+CI bars, rating distribution, t-tests."""

from __future__ import annotations

from ._render import (
    _render_data_summary_table_html,
    _render_table_html,
    _system_sort_key,
    _table_heading_html,
)


def _generate_mos_report(
    df,
    confidence: float,
    font_family: str,
    font_size: int,
    system_order: list[str] | None = None,
    system_labels: dict[str, str] | None = None,
    height_scale: float = 1.0,
    metric_label: str = "MOS",
    axis_dtick: float = 0.5,
    boxplot_range: tuple[float, float] = (0.5, 5.5),
    boxplot_dtick: float = 1,
) -> str:
    """Build the MOS/DMOS/MUSHRA report: mean+CI and distribution charts, t-tests.

    Shared by all three test types - a DMOS/MUSHRA submission's stored row
    shape (utterance/system/rating) is identical to MOS's, so only the
    y-axis label (`metric_label`) and the scale-dependent axis parameters
    (`axis_dtick`, `boxplot_range`, `boxplot_dtick` - 1-5 for MOS/DMOS,
    0-100 for MUSHRA) differ.
    """
    import itertools
    import math
    import warnings

    import plotly.graph_objects as go
    from scipy import stats

    labels = system_labels or {}
    alpha = 1 - confidence

    def _disp(name: str) -> str:
        return labels.get(name, name)

    systems: list[str] = []
    means: list[float] = []
    errors: list[float] = []
    raw: dict[str, list[float]] = {}

    # sort=False here - groups are reordered below via system_order (falling
    # back to alphabetical), rather than pandas' own always-alphabetical sort.
    for system, group in df.groupby("system", sort=False):
        ratings = group["rating"].astype(float)
        n = len(ratings)
        mean = float(ratings.mean())  # type: ignore[arg-type]
        sem = float(stats.sem(ratings)) if n >= 2 else 0.0
        if n >= 2 and sem > 0:
            # scale=0 (every rating identical) sends t.interval() into
            # -inf * 0, which scipy warns about and returns NaN for - a
            # zero-spread sample's CI is trivially the point itself (err=0).
            lo, _ = stats.t.interval(confidence, df=n - 1, loc=mean, scale=sem)
            err = float(mean - lo)
        else:
            err = 0.0
        sys_name = str(system)
        systems.append(sys_name)
        means.append(mean)
        errors.append(err)
        raw[sys_name] = ratings.tolist()

    order = sorted(
        range(len(systems)), key=lambda i: _system_sort_key(systems[i], system_order)
    )
    systems = [systems[i] for i in order]
    means = [means[i] for i in order]
    errors = [errors[i] for i in order]

    ci_label = f"{int(confidence * 100)}% CI"

    mos_fig = go.Figure(
        go.Bar(
            x=[_disp(s) for s in systems],
            y=means,
            error_y=dict(
                type="data",
                array=errors,
                visible=True,
                thickness=2,
                width=6,
                color="black",
            ),
            marker_color="steelblue",
            showlegend=False,
            hovertemplate=(
                "<b>%{x}</b><br>"
                f"{metric_label}: %{{y:.3f}}<br>"
                f"±%{{error_y.array:.3f}} ({ci_label})"
                "<extra></extra>"
            ),
        )
    )
    # Value ± CI text above each bar's error whisker, e.g. "3.22±0.55" - an
    # opaque backing box keeps it readable regardless of what's behind it
    # (bar fill for a tall bar, plain background for a short one), matching
    # _render_binary_outcome_charts' annotation treatment.
    for sys_name, mean, err in zip(systems, means, errors, strict=True):
        mos_fig.add_annotation(
            x=_disp(sys_name),
            y=mean + err,
            yshift=14,
            text=f"{mean:.2f}±{err:.2f}",
            showarrow=False,
            font=dict(size=font_size),
            bgcolor="rgba(255,255,255,0.85)",
            borderpad=2,
        )
    # A phantom line-only trace purely to give the (black) error bars their
    # own legend entry - the bar itself is excluded from the legend above,
    # since a blue bar-color swatch would misrepresent what the CI actually
    # looks like on the chart.
    mos_fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode="lines",
            line=dict(color="black", width=2),
            name=f"{int(confidence * 100)}% confidence intervals",
        )
    )
    # Zoom the y-axis to the actual value±CI spread (snapped to 0.5 ticks,
    # with a minimum span) instead of always showing the fixed 0.5-5.5 scale
    # - systems clustered close together would otherwise be hard to tell
    # apart. A minimum span keeps trivial differences from being visually
    # exaggerated when every system scores nearly the same.
    MIN_SPAN = axis_dtick * 2
    PADDING_FRACTION = 0.2
    data_lo = min(m - e for m, e in zip(means, errors, strict=True))
    data_hi = max(m + e for m, e in zip(means, errors, strict=True))
    padding = (data_hi - data_lo) * PADDING_FRACTION
    padded_lo, padded_hi = data_lo - padding, data_hi + padding
    if padded_hi - padded_lo < MIN_SPAN:
        center = (padded_lo + padded_hi) / 2
        padded_lo, padded_hi = center - MIN_SPAN / 2, center + MIN_SPAN / 2
    # A wide CI (e.g. from a small, high-variance sample) can otherwise pull
    # padded_lo below 0 - never a valid rating on any of this function's
    # scales (1-5 for MOS/DMOS, 0-100 for MUSHRA).
    axis_lo = max(math.floor(padded_lo / axis_dtick) * axis_dtick, 0.0)
    axis_hi = math.ceil(padded_hi / axis_dtick) * axis_dtick

    mos_fig.update_yaxes(
        range=[axis_lo, axis_hi],
        dtick=axis_dtick,
        tickformat=".1f",
        title_text=metric_label,
    )
    mos_fig.update_layout(
        showlegend=True,
        # Above the plot area (not overlaid on it) so it never covers bars,
        # error whiskers, or annotations regardless of how many systems there are.
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=round(320 * height_scale),
        margin=dict(t=50, b=50),
        font=dict(family=font_family, size=font_size),
    )

    dist_fig = go.Figure()
    for sys_name in systems:
        n = len(raw[sys_name])
        dist_fig.add_trace(
            go.Box(
                y=raw[sys_name],
                name=f"{_disp(sys_name)}",
                boxpoints="all",
                jitter=0.3,
                pointpos=-1.6,
                marker_size=4,
            )
        )
    dist_fig.update_yaxes(
        range=list(boxplot_range),
        dtick=boxplot_dtick,
        tickformat=".1f",
        title_text="Rating",
    )
    dist_fig.update_layout(
        showlegend=False,
        height=round(320 * height_scale),
        margin=dict(t=30, b=50),
        font=dict(family=font_family, size=font_size),
    )

    mos_html = mos_fig.to_html(include_plotlyjs=False, full_html=False)
    dist_html = dist_fig.to_html(include_plotlyjs=False, full_html=False)

    n_pairs = math.comb(len(systems), 2)
    table_rows = []
    for sys_i, sys_j in itertools.combinations(systems, 2):
        if len(raw[sys_i]) < 2 or len(raw[sys_j]) < 2:
            # t-test needs at least 2 samples per group to estimate variance.
            table_rows.append([f"{_disp(sys_i)} vs {_disp(sys_j)}", "N/A", "N/A", ""])
            continue
        # Near-identical (or exactly identical) samples make scipy warn about
        # precision loss in its internal variance calculation; we already
        # handle the degenerate NaN outcome below (N/A), so the warning
        # itself is noise to a CLI user by this point, not something actionable.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            raw_p = float(stats.ttest_ind(raw[sys_i], raw[sys_j]).pvalue)  # type: ignore[arg-type]
        if math.isnan(raw_p):
            # Both groups have zero variance (every rating identical) - the
            # t-test is degenerate (0/0) rather than meaningfully "not
            # significant", so show N/A instead of a misleading blank marker
            # (nan < 0.05 is False, which would otherwise read as "not
            # significant").
            table_rows.append([f"{_disp(sys_i)} vs {_disp(sys_j)}", "N/A", "N/A", ""])
            continue
        adj_p = min(raw_p * n_pairs, 1.0) if n_pairs else raw_p
        table_rows.append(
            [
                f"{_disp(sys_i)} vs {_disp(sys_j)}",
                f"{raw_p:.4f}",
                f"{adj_p:.4f}",
                "*" if adj_p < alpha else "",
            ]
        )
    significance_test_table = _render_table_html(
        [
            "Pair",
            "p-value (t-test)",
            "Bonferroni-adjusted p-value",
            f"Significant (α={alpha:.2f})",
        ],
        table_rows,
        font_family,
        font_size,
    )
    data_summary_table = _render_data_summary_table_html(df, font_family, font_size)

    significance_test_heading = _table_heading_html("Significance tests", font_size)
    data_summary_heading = _table_heading_html("Data summary", font_size)
    return (
        f"{mos_html}{dist_html}"
        f"{significance_test_heading}{significance_test_table}"
        f"{data_summary_heading}{data_summary_table}"
    )
