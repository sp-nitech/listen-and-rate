"""Report entry point: read result files, dispatch to the per-test-type report."""

from __future__ import annotations

from functools import partial
from html import escape as _escape_html
from pathlib import Path

from ..config.base import _RESULT_COLUMNS
from ._render import _wrap_report_html
from .ab import _generate_ab_report
from .abx import _generate_abx_report
from .cmos import _generate_cmos_report
from .mos import _generate_mos_report


def _set_html_title(page_html: str, title: str) -> str:
    """Insert a browser-tab <title> - Plotly's fig.to_html() doesn't set one."""
    return page_html.replace("<head>", f"<head><title>{_escape_html(title)}</title>", 1)


def _systems_in(df) -> set[str]:
    """Return the raw system names present in `df` (either schema).

    MOS-family results carry a single `system` column; pair-based results
    (CMOS/AB/ABX/XAB) carry `system_a`/`system_b`. Empty names are ignored.
    """
    if "system" in df.columns:
        return {s for s in df["system"].dropna().astype(str) if s}
    present: set[str] = set()
    for col in ("system_a", "system_b"):
        if col in df.columns:
            present |= {s for s in df[col].dropna().astype(str) if s}
    return present


# _RESULT_COLUMNS (config.base) = columns written by the result savers
# themselves; everything else in a result file is a listener-metadata column.
# metadata_filter may only name the latter, which keeps outcome columns
# (rating/winner/...) structurally unfilterable (filtering results by their
# outcome would be self-serving).


def _filter_group_rows(df, group: dict):
    """Return df's rows matching one group's metadata_filter/stimuli_filter.

    Values are fnmatch glob patterns (a value without metacharacters is an
    exact match); a list of patterns is OR, keys and the two filters are AND.
    Rows whose column value is missing never match. Raises ValueError - always
    naming the group - for a metadata_filter key that isn't a metadata column
    in the results, a stimuli_filter key whose column the result schema
    doesn't carry (e.g. 'system' on pair-based results), or a filter that
    matches no rows at all.
    """
    from fnmatch import fnmatchcase

    label = group["label"]
    sub = df
    for kind in ("metadata_filter", "stimuli_filter"):
        for key, value in (group.get(kind) or {}).items():
            patterns = [value] if isinstance(value, str) else list(value)
            if key not in sub.columns or (
                kind == "metadata_filter" and key in _RESULT_COLUMNS
            ):
                kind_label = (
                    "metadata field" if kind == "metadata_filter" else "stimulus column"
                )
                raise ValueError(
                    f"group {label!r}: {key!r} is not a {kind_label} in the results"
                )
            column = sub[key]
            matches = column.notna() & column.astype(str).map(
                lambda v, pats=patterns: any(fnmatchcase(v, p) for p in pats)
            )
            sub = sub[matches]
    if sub.empty:
        raise ValueError(f"group {label!r} matched no rows in the results")
    return sub


