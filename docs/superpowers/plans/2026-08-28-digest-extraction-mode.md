# Digest Extraction Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `digest` a breadth mode that fills a concept-matrix row per paper from `positioning.md`'s own comparison axes, with an enforced per-cell locator and a human-verified deterministic sample — so a 40-paper survey is tractable without pretending it was read at depth.

**Architecture:** Promote the host-preserving markdown-table core out of `exploration/backlog.py` into `core/mdtable.py`, then build a pure validation library on top of it (axes, cells, locators). A new `digest` CLI group fuses validation to writing so no path records an unvalidated cell. Extraction writes `status.extraction` — never `status.understanding` — and the concept-matrix row is a *projection* of durable per-paper cells, not an independently authored artifact.

**Tech Stack:** Python 3.11+, Typer, `pyyaml`, pytest with a 100% statement+branch coverage gate. No new runtime dependencies.

**Spec:** [`docs/superpowers/specs/2026-08-28-digest-extraction-mode-design.md`](../specs/2026-08-28-digest-extraction-mode-design.md) — read it first; this plan argues from it and cites its sections.

## Global Constraints

- **All package work runs from the `defendable-science/` subdirectory.** Every `uv run` command assumes that cwd.
- **100% statement + branch coverage is a hard gate** (`fail_under = 100`, ADR-0028). `# pragma: no cover` only for genuinely unreachable code, with a stated reason. Five pragmas exist in the package and all predate this work — add none.
- Python 3.11+, line length 88, strict mypy, `ruff check` + `ruff format` clean.
- **MyST field-list docstrings** on every public API (`:param:` / `:returns:` / `:raises:`; types come from annotations, never repeated in prose).
- **stdlib `dataclasses` for value objects. Pydantic is deliberately rejected** — do not reintroduce it.
- **No new runtime dependencies.**
- **Failure honesty:** never let a failure or uncertain condition be reported as a legitimate empty/negative/complete result. Distinguish "failed" from "legitimately empty"; no raw tracebacks at the CLI boundary.
- **Domain-neutrality:** no ML-, venue-, or consumer-specific assumptions in shipped code. The locator pattern set ships as a *default* and is configurable for exactly this reason (spec §3.4).
- **Never commit to `main`.** Work continues on `skills/digest-extraction-mode`.
- **Commits:** author `Davor Runje <davor@synthpop.ai>`, `--no-gpg-sign` (mandated by `.claude/skills/create-pr/STYLE.md` — SSH signing is unavailable in these sessions), and a `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` trailer.
- **Exit codes:** `0` success, `1` anything rejected or incomplete, `2` reserved for Click/Typer usage errors. Do not reuse `2` for a domain outcome — #106/#119 was exactly that mistake and it cost a PR to undo.

## Resolved during planning — a gap in the spec

Spec §6.1 says the axes come from "`positioning.md`'s matrix header". It does not say *which* table. `_parse_document` locates the **first** table in a document, and a real `positioning.md` may grow others. Extraction targeting the wrong table would be silent and awful.

**Resolution:** the promoted `parse_document` gains an optional `under_heading` parameter that bounds the search to one section. Extraction always passes `under_heading="Concept matrix"`. This is additive — `backlog.py` passes nothing and is unaffected.

## File structure

| File | Responsibility |
|---|---|
| `defendable_science/core/mdtable.py` | **NEW.** Host-preserving markdown-table parse/render/splice. Promoted from `backlog.py`, plus `under_heading`. |
| `defendable_science/exploration/backlog.py` | **MODIFY.** Re-imports the promoted names; backlog logic untouched. |
| `defendable_science/digest/__init__.py` | **NEW.** Package docstring only. |
| `defendable_science/digest/extraction.py` | **NEW.** Axes derivation, `Cell`, locator patterns, validation. Pure — no I/O. |
| `defendable_science/digest/artifact.py` | **NEW.** `status.extraction` patching, cells persistence, log entries. |
| `defendable_science/digest/render.py` | **NEW.** The `positioning.md` matrix merge. |
| `defendable_science/digest/sampling.py` | **NEW.** Deterministic sample selection. |
| `defendable_science/defend/record.py` | **MODIFY.** Generalise `_append_log` so one writer owns the log directory. |
| `defendable_science/cli.py` | **MODIFY.** New `digest` Typer group with four subcommands. |
| `skills/digest/SKILL.md`, `skills/progress/SKILL.md` | **MODIFY.** Two contracts, the guardrail carve-out, the tier ladder, the second progress row. |

## PR boundaries

- **PR 1 — table core promotion:** Task 1. Review criterion: `backlog` behaviour unchanged.
- **PR 2 — validation library:** Tasks 2–3. Pure, no writes, exhaustively testable.
- **PR 3 — artifact + CLI:** Tasks 4–6.
- **PR 4 — sampling, render, docs:** Tasks 7–10.

---

## Task 1: Promote the markdown-table core to `core/mdtable.py`

**Files:**
- Create: `defendable_science/core/mdtable.py`
- Create: `tests/test_mdtable.py`
- Modify: `defendable_science/exploration/backlog.py`
- Modify: `tests/test_backlog.py` (only if a test reaches a moved private name)

**Interfaces:**
- Consumes: nothing.
- Produces: `Row = dict[str, str]`; `@dataclass Document(preamble: str = "", header: list[str] | None = None, rows: list[Row] = [], postamble: str = "", saw_table_shape: bool = False)`; `escape_cell(cell: str) -> str`; `split_cells(line: str) -> list[str]`; `is_separator(cells: list[str]) -> bool`; `parse_document(text: str, *, under_heading: str | None = None) -> Document`; `render_table(header: list[str], rows: list[Row]) -> str`; `splice(preamble: str, postamble: str, header: list[str], rows: list[Row]) -> str`.

