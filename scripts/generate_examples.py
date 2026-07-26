"""Generate the example configurations from one template plus per-type values.

The eight examples in examples/ are ~75% comments, and about three quarters of
every file is documentation that is word-for-word identical in all eight. Kept
by hand, one wording fix means eight edits, and the files drift apart when one
is missed. So the shared prose lives once, in template.yaml.in, and each test
type supplies only what is actually its own (its heading, instructions, stimuli
layout, rating labels, choice keys) in examples/<type>.yaml next to it.

The generated files stay committed - people copy one and edit it, and it should
be readable straight from the repository. `make examples` regenerates them and
`--check` (wired into `make lint`) fails if a committed file is out of date.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_DIR = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_DIR / "examples"
TYPES_DIR = Path(__file__).resolve().parent / "examples"
TEMPLATE_PATH = TYPES_DIR / "template.yaml.in"

# `{{name}}`, and the same alone on its own (possibly indented) line.
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
_BLOCK_LINE = re.compile(r"([ \t]*)\{\{(\w+)\}\}(\n?)$")


def render(template: str, values: dict[str, str]) -> str:
    """Substitute the template's `{{name}}` placeholders with `values`.

    A placeholder alone on a line stands for a block: the value's lines are
    written at that line's indentation, and an empty value removes the line
    together with the blank line that follows it (so an omitted section leaves
    no hole). Anywhere else the value is substituted inline.

    Raises KeyError for a placeholder with no value and ValueError for a value
    the template never uses - either one means the two files have drifted.
    """
    used: set[str] = set()

    def value_of(name: str) -> str:
        if name not in values:
            raise KeyError(f"template uses {{{{{name}}}}} but no value was given")
        used.add(name)
        return values[name]

    out: list[str] = []
    lines = template.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        block = _BLOCK_LINE.fullmatch(line)
        if block:
            indent, name, newline = block.groups()
            value = value_of(name)
            if not value:
                if i < len(lines) and not lines[i].strip():
                    i += 1
                continue
            body = "\n".join(indent + s if s else s for s in value.split("\n"))
            out.append(body + newline)
        else:
            out.append(_PLACEHOLDER.sub(lambda m: value_of(m.group(1)), line))

    stray = sorted(set(values) - used)
    if stray:
        raise ValueError(f"values the template never uses: {', '.join(stray)}")
    return "".join(out)


def generate(source: Path) -> str:
    """Render the example configuration for the test type described by `source`."""
    values = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    return render(
        TEMPLATE_PATH.read_text(encoding="utf-8"),
        {k: ("" if v is None else str(v).rstrip("\n")) for k, v in values.items()},
    )


def main() -> int:
    """Write the example configurations, or check that they are up to date."""
    parser = argparse.ArgumentParser(
        description="Generate examples/config.*.yaml from scripts/examples/."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit non-zero if any committed example is out of date",
    )
    args = parser.parse_args()

    stale: list[Path] = []
    for source in sorted(TYPES_DIR.glob("*.yaml")):
        target = EXAMPLES_DIR / f"config.{source.stem}.yaml"
        rendered = generate(source)
        if target.exists() and target.read_text(encoding="utf-8") == rendered:
            continue
        if args.check:
            stale.append(target)
        else:
            target.write_text(rendered, encoding="utf-8")
            print(f"wrote {target.relative_to(REPO_DIR)}")

    if stale:
        for target in stale:
            print(f"out of date: {target.relative_to(REPO_DIR)}", file=sys.stderr)
        print("run `make examples`", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
