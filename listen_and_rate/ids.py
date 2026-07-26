"""The one rule for identifiers that become file paths, shared by both backends.

`experiment_id` names the results subdirectory and `session_id` names the file
inside it, so both are path components chosen outside this code - the config
author picks one, the browser generates the other and echoes it back at submit
time. Anything not in this character set is REJECTED rather than rewritten:

- Rewriting is not injective. Two experiments named "実験" and "試験" would
  both sanitize to "__" and silently pool their results into one directory,
  which is worse than refusing to start.
- Rewriting also has to agree byte-for-byte between the FastAPI server and the
  PHP deployment, or the same experiment writes to two different directories
  depending on how it was deployed. Rejecting has nothing to agree on beyond
  this pattern.

Mirrored by frontend/save.php's ID_PATTERN/assert_valid_id(). The dot is
allowed so a config named `config.mos.yaml` keeps its natural id.

Note this is a validator, not the id *builder* `config/_utils.py::_safe_id`,
which derives internal stimulus ids by substitution. Its output charset is a
subset of this one, so derived ids always satisfy this rule.
"""

from __future__ import annotations

import re

ID_PATTERN = r"^[A-Za-z0-9._-]+$"

_ID_RE = re.compile(ID_PATTERN)

# Allowing the dot lets these two through, and they are not names but
# directory references. Excluded here rather than by a lookahead in the
# pattern, which pydantic-core's regex engine cannot compile and which PHP
# would have to mirror exactly.
_RESERVED = frozenset({".", ".."})


def is_valid_id(value: str) -> bool:
    """Whether `value` may be used as a results path component."""
    return value not in _RESERVED and bool(_ID_RE.match(value))
