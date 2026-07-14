"""Result analysis: per-system statistics and Plotly HTML report generation.

Supports all test types via per-type report generators sharing common
rendering/statistics helpers (see _render):
- MOS/DMOS/MUSHRA (mean + t-interval CI, pairwise t-tests with Bonferroni)
- CMOS (signed mean rating + one-sample t-test)
- AB/XAB (preference/closeness rate + binomial CI and test)
- ABX (discrimination accuracy vs chance + binomial test)

`generate_report_html` reads the result file(s) and dispatches to the right
generator based on each file's test_type.
"""

from __future__ import annotations

from .report import generate_report_html

__all__ = ["generate_report_html"]
