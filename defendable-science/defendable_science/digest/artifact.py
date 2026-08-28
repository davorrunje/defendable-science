"""Extraction mode's writer — the per-paper artifact and the shared log.

Extraction and depth reading share one file per paper (for illustration, the
default layout's ``docs/research/literature/digests/<citekey>.md``; the real
path comes from :meth:`defendable_science.scaffold.layout.Layout.digest`),
because they are two claims of
different strength about the same paper and both belong in its reading record
(spec §5). They do **not** share a frontmatter key:

* depth mode writes ``status.understanding`` — *this reader understands it*;
* extraction writes ``status.extraction`` — *these cells were extracted, each
  carrying a locator, and a sample of the batch was checked by a human*.

``progress status literature`` reports any digest carrying an ``understanding``
block as "digested & understood" (``skills/progress/SKILL.md:140-143``), so a
shared key would count a paper that was never read as read. Nothing in this
module writes ``understanding``, and that is a guarantee, not an accident.

The cells themselves are the durable record; ``positioning.md``'s matrix row is
a projection rendered from them (spec §5), so they are persisted as structured
YAML in a delimited block rather than as prose.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from defendable_science.core.frontmatter import (
    FrontmatterError,
    rebuild,
    set_field,
    split_frontmatter,
)
from defendable_science.defend.record import DEFAULT_LOG_DIR as DEFAULT_LOG_DIR
from defendable_science.defend.record import append_log_entry
from defendable_science.digest.extraction import (
    NOT_ADDRESSED,
    Cell,
    ExtractionError,
    cell_from_mapping,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

#: The admissible verdicts on a batch's sampled check (spec §5). ``pending``
#: until a human has checked; ``failed`` applies to **every** artifact in the
#: run, sampled or not, because a failed sample is evidence about the
#: population (spec §8).
BATCH_CHECK_VERDICTS = ("pending", "verified", "failed")

#: The only value ``status.extraction.locators`` is ever written with (see
#: `ExtractionStatus.locators`). Not a claim about locator *shape* — that is
#: `~.extraction.is_valid_locator` — but about the field itself: a value
#: outside this set was never written by this module, so it is a hand-edit,
#: not a leftover from a real run (defendable-science#147).
LOCATORS_WRITTEN_VALUES = frozenset({"ok"})

#: The frontmatter key extraction owns. Deliberately not ``understanding``.
EXTRACTION_KEY = "extraction"

#: Delimiters for the generated cells block. HTML comments so they survive
#: markdown rendering invisibly, and so the writer can replace exactly its own
#: span without touching a word of anything a human added to the artifact.
CELLS_BEGIN = "<!-- defendable-science: extracted cells (generated) -->"
CELLS_END = "<!-- defendable-science: end extracted cells -->"

#: The seed for a paper that has only ever been extracted: a ``status:`` block
#: and nothing else. No ``understanding`` key, not even a pending one — an
#: absent key says "not read", which is the truth, while
#: ``understanding: {status: pending}`` would announce an intention this run
#: has not formed.
_SEED = "---\nstatus:\n---\n"

_CELLS_HEADING = "## Extracted cells"
_CELLS_CAVEAT = (
    "*Extraction mode: cells with locators, checked by sample. Not verified "
    "comprehension — see `status.extraction`, not `status.understanding`.*"
)

#: The heading/caveat a depth-sourced cells block carries instead (#142). The
#: surrounding markers (`CELLS_BEGIN`/`CELLS_END`) are shared verbatim with
#: extraction's block — `read_cells` locates a block by those markers alone —
#: but the prose *inside* it must not claim extraction's sampling regime for
#: cells that regime never touched. Reusing `_CELLS_CAVEAT` here would put
#: "checked by sample" on a block no sample ever ran over, on the artifact
#: itself, where a later reader would take it at face value.
_DEPTH_CELLS_HEADING = "## Depth-sourced cells"
_DEPTH_CELLS_CAVEAT = (
    "*Depth-sourced: located claims from a paper read at depth (see "
    "`status.understanding`), held to the same locator and validation rules "
    "as extraction's cells. Not extraction's sampling regime — deliberately "
    "no `status.extraction` block; see ADR-0042.*"
)


@dataclass
class ExtractionStatus:
    """The ``status.extraction`` block written into a paper's artifact.

    :param cells: How many cells were recorded for this paper.
    :param locators: Whether every value-bearing cell carries a **non-empty**
        locator. Only ever ``ok``: :func:`write_extraction` refuses to write a
        cell without one, so there is no other value it could hold. It is not
        a claim about locator *shape* — that check belongs to
        :func:`~.extraction.validate`, which the ``digest extract record``
        command fuses to this writer (spec §3.3), so a cell recorded through
        any public surface has been shape-checked too.
    :param in_sample: Whether a human checked **this** paper's cells against its
        sources. Not "was nominated for checking": a draw that is never followed
        by a verdict has established nothing, so only ``digest extract sample
        --verdict`` ever sets it true (see :func:`set_in_sample`). Written
        ``False`` at record time, when no sample has been drawn yet.
    :param batch_check: The verdict on the *batch* this paper was extracted in
        — one of `BATCH_CHECK_VERDICTS`. Separate from `in_sample` because they
        answer different questions: a single field would have to read ``failed``
        for a paper that was never checked, which parses as a finding about that
        paper (spec §5).
    """

    cells: int
    locators: str
    in_sample: bool
    batch_check: str

    def as_mapping(self) -> dict[str, Any]:
        """Return the block as its YAML mapping, with the on-disk key names.

        :returns: The mapping written under ``status.extraction``.
        """
        return {
            "cells": self.cells,
            "locators": self.locators,
            "in-sample": self.in_sample,
            "batch-check": self.batch_check,
        }


# --- rendering ----------------------------------------------------------------


def _cell_mapping(cell: Cell) -> dict[str, Any]:
    """Render one cell as the mapping persisted in the artifact and the log.

    A `NOT_ADDRESSED` cell's locator is recorded as ``scope-evidence``, not as
    ``locator``: it names where the paper declares the scope that excludes the
    axis, which is evidence *for* the absence rather than the source of a
    value, and calling it a locator would let a later reader treat an absence
    as a cited claim.
    """
    item: dict[str, Any] = {"axis": cell.axis, "value": cell.value}
    if cell.value == NOT_ADDRESSED:
        item["justification"] = cell.justification
        if cell.locator is not None:
            item["scope-evidence"] = cell.locator
    else:
        item["locator"] = cell.locator
    return item


def _render_block(
    citekey: str,
    cells: list[Cell],
    *,
    heading: str = _CELLS_HEADING,
    caveat: str = _CELLS_CAVEAT,
) -> list[str]:
    """Render the delimited cells block as body lines.

    :param heading: The block's own heading; overridden by
        :func:`write_depth_cells` so the artifact's prose does not claim
        extraction's regime for cells it never wrote.
    :param caveat: The italic caption under `heading`, same override.
    """
    payload = yaml.safe_dump(
        {"citekey": citekey, "cells": [_cell_mapping(c) for c in cells]},
        sort_keys=False,
        allow_unicode=True,
    )
    return [
        CELLS_BEGIN,
        "",
        heading,
        "",
        caveat,
        "",
        "```yaml",
        *payload.splitlines(),
        "```",
        "",
        CELLS_END,
    ]


# --- locating and splicing the block ------------------------------------------


def _locate_block(body: list[str], path: Path) -> tuple[int, int] | None:
    """Return the block's (begin, end) line indices, or ``None`` if absent.

    :raises ExtractionError: If the markers are present but not a single
        well-ordered pair — guessing which span to overwrite risks destroying
        content this module did not author.
    """
    begins = [i for i, ln in enumerate(body) if ln.strip() == CELLS_BEGIN]
    ends = [i for i, ln in enumerate(body) if ln.strip() == CELLS_END]
    if not begins and not ends:
        return None
    if len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0]:
        return begins[0], ends[0]
    raise ExtractionError(
        f"{path}: the extracted-cells markers are malformed — expected exactly "
        f"one {CELLS_BEGIN!r} followed by one {CELLS_END!r}, found "
        f"{len(begins)} and {len(ends)}; repair or delete the block by hand, "
        "then re-run"
    )


def _splice_block(body: list[str], block: list[str], path: Path) -> list[str]:
    """Replace the cells block in `body`, or append it if there is none.

    Replacement, never a second block: re-extracting a paper restates its cells
    rather than leaving two answers in the file for a reader to choose between.
    """
    span = _locate_block(body, path)
    if span is not None:
        begin, end = span
        return [*body[:begin], *block, *body[end + 1 :]]
    trimmed = list(body)
    while trimmed and not trimmed[-1].strip():
        trimmed.pop()
    return [*trimmed, "", *block]


# --- reading back --------------------------------------------------------------


def _fenced_payload(inner: list[str], path: Path) -> str:
    """Return the YAML text inside the block's fenced code span."""
    try:
        start = inner.index("```yaml")
        stop = inner.index("```", start + 1)
    except ValueError as exc:
        raise ExtractionError(
            f"{path}: the extracted-cells block has no ```yaml fence — it was "
            "hand-edited or truncated; re-run extraction for this paper"
        ) from exc
    return "\n".join(inner[start + 1 : stop])


