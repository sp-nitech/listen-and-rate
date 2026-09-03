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
from typing import Any

from .audio_qa import (
    check_per_item,
    check_per_stimulus,
    measure_per_stimulus,
    measured_rows,
)
from .config import Config, DMOSConfig, MUSHRAConfig, XABConfig
from .config.base import SilenceSideConfig, StimulusConfig

_UNIT = "s"


def measure_silence(
    path: str | Path,
    floor_db: float,
    hysteresis_db: float,
    debounce_ms: float,
    window_ms: float,
    hop_ms: float,
) -> tuple[float, float]:
    """Return one clip's (leading, trailing) silence in seconds.

    The clip is read as a series of short-term RMS readings, and where those
    readings say the audio starts and stops is decided by two guards that a
    bare threshold does not have.

    RMS over a window, rather than the samples themselves: an instantaneous
    sample is a peak reading, so a single click - or the peaks of a noise
    floor sitting 12 dB under its own RMS - would end the silence and report
    almost none for any real recording. `window_ms` is how much audio each
    reading averages, which is what makes it robust, and `hop_ms` is how often
    a reading is taken, which sets the resolution of the answer. They are
    separate so that a finer answer does not have to come from a noisier
    measurement.

    `hysteresis_db` gives the decision an amplitude margin: sound has to reach
    `floor_db + hysteresis_db` to begin, but only has to fall below `floor_db`
    to end. So a quiet ramp into the audio, or the decay of a fricative or a
    room, stays inside the sound rather than being cut off it, while
    low-level noise never starts it.

    `debounce_ms` gives the same decision a margin in time: a stretch over the
    upper threshold has to last that long to count. A lone click or a lip
    smack does not end the silence, and unlike smoothing the readings it does
    that without blurring where the real boundary is.

    Thresholds are absolute (dBFS) rather than relative to this clip's own
    peak, so that clips being compared are judged against the same line - a
    per-clip boundary would move with the recording level and make the
    systems' numbers incomparable. The cost is that they assume the
    recordings fall below `floor_db` when nothing is sounding: room tone
    above it holds the sound open from end to end, every clip reads as 0,
    and the check passes without having looked at anything. Material like
    that needs a higher floor.

    The answer is not biased in one direction. A window straddling the
    boundary is pulled over the threshold by the signal in it, and holding
    the quiet edges inside the sound shortens the reported silence, while
    debouncing a genuinely brief sound lengthens it. Each is bounded by its
    own setting.

    A clip that never reaches the upper threshold, or never holds it for
    `debounce_ms`, is silent throughout. Reporting it as unmeasurable would let
    a broken stimulus past every threshold, so both ends are reported as the
    clip's full length instead, which fails any cap.

    A clip too short to hold an onset that long counts as silent throughout the
    same way, however loud it is: qualifying needs `debounce_ms` / `hop_ms` + 1
    frame readings (see below), and a short enough clip yields fewer. At the
    defaults the cutoff is just over 45 ms, so a 40 ms stimulus of full-scale
    tone still reports 0.04 s of silence at each end and fails any cap.
    """
    import numpy as np

    starts, frame_power, total, rate, window = _frame_power(path, window_ms, hop_ms)
    onset = frame_power > 10.0 ** ((floor_db + hysteresis_db) / 10.0)
    holding = frame_power > 10.0 ** (floor_db / 10.0)

    # An onset only counts once the sound behind it has lasted debounce_ms.
    # A burst lights up every window it touches, so one of length d shows in
    # frames spanning about d + window. Requiring the run to span
    # debounce + window is therefore what requires the sound itself to last
    # debounce, and n frames span (n - 1) * hop + window.
    needed = max(1, int(debounce_ms // max(hop_ms, 1e-9)) + 1)
    if needed > len(onset):
        return total, total
    sustained = np.lib.stride_tricks.sliding_window_view(onset, needed).all(axis=1)
    qualified = np.flatnonzero(sustained)
    if len(qualified) == 0:
        return total, total

    # Hysteresis: from where the sound qualified, take in the quieter frames
    # on either side that are still above the lower threshold.
    first = int(qualified[0])
    while first > 0 and holding[first - 1]:
        first -= 1
    last = int(qualified[-1]) + needed - 1
    while last + 1 < len(holding) and holding[last + 1]:
        last += 1

    leading = float(starts[first]) / rate
    trailing = total - float(starts[last] + window) / rate
    return leading, max(trailing, 0.0)


def _frame_power(
    path: str | Path, window_ms: float, hop_ms: float
) -> tuple[Any, Any, float, int, int]:
    """Read a clip and return (frame starts, frame power, duration, rate, window).

    One reading per window, taking the loudest channel: a clip is not silent
    while any one channel is sounding.
    """
    import numpy as np
    import soundfile as sf

    data, rate = sf.read(str(path))
    samples = np.asarray(data, dtype=np.float64)
    # Squared in place: nobody else holds this array, and a separate one would
    # double the peak memory for what is already the largest thing here.
    np.square(samples, out=samples)
    power = np.max(samples, axis=1) if samples.ndim > 1 else samples

    total = len(power) / rate
    window = max(1, int(round(window_ms / 1000.0 * rate)))
    hop = max(1, int(round(hop_ms / 1000.0 * rate)))
    if len(power) < window:
        # Too short to window: judge the clip as one reading.
        return np.zeros(1, dtype=int), np.array([power.mean()]), total, rate, window

    # Sliced, not indexed with an array: a slice of the strided view is still
    # a view, while indexing copies every window and so allocates window/hop
    # times the clip. Reducing over the view is also faster than a prefix sum
    # at these overlaps (measured: ~10x at the default 25/10 ms, with cumsum
    # only winning past ~30x overlap).
    strided = np.lib.stride_tricks.sliding_window_view(power, window)
    readings = strided[::hop].mean(axis=1)
    starts = np.arange(len(readings)) * hop
    # The grid rarely lands on the end of the file. Without a reading aligned
    # to it, the samples past the last window would be reported as trailing
    # silence - erring long, which is the direction a cap must not err in. One
    # extra reading covers them.
    if starts[-1] != len(strided) - 1:
        readings = np.append(readings, strided[-1].mean())
        starts = np.append(starts, len(strided) - 1)
    return starts, readings, total, rate, window


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

    stimuli = _measured_stimuli(config, check.include_reference)
    measured = measure_per_stimulus(
        stimuli,
        lambda path: measure_silence(
            path,
            check.floor_db,
            check.hysteresis_db,
            check.debounce_ms,
            check.window_ms,
            check.hop_ms,
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


def _measured_stimuli(config: Config, include_reference: bool) -> list[StimulusConfig]:
    """Return the clips this check covers, less the reference when excluded."""
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
