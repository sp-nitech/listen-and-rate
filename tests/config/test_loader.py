"""Tests for load_config: paths, experiment_id, stimuli_dirs, sampling, security."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from listen_and_rate.config import load_config

from ._helpers import (
    minimal_config,
    stimuli_dirs_data,
    two_system_dirs,
    write_config,
)


def test_empty_config_file_raises_clean_error(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("")
    with pytest.raises(ValueError, match="YAML mapping"):
        load_config(path)


def test_non_mapping_config_file_raises_clean_error(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="YAML mapping"):
        load_config(path)


def test_load_config_with_all_fields(tmp_path, test_audio_file):
    data = {
        "test_type": "mos",
        "title": "Full Test",
        "instructions": "Listen carefully.",
        "presentation_order": "random",
        "output": {"format": "json", "path": "./out/"},
        "stimuli": {
            "items": [
                {"id": "s001", "path": str(test_audio_file), "label": "A"},
                {"id": "s002", "path": str(test_audio_file), "label": "B"},
            ]
        },
    }
    result = load_config(write_config(tmp_path, data))
    assert result.presentation_order == "random"
    assert result.output.format == "json"
    assert len(result.stimuli.items) == 2
    assert result.stimuli.items[0].label == "A"


def test_relative_audio_path_resolved_to_absolute(tmp_path, test_audio_file):
    shutil.copy(test_audio_file, tmp_path / "sample.wav")
    result = load_config(write_config(tmp_path, minimal_config("./sample.wav")))
    assert Path(result.stimuli.items[0].path).is_absolute()
    assert Path(result.stimuli.items[0].path).exists()


def test_experiment_id_is_derived_from_config_filename(tmp_path, test_audio_file):
    p = tmp_path / "myexperiment.yaml"
    p.write_text(yaml.dump(minimal_config(str(test_audio_file))))
    assert load_config(p).experiment_id == "myexperiment"


def test_experiment_id_in_yaml_is_rejected(tmp_path, test_audio_file):
    """experiment_id is always derived from the config filename, never
    user-settable - it's not a real model field, so (like any other unknown
    key) putting it in the YAML must be rejected, not silently ignored."""
    data = minimal_config(str(test_audio_file))
    data["experiment_id"] = "should-be-rejected"
    with pytest.raises(ValidationError, match="experiment_id"):
        load_config(write_config(tmp_path, data))


def test_duplicate_stimulus_ids_raise_error(tmp_path, test_audio_file):
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli": {
            "items": [
                {"id": "dup", "path": str(test_audio_file)},
                {"id": "dup", "path": str(test_audio_file)},
            ]
        },
    }
    with pytest.raises((ValidationError, ValueError)):
        load_config(write_config(tmp_path, data))


def test_missing_audio_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(write_config(tmp_path, minimal_config("./nonexistent.wav")))


def test_non_audio_file_with_audio_extension_raises_error(tmp_path):
    # A file that exists but isn't actually decodable audio (here: HTML bytes
    # behind a .wav name) is caught at load time by a cheap header-only check,
    # so the experimenter learns about it before any listener gets stuck on an
    # unplayable stimulus.
    bad = tmp_path / "broken.wav"
    bad.write_bytes(b"<html>not audio at all</html>")
    with pytest.raises(ValueError, match="broken.wav"):
        load_config(write_config(tmp_path, minimal_config(str(bad))))


def test_empty_audio_file_raises_error(tmp_path):
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="empty.wav"):
        load_config(write_config(tmp_path, minimal_config(str(empty))))


def test_same_dir_same_stem_stimuli_rejected(tmp_path, test_audio_file):
    # Two stimuli whose paths differ only in extension (utt1.wav vs utt1.flac
    # in one directory, a realistic codec-comparison layout) are rejected
    # unconditionally: loudness normalization would fold them onto one .wav
    # output (the later write silently replacing the earlier), so allowing
    # them only while normalization is off would make config validity depend
    # on an unrelated setting.
    d = tmp_path / "audio"
    d.mkdir()
    shutil.copy(test_audio_file, d / "utt1.wav")
    shutil.copy(test_audio_file, d / "utt1.flac")
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli": {
            "items": [
                {"id": "original", "path": str(d / "utt1.wav")},
                {"id": "coded", "path": str(d / "utt1.flac")},
            ]
        },
    }
    with pytest.raises(ValueError, match="utt1"):
        load_config(write_config(tmp_path, data))


def test_same_file_referenced_by_multiple_stimuli_allowed(tmp_path, test_audio_file):
    # Deliberately repeating ONE clip under several ids (e.g. an intra-rater
    # consistency trial) is not a basename conflict: every id sharing one
    # normalized output is exactly the intent.
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli": {
            "items": [
                {"id": "first", "path": str(test_audio_file)},
                {"id": "repeat", "path": str(test_audio_file)},
            ]
        },
    }
    assert load_config(write_config(tmp_path, data)) is not None


def test_same_stem_in_different_dirs_allowed(tmp_path, test_audio_file):
    da, db = tmp_path / "A", tmp_path / "B"
    da.mkdir()
    db.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    shutil.copy(test_audio_file, db / "utt1.wav")
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli": {
            "items": [
                {"id": "a", "path": str(da / "utt1.wav")},
                {"id": "b", "path": str(db / "utt1.wav")},
            ]
        },
    }
    assert load_config(write_config(tmp_path, data)) is not None


def test_stimuli_dirs_expansion(tmp_path, test_audio_file):
    d = tmp_path / "system_a"
    d.mkdir()
    shutil.copy(test_audio_file, d / "001.wav")
    shutil.copy(test_audio_file, d / "002.wav")
    data = stimuli_dirs_data([{"path": str(d)}])
    result = load_config(write_config(tmp_path, data))
    assert len(result.stimuli.items) == 2
    for s in result.stimuli.items:
        assert re.match(r"^[a-zA-Z0-9_\-]+$", s.id), f"ID not URL-safe: {s.id}"
    assert result.stimuli.items[0].utterance in {"001", "002"}


def test_stimuli_dirs_system_field(tmp_path, test_audio_file):
    d = tmp_path / "system_a"
    d.mkdir()
    shutil.copy(test_audio_file, d / "001.wav")

    # Without system: directory name is used
    data = stimuli_dirs_data([{"path": str(d)}])
    result = load_config(write_config(tmp_path, data))
    assert result.stimuli.items[0].system == "system_a"

    # With system: overrides directory name
    data = stimuli_dirs_data([{"path": str(d), "system": "System A"}])
    result = load_config(write_config(tmp_path, data))
    assert result.stimuli.items[0].system == "System A"


def test_stimuli_dirs_multiple_systems(tmp_path, test_audio_file):
    da = tmp_path / "sys_a"
    db = tmp_path / "sys_b"
    da.mkdir()
    db.mkdir()
    shutil.copy(test_audio_file, da / "001.wav")
    shutil.copy(test_audio_file, db / "001.wav")
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}])
    result = load_config(write_config(tmp_path, data))
    assert len(result.stimuli.items) == 2
    systems = {s.system for s in result.stimuli.items}
    assert systems == {"sys_a", "sys_b"}


def test_nonexistent_stimuli_dir_raises_error(tmp_path):
    data = stimuli_dirs_data([{"path": "./nonexistent_dir"}])
    with pytest.raises(NotADirectoryError):
        load_config(write_config(tmp_path, data))


def test_stimuli_dirs_no_common_files_raises_error(tmp_path, test_audio_file):
    da = tmp_path / "sys_a"
    db = tmp_path / "sys_b"
    da.mkdir()
    db.mkdir()
    shutil.copy(test_audio_file, da / "001.wav")
    shutil.copy(test_audio_file, db / "002.wav")
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}])
    with pytest.raises(ValueError, match="No common audio files"):
        load_config(write_config(tmp_path, data))


def test_stimuli_dirs_system_specific_files_warns(tmp_path, test_audio_file):
    da = tmp_path / "sys_a"
    db = tmp_path / "sys_b"
    da.mkdir()
    db.mkdir()
    shutil.copy(test_audio_file, da / "001.wav")
    shutil.copy(test_audio_file, da / "002.wav")
    shutil.copy(test_audio_file, db / "001.wav")
    data = stimuli_dirs_data([{"path": str(da)}, {"path": str(db)}])
    with pytest.warns(UserWarning, match="not present in all systems"):
        load_config(write_config(tmp_path, data))


def test_stimuli_dirs_single_system_skips_cross_checks(tmp_path, test_audio_file):
    da = tmp_path / "sys_a"
    da.mkdir()
    shutil.copy(test_audio_file, da / "001.wav")
    data = stimuli_dirs_data([{"path": str(da)}])
    result = load_config(write_config(tmp_path, data))
    assert len(result.stimuli.items) == 1


def test_stimuli_dirs_duplicate_basename_raises_error(tmp_path, test_audio_file):
    sub_a = tmp_path / "group_a" / "audio"
    sub_b = tmp_path / "group_b" / "audio"
    sub_a.mkdir(parents=True)
    sub_b.mkdir(parents=True)
    shutil.copy(test_audio_file, sub_a / "001.wav")
    shutil.copy(test_audio_file, sub_b / "001.wav")
    data = stimuli_dirs_data([{"path": str(sub_a)}, {"path": str(sub_b)}])
    with pytest.raises(ValueError, match="unique"):
        load_config(write_config(tmp_path, data))


def test_stimuli_dirs_duplicate_explicit_system_name_raises_error(
    tmp_path, test_audio_file
):
    """Two directories explicitly labeled with the same system name must be
    rejected - their stimulus IDs wouldn't collide (different dir names), so
    the duplicate-stimulus-ID check alone wouldn't catch this, but every
    per-system statistic and every AB/ABX/CMOS pairing downstream would
    silently conflate the two directories into one system."""
    da, db = two_system_dirs(tmp_path, test_audio_file)
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "Same"},
            {"path": str(db), "system": "Same"},
        ]
    )
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        load_config(write_config(tmp_path, data))


def test_stimuli_dirs_explicit_system_name_collides_with_dir_basename_fallback(
    tmp_path, test_audio_file
):
    """An explicit `system:` name that happens to match another entry's
    dirname-derived default must also be rejected, not just two identical
    explicit names."""
    da = tmp_path / "some_dir"
    db = tmp_path / "A"
    da.mkdir()
    db.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    shutil.copy(test_audio_file, db / "utt1.wav")
    data = stimuli_dirs_data(
        [
            {"path": str(da), "system": "A"},
            {"path": str(db)},  # system defaults to dirname "A"
        ]
    )
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        load_config(write_config(tmp_path, data))


def test_utterances_per_session_validated_against_total(tmp_path, test_audio_file):
    da = tmp_path / "sys_a"
    da.mkdir()
    shutil.copy(test_audio_file, da / "001.wav")
    data = stimuli_dirs_data([{"path": str(da)}], utterances_per_session=5)
    with pytest.raises(ValueError, match="utterances_per_session"):
        load_config(write_config(tmp_path, data))


def test_utterances_per_session_must_be_at_least_one(tmp_path, test_audio_file):
    da = tmp_path / "sys_a"
    da.mkdir()
    shutil.copy(test_audio_file, da / "001.wav")
    data = stimuli_dirs_data([{"path": str(da)}], utterances_per_session=0)
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_stimuli_per_session_validated_against_total(tmp_path, test_audio_file):
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli": {
            "stimuli_per_session": 10,
            "items": [{"id": "s001", "path": str(test_audio_file)}],
        },
    }
    with pytest.raises(ValueError, match="stimuli_per_session"):
        load_config(write_config(tmp_path, data))


def test_stimuli_per_session_must_be_at_least_one(tmp_path, test_audio_file):
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli": {
            "stimuli_per_session": 0,
            "items": [{"id": "s001", "path": str(test_audio_file)}],
        },
    }
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))


def test_stimuli_dir_with_only_unsupported_format_is_rejected(tmp_path):
    """m4a (and any unsupported format) is ignored during dir scan; a dir with
    no recognized audio therefore yields no stimuli and is rejected at load."""
    d = tmp_path / "sys_a"
    d.mkdir()
    (d / "utt1.m4a").write_bytes(b"")
    data = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli_dirs": {"systems": [{"path": str(d)}]},
    }
    with pytest.raises(ValueError, match="No audio stimuli"):
        load_config(write_config(tmp_path, data))


def test_symlink_within_project_is_allowed(tmp_path, test_audio_file, tmp_path_factory):
    external_dir = tmp_path_factory.mktemp("external")
    shutil.copy(test_audio_file, external_dir / "001.wav")
    link = tmp_path / "audio_link"
    link.symlink_to(external_dir)
    data = stimuli_dirs_data([{"path": str(link)}])
    result = load_config(write_config(tmp_path, data))
    assert len(result.stimuli.items) == 1