> **Why this is a promotion and not a copy.** #94 and #95 were both bugs in this exact machinery — a writer that discarded surrounding prose, and one that hardcoded a column schema. They are fixed. Copying the code into a second module is how that class of bug gets reintroduced in a place nobody thinks to check. One implementation, two consumers.

- [ ] **Step 1: Move the code verbatim**

Create `defendable_science/core/mdtable.py` with this module docstring, then move `Row`, `_Document`, `_escape`, `_split_cells`, `_is_separator`, `_collect_rows`, `_parse_document`, `_render_table`, `_splice` out of `exploration/backlog.py` **unchanged**, renaming the public ones by dropping the leading underscore (`_Document` → `Document`, `_escape` → `escape_cell`, `_split_cells` → `split_cells`, `_is_separator` → `is_separator`, `_parse_document` → `parse_document`, `_render_table` → `render_table`, `_splice` → `splice`). Keep `_collect_rows` private.

```python
"""Host-preserving markdown-table I/O (GFM), shared across front-ends.

A table lives inside a document a human wrote. This module reads the table
without losing the prose around it and writes it back without touching
anything it did not author — the property issues #94 and #95 were filed for
when an earlier writer discarded the host document and hardcoded a column
schema. Columns are read from the file's own header, never assumed.
"""
```

- [ ] **Step 2: Re-import in `backlog.py`**

Replace the moved definitions with explicit re-exports. The `X as X` form is **required** — strict mypy's `no_implicit_reexport` rejects the plain form for names other modules reach through this one:

```python
from defendable_science.core.mdtable import Document as Document
from defendable_science.core.mdtable import Row as Row
from defendable_science.core.mdtable import escape_cell as escape_cell
from defendable_science.core.mdtable import is_separator as is_separator
from defendable_science.core.mdtable import parse_document as parse_document
from defendable_science.core.mdtable import render_table as render_table
from defendable_science.core.mdtable import splice as splice
from defendable_science.core.mdtable import split_cells as split_cells
```

Update `backlog.py`'s internal call sites to the new names. If ruff reports `F401` for any name, it is genuinely unused there — delete it from the import rather than adding a `noqa`.

- [ ] **Step 3: Run the existing suite — `backlog` behaviour must be unchanged**

Run: `uv run pytest tests/test_backlog.py -q`
Expected: PASS with no test modified. If a test fails because it reached a moved private name, update only the name it reaches — never an assertion.

- [ ] **Step 4: Write the failing test for `under_heading`**

Create `tests/test_mdtable.py`:

```python
"""Tests for the shared host-preserving markdown-table core."""

from __future__ import annotations

from defendable_science.core import mdtable as md

TWO_TABLES = """# Positioning

## Baselines

| Baseline | Why |
|---|---|
| ridge | simplest floor |

## Concept matrix

<!-- rows = methods -->

| Method | guarantee | scope |
|---|---|---|
| sill1997 | architectural | full |

## Notes

trailing prose
"""


def test_parse_document_takes_the_first_table_by_default() -> None:
    doc = md.parse_document(TWO_TABLES)
    assert doc.header == ["Baseline", "Why"]


def test_under_heading_targets_that_section_s_table() -> None:
    doc = md.parse_document(TWO_TABLES, under_heading="Concept matrix")
    assert doc.header == ["Method", "guarantee", "scope"]
    assert doc.rows == [{"Method": "sill1997", "guarantee": "architectural",
                         "scope": "full"}]


def test_under_heading_round_trips_the_whole_document() -> None:
    doc = md.parse_document(TWO_TABLES, under_heading="Concept matrix")
    assert doc.header is not None
    out = md.splice(doc.preamble, doc.postamble, doc.header, doc.rows)
    assert out == TWO_TABLES


def test_under_heading_preserves_the_other_table_verbatim() -> None:
    doc = md.parse_document(TWO_TABLES, under_heading="Concept matrix")
    assert "| ridge | simplest floor |" in doc.preamble
    assert "trailing prose" in doc.postamble


def test_under_heading_absent_yields_no_table() -> None:
    doc = md.parse_document(TWO_TABLES, under_heading="Nonexistent")
    assert doc.header is None
    assert doc.preamble == TWO_TABLES


def test_under_heading_section_with_no_table_yields_no_table() -> None:
    doc = md.parse_document(TWO_TABLES, under_heading="Notes")
    assert doc.header is None


def test_under_heading_stops_at_the_next_heading() -> None:
    text = "## A\n\nprose\n\n## B\n\n| X |\n|---|\n| 1 |\n"
    assert md.parse_document(text, under_heading="A").header is None
    assert md.parse_document(text, under_heading="B").header == ["X"]


def test_under_heading_matches_any_heading_level() -> None:
    text = "### Concept matrix\n\n| M |\n|---|\n| a |\n"
    assert md.parse_document(text, under_heading="Concept matrix").header == ["M"]
```

- [ ] **Step 5: Run to verify it fails**

Run: `uv run pytest tests/test_mdtable.py -v --no-cov`
Expected: the `under_heading` tests FAIL with `TypeError: parse_document() got an unexpected keyword argument 'under_heading'`.

- [ ] **Step 6: Implement `under_heading`**

Bound the existing scan to one section rather than slicing the text, so `preamble`/`postamble` still cover the whole document and `splice` round-trips unchanged:

