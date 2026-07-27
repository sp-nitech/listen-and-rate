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
        path, floor_db=-60.0, window_ms=window * 1000, hop_ms=10.0
    )
    assert 0.5 - window <= leading <= 0.5
    assert 0.25 - window <= trailing <= 0.25


def test_measure_silence_is_negligible_when_the_clip_is_signal_end_to_end(tmp_path):
    # A sine crosses zero at its very first sample, so a sample or two can sit
    # under the floor. At 16 kHz that is 0.06 ms, far below any usable
    # threshold, which is why the measurement needs no run-length rule.
    path = write_sine(tmp_path / "a.wav", seconds=1.0)
    leading, trailing = measure_silence(
        path, floor_db=-60.0, window_ms=25.0, hop_ms=10.0
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
        tmp_path / "a.wav", floor_db=-60.0, window_ms=25.0, hop_ms=10.0
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
    assert measure_silence(path, floor_db=-60.0, window_ms=25.0, hop_ms=10.0)[
        0
    ] == pytest.approx(0.5, abs=0.03)


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
    assert measure_silence(path, floor_db=-60.0, window_ms=25.0, hop_ms=10.0)[
        0
    ] == pytest.approx(0.5, abs=0.03)


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
        path, floor_db=-60.0, window_ms=window_ms, hop_ms=hop_ms
    )
    assert trailing == pytest.approx(0.0, abs=0.001)


def test_measure_silence_reports_on_the_grid_the_hop_sets(tmp_path):
    # hop_ms decides which instants can be reported, window_ms decides how far
    # short the straddling window pulls the answer. They are separate knobs:
    # a finer grid does not need a shorter (noisier) window.
    path = write_padded_sine(tmp_path / "a.wav", lead=0.5)
    for hop in (0.1, 0.005):
        leading = measure_silence(
            path, floor_db=-60.0, window_ms=20.0, hop_ms=hop * 1000
        )[0]
        assert leading == pytest.approx(round(leading / hop) * hop)  # on the grid
        assert 0.5 - 0.02 - hop < leading <= 0.5  # short by at most a window


def test_measure_silence_hop_does_not_change_how_far_short_the_window_pulls(tmp_path):
    path = write_padded_sine(tmp_path / "a.wav", lead=0.5)
    wide = measure_silence(path, floor_db=-60.0, window_ms=100.0, hop_ms=5.0)[0]
    narrow = measure_silence(path, floor_db=-60.0, window_ms=20.0, hop_ms=5.0)[0]
    assert 0.5 - 0.1 <= wide < narrow <= 0.5


def test_measure_silence_never_overstates_the_silence(tmp_path):
    # A window straddling the boundary is pulled above the floor by the
    # signal in it, so the reported silence is short rather than long. Callers
    # use the number as a cap, and erring short keeps that conservative.
    path = write_padded_sine(tmp_path / "a.wav", lead=0.5, trail=0.3)
    leading, trailing = measure_silence(
        path, floor_db=-60.0, window_ms=50.0, hop_ms=10.0
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
    assert measure_silence(path, floor_db=-60.0, window_ms=25.0, hop_ms=10.0)[
        0
    ] == pytest.approx(0.0)
    assert measure_silence(path, floor_db=-30.0, window_ms=25.0, hop_ms=10.0)[
        0
    ] == pytest.approx(0.5, abs=0.03)


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
        tmp_path / "a.wav", floor_db=-60.0, window_ms=25.0, hop_ms=10.0
    )[0] == pytest.approx(0.5, abs=0.03)


def test_measure_silence_does_not_copy_the_windowed_signal(tmp_path):
    # Indexing the strided view with an array copies every window; slicing it
    # keeps the view. At 25/10 ms that copy is 60x the clip itself, so a long
    # recording would allocate hundreds of megabytes to read its edges.
    import tracemalloc

    write_padded_sine(tmp_path / "a.wav", lead=0.2, tone=20.0)
    tracemalloc.start()
    measure_silence(tmp_path / "a.wav", floor_db=-60.0, window_ms=25.0, hop_ms=10.0)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    samples = 20.2 * 16000 * 8  # the clip itself, as float64
    assert peak < samples * 4


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
