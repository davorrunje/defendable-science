"""``defend record`` — persist understanding status + the accountability trail (#4).

Writes the ``status.understanding`` block into a target artifact's markdown
frontmatter (so :mod:`progress` can roll it up) and appends the examination
outcome — the full per-point evidentiary record (ADR-0033) plus any logged
override or per-gap acknowledgement — to an append-only accountability log.

It records **observed facts**, never a substantive verdict: there is no field for
a "correct answer", a score, or a pass/fail, and it never writes ``verdict`` /
``decision`` / ``defensible``. Design: ``docs/design/proposals/defend-record-helper.md``,
ADR-0033 (evidentiary points, shared with the ``digest`` skill).
``pyyaml`` + stdlib only.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date as date_cls
from pathlib import Path
from typing import TYPE_CHECKING, Any

from defendable_science.core.frontmatter import (
    FrontmatterError,
    rebuild,
    set_field,
    split_frontmatter,
)
from defendable_science.core.paths import require_path_segment

if TYPE_CHECKING:
    from collections.abc import Mapping

TARGETS = frozenset({"claim", "cited-work", "methodology", "paper-comprehension"})
DEFAULT_LOG_DIR = Path("docs/research/defend-log")


class RecordError(ValueError):
    """Raised on a missing/invalid artifact frontmatter or a bad argument."""


def _today() -> str:
    """Return today's date as an ISO string (indirection eases testing)."""
    return date_cls.today().isoformat()


# --- evidentiary point records (ADR-0033) -----------------------------------


@dataclass(frozen=True)
class PointRecord:
    """One probed load-bearing point, with its grounding evidence (ADR-0033).

    :param point: Which load-bearing point this is (e.g. ``assumptions``,
        ``key-result``, ``cited-work-support``).
    :param source_quote: The exact quote grounding it — from the *paper* for
        ``digest``, from the author's own artifact/claim for ``defend``.
    :param reader_answer: What the reader/author actually said, in their own
        words.
    :param resolved: Whether the point held after teaching + re-probe.
    :param location: Where the quote lives (section/equation/sentence), when
        locatable.
    :param gap_note: A short free-text gap fact, used verbatim in the
        artifact's ``unresolved`` list when `resolved` is ``False``. Falls
        back to `point` when absent.
    """

    point: str
    source_quote: str
    reader_answer: str
    resolved: bool
    location: str | None = None
    gap_note: str | None = None


#: Each `PointRecord` field's admissible decoded-JSON types, with the phrasing
#: used to report a mismatch.
_POINT_FIELD_TYPES: dict[str, tuple[tuple[type, ...], str]] = {
    "point": ((str,), "a string"),
    "source_quote": ((str,), "a string"),
    "reader_answer": ((str,), "a string"),
    "resolved": ((bool,), "a boolean"),
    "location": ((str, type(None)), "a string or null"),
    "gap_note": ((str, type(None)), "a string or null"),
}


def point_record_from_mapping(item: Mapping[str, Any]) -> PointRecord:
    """Build a `PointRecord` from a decoded JSON object, enforcing field types.

    Type-checks the fields present before constructing the record. ``resolved``
    is the load-bearing one: Python truthiness would read a ``"false"`` string
    or a ``0``/``1`` as a bool and silently misclassify an unresolved point as
    resolved, dropping its gap from the artifact's ``unresolved`` list.

    :param item: One decoded JSON object, keyed by `PointRecord` field name.
    :returns: The validated record.
    :raises RecordError: If a field's value has the wrong type, or a required
        field is missing / an unknown key is present.
    """
    for name, (admissible, expected) in _POINT_FIELD_TYPES.items():
        if name in item and not isinstance(item[name], admissible):
            raise RecordError(
                f"point record field {name!r} must be {expected}, "
                f"got {type(item[name]).__name__}"
            )
    try:
        return PointRecord(**item)
    except TypeError as exc:
        raise RecordError(f"point record is malformed: {exc}") from exc


def _unresolved_gaps(points: list[PointRecord]) -> list[str]:
    """Return the compact gap-fact strings frontmatter's ``unresolved`` carries."""
    return [p.gap_note or p.point for p in points if not p.resolved]