def _load_payload(payload: str, path: Path) -> tuple[str, list[Any]]:
    """Decode the block's YAML into (citekey, raw cell items)."""
    try:
        data = yaml.safe_load(payload)
    except yaml.YAMLError as exc:
        raise ExtractionError(
            f"{path}: the extracted-cells block is not valid YAML: {exc}"
        ) from exc
    citekey = data.get("citekey") if isinstance(data, dict) else None
    items = data.get("cells") if isinstance(data, dict) else None
    if not isinstance(citekey, str) or not isinstance(items, list):
        raise ExtractionError(
            f"{path}: the extracted-cells block is malformed — expected a "
            "mapping with a 'citekey' string and a 'cells' list"
        )
    return citekey, items


def cells_markers_present(text: str, path: Path) -> bool:
    """Whether `text`'s body carries delimited cells markers, sound or not.

    Distinguishes "no cells were ever recorded" (a legitimate absence,
    ``False``) from "cells were recorded, but the markers are malformed" (a
    defect, raised) — the split :func:`~.check.checks.check_extraction`
    needs to validate a depth-sourced cells block (an artifact with no
    ``status.extraction`` block, defendable-science#142) without treating
    "nothing recorded yet" as a finding (defendable-science#167).
    :func:`cells_from_text` cannot answer this alone: it raises the same
    `ExtractionError` type whether the markers are simply absent or present
    but broken, and a caller needs to tell those two apart before deciding
    whether silence is correct.

    :param text: The artifact's full contents, already read.
    :param path: The artifact's path, named in any raised error.
    :returns: Whether cells markers are present. Their *content* may still be
        malformed — call :func:`cells_from_text` to find out once this
        returns ``True``.
    :raises ExtractionError: If `text` has no frontmatter, or the markers are
        present but not a single well-ordered pair.
    """
    try:
        _, body = split_frontmatter(text)
    except FrontmatterError as exc:
        raise ExtractionError(f"{path}: {exc}") from exc
    return _locate_block(body, path) is not None


