"""Shared exploration-backlog helper for the two *generate* skills (#5).

Drives rows of a markdown backlog table through the state machine
``parked → candidate → ranked → promoted | dropped`` while preserving verbatim
provenance and recording drop reasons. One module, two column profiles selected
by ``level`` (``hypothesis`` for a paper's ``backlog.md``; ``paper`` for the
portfolio's ``portfolio-backlog.md``).

Mechanical only: it makes no scientific judgement, never ranks by fiat, and never
selects what to promote — that is a human act. Design:
``docs/design/proposals/exploration-backlog-helper.md``. ``pyyaml`` + stdlib only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date as date_cls
from pathlib import Path
from typing import Literal

Level = Literal["hypothesis", "paper"]

HYPOTHESIS_COLUMNS = [
    "id",
    "one-line",
    "move/type",
    "provenance",
    "EIG",
    "feas",
    "interest",
    "frame",
    "status",
    "note",
]
PAPER_COLUMNS = [
    "id",
    "one-line",
    "lens",
    "provenance",
    "feas",
    "interest",
    "status",
    "note",
]

#: The columns ``papers.md`` must carry for ``promote`` to register a paper.
REGISTRY_COLUMNS = ["paper-id", "root", "backend"]

#: Allowed source states for the ``rank`` transition.
_RANK_SOURCES = frozenset({"candidate", "parked"})

#: Character cap on a minted row id (truncated on a word boundary).
_ID_MAX = 40

Row = dict[str, str]


class BacklogError(ValueError):
    """Raised on an illegal transition, a missing row, or a guard violation."""


def columns_for(level: Level) -> list[str]:
    """Return the column order for a backlog `level`."""
    return list(HYPOTHESIS_COLUMNS if level == "hypothesis" else PAPER_COLUMNS)


def _slug(one_line: str, limit: int = _ID_MAX) -> str:
    """Kebab-case `one_line` into an id, truncated on a word boundary.

    A mid-word cut is avoided because the paper-level id becomes the ``paper-id``
    that keys the paper across backlog, registry, dashboard and ``progress``, so
    an unreadable default id is effectively unusable.

    :param one_line: The one-line summary to slugify.
    :param limit: Maximum length; the last whole word that fits is kept, or a
        hard cut if the first word alone exceeds it.
    :returns: The slug, or ``"row"`` if `one_line` has no alphanumerics.
    """
    base = re.sub(r"[^a-z0-9]+", "-", one_line.lower()).strip("-")
    if not base:
        return "row"
    if len(base) <= limit:
        return base
    head, sep, _ = base[: limit + 1].rpartition("-")
    return head if sep else base[:limit]


# --- markdown table I/O -----------------------------------------------------


def _escape(cell: str) -> str:
    """Escape a cell for a markdown table (newlines and pipes)."""
    return cell.replace("\\", "\\\\").replace("|", r"\|").replace("\n", " ")


def _split_cells(line: str) -> list[str]:
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


def _is_separator(cells: list[str]) -> bool:
    """Return whether a parsed row is a ``|---|---|`` separator."""
    return bool(cells) and all(set(c) <= {"-", ":"} and c for c in cells)


@dataclass
class _Document:
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
    lines: list[str], header: list[str], start: int
) -> tuple[list[Row], int]:
    """Parse the contiguous data rows at `start`, with the index just past them.

    The table ends at the first line that is not a non-separator pipe row, so
    whatever follows is host prose to be preserved rather than table content.

    :param lines: The document's lines (newlines kept).
    :param header: The confirmed header, whose width every row must match.
    :param start: Index of the first line after the GFM separator.
    :returns: The parsed rows and the index of the first post-table line.
    :raises BacklogError: If a data row's cell count does not match `header` (a
        ragged row would otherwise silently pad/drop required columns).
    """
    rows: list[Row] = []
    end = start
    while end < len(lines):
        if "|" not in lines[end]:
            break
        cells = _split_cells(lines[end])
        if _is_separator(cells):
            break
        if len(cells) != len(header):
            raise BacklogError(
                f"ragged backlog row: {len(cells)} cells, header has "
                f"{len(header)} ({cells!r})"
            )
        rows.append({header[i]: cells[i] for i in range(len(header))})
        end += 1
    return rows, end


def _parse_document(text: str) -> _Document:
    """Locate the markdown table in `text`, keeping the prose around it.

    The header is the pipe line confirmed by a following GFM ``|---|`` separator;
    that anchor is what distinguishes a real table from stray prose pipes.

    :param text: The host markdown document.
    :returns: The located document (``header is None`` if it holds no table).
    :raises BacklogError: If a data row is ragged (see :func:`_collect_rows`).
    """
    lines = text.splitlines(keepends=True)
    candidate: list[str] | None = None
    candidate_at = 0
    pending = 0  # consecutive unconfirmed pipe rows (a table shape sans separator)
    saw_table_shape = False
    for i, line in enumerate(lines):
        if "|" not in line:
            candidate = None  # prose breaks a pending header candidate
            pending = 0
            continue
        cells = _split_cells(line)
        if _is_separator(cells):
            if candidate is None:
                continue
            rows, end = _collect_rows(lines, candidate, i + 1)
            return _Document(
                preamble="".join(lines[:candidate_at]),
                header=candidate,
                rows=rows,
                postamble="".join(lines[end:]),
            )
        candidate, candidate_at = cells, i  # a header only if a separator follows
        pending += 1
        if pending >= 2:  # header + row(s) shape with no separator between
            saw_table_shape = True
    return _Document(preamble=text, saw_table_shape=saw_table_shape)


def _render_table(header: list[str], rows: list[Row]) -> str:
    """Render `rows` as a GFM table in `header`'s column order."""
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    lines.extend(
        "| " + " | ".join(_escape(row.get(c, "")) for c in header) + " |"
        for row in rows
    )
    return "\n".join(lines) + "\n"


