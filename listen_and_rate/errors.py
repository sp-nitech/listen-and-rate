"""Mistakes in what the tool was given, and how an entry point reports them.

A config file, a path on the command line, a results directory: whoever runs
the tool gets these wrong now and then, and the fix is theirs to make. So a
mistake of that kind reads like one - where it is, then what is wrong, the way
a compiler or a linter puts it ("examples/a.yaml: config file not found") -
rather than as a stack trace. Anything else that goes wrong is a bug, and
keeps the traceback that finds it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager


class UserError(ValueError):
    """A mistake in what the tool was given - a value it cannot use.

    The message starts with the file it is in, as the user wrote its path,
    when it is about one ("path: what is wrong", what is wrong in lowercase),
    and is what is wrong alone when it is not.
    """


@contextmanager
def exit_on_user_error() -> Iterator[None]:
    """At an entry point, end on a UserError with its message alone.

    SystemExit with a message prints it to stderr and exits with status 1.
    What was noted on the error (add_note) follows it, as it would under the
    traceback. The traceback is dropped only for a UserError: any other
    exception passes through as it is.
    """
    try:
        yield
    except UserError as exc:
        notes = getattr(exc, "__notes__", [])
        raise SystemExit("\n".join([str(exc), *notes])) from None