def cells_from_text(text: str, path: Path) -> list[Cell]:
    """Parse a paper's recorded cells out of already-read artifact `text`.

    The text-level counterpart of :func:`read_cells`, for a caller — namely
    ``check`` — that reads the artifact through its own I/O seam rather than
    the filesystem directly (defendable-science#147). :func:`read_cells`
    delegates here after doing its own file read, so there is exactly one
    parser, not two that could drift.

    Fails loudly rather than returning an empty list: a paper with no block has
    not been extracted, and reporting that as "extracted, zero cells" would be
    a finding about the paper rather than about the file.

    :param text: The artifact's full contents, already read.
    :param path: The artifact's path, named in any raised error.
    :returns: The recorded cells, in the order they were written.
    :raises ExtractionError: If `text` has no frontmatter, or its cells block
        is absent or malformed.
    """
    try:
        _, body = split_frontmatter(text)
    except FrontmatterError as exc:
        raise ExtractionError(f"{path}: {exc}") from exc
    span = _locate_block(body, path)
    if span is None:
        raise ExtractionError(
            f"{path}: no extracted-cells block — this paper has not been "
            "extracted, and no depth-sourced cells have been recorded for it; "
            "run `digest extract record` (extraction mode) or `digest depth "
            "cells record` (depth mode) for it"
        )
    begin, end = span
    citekey, items = _load_payload(_fenced_payload(body[begin + 1 : end], path), path)
    return [_cell_from_item(item, citekey, path) for item in items]


def read_cells(artifact: str | Path) -> list[Cell]:
    """Read a paper's recorded cells back out of its artifact.

    The inverse of :func:`write_extraction`'s body write, and the source the
    ``positioning.md`` matrix is rendered from — the row is a projection of
    these, never authored independently (spec §5).

    :param artifact: The per-paper digest artifact.
    :returns: The recorded cells, in the order they were written.
    :raises ExtractionError: If the artifact is missing, has no frontmatter, or
        its cells block is absent or malformed.
    """
    path = Path(artifact)
    if not path.is_file():
        raise ExtractionError(f"{path}: digest artifact not found")
    return cells_from_text(path.read_text(encoding="utf-8"), path)


