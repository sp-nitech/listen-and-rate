"""Tests for the silence check: measurement, then the config-driven runner."""

from __future__ import annotations

import pytest

from ._helpers import write_config, write_sine

pytest.importorskip("soundfile")
pytest.importorskip("numpy")

from listen_and_rate.config import load_config  # noqa: E402
from listen_and_rate.silence import (  # noqa: E402
    measure_silence,
    run_configured_silence_check,
)


def write_padded_sine(path, lead=0.0, trail=0.0, tone=1.0, rate=16000, amplitude=0.3):
    """Write a sine surrounded by exact amounts of digital silence."""
    import numpy as np
    import soundfile as sf

    t = np.arange(int(tone * rate)) / rate
    body = amplitude * np.sin(2 * np.pi * 440.0 * t)
    data = np.concatenate(
        [np.zeros(int(lead * rate)), body, np.zeros(int(trail * rate))]
    ).astype("float32")
    sf.write(str(path), data, rate)
    return path


# -- measurement -------------------------------------------------------------


def test_measure_silence_finds_the_padding_on_both_ends(tmp_path):
    # Within one window of the truth, and never over it: the window holding
    # the boundary counts as signal (see measure_silence).
    window = 0.02
    path = write_padded_sine(tmp_path / "a.wav", lead=0.5, trail=0.25)
    leading, trailing = measure_silence(
        path,
        floor_db=-60.0,
        hysteresis_db=0.0,
        debounce_ms=0.0,
        window_ms=window * 1000,
        hop_ms=10.0,
    )
    assert 0.5 - window <= leading <= 0.5
    assert 0.25 - window <= trailing <= 0.25


def test_measure_silence_is_negligible_when_the_clip_is_signal_end_to_end(tmp_path):
    # A sine crosses zero at its very first sample, so a sample or two can sit
    # under the floor. At 16 kHz that is 0.06 ms, far below any usable
    # threshold, which is why the measurement needs no run-length rule.
    path = write_sine(tmp_path / "a.wav", seconds=1.0)
    leading, trailing = measure_silence(
        path,
        floor_db=-60.0,
        hysteresis_db=0.0,
        debounce_ms=0.0,
        window_ms=25.0,
        hop_ms=10.0,
    )
    assert leading == pytest.approx(0.0, abs=0.001)
    assert trailing == pytest.approx(0.0, abs=0.001)


def test_measure_silence_reports_a_fully_silent_clip_as_silent_throughout(tmp_path):
    # A broken stimulus. Calling it "unmeasurable" would let it slip past every
    # threshold, so it is reported as silence all the way through instead and
    # fails any cap that is configured.
    import numpy as np
    import soundfile as sf

    sf.write(str(tmp_path / "a.wav"), np.zeros(16000, dtype="float32"), 16000)
    leading, trailing = measure_silence(
        tmp_path / "a.wav",
        floor_db=-60.0,
        hysteresis_db=0.0,
        debounce_ms=0.0,
        window_ms=25.0,
        hop_ms=10.0,
    )
    assert leading == pytest.approx(1.0)
    assert trailing == pytest.approx(1.0)


def test_measure_silence_survives_a_single_stray_sample(tmp_path):
    # Per-sample comparison ended the silence at the first sample over the
    # floor, so one stray sample decided the whole result. What is judged now
    # is how much energy the window holds.
    import numpy as np
    import soundfile as sf

    path = write_padded_sine(tmp_path / "a.wav", lead=0.5)
    data, rate = sf.read(str(path))
    data = np.asarray(data)
    # A lone -46 dBFS sample. Judged on its own it is over a -60 dBFS floor,
    # but spread across a 20 ms window it carries only -71 dBFS of energy.
    data[int(0.1 * rate)] = 0.005
    sf.write(str(path), data, rate)
    assert measure_silence(
        path,
        floor_db=-60.0,
        hysteresis_db=0.0,
        debounce_ms=0.0,
        window_ms=25.0,
        hop_ms=10.0,
    )[0] == pytest.approx(0.5, abs=0.03)


