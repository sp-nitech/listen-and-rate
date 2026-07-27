"""Pre-test loudness QA: the configured check (gate) and normalization (fix)."""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .audio_qa import (
    MeasuredRow,
    check_per_item,
    measure_per_stimulus,
    measured_rows,
    per_system_stats,
    print_per_system,
    system_mean_range,
)
from .config import Config
from .config.base import LoudnessCriterion, LoudnessNormalizationConfig, StimulusConfig

_UNIT = "LUFS"  # an absolute level
_DIFFERENCE_UNIT = "LU"  # a distance between two levels
_LABEL = "loudness"

_MIN_DURATION_SECONDS = 1.0


def measure_loudness(path: str | Path) -> float | None:
    """Integrated loudness (LUFS) of an audio file, or None when unmeasurable.

    Clips shorter than 1 second are excluded (BS.1770's gated blocks make short
    clips unreliable), as are silent clips (which give -inf).
    """
    import soundfile as sf

    data, rate = sf.read(str(path))
    if len(data) / rate < _MIN_DURATION_SECONDS:
        return None
    meter = _meter_for(rate)
    loudness = float(meter.integrated_loudness(data))
    return loudness if math.isfinite(loudness) else None


_meters: dict[int, Any] = {}


def _meter_for(rate: int) -> Any:
    """Return a cached pyloudnorm Meter for the sample rate (building isn't free)."""
    import pyloudnorm as pyln

    if rate not in _meters:
        _meters[rate] = pyln.Meter(rate)
    return _meters[rate]


def run_configured_loudness_check(config: Config) -> None:
    """Run the loudness check if `loudness_check` is configured (else no-op).

    Prints loudness figures to stdout when a threshold is exceeded (or when a
    criterion is verbose) and raises SystemExit if any threshold is exceeded.
    """
    check = config.loudness_check
    if check is None:
        return

    stimuli = config.stimuli_list.entries if config.stimuli_list else []
    loudness_by_id = measure_per_stimulus(
        stimuli, measure_loudness, "Measuring loudness"
    )
    rows = measured_rows(stimuli, loudness_by_id)

    excluded = len(stimuli) - len(rows)
    if excluded:
        print(f"[loudness] {excluded} clip(s) excluded (shorter than 1s or silent).")

    failed = False
    if check.per_system is not None:
        failed |= _check_per_system(rows, check.per_system)
    if check.per_item is not None:
        failed |= check_per_item(
            rows,
            check.per_item.threshold,
            check.per_item.verbose,
            _UNIT,
            _LABEL,
            difference_unit=_DIFFERENCE_UNIT,
        )

    if failed:
        raise SystemExit(1)


def _check_per_system(rows: list[MeasuredRow], criterion: LoudnessCriterion) -> bool:
    stats = per_system_stats(rows)
    range_ = system_mean_range(stats)
    exceeded = range_ is not None and range_ > criterion.threshold
    if criterion.verbose or exceeded:
        print_per_system(stats, _UNIT, _LABEL)
    if exceeded:
        print(
            f"[loudness] per_system: mean range {range_:.2f} LU exceeds "
            f"threshold {criterion.threshold:.2f} LU."
        )
    return exceeded


# -- Loudness normalization ----------------------------------------------------


def apply_gain_and_write(
    src: str | Path, dst: str | Path, gain_db: float
) -> str | None:
    """Scale src by gain_db and write it to dst as 16-bit PCM WAV.

    Output is PCM_16 (universally browser-playable) regardless of the source's
    subtype. Clipping is measured on the pre-quantization float peak: if the
    gain pushes it past 0 dBFS, a warning string is returned but the sample is
    still written (per the "warn and continue" policy - normalization does not
    silently move the requested target). Returns None when it fits.
    """
    import numpy as np
    import soundfile as sf

    data, rate = sf.read(str(src))
    scaled = data * (10.0 ** (gain_db / 20.0))
    peak = float(np.max(np.abs(scaled))) if len(scaled) else 0.0
    # A stale dst (e.g. a symlink left by a previous symlink-mode export) must
    # be replaced, not written through - sf.write follows symlinks, which would
    # destroy the original file dst points at. Mirrors _symlink_audio_files'
    # and _copy_audio_files' unlink-before-write guard (src is already read).
    dst = Path(dst)
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    sf.write(str(dst), scaled, rate, subtype="PCM_16")
    if peak > 1.0:
        return f"{src}: peak {20 * math.log10(peak):+.1f} dBFS after gain (clipping)"
    return None


