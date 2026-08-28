"""Extraction mode's writer — the per-paper artifact and the shared log.

Extraction and depth reading share one file per paper,
``docs/research/literature/digests/<citekey>.md``, because they are two claims
of different strength about the same paper and both belong in its reading
record (spec §5). They do **not** share a frontmatter key:

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


@dataclass
class ExtractionStatus:
    """The ``status.extraction`` block written into a paper's artifact.

    :param cells: How many cells were recorded for this paper.
    :param locators: Whether every value-bearing cell carries a locator.
        Only ever ``ok``: :func:`write_extraction` refuses to write anything
        else rather than record a claim it cannot make (spec §3.3).
    :param in_sample: Whether **this** paper was drawn into the checked sample.
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


def _render_block(citekey: str, cells: list[Cell]) -> list[str]:
    """Render the delimited cells block as body lines."""
    payload = yaml.safe_dump(
        {"citekey": citekey, "cells": [_cell_mapping(c) for c in cells]},
        sort_keys=False,
        allow_unicode=True,
    )
    return [
        CELLS_BEGIN,
        "",
        _CELLS_HEADING,
        "",
        _CELLS_CAVEAT,
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


def read_cells(artifact: str | Path) -> list[Cell]:
    """Read a paper's recorded cells back out of its artifact.

    The inverse of :func:`write_extraction`'s body write, and the source the
    ``positioning.md`` matrix is rendered from — the row is a projection of
    these, never authored independently (spec §5).

    Fails loudly rather than returning an empty list: a paper with no block has
    not been extracted, and reporting that as "extracted, zero cells" would be
    a finding about the paper rather than about the file.

    :param artifact: The per-paper digest artifact.
    :returns: The recorded cells, in the order they were written.
    :raises ExtractionError: If the artifact is missing, has no frontmatter, or
        its cells block is absent or malformed.
    """
    path = Path(artifact)
    if not path.is_file():
        raise ExtractionError(f"{path}: digest artifact not found")
    try:
        _, body = split_frontmatter(path.read_text(encoding="utf-8"))
    except FrontmatterError as exc:
        raise ExtractionError(f"{path}: {exc}") from exc
    span = _locate_block(body, path)
    if span is None:
        raise ExtractionError(
            f"{path}: no extracted-cells block — this paper has not been "
            "extracted; run `digest extract record` for it"
        )
    begin, end = span
    citekey, items = _load_payload(_fenced_payload(body[begin + 1 : end], path), path)
    return [_cell_from_item(item, citekey, path) for item in items]


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


def _extraction_mapping(fm_lines: list[str], path: Path) -> dict[str, Any]:
    """Return the artifact's existing ``status.extraction`` mapping.

    :raises ExtractionError: If the frontmatter will not parse, or carries no
        ``status.extraction`` mapping. Never creates one: a paper skipped for
        want of a PDF gets no block at all (spec §6.4), and inventing one here
        would manufacture a record of an extraction that did not happen.
    """
    try:
        data = yaml.safe_load("\n".join(fm_lines))
    except yaml.YAMLError as exc:
        raise ExtractionError(f"{path}: frontmatter is not valid YAML: {exc}") from exc
    status = data.get("status") if isinstance(data, dict) else None
    block = status.get(EXTRACTION_KEY) if isinstance(status, dict) else None
    if not isinstance(block, dict):
        raise ExtractionError(
            f"{path}: no 'status.{EXTRACTION_KEY}' block — this paper has not "
            "been extracted, so there is no extraction to record a verdict "
            "against"
        )
    return block


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


def _log_body(artifact: Path, citekey: str, cells: list[Cell], date: str) -> str:
    """Render the accountability-log entry for one paper's extraction.

    Every cell goes in, `NOT_ADDRESSED` ones with their justifications: the
    count of absences is the anti-gaming signal (spec §6.5), and it is only
    auditable later if the absences are in the trail alongside the values.
    """
    entry = {
        "date": date,
        "artifact": str(artifact),
        "kind": "extraction",
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
    :param in_sample: Whether this paper was drawn into the checked sample.
    :param batch_check: The batch's verdict, from `BATCH_CHECK_VERDICTS`.
    :param log_dir: The accountability-log directory (`DEFAULT_LOG_DIR`).
    :param date: ISO date, for ``status.last-updated`` and the log entry.
    :returns: The accountability-log entry written — the one path the caller
        does not already hold.
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
        Path(log_dir), date, path.stem, _log_body(path, citekey, cells, date)
    )


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
    path = Path(artifact)
    if not path.is_file():
        raise ExtractionError(f"{path}: digest artifact not found")
    try:
        fm_lines, body = split_frontmatter(path.read_text(encoding="utf-8"))
        block = _extraction_mapping(fm_lines, path)
        block["batch-check"] = verdict
        fm_lines = set_field(fm_lines, EXTRACTION_KEY, json.dumps(block))
        if date is not None:
            fm_lines = set_field(fm_lines, "last-updated", date)
    except FrontmatterError as exc:
        raise ExtractionError(f"{path}: {exc}") from exc
    path.write_text(rebuild(fm_lines, body), encoding="utf-8")
