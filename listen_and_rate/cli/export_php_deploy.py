"""Generate a PHP static-deployment bundle from a YAML config file."""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import shutil
import textwrap
from collections.abc import Collection
from pathlib import Path

from listen_and_rate import __version__
from listen_and_rate.config import (
    ABXConfig,
    Config,
    DMOSConfig,
    MUSHRAConfig,
    StimulusConfig,
    XABConfig,
    load_sequence_or_exit,
)
from listen_and_rate.duration import run_configured_duration_check
from listen_and_rate.loudness import (
    run_configured_loudness_check,
    run_configured_loudness_normalization,
)
from listen_and_rate.silence import run_configured_silence_check

logger = logging.getLogger(__name__)

# frontend/ lives at the repo root; this file is
# listen_and_rate/cli/export_php_deploy.py.
_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
# Written by every export and by nothing else - the first by a lone config's,
# the second by a sequence's - so either marks a directory as one this tool
# produced. See _clear_outdir_except_results.
_BUNDLE_MARKERS = ("config_data.php", "sequence.php")

_STATIC_ASSETS = [
    "index.html",
    "css",
    "js",
    "save.php",
    "config.php",
    "x_token.php",
    "stage.php",
    "audio_x.php",
]


def _copy_static_assets(outdir: Path) -> None:
    """Copy the static frontend assets (index.html, css/, js/, save.php) into outdir."""
    for name in _STATIC_ASSETS:
        src = _FRONTEND_DIR / name
        dst = outdir / name
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


def _bundle_results_subpath(output_path: str) -> Path | None:
    """Return output.path's bundle-relative results directory, or None if outside.

    Mirrors save.php's resolve_results_dir(): a relative output.path lives
    inside the bundle (the default './results/' is the results/ subdirectory).
    An absolute path - or one escaping the bundle via '..' - points outside
    it, so there is nothing to seed or preserve within the bundle (save.php
    creates the directory at request time on the server instead).
    """
    p = Path(output_path)
    if p.is_absolute():
        return None
    normalized = Path(os.path.normpath(p))
    if normalized.parts and normalized.parts[0] == "..":
        return None
    return normalized


def _seed_results_dir(outdir: Path, results_subpath: Path | None) -> None:
    """Create the bundle's results directory and seed it with .htaccess.

    The .htaccess blocks direct web access to raw .csv/.json rating files
    while still allowing e.g. a generated report.html to live alongside
    them, and is put in place before any session has been saved. A results
    location outside the bundle (results_subpath None) is left alone.
    """
    if results_subpath is None:
        return
    results_dir = outdir / results_subpath
    results_dir.mkdir(parents=True, exist_ok=True)
    # World-writable so save.php (running as the web server user) can
    # create per-experiment subdirectories, matching save.php's own
    # mkdir(...,0777,...).
    results_dir.chmod(0o777)
    content = textwrap.dedent(r"""\
    # Block direct web access to raw per-listener rating data (.csv/.json),
    # but allow everything else (e.g. report.html) so a generated report can
    # live alongside the raw files it summarizes. Raw files are downloaded via
    # SSH/SCP.

    <IfModule mod_authz_core.c>
        <FilesMatch "\.(csv|json)$">
            Require all denied
        </FilesMatch>
    </IfModule>

    <IfModule !mod_authz_core.c>
        <FilesMatch "\.(csv|json)$">
            Deny from all
        </FilesMatch>
    </IfModule>

    # Don't let visitors browse the experiment/session file listing either.
    Options -Indexes
    """)
    with open(results_dir / ".htaccess", "w", encoding="utf-8") as f:
        f.write(content)


def _assert_not_the_frontend_source(outdir: Path) -> None:
    """Refuse an --outdir at or inside this package's own frontend directory.

    The bundle's static assets are copied out of _FRONTEND_DIR, so exporting
    into it would delete the very files the next step reads - leaving neither
    a working bundle nor the source it was built from.
    """
    resolved = outdir.resolve()
    frontend = _FRONTEND_DIR.resolve()
    if resolved == frontend or frontend in resolved.parents:
        raise ValueError(
            f"Refusing to export into {outdir}: that is the frontend source "
            f"directory this bundle is built from ({frontend}). Choose a "
            "separate output directory."
        )


