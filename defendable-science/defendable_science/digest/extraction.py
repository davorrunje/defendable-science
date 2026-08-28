"""Extraction mode's pure library — axes, cells, locators, validation.

No I/O beyond reading the positioning document: everything here is a function
of its inputs, so the rules can be tested exhaustively without touching a
registry, a PDF, or an artifact. The writer that fuses validation to recording
lives in :mod:`defendable_science.digest.artifact`; nothing here writes.

Design: ``docs/superpowers/specs/2026-08-28-digest-extraction-mode-design.md``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from defendable_science.core.mdtable import (
    AmbiguousSectionError,
    Row,
    TableError,
    parse_document,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

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


@dataclass(frozen=True)
class Matrix:
    """A positioning document's concept-matrix table, located in its host.

    Carries enough to write the table back without touching a byte the table
    does not own, so the merge in :mod:`defendable_science.digest.render` reads
    and validates the matrix exactly once.

    :param header: The file's own column order — the row label, then the axes.
        Never ``None``: every "there is no table" case is a refusal.
    :param rows: The matrix's data rows, keyed by `header`.
    :param axes: The comparison axes, i.e. `header` minus its first column,
        stripped and checked.
    :param preamble: Host text before the table, verbatim.
    :param postamble: Host text after the table, verbatim.
    """

    header: list[str]
    rows: list[Row]
    axes: list[str]
    preamble: str
    postamble: str

    @property
    def label_column(self) -> str:
        """The first column, which labels the row rather than naming an axis."""
        return self.header[0]


def read_matrix(path: str | Path) -> Matrix:
    """Read and validate a positioning document's concept matrix.

    Every refusal below names the offending file and says what to do about it:
    this function's whole job is to stop a survey that would otherwise produce
    confidently-shaped, meaningless cells, so a diagnosis without a remedy
    would only move the dead end one step later.

    :param path: The positioning document.
    :returns: The located matrix, its axes in the matrix's own column order.
    :raises ExtractionError: If the file is missing; if it has no
        ``Concept matrix`` section, or **more than one**, or that section has
        no table, or its table is missing its GFM separator, or is ragged; if
        the header carries unreplaced template placeholders or an unnamed
        column; if there are no axes beyond the row label; or if two axes share
        a name.
    """
    target = Path(path)
    if not target.is_file():
        raise ExtractionError(f"{target}: positioning document not found")
    text = target.read_text(encoding="utf-8")
    try:
        doc = parse_document(
            text, under_heading=CONCEPT_MATRIX_HEADING, row_label="concept-matrix"
        )
    except AmbiguousSectionError as exc:
        # Its own message already carries the remedy, and it is not the ragged
        # row's — appending that one would send the author counting cells in a
        # table that is perfectly well-formed.
        raise ExtractionError(f"{target}: {exc}") from exc
    except TableError as exc:
        raise ExtractionError(
            f"{target}: {exc} — give every row one cell per header column"
        ) from exc
    if doc.header is None:
        if _MATRIX_HEADING_LINE.search(text) is None:
            raise ExtractionError(
                f"{target}: no '{CONCEPT_MATRIX_HEADING}' section — ask the "
                "`literature` skill for `position --level paper` to write one"
            )
        if doc.saw_table_shape:
            raise ExtractionError(
                f"{target}: the '{CONCEPT_MATRIX_HEADING}' table is missing its "
                "`|---|---|` separator line under the header row — add it so the "
                "matrix parses as a table"
            )
        raise ExtractionError(
            f"{target}: the '{CONCEPT_MATRIX_HEADING}' section holds no table — add "
            "the matrix, one column per attribute your delta turns on"
        )
    return Matrix(
        header=doc.header,
        rows=doc.rows,
        axes=_checked_axes(doc.header, target),
        preamble=doc.preamble,
        postamble=doc.postamble,
    )


def _checked_axes(header: list[str], target: Path) -> list[str]:
    """Return the matrix's axes — `header` minus its row label — or refuse.

    Split from :func:`read_matrix` only to keep each function's branching
    readable; every refusal here is one of that function's documented ones.

    :param header: The matrix's own column order.
    :param target: The positioning document, named in every message.
    :returns: The axes, stripped, in column order.
    :raises ExtractionError: If there are no axes beyond the row label, if the
        header carries unreplaced template placeholders or an unnamed column,
        or if two **columns** share a name.
    """
    columns = [c.strip() for c in header]
    axes = columns[1:]
    if not axes:
        raise ExtractionError(
            f"{target}: the concept matrix has no comparison axes, only a row "
            "label — add one column per attribute your delta turns on"
        )
    placeholders = [a for a in axes if PLACEHOLDER_RE.match(a)]
    if placeholders:
        raise ExtractionError(
            f"{target}: the concept matrix still carries template "
            f"placeholders {placeholders} — replace them with the attributes "
            "your delta turns on before extracting against them"
        )
    unnamed = [i for i, a in enumerate(axes, start=2) if not a]
    if unnamed:
        raise ExtractionError(
            f"{target}: the concept matrix has unnamed columns at position(s) "
            f"{unnamed} (1-based, counting the row label) — name each one after "
            "the attribute it compares, or delete it"
        )
    # The **whole** header, row label included. A row is parsed into a mapping
    # keyed by the header, so a repeated name collapses two cells into one:
    # `| Method | Method |` loses the citekey the first column carried, and
    # re-emitting writes the survivor into both columns. Checking only the axes
    # would let that through, and it destroys authored content silently.
    duplicates = sorted({c for c in columns if columns.count(c) > 1})
    if duplicates:
        raise ExtractionError(
            f"{target}: duplicate column names {duplicates} in the concept "
            "matrix — two columns of one name collapse into a single cell, "
            "losing what the other one held; rename them so each column is "
            "distinct, or drop the repeat"
        )
    return axes


def axes_from_positioning(path: str | Path) -> list[str]:
    """Read the comparison axes from a positioning document's concept matrix.

    The axes are the matrix header minus its first column, which labels the row
    rather than naming an attribute. Thin over :func:`read_matrix`, which is
    what the writer and the renderer use: the axes are the only part of the
    matrix the *question set* (spec §6.1) is about.

    :param path: The positioning document.
    :returns: The axes, in the matrix's own column order.
    :raises ExtractionError: As :func:`read_matrix`.
    """
    return read_matrix(path).axes


# --- cells --------------------------------------------------------------------

#: The distinguished value for an axis the paper does not address. A cell may
#: not simply be omitted (rule 2 below), so the dodge lands here, where it is
#: counted and visible rather than invisible in a short row.
NOT_ADDRESSED = "not-addressed"


@dataclass(frozen=True)
class Cell:
    """One paper's recorded value on one comparison axis.

    :param citekey: The paper this cell is about.
    :param axis: The concept-matrix axis it fills, verbatim from the header.
    :param value: The extracted value, or `NOT_ADDRESSED`.
    :param locator: Where in the paper the value comes from — required unless
        `value` is `NOT_ADDRESSED`. A `NOT_ADDRESSED` cell *may* still carry
        one, naming where the paper declares the scope that excludes this axis:
        that is evidence **for** the absence, not a pointer at where a claim
        is not, so it is recorded as scope evidence rather than a value source.
    :param justification: Why the axis is out of the paper's scope — required
        when `value` is `NOT_ADDRESSED`.
    """

    citekey: str
    axis: str
    value: str
    locator: str | None = None
    justification: str | None = None


#: Each `Cell` field's admissible decoded-JSON types, with the phrasing used to
#: report a mismatch (mirrors ``defend.record._POINT_FIELD_TYPES``).
_CELL_FIELD_TYPES: dict[str, tuple[tuple[type, ...], str]] = {
    "citekey": ((str,), "a string"),
    "axis": ((str,), "a string"),
    "value": ((str,), "a string"),
    "locator": ((str, type(None)), "a string or null"),
    "justification": ((str, type(None)), "a string or null"),
}


def cell_from_mapping(item: Mapping[str, Any]) -> Cell:
    """Build a `Cell` from a decoded JSON object, enforcing field types.

    An unknown key is refused rather than dropped: silently ignoring a
    misspelled ``locater`` would turn a typo into a cell with no locator at
    all, which rule 1 would then blame on the wrong thing.

    :param item: One decoded JSON object, keyed by `Cell` field name.
    :returns: The validated cell.
    :raises ExtractionError: If a key is unknown, a field's value has the wrong
        type, or a required field is missing.
    """
    unknown = sorted(set(item) - set(_CELL_FIELD_TYPES))
    if unknown:
        raise ExtractionError(
            f"cell has unknown field(s) {unknown}; expected any of "
            f"{sorted(_CELL_FIELD_TYPES)}"
        )
    for name, (admissible, expected) in _CELL_FIELD_TYPES.items():
        if name in item and not isinstance(item[name], admissible):
            raise ExtractionError(
                f"cell field {name!r} must be {expected}, "
                f"got {type(item[name]).__name__}"
            )
    try:
        return Cell(**item)
    except TypeError as exc:
        raise ExtractionError(f"cell is malformed: {exc}") from exc


# --- locators -----------------------------------------------------------------

#: Locator forms accepted out of the box. Extended or replaced via
#: ``literature.extraction.locator_patterns`` — a set built around §/Eq./Thm.
#: encodes one citation culture, and this plugin forbids domain assumptions.
#:
#: A configured pattern must not rely on its own group numbering: the set is
#: concatenated into one alternation, so a numbered backreference like
#: ``(a)\1`` compiles fine alone and then silently renumbers against a
#: different group. No validation can catch that (a name collision, by
#: contrast, is caught below) — prefer non-capturing ``(?:…)`` groups.
DEFAULT_LOCATOR_PATTERNS: tuple[str, ...] = (
    r"§\s*\d+(\.\d+)*",
    r"(Section|Sec\.)\s*\d+(\.\d+)*",
    # The en dash is the typographic page-range separator and is what a reader
    # copying a page range out of a PDF will paste, so both dashes are accepted.
    r"(pp?\.|pages?)\s*\d+(\s*[-–]\s*\d+)?",  # noqa: RUF001
    r"(Eq\.|Equation)\s*\(?\d+\)?",
    r"(Table|Tbl\.)\s*\d+",
    r"(Fig\.|Figure)\s*\d+",
    r"(Alg\.|Algorithm)\s*\d+",
    r"(Thm\.|Theorem|Lemma|Cor\.|Corollary|Def\.|Definition|Prop\.|Proposition)\s*\d+",
)


def compile_locator_patterns(extra: list[str] | None = None) -> list[re.Pattern[str]]:
    """Compile the locator pattern set into anchored, comma-joinable matchers.

    Each pattern is anchored whole-string and permitted to repeat in a
    comma-separated list, so ``"§3, Eq. (4)"`` is accepted while
    ``"somewhere in §3"`` is not — a partial match would defeat the check.

    :param extra: Additional raw patterns from configuration.
    :returns: One compiled pattern matching any comma-joined combination.
    :raises ExtractionError: If a configured pattern is not valid regex, or if
        the configured set cannot be combined (e.g. two patterns reusing one
        group name).
    """
    configured = extra or []
    for pattern in configured:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ExtractionError(
                f"invalid locator pattern {pattern!r} in config: {exc}"
            ) from exc
    raw = [*DEFAULT_LOCATOR_PATTERNS, *configured]
    one = "|".join(f"(?:{p})" for p in raw)
    joined = rf"\A\s*(?:{one})(?:\s*,\s*(?:{one}))*\s*\Z"
    try:
        return [re.compile(joined, re.IGNORECASE)]
    except re.error as exc:
        # Patterns that each compile alone can still clash once combined — two
        # reusing a group name is the common case. Reporting the raw failure
        # would quote an offset into a joined pattern the user never wrote.
        raise ExtractionError(
            f"locator patterns {configured} cannot be combined into one "
            f"matcher: {exc.msg} — make each pattern self-contained, using "
            "non-capturing `(?:…)` groups rather than named or numbered ones"
        ) from exc


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


# --- validation (spec §7.2) ----------------------------------------------------


@dataclass
class Rejection:
    """One reason a paper's extraction was refused.

    :param citekey: The paper the refusal is about.
    :param axis: The offending axis, or ``None`` for a whole-paper problem.
    :param reason: What is wrong, naming the cell — a bare count would send the
        reader hunting (spec §7.4).
    """

    citekey: str
    axis: str | None
    reason: str


def render_rejection(rejection: Rejection) -> str:
    """Render one rejection as a single human-readable line (spec §7.4).

    Composed in one place so every front-end reports a refusal identically:
    "3 cells rejected" sends the reader hunting, and a caller improvising its
    own format makes the log and the terminal disagree about the same event.

    `Rejection.axis` is not re-emitted — every reason already names the axis it
    is about, and prefixing it again would read as two different axes. The
    field stays the machine-readable one, for JSON output.

    :param rejection: The refusal to render.
    :returns: ``<citekey> / <reason>``.
    """
    return f"{rejection.citekey} / {rejection.reason}"


def _cell_problem(
    cell: Cell, axes: list[str], patterns: list[re.Pattern[str]]
) -> str | None:
    """Return why `cell` is inadmissible, or ``None`` if it is fine (rules 1, 3)."""
    if cell.axis not in axes:
        return (
            f"axis {cell.axis!r} is not a matrix axis — the concept matrix has "
            f"{axes}; fix the axis name or add the column to the matrix"
        )
    if cell.value == NOT_ADDRESSED:
        if not (cell.justification or "").strip():
            return (
                f"axis {cell.axis!r} is {NOT_ADDRESSED!r} with no justification — "
                "say what in the paper puts this axis out of its scope"
            )
        return None
    if cell.locator is None:
        return (
            f"axis {cell.axis!r} has no locator — cite where in the paper the "
            f"value comes from, or record it as {NOT_ADDRESSED!r} with a "
            "justification"
        )
    if not is_valid_locator(cell.locator, patterns):
        return (
            f"axis {cell.axis!r}: locator {cell.locator!r} matches no known form "
            "— use e.g. '§3', 'p. 7', 'Eq. (4)', 'Thm. 2', or a comma-joined "
            "combination, or extend `literature.extraction.locator_patterns`"
        )
    return None


def _paper_rejections(
    citekey: str, cells: list[Cell], axes: list[str], patterns: list[re.Pattern[str]]
) -> list[Rejection]:
    """Return every rejection for one paper's cells (spec §7.2 rules 1-3)."""
    rejections = [
        Rejection(citekey, cell.axis, problem)
        for cell in cells
        if (problem := _cell_problem(cell, axes, patterns)) is not None
    ]
    counts = Counter(cell.axis for cell in cells)
    rejections += [
        Rejection(
            citekey,
            axis,
            f"axis {axis!r} is recorded {n} times — an axis may not be filled "
            "twice for one paper; keep exactly one cell per axis",
        )
        for axis, n in counts.items()
        if n > 1
    ]
    # Rule 2, the load-bearing one: without it an agent that finds an axis hard
    # omits the cell, and a short row looks exactly like a clean row.
    rejections += [
        Rejection(
            citekey,
            axis,
            f"axis {axis!r} is missing — every matrix axis must be accounted "
            f"for; record a value with a locator, or {NOT_ADDRESSED!r} with a "
            "justification",
        )
        for axis in axes
        if axis not in counts
    ]
    return rejections


def validate(
    cells: list[Cell], axes: list[str], patterns: list[re.Pattern[str]]
) -> tuple[dict[str, list[Cell]], list[Rejection]]:
    """Partition cells into acceptable papers and rejections (spec §7.2).

    Rejection is **per paper, whole**: a paper with any bad cell contributes no
    accepted cells at all, so no partial row is ever written, while the rest of
    the batch continues — one bad entry must not abort a 40-paper sweep, and
    nothing may half-land (rule 4, the ``fetch_all`` posture).

    :param cells: Every extracted cell, for any number of papers.
    :param axes: The concept matrix's axes, from :func:`axes_from_positioning`.
    :param patterns: Compiled patterns from :func:`compile_locator_patterns`.
    :returns: The accepted cells grouped by citekey, and every rejection.
    """
    by_citekey: dict[str, list[Cell]] = {}
    for cell in cells:
        by_citekey.setdefault(cell.citekey, []).append(cell)
    accepted: dict[str, list[Cell]] = {}
    rejections: list[Rejection] = []
    for citekey, paper_cells in by_citekey.items():
        problems = _paper_rejections(citekey, paper_cells, axes, patterns)
        if problems:
            rejections += problems
        else:
            accepted[citekey] = paper_cells
    return accepted, rejections