def _cell_from_item(item: Any, citekey: str, path: Path) -> Cell:
    """Rebuild one `Cell` from its persisted mapping."""
    if not isinstance(item, dict):
        raise ExtractionError(
            f"{path}: the extracted-cells block holds a non-mapping entry "
            f"({item!r}); each cell must be a mapping of field to value"
        )
    fields = dict(item)
    if "scope-evidence" in fields:
        fields["locator"] = fields.pop("scope-evidence")
    try:
        return cell_from_mapping({"citekey": citekey, **fields})
    except ExtractionError as exc:
        raise ExtractionError(f"{path}: {exc}") from exc


# --- the frontmatter block ------------------------------------------------------


def _parse_status(fm_lines: list[str], path: Path) -> dict[str, Any]:
    """Parse the frontmatter and return its ``status`` mapping, or ``{}``.

    The one place either cell writer's status-block reads (`_status_extraction`,
    `_has_understanding`) touch YAML, so the "frontmatter will not parse" error
    is raised in exactly one place rather than duplicated per reader.

    :raises ExtractionError: If the frontmatter will not parse.
    """
    try:
        data = yaml.safe_load("\n".join(fm_lines))
    except yaml.YAMLError as exc:
        raise ExtractionError(f"{path}: frontmatter is not valid YAML: {exc}") from exc
    status = data.get("status") if isinstance(data, dict) else None
    return status if isinstance(status, dict) else {}


def _status_extraction(fm_lines: list[str], path: Path) -> dict[str, Any] | None:
    """Return the artifact's ``status.extraction`` mapping, or ``None``.

    ``None`` means *this paper was never extracted* — a fact. Frontmatter that
    will not parse is a different thing entirely and raises, because an
    unreadable artifact reported as an unextracted one is exactly the silent
    substitution the failure-honesty rule forbids.

    :raises ExtractionError: If the frontmatter will not parse.
    """
    block = _parse_status(fm_lines, path).get(EXTRACTION_KEY)
    return block if isinstance(block, dict) else None


def _extraction_mapping(fm_lines: list[str], path: Path) -> dict[str, Any]:
    """Return the artifact's existing ``status.extraction`` mapping.

    :raises ExtractionError: If the frontmatter will not parse, or carries no
        ``status.extraction`` mapping. Never creates one: a paper skipped for
        want of a PDF gets no block at all (spec §6.4), and inventing one here
        would manufacture a record of an extraction that did not happen.
    """
    block = _status_extraction(fm_lines, path)
    if block is None:
        raise ExtractionError(
            f"{path}: no 'status.{EXTRACTION_KEY}' block — this paper has not "
            "been extracted, so there is no extraction to record a verdict "
            "against"
        )
    return block


def extraction_status_from_text(text: str, path: Path) -> dict[str, Any] | None:
    """Return the artifact's ``status.extraction`` mapping from already-read `text`.

    The text-level counterpart of :func:`has_extraction` / :func:`_status_extraction`,
    for a caller — namely ``check`` — that reads the artifact through its own
    I/O seam rather than the filesystem directly (defendable-science#147).

    ``None`` means *this paper was never extracted* — a fact. Frontmatter that
    will not parse is a different thing entirely and raises, because an
    unreadable artifact reported as an unextracted one is exactly the silent
    substitution the failure-honesty rule forbids.

    :param text: The artifact's full contents, already read.
    :param path: The artifact's path, named in any raised error.
    :returns: The ``status.extraction`` mapping, or ``None`` if absent.
    :raises ExtractionError: If `text` has no frontmatter, an unterminated
        frontmatter block, or frontmatter that is not valid YAML.
    """
    try:
        fm_lines, _body = split_frontmatter(text)
    except FrontmatterError as exc:
        raise ExtractionError(f"{path}: {exc}") from exc
    return _status_extraction(fm_lines, path)


def has_extraction(artifact: str | Path) -> bool:
    """Whether `artifact` carries a ``status.extraction`` block.

    The membership test for an extraction batch: a digest with no such block was
    never extracted (it may be a depth-mode reading record, which owns
    ``status.understanding`` instead), so it is not a paper this batch's sampled
    check has anything to say about.

    :param artifact: The per-paper digest artifact.
    :returns: ``True`` if the artifact records an extraction.
    :raises ExtractionError: If the artifact is missing, or its frontmatter is
        absent or unparsable — a file that cannot be read is not evidence that
        the paper was never extracted, and must not be quietly excluded.
    """
    path = Path(artifact)
    if not path.is_file():
        raise ExtractionError(f"{path}: digest artifact not found")
    text = path.read_text(encoding="utf-8")
    return extraction_status_from_text(text, path) is not None


