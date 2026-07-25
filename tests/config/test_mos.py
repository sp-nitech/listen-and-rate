"""Tests for MOS (Mean Opinion Score, ITU-T P.800) test configuration."""

from __future__ import annotations

import shutil

import pytest
from pydantic import ValidationError

from listen_and_rate.config import MOSConfig, load_config

from ._helpers import minimal_config, stimuli_dirs_data, write_config

# -- happy path -------------------------------------------------------------


def test_load_valid_mos_config(tmp_path, test_audio_file):
    result = load_config(write_config(tmp_path, minimal_config(str(test_audio_file))))
    assert isinstance(result, MOSConfig)
    assert result.test_type == "mos"
    assert result.title == "Test"
    assert len(result.stimuli.entries) == 1


def test_mos_config_with_three_systems_still_works(tmp_path, test_audio_file):
    """Regression: AB's exactly-2-systems rule must not leak into MOS."""
    dirs = []
    for name in ("sys_a", "sys_b", "sys_c"):
        d = tmp_path / name
        d.mkdir()
        shutil.copy(test_audio_file, d / "utt1.wav")
        dirs.append({"path": str(d)})
    data = stimuli_dirs_data(dirs)
    result = load_config(write_config(tmp_path, data))
    assert len(result.stimuli.entries) == 3


# -- rating_labels validation ------------------------------------------------


def test_mos_rating_labels_rejects_key_outside_1_to_5(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["rating_labels"] = {"33": "Much better"}
    with pytest.raises(ValidationError, match="rating_labels"):
        load_config(write_config(tmp_path, data))


def test_mos_rating_labels_accepts_valid_keys(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["rating_labels"] = {"1": "Bad", "5": "Excellent"}
    result = load_config(write_config(tmp_path, data))
    assert result.rating_labels == {"1": "Bad", "5": "Excellent"}


def test_mos_rating_labels_accepts_bare_numeric_keys(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["rating_labels"] = {1: "Bad", 5: "Excellent"}
    result = load_config(write_config(tmp_path, data))
    assert result.rating_labels == {"1": "Bad", "5": "Excellent"}


# -- practice stage ----------------------------------------------------------


def test_mos_practice_defaults_to_none(tmp_path, test_audio_file):
    result = load_config(write_config(tmp_path, minimal_config(str(test_audio_file))))
    assert result.practice is None


def test_mos_practice_count_defaults_to_zero(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["practice"] = {}
    result = load_config(write_config(tmp_path, data))
    assert result.practice.count == 0


def test_mos_practice_instructions_default_to_none(tmp_path, test_audio_file):
    # Mirrors the required top-level `instructions`, which has no default
    # either: wording the listener sees is always the researcher's to write.
    data = minimal_config(str(test_audio_file))
    data["practice"] = {"count": 1}
    result = load_config(write_config(tmp_path, data))
    assert result.practice.count == 1
    assert result.practice.instructions is None


def test_mos_practice_accepts_custom_instructions(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["practice"] = {"count": 1, "instructions": "Warm-up round."}
    result = load_config(write_config(tmp_path, data))
    assert result.practice.instructions == "Warm-up round."


def test_mos_practice_rejects_negative_count(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["practice"] = {"count": -1}
    with pytest.raises(ValidationError, match="practice"):
        load_config(write_config(tmp_path, data))


def test_mos_practice_rejects_unknown_field(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["practice"] = {"count": 1, "title": "Practice"}
    with pytest.raises(ValidationError, match="title"):
        load_config(write_config(tmp_path, data))


def test_mos_practice_count_exceeding_pool_is_rejected(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))  # pool has 1 stimulus
    data["practice"] = {"count": 2}
    with pytest.raises(ValueError, match="practice.count"):
        load_config(write_config(tmp_path, data))


def test_mos_practice_count_equal_to_pool_is_accepted(tmp_path, test_audio_file):
    data = minimal_config(str(test_audio_file))
    data["practice"] = {"count": 1}
    result = load_config(write_config(tmp_path, data))
    assert result.practice.count == 1
