"""Tests for the configured duration check."""

from __future__ import annotations

import pytest

from listen_and_rate.config import load_config
from listen_and_rate.duration import run_configured_duration_check

from ._helpers import write_config, write_sine


def _config(tmp_path, duration_check, seconds_by_system, item="i1"):
    """A MOS config whose systems all render `item`, at the given lengths."""
    entries = []
    for system, seconds in seconds_by_system.items():
        path = write_sine(tmp_path / f"{system}.wav", seconds=seconds)
        entries.append(
            {
                "id": f"{system}__{item}",
                "path": str(path),
                "system": system,
                "item": item,
            }
        )
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "stimuli_list": {"entries": entries},
    }
    if duration_check is not None:
        data["duration_check"] = duration_check
    return load_config(write_config(tmp_path, data))


def _dmos_config(tmp_path, duration_check, seconds_by_system):
    """A DMOS config whose first system is the (disclosed) reference."""
    systems = []
    for i, (system, seconds) in enumerate(seconds_by_system.items()):
        directory = tmp_path / system
        directory.mkdir()
        write_sine(directory / "i1.wav", seconds=seconds)
        entry = {"path": str(directory)}
        if i == 0:
            entry["reference"] = True
        else:
            entry["system"] = system
        systems.append(entry)
    data = {
        "test_type": "dmos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "stimuli_dirs": {"systems": systems},
        "duration_check": duration_check,
    }
    return load_config(write_config(tmp_path, data))


def test_duration_check_passes_when_the_lengths_agree(tmp_path, capsys):
    config = _config(tmp_path, {"per_item": {"threshold": 0.3}}, {"A": 1.5, "B": 1.55})
    run_configured_duration_check(config)  # no SystemExit
    assert capsys.readouterr().out == ""


def test_duration_check_stops_on_a_spread_across_systems(tmp_path, capsys):
    # The point of the check: B is nowhere near A's length, so B's file almost
    # certainly holds a different utterance than the one its name claims.
    config = _config(tmp_path, {"per_item": {"threshold": 0.3}}, {"A": 1.5, "B": 4.1})
    with pytest.raises(SystemExit) as excinfo:
        run_configured_duration_check(config)
    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "i1" in out
    assert "A=1.50" in out and "B=4.10" in out
    assert "[duration] per_item:" in out


def test_duration_check_reports_the_spread_in_seconds(tmp_path, capsys):
    config = _config(tmp_path, {"per_item": {"threshold": 0.3}}, {"A": 1.0, "B": 2.0})
    with pytest.raises(SystemExit):
        run_configured_duration_check(config)
    out = capsys.readouterr().out
    assert "spread 1.00" in out
    assert "threshold 0.30 s" in out


def test_duration_check_verbose_prints_every_item_when_within_threshold(
    tmp_path, capsys
):
    config = _config(
        tmp_path,
        {"per_item": {"threshold": 1.0, "verbose": True}},
        {"A": 1.5, "B": 1.6},
    )
    run_configured_duration_check(config)  # no SystemExit
    out = capsys.readouterr().out
    assert "per-item spread across systems (s)" in out
    assert "A=1.50" in out and "B=1.60" in out


def test_duration_check_without_a_criterion_judges_nothing(tmp_path, capsys):
    config = _config(tmp_path, {}, {"A": 1.5, "B": 4.1})
    run_configured_duration_check(config)  # no SystemExit
    assert capsys.readouterr().out == ""


def test_duration_check_unset_is_a_no_op(tmp_path, capsys):
    config = _config(tmp_path, None, {"A": 1.5, "B": 4.1})
    run_configured_duration_check(config)  # no SystemExit
    assert capsys.readouterr().out == ""


def test_duration_check_ignores_an_item_in_only_one_system(tmp_path, capsys):
    # A spread needs two systems to be a spread; a lone clip has nothing to
    # disagree with, so it cannot be a mix-up this check can see.
    config = _config(tmp_path, {"per_item": {"threshold": 0.3}}, {"A": 1.5})
    run_configured_duration_check(config)  # no SystemExit
    assert capsys.readouterr().out == ""


def test_duration_check_passes_include_reference_through(tmp_path, capsys):
    # What the flag selects is stimuli_under_check's business (covered in
    # tests/test_audio_qa.py); this only pins that the check hands it over.
    # With Ref dropped, i1 is left in one system and has no spread at all.
    config = _dmos_config(
        tmp_path,
        {"include_reference": False, "per_item": {"threshold": 0.3}},
        {"Ref": 4.1, "Test": 1.5},
    )
    run_configured_duration_check(config)  # no SystemExit
    assert capsys.readouterr().out == ""