def _dump_block(block: dict[str, Any], path: Path) -> str:
    """Re-render a parsed ``status.extraction`` mapping as one YAML flow line.

    The mapping came back from the YAML parser, so it can hold a type JSON
    cannot render — an unquoted ISO date decodes to `datetime.date`, and
    ``json.dumps`` raises `TypeError` on it. Left unguarded that is a raw
    traceback out of a file a human edits, so it is reported as what it is.

    :raises ExtractionError: If the block holds a value JSON cannot render.
    """
    try:
        return json.dumps(block)
    except TypeError as exc:
        raise ExtractionError(
            f"{path}: 'status.extraction' holds a value that cannot be "
            f"rewritten ({exc}); this block is written by `digest extract "
            "record` — remove the hand-added key, or quote its value"
        ) from exc


def _check_verdict(verdict: str) -> None:
    """Refuse a verdict outside `BATCH_CHECK_VERDICTS`."""
    if verdict not in BATCH_CHECK_VERDICTS:
        raise ExtractionError(
            f"batch-check must be one of {list(BATCH_CHECK_VERDICTS)}, got "
            f"{verdict!r} — an unrecognised verdict written into the artifact "
            "would be read by nothing and trusted by everything"
        )


# --- the writer -----------------------------------------------------------------


def _one_citekey(cells: list[Cell]) -> str:
    """Return the single citekey `cells` are about.

    :raises ExtractionError: If there are no cells, or they are about more than
        one paper — the artifact is per-paper, so writing a mixed batch into it
        would file one paper's evidence under another's name.
    """
    citekeys = sorted({c.citekey for c in cells})
    if len(citekeys) != 1:
        raise ExtractionError(
            "write_extraction takes one paper's cells; got "
            f"{citekeys or 'none'} — a paper with nothing extracted gets no "
            "status.extraction block at all (spec §6.4)"
        )
    return citekeys[0]


def _refuse_unvalidated(cells: Iterable[Cell]) -> None:
    """Refuse cells that :func:`~.extraction.validate` would have rejected.

    Validation and writing are one action (spec §3.3), so reaching the writer
    with an unlocated cell means validation was bypassed. Writing it anyway
    would put ``locators: ok`` in the frontmatter over a cell with no locator —
    a false claim in the exact field a reader checks.
    """
    for cell in cells:
        if cell.value == NOT_ADDRESSED:
            if not (cell.justification or "").strip():
                raise ExtractionError(
                    f"{cell.citekey} / axis {cell.axis!r} is {NOT_ADDRESSED!r} "
                    "with no justification; refusing to record it — validate "
                    "the cells with `digest extract record`"
                )
        elif not (cell.locator or "").strip():
            raise ExtractionError(
                f"{cell.citekey} / axis {cell.axis!r} has no locator; refusing "
                "to record it — validate the cells with `digest extract record`"
            )


def _log_body(
    artifact: Path, citekey: str, cells: list[Cell], date: str, *, kind: str
) -> str:
    """Render one paper's accountability-log entry (shared by both cell writers).

    Every cell goes in, `NOT_ADDRESSED` ones with their justifications: the
    count of absences is the anti-gaming signal (spec §6.5), and it is only
    auditable later if the absences are in the trail alongside the values.

    :param kind: ``"extraction"`` for :func:`write_extraction`, ``"depth-cells"``
        for :func:`write_depth_cells` — the log entry carries the same
        provenance distinction as the artifact itself (defendable-science#142),
        so an auditor reading the log alone can tell which standard produced
        each entry without opening the artifact.
    """
    entry = {
        "date": date,
        "artifact": str(artifact),
        "kind": kind,
        "citekey": citekey,
        "cells": [_cell_mapping(c) for c in cells],
        "not-addressed": sum(1 for c in cells if c.value == NOT_ADDRESSED),
    }
    return yaml.safe_dump([entry], sort_keys=False, allow_unicode=True)


