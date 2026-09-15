"""Report entry point: read result files, dispatch to the per-test-type report.

Also implements the optional `groups` sections: the per-test-type generators
return composable body fragments, so this module can stack one labeled,
row-filtered section per group into a single page (see _filter_group_rows).
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from html import escape as _escape_html
from pathlib import Path

from ..errors import UserError
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

# metrics_filter is kept out of _FILTER_KINDS: each metric is matched in its
# own terms (see _METRIC_MATCHERS), so it needs its own dispatch rather than
# another entry in the glob loop.
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


def _participants_section_html(
    df,
    form_labels: dict[str, str] | None = None,
    page_columns: list[str] | None = None,
) -> str:
    """Build the trailing "Participants" section: what the listeners gave.

    One table per form (Metadata / Survey) listing, for every prefixed
    column present in the results, how many SESSIONS gave each response -
    rows are deduplicated by session_id first, since form answers repeat on
    every rating row of a session. A table per recorded metric follows (Dwell
    Time, Browsers); see _metrics_subsection_html. Returns '' when the results
    carry none of these, so reports without them stay unchanged.

    form_labels maps a prefixed column name (e.g. 'survey_trial_count') to
    the field's human label from the config; when present it is shown in the
    Field column instead of the bare key. Columns without a label (or when
    no config was given) fall back to the key, so config-less reports are
    unchanged.

    page_columns is passed through to _metrics_subsection_html.
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
    subsections.append(_metrics_subsection_html(df, page_columns))
    body = "".join(subsections)
    if not body:
        return ""
    return _section_heading_html("Participants") + body


def _metrics_subsection_html(df, page_columns: list[str] | None = None) -> str:
    """Build the Participants tables of the recorded metrics, one per metric.

    Each metric differs in granularity and type (see MetricsConfig), so each
    has a table of its own, built by its entry in _METRIC_TABLES. A metric
    the results do not carry is left out.
    """
    return "".join(
        build(df, page_columns)
        for metric, build in _METRIC_TABLES.items()
        if METRICS_COLUMN_PREFIX + metric in df.columns
    )


def _dwell_time_table_html(df, page_columns: list[str] | None) -> str:
    """Build the "Dwell Time" table: how long each session's test took.

    Each session's readings are added up and the table shows the mean,
    median, min and max of those totals, as m:ss. The median sits beside the
    mean because one listener who left the tab open moves the mean and the
    max a long way.

    The readings are added up per page, not per row. page_columns names the
    columns that identify one page when a page writes several rows each
    carrying its one reading (MUSHRA); None means every row is its own page.

    Blank readings are dropped before adding up. dwell_time is recorded on
    every answered page or on none of a session's pages, so what this leaves
    out is a whole session from a file written before it was turned on - not
    part of a session, which would understate its total. Returns '' when
    there is no reading at all.
    """
    per_page = df.drop_duplicates(page_columns) if page_columns else df
    values = per_page[METRICS_COLUMN_PREFIX + "dwell_time"].apply(_metric_value)
    totals = values[values.notna()].groupby(per_page["session_id"]).sum()
    if totals.empty:
        return ""
    stats = (totals.mean(), totals.median(), totals.min(), totals.max())
    return _table_heading_html("Dwell Time") + _render_table_html(
        ["Mean", "Median", "Min", "Max"], [[_format_duration(s) for s in stats]]
    )


def _format_duration(seconds: float) -> str:
    """Render seconds as m:ss, rounded to the whole second.

    Minutes keep counting past the hour ("75:12") rather than rolling into an
    h:mm:ss form: a listening session that long is rare, and one format for
    every row keeps the column comparable at a glance.
    """
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}:{secs:02d}"


def _browsers_table_html(df, page_columns: list[str] | None) -> str:
    """Build the "Browsers" table: how many sessions each browser took.

    user_agent is stored raw and named here, by ua-parser (the User Agent
    String Parser project's rules), so its name is shown as it gives it -
    "Mobile Safari" apart from "Safari" is worth seeing in a listening test.
    An agent it cannot name counts as "Other". Counted per session, like the
    form answers, since every row of a session carries the same value. A
    blank is left out: it is a request that carried none, or a file from
    before user_agent was turned on. Returns '' when there is no value at all.
    """
    from ua_parser import parse_user_agent

    per_session = df.drop_duplicates("session_id")
    agents = per_session[METRICS_COLUMN_PREFIX + "user_agent"].dropna().astype(str)
    if agents.empty:
        return ""
    names = agents.map(lambda ua: getattr(parse_user_agent(ua), "family", "Other"))
    counts = names.value_counts().sort_index()
    return _table_heading_html("Browsers") + _render_table_html(
        ["Browser", "Sessions"], [[name, str(int(n))] for name, n in counts.items()]
    )


# Each metric's Participants table, in MetricsConfig's column order.
_METRIC_TABLES = {
    "dwell_time": _dwell_time_table_html,
    "user_agent": _browsers_table_html,
}


