"""Tests for config-error formatting: config-file mistakes must not surface
pydantic's "For further information visit https://errors.pydantic.dev/..." URL,
consistently across built-in and custom validation errors."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from listen_and_rate.config import format_config_error, load_config
from listen_and_rate.config.loader import Config

from ._helpers import minimal_config, write_config

_PYDANTIC_URL = "errors.pydantic.dev"


def _error_for(data: dict) -> ValidationError:
    with pytest.raises(ValidationError) as excinfo:
        TypeAdapter(Config).validate_python(data)
    return excinfo.value


@pytest.mark.parametrize(
    ("mutate", "expected_substring"),
    [
        (lambda d: d.update(test_type="mos2"), "test_type"),
        (lambda d: d.__setitem__("bogus_key", 1), "bogus_key"),
        (lambda d: d.pop("title"), "title"),
        (
            lambda d: d.__setitem__(
                "stimuli", {"stimuli_per_session": -1, "items": d["stimuli"]["items"]}
            ),
            "stimuli_per_session",
        ),
    ],
)
def test_format_config_error_has_no_pydantic_url(mutate, expected_substring):
    data = minimal_config("/tmp/nonexistent.wav")
    mutate(data)
    message = format_config_error(_error_for(data))
    assert _PYDANTIC_URL not in message
    assert expected_substring in message


def test_format_config_error_lists_every_error():
    data = minimal_config("/tmp/nonexistent.wav")
    data.pop("title")
    data.pop("instructions")
    message = format_config_error(_error_for(data))
    assert "title" in message
    assert "instructions" in message


def test_load_config_still_raises_validation_error(tmp_path):
    """load_config keeps raising ValidationError; only display formats it."""
    data = minimal_config("/tmp/nonexistent.wav")
    data["test_type"] = "mos2"
    with pytest.raises(ValidationError):
        load_config(write_config(tmp_path, data))
