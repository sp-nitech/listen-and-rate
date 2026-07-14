"""Pre-test loudness check."""

from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Any

from .config import Config
from .config.base import LoudnessCriterion

# One measured clip: system, utterance, and integrated loudness (LUFS).
LoudnessRow = tuple[str, str, float]

_MIN_DURATION_SECONDS = 1.0


def per_system_stats(rows: list[LoudnessRow]) -> dict[str, tuple[float, float, int]]:
    """Per system, the mean loudness, population std, and clip count."""
    by_system: dict[str, list[float]] = {}
    for system, _utterance, lufs in rows:
        by_system.setdefault(system, []).append(lufs)
    return {
        system: (statistics.fmean(values), statistics.pstdev(values), len(values))
        for system, values in by_system.items()
    }


def system_mean_range(stats: dict[str, tuple[float, float, int]]) -> float | None:
    """Range (max-min) of the per-system means, or None if < 2 systems."""
    means = [mean for mean, _std, _count in stats.values()]
    if len(means) < 2:
        return None
    return max(means) - min(means)


def per_utterance_spreads(
    rows: list[LoudnessRow],
) -> dict[str, tuple[float, dict[str, float]]]:
    """Per utterance in >= 2 systems: cross-system spread (max-min) + each value.

    Utterances present in fewer than two systems have no cross-system spread and
    are omitted.
    """
    by_utterance: dict[str, dict[str, float]] = {}
    for system, utterance, lufs in rows:
        by_utterance.setdefault(utterance, {})[system] = lufs
    spreads: dict[str, tuple[float, dict[str, float]]] = {}
    for utterance, by_system in by_utterance.items():
        if len(by_system) < 2:
            continue
        values = by_system.values()
        spreads[utterance] = (max(values) - min(values), by_system)
    return spreads


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

    from tqdm import tqdm

    items = config.stimuli.items if config.stimuli else []
    rows: list[LoudnessRow] = []
    excluded = 0
    # Progress bar goes to stderr (separate from the stdout report) and, with
    # disable=None, shows only on an interactive terminal - silent in pipes/tests.
    for item in tqdm(items, desc="Measuring loudness", unit="clip", disable=None):
        lufs = measure_loudness(item.path)
        if lufs is None:
            excluded += 1
            continue
        rows.append((item.system or "", item.utterance or item.id, lufs))

    if excluded:
        print(f"[loudness] {excluded} clip(s) excluded (shorter than 1s or silent).")

    failed = False
    if check.per_system is not None:
        failed |= _check_per_system(rows, check.per_system)
    if check.per_stimulus is not None:
        failed |= _check_per_stimulus(rows, check.per_stimulus)

    if failed:
        raise SystemExit(1)


def _check_per_system(rows: list[LoudnessRow], criterion: LoudnessCriterion) -> bool:
    stats = per_system_stats(rows)
    range_ = system_mean_range(stats)
    exceeded = range_ is not None and range_ > criterion.threshold
    if criterion.verbose or exceeded:
        _print_per_system(stats)
    if exceeded:
        print(
            f"[loudness] per_system: mean range {range_:.2f} LU exceeds "
            f"threshold {criterion.threshold:.2f} LU."
        )
    return exceeded


def _check_per_stimulus(rows: list[LoudnessRow], criterion: LoudnessCriterion) -> bool:
    spreads = per_utterance_spreads(rows)
    offenders = {
        u: v for u, (spread, v) in spreads.items() if spread > criterion.threshold
    }
    if criterion.verbose:
        _print_per_stimulus(spreads)
    elif offenders:
        _print_per_stimulus({u: spreads[u] for u in offenders})
    if offenders:
        print(
            f"[loudness] per_stimulus: {len(offenders)} utterance(s) exceed "
            f"threshold {criterion.threshold:.2f} LU: {sorted(offenders)}"
        )
    return bool(offenders)


def _print_per_system(stats: dict[str, tuple[float, float, int]]) -> None:
    # stats preserves the order systems first appear in the stimuli list, i.e.
    # the order they are declared in the config - keep that, don't re-sort.
    print("[loudness] per-system integrated loudness (LUFS):")
    for system, (mean, std, count) in stats.items():
        print(f"  {system}: mean {mean:.2f}  std {std:.2f}  (n={count})")


def _print_per_stimulus(
    spreads: dict[str, tuple[float, dict[str, float]]],
) -> None:
    # Within each utterance, systems keep their config declaration order.
    print("[loudness] per-utterance loudness across systems (LUFS):")
    for utterance in sorted(spreads):
        spread, by_system = spreads[utterance]
        per_sys = "  ".join(f"{s}={lufs:.2f}" for s, lufs in by_system.items())
        print(f"  {utterance}: spread {spread:.2f}  [{per_sys}]")
