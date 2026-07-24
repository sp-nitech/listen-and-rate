"""Tests for the loudness check: pure aggregation (no deps) and, gated on the
optional audio libraries, real measurement + the config-driven runner."""

from __future__ import annotations

import math
import sys

import pytest

from listen_and_rate.loudness import (
    per_system_stats,
    per_utterance_spreads,
    system_mean_range,
)

from ._helpers import write_sine

# -- pure aggregation (no soundfile/pyloudnorm needed) ------------------------


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


# -- measurement + runner (require the optional audio libraries) --------------

pytest.importorskip("soundfile")
pytest.importorskip("pyloudnorm")


def test_measure_loudness_excludes_clips_under_one_second(tmp_path):
    from listen_and_rate.loudness import measure_loudness

    short = write_sine(tmp_path / "short.wav", 0.5, 0.5)
    assert measure_loudness(short) is None


def test_measure_loudness_louder_clip_measures_higher(tmp_path):
    from listen_and_rate.loudness import measure_loudness

    quiet = measure_loudness(write_sine(tmp_path / "quiet.wav", 1.5, 0.1))
    loud = measure_loudness(write_sine(tmp_path / "loud.wav", 1.5, 0.8))
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
    write_sine(da / "utt1.wav", 1.5, quiet_amp)
    write_sine(db / "utt1.wav", 1.5, loud_amp)
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
    write_sine(db / "utt1.wav", 1.5, 0.5)
    write_sine(da / "utt1.wav", 1.5, 0.5)
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
    write_sine(da / "utt1.wav", 1.5, 0.5)
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


# -- loudness normalization ----------------------------------------------------


def _config_with_normalize(tmp_path, normalize, amps):
    """Build/load a 2-system MOS config; `amps` = {system: [(utt, amp), ...]}."""
    import yaml

    from listen_and_rate.config import load_config

    systems = []
    for system, utt_amps in amps.items():
        d = tmp_path / system
        d.mkdir()
        for utt, amp in utt_amps:
            write_sine(d / f"{utt}.wav", 1.5, amp)
        systems.append({"path": str(d), "system": system})
    cfg = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "loudness_normalization": normalize,
        "stimuli_dirs": {"systems": systems},
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(cfg))
    return load_config(p)


def test_apply_gain_and_write_warns_on_clipping(tmp_path):
    from listen_and_rate.loudness import apply_gain_and_write

    src = write_sine(tmp_path / "s.wav", 1.5, 0.6)
    clip_warn = apply_gain_and_write(src, tmp_path / "loud.wav", gain_db=12.0)
    assert clip_warn is not None and "clip" in clip_warn.lower()
    assert apply_gain_and_write(src, tmp_path / "soft.wav", gain_db=-6.0) is None


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="creating symlinks needs privileges a Windows runner may lack",
)
def test_apply_gain_and_write_replaces_symlink_dst_without_touching_target(tmp_path):
    """A stale symlink at dst (e.g. left by a previous symlink-mode export)
    must be replaced by a real file - writing through it would destroy the
    original stimulus it points to. Mirrors _symlink_audio_files' own
    unlink-before-write guard."""
    from listen_and_rate.loudness import apply_gain_and_write

    src = write_sine(tmp_path / "src.wav", 1.5, 0.5)
    original_bytes = src.read_bytes()
    dst = tmp_path / "dst.wav"
    dst.symlink_to(src)

    apply_gain_and_write(src, dst, gain_db=-6.0)

    assert src.read_bytes() == original_bytes  # original untouched
    assert not dst.is_symlink() and dst.is_file()  # replaced by a real file


def test_normalize_scope_system_reports_gain_applied_for_short_clips(tmp_path, capsys):
    """scope=system applies the system's shared gain to a short (<1s) clip too
    (gain 0 would break its relative loudness against its siblings), so the
    summary must not claim it was 'written unchanged'."""
    import soundfile as sf

    from listen_and_rate.loudness import run_configured_loudness_normalization

    config = _config_with_normalize(
        tmp_path,
        {"target": -20.0, "scope": "system"},
        {"A": [("long", 0.1)]},
    )
    # Add a short clip to system A after loading via a second config build is
    # awkward; instead write it into the dir and reload.
    write_sine(tmp_path / "A" / "short.wav", 0.5, 0.1)
    from listen_and_rate.config import load_config

    config = load_config(tmp_path / "config.yaml")

    out = tmp_path / "normalized"
    result = run_configured_loudness_normalization(
        config, lambda item: out / f"{item.id}.wav"
    )
    stdout = capsys.readouterr().out
    assert "A__short" in stdout
    assert "written unchanged" not in stdout  # the gain WAS applied

    # And the behavior itself: the short clip received system A's gain.
    orig_peak = float(abs(sf.read(str(tmp_path / "A" / "short.wav"))[0]).max())
    new_peak = float(abs(sf.read(result["A__short"])[0]).max())
    assert new_peak != pytest.approx(orig_peak, abs=0.01)