def _apply_metrics_filter(sub, group: dict, label: str):
    """Drop rows whose recorded metrics do not match the group's filter.

    Each metric is matched in its own terms, by its entry in
    _METRIC_MATCHERS (see MetricsFilter). A metric left unset (None, as the
    report config hands it over) is not filtered on. A row with no reading
    for a metric never matches, matching how a missing column value is
    treated by the glob filters.
    """
    kind, prefix, kind_label = _METRICS_FILTER
    for key, value in (group.get(kind) or {}).items():
        if value is None:
            continue
        column_name = prefix + key
        if column_name not in sub.columns:
            raise UserError(
                f"group {label!r}: {key!r} is not a {kind_label} in the results"
            )
        sub = sub[_METRIC_MATCHERS[key](sub[column_name], value)]
    return sub


def _within_range(column, bounds: dict):
    """Which of column's readings fall within the inclusive {min, max} bounds."""
    values = column.apply(_metric_value)
    matches = values.notna()
    # Inclusive, so a whole-number threshold reads as written: min 1 keeps
    # a trial that took exactly one second.
    if bounds.get("min") is not None:
        matches &= values >= bounds["min"]
    if bounds.get("max") is not None:
        matches &= values <= bounds["max"]
    return matches


def _metric_value(value) -> float:
    """Parse one stored metric reading; NaN when it is blank or not a number.

    NaN rather than None so the column stays a float Series and the bound
    comparisons stay vectorized - and so an unmeasured row is excluded by
    notna(), the way a missing value is in the glob filters.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _matches_glob(column, value: str | list[str]):
    """Which of column's values match the glob pattern, or any of a list.

    fnmatch patterns (a value without metacharacters is an exact match). A
    missing value never matches, and is never handed to fnmatch: it stays a
    float NaN even through astype(str) in pandas 3, which fnmatch rejects.
    """
    from fnmatch import fnmatchcase

    from pandas import notna

    patterns = [value] if isinstance(value, str) else list(value)
    return column.map(
        lambda v: bool(notna(v)) and any(fnmatchcase(str(v), p) for p in patterns)
    )


# How each metric's metrics_filter value is matched (see MetricsFilter).
_METRIC_MATCHERS = {
    "dwell_time": _within_range,
    "user_agent": _matches_glob,
}


def _filter_group_rows(df, group: dict):
    """Return df's rows matching one group's filters.

    metadata/survey/stimuli filter values are glob patterns (see
    _matches_glob), and metrics_filter values are matched per metric (see
    _apply_metrics_filter). Keys and the filter blocks are AND. Raises
    ValueError - always naming the group - for a key whose (prefixed) column
    the results don't carry, or a filter that matches no rows at all.
    """
    label = group["label"]
    sub = _apply_metrics_filter(df, group, label)
    for kind, prefix, kind_label in _FILTER_KINDS:
        for key, value in (group.get(kind) or {}).items():
            column_name = prefix + key
            if column_name not in sub.columns:
                raise UserError(
                    f"group {label!r}: {key!r} is not a {kind_label} in the results"
                )
            sub = sub[_matches_glob(sub[column_name], value)]
    if sub.empty:
        raise UserError(f"group {label!r} matched no rows in the results")
    return sub


def generate_report_html(
    paths: Sequence[str | Path],
    title: str = "Listening Test Results",
    confidence: float = 0.95,
    font_family: str = "sans-serif",
    font_size: int = 13,
    width: int = 900,
    system_order: list[str] | None = None,
    system_labels: dict[str, str] | None = None,
    bold_system_names: bool = False,
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

    When the results carry metadata/survey form answers or recorded metrics,
    a trailing "Participants" section shows the per-session response
    distributions and each metric's session totals (always over the full
    data, regardless of groups).

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
        bold_system_names: Wrap the figures' system names in <b>. Figures
            only - the tables escape their cells (see _render_table_html).
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
    if len(missing) == 1:
        raise UserError(f"{missing[0]}: result file not found")
    if missing:
        raise UserError(f"result files not found: {', '.join(missing)}")

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
        raise UserError(
            f"mixed test_type values in result files: {sorted(test_types_present)}"
        )

    if require_full_order and system_order is not None:
        effective_type = next(iter(known_types)) if known_types else "mos"
        check_df = (
            df[df["test_type"] == effective_type] if "test_type" in df.columns else df
        )
        missing = sorted(_systems_in(check_df) - set(system_order))
        if missing:
            raise UserError(
                f"order is missing system(s) present in the results: {missing}"
            )

    # Resolve the test type to a body renderer once; groups then reuse the
    # same renderer per filtered subset. page_columns identify one trial page
    # when a page writes more than one row (see _participants_section_html).
    page_columns = None
    common = dict(
        confidence=confidence,
        font_family=font_family,
        font_size=font_size,
        system_order=system_order,
        system_labels=system_labels,
        bold_system_names=bold_system_names,
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
            raise UserError("no MOS rows found in the result files")
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
        # One page rates every system of an item at once.
        page_columns = ["session_id", "item"]
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
    # Trailing form-answer distributions and metric totals, always computed on
    # the FULL data (never per group) and rendered at most once; '' without
    # form or metrics columns.
    body += _participants_section_html(typed_df, form_labels, page_columns)
    html = _wrap_report_html(title, body, width)
    return _set_html_title(html, title)
