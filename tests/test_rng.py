from __future__ import annotations

import ast
import random
from pathlib import Path

from listen_and_rate.rng import rng

PACKAGE = Path(__file__).resolve().parents[1] / "listen_and_rate"


def test_rng_is_seeded_from_the_operating_system():
    assert isinstance(rng, random.SystemRandom)


def test_no_module_but_rng_reaches_for_the_stdlib_random_module():
    """One definition of "random" for the whole package.

    Every draw the package makes is a listener-facing randomization - which
    subset a listener gets, what order it comes in, which stimulus the hidden
    X duplicates. Two sources would mean two answers to "how random is this",
    and the ABX one has to be unpredictable (see x_token.py). Mirrors
    frontend/config.php, which draws only through random_int().
    """
    offenders = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.name == "rng.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imports_random = (
                isinstance(node, ast.Import)
                and any(a.name == "random" for a in node.names)
            ) or (isinstance(node, ast.ImportFrom) and node.module == "random")
            if imports_random:
                offenders.append(f"{path.relative_to(PACKAGE)}:{node.lineno}")
    assert offenders == [], f"import listen_and_rate.rng instead: {offenders}"
