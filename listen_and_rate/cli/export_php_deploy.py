"""Generate a PHP static-deployment bundle from a YAML config file."""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import shutil
import textwrap
from pathlib import Path

from listen_and_rate.config import (
    ABXConfig,
    DMOSConfig,
    MUSHRAConfig,
    StimulusConfig,
    XABConfig,
    load_config_or_exit,
)
from listen_and_rate.loudness import run_configured_loudness_check

logger = logging.getLogger(__name__)

# frontend/ lives at the repo root; this file is
# listen_and_rate/cli/export_php_deploy.py.
_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
_STATIC_ASSETS = [
    "index.html",
    "css",
    "js",
    "save.php",
    "config.php",
    "x_token.php",
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
    # World-writable so save.php (running as the web server user) can create
    # per-experiment subdirectories, matching save.php's own mkdir(...,0777,...).
    results_dir.chmod(0o777)
    content = textwrap.dedent(r"""\
    # Block direct web access to raw per-listener rating data (.csv/.json), but
    # allow everything else (e.g. report.html) so a generated report can live
    # alongside the raw files it summarizes. Raw files are downloaded via SSH/SCP.

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


def _clear_outdir_except_results(outdir: Path, results_subpath: Path | None) -> None:
    """Remove everything in outdir except the results directory.

    Everything else (index.html, css/, js/, save.php, config.php,
    config_data.php, stimulus_map.php, symlinked audio) is fully reproducible
    from the YAML config and frontend source, so it's always safe to
    regenerate. The results directory (output.path resolved inside the
    bundle) holds collected listener data, which is not reproducible, so it
    is preserved unconditionally regardless of --overwrite. With an
    output.path outside the bundle (results_subpath None) nothing inside
    the bundle holds data, so everything is cleared.
    """
    preserve = results_subpath.parts[0] if results_subpath is not None else None
    for entry in outdir.iterdir():
        if preserve is not None and entry.name == preserve:
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


def _symlink_audio_files(
    outdir: Path, all_items: list[StimulusConfig], audio_urls: dict[str, str]
) -> None:
    """Symlink each stimulus's audio file into outdir at its audio_url path.

    Avoids copying (potentially large) audio files into the deploy bundle.
    Targets are resolved to absolute paths, so the symlinks keep working even
    if outdir itself is later moved elsewhere (only the original source files
    must stay put). Uploading the bundle to a remote host still requires
    transferring the audio files there too (e.g. `scp -r`/`rsync -L` to
    follow the links).
    """
    for s in all_items:
        dst = outdir / audio_urls[s.id]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_symlink() or dst.exists():
            dst.unlink()
        dst.symlink_to(Path(s.path).resolve())


def _copy_audio_files(
    outdir: Path, all_items: list[StimulusConfig], audio_urls: dict[str, str]
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
    for s in all_items:
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
        items = ", ".join(
            f"'{_php_string(str(k))}' => {_php_value(v)}" for k, v in value.items()
        )
        return f"[{items}]"
    if isinstance(value, (list, tuple)):
        items = ", ".join(_php_value(v) for v in value)
        return f"[{items}]"
    raise TypeError(f"Cannot render {value!r} as a PHP value")


def _render_stimulus_map_php(items: list[StimulusConfig]) -> str:
    """Render a PHP file returning id -> {system, utterance} for save.php.

    This is deliberately kept out of config_data.php (read by config.php to
    build the browser-facing response) so listeners cannot see which system a
    stimulus belongs to before rating it. Requesting this .php file directly
    over HTTP executes it without producing output, so it is safe to place in
    the web root.
    """
    lines = ["<?php", "", "return ["]
    for s in items:
        lines.append(
            f"    '{_php_string(s.id)}' => "
            f"['system' => '{_php_string(s.system or '')}', "
            f"'utterance' => '{_php_string(s.utterance or '')}'],"
        )
    lines.append("];")
    lines.append("")
    return "\n".join(lines)


def _render_config_data_php(data: dict) -> str:
    """Render the static experiment definition as a PHP file for config.php.

    config.php includes this at request time to build the browser-facing
    response, re-sampling stimuli_per_session/utterances_per_session and
    randomize fresh on every request (see frontend/config.php).
    """
    return f"<?php\n\nreturn {_php_value(data)};\n"


def main() -> None:
    """Load YAML config, resolve stimuli, and write a full PHP deployment bundle.

    Copies the static frontend assets (index.html, css/, js/, save.php,
    config.php) into --outdir, then writes config_data.php and
    stimulus_map.php there too, so --outdir ends up as a self-contained bundle
    ready to upload as-is. config_data.php holds the raw experiment
    definition (including stimuli_per_session/utterances_per_session); it is
    read by config.php, which re-applies per-session sampling and randomize
    on every request rather than baking in one fixed subset, and withholds
    'system' from its response to keep listeners blind to the underlying
    system under test. stimulus_map.php carries that mapping for save.php.
    """
    # Emit INFO-level progress to stderr when run as a real CLI. Under pytest
    # the root logger already has a handler, so this no-ops and the messages
    # are captured (not shown) instead of cluttering test output.
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(
        description="Generate a PHP static-deployment bundle from a YAML config file.",
    )
    parser.add_argument(
        "--config", required=True, metavar="PATH", help="Path to the YAML config file"
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
            "Regenerate --outdir if it already exists (default: false, to avoid "
            "clobbering the wrong directory by accident). results/ is always "
            "preserved regardless of this flag, since collected listener data "
            "can't be regenerated."
        ),
    )
    parser.add_argument(
        "--copy-audio",
        action="store_true",
        default=False,
        help=(
            "Hard-copy audio files into the bundle instead of symlinking them "
            "(default: symlink). Use this when the bundle is uploaded by a plain "
            "FTP client or shipped as a zip, since symlinks don't survive either; "
            "it makes the bundle self-contained at the cost of a larger size."
        ),
    )
    args = parser.parse_args()

    config = load_config_or_exit(args.config)
    run_configured_loudness_check(config)
    if config.stimuli is None:
        raise RuntimeError("config.stimuli is None after loading")

    all_items = config.stimuli.items
    audio_urls = {s.id: _audio_url(Path(s.path)) for s in all_items}
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
            "utterance": s.utterance,
            "audio_url": audio_urls[s.id],
            # Not sensitive (unlike 'system') - it's the same distinction
            # already visible to the listener as the "Reference"/"Test" label.
            "reference": reference_system is not None and s.system == reference_system,
            # Also disclosed (per MUSHRA's design): the anchor slider is
            # always shown last and labeled "Anchor" to the listener.
            "anchor": anchor_system is not None and s.system == anchor_system,
        }
        for s in all_items
    ]

    practice = config.practice

    config_data = {
        "experiment_id": Path(args.config).stem,
        "test_type": config.test_type,
        "title": config.title,
        "instructions": config.instructions,
        "randomize": config.randomize,
        "preload_audio": config.preload_audio,
        "output_format": config.output.format,
        # save.php resolves this against the bundle directory when relative
        # (see its resolve_results_dir()), mirroring the FastAPI deployment's
        # use of output.path - both layouts are <deployment root>/<output.path>.
        "output_path": config.output.path,
        "metadata": [f.model_dump() for f in config.metadata],
        "shortcuts": config.shortcuts.browser_dict(),
        "rating_labels": getattr(config, "rating_labels", None),
        # Server-side only (never echoed to the browser response) - used by
        # config.php to identify the reference stimulus in each utterance
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
        "stimuli_per_session": (
            config.stimuli.stimuli_per_session if config.stimuli else None
        ),
        # Practice stage - config.php re-samples practice_count pages
        # (stimuli for MOS, trials otherwise) from the full pool on every
        # request, independently of the session sampling above.
        "practice_count": (practice.count if practice else 0),
        "practice_instructions": (practice.instructions if practice else None),
        "utterances_per_session": (
            config.stimuli_dirs.utterances_per_session if config.stimuli_dirs else None
        ),
        "stimuli": stimuli,
    }

    outdir = Path(args.outdir)
    results_subpath = _bundle_results_subpath(config.output.path)
    if outdir.exists():
        if not args.overwrite:
            raise FileExistsError(
                f"{outdir} already exists. "
                f"Pass --overwrite to regenerate it, or remove it manually."
            )
        _clear_outdir_except_results(outdir, results_subpath)
    outdir.mkdir(parents=True, exist_ok=True)
    _copy_static_assets(outdir)
    _seed_results_dir(outdir, results_subpath)
    if args.copy_audio:
        _copy_audio_files(outdir, all_items, audio_urls)
    else:
        _symlink_audio_files(outdir, all_items, audio_urls)

    config_data_path = outdir / "config_data.php"
    config_data_path.write_text(_render_config_data_php(config_data), encoding="utf-8")

    stimulus_map_path = outdir / "stimulus_map.php"
    stimulus_map_path.write_text(_render_stimulus_map_php(all_items), encoding="utf-8")

    logger.info(
        "Copy `%s` to your public_html or www directory to deploy the experiment",
        outdir,
    )