def _splice(preamble: str, postamble: str, header: list[str], rows: list[Row]) -> str:
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
    return preamble + _render_table(header, rows) + postamble


@dataclass
class Backlog:
    """A backlog table together with the host document it was read from.

    :param level: The backlog level (selects the canonical column profile).
    :param rows: The parsed rows, each a ``column -> value`` mapping.
    :param preamble: Host text before the table (heading, explanatory prose),
        re-emitted verbatim by :meth:`dumps` so a round-trip loses nothing.
    :param postamble: Host text after the table, re-emitted verbatim.
    :param file_header: The column order read from the file; ``None`` for a
        backlog not read from one, which uses this level's profile.
    """

    level: Level
    rows: list[Row] = field(default_factory=list)
    preamble: str = ""
    postamble: str = ""
    file_header: list[str] | None = None

    @property
    def columns(self) -> list[str]:
        """The column order this backlog reads and writes.

        The host file's own header when one was parsed, so extra columns survive
        and a file is never silently restructured into ``columns_for(level)``;
        this level's canonical profile otherwise.
        """
        return list(self.file_header) if self.file_header else columns_for(self.level)

    def _require(self, *columns: str) -> None:
        """Guard that the host table can carry the columns a mutation writes.

        :param columns: The columns the caller is about to write.
        :raises BacklogError: Naming the missing columns and both layouts. The
            mutation is refused rather than written into a header that cannot
            hold it, which serialization would silently drop.
        """
        missing = [c for c in columns if c not in self.columns]
        if missing:
            raise BacklogError(
                f"backlog table cannot carry required column(s) {missing}: its "
                f"header is {self.columns}; add them, or migrate the table to "
                f"the {self.level} profile {columns_for(self.level)}"
            )

    @classmethod
    def loads(cls, text: str, level: Level) -> Backlog:
        """Parse a markdown backlog table from `text`, host document included.

        :param text: The markdown document (may contain prose around the table).
        :param level: The backlog level.
        :returns: The parsed backlog, carrying the surrounding prose and the
            file's own header so :meth:`dumps` can write both back.
        :raises BacklogError: If table-like content is present but never anchored
            by a GFM separator (a malformed table is not a genuinely empty one),
            or a data row's cell count does not match the header (a ragged row
            would otherwise silently pad/drop required columns).
        """
        doc = _parse_document(text)
        if doc.header is None and doc.saw_table_shape:
            raise BacklogError(
                "malformed backlog table: table-like rows with no GFM '|---|' "
                "separator to anchor a header"
            )
        return cls(
            level=level,
            rows=doc.rows,
            preamble=doc.preamble,
            postamble=doc.postamble,
            file_header=doc.header,
        )

    @classmethod
    def load(cls, path: str | Path, level: Level) -> Backlog:
        """Load a backlog table from a file (empty if the file is absent)."""
        file_path = Path(path)
        if not file_path.is_file():
            return cls(level=level, rows=[])
        return cls.loads(file_path.read_text(encoding="utf-8"), level)

    def dumps(self) -> str:
        """Serialize the backlog, host document included.

        The table is rendered in :attr:`columns` order; the heading and prose
        around it are written back verbatim.
        """
        return _splice(self.preamble, self.postamble, self.columns, self.rows)

    def save(self, path: str | Path) -> None:
        """Write the backlog — table and surrounding prose — to `path`."""
        Path(path).write_text(self.dumps(), encoding="utf-8")

    # --- lookup ---

    def get(self, row_id: str) -> Row:
        """Return the row with `row_id`, or raise :class:`BacklogError`."""
        self._require("id")
        for row in self.rows:
            if row.get("id") == row_id:
                return row
        raise BacklogError(f"no backlog row with id {row_id!r}")

    def _fresh_id(self, one_line: str) -> str:
        """Mint a stable, unique kebab-case id from a one-line summary."""
        base = _slug(one_line)
        existing = {row.get("id", "") for row in self.rows}
        if base not in existing:
            return base
        n = 2
        while f"{base}-{n}" in existing:
            n += 1
        return f"{base}-{n}"

    def _new_row(
        self, one_line: str, provenance: str, status: str, row_id: str | None
    ) -> Row:
        """Build a blank row for this level with the given fields."""
        row = dict.fromkeys(self.columns, "")
        row["id"] = row_id or self._fresh_id(one_line)
        row["one-line"] = one_line
        row["provenance"] = provenance
        row["status"] = status
        return row

    # --- transition verbs ---

    def park(self, one_line: str, provenance: str, *, row_id: str | None = None) -> Row:
        """Append a ``parked`` row (a raw idea, no analysis).

        :param one_line: The one-line idea.
        :param provenance: Its origin (verbatim); required.
        :param row_id: Optional explicit id; minted from `one_line` otherwise.
        :returns: The new row.
        :raises BacklogError: If `provenance` is empty or `row_id` collides.
        """
        return self._append(one_line, provenance, "parked", row_id)

    def add(self, one_line: str, provenance: str, *, row_id: str | None = None) -> Row:
        """Append a ``candidate`` row (realizes the ``generate`` verb).

        :param one_line: The one-line hypothesis/paper idea.
        :param provenance: Its origin (verbatim); required.
        :param row_id: Optional explicit id.
        :returns: The new row.
        :raises BacklogError: If `provenance` is empty or `row_id` collides.
        """
        return self._append(one_line, provenance, "candidate", row_id)

    def _append(
        self, one_line: str, provenance: str, status: str, row_id: str | None
    ) -> Row:
        self._require("id", "one-line", "provenance", "status")
        if not provenance.strip():
            raise BacklogError("provenance is required (no orphan ideas)")
        if row_id is not None and any(r.get("id") == row_id for r in self.rows):
            raise BacklogError(f"id {row_id!r} already exists")
        row = self._new_row(one_line, provenance, status, row_id)
        self.rows.append(row)
        return row

    def rank(self, row_id: str, **scores: str) -> Row:
        """Set a row to ``ranked`` and write its scores.

        :param row_id: The row to rank.
        :param scores: Column→value scores (e.g. ``feas``, ``interest``, ``EIG``,
            ``frame``). A score key not in this level's columns is a hard error,
            never silently dropped — a mistyped or level-mismatched score must
            not vanish while the row is still marked ``ranked``.
        :returns: The updated row.
        :raises BacklogError: If the row's status is not ``candidate``/``parked``,
            or a score key is not a column of this level.
        """
        self._require("status")
        row = self.get(row_id)
        if row.get("status") not in _RANK_SOURCES:
            raise BacklogError(
                f"cannot rank {row_id!r} from status {row.get('status')!r} "
                f"(must be one of {sorted(_RANK_SOURCES)})"
            )
        unknown = [key for key in scores if key not in self.columns]
        if unknown:
            raise BacklogError(
                f"unknown score key(s) {sorted(unknown)} for level {self.level!r} "
                f"(columns: {self.columns})"
            )
        for key, value in scores.items():
            row[key] = value
        row["status"] = "ranked"
        return row

    def promote(self, row_id: str) -> Row:
        """Mark a ``ranked`` row ``promoted`` (an explicit human pick).

        Only flips the row's status; scaffolding the next-stage artifact is the
        caller's responsibility (see :func:`scaffold_hypothesis` /
        :func:`scaffold_paper`).

        :param row_id: The row to promote.
        :returns: The updated row.
        :raises BacklogError: If the row's status is not ``ranked``.
        """
        self._require("status")
        row = self.get(row_id)
        if row.get("status") != "ranked":
            raise BacklogError(
                f"cannot promote {row_id!r} from status {row.get('status')!r} "
                "(must be 'ranked'); rank it first"
            )
        row["status"] = "promoted"
        return row

    def drop(self, row_id: str, reason: str) -> Row:
        """Retire a row as ``dropped`` with a recorded reason (never deletes it).

        :param row_id: The row to drop.
        :param reason: Why it is dropped (file-drawer discipline); required.
        :returns: The updated row.
        :raises BacklogError: If `reason` is empty.
        """
        self._require("status", "note")
        if not reason.strip():
            raise BacklogError("a drop reason is required (file-drawer discipline)")
        row = self.get(row_id)
        row["status"] = "dropped"
        row["note"] = reason
        return row

    def listing(self, *, status: str | None = None) -> list[Row]:
        """Return rows, optionally filtered by `status` (read-only)."""
        if status is None:
            return list(self.rows)
        return [row for row in self.rows if row.get("status") == status]