def write_extraction(
    artifact: str | Path,
    cells: list[Cell],
    *,
    in_sample: bool,
    batch_check: str,
    log_dir: str | Path,
    date: str,
) -> Path:
    """Record one paper's extracted cells, and append the accountability log.

    Creates the artifact from a minimal seed if it does not exist; otherwise
    edits in place, replacing the cells block and the ``status.extraction``
    line and leaving every other byte — prose, comments, and any
    ``status.understanding`` depth mode wrote — exactly as it was.

    :param artifact: The per-paper digest artifact to write.
    :param cells: This paper's validated cells; must be non-empty and all about
        the same paper.
    :param in_sample: Whether a human has checked this paper's cells against its
        sources — ``False`` from ``digest extract record``, which runs before
        any sample is drawn. Re-extracting a paper resets it, so the flag can
        never outlive the cells it certified.
    :param batch_check: The batch's verdict, from `BATCH_CHECK_VERDICTS`.
    :param log_dir: The accountability-log directory (`DEFAULT_LOG_DIR`).
    :param date: ISO date, for ``status.last-updated`` and the log entry.
    :returns: The accountability-log entry written — the one path the caller
        does not already hold. Named from the paper's citekey
        (defendable-science#146), not from the artifact's filename — the log
        entry stays joined to the paper it records even if `Layout.digest`'s
        naming scheme ever changes.
    :raises ExtractionError: If the cells are empty, span more than one paper,
        or would not survive validation; if `batch_check` is not a known
        verdict; or if the existing artifact's frontmatter is malformed.
    """
    path = Path(artifact)
    citekey = _one_citekey(cells)
    _refuse_unvalidated(cells)
    _check_verdict(batch_check)

    text = path.read_text(encoding="utf-8") if path.is_file() else _SEED
    try:
        fm_lines, body = split_frontmatter(text)
        status = ExtractionStatus(
            cells=len(cells),
            locators="ok",
            in_sample=in_sample,
            batch_check=batch_check,
        )
        fm_lines = set_field(fm_lines, EXTRACTION_KEY, json.dumps(status.as_mapping()))
        fm_lines = set_field(fm_lines, "last-updated", date)
    except FrontmatterError as exc:
        raise ExtractionError(f"{path}: {exc}") from exc

    body = _splice_block(body, _render_block(citekey, cells), path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rebuild(fm_lines, body), encoding="utf-8")
    return append_log_entry(
        Path(log_dir),
        date,
        citekey,
        _log_body(path, citekey, cells, date, kind="extraction"),
    )


# --- depth-sourced cells (defendable-science#142) -------------------------------


def _has_understanding(fm_lines: list[str], path: Path) -> bool:
    """Whether the frontmatter carries a ``status.understanding`` block.

    :raises ExtractionError: If the frontmatter will not parse.
    """
    return "understanding" in _parse_status(fm_lines, path)


def write_depth_cells(
    artifact: str | Path,
    cells: list[Cell],
    *,
    log_dir: str | Path,
    date: str,
) -> Path:
    """Record one paper's matrix cells sourced from its depth-mode reading.

    A depth digest already establishes locatable claims about the paper — its
    problem, method, key result, assumptions, limitations — at a *higher*
    standard than extraction, but has no cells block to feed the concept
    matrix. This writes one, in the exact shape :func:`write_extraction` does
    (same `Cell` type, same mandatory locator, same delimited block that
    :func:`read_cells` already understands), so ``digest extract render``
    picks the row up with no change to the read side at all.

    **Provenance, not a new field.** This never writes ``status.extraction`` —
    that block describes extraction's own sampling regime (``in-sample`` /
    ``batch-check``, ADR-0040), which never ran for a depth-read paper, and
    writing it here would be a false claim about this paper. A cells block
    with no ``status.extraction`` *is* the signal that the row is
    depth-sourced; one with both is extraction-sourced, today's only case. See
    ADR-0042 for the full reasoning and the rejected alternatives.

    Requires the artifact to already exist and carry ``status.understanding``:
    unlike :func:`write_extraction`, which may seed a fresh artifact for a
    paper nothing has touched yet, depth-sourced cells restate claims a depth
    digest already certified, so there is nothing honest to seed if that
    certification never happened. Refuses an artifact that already carries
    ``status.extraction`` for the same reason in the other direction — that
    artifact's cells are extraction's, and overwriting them here would blur
    which standard produced the row.

    Leaves every other byte untouched: the ``status.understanding`` block, the
    written body, and all surrounding prose survive byte-identical (verified
    by a direct diff test) — only ``status.last-updated`` and the delimited
    cells block change.

    :param artifact: The per-paper digest artifact; must already exist.
    :param cells: This paper's validated cells; must be non-empty and all
        about the same paper.
    :param log_dir: The accountability-log directory (`DEFAULT_LOG_DIR`).
    :param date: ISO date, for ``status.last-updated`` and the log entry.
    :returns: The accountability-log entry written, named from the paper's
        citekey (mirroring :func:`write_extraction`).
    :raises ExtractionError: If the artifact does not exist; if it has no
        ``status.understanding`` block; if it already carries
        ``status.extraction``; if the cells are empty, span more than one
        paper, or would not survive validation; or if the artifact's
        frontmatter is malformed.
    """
    path = Path(artifact)
    if not path.is_file():
        raise ExtractionError(
            f"{path}: digest artifact not found — depth-sourced cells can "
            "only be recorded against an existing depth digest; run `digest` "
            "on this paper first"
        )
    citekey = _one_citekey(cells)
    _refuse_unvalidated(cells)

    text = path.read_text(encoding="utf-8")
    try:
        fm_lines, body = split_frontmatter(text)
        if _status_extraction(fm_lines, path) is not None:
            raise ExtractionError(
                f"{path}: already carries a 'status.extraction' block — its "
                "cells are extraction's, not depth mode's; recording "
                "depth-sourced cells over them would blur which standard "
                "produced the row. Use `digest extract record` to update "
                "extraction cells instead"
            )
        if not _has_understanding(fm_lines, path):
            raise ExtractionError(
                f"{path}: no 'status.understanding' block — depth-sourced "
                "cells restate claims a depth digest already certified; run "
                "`digest` (depth mode) on this paper first, or use `digest "
                "extract record` if this is extraction-mode reading instead"
            )
        fm_lines = set_field(fm_lines, "last-updated", date)
    except FrontmatterError as exc:
        raise ExtractionError(f"{path}: {exc}") from exc

    block = _render_block(
        citekey, cells, heading=_DEPTH_CELLS_HEADING, caveat=_DEPTH_CELLS_CAVEAT
    )
    body = _splice_block(body, block, path)
    path.write_text(rebuild(fm_lines, body), encoding="utf-8")
    return append_log_entry(
        Path(log_dir),
        date,
        citekey,
        _log_body(path, citekey, cells, date, kind="depth-cells"),
    )


