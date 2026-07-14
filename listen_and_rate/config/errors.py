"""Human-friendly formatting of config validation errors.

A config file is written by hand by the experimenter, so a mistake in it
should read like a config error, not a library stack trace. Pydantic's
default str(ValidationError) appends a "For further information visit
https://errors.pydantic.dev/..." line to every built-in error (Literal,
ge/gt bounds, missing fields, the test_type discriminator, ...) - noise here.
This renders the same errors without that URL, uniformly for both pydantic's
built-in errors and this package's own PydanticCustomError messages.
"""

from __future__ import annotations

from pydantic import ValidationError


def format_config_error(exc: ValidationError) -> str:
    """Render a config ValidationError as a clean, URL-free multi-line message.

    include_url=False drops pydantic's documentation-link trailer; each error
    is shown as "<dotted location>: <message>" (the location is omitted for
    errors that have none, e.g. the top-level test_type discriminator).
    """
    lines = [f"Invalid configuration ({exc.error_count()} error(s)):"]
    for err in exc.errors(include_url=False):
        location = ".".join(str(part) for part in err["loc"])
        prefix = f"{location}: " if location else ""
        lines.append(f"  - {prefix}{err['msg']}")
    return "\n".join(lines)