def test_measure_silence_ignores_a_noise_floor_below_the_threshold(tmp_path):
    # Gaussian noise at -70 dBFS RMS peaks around -58 dBFS, above a -60 floor.
    # Judged sample by sample that reads as signal, which would report almost
    # no leading silence for any real recording.
    import numpy as np
    import soundfile as sf

    path = write_padded_sine(tmp_path / "a.wav", lead=0.5)
    data, rate = sf.read(str(path))
    data = np.asarray(data)
    lead = int(0.5 * rate)
    rng = np.random.default_rng(0)
    data[:lead] += rng.normal(0, 10 ** (-70 / 20), lead)
    sf.write(str(path), data, rate)
    assert measure_silence(
        path,
        floor_db=-60.0,
        hysteresis_db=0.0,
        debounce_ms=0.0,
        window_ms=25.0,
        hop_ms=10.0,
    )[0] == pytest.approx(0.5, abs=0.03)


@pytest.mark.parametrize(
    ("window_ms", "hop_ms"), [(25.0, 10.0), (20.0, 10.0), (33.0, 7.0), (50.0, 50.0)]
)
def test_measure_silence_examines_the_last_samples_whatever_the_grid(
    tmp_path, window_ms, hop_ms
):
    # The hop grid does not generally land on the end of the file, and the
    # samples past the final window would otherwise be reported as trailing
    # silence - erring long, which is the direction a cap must not err in.
    path = write_padded_sine(tmp_path / "a.wav", lead=0.1, trail=0.0, tone=1.0)
    _, trailing = measure_silence(
        path,
        floor_db=-60.0,
        hysteresis_db=0.0,
        debounce_ms=0.0,
        window_ms=window_ms,
        hop_ms=hop_ms,
    )
    assert trailing == pytest.approx(0.0, abs=0.001)


def test_measure_silence_reports_on_the_grid_the_hop_sets(tmp_path):
    # hop_ms decides which instants can be reported, window_ms decides how far
    # short the straddling window pulls the answer. They are separate knobs:
    # a finer grid does not need a shorter (noisier) window.
    path = write_padded_sine(tmp_path / "a.wav", lead=0.5)
    for hop in (0.1, 0.005):
        leading = measure_silence(
            path,
            floor_db=-60.0,
            hysteresis_db=0.0,
            debounce_ms=0.0,
            window_ms=20.0,
            hop_ms=hop * 1000,
        )[0]
        assert leading == pytest.approx(round(leading / hop) * hop)  # on the grid
        assert 0.5 - 0.02 - hop < leading <= 0.5  # short by at most a window


def test_measure_silence_hop_does_not_change_how_far_short_the_window_pulls(tmp_path):
    path = write_padded_sine(tmp_path / "a.wav", lead=0.5)
    wide = measure_silence(
        path,
        floor_db=-60.0,
        hysteresis_db=0.0,
        debounce_ms=0.0,
        window_ms=100.0,
        hop_ms=5.0,
    )[0]
    narrow = measure_silence(
        path,
        floor_db=-60.0,
        hysteresis_db=0.0,
        debounce_ms=0.0,
        window_ms=20.0,
        hop_ms=5.0,
    )[0]
    assert 0.5 - 0.1 <= wide < narrow <= 0.5


def test_measure_silence_stays_within_a_window_of_the_truth(tmp_path):
    # With the guards off, the only error left is the window straddling the
    # boundary, which pulls the answer short. Turning them on adds error in
    # the other direction (see the hysteresis and debounce tests), so the
    # measurement is bounded rather than one-directional.
    path = write_padded_sine(tmp_path / "a.wav", lead=0.5, trail=0.3)
    leading, trailing = measure_silence(
        path,
        floor_db=-60.0,
        hysteresis_db=0.0,
        debounce_ms=0.0,
        window_ms=50.0,
        hop_ms=10.0,
    )
    assert leading <= 0.5 + 1e-9
    assert trailing <= 0.3 + 1e-9


