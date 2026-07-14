"""Tests for the loudness check: pure aggregation (no deps) and, gated on the
optional audio libraries, real measurement + the config-driven runner."""

from __future__ import annotations

import math

import pytest

from listen_and_rate.loudness import (
    per_system_stats,
    per_utterance_spreads,
    system_mean_range,
)

# ── pure aggregation (no soundfile/pyloudnorm needed) ────────────────────────


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


def test_per_utterance_spreads_only_multi_system_utterances():
    rows = [
        ("A", "u1", -20.0),
        ("B", "u1", -23.0),  # u1 present in A and B -> spread 3.0
        ("A", "u2", -20.0),  # u2 only in A -> excluded (no cross-system spread)
    ]
    spreads = per_utterance_spreads(rows)
    assert set(spreads) == {"u1"}
    spread, by_system = spreads["u1"]
    assert spread == pytest.approx(3.0)
    assert by_system == {"A": -20.0, "B": -23.0}


# ── measurement + runner (require the optional audio libraries) ──────────────

pytest.importorskip("soundfile")
pytest.importorskip("pyloudnorm")


def _write_sine(path, seconds, amplitude, rate=16000, freq=440.0):
    import numpy as np
    import soundfile as sf

    t = np.arange(int(seconds * rate)) / rate
    sf.write(
        str(path), (amplitude * np.sin(2 * np.pi * freq * t)).astype("float32"), rate
    )
    return path


def test_measure_loudness_excludes_clips_under_one_second(tmp_path):
    from listen_and_rate.loudness import measure_loudness

    short = _write_sine(tmp_path / "short.wav", 0.5, 0.5)
    assert measure_loudness(short) is None


def test_measure_loudness_louder_clip_measures_higher(tmp_path):
    from listen_and_rate.loudness import measure_loudness

    quiet = measure_loudness(_write_sine(tmp_path / "quiet.wav", 1.5, 0.1))
    loud = measure_loudness(_write_sine(tmp_path / "loud.wav", 1.5, 0.8))
    assert quiet is not None and loud is not None
    assert math.isfinite(quiet) and math.isfinite(loud)
    assert loud > quiet


def _config_with_two_systems(
    tmp_path, monkeypatch, loudness_check, quiet_amp, loud_amp
):
    """Build a 2-system MOS config (system A quiet, B loud) and load it."""
    import yaml

    from listen_and_rate.config import load_config

    da, db = tmp_path / "A", tmp_path / "B"
    da.mkdir()
    db.mkdir()
    _write_sine(da / "utt1.wav", 1.5, quiet_amp)
    _write_sine(db / "utt1.wav", 1.5, loud_amp)
    cfg = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "loudness_check": loudness_check,
        "stimuli_dirs": {
            "systems": [
                {"path": str(da), "system": "A"},
                {"path": str(db), "system": "B"},
            ]
        },
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(cfg))
    return load_config(p)


def test_runner_exits_when_threshold_exceeded(tmp_path, capsys):
    from listen_and_rate.loudness import run_configured_loudness_check

    config = _config_with_two_systems(
        tmp_path, None, {"per_system": {"threshold": 0.5}}, quiet_amp=0.05, loud_amp=0.8
    )
    with pytest.raises(SystemExit):
        run_configured_loudness_check(config)
    out = capsys.readouterr().out
    assert "A" in out and "B" in out  # both systems' loudness printed


def test_runner_verbose_prints_without_exit_when_within_threshold(tmp_path, capsys):
    from listen_and_rate.loudness import run_configured_loudness_check

    # Same amplitude -> systems matched; large threshold so no failure.
    config = _config_with_two_systems(
        tmp_path,
        None,
        {"per_system": {"threshold": 5.0, "verbose": True}},
        quiet_amp=0.5,
        loud_amp=0.5,
    )
    run_configured_loudness_check(config)  # no SystemExit
    assert "A" in capsys.readouterr().out


def test_runner_silent_within_threshold_without_verbose(tmp_path, capsys):
    from listen_and_rate.loudness import run_configured_loudness_check

    config = _config_with_two_systems(
        tmp_path,
        None,
        {"per_system": {"threshold": 5.0, "verbose": False}},
        quiet_amp=0.5,
        loud_amp=0.5,
    )
    run_configured_loudness_check(config)
    assert capsys.readouterr().out == ""


def test_per_system_output_follows_config_order_not_alphabetical(tmp_path, capsys):
    """Systems declared B then A must print in that (config) order, not sorted."""
    import yaml

    from listen_and_rate.config import load_config
    from listen_and_rate.loudness import run_configured_loudness_check

    db, da = tmp_path / "B", tmp_path / "A"
    db.mkdir()
    da.mkdir()
    _write_sine(db / "utt1.wav", 1.5, 0.5)
    _write_sine(da / "utt1.wav", 1.5, 0.5)
    cfg = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "loudness_check": {"per_system": {"threshold": 100.0, "verbose": True}},
        "stimuli_dirs": {
            "systems": [
                {"path": str(db), "system": "B"},
                {"path": str(da), "system": "A"},
            ]
        },
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(cfg))
    run_configured_loudness_check(load_config(p))
    out = capsys.readouterr().out
    assert out.index("  B:") < out.index("  A:")


def test_runner_noop_when_not_configured(tmp_path, capsys):
    import yaml

    from listen_and_rate.config import load_config
    from listen_and_rate.loudness import run_configured_loudness_check

    da = tmp_path / "A"
    da.mkdir()
    _write_sine(da / "utt1.wav", 1.5, 0.5)
    cfg = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli_dirs": {"systems": [{"path": str(da), "system": "A"}]},
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(cfg))
    run_configured_loudness_check(load_config(p))
    assert capsys.readouterr().out == ""
