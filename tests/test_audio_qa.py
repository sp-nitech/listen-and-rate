"""Tests for the shared audio-QA machinery: aggregation and per-clip measuring.

These are the parts the duration, loudness and silence checks are all built
from, so they are tested once here rather than in each check's own module.
"""

from __future__ import annotations

import math
import shutil

import pytest

from listen_and_rate.audio_qa import (
    check_per_item,
    check_per_stimulus,
    measure_per_stimulus,
    per_item_spreads,
    per_system_stats,
    stimuli_under_check,
    system_mean_range,
)
from listen_and_rate.config import load_config

from ._helpers import write_config


def test_per_system_stats_mean_std_count():
    rows = [
        ("A", "u1", -20.0),
        ("A", "u2", -22.0),
        ("B", "u1", -23.0),
        ("B", "u2", -23.0),
    ]
    stats = per_system_stats(rows)
    assert stats["A"] == pytest.approx((-21.0, 1.0, 2))  # mean -21, pstdev 1.0
    assert stats["B"] == pytest.approx((-23.0, 0.0, 2))


def test_system_mean_range_is_max_minus_min_of_means():
    rows = [("A", "u1", -20.0), ("B", "u1", -23.0), ("C", "u1", -21.5)]
    assert system_mean_range(per_system_stats(rows)) == pytest.approx(3.0)


def test_system_mean_range_none_with_fewer_than_two_systems():
    rows = [("A", "u1", -20.0), ("A", "u2", -21.0)]
    assert system_mean_range(per_system_stats(rows)) is None


def test_per_item_spreads_only_multi_system_items():
    rows = [
        ("A", "u1", -20.0),
        ("B", "u1", -23.0),  # u1 present in A and B -> spread 3.0
        ("A", "u2", -20.0),  # u2 only in A -> excluded (no cross-system spread)
    ]
    spreads = per_item_spreads(rows)
    assert set(spreads) == {"u1"}
    spread, by_system = spreads["u1"]
    assert spread == pytest.approx(3.0)
    assert by_system == {"A": -20.0, "B": -23.0}


def test_measure_per_stimulus_reads_each_file_once():
    """Ids sharing one file are measured once, not once per id.

    Several systems may point at the same directory (a deliberate repeat of
    the same clips under two names), which gives distinct ids the same path.
    """
    from listen_and_rate.config.base import StimulusConfig

    calls: list[str] = []

    def _fake_measure(path):
        calls.append(str(path))
        return -20.0

    stimuli = [
        StimulusConfig(id="A__u1", path="/x/u1.wav", system="A", item="u1"),
        StimulusConfig(id="B__u1", path="/x/u1.wav", system="B", item="u1"),
        StimulusConfig(id="A__u2", path="/x/u2.wav", system="A", item="u2"),
    ]
    result = measure_per_stimulus(stimuli, _fake_measure, "t")

    assert sorted(calls) == ["/x/u1.wav", "/x/u2.wav"]
    # Every id still gets its own entry, whatever the file was shared with.
    assert result == {"A__u1": -20.0, "B__u1": -20.0, "A__u2": -20.0}


# -- per_stimulus (the axis the silence check adds) --------------------------


def test_check_per_stimulus_flags_only_the_clips_over_the_threshold(capsys):
    exceeded = check_per_stimulus(
        {"a": 0.1, "b": 0.9}, threshold=0.5, verbose=False, unit="s", label="x"
    )
    out = capsys.readouterr().out
    assert exceeded
    assert "b" in out and "a" not in out.split("threshold")[0]


def test_check_per_stimulus_is_silent_when_every_clip_fits(capsys):
    exceeded = check_per_stimulus(
        {"a": 0.1}, threshold=0.5, verbose=False, unit="s", label="x"
    )
    assert not exceeded
    assert capsys.readouterr().out == ""


def test_check_per_stimulus_verbose_prints_every_clip(capsys):
    check_per_stimulus({"a": 0.1}, threshold=0.5, verbose=True, unit="s", label="x")
    assert "a" in capsys.readouterr().out


def test_check_per_item_states_the_threshold_in_the_difference_unit(capsys):
    # A spread is a difference. For loudness the values are LUFS but their
    # difference is LU, and printing a threshold "in LUFS" would name a level
    # where a distance was meant.
    check_per_item(
        [("A", "i1", -20.0), ("B", "i1", -24.0)],
        threshold=1.0,
        verbose=False,
        unit="LUFS",
        label="loudness",
        difference_unit="LU",
    )
    out = capsys.readouterr().out
    assert "threshold 1.00 LU:" in out
    assert "(LUFS)" in out  # the values themselves are still absolute


