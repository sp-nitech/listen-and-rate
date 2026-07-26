"""Reading result files, and checking which release produced them.

Kept apart from report.py, which turns rows into figures: this is about
getting rows out of files and refusing the ones that cannot be combined. The
version check lives here because it is the reader that knows which file each
version came from.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .. import __version__
from ..storage import (
    METADATA_COLUMN_PREFIX,
    SURVEY_COLUMN_PREFIX,
    TOOL_VERSION_COLUMN,
)

logger = logging.getLogger(__name__)

# What a result file says when it was written before the version was recorded.
UNKNOWN_VERSION = "unknown"

# How many file names a version-mismatch message lists before summarizing. A
# study has one file per listener, and naming all of them would bury the
# sentence that explains what to do.
_NAMES_SHOWN = 3


class ResultVersionMismatch(ValueError):
    """Result files were produced by different releases of the tool."""


def _read_result_file(path):
    """Read one result file (CSV or JSON) into a DataFrame of rows."""
    import pandas as pd

    path = Path(path)
    if path.suffix.lower() != ".json":
        # The version is text. Left to infer, pandas reads "1.10" as the float
        # 1.1 and the release comparison would be against a version that never
        # existed. A dtype for a column the file does not have is ignored.
        return pd.read_csv(path, dtype={TOOL_VERSION_COLUMN: str})

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    for r in data.get("records", []):
        row: dict = {
            TOOL_VERSION_COLUMN: data.get(TOOL_VERSION_COLUMN, ""),
            "session_id": data.get("session_id", ""),
            "timestamp": data.get("timestamp", ""),
            "test_type": data.get("test_type", ""),
            **r,
        }
        # Flatten the nested form objects into the same prefixed columns CSV
        # results carry, so filters and the Participants section behave
        # identically for both formats.
        for k, v in _form_object(data, "metadata").items():
            row[METADATA_COLUMN_PREFIX + k] = v
        for k, v in _form_object(data, "survey").items():
            row[SURVEY_COLUMN_PREFIX + k] = v
        rows.append(row)
    return pd.DataFrame(rows)


def _form_object(data: dict, key: str) -> dict:
    """Read a stored metadata/survey object, tolerating PHP's empty-list form.

    PHP cannot tell an empty list from an empty map, so json_encode writes
    "metadata": [] where the Python saver writes {}. save.php now writes an
    object, but files from before that are already on disk.
    """
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _versions_in(df) -> set[str]:
    """Return the tool versions a file records, or {"unknown"} when it has none."""
    if TOOL_VERSION_COLUMN not in df.columns:
        return {UNKNOWN_VERSION}
    found = {str(v).strip() for v in df[TOOL_VERSION_COLUMN].dropna()}
    return {v for v in found if v} or {UNKNOWN_VERSION}


def _summarize(names: set[str]) -> str:
    """List a few file names, then say how many were left out."""
    shown = sorted(names)[:_NAMES_SHOWN]
    rest = len(names) - len(shown)
    return ", ".join(shown) + (f", and {rest} more" if rest else "")


def _release(version: str) -> str:
    """Return the major.minor part of a version, the part that has to match.

    A patch release fixes behaviour without changing what a column means, so
    results from 0.2.1 and 0.2.7 combine safely.
    """
    parts = version.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else version


def result_versions(paths) -> set[str]:
    """Return the tool versions recorded across these result files.

    A file that cannot be read contributes nothing. This runs on the failure
    path, where raising would replace the real error with a worse one.
    """
    found: set[str] = set()
    for path in paths:
        try:
            found |= _versions_in(_read_result_file(path))
        except Exception:  # noqa: BLE001 - any unreadable file is simply unknown
            continue
    return found


def _check_tool_versions(by_file: dict) -> None:
    """Refuse result files that disagree, and warn when they predate this tool.

    Combining files from two releases is not a near miss to warn about. A
    renamed column reads as missing, so those rows are dropped from the report
    without a word, and a column that changed meaning is averaged in as if it
    had not. Both produce a plausible-looking report that is wrong.
    """
    by_release: dict[str, set[str]] = {}
    for path, versions in by_file.items():
        for version in versions:
            by_release.setdefault(_release(version), set()).add(Path(path).name)

    if len(by_release) > 1:
        listing = ", ".join(
            f"{release} ({_summarize(names)})"
            for release, names in sorted(by_release.items())
        )
        raise ResultVersionMismatch(
            f"Result files disagree on the version that produced them: {listing}. "
            "Mixing them would silently drop or misread rows. "
            "Analyze each version's results separately."
        )

    warning = _older_release_warning(by_file)
    if warning:
        logger.warning("%s", warning)


def _older_release_warning(by_file: dict) -> str | None:
    """Describe how these results differ from this release, or return None.

    A file with no version column was written before the version was recorded,
    which makes it older than anything that does record one. Those are the
    results most likely to have drifted, so they get a warning of their own
    rather than the silence "unknown" would otherwise buy them.
    """
    recorded = sorted({v for versions in by_file.values() for v in versions})
    if not recorded:
        return None
    if UNKNOWN_VERSION in recorded:
        return (
            "These results do not record which version of listen-and-rate "
            f"produced them, so they come from a release older than this one "
            f"({__version__}). Column meanings may have changed since. Check "
            "the release notes if the numbers look wrong."
        )
    if _release(recorded[0]) == _release(__version__):
        return None
    return (
        f"These results were produced by listen-and-rate {', '.join(recorded)}, "
        f"but this is {__version__}. Column meanings may have changed since. "
        "Check the release notes if the numbers look wrong."
    )


def version_difference_note(paths) -> str | None:
    """Explain that a version difference may be behind a failure, or return None.

    Returned only when the results come from another release, so a failure
    that has nothing to do with the version says nothing about it.
    """
    recorded = sorted(result_versions(paths))
    if not recorded:
        return None
    if UNKNOWN_VERSION in recorded:
        produced = (
            "These results do not record which version of listen-and-rate "
            f"produced them, so they come from a release older than this one "
            f"({__version__})."
        )
    elif _release(recorded[0]) != _release(__version__):
        produced = (
            f"These results were produced by listen-and-rate "
            f"{', '.join(recorded)}, but this is {__version__}."
        )
    else:
        return None
    return (
        f"{produced} The failure above may come from that difference rather "
        "than from the data."
    )