```python
_HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")


def _section_bounds(lines: list[str], title: str) -> tuple[int, int] | None:
    """Return ``(start, end)`` line indices for the section under `title`.

    The section runs from the line after its heading to the line before the
    next heading of any level, or to the end of the document.

    :param lines: The document's lines.
    :param title: The heading text to find, compared case-insensitively.
    :returns: The bounds, or ``None`` when no such heading exists.
    """
    want = title.strip().casefold()
    start: int | None = None
    for i, line in enumerate(lines):
        match = _HEADING.match(line)
        if match is None:
            continue
        if start is not None:
            return start, i
        if match.group("title").strip().casefold() == want:
            start = i + 1
    return None if start is None else (start, len(lines))
```

Then give `parse_document` the parameter, defaulting the window to the whole document:

```python
def parse_document(text: str, *, under_heading: str | None = None) -> Document:
    """Locate the markdown table in `text`, keeping the prose around it.

    :param text: The host document.
    :param under_heading: When given, only consider a table inside the section
        under that heading. A document may hold several tables, and the caller
        usually means one of them specifically.
    :returns: The located document; ``header`` is ``None`` when the window
        holds no table, in which case `preamble` is the whole of `text`.
    """
    lines = text.splitlines(keepends=True)
    window = (0, len(lines))
    if under_heading is not None:
        bounds = _section_bounds(lines, under_heading)
        if bounds is None:
            return Document(preamble=text)
        window = bounds
    # …existing scan, but iterating only over lines[window[0]:window[1]] and
    # offsetting the indices it records by window[0], so preamble/postamble are
    # still measured against the whole document.
```

Keep the body's existing logic; only the iteration bounds and index offset change.

- [ ] **Step 7: Run to verify it passes**

Run: `uv run pytest tests/test_mdtable.py tests/test_backlog.py -v --no-cov`
Expected: PASS, both files.

- [ ] **Step 8: Full gate**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: PASS, coverage 100%.

- [ ] **Step 9: Commit**

```bash
git add defendable_science/core/mdtable.py defendable_science/exploration/backlog.py tests/test_mdtable.py
git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" commit --no-gpg-sign -m "refactor(core): promote the markdown-table core to core/mdtable.py

One host-preserving table implementation, two consumers. #94 and #95 were both
bugs in this machinery; copying it into a second module is how that class comes
back somewhere nobody checks.

Adds an additive under_heading parameter: a document may hold several tables
and a caller usually means one specifically. backlog passes nothing.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Derive the question set from the concept matrix

**Files:**
- Create: `defendable_science/digest/__init__.py` (docstring only)
- Create: `defendable_science/digest/extraction.py`
- Create: `tests/test_extraction.py`

**Interfaces:**
- Consumes: `parse_document`, `Document` from Task 1.
- Produces: `class ExtractionError(ValueError)`; `PLACEHOLDER_RE: re.Pattern[str]`; `CONCEPT_MATRIX_HEADING = "Concept matrix"`; `SELF_ROW = "**This paper**"`; `def axes_from_positioning(path: str | Path) -> list[str]`.

> **The two refusals are the point of this task.** `positioning.md` ships `| Method | <attr 1> | <attr 2> | <attr 3> |`. Extracting 40 papers against `<attr 1>` would produce 320 confidently-shaped, meaningless cells. Refusing costs the author one message; not refusing costs them the run.

- [ ] **Step 1: Write the failing test**

Create `tests/test_extraction.py`:

```python
"""Tests for extraction's pure library: axes, cells, locators, validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from defendable_science.digest import extraction as ex

REAL = """## Concept matrix

<!-- rows = methods -->

| Method | guarantee type | scope | verifiability |
|---|---|---|---|
| *<prior work>* | | | |
| **This paper** | | | |
"""

TEMPLATE = """## Concept matrix

| Method | <attr 1> | <attr 2> | <attr 3> |
|---|---|---|---|
| **This paper** | | | |
"""


def _write(tmp_path: Path, text: str) -> Path:
    target = tmp_path / "positioning.md"
    target.write_text(text, encoding="utf-8")
    return target


def test_axes_are_the_header_minus_the_row_label(tmp_path: Path) -> None:
    assert ex.axes_from_positioning(_write(tmp_path, REAL)) == [
        "guarantee type", "scope", "verifiability"
    ]


def test_unreplaced_placeholders_refuse(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="placeholder"):
        ex.axes_from_positioning(_write(tmp_path, TEMPLATE))


def test_one_replaced_axis_still_refuses_if_others_are_placeholders(
    tmp_path: Path,
) -> None:
    text = TEMPLATE.replace("<attr 1>", "guarantee type")
    with pytest.raises(ex.ExtractionError, match="placeholder"):
        ex.axes_from_positioning(_write(tmp_path, text))


def test_no_concept_matrix_section_refuses(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="no 'Concept matrix'"):
        ex.axes_from_positioning(_write(tmp_path, "## Baselines\n\nprose\n"))


def test_section_present_but_no_table_refuses(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="no table"):
        ex.axes_from_positioning(_write(tmp_path, "## Concept matrix\n\nTBD\n"))


def test_header_with_only_a_row_label_refuses(tmp_path: Path) -> None:
    text = "## Concept matrix\n\n| Method |\n|---|\n| a |\n"
    with pytest.raises(ex.ExtractionError, match="no comparison axes"):
        ex.axes_from_positioning(_write(tmp_path, text))


def test_missing_file_refuses_actionably(tmp_path: Path) -> None:
    with pytest.raises(ex.ExtractionError, match="not found"):
        ex.axes_from_positioning(tmp_path / "absent.md")


def test_duplicate_axis_names_refuse(tmp_path: Path) -> None:
    text = "## Concept matrix\n\n| Method | a | a |\n|---|---|---|\n| x | | |\n"
    with pytest.raises(ex.ExtractionError, match="duplicate"):
        ex.axes_from_positioning(_write(tmp_path, text))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_extraction.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'defendable_science.digest'`

- [ ] **Step 3: Implement**

Create `defendable_science/digest/__init__.py`:

```python
"""Reading an external paper: depth-first comprehension, and breadth extraction."""
```

Create `defendable_science/digest/extraction.py`:

```python
"""Extraction mode's pure library — axes, cells, locators, validation.