def test_check_per_item_reuses_the_unit_when_a_difference_is_the_same_kind(capsys):
    check_per_item(
        [("A", "i1", 0.1), ("B", "i1", 0.9)],
        threshold=0.2,
        verbose=False,
        unit="s",
        label="leading silence",
    )
    assert "threshold 0.20 s:" in capsys.readouterr().out


# -- the threshold boundary --------------------------------------------------


@pytest.mark.parametrize(("low", "high"), [(1.5, 1.6), (1.0, 1.1), (3.2, 3.3)])
def test_check_per_item_does_not_exceed_at_exactly_the_threshold(low, high, capsys):
    """A spread equal to the threshold fits, whatever the binary rounding says.

    Subtracting two decimal values lands a hair either side of the decimal
    answer (1.6 - 1.5 is 0.100000000000000089, 3.3 - 3.2 is
    0.099999999999999645), so a bare `>` calls some of these pairs over the
    threshold and others under it. Every figure is printed to two decimals,
    which leaves the report saying a spread of 0.10 exceeds a threshold of
    0.10 in one item and not in the next.
    """
    exceeded = check_per_item(
        [("A", "i1", low), ("B", "i1", high)],
        threshold=0.1,
        verbose=False,
        unit="s",
        label="duration",
    )
    assert not exceeded
    assert capsys.readouterr().out == ""


def test_check_per_item_still_exceeds_just_past_the_threshold():
    # The tolerance absorbs binary rounding, not a real difference: a spread
    # a millisecond over the threshold is still over it.
    assert check_per_item(
        [("A", "i1", 1.5), ("B", "i1", 1.601)],
        threshold=0.1,
        verbose=False,
        unit="s",
        label="duration",
    )


def test_an_infinite_threshold_reports_but_never_exceeds(capsys):
    """The default threshold: enabled, measured, reported, never failed on.

    It is what a criterion written without a threshold gets, so `verbose`
    alone turns a check into a survey of the figures - which is how an
    experimenter picks a real threshold in the first place.
    """
    assert not check_per_item(
        [("A", "i1", 1.0), ("B", "i1", 99.0)],
        threshold=math.inf,
        verbose=True,
        unit="s",
        label="duration",
    )
    assert "A=1.00" in capsys.readouterr().out

    assert not check_per_stimulus(
        {"a": 99.0}, threshold=math.inf, verbose=False, unit="s", label="x"
    )
    assert capsys.readouterr().out == ""


def test_check_per_stimulus_does_not_exceed_at_exactly_the_threshold(capsys):
    # Same boundary, same reason, on the axis that caps one clip on its own.
    exceeded = check_per_stimulus(
        {"a": 0.3}, threshold=0.3, verbose=False, unit="s", label="x"
    )
    assert not exceeded
    assert capsys.readouterr().out == ""


# -- stimuli_under_check (which clips a check covers) ------------------------


def _dmos_config(tmp_path, test_audio_file, systems=("Ref", "Test")):
    """A DMOS config whose first system is the (disclosed) reference."""
    entries = []
    for i, system in enumerate(systems):
        directory = tmp_path / system
        directory.mkdir()
        shutil.copy(test_audio_file, directory / "i1.wav")
        entry = {"path": str(directory)}
        if i == 0:
            entry["reference"] = True
        else:
            entry["system"] = system
        entries.append(entry)
    return load_config(
        write_config(
            tmp_path,
            {
                "test_type": "dmos",
                "title": "T",
                "instructions": "I",
                "stimuli_dirs": {"systems": entries},
            },
        )
    )


def test_stimuli_under_check_keeps_the_reference_by_default(tmp_path, test_audio_file):
    config = _dmos_config(tmp_path, test_audio_file)
    covered = stimuli_under_check(config, include_reference=True)
    assert {s.system for s in covered} == {"Ref", "Test"}


def test_stimuli_under_check_drops_the_reference_when_excluded(
    tmp_path, test_audio_file
):
    config = _dmos_config(tmp_path, test_audio_file)
    covered = stimuli_under_check(config, include_reference=False)
    assert {s.system for s in covered} == {"Test"}


def test_stimuli_under_check_has_nothing_to_drop_without_a_reference(
    tmp_path, test_audio_file
):
    """A test type with no reference system is unaffected by the flag.

    Only dmos, xab and mushra declare one, so for the rest there is no clip
    the flag could name and every stimulus is covered either way.
    """
    config = load_config(
        write_config(
            tmp_path,
            {
                "test_type": "mos",
                "title": "T",
                "instructions": "I",
                "stimuli_list": {
                    "entries": [{"id": "s001", "path": str(test_audio_file)}]
                },
            },
        )
    )
    assert len(stimuli_under_check(config, include_reference=False)) == 1
