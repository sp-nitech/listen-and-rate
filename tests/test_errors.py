"""Tests for how a mistake in what the tool was given is reported."""

from __future__ import annotations

import pytest

from listen_and_rate.errors import UserError, exit_on_user_error


def test_the_entry_point_exits_with_the_message_and_no_traceback():
    with pytest.raises(SystemExit) as excinfo:
        with exit_on_user_error():
            raise UserError("a.yaml: config file not found")
    assert excinfo.value.code == "a.yaml: config file not found"
    # A message as the code: Python prints it to stderr and exits with 1.
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__


def test_the_entry_point_keeps_what_was_noted_on_the_error():
    # A note can say why a mistake happened (results from another release,
    # say), which is as much the listener's business as the mistake itself.
    error = UserError("no MOS rows found")
    error.add_note("these results were written by 9.9.0")
    with pytest.raises(SystemExit) as excinfo:
        with exit_on_user_error():
            raise error
    assert excinfo.value.code == (
        "no MOS rows found\nthese results were written by 9.9.0"
    )


def test_any_other_error_keeps_its_traceback():
    # Only a mistake the tool expects is shortened. Anything else is a bug,
    # and its traceback is what finds it.
    with pytest.raises(KeyError):
        with exit_on_user_error():
            raise KeyError("x")
