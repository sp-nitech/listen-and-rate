"""Tests for the /audio/{stimulus_id} streaming route."""

from __future__ import annotations

import pytest

from .._helpers import write_config, write_sine


def test_audio_served_is_loudness_normalized_when_configured(tmp_path, monkeypatch):
    pytest.importorskip("soundfile")

    from listen_and_rate.loudness import measure_loudness
    from listen_and_rate.main import create_app

    sine = write_sine(tmp_path / "clip.wav")
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "loudness_normalization": {"target": -20.0, "scope": "stimulus"},
        "stimuli": {"entries": [{"id": "s001", "path": str(sine)}]},
    }
    cfg_path = write_config(tmp_path, config)
    monkeypatch.setenv("LISTEN_AND_RATE_CONFIG", str(cfg_path))

    from fastapi.testclient import TestClient

    with TestClient(create_app()) as client:
        res = client.get("/audio/s001")
        assert res.status_code == 200
        served = tmp_path / "served.wav"
        served.write_bytes(res.content)
        assert measure_loudness(served) == pytest.approx(-20.0, abs=0.5)


def test_normalization_cache_is_cleaned_up_when_startup_fails(tmp_path, monkeypatch):
    """If normalization itself fails during startup, the freshly created temp
    cache must not be orphaned (it would otherwise accumulate a full copy of
    the stimuli under /tmp on every failed start)."""
    pytest.importorskip("soundfile")
    import tempfile

    from listen_and_rate import main as main_module

    sine = write_sine(tmp_path / "clip.wav")
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "loudness_normalization": {"target": -20.0},
        "stimuli": {"entries": [{"id": "s001", "path": str(sine)}]},
    }
    cfg_path = write_config(tmp_path, config)
    monkeypatch.setenv("LISTEN_AND_RATE_CONFIG", str(cfg_path))

    # Keep the cache under tmp_path so leftovers are visible to this test.
    tempdir = tmp_path / "tempdir"
    tempdir.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tempdir))

    def _boom(config, dst_for):
        raise RuntimeError("normalization failed mid-way")

    monkeypatch.setattr(main_module, "run_configured_loudness_normalization", _boom)

    from fastapi.testclient import TestClient

    with pytest.raises(RuntimeError, match="normalization failed"):
        with TestClient(main_module.create_app()):
            pass

    assert list(tempdir.iterdir()) == []  # no orphaned lar-normalized-* dir


def test_audio_valid_id(client):
    res = client.get("/audio/s001")
    assert res.status_code == 200
    assert "audio" in res.headers["content-type"]


def test_audio_head_request_returns_200(client):
    """The frontend's preflight check (checkAudioFiles) HEAD-requests every
    audio URL; without an explicit HEAD route the request falls through to
    the StaticFiles catch-all mounted at / and 404s, blocking every test
    from starting in FastAPI mode."""
    res = client.head("/audio/s001")
    assert res.status_code == 200


def test_audio_returns_404_for_unknown_id(client):
    assert client.get("/audio/nonexistent").status_code == 404


def test_audio_range_request_returns_206(client):
    assert client.get("/audio/s001", headers={"Range": "bytes=0-99"}).status_code == 206