No I/O beyond reading the positioning document: everything here is a function
of its inputs, so the rules can be tested exhaustively without touching a
registry, a PDF, or an artifact. The writer that fuses validation to recording
lives in :mod:`defendable_science.digest.artifact`; nothing here writes.

Design: ``docs/superpowers/specs/2026-08-28-digest-extraction-mode-design.md``.
"""

from __future__ import annotations

import re
from pathlib import Path

from defendable_science.core.mdtable import parse_document

#: The heading whose table holds the comparison axes.
CONCEPT_MATRIX_HEADING = "Concept matrix"

#: The matrix's self-reference row — the author's own delta, never a paper.
SELF_ROW = "**This paper**"

#: An unreplaced template placeholder, e.g. ``<attr 1>`` or ``<prior work>``.
PLACEHOLDER_RE = re.compile(r"^<[^>]*>$")


class ExtractionError(ValueError):
    """Raised when extraction cannot proceed and must not guess."""


def axes_from_positioning(path: str | Path) -> list[str]:
    """Read the comparison axes from a positioning document's concept matrix.

    The axes are the matrix header minus its first column, which labels the
    row rather than naming an attribute.

    :param path: The positioning document.
    :returns: The axes, in the matrix's own column order.
    :raises ExtractionError: If the file is missing; if it has no
        ``Concept matrix`` section, or that section has no table; if the
        header carries unreplaced template placeholders; if there are no
        axes beyond the row label; or if two axes share a name.
    """
    target = Path(path)
    if not target.is_file():
        raise ExtractionError(f"{target}: positioning document not found")
    text = target.read_text(encoding="utf-8")
    doc = parse_document(text, under_heading=CONCEPT_MATRIX_HEADING)
    if doc.header is None:
        if f"# {CONCEPT_MATRIX_HEADING}" not in text:
            raise ExtractionError(
                f"{target}: no '{CONCEPT_MATRIX_HEADING}' section — run "
                "`literature position --level paper` first"
            )
        raise ExtractionError(
            f"{target}: the '{CONCEPT_MATRIX_HEADING}' section holds no table"
        )
    axes = [c.strip() for c in doc.header[1:]]
    placeholders = [a for a in axes if PLACEHOLDER_RE.match(a)]
    if placeholders:
        raise ExtractionError(
            f"{target}: the concept matrix still carries template "
            f"placeholders {placeholders} — replace them with the attributes "
            "your delta turns on before extracting against them"
        )
    if not axes:
        raise ExtractionError(
            f"{target}: the concept matrix has no comparison axes, only a "
            "row label"
        )
    seen = {a for a in axes}
    if len(seen) != len(axes):
        raise ExtractionError(f"{target}: duplicate axis names in {axes}")
    return axes
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_extraction.py -v --no-cov`
Expected: PASS (8 tests)

- [ ] **Step 5: Confirm module coverage**

Run: `uv run pytest tests/test_extraction.py --cov=defendable_science.digest.extraction --cov-branch --cov-report=term-missing --no-cov-on-fail`
Expected: 100%. Any uncovered branch is a refusal with no test — add the test, not a pragma.

- [ ] **Step 6: Commit**

```bash
git add defendable_science/digest tests/test_extraction.py
git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" commit --no-gpg-sign -m "feat(digest): derive extraction's question set from the concept matrix

Refuses on unreplaced template placeholders. Extracting 40 papers against
'<attr 1>' would produce 320 confidently-shaped meaningless cells; refusing
costs the author one message.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Cells, locator patterns, and the validation rules

**Files:**
- Modify: `defendable_science/digest/extraction.py`
- Modify: `tests/test_extraction.py`

**Interfaces:**
- Consumes: `ExtractionError`, `axes_from_positioning` from Task 2.
- Produces:
  - `NOT_ADDRESSED = "not-addressed"`
  - `DEFAULT_LOCATOR_PATTERNS: tuple[str, ...]`
  - `@dataclass(frozen=True) class Cell: citekey: str; axis: str; value: str; locator: str | None = None; justification: str | None = None`
  - `def cell_from_mapping(item: Mapping[str, Any]) -> Cell`
  - `def compile_locator_patterns(extra: list[str] | None = None) -> list[re.Pattern[str]]`
  - `def is_valid_locator(locator: str, patterns: list[re.Pattern[str]]) -> bool`
  - `@dataclass class Rejection: citekey: str; axis: str | None; reason: str`
  - `def validate(cells: list[Cell], axes: list[str], patterns: list[re.Pattern[str]]) -> tuple[dict[str, list[Cell]], list[Rejection]]` — returns accepted cells grouped by citekey, and rejections. **A citekey with any rejection appears in neither group's accepted map** (spec §7.2 rule 4: rejection is per paper, whole).

> **Rule 2 is the one to get right.** Requiring *every* axis to be present is what makes `not-addressed` necessary at all. Without it an agent that finds an axis hard simply omits the cell, and a short row looks like a clean row. With it, the dodge is forced into `not-addressed`, which is counted and visible.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_extraction.py`:

```python
AXES = ["guarantee type", "scope"]


def _cell(**kw: object) -> ex.Cell:
    base: dict[str, object] = {
        "citekey": "sill1997", "axis": "guarantee type",
        "value": "architectural", "locator": "§2, Eq. (3)",
    }
    base.update(kw)
    return ex.Cell(**base)  # type: ignore[arg-type]


def _full(citekey: str = "sill1997") -> list[ex.Cell]:
    return [
        _cell(citekey=citekey, axis="guarantee type"),
        _cell(citekey=citekey, axis="scope", locator="p. 4"),
    ]


PATTERNS = ex.compile_locator_patterns()


@pytest.mark.parametrize(
    "locator",
    ["§3", "§3.2", "§3.2.1", "Section 3", "Sec. 3", "p. 7", "pp. 7-9",
     "page 7", "Eq. (4)", "Equation 4", "Table 2", "Fig. 5", "Figure 5",
     "Alg. 1", "Thm. 2", "Theorem 2", "Lemma 3", "Def. 1", "§3, Eq. (4)",
     "p. 7, Table 2"],
)
def test_well_formed_locators_are_accepted(locator: str) -> None:
    assert ex.is_valid_locator(locator, PATTERNS)


@pytest.mark.parametrize(
    "locator",
    ["see paper", "somewhere in §3", "the introduction", "passim", "",
     "   ", "throughout", "as discussed"],
)
def test_vague_locators_are_refused(locator: str) -> None:
    assert not ex.is_valid_locator(locator, PATTERNS)


def test_extra_patterns_extend_the_default_set() -> None:
    patterns = ex.compile_locator_patterns([r"cl\. \d+"])
    assert ex.is_valid_locator("cl. 14", patterns)
    assert ex.is_valid_locator("§3", patterns)


def test_a_complete_paper_is_accepted() -> None:
    accepted, rejections = ex.validate(_full(), AXES, PATTERNS)
    assert rejections == []
    assert sorted(c.axis for c in accepted["sill1997"]) == ["guarantee type", "scope"]


def test_a_missing_axis_rejects_the_whole_paper() -> None:
    accepted, rejections = ex.validate(_full()[:1], AXES, PATTERNS)
    assert accepted == {}
    assert any("scope" in r.reason and "missing" in r.reason for r in rejections)


def test_an_invented_axis_rejects_the_whole_paper() -> None:
    cells = [*_full(), _cell(axis="made up", locator="§9")]
    accepted, rejections = ex.validate(cells, AXES, PATTERNS)
    assert accepted == {}
    assert any("not a matrix axis" in r.reason for r in rejections)


def test_a_bad_locator_rejects_the_whole_paper_not_just_the_cell() -> None:
    cells = [_cell(), _cell(axis="scope", locator="see paper")]
    accepted, rejections = ex.validate(cells, AXES, PATTERNS)
    assert accepted == {}
    assert any("see paper" in r.reason for r in rejections)


def test_one_bad_paper_does_not_reject_a_good_one() -> None:
    cells = [*_full("good"), *_full("bad")[:1]]
    accepted, rejections = ex.validate(cells, AXES, PATTERNS)
    assert set(accepted) == {"good"}
    assert {r.citekey for r in rejections} == {"bad"}


def test_not_addressed_needs_a_justification_not_a_locator() -> None:
    cells = [
        _cell(),
        _cell(axis="scope", value=ex.NOT_ADDRESSED, locator=None,
              justification="scoped to full monotonicity in §1"),
    ]
    accepted, rejections = ex.validate(cells, AXES, PATTERNS)
    assert rejections == []
    assert len(accepted["sill1997"]) == 2


def test_not_addressed_without_a_justification_is_rejected() -> None:
    cells = [_cell(), _cell(axis="scope", value=ex.NOT_ADDRESSED, locator=None)]
    _, rejections = ex.validate(cells, AXES, PATTERNS)
    assert any("justification" in r.reason for r in rejections)


def test_not_addressed_with_a_blank_justification_is_rejected() -> None:
    cells = [_cell(), _cell(axis="scope", value=ex.NOT_ADDRESSED, locator=None,
                            justification="   ")]
    _, rejections = ex.validate(cells, AXES, PATTERNS)
    assert any("justification" in r.reason for r in rejections)


def test_a_normal_cell_with_no_locator_is_rejected() -> None:
    cells = [_cell(), _cell(axis="scope", locator=None)]
    _, rejections = ex.validate(cells, AXES, PATTERNS)
    assert any("locator" in r.reason for r in rejections)


def test_a_duplicated_axis_for_one_paper_is_rejected() -> None:
    cells = [*_full(), _cell(axis="scope", locator="p. 9")]
    _, rejections = ex.validate(cells, AXES, PATTERNS)
    assert any("twice" in r.reason for r in rejections)


def test_cell_from_mapping_rejects_a_non_string_field() -> None:
    with pytest.raises(ex.ExtractionError, match="citekey"):
        ex.cell_from_mapping({"citekey": 7, "axis": "a", "value": "v"})


def test_cell_from_mapping_rejects_an_unknown_field() -> None:
    with pytest.raises(ex.ExtractionError, match="unknown"):
        ex.cell_from_mapping(
            {"citekey": "k", "axis": "a", "value": "v", "bogus": "x"}
        )
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_extraction.py -v --no-cov`
Expected: FAIL — `AttributeError: module ... has no attribute 'compile_locator_patterns'`

- [ ] **Step 3: Implement**

Append to `defendable_science/digest/extraction.py`. Anchor every pattern with `\A…\Z` so `"somewhere in §3"` cannot pass on a partial match — that is the whole point of shape validation:

```python
#: The distinguished value for an axis the paper does not address.
NOT_ADDRESSED = "not-addressed"

#: Locator forms accepted out of the box. Extended or replaced via
#: ``literature.extraction.locator_patterns`` — a set built around §/Eq./Thm.
#: encodes one citation culture, and this plugin forbids domain assumptions.
DEFAULT_LOCATOR_PATTERNS: tuple[str, ...] = (
    r"§\s*\d+(\.\d+)*",
    r"(Section|Sec\.)\s*\d+(\.\d+)*",
    r"(pp?\.|pages?)\s*\d+(\s*[-–]\s*\d+)?",
    r"(Eq\.|Equation)\s*\(?\d+\)?",
    r"(Table|Tbl\.)\s*\d+",
    r"(Fig\.|Figure)\s*\d+",
    r"(Alg\.|Algorithm)\s*\d+",
    r"(Thm\.|Theorem|Lemma|Cor\.|Corollary|Def\.|Definition|Prop\.|Proposition)\s*\d+",
)
```

`compile_locator_patterns(extra)` compiles each default plus each extra into a **comma-joinable** anchored alternation, so `"§3, Eq. (4)"` passes while `"somewhere in §3"` does not:

```python
def compile_locator_patterns(extra: list[str] | None = None) -> list[re.Pattern[str]]:
    """Compile the locator pattern set into anchored, comma-joinable matchers.

    Each pattern is anchored whole-string and permitted to repeat in a
    comma-separated list, so ``"§3, Eq. (4)"`` is accepted while
    ``"somewhere in §3"`` is not — a partial match would defeat the check.

    :param extra: Additional raw patterns from configuration.
    :returns: One compiled pattern matching any comma-joined combination.
    :raises ExtractionError: If a configured pattern is not valid regex.
    """
    raw = [*DEFAULT_LOCATOR_PATTERNS, *(extra or [])]
    for pattern in extra or []:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ExtractionError(
                f"invalid locator pattern {pattern!r} in config: {exc}"
            ) from exc
    one = "|".join(f"(?:{p})" for p in raw)
    joined = rf"\A\s*(?:{one})(?:\s*,\s*(?:{one}))*\s*\Z"
    return [re.compile(joined, re.IGNORECASE)]


def is_valid_locator(locator: str, patterns: list[re.Pattern[str]]) -> bool:
    """Return whether `locator` is well-formed against the pattern set.

    Proves the locator's *shape*, never its correctness — a cell may cite §3
    when the claim is in §5, and what catches that is ``defend --target
    cited-work`` later, which is why the locator is mandatory at all.

    :param locator: The recorded locator.
    :param patterns: Compiled patterns from :func:`compile_locator_patterns`.
    :returns: Whether it matches.
    """
    return any(p.match(locator) is not None for p in patterns)
```

Then `Cell`, `cell_from_mapping` (mirroring `record.point_record_from_mapping`'s field-type enforcement, rejecting unknown keys), `Rejection`, and `validate` implementing the four rules of spec §7.2 — collecting rejections per paper and omitting any paper with a rejection from the accepted map.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_extraction.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Full gate and commit**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`

```bash
git add defendable_science/digest/extraction.py tests/test_extraction.py
git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" commit --no-gpg-sign -m "feat(digest): cells, anchored locator patterns, and the validation rules

Patterns are anchored whole-string and comma-joinable, so '§3, Eq. (4)' passes
and 'somewhere in §3' does not — an unanchored match would accept the vague
filler the rule exists to catch.

Completeness is rule 2 and it is load-bearing: without it an agent that finds
an axis hard omits the cell, and a short row looks like a clean row.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: The artifact writer and the shared log appender

**Files:**
- Create: `defendable_science/digest/artifact.py`
- Create: `tests/test_digest_artifact.py`
- Modify: `defendable_science/defend/record.py` (generalise `_append_log`)

**Interfaces:**
- Consumes: `Cell`, `NOT_ADDRESSED` from Task 3; `patch_status_child` / `DEFAULT_LOG_DIR` from `defend/record.py`.
- Produces:
  - `def append_log_entry(log_dir: Path, date: str, stem: str, body: str) -> Path` (in `defend/record.py`, generalised from `_append_log`)
  - `@dataclass class ExtractionStatus: cells: int; locators: str; in_sample: bool; batch_check: str`
  - `def write_extraction(artifact: Path, cells: list[Cell], *, in_sample: bool, batch_check: str, log_dir: Path, date: str) -> Path`
  - `def set_batch_check(artifact: Path, verdict: str) -> None`

Behaviours to cover, each with its own test:

1. A fresh artifact is created with the seed frontmatter plus `status.extraction`, and a cells block in the body.
2. An **existing** artifact with a depth-mode `status.understanding` block keeps it byte-identical; only `status.extraction` is added or replaced.
3. `status.understanding` is **never** written by this module — assert it directly, by writing extraction to an artifact that has none and confirming none appears. This is the guarantee-inflation guard of spec §3.2.
4. `in-sample` and `batch-check` are separate keys with the meanings of spec §5 — a paper not in the sample in a failed batch reads `in-sample: false`, `batch-check: failed`.
5. Re-running extraction on the same paper replaces its cells rather than appending a second block.
6. The log entry lands in `log_dir` with a unique name and contains every cell including `not-addressed` ones with their justifications.
7. `set_batch_check` updates only that key and leaves cells and `understanding` untouched.

- [ ] **Step 1: Generalise the log appender**

In `defend/record.py`, split `_append_log` so one function owns naming and uniqueness and both callers render their own YAML:

```python
def append_log_entry(log_dir: Path, date: str, stem: str, body: str) -> Path:
    """Write a uniquely-named log file under `log_dir`, returning its path.

    One writer owns the accountability-log directory so its naming stays
    consistent across the examination kinds that write into it.

    :param log_dir: The accountability-log directory.
    :param date: ISO date, used as the filename prefix.
    :param stem: The artifact stem, used as the filename body.
    :param body: The rendered YAML to write.
    :returns: The path written.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    target = log_dir / f"{date}-{stem}.yml"
    n = 2
    while target.exists():
        target = log_dir / f"{date}-{stem}-{n}.yml"
        n += 1
    target.write_text(body, encoding="utf-8")
    return target


