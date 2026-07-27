"""Pre-test silence QA: how much nothing each clip starts and ends with.

Leading silence that differs between systems breaks the blinding a listening
test depends on. A listener who notices that one side always starts a beat
later can identify it without hearing it, and from then on the comparison
measures the delay rather than the audio - the same failure the loudness check
exists to prevent. Trailing silence costs the listener time instead: playback
is gated on the clip reaching its end, so a long tail is time every listener
must sit through on every trial.

This module only measures and reports. Nothing here modifies the audio.
"""

from __future__ import annotations

from pathlib import Path

from .audio_qa import (
    check_per_item,
    check_per_stimulus,
    measure_per_stimulus,
    measured_rows,
)
from .config import Config
from .config.base import SilenceSideConfig, StimulusConfig

_UNIT = "s"


def measure_silence(
    path: str | Path,
    floor_db: float,
    window_ms: float,
    hop_ms: float,
) -> tuple[float, float]:
    """Return one clip's (leading, trailing) silence in seconds.

    Silence is a stretch whose short-term RMS stays below `floor_db` dBFS.
    RMS over a window, rather than the samples themselves: an instantaneous
    sample is a peak reading, so a single click - or the peaks of a noise
    floor sitting 12 dB under its own RMS - would end the silence and report
    almost none for any real recording.

    `window_ms` is how much audio each reading averages, which is what makes
    it robust, and `hop_ms` is how often a reading is taken, which sets the
    resolution of the answer. Keeping them separate means a finer answer does
    not have to come from a noisier measurement.

    The boundary is absolute rather than relative to this clip's own peak, so
    that clips being compared are judged against the same line - a per-clip
    boundary would move with the recording level and make the systems'
    numbers incomparable.

    A window straddling the boundary is pulled over the floor by the signal
    in it, so the result errs short rather than long. Callers use it as a cap,
    which makes erring short the conservative direction.

    A clip with no window above the floor is silent throughout. Reporting it
    as unmeasurable would let a broken stimulus past every threshold, so both
    ends are reported as the clip's full length instead, which fails any cap.
    """
    import numpy as np
    import soundfile as sf

    data, rate = sf.read(str(path))
    samples = np.asarray(data, dtype=np.float64)
    # Power per sample, taking the loudest channel: a clip is not silent while
    # any one channel is sounding.
    power = np.max(samples * samples, axis=1) if samples.ndim > 1 else samples * samples

    total = len(power) / rate
    window = max(1, int(round(window_ms / 1000.0 * rate)))
    hop = max(1, int(round(hop_ms / 1000.0 * rate)))
    if len(power) < window:
        # Too short to window: judge the clip as one reading.
        loud = np.array([float(power.mean()) > 10.0 ** (floor_db / 10.0)])
        starts = np.zeros(1, dtype=int)
    else:
        # Sliced, not indexed with an array: a slice of the strided view is
        # still a view, while indexing copies every window and so allocates
        # window/hop times the clip. Reducing over the view is also faster
        # than a prefix sum at these overlaps (measured: ~10x at the default
        # 25/10 ms, with cumsum only winning past ~30x overlap).
        strided = np.lib.stride_tricks.sliding_window_view(power, window)
        threshold = 10.0 ** (floor_db / 10.0)
        loud = strided[::hop].mean(axis=1) > threshold
        starts = np.arange(len(loud)) * hop
        # The grid rarely lands on the end of the file. Without a reading
        # aligned to it, the samples past the last window would be reported as
        # trailing silence - erring long, which is the direction a cap must
        # not err in. One extra reading covers them.
        if starts[-1] != len(strided) - 1:
            loud = np.append(loud, float(strided[-1].mean()) > threshold)
            starts = np.append(starts, len(strided) - 1)

    active = np.flatnonzero(loud)
    if len(active) == 0:
        return total, total
    leading = float(starts[active[0]]) / rate
    trailing = total - float(starts[active[-1]] + window) / rate
    return leading, max(trailing, 0.0)


def run_configured_silence_check(config: Config) -> None:
    """Run the silence check if `silence_check` is configured (else no-op).

    Prints the offending figures to stdout (or every figure for a verbose
    criterion) and raises SystemExit if any threshold is exceeded. Runs after
    the loudness check: the floor is absolute, so silence figures taken from
    clips whose levels disagree may say more about the level difference than
    about the clips.
    """
    check = config.silence_check
    if check is None:
        return

    stimuli = config.stimuli_list.entries if config.stimuli_list else []
    measured = measure_per_stimulus(
        stimuli,
        lambda path: measure_silence(
            path, check.floor_db, check.window_ms, check.hop_ms
        ),
        desc="Measuring silence",
    )

    failed = False
    for side, criteria in (("leading", check.leading), ("trailing", check.trailing)):
        if criteria is None:
            continue
        index = 0 if side == "leading" else 1
        seconds = {stimulus_id: pair[index] for stimulus_id, pair in measured.items()}
        failed |= _check_side(stimuli, seconds, criteria, side)

    if failed:
        raise SystemExit(1)


def _check_side(
    stimuli: list[StimulusConfig],
    seconds: dict[str, float],
    criteria: SilenceSideConfig,
    side: str,
) -> bool:
    """Apply one end's configured criteria, returning whether any exceeded."""
    failed = False
    if criteria.per_stimulus is not None:
        failed |= check_per_stimulus(
            seconds,
            criteria.per_stimulus.threshold,
            criteria.per_stimulus.verbose,
            _UNIT,
            f"{side} silence",
        )
    if criteria.per_item is not None:
        rows = measured_rows(stimuli, seconds)
        failed |= check_per_item(
            rows,
            criteria.per_item.threshold,
            criteria.per_item.verbose,
            _UNIT,
            f"{side} silence",
        )
    return failed
