"""Analyze MOS results and generate a standalone Plotly HTML report."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from listen_and_rate.analysis import generate_report_html
from listen_and_rate.analysis._results import (
    ResultVersionMismatch,
    version_difference_note,
)
from listen_and_rate.config import (
    Config,
    ReportConfig,
    load_report_config,
    load_sequence,
)
from listen_and_rate.errors import UserError, exit_on_user_error
from listen_and_rate.storage import METADATA_COLUMN_PREFIX, SURVEY_COLUMN_PREFIX

logger = logging.getLogger(__name__)

# The report's base content width in pixels; report-config scale.width is a
# multiplier on this (scale.height likewise multiplies each chart's height).
BASE_WIDTH = 900


# Said of a results directory, given or derived from a config, that holds none.
_NO_RESULT_FILES = "no result files (.csv or .json) found"


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
        "--results",
        nargs="+",
        metavar="PATH",
        help=(
            "Result CSV/JSON file(s) or a results directory. May be omitted "
            "when --config is given: the directory is then derived from the "
            "config's output.path (the FastAPI deployment's layout)."
        ),
    )
    parser.add_argument(
        "--config",
        nargs="+",
        metavar="PATH",
        help=(
            "Path to the YAML config file used to collect these results. "
            "When given, systems/pairs are shown in stimuli_dirs.systems' "
            "order instead of alphabetically. Without --results it also "
            "locates the results directory. Give a sequence's configs, in "
            "order, to write one report per test next to its own results."
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
            "Requires --config. It cannot be combined with --results or an "
            "absolute output.path."
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help=(
            "Output HTML path (default: report.html next to the results). "
            "Not with several --config, whose reports each go next to their "
            "own results."
        ),
    )
    parser.add_argument(
        "--report-config",
        metavar="PATH",
        help=(
            "Path to a report (figure) YAML controlling presentation: figure "
            "scale (width/height multipliers), font, confidence level, "
            "system display order/labels, and stacked filtered sections "
            "(groups). Optional, and defaults are used when omitted. See "
            "examples/report-config.yaml."
        ),
    )
    args = parser.parse_args()
    with exit_on_user_error():
        _report(parser, args)


def _report(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Write the report(s) main() was asked for, one per config given."""
    report = (
        load_report_config(args.report_config) if args.report_config else ReportConfig()
    )

    # A sequence's configs are loaded together, so a later test's report gets
    # the metadata labels its config shares with the first (see
    # load_sequence) - loading it alone would leave them out.
    configs = load_sequence(args.config) if args.config else []
    if len(configs) > 1:
        if args.results:
            parser.error(
                "--results cannot be combined with several --config: each "
                "test's results are found from its own config"
            )
        if args.output:
            parser.error(
                "--output cannot be combined with several --config: each "
                "test's report is written next to its own results"
            )
    for config in configs or [None]:
        _write_report(parser, args, report, config)


def _write_report(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    report: ReportConfig,
    config: Config | None,
) -> None:
    """Write one report: for `config`'s results, or for --results alone (None)."""
    paths: Sequence[str | Path]
    if args.results:
        if args.root:
            parser.error("--root cannot be combined with --results")
        if len(args.results) == 1 and Path(args.results[0]).is_dir():
            paths = _result_paths_in(Path(args.results[0]))
            if not paths:
                raise UserError(f"{args.results[0]}: {_NO_RESULT_FILES}")
        else:
            # As written, so a file that is not there is named as it was typed.
            paths = list(args.results)
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
            raise UserError(f"{derived_dir}: {_NO_RESULT_FILES}")
    elif args.root:
        parser.error("--root requires --config")
    else:
        parser.error(
            "Pass --results (result files or a results directory), or "
            "--config to derive the directory from the config's output.path"
        )

    # Default the report location to the results' own directory, so both
    # deployment modes work without an explicit --output.
    out_path = (
        Path(args.output) if args.output else Path(paths[0]).parent / "report.html"
    )

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

    # Map each form field's prefixed result column to its human label, so the
    # Participants section reads "Playback device" instead of "device". Only
    # available when --config was given; without it the section falls back to
    # the bare keys.
    form_labels = None
    if config is not None:
        form_labels = {
            METADATA_COLUMN_PREFIX + f.key: f.label for f in config.metadata.fields
        } | {SURVEY_COLUMN_PREFIX + f.key: f.label for f in config.survey.fields}

    try:
        html = _render(paths, report, system_order, require_full_order, form_labels)
    except ResultVersionMismatch:
        # Already says the versions differ, in more detail than the note would.
        raise
    except Exception as exc:
        # Results from another release are a common reason for the analysis to
        # break, and the traceback alone gives no hint of it.
        note = version_difference_note(paths)
        if note:
            exc.add_note(note)
        raise

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    logger.info("Report saved: %s", out_path)


def _render(paths, report, system_order, require_full_order, form_labels) -> str:
    """Build the report HTML from the resolved CLI arguments."""
    return generate_report_html(
        paths,
        confidence=report.confidence,
        font_family=report.font.family,
        font_size=report.font.size,
        width=round(BASE_WIDTH * report.scale.width),
        system_order=system_order,
        system_labels=report.labels,
        bold_system_names=report.bold_system_names,
        height_scale=report.scale.height,
        bar_width_scale=report.scale.bar_width,
        png_scale=report.scale.png,
        require_full_order=require_full_order,
        form_labels=form_labels,
        tie_label=report.tie_label,
        mean_bar_color=report.color.mean_bar,
        count_bar_color=report.color.count_bar,
        groups=(
            [g.model_dump() for g in report.groups]
            if report.groups is not None
            else None
        ),
    )
