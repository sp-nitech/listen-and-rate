"""Shared TestClient builders and practice constants for the API route tests."""

from __future__ import annotations

import shutil

import yaml
from fastapi.testclient import TestClient


def _create_app_client(tmp_path, config: dict, monkeypatch) -> TestClient:
    """Write `config` to config.yaml, point the app at it, and build a TestClient."""
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(config))
    monkeypatch.setenv("LISTEN_AND_RATE_CONFIG", str(p))
    from listen_and_rate.main import create_app

    return TestClient(create_app())


def _two_system_dirs(tmp_path, test_audio_file, n_utterances):
    """Create sys_a/sys_b dirs, each with n_utterances audio files named uttN.wav."""
    da = tmp_path / "sys_a"
    db = tmp_path / "sys_b"
    da.mkdir()
    db.mkdir()
    for i in range(n_utterances):
        shutil.copy(test_audio_file, da / f"utt{i}.wav")
        shutil.copy(test_audio_file, db / f"utt{i}.wav")
    return da, db


def _two_system_client(
    tmp_path,
    test_audio_file,
    monkeypatch,
    test_type,
    n_utterances=2,
    utterances_per_session=None,
    presentation_order="random",
    **extra,
):
    da, db = _two_system_dirs(tmp_path, test_audio_file, n_utterances)
    stimuli_dirs = {
        "systems": [
            {"path": str(da), "system": "A"},
            {"path": str(db), "system": "B"},
        ]
    }
    if utterances_per_session is not None:
        stimuli_dirs["utterances_per_session"] = utterances_per_session
    config = {
        "test_type": test_type,
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "presentation_order": presentation_order,
        "stimuli_dirs": stimuli_dirs,
        **extra,
    }
    return _create_app_client(tmp_path, config, monkeypatch)


def _make_stimuli_dirs_config(
    tmp_path, test_audio_file, n_utterances, n_systems, **kwargs
):
    dirs = []
    for si in range(n_systems):
        d = tmp_path / f"sys_{si}"
        d.mkdir()
        for ui in range(n_utterances):
            shutil.copy(test_audio_file, d / f"utt{ui}.wav")
        dirs.append({"path": str(d)})
    return {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "stimuli_dirs": {"systems": dirs, **kwargs},
    }


def _mos_practice_config(tmp_path, test_audio_file, n_items, practice):
    return {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "practice": practice,
        "stimuli": {
            "items": [
                {"id": f"s{i:03d}", "path": str(test_audio_file)}
                for i in range(n_items)
            ],
        },
    }


def _dmos_client(
    tmp_path,
    test_audio_file,
    monkeypatch,
    n_utterances=2,
    n_test_systems=1,
    utterances_per_session=None,
    presentation_order="random",
    **extra,
):
    d_ref = tmp_path / "sys_ref"
    d_ref.mkdir()
    for i in range(n_utterances):
        shutil.copy(test_audio_file, d_ref / f"utt{i}.wav")
    systems = [{"path": str(d_ref), "system": "Reference", "reference": True}]
    for t in range(n_test_systems):
        d_test = tmp_path / f"sys_test{t}"
        d_test.mkdir()
        for i in range(n_utterances):
            shutil.copy(test_audio_file, d_test / f"utt{i}.wav")
        systems.append({"path": str(d_test), "system": f"Test{t}"})

    stimuli_dirs = {"systems": systems}
    if utterances_per_session is not None:
        stimuli_dirs["utterances_per_session"] = utterances_per_session
    config = {
        "test_type": "dmos",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "presentation_order": presentation_order,
        "stimuli_dirs": stimuli_dirs,
        **extra,
    }
    return _create_app_client(tmp_path, config, monkeypatch)


def _cmos_client(
    tmp_path,
    test_audio_file,
    monkeypatch,
    n_utterances=2,
    utterances_per_session=None,
    presentation_order="random",
    **extra,
):
    return _two_system_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        "cmos",
        n_utterances,
        utterances_per_session,
        presentation_order,
        **extra,
    )


def _ab_client(
    tmp_path,
    test_audio_file,
    monkeypatch,
    n_utterances=2,
    allow_tie=True,
    utterances_per_session=None,
    presentation_order="random",
    **extra,
):
    return _two_system_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        "ab",
        n_utterances,
        utterances_per_session,
        presentation_order,
        allow_tie=allow_tie,
        **extra,
    )


def _abx_client(
    tmp_path,
    test_audio_file,
    monkeypatch,
    n_utterances=2,
    utterances_per_session=None,
    presentation_order="random",
    **extra,
):
    return _two_system_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        "abx",
        n_utterances,
        utterances_per_session,
        presentation_order,
        **extra,
    )


def _xab_client(
    tmp_path,
    test_audio_file,
    monkeypatch,
    n_utterances=2,
    utterances_per_session=None,
    presentation_order="random",
    **extra,
):
    dirs = []
    for name in ("ref", "sys_a", "sys_b"):
        d = tmp_path / name
        d.mkdir()
        for i in range(n_utterances):
            shutil.copy(test_audio_file, d / f"utt{i}.wav")
        dirs.append(d)
    stimuli_dirs = {
        "systems": [
            {"path": str(dirs[0]), "system": "Ref", "reference": True},
            {"path": str(dirs[1]), "system": "A"},
            {"path": str(dirs[2]), "system": "B"},
        ]
    }
    if utterances_per_session is not None:
        stimuli_dirs["utterances_per_session"] = utterances_per_session
    config = {
        "test_type": "xab",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "presentation_order": presentation_order,
        "stimuli_dirs": stimuli_dirs,
        **extra,
    }
    return _create_app_client(tmp_path, config, monkeypatch)


def _mushra_client(
    tmp_path,
    test_audio_file,
    monkeypatch,
    n_utterances=2,
    n_test_systems=2,
    with_reference=True,
    with_anchor=True,
    utterances_per_session=None,
    presentation_order="random",
    **extra,
):
    systems = []
    if with_reference:
        d_ref = tmp_path / "sys_ref"
        d_ref.mkdir()
        for i in range(n_utterances):
            shutil.copy(test_audio_file, d_ref / f"utt{i}.wav")
        systems.append({"path": str(d_ref), "system": "Reference", "reference": True})
    for t in range(n_test_systems):
        d_test = tmp_path / f"sys_test{t}"
        d_test.mkdir()
        for i in range(n_utterances):
            shutil.copy(test_audio_file, d_test / f"utt{i}.wav")
        systems.append({"path": str(d_test), "system": f"Test{t}"})
    if with_anchor:
        d_anchor = tmp_path / "sys_anchor"
        d_anchor.mkdir()
        for i in range(n_utterances):
            shutil.copy(test_audio_file, d_anchor / f"utt{i}.wav")
        systems.append({"path": str(d_anchor), "system": "Anchor", "anchor": True})

    stimuli_dirs = {"systems": systems}
    if utterances_per_session is not None:
        stimuli_dirs["utterances_per_session"] = utterances_per_session
    config = {
        "test_type": "mushra",
        "title": "T",
        "instructions": "I",
        "output": {"format": "csv", "path": str(tmp_path / "results")},
        "presentation_order": presentation_order,
        "stimuli_dirs": stimuli_dirs,
        **extra,
    }
    return _create_app_client(tmp_path, config, monkeypatch)


_PRACTICE = {"count": 1, "instructions": "Warm-up."}


def _assert_practice_common(data, n_trials=1):
    assert data["practice_instructions"] == "Warm-up."
    assert len(data["practice_trials"]) == n_trials
