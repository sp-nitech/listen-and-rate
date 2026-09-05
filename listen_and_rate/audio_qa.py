"""Shared machinery for the pre-test audio checks (duration, loudness, silence).

Each check puts one number against each clip and then judges it on the axes of
the system x item grid whose cells are the stimuli. Nothing here knows what the
number means, so the aggregation, the threshold comparison and the printed
report are written once and the unit is passed in: `loudness.py` reads them as
LUFS, `silence.py` and `duration.py` as seconds.

`stimuli_under_check` is the exception to that indifference. Which clips a
check covers depends on whether the test type has a reference system, so it
knows the config types that declare one - the one place here that does.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TypeVar

from .config import Config, DMOSConfig, MUSHRAConfig, XABConfig
from .config.base import StimulusConfig

# What one measurement yields per clip: a float for loudness, a (leading,
# trailing) pair for silence. This module never looks inside it.
_Measured = TypeVar("_Measured")

# One measured clip: system, item, and the measured value.
MeasuredRow = tuple[str, str, float]

# How far past a threshold a figure must sit to count as over it. Both checks
# subtract or compare decimal quantities, and binary floats land a hair either
# side of the decimal answer: 1.6 - 1.5 is 0.100000000000000089 while 3.3 - 3.2
# is 0.099999999999999645. A bare `>` therefore calls one of those spreads over
# a threshold of 0.1 and the other under it, and since every figure is printed
# to two decimals the report reads as "0.10 exceeds 0.10" for one item and not
# the next. This sits far below the resolution of anything measured here -
# durations are rounded to a millisecond - so it only ever absorbs that noise.
_TOLERANCE = 1e-9


def per_system_stats(rows: list[MeasuredRow]) -> dict[str, tuple[float, float, int]]:
    """Per system, the mean value, population std, and clip count."""
    by_system: dict[str, list[float]] = {}
    for system, _item, value in rows:
        by_system.setdefault(system, []).append(value)
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


def per_item_spreads(
    rows: list[MeasuredRow],
) -> dict[str, tuple[float, dict[str, float]]]:
    """Per item in >= 2 systems: cross-system spread (max-min) + each value.

    Items present in fewer than two systems have no cross-system spread and
    are omitted.
    """
    by_item: dict[str, dict[str, float]] = {}
    for system, item, value in rows:
        by_item.setdefault(item, {})[system] = value
    spreads: dict[str, tuple[float, dict[str, float]]] = {}
    for item, by_system in by_item.items():
        if len(by_system) < 2:
            continue
        values = by_system.values()
        spreads[item] = (max(values) - min(values), by_system)
    return spreads


def stimuli_under_check(
    config: Config, include_reference: bool
) -> list[StimulusConfig]:
    """Return the clips a check covers, less the reference when excluded."""
    stimuli = config.stimuli_list.entries if config.stimuli_list else []
    if include_reference:
        return stimuli
    # Only these test types have one, and only when a system is flagged.
    reference = (
        config.reference_system
        if isinstance(config, (DMOSConfig, XABConfig, MUSHRAConfig))
        else None
    )
    if not reference:
        return stimuli
    return [s for s in stimuli if s.system != reference]


def measure_per_stimulus(
    stimuli: list[StimulusConfig],
    measure: Callable[[str | Path], _Measured],
    desc: str,
) -> dict[str, _Measured]:
    """Measure each stimulus once, keyed by id.

    The progress bar goes to stderr (separate from the stdout report) and,
    with disable=None, shows only on an interactive terminal - silent in
    pipes/tests.

    Measured per FILE, reported per id: several systems may be backed by the
    same directory, which gives distinct ids an identical path, and decoding
    one clip several times would only produce the same number again.
    """
    from tqdm import tqdm

    by_path: dict[str, _Measured] = {}
    for s in tqdm(stimuli, desc=desc, unit="clip", disable=None):
        if s.path not in by_path:
            by_path[s.path] = measure(s.path)
    return {s.id: by_path[s.path] for s in stimuli}


def measured_rows(
    stimuli: list[StimulusConfig], value_by_id: Mapping[str, float | None]
) -> list[MeasuredRow]:
    """Build the (system, item, value) rows of the measurable stimuli, in order."""
    return [
        (s.system or "", s.item or s.id, value)
        for s in stimuli
        if (value := value_by_id[s.id]) is not None
    ]


def check_per_item(
    rows: list[MeasuredRow],
    threshold: float,
    verbose: bool,
    unit: str,
    label: str,
    difference_unit: str | None = None,
) -> bool:
    """Compare each item's cross-system spread against `threshold`.

    Returns whether any item exceeded. Prints the offending items (or every
    item when verbose).

    `difference_unit` names the unit a spread is measured in, when that
    differs from the unit of the values themselves: loudness values are LUFS
    but the distance between two of them is LU. It defaults to `unit`, which
    is right wherever a difference is the same kind of quantity as the value,
    as seconds of silence are.
    """
    spread_unit = difference_unit if difference_unit is not None else unit
    spreads = per_item_spreads(rows)
    offenders = {
        item: by_system
        for item, (spread, by_system) in spreads.items()
        if spread > threshold + _TOLERANCE
    }
    if verbose:
        _print_per_item(spreads, unit, label)
    elif offenders:
        _print_per_item({item: spreads[item] for item in offenders}, unit, label)
    if offenders:
        print(
            f"[{label}] per_item: {len(offenders)} item(s) exceed "
            f"threshold {threshold:.2f} {spread_unit}: {sorted(offenders)}"
        )
    return bool(offenders)


def check_per_stimulus(
    value_by_id: Mapping[str, float],
    threshold: float,
    verbose: bool,
    unit: str,
    label: str,
) -> bool:
    """Compare each clip's own value against `threshold`.

    Unlike the grid axes, this judges a clip on its own rather than against
    its neighbours, which is what an absolute cap needs.
    """
    offenders = {
        stimulus_id: value
        for stimulus_id, value in value_by_id.items()
        if value > threshold + _TOLERANCE
    }
    if verbose:
        _print_per_stimulus(value_by_id, unit, label)
    elif offenders:
        _print_per_stimulus(offenders, unit, label)
    if offenders:
        print(
            f"[{label}] per_stimulus: {len(offenders)} clip(s) exceed "
            f"threshold {threshold:.2f} {unit}: {sorted(offenders)}"
        )
    return bool(offenders)


def print_per_system(
    stats: dict[str, tuple[float, float, int]], unit: str, label: str
) -> None:
    """Print each system's mean, std and count."""
    # stats preserves the order systems first appear in the stimuli list, i.e.
    # the order they are declared in the config - keep that, don't re-sort.
    print(f"[{label}] per-system mean ({unit}):")
    for system, (mean, std, count) in stats.items():
        print(f"  {system}: mean {mean:.2f}  std {std:.2f}  (n={count})")


def _print_per_item(
    spreads: dict[str, tuple[float, dict[str, float]]], unit: str, label: str
) -> None:
    # Within each item, systems keep their config declaration order.
    print(f"[{label}] per-item spread across systems ({unit}):")
    for item in sorted(spreads):
        spread, by_system = spreads[item]
        per_sys = "  ".join(f"{s}={value:.2f}" for s, value in by_system.items())
        print(f"  {item}: spread {spread:.2f}  [{per_sys}]")


def _print_per_stimulus(
    value_by_id: Mapping[str, float], unit: str, label: str
) -> None:
    print(f"[{label}] per-stimulus ({unit}):")
    for stimulus_id in sorted(value_by_id):
        print(f"  {stimulus_id}: {value_by_id[stimulus_id]:.2f}")
