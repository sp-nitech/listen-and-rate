"""Report entry point: read result files, dispatch to the per-test-type report.

Also implements the optional `groups` sections: the per-test-type generators
return composable body fragments, so this module can stack one labeled,
row-filtered section per group into a single page (see _filter_group_rows).
"""

from __future__ import annotations

from functools import partial
from html import escape as _escape_html
from pathlib import Path

from ..storage import (
    METADATA_COLUMN_PREFIX,
    METRICS_COLUMN_PREFIX,
    SURVEY_COLUMN_PREFIX,
)
from ._render import (
    _TEXT_SIZE,
    _render_table_html,
    _table_heading_html,
    _wrap_report_html,
)
from ._results import _check_tool_versions, _read_result_file, _versions_in
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


# Filter kinds: YAML block name, the column-name prefix its keys resolve
# through, and the label used in error messages. Form answers are stored
# under the metadata_/survey_ prefixes (see storage.py), so each block can
# only ever reach its own namespace - outcome columns (rating/winner/...)
# are unreachable by construction, and a survey key inside metadata_filter
# fails loudly instead of silently matching.
_FILTER_KINDS = (
    ("metadata_filter", METADATA_COLUMN_PREFIX, "metadata field"),
    ("survey_filter", SURVEY_COLUMN_PREFIX, "survey field"),
    ("stimuli_filter", "", "stimulus column"),
)

# metrics_filter is kept out of _FILTER_KINDS: its values are numeric ranges,
# not glob patterns, so it needs its own comparison rather than another entry
# in the loop that applies them.
_METRICS_FILTER = ("metrics_filter", METRICS_COLUMN_PREFIX, "recorded metric")


def _section_heading_html(label: str) -> str:
    """Render a centered section title whose underline hugs the label text.

    Shared by the groups sections and the Participants section (see the
    groups heading rationale in generate_report_html). Uses the fixed HTML
    font, not the chart font.
    """
    style = (
        f"display:inline-block;font-size:{_TEXT_SIZE + 6}px;"
        "margin:0;padding:0 24px 8px;border-bottom:1px solid #bbb"
    )
    return (
        '<div style="text-align:center;margin-top:64px">'
        f'<h2 style="{style}">{_escape_html(label)}</h2></div>'
    )


def _participants_section_html(df, form_labels: dict[str, str] | None = None) -> str:
    """Build the trailing "Participants" section: form-answer distributions.

    One table per form (Metadata / Survey) listing, for every prefixed
    column present in the results, how many SESSIONS gave each response -
    rows are deduplicated by session_id first, since form answers repeat on
    every rating row of a session. Returns '' when the results carry no form
    columns at all, so reports without metadata/survey stay unchanged.

    form_labels maps a prefixed column name (e.g. 'survey_trial_count') to
    the field's human label from the config; when present it is shown in the
    Field column instead of the bare key. Columns without a label (or when
    no config was given) fall back to the key, so config-less reports are
    unchanged.
    """
    labels = form_labels or {}
    per_session = df.drop_duplicates("session_id") if "session_id" in df.columns else df
    subsections = []
    for form_label, prefix in (
        ("Metadata", METADATA_COLUMN_PREFIX),
        ("Survey", SURVEY_COLUMN_PREFIX),
    ):
        columns = [c for c in df.columns if c.startswith(prefix)]
        if not columns:
            continue
        rows = []
        for column in columns:
            field = labels.get(column, column[len(prefix) :])
            counts = per_session[column].dropna().astype(str).value_counts()
            for response, n in counts.sort_index().items():
                rows.append([field, str(response), str(int(n))])
        subsections.append(
            _table_heading_html(form_label)
            + _render_table_html(["Field", "Response", "Sessions"], rows)
        )
    if not subsections:
        return ""
    return _section_heading_html("Participants") + "".join(subsections)


def _apply_metrics_filter(sub, group: dict, label: str):
    """Drop rows whose recorded metrics fall outside the group's ranges.

    Separate from the glob filters because the values are numbers: a duration
    has no useful pattern match, only bounds. A row with no reading for a
    metric never matches, matching how a missing column value is treated
    there.
    """
    kind, prefix, kind_label = _METRICS_FILTER
    for key, bounds in (group.get(kind) or {}).items():
        column_name = prefix + key
        if column_name not in sub.columns:
            raise ValueError(
                f"group {label!r}: {key!r} is not a {kind_label} in the results"
            )
        values = sub[column_name].apply(_metric_value)
        matches = values.notna()
        # Inclusive, so a whole-number threshold reads as written: min 1 keeps
        # a trial that took exactly one second.
        if bounds.get("min") is not None:
            matches &= values >= bounds["min"]
        if bounds.get("max") is not None:
            matches &= values <= bounds["max"]
        sub = sub[matches]
    return sub


