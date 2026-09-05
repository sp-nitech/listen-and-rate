"""Pre-test duration QA: whether one item's clips agree in length.

This check guards against the wrong file rather than against the systems.
Stimuli are grouped into items on filename alone (see loader.py's
_expand_stimuli_dirs), so a clip that does not hold the utterance its name
claims is paired with the others regardless, and the listener is then asked to
compare two unrelated recordings. Neither of the other checks notices:
loudness looks at level, silence at the two ends, and neither says anything
about what was said.

Length is the cheap way in. Two renderings of one utterance run to about the
same length, so a gap far wider than a speaking-rate difference is the sign
that one of them is a different recording.

The lengths are the ones load_config already read from the audio headers, so
this check opens no files and costs nothing. That, and its independence from
playback level, is why it runs before the other two.
"""

from __future__ import annotations

from .audio_qa import check_per_item, measured_rows, stimuli_under_check
from .config import Config

_UNIT = "s"
_LABEL = "duration"


def run_configured_duration_check(config: Config) -> None:
    """Run the duration check if `duration_check` is configured (else no-op).

    Prints the offending items to stdout (or every item for a verbose
    criterion) and raises SystemExit if the threshold is exceeded.
    """
    check = config.duration_check
    if check is None or check.per_item is None:
        return

    stimuli = stimuli_under_check(config, check.include_reference)
    rows = measured_rows(stimuli, config.durations)
    if check_per_item(
        rows, check.per_item.threshold, check.per_item.verbose, _UNIT, _LABEL
    ):
        raise SystemExit(1)