# --- promote scaffolding ----------------------------------------------------


def today_iso() -> str:
    """Return today's date as an ISO string (indirection eases testing)."""
    return date_cls.today().isoformat()


_HYPOTHESIS_TEMPLATE = """\
---
status:
  level: hypothesis
  id: {slug}
  verdict: pending
  readiness: pending
  signed-off-by: null
  signed-off-date: null
  evidence: []
  covers: []
  load-bearing: null
  understanding: {{status: pending, unresolved: []}}
  blockers: []
  last-updated: {today}
---

# Hypothesis: {one_line}

## Claim

*{one_line}*

## Why it matters

<!-- Which paper claim does this feed; is it load-bearing? -->

## What confirmation vs. refutation looks like

- **Confirming:** *<...>*
- **Refuting:** *<...>*

## Provenance

{provenance}
"""


def scaffold_hypothesis(
    paper_root: str | Path,
    slug: str,
    one_line: str,
    provenance: str,
    *,
    today: str | None = None,
) -> Path:
    """Scaffold a promoted hypothesis folder with a status-frontmatter stub.

    Writes ``<paper_root>/hypotheses/<slug>/hypothesis.md`` (the first staged doc
    of ``hypothesis-testing``), carrying the backlog provenance forward. Refuses
    to overwrite an existing file.

    :param paper_root: The paper's root directory.
    :param slug: The ``<YYYY-MM-DD-slug>`` hypothesis folder name.
    :param one_line: The claim carried from the backlog row.
    :param provenance: The verbatim provenance carried from the backlog row.
    :param today: ISO date for ``last-updated`` (defaults to today).
    :returns: The path to the written ``hypothesis.md``.
    :raises BacklogError: If the target file already exists.
    """
    folder = Path(paper_root) / "hypotheses" / slug
    target = folder / "hypothesis.md"
    if target.exists():
        raise BacklogError(f"{target} already exists — refusing to overwrite")
    folder.mkdir(parents=True, exist_ok=True)
    target.write_text(
        _HYPOTHESIS_TEMPLATE.format(
            slug=slug,
            one_line=one_line,
            provenance=provenance,
            today=today or today_iso(),
        ),
        encoding="utf-8",
    )
    return target