def test_measure_silence_follows_the_floor(tmp_path):
    # Padding at -40 dBFS is silence under a -30 floor and signal under -60.
    path = write_padded_sine(tmp_path / "a.wav", lead=0.5, amplitude=0.3)
    import numpy as np
    import soundfile as sf

    data, rate = sf.read(str(path))
    data = np.asarray(data)
    data[: int(0.5 * rate)] = 0.01  # -40 dBFS
    sf.write(str(path), data, rate)
    assert measure_silence(
        path,
        floor_db=-60.0,
        hysteresis_db=0.0,
        debounce_ms=0.0,
        window_ms=25.0,
        hop_ms=10.0,
    )[0] == pytest.approx(0.0)
    assert measure_silence(
        path,
        floor_db=-30.0,
        hysteresis_db=0.0,
        debounce_ms=0.0,
        window_ms=25.0,
        hop_ms=10.0,
    )[0] == pytest.approx(0.5, abs=0.03)


def test_measure_silence_handles_a_multichannel_clip(tmp_path):
    import numpy as np
    import soundfile as sf

    rate = 16000
    t = np.arange(rate) / rate
    body = 0.3 * np.sin(2 * np.pi * 440.0 * t)
    silence = np.zeros(int(0.5 * rate))
    mono = np.concatenate([silence, body])
    sf.write(str(tmp_path / "a.wav"), np.stack([mono, mono], axis=1), rate)
    assert measure_silence(
        tmp_path / "a.wav",
        floor_db=-60.0,
        hysteresis_db=0.0,
        debounce_ms=0.0,
        window_ms=25.0,
        hop_ms=10.0,
    )[0] == pytest.approx(0.5, abs=0.03)


def test_measure_silence_does_not_copy_the_windowed_signal(tmp_path):
    # Indexing the strided view with an array copies every window; slicing it
    # keeps the view. At 25/10 ms that copy is 60x the clip itself, so a long
    # recording would allocate hundreds of megabytes to read its edges.
    import tracemalloc

    write_padded_sine(tmp_path / "a.wav", lead=0.2, tone=20.0)
    tracemalloc.start()
    measure_silence(
        tmp_path / "a.wav",
        floor_db=-60.0,
        hysteresis_db=0.0,
        debounce_ms=0.0,
        window_ms=25.0,
        hop_ms=10.0,
    )
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    samples = 20.2 * 16000 * 8  # the clip itself, as float64
    assert peak < samples * 4


# -- hysteresis and debounce -------------------------------------------------


def write_signal(path, segments, rate=16000):
    """Write a clip from (seconds, amplitude) segments, 0 amplitude meaning silence."""
    import numpy as np
    import soundfile as sf

    parts = []
    for seconds, amplitude in segments:
        n = int(seconds * rate)
        if amplitude == 0:
            parts.append(np.zeros(n))
        else:
            parts.append(amplitude * np.sin(2 * np.pi * 440.0 * np.arange(n) / rate))
    sf.write(str(path), np.concatenate(parts).astype("float32"), rate)
    return path


DEFAULTS = dict(
    floor_db=-50.0, hysteresis_db=5.0, debounce_ms=30.0, window_ms=25.0, hop_ms=10.0
)


def test_debounce_ignores_a_burst_shorter_than_it(tmp_path):
    # 10 ms of tone inside the silence, then the real onset. Without debounce
    # the blip would end the silence at 0.2 s.
    path = write_signal(
        tmp_path / "a.wav", [(0.2, 0), (0.01, 0.3), (0.29, 0), (0.5, 0.3)]
    )
    leading = measure_silence(path, **DEFAULTS)[0]
    assert leading == pytest.approx(0.5, abs=0.03)


def test_debounce_keeps_a_burst_longer_than_it(tmp_path):
    path = write_signal(
        tmp_path / "a.wav", [(0.2, 0), (0.05, 0.3), (0.25, 0), (0.5, 0.3)]
    )
    leading = measure_silence(path, **DEFAULTS)[0]
    assert leading == pytest.approx(0.2, abs=0.03)


def test_hysteresis_lets_a_quiet_onset_ramp_count_as_sound(tmp_path):
    # The loud part qualifies, and the quiet ramp before it is above the lower
    # threshold, so the sound starts at the ramp - not where it gets loud.
    quiet = 10 ** ((-50 + 4) / 20)  # between the two thresholds
    path = write_signal(tmp_path / "a.wav", [(0.3, 0), (0.1, quiet), (0.5, 0.3)])
    leading = measure_silence(path, **DEFAULTS)[0]
    assert leading == pytest.approx(0.3, abs=0.03)


