"""Extraction mode's matrix merge — extracted cells into ``positioning.md``.

A **merge, not a rewrite** (spec §9). The document this writes into is one the
author hand-wrote: taxonomy prose, a PRISMA log, the per-branch delta, section
comments. Everything the concept-matrix table does not own is written back
verbatim by :func:`~defendable_science.core.mdtable.splice`, and the table
itself is only ever inserted into or updated.

Three properties are load-bearing, and each is a test in
``tests/test_digest_render.py``:

* **Render never deletes a row.** A paper leaving the survey is removed by
  hand. Automatic deletion is the one operation here with no safe failure mode
  — a bug that drops rows loses the author's work silently, and
  defendable-science#94 is a live reminder of how that goes.
* **``**This paper**`` is never touched.** It is the author's own delta, not a
  paper anything extracted; a caller that asks to write it is refused rather
  than obeyed or silently skipped.
* **An ambiguous matrix is refused, not guessed at.** Two rows carrying one
  citekey give no answer to *which row is the row*, and picking one would
  overwrite a line the author wrote deliberately.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from defendable_science.core.mdtable import Row, splice
from defendable_science.digest.extraction import (
    NOT_ADDRESSED,
    SELF_ROW,
    ExtractionError,
    Matrix,
    read_matrix,
)

if TYPE_CHECKING:
    from pathlib import Path

#: How `NOT_ADDRESSED` appears in the matrix. Deliberately not an empty cell:
#: an empty cell reads as *not yet extracted*, and "the paper does not address
#: this axis" is a different — and evidenced — claim (spec §6.5). Italicised so
#: it is visibly a marker rather than a value a paper reported.
MATRIX_NOT_ADDRESSED = "*not addressed*"


def _row_index(rows: list[Row], label: str, citekey: str) -> int | None:
    """Return the index of `citekey`'s row, or ``None`` if it has none.

    :raises ExtractionError: If more than one row carries the label. Which of
        them is *the* row is unknowable, and updating either would overwrite a
        line a human wrote on purpose.
    """
    hits = [i for i, row in enumerate(rows) if row.get(label, "").strip() == citekey]
    if len(hits) > 1:
        raise ExtractionError(
            f"{citekey!r} appears in {len(hits)} rows of the concept matrix — "
            "which row is the paper's row cannot be guessed; merge or delete "
            "the duplicates by hand, then re-run"
        )
    return hits[0] if hits else None


def _insertion_point(rows: list[Row], label: str) -> int:
    """Return where a new row goes: last, but above the author's own delta.

    `SELF_ROW` is the matrix's punchline — the delta every other row is there
    to contrast with — so new prior work is inserted above it rather than
    pushing it into the middle of the table.
    """
    if rows and rows[-1].get(label, "").strip() == SELF_ROW:
        return len(rows) - 1
    return len(rows)


def _checked_values(values: dict[str, str], matrix: Matrix, citekey: str) -> Row:
    """Return `values` as matrix cells, refusing an axis the matrix lacks.

    :raises ExtractionError: If a key is not one of the matrix's axes. Writing
        it would need a column the author never made, and dropping it would
        lose a recorded cell without saying so.
    """
    unknown = sorted(set(values) - set(matrix.axes))
    if unknown:
        raise ExtractionError(
            f"{citekey}: {unknown} is not a matrix axis — the concept matrix "
            f"has {matrix.axes}; fix the axis name, or add the column to the "
            "matrix and re-extract against it"
        )
    return {
        axis: MATRIX_NOT_ADDRESSED if value == NOT_ADDRESSED else value
        for axis, value in values.items()
    }


def render_matrix(positioning: Path, rows: dict[str, dict[str, str]]) -> str:
    """Merge extracted cells into the concept matrix, returning the document.

    Pure: it reads `positioning` and returns the text that should replace it,
    writing nothing. Every refusal therefore leaves the file byte-identical,
    which is the property the caller depends on.

    A row already in the file and absent from `rows` survives untouched, as
    does any column the author added beyond the axes. A citekey with no row
    gets one, filled for the axes given and left empty for the rest — empty
    because the author has something to fill in there, which is true.

    :param positioning: The positioning document holding the concept matrix.
    :param rows: The cells to merge: citekey → axis → value. A value equal to
        `NOT_ADDRESSED` renders as `MATRIX_NOT_ADDRESSED`.
    :returns: The whole document with its matrix merged.
    :raises ExtractionError: If the matrix cannot be read or is not ready to be
        rendered into (see :func:`~.extraction.read_matrix`); if `rows` names
        `SELF_ROW`, which is the author's own delta; if it names an axis the
        matrix does not have; or if a citekey labels more than one row.
    """
    matrix = read_matrix(positioning)
    if SELF_ROW in rows:
        raise ExtractionError(
            f"{positioning}: refusing to write the {SELF_ROW} row — it is the "
            "author's own delta, not an extracted paper; record it by hand"
        )
    merged: list[Row] = [dict(row) for row in matrix.rows]
    label = matrix.label_column
    for citekey in sorted(rows):
        values = _checked_values(rows[citekey], matrix, citekey)
        index = _row_index(merged, label, citekey)
        if index is None:
            fresh: Row = dict.fromkeys(matrix.header, "")
            fresh[label] = citekey
            merged.insert(_insertion_point(merged, label), {**fresh, **values})
        else:
            merged[index].update(values)
    return splice(matrix.preamble, matrix.postamble, matrix.header, merged)