def _append_log(log_dir: Path, entry: LogEntry) -> Path:
    """Write a per-examination log file (unique name), returning its path."""
    return append_log_entry(
        log_dir, entry.date, Path(entry.artifact).stem, _log_yaml(entry)
    )
```

- [ ] **Step 2: Confirm `defend` is unchanged**

Run: `uv run pytest tests/test_record.py -q`
Expected: PASS with no test modified.

- [ ] **Step 3: Write the failing tests, implement, and verify**

Write `tests/test_digest_artifact.py` covering behaviours 1–7 above, run it to see it fail, implement `defendable_science/digest/artifact.py`, and run it to green. Reuse `record.patch_status_child` for frontmatter patching rather than writing a second YAML-frontmatter editor — `defend/record.py:135` already handles the indentation and trailing-comment cases correctly.

- [ ] **Step 4: Full gate and commit**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`

```bash
git add defendable_science/digest/artifact.py defendable_science/defend/record.py tests/test_digest_artifact.py
git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" commit --no-gpg-sign -m "feat(digest): the extraction artifact writer, and one log-directory writer

status.extraction never touches status.understanding: progress reports any
digests/*.md with an understanding block as 'digested & understood', so sharing
the key would count an extracted-but-unread paper as read.

in-sample and batch-check are separate because they answer different questions;
a single field would have to say 'failed' for a paper never checked.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `digest extract axes` and `digest extract record`

**Files:**
- Modify: `defendable_science/cli.py`
- Create: `tests/test_digest_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 2–4.
- Produces the CLI surface of spec §3.1.