def append_papers_registry(
    papers_md: str | Path, paper_id: str, root: str, backend: str
) -> None:
    """Insert one paper row into the ``papers.md`` registry (create if absent).

    The row is spliced in as the registry table's last data row wherever that
    table sits in the document, so prose after it stays prose instead of being
    orphaned behind a stray row. Columns the host header carries beyond
    :data:`REGISTRY_COLUMNS` are written empty for the author to fill, never
    dropped and never producing a ragged row.

    :param papers_md: Path to ``docs/research/papers.md``.
    :param paper_id: The stable paper id (must be new).
    :param root: The paper's root path, relative to the repo.
    :param backend: The experiment-backend binding for the paper.
    :raises BacklogError: If `paper_id` is already registered, the registry table
        lacks one of :data:`REGISTRY_COLUMNS`, or its rows are not anchored by a
        GFM separator (writing into a malformed registry would corrupt it).
    """
    path = Path(papers_md)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    doc = _parse_document(text)
    if doc.header is None and doc.saw_table_shape:
        raise BacklogError(
            f"malformed registry table in {path}: table-like rows with no GFM "
            "'|---|' separator to anchor a header"
        )
    header = doc.header or list(REGISTRY_COLUMNS)
    missing = [c for c in REGISTRY_COLUMNS if c not in header]
    if missing:
        raise BacklogError(
            f"registry table in {path} is missing required column(s) {missing}: "
            f"its header is {header}"
        )
    if any(row.get("paper-id") == paper_id for row in doc.rows):
        raise BacklogError(f"paper-id {paper_id!r} already in {path}")
    doc.rows.append({"paper-id": paper_id, "root": root, "backend": backend})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _splice(doc.preamble, doc.postamble, header, doc.rows), encoding="utf-8"
    )


