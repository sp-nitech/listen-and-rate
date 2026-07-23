"""AB/XAB report: preference (or closeness) rate bars, raw counts, binomial test."""

from __future__ import annotations

from ._render import (
    _binomial_pair_stats,
    _ordered_pairs,
    _render_binary_outcome_charts,
    _render_trailing_tables_html,
)


def _generate_ab_report(
    df,
    confidence: float,
    font_family: str,
    font_size: int,
    system_order: list[str] | None = None,
    system_labels: dict[str, str] | None = None,
    height_scale: float = 1.0,
    mean_bar_color: str = "#72b7b2",
    count_bar_color: str = "#cd5c5c",
    outcome_column: str = "winner",
    rate_axis_title: str = "Preference rate",
    tie_label: str = "No preference",
    include_tie: bool = True,
) -> str:
    """Build the AB report: rate and count charts plus a binomial-test table.

    Also reused by XAB, whose stored rows differ from AB's only in the
    outcome column ("closer" instead of "winner", no tie value) and in what
    the rate means (closeness to the reference rather than preference) -
    hence the outcome_column/rate_axis_title/include_tie parameters.
    """
    labels = system_labels or {}
    alpha = 1 - confidence

    def _disp(name: str) -> str:
        return labels.get(name, name)

    pair_labels: list[str] = []
    pref_rate_a: list[float] = []
    pref_errors: list[float] = []
    hover_text: list[str] = []
    count_labels: list[str] = []
    count_values: list[int] = []
    table_rows: list[list[str]] = []

    for orig_a, orig_b, system_a, system_b in _ordered_pairs(df, system_order):
        sub = df[(df["system_a"] == orig_a) & (df["system_b"] == orig_b)]
        n_a = int((sub[outcome_column] == system_a).sum())
        n_b = int((sub[outcome_column] == system_b).sum())
        rate_a, err, p_value = _binomial_pair_stats(n_a, n_a + n_b, confidence)

        da, db = _disp(system_a), _disp(system_b)
        pair_labels.append(f"{da} vs {db}")
        pref_rate_a.append(rate_a)
        pref_errors.append(err)
        hover_text.append(f"{da}: {rate_a:.0%}  /  {db}: {1 - rate_a:.0%}")
        if include_tie:
            # Tie centered between the two systems' counts, matching CMOS's
            # vertical category chart's visual style. The bar's name is
            # configurable (report-config tie_label); its centered position is
            # not, since it encodes "neither of the flanking systems".
            n_tie = int((sub[outcome_column] == "tie").sum())
            count_labels.extend([da, tie_label, db])
            count_values.extend([n_a, n_tie, n_b])
        else:
            count_labels.extend([da, db])
            count_values.extend([n_a, n_b])
        table_rows.append(
            [
                f"{da} vs {db}",
                f"{p_value:.4f}",
                "*" if p_value < alpha else "",
            ]
        )

    pref_html, counts_html = _render_binary_outcome_charts(
        pair_labels,
        pref_rate_a,
        pref_errors,
        hover_text,
        count_labels,
        count_values,
        rate_axis_title,
        confidence,
        font_family,
        font_size,
        height_scale,
        mean_bar_color=mean_bar_color,
        count_bar_color=count_bar_color,
    )
    trailing_tables = _render_trailing_tables_html(
        ["Pair", "p-value (binomial test)", f"Significant (α={alpha:.2f})"],
        table_rows,
        df,
    )
    return f"{pref_html}{counts_html}{trailing_tables}"
