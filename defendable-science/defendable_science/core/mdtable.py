"""Host-preserving markdown-table I/O (GFM), shared across front-ends.

A table lives inside a document a human wrote. This module reads the table
without losing the prose around it and writes it back without touching
anything it did not author — the property issues #94 and #95 were filed for
when an earlier writer discarded the host document and hardcoded a column
schema. Columns are read from the file's own header, never assumed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

Row = dict[str, str]

#: A markdown heading of any level, with its title text.
_HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")


class TableError(ValueError):
    """Raised when a document's table is malformed (a ragged data row)."""


def escape_cell(cell: str) -> str:
    """Escape a cell for a markdown table (newlines and pipes)."""
    return cell.replace("\\", "\\\\").replace("|", r"\|").replace("\n", " ")


def split_cells(line: str) -> list[str]:
    """Split one markdown table row into unescaped cell values."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(line):
        char = line[i]
        if char == "\\" and i + 1 < len(line):
            buf.append(line[i + 1])
            i += 2
            continue
        if char == "|":
            cells.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(char)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def is_separator(cells: list[str]) -> bool:
    """Return whether a parsed row is a ``|---|---|`` separator."""
    return bool(cells) and all(set(c) <= {"-", ":"} and c for c in cells)


@dataclass
class Document:
    """A host markdown document with its table located in place.

    :param preamble: Text before the table's header line, verbatim; the whole
        document when it holds no table.
    :param header: The column order read from the file, or ``None`` if the
        document holds no table.
    :param rows: The data rows, keyed by the file's own header.
    :param postamble: Text after the table's last data row, verbatim.
    :param saw_table_shape: Whether table-like rows were seen but never anchored
        by a GFM separator (a malformed table, not an empty document).
    """

    preamble: str = ""
    header: list[str] | None = None
    rows: list[Row] = field(default_factory=list)
    postamble: str = ""
    saw_table_shape: bool = False


def _collect_rows(
    lines: list[str], header: list[str], start: int, end_limit: int, row_label: str
) -> tuple[list[Row], int]:
    """Parse the contiguous data rows at `start`, with the index just past them.

    The table ends at the first line that is not a non-separator pipe row, so
    whatever follows is host prose to be preserved rather than table content.

    :param lines: The document's lines (newlines kept).
    :param header: The confirmed header, whose width every row must match.
    :param start: Index of the first line after the GFM separator.
    :param end_limit: Index one past the last line the table may occupy.
    :param row_label: What to call a row in an error message (the caller's
        domain noun, so the diagnostic names the artifact the human edited).
    :returns: The parsed rows and the index of the first post-table line.
    :raises TableError: If a data row's cell count does not match `header` (a
        ragged row would otherwise silently pad/drop required columns).
    """
    rows: list[Row] = []
    end = start
    while end < end_limit:
        if "|" not in lines[end]:
            break
        cells = split_cells(lines[end])
        if is_separator(cells):
            break
        if len(cells) != len(header):
            raise TableError(
                f"ragged {row_label} row: {len(cells)} cells, header has "
                f"{len(header)} ({cells!r})"
            )
        rows.append({header[i]: cells[i] for i in range(len(header))})
        end += 1
    return rows, end


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


def parse_document(
    text: str, *, under_heading: str | None = None, row_label: str = "table"
) -> Document:
    """Locate the markdown table in `text`, keeping the prose around it.

    The header is the pipe line confirmed by a following GFM ``|---|`` separator;
    that anchor is what distinguishes a real table from stray prose pipes.
    `preamble` and `postamble` are always measured against the whole document,
    so :func:`splice` round-trips even when the search is narrowed to a section.

    :param text: The host markdown document.
    :param under_heading: When given, only consider a table inside the section
        under that heading. A document may hold several tables, and the caller
        usually means one of them specifically.
    :param row_label: What to call a row in a ragged-row error message.
    :returns: The located document; ``header`` is ``None`` when the window holds
        no table, in which case `preamble` is the whole of `text`.
    :raises TableError: If a data row is ragged (see :func:`_collect_rows`).
    """
    lines = text.splitlines(keepends=True)
    window = (0, len(lines))
    if under_heading is not None:
        bounds = _section_bounds(lines, under_heading)
        if bounds is None:
            return Document(preamble=text)
        window = bounds
    candidate: list[str] | None = None
    candidate_at = 0
    pending = 0  # consecutive unconfirmed pipe rows (a table shape sans separator)
    saw_table_shape = False
    for offset, line in enumerate(lines[window[0] : window[1]]):
        i = window[0] + offset
        if "|" not in line:
            candidate = None  # prose breaks a pending header candidate
            pending = 0
            continue
        cells = split_cells(line)
        if is_separator(cells):
            if candidate is None:
                continue
            rows, end = _collect_rows(lines, candidate, i + 1, window[1], row_label)
            return Document(
                preamble="".join(lines[:candidate_at]),
                header=candidate,
                rows=rows,
                postamble="".join(lines[end:]),
            )
        candidate, candidate_at = cells, i  # a header only if a separator follows
        pending += 1
        if pending >= 2:  # header + row(s) shape with no separator between
            saw_table_shape = True
    return Document(preamble=text, saw_table_shape=saw_table_shape)


def render_table(header: list[str], rows: list[Row]) -> str:
    """Render `rows` as a GFM table in `header`'s column order."""
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    lines.extend(
        "| " + " | ".join(escape_cell(row.get(c, "")) for c in header) + " |"
        for row in rows
    )
    return "\n".join(lines) + "\n"


def splice(preamble: str, postamble: str, header: list[str], rows: list[Row]) -> str:
    """Re-emit a host document with its table region replaced.

    Everything the table does not own — the heading and the prose before and
    after it — is written back verbatim, so ``load → mutate → save`` is lossless.

    :param preamble: Host text before the table.
    :param postamble: Host text after the table.
    :param header: The column order to render.
    :param rows: The rows to render.
    :returns: The whole document, table spliced in.
    """
    if preamble and not preamble.endswith("\n"):
        preamble += "\n"  # a table cannot start mid-line
    return preamble + render_table(header, rows) + postamble
