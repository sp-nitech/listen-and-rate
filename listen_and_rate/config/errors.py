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

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import yaml
from pydantic import ValidationError

from ..errors import UserError


def format_config_error(exc: ValidationError) -> str:
    """Render a config ValidationError as a clean, URL-free multi-line message.

    include_url=False drops pydantic's documentation-link trailer; each error
    is shown as "<dotted location>: <message>" (the location is omitted for
    errors that have none, e.g. the top-level test_type discriminator).
    """
    count = exc.error_count()
    lines = [f"invalid configuration ({count} error{'' if count == 1 else 's'}):"]
    for err in exc.errors(include_url=False):
        location = ".".join(str(part) for part in err["loc"])
        prefix = f"{location}: " if location else ""
        lines.append(f"  - {prefix}{err['msg']}")
    return "\n".join(lines)


@contextmanager
def config_file_errors(config_path: str | Path) -> Iterator[None]:
    """Read a config file inside this, and what is wrong with it names it.

    Whoever wrote the file has to find the mistake in it, so each is a
    UserError that starts with the file, named as they wrote its path: one
    that is not there, YAML that does not parse - placed at its line and
    column - and fields that do not validate. So is a ValueError (a UserError
    included) or an OSError raised while reading it, which is how the loaders
    report what the fields mean in practice (a missing audio file, a count out
    of range). Anything else is a bug, and passes through.
    """
    if not Path(config_path).is_file():
        raise UserError(f"{config_path}: config file not found")
    try:
        yield
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        where = (
            config_path
            if mark is None
            else f"{config_path}:{mark.line + 1}:{mark.column + 1}"
        )
        raise UserError(f"{where}: invalid YAML: {exc.problem or exc}") from exc
    except yaml.YAMLError as exc:
        raise UserError(f"{config_path}: invalid YAML: {exc}") from exc
    except ValidationError as exc:
        raise UserError(f"{config_path}: {format_config_error(exc)}") from exc
    except (ValueError, OSError) as exc:
        raise UserError(f"{config_path}: {exc}") from exc
