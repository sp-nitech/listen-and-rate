"""ABX report: discrimination accuracy vs chance, raw counts, binomial test."""

from __future__ import annotations

from ._render import (
    _binomial_pair_stats,
    _figure_namer,
    _ordered_pairs,
    _pvalue_header,
    _render_binary_outcome_charts,
    _render_trailing_tables_html,
    _significant_header,
    _table_namer,
)


def _generate_abx_report(
    df,
    confidence: float,
    font_family: str,
    font_size: int,
    system_order: list[str] | None = None,
    system_labels: dict[str, str] | None = None,
    bold_system_names: bool = False,
    height_scale: float = 1.0,
    bar_width_scale: float = 1.0,
    png_scale: float = 2.0,
    mean_bar_color: str = "#72b7b2",
    count_bar_color: str = "#cd5c5c",
) -> str:
    """Build the ABX report: accuracy and count charts plus a binomial table.

    Accuracy is tested against 50% (chance level) rather than "no preference"
    - the same binomtest mechanism as AB's win-rate test, but answering "can
    listeners tell A and B apart?" instead of "which do they prefer?".
    """
    # Two namers: the figures may carry markup, the tables never can.
    figure_name = _figure_namer(system_labels, bold_system_names)
    table_name = _table_namer(system_labels)
    alpha = 1 - confidence

    pair_labels: list[str] = []
    accuracy: list[float] = []
    accuracy_errors_upper: list[float] = []
    accuracy_errors_lower: list[float] = []
    hover_text: list[str] = []
    count_labels: list[str] = []
    count_values: list[int] = []
    table_rows: list[list[str]] = []

    for orig_a, orig_b, system_a, system_b in _ordered_pairs(df, system_order):
        sub = df[(df["system_a"] == orig_a) & (df["system_b"] == orig_b)]
        n_correct = int(sub["correct"].astype(bool).sum())
        n_total = len(sub)
        n_incorrect = n_total - n_correct
        rate, ci_lo, ci_hi, p_value = _binomial_pair_stats(
            n_correct, n_total, confidence
        )

        pair_labels.append(f"{figure_name(system_a)} vs {figure_name(system_b)}")
        accuracy.append(rate)
        accuracy_errors_upper.append(ci_hi - rate)
        accuracy_errors_lower.append(rate - ci_lo)
        hover_text.append(
            # An interval, not +/-: the binomial CI is asymmetric away from
            # 50% (see _binomial_pair_stats). The counts behind the rate are
            # not repeated here - the counts chart sits directly below, and
            # every other test type's annotation carries the value alone.
            f"Correct: {rate:.0%} [{ci_lo:.0%}\u200a\u2013\u200a{ci_hi:.0%}]"
        )
        # ABXConfig requires exactly 2 systems, so there is only ever one
        # pair and generic "Correct"/"Incorrect" labels stay unambiguous.
        count_labels.extend(["Correct", "Incorrect"])
        count_values.extend([n_correct, n_incorrect])
        table_rows.append(
            [
                f"{table_name(system_a)} vs {table_name(system_b)}",
                f"{p_value:.4f}",
                "*" if p_value < alpha else "",
            ]
        )

    accuracy_html, counts_html = _render_binary_outcome_charts(
        pair_labels,
        accuracy,
        accuracy_errors_upper,
        accuracy_errors_lower,
        hover_text,
        count_labels,
        count_values,
        "Accuracy vs. chance",
        confidence,
        font_family,
        font_size,
        height_scale,
        bar_width_scale,
        png_scale,
        mean_bar_color=mean_bar_color,
        count_bar_color=count_bar_color,
    )
    trailing_tables = _render_trailing_tables_html(
        ["Pair", _pvalue_header("binomial test"), _significant_header(alpha)],
        table_rows,
        df,
    )
    return f"{accuracy_html}{counts_html}{trailing_tables}"