def _normalization_gains(
    stimuli: list[StimulusConfig],
    loudness_by_id: dict[str, float | None],
    norm: LoudnessNormalizationConfig,
) -> tuple[dict[str, float], list[str]]:
    """Compute each stimulus id's gain (dB), plus the ids that couldn't be measured.

    scope="stimulus": each clip gets its own gain to reach target.
    scope="system": one gain per system, derived from that system's mean
    loudness (reusing per_system_stats), so within-system loudness differences
    are preserved. Unmeasurable clips (silent / < 1s) are excluded from
    measurement and listed for reporting; with scope="stimulus" they get gain
    0 (written unchanged), while with scope="system" they still receive their
    system's shared gain - gain 0 would shift their loudness relative to their
    measurable siblings, defeating the one-gain-per-system contract.
    """
    unmeasured = [s.id for s in stimuli if loudness_by_id[s.id] is None]

    # The loudness each clip is shifted toward: for scope="system" it is the
    # clip's system mean (one gain per system, preserving within-system
    # differences); for scope="stimulus" it is the clip's own loudness.
    if norm.scope == "system":
        stats = per_system_stats(measured_rows(stimuli, loudness_by_id))
        system_mean = {system: mean for system, (mean, _std, _n) in stats.items()}
        reference_of = {s.id: system_mean.get(s.system or "") for s in stimuli}
    else:
        reference_of = {s.id: loudness_by_id[s.id] for s in stimuli}

    gains: dict[str, float] = {}
    for s in stimuli:
        reference = reference_of[s.id]
        gains[s.id] = 0.0 if reference is None else norm.target - reference
    return gains, unmeasured


def run_configured_loudness_normalization(
    config: Config, dst_for: Callable[[StimulusConfig], Path]
) -> dict[str, str]:
    """Normalize stimuli per config.loudness_normalization, writing each via dst_for.

    Returns id -> written output path (str); {} (no-op) when
    loudness_normalization is unset. dst_for(stimulus) resolves each output
    path so the caller controls the bundle/cache layout; every output is
    written as WAV (see apply_gain_and_write). Prints a summary of clips that
    couldn't be measured (silent / < 1s, written unchanged) or clipped after
    gain. Does not exit - this is the corrective step, not a QA gate.
    """
    norm = config.loudness_normalization
    if norm is None:
        return {}

    stimuli = config.stimuli_list.entries if config.stimuli_list else []

    # Phase 1: measure every clip's integrated loudness once.
    loudness_by_id = measure_per_stimulus(
        stimuli, measure_loudness, "Normalizing loudness"
    )

    # Phase 2: decide each clip's gain (per-clip, or one gain per system).
    gains, unmeasured = _normalization_gains(stimuli, loudness_by_id, norm)

    # Phase 3: apply the gain and write each output.
    result: dict[str, str] = {}
    clipped: list[str] = []
    for s in stimuli:
        dst = dst_for(s)
        dst.parent.mkdir(parents=True, exist_ok=True)
        warning = apply_gain_and_write(s.path, dst, gains[s.id])
        if warning is not None:
            clipped.append(warning)
        result[s.id] = str(dst)

    if unmeasured:
        # scope="system" still applies the system's shared gain to these clips
        # (see _normalization_gains); only scope="stimulus" leaves them as-is.
        detail = (
            "written unchanged"
            if norm.scope == "stimulus"
            else "their system's shared gain still applies"
        )
        print(
            f"[loudness] normalize: {len(unmeasured)} clip(s) not measurable "
            f"(silent or < 1s); {detail}: {sorted(unmeasured)}"
        )
    if clipped:
        print("[loudness] normalize: clipping after gain:")
        for warning in clipped:
            print(f"  {warning}")
    return result