Follow `cli.py`'s existing group patterns — `_load_config_or_exit`, `_cache_root`, config validation that exits 1 naming the bad key, `typer.echo(..., err=True)`, `json.dumps(..., indent=2)` on stdout.

Behaviours to cover:

1. `digest extract axes` prints the axes as JSON; a placeholder-bearing matrix exits 1 with the refusal message, not a traceback.
2. `digest extract record --cells FILE` validates and writes in one action; there is **no** flag or path that writes without validating.
3. Any rejection exits 1 and names the offending cells — citekey, axis, and reason — never just a count.
4. A malformed cells JSON (not an array, a non-object element, an unknown field) exits 1 with an actionable message.
5. `--cells -` reads stdin.
6. Config plumbing reads `literature.extraction.locator_patterns`; an invalid regex there exits 1 naming the pattern; a non-list value exits 1 naming the key.
7. Exit codes are `0` / `1`, with `2` left to Click. **Add a test asserting a usage error still exits 2** — #106/#119 was precisely this collision and it cost a PR.

- [ ] **Step 1–4:** Write the failing tests, run to see them fail, implement, run to green, then the full gate.
- [ ] **Step 5: Commit** with the same authorship convention.

---

## Task 6: Triage writeback and the comment-refusal path

**Files:**
- Modify: `defendable_science/digest/artifact.py`, `defendable_science/cli.py`
- Modify: `tests/test_digest_artifact.py`, `tests/test_digest_cli.py`

