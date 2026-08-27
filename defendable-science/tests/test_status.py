"""The single definition of the status frontmatter block (#120)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
import yaml

from defendable_science.scaffold import status as st

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_render_emits_the_documented_hypothesis_block() -> None:
    assert st.render("hypothesis") == (
        "status:\n"
        "  level: hypothesis\n"
        "  id: null\n"
        "  verdict: pending\n"
        "  readiness: pending\n"
        "  signed-off-by: null\n"
        "  signed-off-date: null\n"
        "  evidence: []\n"
        "  covers: []\n"
        "  load-bearing: null\n"
        "  understanding: {status: pending, unresolved: []}\n"
        "  blockers: []\n"
        "  last-updated: null\n"
    )


def test_render_applies_per_level_defaults() -> None:
    paper = yaml.safe_load(st.render("paper"))["status"]
    assert paper["verdict"] is None
    assert paper["readiness"] == "drafting"

    thesis = yaml.safe_load(st.render("thesis"))["status"]
    assert thesis["verdict"] == "n/a"
    assert thesis["readiness"] is None


def test_render_applies_overrides_in_field_order() -> None:
    text = st.render(
        "hypothesis",
        {
            "id": "2026-03-04-monotone",
            "last-updated": "2026-03-04",
            "verdict": "refuted",
        },
    )
    status = yaml.safe_load(text)["status"]

    assert status["id"] == "2026-03-04-monotone"
    assert status["verdict"] == "refuted"
    assert status["last-updated"] == date(2026, 3, 4)  # YAML types a bare date
    keys = [line.split(":")[0].strip() for line in text.splitlines()[1:]]
    assert keys == list(st.FIELD_ORDER)


def test_render_rejects_an_unknown_level() -> None:
    with pytest.raises(st.StatusError, match="unknown level"):
        st.render("chapter")


def test_render_rejects_an_unknown_field() -> None:
    with pytest.raises(st.StatusError, match="unknown status field"):
        st.render("paper", {"priority": "high"})


def test_render_never_emits_a_placeholder() -> None:
    for level in ("hypothesis", "paper", "thesis"):
        assert "<" not in st.render(level)


def test_parse_returns_the_status_mapping() -> None:
    text = "---\nstatus:\n  level: paper\n  id: x\n---\n\n# Pitch\n"
    assert st.parse(text) == {"level": "paper", "id": "x"}


def test_parse_returns_none_without_frontmatter() -> None:
    assert st.parse("# Pitch\n\nno frontmatter here\n") is None


def test_parse_returns_none_when_frontmatter_is_unterminated() -> None:
    assert st.parse("---\nstatus:\n  level: paper\n") is None


def test_parse_raises_on_invalid_yaml() -> None:
    with pytest.raises(st.StatusError, match="invalid YAML"):
        st.parse("---\nstatus: [unclosed\n---\n")


def test_parse_returns_none_when_there_is_no_status_key() -> None:
    assert st.parse("---\ntitle: x\n---\n") is None


def test_parse_raises_when_status_is_not_a_mapping() -> None:
    with pytest.raises(st.StatusError, match="'status' must be a mapping"):
        st.parse("---\nstatus: draft\n---\n")


# --- the drift guard over every shipped template ----------------------------


def _status_block(text: str) -> str:
    """Return the frontmatter's status block, inline comments and blanks stripped."""
    match = re.search(r"\A---\n(.*?)^---\n", text, re.S | re.M)
    assert match is not None, "no terminated YAML frontmatter"
    lines = []
    for line in match.group(1).splitlines():
        stripped = re.sub(r"\s+#.*$", "", line).rstrip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("relpath", sorted(st.TEMPLATE_FORMS))
def test_every_shipped_template_matches_the_renderer(relpath: str) -> None:
    """The status block is what `progress` projects; a drift makes work vanish.

    Prose deliberately differs — the shipped template is the fuller authoring
    skeleton — but the frontmatter must not, and nothing at runtime can enforce
    that because the wheel ships only ``defendable_science`` (ADR-0026).
    """
    shipped = _REPO_ROOT / "resources" / "templates" / relpath
    assert shipped.is_file(), (
        f"{shipped} is missing; the drift guard cannot run. These tests are meant "
        "to run from a repo checkout, which has both artifacts."
    )
    form = st.TEMPLATE_FORMS[relpath]
    expected = st.render(form["level"], {k: v for k, v in form.items() if k != "level"})

    assert _status_block(shipped.read_text(encoding="utf-8")) == expected


@pytest.mark.parametrize("relpath", sorted(st.TEMPLATE_FORMS))
def test_no_shipped_template_carries_a_placeholder_in_a_machine_read_field(
    relpath: str,
) -> None:
    """`readiness: <synthesis | defensible>` parses as a real value (#121)."""
    shipped = _REPO_ROOT / "resources" / "templates" / relpath
    block = _status_block(shipped.read_text(encoding="utf-8"))
    status = yaml.safe_load(block)["status"]

    placeholders = {
        key: value
        for key, value in status.items()
        if isinstance(value, str) and value.startswith("<")
    }
    assert placeholders == {}