def _registry_root(root: Path, research: Path) -> str:
    """Render the paper root relative to the repo root for the registry row."""
    repo = research.parent.parent  # docs/research → repo root
    try:
        return str(root.relative_to(repo))
    except ValueError:
        return str(root)


def scaffold_paper(
    research_root: str | Path,
    paper_id: str,
    one_line: str,
    *,
    backend: str = "",
) -> Path:
    """Scaffold a promoted paper root and register it in ``papers.md``.

    Creates ``<research_root>/<paper_id>/{hypotheses,paper}/`` with an empty
    ``backlog.md`` and a ``paper/pitch.md`` seeded from the row, then appends the
    ``papers.md`` registry row.

    :param research_root: The ``docs/research`` directory.
    :param paper_id: The stable paper id.
    :param one_line: The pitch line carried from the portfolio-backlog row.
    :param backend: The experiment-backend binding to record.
    :returns: The paper root directory.
    :raises BacklogError: If the paper root already exists.
    """
    research = Path(research_root)
    root = research / paper_id
    if root.exists():
        raise BacklogError(f"{root} already exists — refusing to overwrite")
    (root / "hypotheses").mkdir(parents=True)
    (root / "paper").mkdir(parents=True)
    (root / "backlog.md").write_text(
        Backlog(level="hypothesis").dumps(), encoding="utf-8"
    )
    (root / "paper" / "pitch.md").write_text(
        f"# Pitch: {paper_id}\n\n{one_line}\n", encoding="utf-8"
    )
    append_papers_registry(
        research / "papers.md", paper_id, _registry_root(root, research), backend
    )
    return root