def _clear_outdir_except_results(
    outdir: Path, results_subpaths: Collection[Path | None]
) -> None:
    """Remove everything in outdir except the results directories.

    Everything else (index.html, css/, js/, save.php, config.php,
    config_data.php, stimulus_map.php, symlinked audio) is fully reproducible
    from the YAML config and frontend source, so it's always safe to
    regenerate. A results directory (an output.path resolved inside the
    bundle - one per config, see _bundle_results_subpath) holds collected
    listener data, which is not reproducible, so it is preserved
    unconditionally regardless of --overwrite. An output.path outside the
    bundle (a None subpath) holds no data inside it, so preserves nothing.

    Two shapes are refused rather than cleared, because in both this function
    cannot tell reproducible files from collected data:

    - a non-empty directory with none of _BUNDLE_MARKERS in it was not
      written by this tool, so a mistyped --outdir (a public_html serving
      other things, say) would have everything but results/ deleted out of it;
    - results at the bundle root (output.path resolving to '.') puts the
      collected data in the same directory as everything regenerated, so
      "clear all but the results" has no meaning.
    """
    inside = [p for p in results_subpaths if p is not None]
    for results_subpath in inside:
        if not results_subpath.parts:
            raise ValueError(
                f"output.path ({results_subpath}) puts the results at the bundle "
                "root, so regenerating the bundle cannot preserve them. Use a "
                "subdirectory (the default is './results/'), or an absolute "
                "path outside the bundle."
            )
    entries = list(outdir.iterdir())
    if entries and not any((outdir / m).exists() for m in _BUNDLE_MARKERS):
        raise FileExistsError(
            f"{outdir} is not empty and does not look like a bundle this tool "
            f"wrote (none of {', '.join(_BUNDLE_MARKERS)} is in it), so "
            "--overwrite will not clear it. Point --outdir at a new or "
            "previously exported directory, or empty this one yourself."
        )
    preserve = {p.parts[0] for p in inside}
    for entry in entries:
        if entry.name in preserve:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def _audio_url(audio_path: Path) -> str:
    """Return a web-relative URL for an audio file.

    Raises ValueError if the path is outside the current working directory,
    because such paths cannot be expressed as web-relative URLs.
    """
    cwd = Path.cwd()
    try:
        return str(audio_path.relative_to(cwd))
    except ValueError:
        raise ValueError(
            f"Audio path is outside the working directory and cannot be exported:\n"
            f"  {audio_path}\n"
            f"Move the file inside the project directory or use a symlink."
        ) from None