# --- frontmatter patching ---------------------------------------------------
#
# The line-level helpers live in ``core.frontmatter`` — ``digest`` extraction
# needs the same editing for ``status.extraction`` and must not reach into this
# module's privates. Their `FrontmatterError` is re-raised as `RecordError`
# here so this front-end's public contract (and its messages) are unchanged.


def patch_understanding(
    text: str, status: str, gaps: list[str], *, last_updated: str
) -> str:
    """Return `text` with ``status.understanding`` and ``status.last-updated`` set.

    Only those two sub-keys change; every other line (including comments and the
    body) is preserved.

    :param text: The artifact's markdown content.
    :param status: ``ok`` or ``gaps``.
    :param gaps: The still-open gap facts (empty when `status` is ``ok``).
    :param last_updated: ISO date for ``status.last-updated``.
    :returns: The patched document.
    :raises RecordError: If `status` is invalid or the frontmatter is malformed.
    """
    if status not in ("ok", "gaps"):
        raise RecordError(f"status must be 'ok' or 'gaps', got {status!r}")
    understanding = json.dumps({"status": status, "unresolved": gaps})
    try:
        fm_lines, body_lines = split_frontmatter(text)
        fm_lines = set_field(fm_lines, "understanding", understanding)
        fm_lines = set_field(fm_lines, "last-updated", last_updated)
    except FrontmatterError as exc:
        raise RecordError(str(exc)) from exc
    return rebuild(fm_lines, body_lines)


# --- the accountability log -------------------------------------------------


@dataclass
class LogEntry:
    """One examination outcome, appended to the accountability log.

    :param date: ISO examination date.
    :param artifact: Path to the examined artifact.
    :param target: ``claim`` / ``cited-work`` / ``methodology`` /
        ``paper-comprehension``.
    :param status: ``ok`` or ``gaps``.
    :param points: Every probed load-bearing point, resolved or not — the
        evidentiary record (ADR-0033): what grounds it and what the reader/
        author actually said.
    :param outcome: ``resolved`` / ``unresolved`` / ``overridden`` /
        ``acknowledged-per-gap``.
    :param acknowledgements: Per-gap sign-offs ``[{"gap": …, "by": …}]``.
    :param signed_off_by: The named human for an override/acknowledgement.
    :param transcript: Filename of the persisted transcript, if any.
    """

    date: str
    artifact: str
    target: str
    status: str
    points: list[PointRecord]
    outcome: str
    acknowledgements: list[dict[str, str]] = field(default_factory=list)
    signed_off_by: str | None = None
    transcript: str | None = None


def _derive_outcome(
    gaps: list[str], override: bool, acknowledgements: list[dict[str, str]]
) -> str:
    """Derive the log outcome from the recorded gaps and how they were handled."""
    if not gaps:
        return "resolved"
    if acknowledgements:
        return "acknowledged-per-gap"
    if override:
        return "overridden"
    return "unresolved"


def _log_yaml(entry: LogEntry) -> str:
    """Render a log entry as a YAML list item (stable key order)."""
    import yaml

    return yaml.safe_dump([asdict(entry)], sort_keys=False, allow_unicode=True)


# --- top-level record -------------------------------------------------------


@dataclass
class RecordResult:
    """What :func:`record` wrote.

    :param artifact: The patched artifact path.
    :param log_entry: The appended log-entry file.
    :param transcript: The written transcript path, if any.
    :param outcome: The derived outcome.
    """

    artifact: Path
    log_entry: Path
    transcript: Path | None
    outcome: str