def generate_report_html(
    paths: list[Path],
    title: str = "Listening Test Results",
    confidence: float = 0.95,
    font_family: str = "sans-serif",
    font_size: int = 13,
    width: int = 900,
    system_order: list[str] | None = None,
    system_labels: dict[str, str] | None = None,
    height_scale: float = 1.0,
    require_full_order: bool = False,
    groups: list[dict] | None = None,
) -> str:
    """Read result file(s) (CSV or JSON), compute statistics, return standalone HTML.

    Dispatches to a MOS or AB report based on the data's test_type column.
    Requires optional 'analyze' dependencies (plotly, scipy, pandas).
    Install with:  uv sync --extra analyze   (or:  make setup-analyze)

    system_order, if given, controls the order systems/pairs are displayed
    in (e.g. the order written in the original config's stimuli_dirs) -
    otherwise systems are shown alphabetically. system_labels renames systems
    for display only (data keys stay the raw names). height_scale multiplies
    every chart's height. When require_full_order is set, system_order must
    list every system present in the results (raises ValueError otherwise);
    the significance threshold alpha is 1 - confidence.

    groups, if given, stacks one report section per group vertically - an
    <h2> heading (the group's label) followed by the full set of charts and
    tables for the rows selected by its filters (see _filter_group_rows;
    a group without filters covers everything). Without groups the report
    is a single unlabeled section, as before.
    """
    try:
        import json as _json

        import pandas as pd
    except ImportError as exc:
        raise ImportError(
            f"Analysis dependencies not installed ({exc}). Run: make setup-analyze"
        ) from exc

    def _read(path: Path) -> pd.DataFrame:
        if path.suffix.lower() == ".json":
            with open(path, encoding="utf-8") as f:
                data = _json.load(f)
            rows = []
            for r in data.get("ratings", []):
                row: dict = {
                    "session_id": data.get("session_id", ""),
                    "timestamp": data.get("timestamp", ""),
                    "test_type": data.get("test_type", ""),
                    **r,
                }
                for k, v in data.get("metadata", {}).items():
                    row[k] = v
                rows.append(row)
            return pd.DataFrame(rows)
        return pd.read_csv(path)

    missing = [str(p) for p in paths if not Path(p).is_file()]
    if missing:
        raise FileNotFoundError(f"Result file(s) not found: {', '.join(missing)}")

    df = pd.concat([_read(p) for p in paths], ignore_index=True)

    # Empty system fields (explicit stimuli without system:) come back from
    # read_csv as NaN, which groupby("system") silently drops - every row
    # would vanish from the MOS report. Restore them as the empty string the
    # saver actually wrote.
    if "system" in df.columns:
        df["system"] = df["system"].fillna("")

    test_types_present = set(df["test_type"]) if "test_type" in df.columns else set()
    known_types = test_types_present & {
        "mos",
        "dmos",
        "cmos",
        "ab",
        "abx",
        "xab",
        "mushra",
    }
    if len(known_types) > 1:
        raise ValueError(
            f"Mixed test_type values in result files: {sorted(test_types_present)}"
        )

    if require_full_order and system_order is not None:
        effective_type = next(iter(known_types)) if known_types else "mos"
        check_df = (
            df[df["test_type"] == effective_type] if "test_type" in df.columns else df
        )
        missing = sorted(_systems_in(check_df) - set(system_order))
        if missing:
            raise ValueError(
                f"order is missing system(s) present in the results: {missing}"
            )

    # Resolve the test type to a body renderer once; groups then reuse the
    # same renderer per filtered subset.
    common = dict(
        confidence=confidence,
        font_family=font_family,
        font_size=font_size,
        system_order=system_order,
        system_labels=system_labels,
        height_scale=height_scale,
    )
    if "mos" in known_types or not known_types:
        # MOS is also the fallback for legacy files without a recognizable
        # test_type (filtering below then yields the "no rows" error).
        if "test_type" in df.columns:
            df = df[df["test_type"] == "mos"]
        if df.empty:
            raise ValueError("No MOS rows found in the provided result file(s)")
        typed_df = df
        render = partial(_generate_mos_report, **common)
    elif "dmos" in known_types:
        typed_df = df[df["test_type"] == "dmos"]
        render = partial(_generate_mos_report, **common, metric_label="DMOS")
    elif "cmos" in known_types:
        typed_df = df[df["test_type"] == "cmos"]
        render = partial(_generate_cmos_report, **common)
    elif "ab" in known_types:
        typed_df = df[df["test_type"] == "ab"]
        render = partial(_generate_ab_report, **common)
    elif "abx" in known_types:
        typed_df = df[df["test_type"] == "abx"]
        render = partial(_generate_abx_report, **common)
    elif "xab" in known_types:
        typed_df = df[df["test_type"] == "xab"]
        render = partial(
            _generate_ab_report,
            **common,
            outcome_column="closer",
            rate_axis_title="Closer-to-reference rate",
            include_tie=False,
        )
    else:  # "mushra"
        typed_df = df[df["test_type"] == "mushra"]
        render = partial(
            _generate_mos_report,
            **common,
            metric_label="MUSHRA",
            axis_dtick=10,
            boxplot_range=(0, 100),
            boxplot_dtick=10,
        )

    if groups is None:
        body = render(typed_df)
    else:
        # Each label reads as a section title: an underline hugging the text
        # (inline-block h2 + border-bottom, so its width follows the label),
        # with sections separated by whitespace alone - no full-width rules.
        heading_style = (
            f"display:inline-block;font-size:{font_size + 6}px;"
            "margin:0;padding:0 24px 8px;border-bottom:1px solid #bbb"
        )
        body = "".join(
            '<div style="text-align:center;margin-top:64px">'
            f'<h2 style="{heading_style}">{_escape_html(group["label"])}</h2></div>'
            + render(_filter_group_rows(typed_df, group))
            for group in groups
        )
    html = _wrap_report_html(title, body, font_family, font_size, width)
    return _set_html_title(html, title)