def test_hysteresis_keeps_a_decaying_tail_inside_the_sound(tmp_path):
    quiet = 10 ** ((-50 + 4) / 20)
    path = write_signal(tmp_path / "a.wav", [(0.5, 0.3), (0.1, quiet), (0.3, 0)])
    trailing = measure_silence(path, **DEFAULTS)[1]
    assert trailing == pytest.approx(0.3, abs=0.03)


def test_a_level_between_the_thresholds_alone_is_not_sound(tmp_path):
    # Nothing ever reaches the upper threshold, so there is no onset to hold.
    quiet = 10 ** ((-50 + 4) / 20)
    path = write_signal(tmp_path / "a.wav", [(0.2, 0), (0.5, quiet)])
    leading, trailing = measure_silence(path, **DEFAULTS)
    assert leading == pytest.approx(0.7, abs=0.03)
    assert trailing == pytest.approx(0.7, abs=0.03)


def test_a_clip_shorter_than_the_debounce_reads_as_silent(tmp_path):
    # Nothing in it sustains the upper threshold for debounce_ms, so by the
    # rule's own definition there is no sound. Such a clip is broken for a
    # listening test anyway, and reading it as silent is what fails a cap.
    path = write_signal(tmp_path / "a.wav", [(0.02, 0.3)])
    assert measure_silence(path, **DEFAULTS) == pytest.approx((0.02, 0.02))


def test_a_clip_past_the_debounce_but_too_short_to_frame_reads_as_silent(tmp_path):
    # The cutoff is not debounce_ms alone: qualifying needs debounce/hop + 1
    # readings, and a clip this short yields fewer however loud it is. Pinned
    # separately from the case above because 40 ms is past the 30 ms debounce,
    # so only the framing explains it.
    path = write_signal(tmp_path / "a.wav", [(0.04, 0.9)])
    assert measure_silence(path, **DEFAULTS) == pytest.approx((0.04, 0.04))


def test_a_noise_floor_above_the_threshold_leaves_no_silence_to_find(tmp_path):
    # An absolute floor assumes the recordings sit below it when nothing is
    # sounding. Room tone above it holds the sound open, so every clip reads
    # as 0 and the check passes vacuously - the floor has to be raised for
    # material like this. Pinned because the failure is otherwise silent.
    import numpy as np
    import soundfile as sf

    rate = 16000
    tone = np.random.default_rng(0).normal(0, 10 ** (-45 / 20), int(0.5 * rate))
    body = 0.3 * np.sin(2 * np.pi * 440.0 * np.arange(rate) / rate)
    sf.write(str(tmp_path / "a.wav"), np.concatenate([tone, body]), rate)
    assert measure_silence(tmp_path / "a.wav", **DEFAULTS) == (0.0, 0.0)
    raised = dict(DEFAULTS, floor_db=-40.0)
    assert measure_silence(tmp_path / "a.wav", **raised)[0] == pytest.approx(
        0.5, abs=0.03
    )


# -- the configured runner ---------------------------------------------------


def _config(tmp_path, silence_check, lead_by_system):
    entries = []
    for system, lead in lead_by_system.items():
        path = write_padded_sine(tmp_path / f"{system}.wav", lead=lead)
        entries.append(
            {"id": f"{system}__i1", "path": str(path), "system": system, "item": "i1"}
        )
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "stimuli_list": {"entries": entries},
    }
    if silence_check is not None:
        data["silence_check"] = silence_check
    return load_config(write_config(tmp_path, data))


def _dmos_config(tmp_path, silence_check, lead_by_system):
    """A DMOS config whose first system is the (disclosed) reference."""
    systems = []
    for i, (system, lead) in enumerate(lead_by_system.items()):
        directory = tmp_path / system
        directory.mkdir()
        write_padded_sine(directory / "i1.wav", lead=lead)
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
        "silence_check": silence_check,
    }
    return load_config(write_config(tmp_path, data))


def test_silence_check_measures_the_reference_by_default(tmp_path):
    config = _dmos_config(
        tmp_path,
        {"leading": {"per_item": {"threshold": 0.1}}},
        {"Ref": 0.6, "Test": 0.05},
    )
    with pytest.raises(SystemExit):
        run_configured_silence_check(config)