def record(
    artifact: str | Path,
    target: str,
    points: list[PointRecord],
    *,
    signed_off_by: str | None = None,
    override: bool = False,
    acknowledgements: list[dict[str, str]] | None = None,
    transcript: str | None = None,
    log_dir: str | Path = DEFAULT_LOG_DIR,
    today: str | None = None,
    record_understanding: bool = True,
) -> RecordResult:
    """Record an examination outcome: patch the artifact and append the log.

    `target` alone does not say what `artifact` owns: for `claim`/
    `methodology`/`paper-comprehension`, and for a `cited-work` examination of
    the *author's own* artifact, `artifact` is a reading/writing record that
    owns ``status.understanding``, and patching it is exactly right. But a
    `cited-work` examination can also be driven from `digest` extraction
    (`../digest/artifact.py`) — probing an extracted cell's value against its
    locator in the *cited* paper's own source — and there `artifact` is that
    paper's **digest artifact**, which owns ``status.extraction``, never
    ``status.understanding`` (`~.digest.artifact`'s own guarantee: a digest
    carrying an ``understanding`` block reads as "digested & understood" to
    `progress`, so writing one from an extraction-sourced check would forge
    exactly that signal for a paper nobody has read). `record` cannot infer
    which case it is from `target` alone, so the caller states it: pass
    `record_understanding=False` (CLI: ``--no-understanding``) whenever
    `artifact` is a digest artifact being checked from its extracted cells.
    Every other write — the log entry, its `status`/`outcome`, per-point
    evidence — is identical either way; only the frontmatter patch is skipped.

    :param artifact: The examined markdown artifact.
    :param target: ``claim`` / ``cited-work`` / ``methodology`` /
        ``paper-comprehension``.
    :param points: Every probed load-bearing point, resolved or not — the
        evidentiary record (ADR-0033).
    :param signed_off_by: Named human; required when gaps are waved through.
    :param override: A blanket logged override of the surfaced gaps.
    :param acknowledgements: Per-gap acknowledgements (thesis gate, ADR-0021).
    :param transcript: Optional transcript content to persist beside the artifact.
    :param log_dir: Directory for the append-only accountability log.
    :param today: ISO date (defaults to today).
    :param record_understanding: Whether to patch ``status.understanding``
        into `artifact`. ``True`` for every existing caller; pass ``False``
        for a `cited-work` examination whose `artifact` is a `digest`
        extraction artifact, which must never gain an ``understanding``
        block from this path (defendable-science#141).
    :returns: What was written.
    :raises RecordError: On an invalid target, or if gaps are passed without a
        named sign-off.
    """
    if target not in TARGETS:
        raise RecordError(f"target must be one of {sorted(TARGETS)}, got {target!r}")
    acks = acknowledgements or []
    date = today or _today()
    gaps = _unresolved_gaps(points)
    status = "gaps" if gaps else "ok"
    outcome = _derive_outcome(gaps, override, acks)

    if outcome in ("overridden", "acknowledged-per-gap") and not signed_off_by:
        raise RecordError("passing surfaced gaps requires a named --signed-off-by")

    artifact_path = Path(artifact)
    if record_understanding:
        patched = patch_understanding(
            artifact_path.read_text(encoding="utf-8"), status, gaps, last_updated=date
        )
        artifact_path.write_text(patched, encoding="utf-8")

    transcript_path: Path | None = None
    if transcript is not None:
        transcript_path = artifact_path.with_name(f"defend-{date}.md")
        transcript_path.write_text(transcript, encoding="utf-8")

    entry = LogEntry(
        date=date,
        artifact=str(artifact_path),
        target=target,
        status=status,
        points=points,
        outcome=outcome,
        acknowledgements=acks,
        signed_off_by=signed_off_by,
        transcript=transcript_path.name if transcript_path else None,
    )
    log_entry_path = _append_log(Path(log_dir), entry)
    return RecordResult(
        artifact=artifact_path,
        log_entry=log_entry_path,
        transcript=transcript_path,
        outcome=outcome,
    )


def append_log_entry(log_dir: Path, date: str, stem: str, body: str) -> Path:
    """Write a uniquely-named log file under `log_dir`, returning its path.

    One writer owns the accountability-log directory so its naming stays
    consistent across the examination kinds that write into it — ``defend``'s
    per-point record and ``digest`` extraction's per-paper cells both land
    here, and the log is only independently reviewable if it is one trail.

    Never overwrites: a second entry for the same artifact on the same day gets
    a ``-2`` suffix, because the log is append-only evidence.

    :param log_dir: The accountability-log directory (created if absent).
    :param date: ISO date, used as the filename prefix.
    :param stem: What a reader would search the log directory for, used as the
        filename body — ``defend record`` passes the examined artifact's own
        filename stem, while ``digest extract record`` passes the paper's
        citekey (defendable-science#146) rather than the digest artifact's
        stem, so the entry stays named after the paper even if the artifact's
        naming scheme changes.
    :param body: The rendered YAML to write.
    :returns: The path written.
    :raises RecordError: If `stem` is not a single path segment — see
        :func:`~defendable_science.core.paths.require_path_segment`
        (defendable-science#182).
    """
    stem = require_path_segment(stem, what="stem", error=RecordError)
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
