"""Shared (non-fixture) helper functions used across tests/config/test_*.py."""

from __future__ import annotations

import shutil

from .._helpers import write_config as write_config  # re-exported for config tests


def minimal_config(audio_path: str) -> dict:
    return {
        "test_type": "mos",
        "title": "Test",
        "instructions": "Rate the quality.",
        "stimuli": {"items": [{"id": "s001", "path": audio_path}]},
    }


def stimuli_dirs_data(dirs: list[dict], test_type: str = "mos", **kwargs) -> dict:
    return {
        "test_type": test_type,
        "title": "T",
        "instructions": "I",
        "stimuli_dirs": {"systems": dirs, **kwargs},
    }


def make_system_dirs(tmp_path, test_audio_file, names, utterances=("utt1", "utt2")):
    """Create one audio directory per name in `names`, each with the same files."""
    dirs = []
    for name in names:
        d = tmp_path / name
        d.mkdir()
        for u in utterances:
            shutil.copy(test_audio_file, d / f"{u}.wav")
        dirs.append(d)
    return tuple(dirs)


def two_system_dirs(tmp_path, test_audio_file, utterances=("utt1", "utt2")):
    return make_system_dirs(tmp_path, test_audio_file, ("sys_a", "sys_b"), utterances)


def three_system_dirs(tmp_path, test_audio_file, utterances=("utt1", "utt2")):
    return make_system_dirs(
        tmp_path, test_audio_file, ("sys_ref", "sys_b", "sys_c"), utterances
    )
