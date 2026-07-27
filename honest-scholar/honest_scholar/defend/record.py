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
import re
from dataclasses import asdict, dataclass, field
from datetime import date as date_cls
from pathlib import Path

TARGETS = frozenset(
    {"claim", "cited-work", "methodology", "paper-comprehension"}
)
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


def _unresolved_gaps(points: list[PointRecord]) -> list[str]:
    """Return the compact gap-fact strings frontmatter's ``unresolved`` carries."""
    return [p.gap_note or p.point for p in points if not p.resolved]


# --- frontmatter patching ---------------------------------------------------


def _split_frontmatter(text: str) -> tuple[list[str], list[str]]:
    """Split a markdown doc into (frontmatter lines, body lines).

    :raises RecordError: If there is no terminated ``---`` frontmatter block.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise RecordError("artifact has no YAML frontmatter")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], lines[i + 1 :]
    raise RecordError("artifact has an unterminated frontmatter block")


def _rebuild(fm_lines: list[str], body_lines: list[str]) -> str:
    """Reassemble a document from frontmatter and body lines."""
    parts = ["---", *fm_lines, "---", *body_lines]
    return "\n".join(parts) + "\n"


def _set_field(fm_lines: list[str], key: str, value: str) -> list[str]:
    """Set ``status.<key>`` to `value`, preserving any trailing comment.

    Replaces the existing line if present; otherwise inserts it directly under
    the ``status:`` block. Indentation is taken from the block's children.

    :param fm_lines: The frontmatter lines (mutated copy returned).
    :param key: The child key under ``status:`` (e.g. ``understanding``).
    :param value: The rendered YAML value.
    :returns: The updated frontmatter lines.
    :raises RecordError: If there is no ``status:`` block.
    """
    lines = list(fm_lines)
    status_idx = next(
        (i for i, ln in enumerate(lines) if re.match(r"^status:\s*$", ln)), None
    )
    if status_idx is None:
        raise RecordError("artifact frontmatter has no 'status:' block")

    child_indent = "  "
    for ln in lines[status_idx + 1 :]:
        if ln.strip() and (stripped_indent := len(ln) - len(ln.lstrip())) > 0:
            child_indent = " " * stripped_indent
            break

    key_pat = re.compile(rf"^{re.escape(child_indent)}{re.escape(key)}:\s*(.*)$")
    for i in range(status_idx + 1, len(lines)):
        line = lines[i]
        # Stop at a dedent back to top level (end of the status block).
        if line.strip() and not line.startswith(child_indent):
            break
        match = key_pat.match(line)
        if match:
            # A YAML comment needs whitespace before '#' (or the value is entirely
            # a comment); a '#' *inside* a value is not a comment delimiter.
            raw_value = match.group(1)
            comment = ""
            cmatch = re.search(r"\s#(.*)$", f" {raw_value}")
            if cmatch:
                comment = f"  # {cmatch.group(1).strip()}"
            lines[i] = f"{child_indent}{key}: {value}{comment}"
            return lines

    lines.insert(status_idx + 1, f"{child_indent}{key}: {value}")
    return lines


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
    fm_lines, body_lines = _split_frontmatter(text)
    fm_lines = _set_field(fm_lines, "understanding", understanding)
    fm_lines = _set_field(fm_lines, "last-updated", last_updated)
    return _rebuild(fm_lines, body_lines)


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
) -> RecordResult:
    """Record an examination outcome: patch the artifact and append the log.

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


def _append_log(log_dir: Path, entry: LogEntry) -> Path:
    """Write a per-examination log file (unique name), returning its path."""
    log_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(entry.artifact).stem
    target = log_dir / f"{entry.date}-{stem}.yml"
    n = 2
    while target.exists():
        target = log_dir / f"{entry.date}-{stem}-{n}.yml"
        n += 1
    target.write_text(_log_yaml(entry), encoding="utf-8")
    return target
