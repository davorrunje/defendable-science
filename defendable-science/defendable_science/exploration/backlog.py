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

#: Allowed source states for the ``rank`` transition.
_RANK_SOURCES = frozenset({"candidate", "parked"})

Row = dict[str, str]


class BacklogError(ValueError):
    """Raised on an illegal transition, a missing row, or a guard violation."""


def columns_for(level: Level) -> list[str]:
    """Return the column order for a backlog `level`."""
    return list(HYPOTHESIS_COLUMNS if level == "hypothesis" else PAPER_COLUMNS)


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
class Backlog:
    """An in-memory backlog table.

    :param level: The backlog level (selects the column profile).
    :param rows: The parsed rows, each a ``column -> value`` mapping.
    """

    level: Level
    rows: list[Row] = field(default_factory=list)

    @property
    def columns(self) -> list[str]:
        """The column order for this backlog's level."""
        return columns_for(self.level)

    @classmethod
    def loads(cls, text: str, level: Level) -> Backlog:
        """Parse a markdown backlog table from `text`.

        :param text: The markdown document (may contain prose around the table).
        :param level: The backlog level.
        :returns: The parsed backlog.
        :raises BacklogError: If table-like content is present but never anchored
            by a GFM separator (a malformed table is not a genuinely empty one),
            or a data row's cell count does not match the header (a ragged row
            would otherwise silently pad/drop required columns).
        """
        header: list[str] | None = None
        rows: list[Row] = []
        candidate: list[str] | None = None
        pending = 0  # consecutive unconfirmed pipe rows (a table shape sans separator)
        saw_table_shape = False
        for line in text.splitlines():
            if "|" not in line:
                candidate = None  # prose breaks a pending header candidate
                pending = 0
                continue
            cells = _split_cells(line)
            if _is_separator(cells):
                # The GFM separator confirms the preceding pipe line was the header;
                # this is what distinguishes the table from stray prose pipes.
                if header is None and candidate is not None:
                    header = candidate
                    candidate = None
                    pending = 0
                continue
            if header is None:
                candidate = cells  # a header only if a separator follows it
                pending += 1
                if pending >= 2:  # header + row(s) shape with no separator between
                    saw_table_shape = True
                continue
            if len(cells) != len(header):
                raise BacklogError(
                    f"ragged backlog row: {len(cells)} cells, header has "
                    f"{len(header)} ({cells!r})"
                )
            rows.append({header[i]: cells[i] for i in range(len(header))})
        if header is None and saw_table_shape:
            raise BacklogError(
                "malformed backlog table: table-like rows with no GFM '|---|' "
                "separator to anchor a header"
            )
        return cls(level=level, rows=rows)

    @classmethod
    def load(cls, path: str | Path, level: Level) -> Backlog:
        """Load a backlog table from a file (empty if the file is absent)."""
        file_path = Path(path)
        if not file_path.is_file():
            return cls(level=level, rows=[])
        return cls.loads(file_path.read_text(encoding="utf-8"), level)

    def dumps(self) -> str:
        """Serialize the backlog to a markdown table string."""
        cols = self.columns
        lines = [
            "| " + " | ".join(cols) + " |",
            "|" + "|".join("---" for _ in cols) + "|",
        ]
        lines.extend(
            "| " + " | ".join(_escape(row.get(c, "")) for c in cols) + " |"
            for row in self.rows
        )
        return "\n".join(lines) + "\n"

    def save(self, path: str | Path) -> None:
        """Write the backlog table to `path`."""
        Path(path).write_text(self.dumps(), encoding="utf-8")

    # --- lookup ---

    def get(self, row_id: str) -> Row:
        """Return the row with `row_id`, or raise :class:`BacklogError`."""
        for row in self.rows:
            if row.get("id") == row_id:
                return row
        raise BacklogError(f"no backlog row with id {row_id!r}")

    def _fresh_id(self, one_line: str) -> str:
        """Mint a stable, unique kebab-case id from a one-line summary."""
        base = re.sub(r"[^a-z0-9]+", "-", one_line.lower()).strip("-")[:40] or "row"
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


def _today() -> str:
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
            slug=slug, one_line=one_line, provenance=provenance, today=today or _today()
        ),
        encoding="utf-8",
    )
    return target


def append_papers_registry(
    papers_md: str | Path, paper_id: str, root: str, backend: str
) -> None:
    """Append one paper row to the ``papers.md`` registry (create if absent).

    :param papers_md: Path to ``docs/research/papers.md``.
    :param paper_id: The stable paper id (must be new).
    :param root: The paper's root path, relative to the repo.
    :param backend: The experiment-backend binding for the paper.
    :raises BacklogError: If `paper_id` is already registered.
    """
    path = Path(papers_md)
    header = "| paper-id | root | backend |\n|---|---|---|\n"
    text = path.read_text(encoding="utf-8") if path.is_file() else header
    if re.search(rf"^\|\s*{re.escape(paper_id)}\s*\|", text, flags=re.MULTILINE):
        raise BacklogError(f"paper-id {paper_id!r} already in {path}")
    if not text.endswith("\n"):
        text += "\n"
    text += f"| {paper_id} | {root} | {backend} |\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