def has_extraction_or_cells(artifact: str | Path) -> bool:
    """Whether `artifact` is a candidate for ``digest extract render``'s default batch.

    True if the artifact carries ``status.extraction`` (today's
    extraction-sourced case — even one with a missing or malformed cells
    block, so that inconsistency surfaces as a read error when the cells are
    actually gathered, rather than silently vanishing from the batch) **or** a
    delimited cells block with no ``status.extraction`` (a depth-sourced row,
    defendable-science#142). :func:`has_extraction` alone would silently
    exclude every depth-sourced row from a bulk render — the exact "silently
    skipped inside a bulk render that still reports success" failure #142's
    acceptance criteria forbid — so this is a separate, wider predicate.
    :func:`digest extract sample`'s own batch stays `has_extraction`-only:
    extraction's sampling regime never ran for a depth-sourced paper, and
    folding it in there would let a bulk sample draw a paper that regime
    never touched.

    :param artifact: The per-paper digest artifact.
    :returns: Whether the artifact is a render candidate.
    :raises ExtractionError: If the artifact is missing, its frontmatter is
        absent or unparsable, or the cells-block markers are malformed.
    """
    path = Path(artifact)
    if not path.is_file():
        raise ExtractionError(f"{path}: digest artifact not found")
    text = path.read_text(encoding="utf-8")
    try:
        fm_lines, body = split_frontmatter(text)
    except FrontmatterError as exc:
        raise ExtractionError(f"{path}: {exc}") from exc
    if _status_extraction(fm_lines, path) is not None:
        return True
    return _locate_block(body, path) is not None


def has_understanding_without_cells(artifact: str | Path) -> bool:
    """Whether `artifact` is a depth digest that could contribute a row, but hasn't.

    True only for a depth digest (``status.understanding`` present) with
    **no** delimited cells block at all and no ``status.extraction`` — a
    paper a bulk ``digest extract render`` would otherwise pass over in
    total silence, because :func:`has_extraction_or_cells` correctly excludes
    it from the batch (it has no recorded cells to render) but nothing else
    then says so. Left unsurfaced, a survey author who read a paper at depth
    and forgot to run ``digest depth cells record`` would see a clean
    ``ok: true`` bulk render with no indication that paper was ever a
    candidate — the same silent-skip failure #142's acceptance criteria
    forbid, just triggered by "no cells recorded yet" instead of "cells
    block missing after being declared".

    An artifact that already has cells (either provenance) or a
    ``status.extraction`` block returns ``False`` here — this predicate is
    about the "not yet recorded" state specifically, not about presence.

    :param artifact: The per-paper digest artifact.
    :returns: Whether the artifact is a depth digest with no cells recorded yet.
    :raises ExtractionError: If the artifact is missing or its frontmatter is
        absent or unparsable.
    """
    path = Path(artifact)
    if not path.is_file():
        raise ExtractionError(f"{path}: digest artifact not found")
    text = path.read_text(encoding="utf-8")
    try:
        fm_lines, body = split_frontmatter(text)
    except FrontmatterError as exc:
        raise ExtractionError(f"{path}: {exc}") from exc
    if _status_extraction(fm_lines, path) is not None:
        return False
    if _locate_block(body, path) is not None:
        return False
    return _has_understanding(fm_lines, path)