def test_normalize_scope_stimulus_reports_short_clips_written_unchanged(
    tmp_path, capsys
):
    import soundfile as sf

    from listen_and_rate.config import load_config
    from listen_and_rate.loudness import run_configured_loudness_normalization

    config = _config_with_normalize(
        tmp_path,
        {"target": -20.0, "scope": "stimulus"},
        {"A": [("long", 0.1)]},
    )
    write_sine(tmp_path / "A" / "short.wav", 0.5, 0.1)
    config = load_config(tmp_path / "config.yaml")

    out = tmp_path / "normalized"
    result = run_configured_loudness_normalization(
        config, lambda item: out / f"{item.id}.wav"
    )
    stdout = capsys.readouterr().out
    assert "A__short" in stdout
    assert "written unchanged" in stdout

    # gain 0: amplitude preserved (bytes may differ due to PCM_16 re-encode).
    orig_peak = float(abs(sf.read(str(tmp_path / "A" / "short.wav"))[0]).max())
    new_peak = float(abs(sf.read(result["A__short"])[0]).max())
    assert new_peak == pytest.approx(orig_peak, abs=0.01)


def test_normalize_scope_stimulus_brings_every_clip_to_target(tmp_path):
    from listen_and_rate.loudness import (
        measure_loudness,
        run_configured_loudness_normalization,
    )

    config = _config_with_normalize(
        tmp_path,
        {"target": -20.0, "scope": "stimulus"},
        {"A": [("utt1", 0.1), ("utt2", 0.4)], "B": [("utt1", 0.6), ("utt2", 0.2)]},
    )
    out = tmp_path / "normalized"
    result = run_configured_loudness_normalization(
        config, lambda item: out / f"{item.id}.wav"
    )
    assert len(result) == 4
    for path in result.values():
        assert measure_loudness(path) == pytest.approx(-20.0, abs=0.5)


def test_normalize_scope_system_matches_means_and_preserves_within_system(tmp_path):
    from listen_and_rate.loudness import (
        measure_loudness,
        run_configured_loudness_normalization,
    )

    config = _config_with_normalize(
        tmp_path,
        {"target": -20.0, "scope": "system"},
        {"A": [("utt1", 0.1), ("utt2", 0.6)], "B": [("utt1", 0.3), ("utt2", 0.3)]},
    )
    by_id = {s.id: s for s in config.stimuli.items}
    a_ids = [s.id for s in config.stimuli.items if s.system == "A"]
    orig = {sid: measure_loudness(by_id[sid].path) for sid in a_ids}

    out = tmp_path / "normalized"
    result = run_configured_loudness_normalization(
        config, lambda item: out / f"{item.id}.wav"
    )
    new = {sid: measure_loudness(result[sid]) for sid in a_ids}

    # System A's mean lands on target...
    assert sum(new.values()) / len(new) == pytest.approx(-20.0, abs=0.5)
    # ...but the within-system difference between utterances is preserved
    # (one gain per system, not per clip).
    d_orig = orig[a_ids[0]] - orig[a_ids[1]]
    d_new = new[a_ids[0]] - new[a_ids[1]]
    assert d_new == pytest.approx(d_orig, abs=0.3)
    assert abs(d_orig) > 1.0  # sanity: the two clips really did differ


def test_normalize_noop_returns_empty_when_not_configured(tmp_path):
    import yaml

    from listen_and_rate.config import load_config
    from listen_and_rate.loudness import run_configured_loudness_normalization

    da = tmp_path / "A"
    da.mkdir()
    write_sine(da / "utt1.wav", 1.5, 0.5)
    cfg = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli_dirs": {"systems": [{"path": str(da), "system": "A"}]},
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(cfg))
    assert (
        run_configured_loudness_normalization(load_config(p), lambda item: tmp_path)
        == {}
    )
