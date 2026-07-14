"""Analyze MOS results and generate a standalone Plotly HTML report."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from listen_and_rate.analysis import generate_report_html
from listen_and_rate.config import (
    ReportConfig,
    load_config_or_exit,
    load_report_config_or_exit,
)

logger = logging.getLogger(__name__)

# The report's base content width in pixels; report-config scale.width is a
# multiplier on this (scale.height likewise multiplies each chart's height).
BASE_WIDTH = 900


def _result_paths_in(directory: Path) -> list[Path]:
    """Every CSV/JSON result file in `directory`, in sorted order."""
    return sorted([*directory.glob("*.csv"), *directory.glob("*.json")])


def main() -> None:
    """Generate a Plotly MOS report from result file(s) or a results directory."""
    # Emit INFO-level progress to stderr when run as a real CLI. Under pytest
    # the root logger already has a handler, so this no-ops and the messages
    # are captured (not shown) instead of cluttering test output.
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(
        description="Generate a Plotly MOS report from result file(s) or a directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "results",
        nargs="*",
        help=(
            "Result CSV/JSON file(s) or a results directory. May be omitted "
            "when --config is given: the directory is then derived from the "
            "config's output.path (the FastAPI deployment's layout)."
        ),
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help=(
            "Path to the YAML config file used to collect these results. "
            "When given, systems/pairs are shown in stimuli_dirs.systems' "
            "order instead of alphabetically; with no positional results "
            "argument it also locates the results directory."
        ),
    )
    parser.add_argument(
        "--root",
        metavar="PATH",
        help=(
            "Deployment root to resolve the config's relative output.path "
            "against: results are read from <root>/<output.path>/<config "
            "name>. Point it at the exported PHP bundle's directory, or at "
            "wherever a FastAPI deployment's working directory was copied. "
            "Requires --config; cannot be combined with a positional "
            "results argument or an absolute output.path."
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help="Output HTML path (default: report.html next to the results)",
    )
    parser.add_argument(
        "--report-config",
        metavar="PATH",
        help=(
            "Path to a report (figure) YAML controlling presentation: figure "
            "scale (width/height multipliers), font, confidence level, and "
            "system display order/labels. Optional; defaults are used when "
            "omitted. See examples/report.yaml."
        ),
    )
    args = parser.parse_args()

    report = (
        load_report_config_or_exit(args.report_config)
        if args.report_config
        else ReportConfig()
    )

    config = load_config_or_exit(args.config) if args.config else None

    if args.results:
        if args.root:
            parser.error("--root cannot be combined with a positional results argument")
        if len(args.results) == 1 and Path(args.results[0]).is_dir():
            paths = _result_paths_in(Path(args.results[0]))
            if not paths:
                raise FileNotFoundError(f"No CSV/JSON files found in {args.results[0]}")
        else:
            paths = [Path(p) for p in args.results]
    elif config is not None:
        # Both deployments store results at <deployment root>/<output.path>/
        # <config name> (save.php resolves output.path against its bundle
        # directory). Without --root, the deployment root is the current
        # directory - plain relative-path resolution.
        output_path = Path(config.output.path)
        if args.root:
            if output_path.is_absolute():
                parser.error(
                    "--root cannot be combined with an absolute output.path "
                    f"({config.output.path}): the results' location does not "
                    "depend on a deployment root"
                )
            derived_dir = Path(args.root) / output_path / config.experiment_id
        else:
            derived_dir = output_path / config.experiment_id
        paths = _result_paths_in(derived_dir)
        if not paths:
            raise FileNotFoundError(f"No CSV/JSON files found in {derived_dir}")
    elif args.root:
        parser.error("--root requires --config")
    else:
        parser.error(
            "Pass result files/a results directory, or --config to derive "
            "the directory from the config's output.path"
        )

    # Default the report location to the results' own directory, so both
    # deployment modes work without an explicit --output.
    out_path = Path(args.output) if args.output else paths[0].parent / "report.html"

    # The report config's explicit order wins (and must be complete); otherwise
    # fall back to the experiment config's stimuli_dirs order (tolerant).
    if report.order is not None:
        system_order = report.order
        require_full_order = True
    elif config is not None and config.stimuli_dirs is not None:
        system_order = [entry.resolved_system for entry in config.stimuli_dirs.systems]
        require_full_order = False
    else:
        system_order = None
        require_full_order = False

    html = generate_report_html(
        paths,
        confidence=report.confidence,
        font_family=report.font.family,
        font_size=report.font.size,
        width=round(BASE_WIDTH * report.scale.width),
        system_order=system_order,
        system_labels=report.labels,
        height_scale=report.scale.height,
        require_full_order=require_full_order,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    logger.info("Report saved: %s", out_path)
