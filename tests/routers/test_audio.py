"""Tests for the /audio/{stimulus_id} streaming route."""

from __future__ import annotations


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
