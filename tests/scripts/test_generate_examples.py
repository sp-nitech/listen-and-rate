from __future__ import annotations

from pathlib import Path

import pytest
from generate_examples import EXAMPLES_DIR, TYPES_DIR, generate, render

REPO = Path(__file__).resolve().parents[2]


def test_render_substitutes_an_inline_placeholder():
    rendered = render("test_type: {{test_type}}\n", {"test_type": "mos"})
    assert rendered == "test_type: mos\n"


def test_render_expands_a_multi_line_value_on_its_own_line():
    template = "a\n{{body}}\nb\n"
    assert render(template, {"body": "one\ntwo"}) == "a\none\ntwo\nb\n"


def test_render_keeps_the_indentation_of_a_multi_line_value():
    template = "instructions: |\n  {{instructions}}\n"
    rendered = render(template, {"instructions": "one\ntwo"})
    assert rendered == "instructions: |\n  one\n  two\n"


def test_render_drops_the_line_and_its_trailing_blank_line_for_an_empty_value():
    template = "a\n\n{{section}}\n\nb\n"
    assert render(template, {"section": ""}) == "a\n\nb\n"


def test_render_rejects_a_placeholder_with_no_value():
    with pytest.raises(KeyError, match="title"):
        render("{{title}}\n", {})


def test_render_rejects_a_value_the_template_never_uses():
    with pytest.raises(ValueError, match="stray"):
        render("{{title}}\n", {"title": "T", "stray": "x"})


@pytest.mark.parametrize("source", sorted(TYPES_DIR.glob("*.yaml")))
def test_committed_example_matches_the_generated_one(source):
    generated = EXAMPLES_DIR / f"config.{source.stem}.yaml"
    assert generated.read_text(encoding="utf-8") == generate(source), (
        f"{generated.relative_to(REPO)} is stale - run `make examples`"
    )


def test_every_committed_example_has_a_source():
    generated = {p.name for p in EXAMPLES_DIR.glob("config.*.yaml")}
    expected = {f"config.{p.stem}.yaml" for p in TYPES_DIR.glob("*.yaml")}
    assert generated == expected