def _symlinks_supported(outdir: Path) -> bool:
    """Return whether symlinks can be created inside outdir.

    Windows without Developer Mode (and some filesystems) raise OSError from
    symlink creation; probe it once so the export can fall back to copying
    rather than crashing halfway through.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    probe = outdir / ".lar-symlink-probe"
    probe.unlink(missing_ok=True)
    try:
        probe.symlink_to(outdir)
    except OSError:
        return False
    probe.unlink()
    return True


def _symlink_audio_files(
    outdir: Path, all_stimuli: list[StimulusConfig], audio_urls: dict[str, str]
) -> None:
    """Symlink each stimulus's audio file into outdir at its audio_url path.

    Avoids copying (potentially large) audio files into the deploy bundle.
    Targets are resolved to absolute paths, so the symlinks keep working even
    if outdir itself is later moved elsewhere (only the original source files
    must stay put). Uploading the bundle to a remote host still requires
    transferring the audio files there too (e.g. `scp -r`/`rsync -L` to
    follow the links).

    Where symlinks are unavailable (e.g. Windows without Developer Mode), falls
    back to copying the audio in (like --copy-audio) with a warning, since a
    half-symlinked bundle would be worse than a fully self-contained one.
    """
    if not _symlinks_supported(outdir):
        logger.warning(
            "Symlinks are not supported here (e.g. Windows without Developer "
            "Mode). Copying audio into the bundle instead. Pass --copy-audio "
            "to make this the explicit, intended behavior."
        )
        _copy_audio_files(outdir, all_stimuli, audio_urls)
        return
    for s in all_stimuli:
        dst = outdir / audio_urls[s.id]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_symlink() or dst.exists():
            dst.unlink()
        dst.symlink_to(Path(s.path).resolve())


def _copy_audio_files(
    outdir: Path, all_stimuli: list[StimulusConfig], audio_urls: dict[str, str]
) -> None:
    """Hard-copy each stimulus's audio file into outdir at its audio_url path.

    The opt-in (`--copy-audio`) alternative to _symlink_audio_files: it makes
    the bundle fully self-contained, so its audio survives being uploaded by a
    plain FTP client (which doesn't dereference symlinks) or zipped and
    unzipped on another host - at the cost of duplicating (potentially large)
    audio into the bundle. shutil.copy2 follows the source if it is itself a
    symlink, so the result is always a real file. The source is resolved to an
    absolute path, matching _symlink_audio_files' target resolution.
    """
    for s in all_stimuli:
        dst = outdir / audio_urls[s.id]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_symlink() or dst.exists():
            dst.unlink()
        shutil.copy2(Path(s.path).resolve(), dst)


def _php_string(s: str) -> str:
    """Escape a string for embedding in a single-quoted PHP string literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _php_value(value: object) -> str:
    """Render a Python value as a PHP literal (recursively for list/dict)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return f"'{_php_string(value)}'"
    if isinstance(value, dict):
        parts = ", ".join(
            f"'{_php_string(str(k))}' => {_php_value(v)}" for k, v in value.items()
        )
        return f"[{parts}]"
    if isinstance(value, (list, tuple)):
        parts = ", ".join(_php_value(v) for v in value)
        return f"[{parts}]"
    raise TypeError(f"Cannot render {value!r} as a PHP value")


def _render_stimulus_map_php(stimuli: list[StimulusConfig]) -> str:
    """Render a PHP file returning id -> {system, item} for save.php.

    This is deliberately kept out of config_data.php (read by config.php to
    build the browser-facing response) so listeners cannot see which system a
    stimulus belongs to before rating it. Requesting this .php file directly
    over HTTP executes it without producing output, so it is safe to place in
    the web root.
    """
    lines = ["<?php", "", "return ["]
    for s in stimuli:
        lines.append(
            f"    '{_php_string(s.id)}' => "
            f"['system' => '{_php_string(s.system or '')}', "
            f"'item' => '{_php_string(s.item or '')}'],"
        )
    lines.append("];")
    lines.append("")
    return "\n".join(lines)


def _render_config_data_php(data: dict) -> str:
    """Render the static experiment definition as a PHP file for config.php.

    config.php includes this at request time to build the browser-facing
    response, re-sampling stimuli_per_session/items_per_session and
    re-applying presentation_order fresh on every request (see
    frontend/config.php).
    """
    return f"<?php\n\nreturn {_php_value(data)};\n"


def _render_sequence_php(stage_ids: list[str]) -> str:
    """Render a sequence bundle's stage ids, in order, for stage.php.

    Its presence is what makes a bundle a sequence: stage.php then serves
    each request from stages/<id>/ of the stage it names.
    """
    return f"<?php\n\nreturn {_php_value(stage_ids)};\n"


def _build_config_data(
    config: Config,
    all_stimuli: list[StimulusConfig],
    audio_urls: dict[str, str],
) -> dict:
    """Assemble the static experiment definition written to config_data.php.

    Everything config.php needs to rebuild the browser-facing response on each
    request (re-applying per-session sampling and presentation_order), plus the
    server-side only fields (reference_system, x_secret, ...) that must never
    reach the browser - see each field's comment.
    """
    reference_system = (
        config.reference_system
        if isinstance(config, (DMOSConfig, XABConfig, MUSHRAConfig))
        and config.reference_system
        else None
    )
    anchor_system = config.anchor_system if isinstance(config, MUSHRAConfig) else None
    stimuli = [
        {
            "id": s.id,
            "label": s.label,
            "item": s.item,
            "audio_url": audio_urls[s.id],
            # Not sensitive (unlike 'system') - it's the same distinction
            # already visible to the listener as the "Reference"/"Test" label.
            "reference": reference_system is not None and s.system == reference_system,
            # Also disclosed (per MUSHRA's design): the anchor slider is
            # always shown last and labeled "Anchor" to the listener.
            "anchor": anchor_system is not None and s.system == anchor_system,
        }
        for s in all_stimuli
    ]

    practice = config.practice

    return {
        "experiment_id": config.experiment_id,
        "ui_language": config.ui_language,
        # Which per-answer measurements save.php should keep; mirrors the
        # FastAPI config response (see _test_config_response).
        "metrics": config.metrics.model_dump(),
        # How long an interrupted session may be resumed for, in browser
        # milliseconds; mirrors the FastAPI config response. Converted here
        # rather than in config.php because the hours only ever exist in the
        # YAML, which the PHP host never sees.
        "resume": {"max_age_ms": config.resume.max_age_ms},
        "test_type": config.test_type,
        "title": config.title,
        "instructions": config.instructions,
        "presentation_order": config.presentation_order,
        "audio_preload": config.audio_preload,
        # {stimulus_id: seconds}, baked in at export time (config.php has no
        # soundfile) so the browser can show clip length without a metadata
        # fetch. See _shared.py's _test_config_response.
        "durations": config.durations,
        "output_format": config.output.format,
        # save.php resolves this against the bundle directory when
        # relative (see its resolve_results_dir()), mirroring the FastAPI
        # deployment's use of output.path - both layouts are <deployment
        # root>/<output.path>.
        "output_path": config.output.path,
        # One {title, description, fields} block per form, the same shape as
        # the YAML and the FastAPI response - one shape across every layer.
        "metadata": {
            "title": config.metadata.title,
            "description": config.metadata.description,
            "fields": [f.model_dump() for f in config.metadata.fields],
        },
        "survey": {
            "title": config.survey.title,
            "description": config.survey.description,
            "fields": [f.model_dump() for f in config.survey.fields],
        },
        "shortcuts": config.shortcuts.browser_dict(),
        "rating_labels": getattr(config, "rating_labels", None),
        # Server-side only (never echoed to the browser response) - used by
        # config.php to identify the reference stimulus in each item
        # group via stimulus_map.php, the same way save.php already looks up
        # 'system' there without exposing it to the client.
        "reference_system": reference_system,
        # Also server-side only: config.php's group_mushra_trials() needs to
        # know how many rateable (non-reference) systems make up one
        # complete trial, since its public 'stimuli' list withholds 'system'
        # names (a stimulus's 'reference'/'anchor' flags are the only system
        # identity it carries) and so can't derive this count on its own.
        "mushra_rateable_system_count": (
            len(
                {
                    s.resolved_system
                    for s in (
                        config.stimuli_dirs.systems if config.stimuli_dirs else []
                    )
                    if not s.reference
                }
            )
            if isinstance(config, MUSHRAConfig)
            else None
        ),
        "allow_tie": getattr(config, "allow_tie", None),
        # Stable per-deployment secret for blinding ABX's hidden "X" reference
        # (see listen_and_rate/x_token.py); generated once at export time
        # so it stays the same across every request to this deployment.
        "x_secret": secrets.token_hex(32) if isinstance(config, ABXConfig) else None,
        # Stamped into every result file save.php writes. PHP cannot read the
        # Python package's version at request time, and the version that
        # exported this bundle is the one whose behaviour produced the
        # results, since the PHP files themselves came from it.
        "tool_version": __version__,
        "stimuli_per_session": (
            config.stimuli_list.stimuli_per_session if config.stimuli_list else None
        ),
        # Practice stage - config.php re-samples practice_count pages
        # (stimuli for MOS, trials otherwise) from the full pool on every
        # request, independently of the session sampling above.
        "practice_count": (practice.count if practice else 0),
        "practice_instructions": (practice.instructions if practice else None),
        "items_per_session": (
            config.stimuli_dirs.items_per_session if config.stimuli_dirs else None
        ),
        "stimuli": stimuli,
    }


def _stage_audio_urls(config: Config, stage_subdir: Path) -> dict[str, str]:
    """Return each stimulus's bundle-relative audio URL, under stage_subdir.

    The URL mirrors the file's path relative to the working directory, so
    distinct files never share one. Normalized audio is always written out as
    WAV (see apply_gain_and_write), so its URL carries a .wav suffix even when
    the source was e.g. .mp3. The rewrite cannot collide two stimuli onto one
    output path: load_config already rejects stimuli whose paths differ only
    in extension.
    """
    if config.stimuli_list is None:
        raise RuntimeError("config.stimuli_list is None after loading")
    normalize = config.loudness_normalization is not None
    urls = {}
    for s in config.stimuli_list.entries:
        url = Path(_audio_url(Path(s.path)))
        urls[s.id] = str(stage_subdir / (url.with_suffix(".wav") if normalize else url))
    return urls


def _write_stage(
    outdir: Path,
    stage_subdir: Path,
    config: Config,
    audio_urls: dict[str, str],
    copy_audio: bool,
) -> None:
    """Write one config's audio, config_data.php, and stimulus_map.php.

    The two PHP files go in outdir/stage_subdir, where stage.php looks for
    them; the audio goes at its bundle-relative audio_url.
    """
    all_stimuli = config.stimuli_list.entries if config.stimuli_list else []
    if config.loudness_normalization is not None:
        # Normalization always writes real (loudness-adjusted) audio into the
        # bundle, so it supersedes the symlink/--copy-audio choice.
        run_configured_loudness_normalization(
            config, lambda s: outdir / audio_urls[s.id]
        )
    elif copy_audio:
        _copy_audio_files(outdir, all_stimuli, audio_urls)
    else:
        _symlink_audio_files(outdir, all_stimuli, audio_urls)

    stage_dir = outdir / stage_subdir
    stage_dir.mkdir(parents=True, exist_ok=True)
    # config.experiment_id, not the filename: load_config already resolved
    # one from the other, and recomputing it here would ignore an explicit
    # `experiment_id:` and send the bundle to a different results directory
    # than the FastAPI server uses.
    config_data = _build_config_data(config, all_stimuli, audio_urls)
    (stage_dir / "config_data.php").write_text(
        _render_config_data_php(config_data), encoding="utf-8"
    )
    (stage_dir / "stimulus_map.php").write_text(
        _render_stimulus_map_php(all_stimuli), encoding="utf-8"
    )


def main() -> None:
    """Load YAML config, resolve stimuli, and write a full PHP deployment bundle.

    Copies the static frontend assets (index.html, css/, js/, save.php,
    config.php) into --outdir, then writes config_data.php and
    stimulus_map.php there too, so --outdir ends up as a self-contained bundle
    ready to upload as-is. config_data.php holds the raw experiment
    definition (including stimuli_per_session/items_per_session); it is
    read by config.php, which re-applies per-session sampling and
    presentation_order on every request rather than baking in one fixed
    subset, and withholds
    'system' from its response to keep listeners blind to the underlying
    system under test. stimulus_map.php carries that mapping for save.php.

    Given several configs, writes a sequence instead: one copy of the page
    and scripts, sequence.php listing the stages (the configs' experiment_ids,
    in the order given), and each stage's config_data.php, stimulus_map.php,
    and audio under stages/<experiment_id>/ (see frontend/stage.php). Results
    stay under the bundle root either way, so re-exporting one shape as the
    other keeps what was collected.
    """
    # Emit INFO-level progress to stderr when run as a real CLI. Under pytest
    # the root logger already has a handler, so this no-ops and the messages
    # are captured (not shown) instead of cluttering test output.
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(
        description="Generate a PHP static-deployment bundle from a YAML config file.",
    )
    parser.add_argument(
        "--config",
        required=True,
        nargs="+",
        metavar="PATH",
        help=(
            "Path to the YAML config file. Give several to export a sequence: "
            "the tests run back to back from one link, in the order given."
        ),
    )
    parser.add_argument(
        "--outdir",
        required=True,
        metavar="DIR",
        help="Directory to write the deployment bundle into.",
    )
    parser.add_argument(
        "--overwrite",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Regenerate --outdir if it already exists (default: false). The results "
            "directory within the bundle is always preserved regardless of this flag "
            "to avoid losing collected listener data."
        ),
    )
    parser.add_argument(
        "--copy-audio",
        action="store_true",
        default=False,
        help=(
            "Hard-copy audio files into the bundle instead of symlinking them "
            "(default: symlink). Use this when the bundle is uploaded by a plain "
            "FTP client or shipped as a zip, since symlinks don't survive "
            "either. It makes the bundle self-contained at a larger size."
        ),
    )
    args = parser.parse_args()

    configs = load_sequence_or_exit(args.config)
    for config in configs:
        run_configured_duration_check(config)
        run_configured_loudness_check(config)
        run_configured_silence_check(config)
    # A lone config's files sit at the bundle root, as they always have; each
    # stage of a sequence gets its own directory (see frontend/stage.php).
    is_sequence = len(configs) > 1
    stage_subdirs = [
        Path("stages", c.experiment_id) if is_sequence else Path() for c in configs
    ]
    # Resolved before outdir is touched: an audio file outside the working
    # directory fails here, leaving an existing bundle as it was.
    audio_urls = [
        _stage_audio_urls(c, sub) for c, sub in zip(configs, stage_subdirs, strict=True)
    ]

    outdir = Path(args.outdir)
    _assert_not_the_frontend_source(outdir)
    results_subpaths = {_bundle_results_subpath(c.output.path) for c in configs}
    if outdir.exists():
        if not args.overwrite:
            raise FileExistsError(
                f"{outdir} already exists. "
                f"Pass --overwrite to regenerate it, or remove it manually."
            )
        _clear_outdir_except_results(outdir, results_subpaths)
    outdir.mkdir(parents=True, exist_ok=True)
    _copy_static_assets(outdir)
    # Before any stage: sequence.php is also what marks the directory as a
    # bundle (_BUNDLE_MARKERS), so a stage that fails to write - a broken
    # file, Ctrl-C - leaves a bundle a rerun with --overwrite can still clear.
    if is_sequence:
        (outdir / "sequence.php").write_text(
            _render_sequence_php([c.experiment_id for c in configs]),
            encoding="utf-8",
        )
    for results_subpath in results_subpaths:
        _seed_results_dir(outdir, results_subpath)
    for config, sub, urls in zip(configs, stage_subdirs, audio_urls, strict=True):
        _write_stage(outdir, sub, config, urls, args.copy_audio)

    logger.info(
        "Copy `%s` to your public_html or www directory to deploy the experiment",
        outdir,
    )