Behaviours:

1. A successful extraction sets the paper's triage fields via `registry.patch_triage`.
2. **A `triage.yml` carrying YAML comments makes `patch_triage` raise `RegistryError`. The cells must still be recorded.** The run reports `triage not updated for ⟨citekeys⟩; set ⟨fields⟩ by hand`, exits 1 because something genuinely did not complete, and leaves the sidecar **byte-identical**. Assert all three.
3. The same holds for `patch_triage`'s non-mapping-row refusal.
4. No path strips comments to work around the refusal — the refusal's own rationale is that those `rationale` fields are the PRISMA audit trail.

- [ ] **Steps:** failing tests → implement → green → full gate → commit.

---

## Task 7: Deterministic sampling

**Files:**
- Create: `defendable_science/digest/sampling.py`, `tests/test_sampling.py`
- Modify: `defendable_science/cli.py`

**Interfaces:**
- Produces: `def select_sample(citekeys: list[str], size: int) -> list[str]`; `def default_size(n: int) -> int` returning `min(n, max(3, ceil(n / 10)))`.

> **Determinism is the anti-gaming property, not a convenience.** A freshly-random draw per run lets anyone re-roll until an easy sample comes up. Seed from the sorted citekey set so the same batch always draws the same papers.

Behaviours:

1. The same citekey set yields the same sample across calls, processes, and orderings of the input list (sort before seeding).
2. A different citekey set yields a different sample (not a guarantee for all inputs — assert on a specific pair).
3. `default_size` returns `3` for small batches, `4` for 40, and never exceeds the batch size.
4. A batch smaller than the sample size samples everything.
5. `digest extract sample` reports which papers were drawn and exits 0; recording the human's verdict sets `batch-check` on **every** artifact in the batch, sampled or not (spec §8).
6. A `failed` verdict does **not** modify any cell — assert the cells are byte-identical after.

