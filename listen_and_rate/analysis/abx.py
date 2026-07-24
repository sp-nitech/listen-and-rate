"""ABX report: discrimination accuracy vs chance, raw counts, binomial test."""

from __future__ import annotations

from ._render import (
    _binomial_pair_stats,
    _display_namer,
    _ordered_pairs,
    _pvalue_header,
    _render_binary_outcome_charts,
    _render_trailing_tables_html,
    _significant_header,
)


def _generate_abx_report(
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
    """Build the ABX report: accuracy and count charts plus a binomial table.

    Accuracy is tested against 50% (chance level) rather than "no preference"
    - the same binomtest mechanism as AB's win-rate test, but answering "can
    listeners tell A and B apart?" instead of "which do they prefer?".
    """
    _disp = _display_namer(system_labels)
    alpha = 1 - confidence

    pair_labels: list[str] = []
    accuracy: list[float] = []
    accuracy_errors: list[float] = []
    hover_text: list[str] = []
    count_labels: list[str] = []
    count_values: list[int] = []
    table_rows: list[list[str]] = []

    for orig_a, orig_b, system_a, system_b in _ordered_pairs(df, system_order):
        sub = df[(df["system_a"] == orig_a) & (df["system_b"] == orig_b)]
        n_correct = int(sub["correct"].astype(bool).sum())
        n_total = len(sub)
        n_incorrect = n_total - n_correct
        rate, err, p_value = _binomial_pair_stats(n_correct, n_total, confidence)

        pair_labels.append(f"{_disp(system_a)} vs {_disp(system_b)}")
        accuracy.append(rate)
        accuracy_errors.append(err)
        hover_text.append(
            f"Correct: {n_correct}/{n_total} ({rate:.0%}\u2009±\u2009{err:.0%})"
        )
        # ABXConfig requires exactly 2 systems, so there is only ever one
        # pair and generic "Correct"/"Incorrect" labels stay unambiguous.
        count_labels.extend(["Correct", "Incorrect"])
        count_values.extend([n_correct, n_incorrect])
        table_rows.append(
            [
                f"{_disp(system_a)} vs {_disp(system_b)}",
                f"{p_value:.4f}",
                "*" if p_value < alpha else "",
            ]
        )

    accuracy_html, counts_html = _render_binary_outcome_charts(
        pair_labels,
        accuracy,
        accuracy_errors,
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
