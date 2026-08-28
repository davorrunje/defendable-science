"""Plugin-content guards. Run from a repo checkout, which has both artifacts.

These assert on the plugin's markdown rather than on the package, following the
precedent of the template drift guard in ``tests/test_status.py``: the wheel
ships only ``defendable_science``, so nothing at runtime can enforce these.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS = sorted((_REPO_ROOT / "skills").glob("*/SKILL.md"))

#: A concrete path is allowed when the line labels it as illustrative.
_ALLOWED = re.compile(r"for illustration|illustration:|default layout|e\.g\.|<!--")


def _prose_offenders(text: str) -> list[tuple[int, str]]:
    """Return (line number, line) for each hard-coded research path in prose.

    Tracks fence state (```) to skip lines inside fenced code blocks.
    Allows lines matching _ALLOWED pattern.

    :param text: The markdown text to scan.
    :returns: List of (line_number, line_text) tuples for offending lines.
    """
    offenders = []
    in_fence = False

    for n, line in enumerate(text.splitlines(), 1):
        # Track fence state (```)
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue

        # Skip if inside a fence or if the line is allowed
        if in_fence or _ALLOWED.search(line):
            continue

        # Check for hard-coded paths
        if "docs/research/" in line:
            offenders.append((n, line.strip()))

    return offenders


@pytest.mark.parametrize("skill", _SKILLS, ids=lambda p: p.parent.name)
def test_no_skill_hard_codes_the_research_tree(skill: Path) -> None:
    """The layout has one definition; a tenth prose copy is how it drifted."""
    text = skill.read_text(encoding="utf-8")
    offenders = _prose_offenders(text)

    # Format offenders as "file:line: text" for error message
    formatted = [
        f"{skill.relative_to(_REPO_ROOT)}:{n}: {line}" for n, line in offenders
    ]

    assert formatted == [], "\n".join(formatted)


def test_the_guard_actually_has_skills_to_check() -> None:
    """A glob that silently matched nothing would make the guard vacuous."""
    assert len(_SKILLS) >= 8


def test_guard_allows_paths_in_fenced_blocks() -> None:
    """Paths inside fenced code blocks are allowed, prose paths are not."""
    content = """# Example Skill

Here is a path in prose: docs/research/paper.md

```bash
# This path is in a fence: docs/research/paper.md
cd docs/research
```

This path is again in prose: docs/research/hypothesis.md

```python
# Another fenced path: docs/research/hypothesis.md
path = "docs/research/hypothesis.md"
```
"""

    prose_offenders = _prose_offenders(content)

    # Should have found the two prose paths (lines 3 and 10)
    assert len(prose_offenders) == 2
    assert prose_offenders[0][0] == 3
    assert prose_offenders[1][0] == 10

    # The fenced paths should NOT be in the offenders
    offender_lines = [n for n, _ in prose_offenders]
    assert 6 not in offender_lines  # line 6 is inside fence (lines 5-8)
    assert 14 not in offender_lines  # line 14 is inside fence (lines 12-15)
