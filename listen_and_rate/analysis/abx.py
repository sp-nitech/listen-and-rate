"""ABX report: discrimination accuracy vs chance, raw counts, binomial test."""

from __future__ import annotations

from ._render import (
    _binomial_pair_stats,
    _ordered_pairs,
    _render_binary_outcome_charts,
    _render_pvalue_table_html,
    _render_summary_stats_table_html,
)


def _generate_abx_report(
    df,
    confidence: float,
    font_family: str,
    font_size: int,
    system_order: list[str] | None = None,
    system_labels: dict[str, str] | None = None,
    height_scale: float = 1.0,
) -> str:
    """Build the ABX report: accuracy and count charts plus a binomial table.

    Accuracy is tested against 50% (chance level) rather than "no preference"
    - the same binomtest mechanism as AB's win-rate test, but answering "can
    listeners tell A and B apart?" instead of "which do they prefer?".
    """
    labels = system_labels or {}
    alpha = 1 - confidence

    def _disp(name: str) -> str:
        return labels.get(name, name)

    pair_labels: list[str] = []
    accuracy: list[float] = []
    acc_errors: list[float] = []
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
        acc_errors.append(err)
        hover_text.append(f"Correct: {n_correct}/{n_total} ({rate:.0%})")
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

    acc_html, counts_html = _render_binary_outcome_charts(
        pair_labels,
        accuracy,
        acc_errors,
        hover_text,
        count_labels,
        count_values,
        "Accuracy vs. chance",
        confidence,
        font_family,
        font_size,
        height_scale,
    )
    table_html = _render_pvalue_table_html(
        ["Pair", "p-value (binomial)", f"Significant (α={alpha:.2f})"],
        table_rows,
        font_family,
        font_size,
    )
    stats_html = _render_summary_stats_table_html(df, font_family, font_size)
    return f"{acc_html}{counts_html}{table_html}{stats_html}"