def _metric_value(value) -> float:
    """Parse one stored metric reading; NaN when it is blank or not a number.

    NaN rather than None so the column stays a float Series and the bound
    comparisons below stay vectorized - and so an unmeasured row is excluded
    by notna(), the way a missing value is in the glob filters.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _filter_group_rows(df, group: dict):
    """Return df's rows matching one group's metadata/survey/stimuli filters.

    Values are fnmatch glob patterns (a value without metacharacters is an
    exact match); a list of patterns is OR, keys and the filter blocks are
    AND. Rows whose column value is missing never match. Raises ValueError -
    always naming the group - for a key whose (prefixed) column the results
    don't carry, or a filter that matches no rows at all.
    """
    from fnmatch import fnmatchcase

    label = group["label"]
    sub = df
    sub = _apply_metrics_filter(sub, group, label)
    for kind, prefix, kind_label in _FILTER_KINDS:
        for key, value in (group.get(kind) or {}).items():
            patterns = [value] if isinstance(value, str) else list(value)
            column_name = prefix + key
            if column_name not in sub.columns:
                raise ValueError(
                    f"group {label!r}: {key!r} is not a {kind_label} in the results"
                )
            column = sub[column_name]
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
    bar_width_scale: float = 1.0,
    png_scale: float = 2.0,
    require_full_order: bool = False,
    groups: list[dict] | None = None,
    form_labels: dict[str, str] | None = None,
    tie_label: str = "No preference",
    mean_bar_color: str = "#72b7b2",
    count_bar_color: str = "#cd5c5c",
) -> str:
    """Read result file(s) (CSV or JSON), compute statistics, return standalone HTML.

    Dispatches to a MOS or AB report based on the data's test_type column.
    Requires optional 'analyze' dependencies (plotly, scipy, pandas).
    Install with:  uv sync --extra analyze   (or:  make setup-analyze)

    When the results carry metadata/survey form answers, a trailing
    "Participants" section shows their per-session response distributions
    (always over the full data, regardless of groups).

    Args:
        paths: Result CSV/JSON file(s); all rows are combined into one report.
        title: Page title, shown as the heading and the browser-tab title.
        confidence: CI level for every interval and significance test; the
            significance threshold alpha is 1 - confidence.
        font_family: Chart font family (the HTML chrome keeps a fixed font).
        font_size: Chart font size in px (likewise charts only).
        width: Page content width in px, which caps the charts' width
            (tables keep their natural width).
        system_order: Display order of systems/pairs (e.g. the order written
            in the original config's stimuli_dirs); alphabetical when None.
        system_labels: Maps a raw system name to its display name
            (charts/tables only; the stored data keeps its raw names).
        height_scale: Multiplier on every chart's height.
        bar_width_scale: Multiplier on every bar's width within its category
            slot; the gap between bars floors at zero once they fill the
            slot (>= 1.25). Boxplots are unaffected.
        png_scale: Resolution multiplier for the modebar's PNG download
            (every figure); the on-screen display is unaffected.
        require_full_order: When set, system_order must list every system
            present in the results (raises ValueError otherwise).
        groups: When given, stacks one report section per group vertically -
            an <h2> heading (the group's label) followed by the full set of
            charts and tables for the rows selected by its filters (see
            _filter_group_rows; a group without filters covers everything).
            Without groups the report is a single unlabeled section.
        form_labels: Maps a prefixed form column (e.g. 'survey_trial_count')
            to that field's human label from the config, shown in the
            Participants section's Field column in place of the bare key.
        tie_label: Name of the AB count chart's centered tie bar (its
            position is always centered). Ignored by the other test types.
        mean_bar_color: Fill color of the mean/rate bars.
        count_bar_color: Fill color of the raw-count bars.

    Returns:
        The complete report page as a standalone HTML string.

    """
    try:
        import pandas as pd
    except ImportError as exc:
        raise ImportError(
            f"Analysis dependencies not installed ({exc}). Run: make setup-analyze"
        ) from exc

    missing = [str(p) for p in paths if not Path(p).is_file()]
    if missing:
        raise FileNotFoundError(f"Result file(s) not found: {', '.join(missing)}")

    frames = {Path(p): _read_result_file(p) for p in paths}
    _check_tool_versions({p: _versions_in(f) for p, f in frames.items()})
    df = pd.concat(frames.values(), ignore_index=True)

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
        bar_width_scale=bar_width_scale,
        png_scale=png_scale,
        mean_bar_color=mean_bar_color,
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
        render = partial(
            _generate_cmos_report, **common, count_bar_color=count_bar_color
        )
    elif "ab" in known_types:
        typed_df = df[df["test_type"] == "ab"]
        render = partial(
            _generate_ab_report,
            **common,
            count_bar_color=count_bar_color,
            tie_label=tie_label,
        )
    elif "abx" in known_types:
        typed_df = df[df["test_type"] == "abx"]
        render = partial(
            _generate_abx_report, **common, count_bar_color=count_bar_color
        )
    elif "xab" in known_types:
        typed_df = df[df["test_type"] == "xab"]
        render = partial(
            _generate_ab_report,
            **common,
            count_bar_color=count_bar_color,
            outcome_column="closer",
            rate_axis_title="Closer-to-reference rate",
            include_tie=False,
        )
    else:  # "mushra"
        typed_df = df[df["test_type"] == "mushra"]
        render = partial(
            _generate_mos_report,
            **common,
            metric_label="MUSHRA score",
            axis_step=10,
            axis_tickformat=None,  # integer 0-100 scale: "60", not "60.0"
            value_precision=1,  # 0-100 scale: "62.3±5.1", not "62.34±5.12"
            # Padded past the scale's own ends: a whisker cap or a point
            # drawn exactly at 0 or 100 would be half outside the plot area.
            # The MOS/DMOS call above pads its 1-5 scale for the same reason.
            boxplot_range=(-2, 102),
            boxplot_dtick=20,  # 0/20/.../100, matching the MUSHRA slider labels
        )

    if groups is None:
        body = render(typed_df)
    else:
        # Each label reads as a section title: an underline hugging the text
        # (inline-block h2 + border-bottom, so its width follows the label),
        # with sections separated by whitespace alone - no full-width rules.
        body = "".join(
            _section_heading_html(group["label"])
            + render(_filter_group_rows(typed_df, group))
            for group in groups
        )
    # Trailing form-answer distributions, always computed on the FULL data
    # (never per group) and rendered at most once; '' without form columns.
    body += _participants_section_html(typed_df, form_labels)
    html = _wrap_report_html(title, body, width)
    return _set_html_title(html, title)
