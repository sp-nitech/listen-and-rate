"""Small YAML/string coercion and validation helpers shared across config submodules."""

from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic_core import PydanticCustomError

_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")

_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg"}
_ID_UNSAFE = re.compile(r"[^a-zA-Z0-9_\-]")


def _safe_id(s: str) -> str:
    """Replace characters that are not URL-safe with underscores."""
    return _ID_UNSAFE.sub("_", s)


def _coerce_scalar_to_str(v: object) -> object:
    """Coerce a bare int/float YAML scalar to its string form.

    Users commonly write unquoted numeric-looking labels (e.g. `system: 1`),
    which YAML parses as a number rather than a string. Lists/dicts are left
    untouched so a genuinely malformed value still fails validation normally.
    """
    if isinstance(v, (int, float)):
        return str(v)
    return v


def _coerce_dict_keys_and_values_to_str(v: object) -> object:
    """Coerce bare int/float YAML dict keys and values to their string form.

    Same motivation as _coerce_scalar_to_str, applied to a whole dict at
    once - e.g. a rating shortcut written as `1: 1` (both key and value
    parsed as YAML numbers) instead of `"1": "1"`. Non-dict input is left
    untouched so a genuinely malformed value still fails validation normally.
    """
    if not isinstance(v, dict):
        return v
    return {
        _coerce_scalar_to_str(k): _coerce_scalar_to_str(val) for k, val in v.items()
    }


def _normalize(p: Path) -> Path:
    """Make absolute and normalize '..' without following symlinks."""
    if not p.is_absolute():
        p = Path.cwd() / p
    return Path(os.path.normpath(p))


def _check_rating_labels_keys(
    rating_labels: dict[str, str] | None, valid_keys: set[str]
) -> None:
    """Reject rating_labels keys outside a test type's actual rating range.

    Without this, a typo'd key (e.g. "33" instead of "3") would silently do
    nothing - the real rating value never gets a label, and the mistake
    surfaces only as a blank button in the UI, not a config error.
    """
    if not rating_labels:
        return
    unknown = sorted(set(rating_labels) - valid_keys)
    if unknown:
        raise PydanticCustomError(
            "rating_labels_unknown_key",
            "rating_labels has key(s) outside the valid rating range "
            "{valid}: {unknown}",
            {"valid": sorted(valid_keys), "unknown": unknown},
        )
