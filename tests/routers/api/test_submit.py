"""Tests for /api/submit output formats and metadata validation."""

from __future__ import annotations

import csv
import json

import pytest

from ._helpers import (
    _create_app_client,
)


def test_submit_happy_path(client, config_yaml):
    results_dir = config_yaml.parent / "results"
    res = client.post(
        "/api/submit",
        json={
            "session_id": "sess-ok",
            "test_type": "mos",
            "ratings": [
                {"stimulus_id": "s001", "rating": 5},
                {"stimulus_id": "s002", "rating": 4},
            ],
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    rows = list(csv.DictReader((results_dir / "config" / "sess-ok.csv").open()))
    assert "system" in rows[0]
    assert "utterance" in rows[0]
    assert "stimulus_id" not in rows[0]


def test_submit_same_session_id_twice_returns_409(client):
    body = {
        "session_id": "sess-dup",
        "test_type": "mos",
        "ratings": [
            {"stimulus_id": "s001", "rating": 5},
            {"stimulus_id": "s002", "rating": 4},
        ],
    }
    assert client.post("/api/submit", json=body).status_code == 200
    res = client.post("/api/submit", json=body)
    assert res.status_code == 409
    assert "already" in res.json()["detail"].lower()


def test_submit_writes_json_when_format_is_json(tmp_path, test_audio_file, monkeypatch):
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "json", "path": str(tmp_path / "results")},
        "stimuli": {
            "items": [
                {"id": "s001", "path": str(test_audio_file)},
                {"id": "s002", "path": str(test_audio_file)},
            ]
        },
    }
    with _create_app_client(tmp_path, config, monkeypatch) as tc:
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "sess-json",
                "test_type": "mos",
                "ratings": [
                    {"stimulus_id": "s001", "rating": 5},
                    {"stimulus_id": "s002", "rating": 4},
                ],
            },
        )
    assert res.status_code == 200
    json_path = tmp_path / "results" / "config" / "sess-json.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text())
    assert data["session_id"] == "sess-json"
    assert data["test_type"] == "mos"
    assert len(data["ratings"]) == 2


def test_submit_unknown_stimulus_returns_400(client):
    res = client.post(
        "/api/submit",
        json={
            "session_id": "s",
            "test_type": "mos",
            "ratings": [
                {"stimulus_id": "unknown", "rating": 4},
                {"stimulus_id": "s002", "rating": 3},
            ],
        },
    )
    assert res.status_code == 400


@pytest.mark.parametrize("rating", [0, 6])
def test_submit_rating_out_of_range_returns_400(client, rating):
    res = client.post(
        "/api/submit",
        json={
            "session_id": "s",
            "test_type": "mos",
            "ratings": [
                {"stimulus_id": "s001", "rating": rating},
                {"stimulus_id": "s002", "rating": 3},
            ],
        },
    )
    assert res.status_code == 400


def test_submit_malformed_body_returns_422(client):
    assert client.post("/api/submit", json={"invalid": True}).status_code == 422


def test_submit_mos_missing_ratings_returns_400(client):
    """A mos submission with no ratings key must be rejected, not silently accepted."""
    res = client.post("/api/submit", json={"session_id": "s", "test_type": "mos"})
    assert res.status_code == 400


def test_submit_mos_empty_ratings_returns_400(client):
    res = client.post(
        "/api/submit", json={"session_id": "s", "test_type": "mos", "ratings": []}
    )
    assert res.status_code == 400


def _client_with_metadata_config(
    tmp_path, test_audio_file, monkeypatch, metadata_fields
):
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "stimuli": {
            "items": [
                {"id": "s001", "path": str(test_audio_file)},
                {"id": "s002", "path": str(test_audio_file)},
            ]
        },
        "metadata": metadata_fields,
    }
    return _create_app_client(tmp_path, config, monkeypatch)


def _submit(tc, metadata):
    return tc.post(
        "/api/submit",
        json={
            "session_id": "s",
            "test_type": "mos",
            "ratings": [
                {"stimulus_id": "s001", "rating": 5},
                {"stimulus_id": "s002", "rating": 4},
            ],
            "metadata": metadata,
        },
    )


def test_submit_missing_required_metadata_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    fields = [
        {"key": "listener", "label": "Listener", "type": "text", "required": True}
    ]
    with _client_with_metadata_config(
        tmp_path, test_audio_file, monkeypatch, fields
    ) as tc:
        res = _submit(tc, {})
        assert res.status_code == 400


def test_submit_invalid_text_metadata_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    fields = [
        {"key": "listener", "label": "Listener", "type": "text", "required": True}
    ]
    with _client_with_metadata_config(
        tmp_path, test_audio_file, monkeypatch, fields
    ) as tc:
        res = _submit(tc, {"listener": "=cmd|'/C calc'!A1"})
        assert res.status_code == 400


def test_submit_select_metadata_not_in_options_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    fields = [
        {
            "key": "device",
            "label": "Device",
            "type": "select",
            "options": ["Headphones", "Speakers"],
            "required": True,
        }
    ]
    with _client_with_metadata_config(
        tmp_path, test_audio_file, monkeypatch, fields
    ) as tc:
        res = _submit(tc, {"device": "Bone conduction"})
        assert res.status_code == 400


def test_submit_valid_metadata_is_saved(tmp_path, test_audio_file, monkeypatch):
    fields = [
        {"key": "listener", "label": "Listener", "type": "text", "required": True},
        {
            "key": "device",
            "label": "Device",
            "type": "select",
            "options": ["Headphones", "Speakers"],
            "required": True,
        },
    ]
    with _client_with_metadata_config(
        tmp_path, test_audio_file, monkeypatch, fields
    ) as tc:
        res = _submit(tc, {"listener": "Alice-01", "device": "Headphones"})
        assert res.status_code == 200
        rows = list(csv.DictReader((tmp_path / "results" / "config" / "s.csv").open()))
        assert rows[0]["listener"] == "Alice-01"
        assert rows[0]["device"] == "Headphones"


def test_submit_strips_unknown_metadata_keys(tmp_path, test_audio_file, monkeypatch):
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "json", "path": str(tmp_path / "results")},
        "stimuli": {
            "items": [
                {"id": "s001", "path": str(test_audio_file)},
                {"id": "s002", "path": str(test_audio_file)},
            ]
        },
    }
    with _create_app_client(tmp_path, config, monkeypatch) as tc:
        res = _submit(tc, {"unexpected": "=cmd|'/C calc'!A1"})
        assert res.status_code == 200
        data = json.loads((tmp_path / "results" / "config" / "s.json").read_text())
        assert data["metadata"] == {}
