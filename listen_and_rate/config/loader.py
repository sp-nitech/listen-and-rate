"""Config discriminated union and the YAML config file loader."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import Field, TypeAdapter, ValidationError

from ._utils import _AUDIO_EXTENSIONS, _duplicates, _normalize, _safe_id
from .ab import ABConfig, build_ab_trials
from .abx import ABXConfig
from .base import StimuliConfig, StimuliDirsConfig, StimulusConfig
from .cmos import CMOSConfig
from .dmos import DMOSConfig, build_dmos_trials
from .errors import format_config_error
from .mos import MOSConfig
from .mushra import MUSHRAConfig, build_mushra_trials
from .xab import XABConfig, build_xab_trials

Config = Annotated[
    MOSConfig
    | DMOSConfig
    | CMOSConfig
    | ABConfig
    | ABXConfig
    | XABConfig
    | MUSHRAConfig,
    Field(discriminator="test_type"),
]


def _expand_stimuli_dirs(dirs_config: StimuliDirsConfig) -> list[StimulusConfig]:
    """Scan each system directory for audio files and return a flat stimulus list.

    Validates that all systems share a common set of utterances (filenames).
    Emits a UserWarning for utterances missing from any system; raises ValueError
    if no common utterances exist at all.
    """
    dir_entries: list[tuple[str, str, list[Path]]] = []
    for entry in dirs_config.systems:
        dir_path_raw = Path(entry.path)
        dir_path = dir_path_raw.resolve()
        if not dir_path.is_dir():
            raise NotADirectoryError(
                f"stimuli_dirs path is not a directory: {dir_path_raw}"
            )
        dir_name = dir_path_raw.name
        audio_files = sorted(
            f
            for f in dir_path.iterdir()
            if f.is_file() and f.suffix.lower() in _AUDIO_EXTENSIONS
        )
        dir_entries.append((dir_name, entry.resolved_system, audio_files))

    systems_seen = [system for _, system, _ in dir_entries]
    duplicate_systems = _duplicates(systems_seen)
    if duplicate_systems:
        raise ValueError(
            f"stimuli_dirs.systems has duplicate system name(s): {duplicate_systems}. "
            "Each entry must resolve to a unique system name (its explicit "
            "'system:' value, or its directory's basename when omitted) - "
            "set 'system:' explicitly on the conflicting entries to disambiguate."
        )

    if len(dir_entries) > 1:
        stems_per_dir: dict[str, set[str]] = {
            dir_name: {f.stem for f in files} for dir_name, _, files in dir_entries
        }
        common = set.intersection(*stems_per_dir.values())
        if not common:
            raise ValueError(
                "No common audio files found across all systems in stimuli_dirs. "
                "Ensure each system directory contains files with matching names."
            )
        all_stems = set.union(*stems_per_dir.values())
        system_specific = all_stems - common
        if system_specific:

            def _missing_in(stem: str) -> str:
                dirs = ", ".join(
                    n for n, stems in stems_per_dir.items() if stem not in stems
                )
                return f"'{stem}' missing in [{dirs}]"

            details = ", ".join(_missing_in(s) for s in sorted(system_specific))
            warnings.warn(
                f"Some utterances are not present in all systems: {details}",
                UserWarning,
                stacklevel=4,
            )

    stimuli: list[StimulusConfig] = []
    for dir_name, system, audio_files in dir_entries:
        for audio_file in audio_files:
            sid = f"{_safe_id(dir_name)}__{_safe_id(audio_file.stem)}"
            stimuli.append(
                StimulusConfig(
                    id=sid,
                    path=str(audio_file),
                    system=system,
                    utterance=audio_file.stem,
                )
            )
    return stimuli


def _check_no_basename_conflicts(items: list[StimulusConfig]) -> None:
    """Reject DISTINCT stimulus files whose paths differ only in extension.

    utt1.wav vs utt1.mp3 in one directory: loudness normalization would fold
    such a pair onto one .wav output file - the later write silently replacing
    the earlier, making both ids serve identical audio - and allowing the pair
    only while normalization is off would make config validity depend on an
    unrelated setting, so it is rejected unconditionally. Referencing the SAME
    file from several stimulus ids stays allowed - a deliberate repeat of one
    clip (e.g. an intra-rater consistency trial), where every id sharing one
    output is the point.
    """
    by_basename: dict[tuple[str, str], set[str]] = {}
    for s in items:
        p = Path(s.path)
        by_basename.setdefault((str(p.parent), p.stem), set()).add(str(p))
    duplicated = {k: paths for k, paths in by_basename.items() if len(paths) > 1}
    if duplicated:
        detail = "; ".join(
            ", ".join(sorted(paths)) for _, paths in sorted(duplicated.items())
        )
        raise ValueError(
            "Stimulus files in the same directory must not share a basename "
            f"(paths differing only in extension): {detail}. Rename the files "
            "so their basenames differ."
        )


def _check_audio_and_measure_durations(
    items: list[StimulusConfig],
) -> dict[str, float]:
    """Validate each stimulus file and return {stimulus_id: duration_seconds}.

    Reads only the audio header (soundfile.info), not the samples, so the cost
    is constant per file regardless of clip length - cheap enough to run
    unconditionally at load time. This catches the common "the file is there
    but isn't really audio" case (a wrong/corrupt file, an HTML error page
    saved under a .wav name, an empty file) before any listener reaches an
    unplayable stimulus and gets stuck on a playback-gated page. A file whose
    header is intact but whose body is truncated still slips through -
    detecting that needs a full decode, left to the opt-in loudness check.

    The header already carries frames/samplerate, so the clip duration falls
    out for free; it is served to the browser (see the config response's
    `durations`) so the player's time bar can show the length immediately,
    without waiting on a per-clip metadata fetch.

    soundfile (a core dependency) is imported here, not at module top, to keep
    importing this package cheap when no config is being loaded - matching
    loudness.py's lazy-import style.
    """
    import soundfile as sf

    durations: dict[str, float] = {}
    for stimulus in items:
        if not Path(stimulus.path).is_file():
            raise FileNotFoundError(f"Audio file not found: {stimulus.path}")
        try:
            info = sf.info(stimulus.path)
        except Exception as exc:
            raise ValueError(
                f"Not a readable audio file: {stimulus.path} ({exc})"
            ) from None
        if info.frames == 0:
            raise ValueError(f"Audio file has no audio samples: {stimulus.path}")
        durations[stimulus.id] = round(info.frames / info.samplerate, 3)
    return durations


def load_config(config_path: str | Path) -> Config:
    """Load and validate a YAML config file; resolve paths relative to CWD."""
    path = Path(config_path).resolve()

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # An empty file parses to None and a top-level list to a list - both
    # would crash the key lookups below with a bare TypeError, so reject
    # them with a message that names the actual problem (and the file).
    if not isinstance(data, dict):
        found = "an empty file" if data is None else f"a {type(data).__name__}"
        raise ValueError(
            f"Config file must be a YAML mapping of config fields, got {found}: {path}"
        )

    # Accept test_type/output.format in any case - "MOS" is commonly written
    # uppercase as an acronym, and a case-mismatch would otherwise surface as
    # a confusing discriminated-union validation error.
    if "test_type" in data:
        data["test_type"] = str(data["test_type"]).lower()
    if isinstance(data.get("output"), dict) and "format" in data["output"]:
        data["output"]["format"] = str(data["output"]["format"]).lower()

    # Normalize paths in stimuli.items[].path
    if isinstance(data.get("stimuli"), dict):
        for item in data["stimuli"].get("items") or []:
            item["path"] = str(_normalize(Path(item["path"])))

    # Normalize paths in stimuli_dirs.systems[].path
    if isinstance(data.get("stimuli_dirs"), dict):
        for entry in data["stimuli_dirs"].get("systems") or []:
            entry["path"] = str(_normalize(Path(entry["path"])))

    config = TypeAdapter(Config).validate_python(data)
    config._experiment_id = path.stem

    if config.stimuli_dirs is not None:
        expanded = _expand_stimuli_dirs(config.stimuli_dirs)
        ids = [s.id for s in expanded]
        if len(ids) != len(set(ids)):
            raise ValueError("stimulus IDs must be unique across stimuli_dirs")
        n = config.stimuli_dirs.utterances_per_session
        if n is not None:
            unique_utterances = {s.utterance for s in expanded if s.utterance}
            if n > len(unique_utterances):
                raise ValueError(
                    f"utterances_per_session ({n}) exceeds the total number of "
                    f"utterances ({len(unique_utterances)})"
                )
        config = config.model_copy(update={"stimuli": StimuliConfig(items=expanded)})

    if config.stimuli is None or not config.stimuli.items:
        raise ValueError(
            "No audio stimuli found; check the paths and that files use a "
            "supported format (.wav, .mp3, .flac, .ogg)."
        )

    _check_no_basename_conflicts(config.stimuli.items)

    if config.stimuli is not None and config.stimuli.stimuli_per_session is not None:
        n = config.stimuli.stimuli_per_session
        total = len(config.stimuli.items)
        if n > total:
            raise ValueError(
                f"stimuli_per_session ({n}) exceeds the total number of "
                f"stimuli ({total})"
            )

    def _check_practice_count(pool_size: int, pool_label: str) -> None:
        """Reject practice.count larger than the pool it is sampled from."""
        n = config.practice.count if config.practice else 0
        if n > pool_size:
            raise ValueError(
                f"practice.count ({n}) exceeds the total number of "
                f"{pool_label} ({pool_size})"
            )

    if isinstance(config, MOSConfig):
        _check_practice_count(
            len(config.stimuli.items) if config.stimuli else 0, "stimuli"
        )

    config._durations = _check_audio_and_measure_durations(
        config.stimuli.items if config.stimuli else []
    )

    if isinstance(config, DMOSConfig):
        dmos_trials = build_dmos_trials(
            config.stimuli.items if config.stimuli else [], config.reference_system
        )
        if not dmos_trials:
            raise ValueError(
                "No utterance is present in both the reference and a test "
                "system; this test type requires at least one paired utterance"
            )
        n = config.stimuli_dirs.utterances_per_session if config.stimuli_dirs else None
        unique_utterances = {t.utterance for t in dmos_trials}
        if n is not None and n > len(unique_utterances):
            raise ValueError(
                f"utterances_per_session ({n}) exceeds the number of paired "
                f"utterances ({len(unique_utterances)})"
            )
        _check_practice_count(len(dmos_trials), "trials")

    if isinstance(config, (CMOSConfig, ABConfig, ABXConfig)):
        trials = build_ab_trials(config.stimuli.items if config.stimuli else [])
        if not trials:
            raise ValueError(
                "No utterance is present in both systems; this test type requires "
                "at least one paired utterance"
            )
        n = config.stimuli_dirs.utterances_per_session if config.stimuli_dirs else None
        if n is not None and n > len(trials):
            raise ValueError(
                f"utterances_per_session ({n}) exceeds the number of paired "
                f"trials ({len(trials)})"
            )
        _check_practice_count(len(trials), "trials")

    if isinstance(config, XABConfig):
        xab_trials = build_xab_trials(
            config.stimuli.items if config.stimuli else [], config.reference_system
        )
        if not xab_trials:
            raise ValueError(
                "No utterance is present in the reference and both test "
                "systems; this test type requires at least one complete "
                "utterance"
            )
        n = config.stimuli_dirs.utterances_per_session if config.stimuli_dirs else None
        if n is not None and n > len(xab_trials):
            raise ValueError(
                f"utterances_per_session ({n}) exceeds the number of complete "
                f"utterances ({len(xab_trials)})"
            )
        _check_practice_count(len(xab_trials), "trials")

    if isinstance(config, MUSHRAConfig):
        rateable_systems = {
            s.resolved_system
            for s in (config.stimuli_dirs.systems if config.stimuli_dirs else [])
            if not s.reference
        }
        mushra_trials = build_mushra_trials(
            config.stimuli.items if config.stimuli else [],
            config.reference_system,
            rateable_systems,
        )
        if not mushra_trials:
            raise ValueError(
                "No utterance has a stimulus for every rateable system; this "
                "test type requires at least one complete utterance"
            )
        n = config.stimuli_dirs.utterances_per_session if config.stimuli_dirs else None
        if n is not None and n > len(mushra_trials):
            raise ValueError(
                f"utterances_per_session ({n}) exceeds the number of complete "
                f"utterances ({len(mushra_trials)})"
            )
        _check_practice_count(len(mushra_trials), "trials")

    return config


def load_config_or_exit(config_path: str | Path) -> Config:
    """load_config, but turn a config-file ValidationError into a clean exit.

    Used at the app/CLI boundaries so an experimenter's config typo prints a
    short, URL-free message (see format_config_error) and exits, instead of a
    stack trace ending in pydantic's errors.pydantic.dev link. load_config
    itself still raises ValidationError, which the test suite relies on.
    """
    try:
        return load_config(config_path)
    except ValidationError as exc:
        raise SystemExit(format_config_error(exc)) from None