def _set_extraction_key(
    artifact: str | Path, key: str, value: Any, date: str | None
) -> None:
    """Set one key of an already-extracted artifact's ``status.extraction``.

    Exactly one key per call, and ``last-updated`` when a date is given:
    `set_batch_check` and `set_in_sample` answer different questions (spec §5)
    and must stay separately callable, so nothing can set them together by
    accident. The body — and so every cell — is rebuilt verbatim.

    :raises ExtractionError: If the artifact is missing or malformed, or carries
        no ``status.extraction`` block.
    """
    path = Path(artifact)
    if not path.is_file():
        raise ExtractionError(f"{path}: digest artifact not found")
    try:
        fm_lines, body = split_frontmatter(path.read_text(encoding="utf-8"))
        block = _extraction_mapping(fm_lines, path)
        block[key] = value
        fm_lines = set_field(fm_lines, EXTRACTION_KEY, _dump_block(block, path))
        if date is not None:
            fm_lines = set_field(fm_lines, "last-updated", date)
    except FrontmatterError as exc:
        raise ExtractionError(f"{path}: {exc}") from exc
    path.write_text(rebuild(fm_lines, body), encoding="utf-8")


def set_batch_check(
    artifact: str | Path, verdict: str, *, date: str | None = None
) -> None:
    """Set ``status.extraction.batch-check`` on an already-extracted artifact.

    Touches that one key (and ``last-updated``, when a date is given). The
    cells are left byte-identical on purpose: a failed sample is evidence about
    the *batch*, and quietly repairing the caught cell would convert a signal
    about the population into a tidy-looking local fix (spec §8).

    :param artifact: The per-paper digest artifact.
    :param verdict: One of `BATCH_CHECK_VERDICTS`.
    :param date: ISO date for ``status.last-updated``; left alone if omitted.
    :raises ExtractionError: If the verdict is unknown, the artifact is missing
        or malformed, or it carries no ``status.extraction`` block.
    """
    _check_verdict(verdict)
    _set_extraction_key(artifact, "batch-check", verdict, date)


def set_in_sample(
    artifact: str | Path, *, in_sample: bool, date: str | None = None
) -> None:
    """Record that a human checked **this** paper's cells against its sources.

    ``in-sample: true`` means *a human looked at these cells and the places they
    cite*, not *this paper was nominated* — a draw that is never followed by a
    verdict has established nothing, so only ``digest extract sample
    --verdict`` sets it. Writing it at draw time would let an unanswered
    invocation leave behind an artifact claiming it had been checked.

    Separate from `set_batch_check` because the two keys answer different
    questions (spec §5): an unsampled paper in a failed batch reads
    ``in-sample: false``, ``batch-check: failed``.

    :param artifact: The per-paper digest artifact.
    :param in_sample: Whether this paper's cells were checked by a human.
    :param date: ISO date for ``status.last-updated``; left alone if omitted.
    :raises ExtractionError: If the artifact is missing or malformed, or carries
        no ``status.extraction`` block — a paper that was never extracted cannot
        have been sampled.
    """
    _set_extraction_key(artifact, "in-sample", in_sample, date)


def append_check_log(
    artifact: str | Path,
    citekey: str,
    cells: list[Cell],
    *,
    verdict: str,
    batch: Iterable[str],
    log_dir: str | Path,
    date: str,
) -> Path:
    """Record one sampled paper's check in the shared accountability log.

    The same trail :func:`write_extraction` and ``defend record`` write to
    (spec §8), so the evidence is independently reviewable later without
    re-running the session. Every cell the human was shown goes in, alongside
    the batch it was drawn from — the verdict is a statement about that
    population, and an entry that named only the paper would read as one about
    the paper.

    :param artifact: The sampled paper's digest artifact.
    :param citekey: The paper the cells belong to.
    :param cells: The cells the human checked.
    :param verdict: The batch verdict recorded, from `BATCH_CHECK_VERDICTS`.
    :param batch: Every citekey in the batch, sampled or not.
    :param log_dir: The accountability-log directory.
    :param date: ISO date for the entry and its filename.
    :returns: The log entry written.
    :raises ExtractionError: If `verdict` is not a known verdict.
    """
    _check_verdict(verdict)
    path = Path(artifact)
    entry = {
        "date": date,
        "artifact": str(path),
        "kind": "extraction-check",
        "citekey": citekey,
        "verdict": verdict,
        "batch": sorted(batch),
        "cells": [_cell_mapping(c) for c in cells],
    }
    return append_log_entry(
        Path(log_dir),
        date,
        citekey,
        yaml.safe_dump([entry], sort_keys=False, allow_unicode=True),
    )