- [ ] **Steps:** failing tests → implement → green → full gate → commit.

---

## Task 8: `digest extract render` — the matrix merge

**Files:**
- Create: `defendable_science/digest/render.py`, `tests/test_digest_render.py`
- Modify: `defendable_science/cli.py`

**Interfaces:**
- Consumes: `parse_document`, `splice` from Task 1; the artifact reader from Task 4.
- Produces: `def render_matrix(positioning: Path, rows: dict[str, dict[str, str]]) -> str`.

> **Render never deletes a row.** It is the one operation here with no safe failure mode: a bug that drops rows loses the author's work silently, and #94 is a live reminder. Insert or update only; a paper leaving the survey is removed by hand.

Behaviours, each its own test:

1. A new citekey is inserted as a row; existing rows are untouched.
2. An existing citekey's row is updated in place, preserving column order.
3. **`**This paper**` is never touched** — it is the author's own delta.
4. **A row present in the file but absent from `rows` survives** — no deletion, ever.
5. Preamble, postamble, the section comment, and any *other* table in the document survive byte-identical.
6. Rendering twice is idempotent.
7. A cell value containing `|` or a newline is escaped so the table stays well-formed.
8. `not-addressed` cells render as a distinguishable marker rather than an empty cell — an empty cell reads as "not yet extracted", which is a different claim.

- [ ] **Steps:** failing tests → implement → green → full gate → commit.

---

## Task 9: Skill and progress documentation

**Files:**
- Modify: `skills/digest/SKILL.md`, `skills/progress/SKILL.md`
- Modify: `resources/ensure-tooling.md` (compat pin per ADR-0026), `CHANGELOG.md`

Required content:

1. **`skills/digest/SKILL.md`** states both modes and their contracts verbatim from spec §4, and **carves the "verified, never self-attested" guardrail** so it reads as covering depth mode only. Extraction says something weaker and must say it in its own words.
2. The tier ladder table of spec §4.1.
3. The `not-addressed` convention and the fact that its count is the anti-gaming signal.
4. That the **human** checks the sample, and why (spec §3.5) — if the agent checked its own extraction the mode would certify nothing.
5. That `render` never deletes a row and that a hand-edited row label is overwritten, since the row is a projection.
6. **`skills/progress/SKILL.md`** gains the second row: `extracted N / digested M`, explicitly not summed.
7. Every documented command verified against the shipped CLI with `--help`. A documented flag that does not exist is the defect class this repo spent a week removing.

- [ ] **Steps:** write → `./tools/validate-plugin.sh` → `uvx pre-commit run --all-files` (**actually run them**; a prior task in this project reported a green gate it had not exercised) → commit.

---

## Task 10: File the follow-ups

Per spec §13, using the local `create-issue` skill:

1. **`defend --target cited-work` consuming extraction cells directly** — the locators exist precisely so it can, and wiring it is what closes the loop from extraction to verification.
2. **Rendering a matrix row from depth-mode digests** — a depth digest also produces locatable claims, and today they cannot feed the matrix.

- [ ] File both; report the issue numbers.

---

## Self-review

**Spec coverage.** §3.1 → Tasks 5, 7, 8 (the four subcommands); §3.2 → Task 4 behaviour 3, Task 9 item 6; §3.3 → Task 5 behaviour 2; §3.4 → Task 3; §3.5 → Task 7; §4 → Task 9; §5 → Task 4; §6.1 → Task 2; §6.2 → Task 1; §6.3 → Task 5; §6.4 → Task 5; §6.5 → Task 3; §7 → Tasks 3, 5; §7.5 → Task 6; §8 → Task 7; §9 → Task 8; §10 → Tasks 5, 6; §11 → distributed; §12 → the PR boundaries; §13 → Task 10.

**One spec gap found and resolved in-plan:** which table in `positioning.md` the axes come from. Recorded above the file structure; handled by Task 1's `under_heading`.

**Known shape of this plan, stated rather than hidden.** Tasks 1–3 and the interface blocks throughout carry complete code. Tasks 4–9 enumerate behaviours with the reasoning for each, and give code only where the shape is not obvious from the codebase's existing patterns (the log appender, the pattern compiler). That is deliberate: those tasks are dense in fixtures whose setup is mechanical once Tasks 1–3 exist, and the previous plan in this project used the same shape successfully. An executor wanting literal code for 4–9 should write the first test of each, confirm the fixture shape, then follow the list.

**Type consistency.** `Row` and `Document` come from Task 1 and are used unchanged after. `Cell`, `Rejection`, `NOT_ADDRESSED`, `ExtractionError` come from Tasks 2–3. `validate` returns `tuple[dict[str, list[Cell]], list[Rejection]]` and every later reference uses that shape. `append_log_entry(log_dir, date, stem, body)` is defined in Task 4 and used only there. `batch_check` / `in_sample` are the field names throughout, matching spec §5's `batch-check` / `in-sample` YAML keys (underscore in Python, hyphen in YAML — stated here because that mismatch is exactly the kind of thing that drifts).
