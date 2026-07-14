"""Report entry point: read result files, dispatch to the per-test-type report."""

from __future__ import annotations

from html import escape as _escape_html
from pathlib import Path

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

    if "mos" in known_types or not known_types:
        # MOS is also the fallback for legacy files without a recognizable
        # test_type (filtering below then yields the "no rows" error).
        if "test_type" in df.columns:
            df = df[df["test_type"] == "mos"]
        if df.empty:
            raise ValueError("No MOS rows found in the provided result file(s)")
        html = _generate_mos_report(
            df,
            title,
            confidence,
            font_family,
            font_size,
            width,
            system_order,
            system_labels=system_labels,
            height_scale=height_scale,
        )
    elif "dmos" in known_types:
        html = _generate_mos_report(
            df[df["test_type"] == "dmos"],
            title,
            confidence,
            font_family,
            font_size,
            width,
            system_order,
            system_labels=system_labels,
            height_scale=height_scale,
            metric_label="DMOS",
        )
    elif "cmos" in known_types:
        html = _generate_cmos_report(
            df[df["test_type"] == "cmos"],
            title,
            confidence,
            font_family,
            font_size,
            width,
            system_order,
            system_labels=system_labels,
            height_scale=height_scale,
        )
    elif "ab" in known_types:
        html = _generate_ab_report(
            df[df["test_type"] == "ab"],
            title,
            confidence,
            font_family,
            font_size,
            width,
            system_order,
            system_labels=system_labels,
            height_scale=height_scale,
        )
    elif "abx" in known_types:
        html = _generate_abx_report(
            df[df["test_type"] == "abx"],
            title,
            confidence,
            font_family,
            font_size,
            width,
            system_order,
            system_labels=system_labels,
            height_scale=height_scale,
        )
    elif "xab" in known_types:
        html = _generate_ab_report(
            df[df["test_type"] == "xab"],
            title,
            confidence,
            font_family,
            font_size,
            width,
            system_order,
            system_labels=system_labels,
            height_scale=height_scale,
            outcome_column="closer",
            rate_axis_title="Closer-to-reference rate",
            include_tie=False,
        )
    else:  # "mushra"
        html = _generate_mos_report(
            df[df["test_type"] == "mushra"],
            title,
            confidence,
            font_family,
            font_size,
            width,
            system_order,
            system_labels=system_labels,
            height_scale=height_scale,
            metric_label="MUSHRA",
            axis_dtick=10,
            boxplot_range=(0, 100),
            boxplot_dtick=10,
        )
    return _set_html_title(html, title)
