from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ._helpers import write_config


@pytest.fixture(autouse=True)
def chdir_to_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def test_audio_file(tmp_path) -> Path:
    p = tmp_path / "test.wav"
    with wave.open(str(p), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(struct.pack("<1600h", *([0] * 1600)))
    return p


@pytest.fixture
def config_yaml(tmp_path, test_audio_file) -> Path:
    config = {
        "test_type": "mos",
        "title": "Test Evaluation",
        "instructions": "Rate the quality.",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "presentation_order": "fixed",
        "stimuli": {
            "items": [
                {"id": "s001", "path": str(test_audio_file)},
                {"id": "s002", "path": str(test_audio_file)},
            ]
        },
    }
    return write_config(tmp_path, config)


@pytest.fixture
def client(config_yaml, monkeypatch) -> TestClient:
    monkeypatch.setenv("LISTEN_AND_RATE_CONFIG", str(config_yaml))
    from listen_and_rate.main import create_app

    with TestClient(create_app()) as tc:
        yield tc
