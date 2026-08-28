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

from defendable_science.core.mdtable import TableError, parse_document

#: The heading whose table holds the comparison axes.
CONCEPT_MATRIX_HEADING = "Concept matrix"

#: The matrix's self-reference row — the author's own delta, never a paper.
SELF_ROW = "**This paper**"

#: An unreplaced template placeholder, e.g. ``<attr 1>`` or ``<prior work>``.
PLACEHOLDER_RE = re.compile(r"^<[^>]*>$")

#: The concept-matrix heading as a line, matched the way the parser matches it:
#: any level, case-insensitively (see ``core.mdtable._section_bounds``). Used
#: only to tell "no such section" apart from "section, but no table".
_MATRIX_HEADING_LINE = re.compile(
    rf"^#{{1,6}}\s+{re.escape(CONCEPT_MATRIX_HEADING)}\s*$",
    re.IGNORECASE | re.MULTILINE,
)


class ExtractionError(ValueError):
    """Raised when extraction cannot proceed and must not guess."""


def axes_from_positioning(path: str | Path) -> list[str]:
    """Read the comparison axes from a positioning document's concept matrix.

    The axes are the matrix header minus its first column, which labels the
    row rather than naming an attribute.

    :param path: The positioning document.
    :returns: The axes, in the matrix's own column order.
    :raises ExtractionError: If the file is missing; if it has no
        ``Concept matrix`` section, or that section has no table, or its table
        is ragged; if the header carries unreplaced template placeholders or an
        unnamed column; if there are no axes beyond the row label; or if two
        axes share a name.
    """
    target = Path(path)
    if not target.is_file():
        raise ExtractionError(f"{target}: positioning document not found")
    text = target.read_text(encoding="utf-8")
    try:
        doc = parse_document(text, under_heading=CONCEPT_MATRIX_HEADING)
    except TableError as exc:
        raise ExtractionError(f"{target}: {exc}") from exc
    if doc.header is None:
        if _MATRIX_HEADING_LINE.search(text) is None:
            raise ExtractionError(
                f"{target}: no '{CONCEPT_MATRIX_HEADING}' section — run "
                "`literature position --level paper` first"
            )
        raise ExtractionError(
            f"{target}: the '{CONCEPT_MATRIX_HEADING}' section holds no table"
        )
    axes = [c.strip() for c in doc.header[1:]]
    if not axes:
        raise ExtractionError(
            f"{target}: the concept matrix has no comparison axes, only a row label"
        )
    placeholders = [a for a in axes if PLACEHOLDER_RE.match(a)]
    if placeholders:
        raise ExtractionError(
            f"{target}: the concept matrix still carries template "
            f"placeholders {placeholders} — replace them with the attributes "
            "your delta turns on before extracting against them"
        )
    if any(not a for a in axes):
        raise ExtractionError(
            f"{target}: the concept matrix has an unnamed column — every axis "
            "needs a name a reader can answer against"
        )
    if len(set(axes)) != len(axes):
        raise ExtractionError(f"{target}: duplicate axis names in {axes}")
    return axes
