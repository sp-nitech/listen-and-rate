"""Tests for the shared identifier rule."""

from __future__ import annotations

import pytest

from listen_and_rate.ids import is_valid_id


@pytest.mark.parametrize(
    "value",
    ["config.mos", "study-a", "exp_1", "A", "1", "a.b-c_d"],
)
def test_accepts_path_safe_identifiers(value):
    assert is_valid_id(value)


@pytest.mark.parametrize(
    "value",
    [
        "",  # would make the path collapse onto its parent
        "my config",  # space
        "実験1",  # any non-ASCII
        "a/b",  # separator
        "..",  # parent directory
        "a\\b",  # Windows separator
        "a\nb",  # newline, so a header/log line cannot be split
    ],
)
def test_rejects_everything_that_is_not(value):
    assert not is_valid_id(value)