def test_silence_check_can_leave_the_reference_out(tmp_path, capsys):
    # The reference is disclosed in every test type that has one, so its
    # silence cannot give away which clip it is - the risk per_item exists
    # for. A natural recording also tends to carry silence nobody can edit.
    config = _dmos_config(
        tmp_path,
        {"include_reference": False, "leading": {"per_item": {"threshold": 0.1}}},
        {"Ref": 0.6, "Test": 0.05},
    )
    run_configured_silence_check(config)
    assert capsys.readouterr().out == ""


def test_leaving_the_reference_out_also_applies_to_the_per_clip_cap(tmp_path):
    config = _dmos_config(
        tmp_path,
        {"include_reference": False, "leading": {"per_stimulus": {"threshold": 0.3}}},
        {"Ref": 0.6, "Test": 0.05},
    )
    run_configured_silence_check(config)


def test_silence_check_is_a_noop_when_unconfigured(tmp_path, capsys):
    run_configured_silence_check(_config(tmp_path, None, {"A": 0.8}))
    assert capsys.readouterr().out == ""


def test_silence_check_passes_when_every_clip_is_inside_the_cap(tmp_path):
    config = _config(
        tmp_path, {"leading": {"per_stimulus": {"threshold": 0.5}}}, {"A": 0.1}
    )
    run_configured_silence_check(config)  # no SystemExit


def test_silence_check_per_stimulus_stops_on_a_clip_over_the_cap(tmp_path, capsys):
    config = _config(
        tmp_path, {"leading": {"per_stimulus": {"threshold": 0.2}}}, {"A": 0.8}
    )
    with pytest.raises(SystemExit):
        run_configured_silence_check(config)
    out = capsys.readouterr().out
    assert "A__i1" in out and "leading" in out


def test_silence_check_per_item_stops_on_a_spread_across_systems(tmp_path, capsys):
    # The blinding leak: same item, one system starts much later than the other.
    config = _config(
        tmp_path,
        {"leading": {"per_item": {"threshold": 0.1}}},
        {"A": 0.05, "B": 0.6},
    )
    with pytest.raises(SystemExit):
        run_configured_silence_check(config)
    out = capsys.readouterr().out
    assert "i1" in out


def test_silence_check_per_item_passes_when_systems_agree(tmp_path):
    config = _config(
        tmp_path,
        {"leading": {"per_item": {"threshold": 0.2}}},
        {"A": 0.5, "B": 0.55},
    )
    run_configured_silence_check(config)


def test_silence_check_trailing_is_independent_of_leading(tmp_path):
    # Only leading is configured, so a long tail must not stop the run.
    path = write_padded_sine(tmp_path / "A.wav", lead=0.05, trail=2.0)
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "stimuli_list": {"entries": [{"id": "A__i1", "path": str(path)}]},
        "silence_check": {"leading": {"per_stimulus": {"threshold": 0.5}}},
    }
    run_configured_silence_check(load_config(write_config(tmp_path, data)))


def test_silence_check_verbose_prints_even_when_nothing_is_exceeded(tmp_path, capsys):
    config = _config(
        tmp_path,
        {"leading": {"per_stimulus": {"threshold": 5.0, "verbose": True}}},
        {"A": 0.1},
    )
    run_configured_silence_check(config)
    assert "A__i1" in capsys.readouterr().out


def test_serve_startup_checks_loudness_before_silence(tmp_path, monkeypatch):
    # Order matters: the floor is absolute, so silence figures taken from
    # clips whose levels disagree may say more about the level difference.
    from fastapi.testclient import TestClient

    from listen_and_rate import main

    called: list[str] = []
    monkeypatch.setattr(
        main, "run_configured_loudness_check", lambda c: called.append("loudness")
    )
    monkeypatch.setattr(
        main, "run_configured_silence_check", lambda c: called.append("silence")
    )
    _config(tmp_path, {"leading": {"per_stimulus": {}}}, {"A": 0.05})
    monkeypatch.setenv("LISTEN_AND_RATE_CONFIG", str(tmp_path / "config.yaml"))
    with TestClient(main.create_app()):
        pass
    assert called == ["loudness", "silence"]
