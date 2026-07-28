# `digest` Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `digest` skill (defendable-science#68) — an inbound, cross-cutting comprehension-verification skill for external papers — plus the evidentiary accountability-record upgrade it and `defend` now share.

**Architecture:** A shared, evidentiary `points`-based record schema lands first in `defendable_science/defend/record.py` + its CLI (used by both `defend` and the new `digest`). Then the new `skills/digest/SKILL.md` and its composition edits to `defend`/`literature`/`progress`/design docs. Two new ADRs record the two material decisions (the record-schema change; the new skill). Resolves the spec at `docs/superpowers/specs/2026-07-22-digest-skill-design.md`.

**Tech Stack:** Python 3.11+, Typer CLI, pytest + pytest-cov (100% statement+branch gate), ruff, mypy strict, stdlib `dataclasses` + `pyyaml`. Plugin side is pure Markdown (SKILL.md files, MADR ADRs).

## Global Constraints

- 100% statement+branch coverage is a hard gate on the `defendable-science` package (ADR-0028, `defendable-science/pyproject.toml` `fail_under = 100`). Every new branch needs a test.
- Python 3.11+, line length 88, MyST field-list docstrings (`:param:`/`:returns:`/`:raises:`) on public API, strict mypy, stdlib `dataclasses` for value objects. No Pydantic.
- Never commit to `main` — branch, then open a PR via the local `create-pr` skill.
- Any material design decision gets a new MADR ADR in `decisions/`, linked from `decisions/README.md`.
- Commits: authored Davor Runje `<davor@synthpop.ai>` with a `Co-Authored-By: Claude …` trailer; skill-produced-artifact commits additionally carry the discovery trailers in `resources/commit-attribution.md` (not applicable to this plan's own commits — this plan modifies the plugin/package itself, it doesn't run a skill to produce research artifacts).
- Package work runs from the `defendable-science/` subdirectory (`uv run pytest -q`, `uv run ruff check`, `uv run ruff format`, `uv run mypy`); plugin-side validation is `./tools/validate-plugin.sh` from the repo root.

---

## File Structure

| File | Responsibility |
|---|---|
| `defendable-science/defendable_science/defend/record.py` | `PointRecord` dataclass; `record()`/`LogEntry` moved from bare `gaps: list[str]` to evidentiary `points: list[PointRecord]`; `TARGETS` gains `paper-comprehension`. |
| `defendable-science/defendable_science/cli.py` | `defend record`'s `--gaps` flag replaced by `--points <file>`/`--points -` (JSON). |
| `defendable-science/tests/test_record.py` | Updated + new tests for the schema change and the CLI flag. |
| `decisions/0033-evidentiary-point-records.md` (new) | ADR for the shared record-schema change. |
| `decisions/0034-digest-skill.md` (new) | ADR for the new `digest` skill. |
| `decisions/README.md` | Index entries for ADR-0033, ADR-0034. |
| `decisions/0015-defend-cross-cutting.md` | Cross-link note to ADR-0033. |
| `skills/digest/SKILL.md` (new) | The skill itself. |
| `skills/defend/SKILL.md` | Record step reflects evidentiary points; `cited-work` row gets the escalation-to-`digest` note. |
| `skills/literature/SKILL.md` | Composition section gets a `digest` bullet. |
| `skills/progress/SKILL.md` | New "Literature reading" roll-up section; `Verbs` table row updated. |
| `docs/design/00-meta-spec.md` | Skill-tree diagram gets `digest/SKILL.md`. |
| `docs/design/01-lifecycle.md` | Content-layout gets `digests/<citekey>.md`; §9 plugin-side list gets `digest`. |
| `CLAUDE.md` | Cross-cutting skill list gets `digest`. |

Tasks 1–2 (code) must land before Tasks 4–9 (prose) reference `--points`/`paper-comprehension` accurately, so the order below is load-bearing, not arbitrary.

---

### Task 1: Evidentiary `PointRecord` + `record()`/`LogEntry` schema

**Files:**
- Modify: `defendable-science/defendable_science/defend/record.py` (full-file replacement below)
- Test: `defendable-science/tests/test_record.py` (non-CLI tests; Task 2 handles the CLI tests in the same file)

**Interfaces:**
- Produces: `defendable_science.defend.record.PointRecord` (frozen dataclass: `point: str`, `source_quote: str`, `reader_answer: str`, `resolved: bool`, `location: str | None = None`, `gap_note: str | None = None`); `record(artifact, target, points: list[PointRecord], *, signed_off_by=None, override=False, acknowledgements=None, transcript=None, log_dir=DEFAULT_LOG_DIR, today=None) -> RecordResult` (third positional arg renamed from `gaps` and retyped); `TARGETS` now includes `"paper-comprehension"`. `patch_understanding()` is **unchanged** (still `(text, status, gaps: list[str], *, last_updated)`).
- Consumes: nothing new — stdlib `dataclasses`, `json`, `re`, `datetime`, `pathlib` (as before), plus `dataclasses.asdict` (new import).

- [ ] **Step 1: Write the failing/updated tests**

Replace `defendable-science/tests/test_record.py` in full with the content below (this task covers everything except the CLI tests at the bottom, which Task 2 rewrites in place — they're included here unchanged from today's file so the file stays runnable after this step; Task 2 will replace them):

```python
"""Tests for the ``defend record`` helper (defendable-science#4, defendable-science#68)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import yaml
from typer.testing import CliRunner

from defendable_science.cli import app
from defendable_science.defend import record as r

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

_ARTIFACT = """\
---
status:
  level: hypothesis
  id: 2026-07-18-x
  verdict: pending
  understanding: {status: pending, unresolved: []}   # written by the defend skill
  last-updated: 2026-01-01
---

# Hypothesis: x

Body stays intact.
"""


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / "findings.md"
    path.write_text(_ARTIFACT, encoding="utf-8")
    return path


def _resolved(point: str = "assumptions") -> r.PointRecord:
    """A minimal resolved point record for tests that don't care about content."""
    return r.PointRecord(
        point=point,
        source_quote="the paper/artifact text grounding this point",
        reader_answer="a correct, articulated answer",
        resolved=True,
    )


def _gap(note: str, *, point: str = "assumptions") -> r.PointRecord:
    """A minimal unresolved point record carrying a specific gap fact."""
    return r.PointRecord(
        point=point,
        source_quote="the paper/artifact text grounding this point",
        reader_answer="an incomplete or wrong answer",
        resolved=False,
        gap_note=note,
    )


def test_patch_sets_understanding_and_preserves_rest() -> None:
    out = r.patch_understanding(_ARTIFACT, "ok", [], last_updated="2026-07-18")
    parsed = yaml.safe_load(out.split("---")[1])
    assert parsed["status"]["understanding"] == {"status": "ok", "unresolved": []}
    assert str(parsed["status"]["last-updated"]) == "2026-07-18"
    # Body and unrelated frontmatter untouched.
    assert "Body stays intact." in out
    assert "verdict: pending" in out
    assert "# written by the defend skill" in out  # comment preserved


def test_patch_records_gaps() -> None:
    out = r.patch_understanding(
        _ARTIFACT,
        "gaps",
        ["no answer to the falsification probe"],
        last_updated="2026-07-18",
    )
    parsed = yaml.safe_load(out.split("---")[1])
    assert parsed["status"]["understanding"]["status"] == "gaps"
    assert parsed["status"]["understanding"]["unresolved"] == [
        "no answer to the falsification probe"
    ]


def test_patch_inserts_missing_fields() -> None:
    minimal = "---\nstatus:\n  level: hypothesis\n---\n\n# body\n"
    out = r.patch_understanding(minimal, "ok", [], last_updated="2026-07-18")
    parsed = yaml.safe_load(out.split("---")[1])
    assert parsed["status"]["understanding"] == {"status": "ok", "unresolved": []}
    assert str(parsed["status"]["last-updated"]) == "2026-07-18"


def test_patch_rejects_bad_status() -> None:
    with pytest.raises(r.RecordError, match="status must be"):
        r.patch_understanding(_ARTIFACT, "great", [], last_updated="2026-07-18")


def test_patch_requires_frontmatter() -> None:
    with pytest.raises(r.RecordError, match="no YAML frontmatter"):
        r.patch_understanding("# no frontmatter\n", "ok", [], last_updated="x")


def test_patch_is_idempotent() -> None:
    once = r.patch_understanding(_ARTIFACT, "ok", [], last_updated="2026-07-18")
    twice = r.patch_understanding(once, "ok", [], last_updated="2026-07-18")
    assert once == twice


def test_record_ok_writes_log(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    result = r.record(
        artifact,
        "methodology",
        [_resolved()],
        log_dir=tmp_path / "log",
        today="2026-07-18",
    )
    assert result.outcome == "resolved"
    assert result.log_entry.is_file()
    entry = yaml.safe_load(result.log_entry.read_text(encoding="utf-8"))[0]
    assert entry["target"] == "methodology"
    assert entry["status"] == "ok"


def test_record_bad_target_raises(tmp_path: Path) -> None:
    with pytest.raises(r.RecordError, match="target must be"):
        r.record(_artifact(tmp_path), "vibes", [], today="2026-07-18")


def test_record_paper_comprehension_target_accepted(tmp_path: Path) -> None:
    result = r.record(
        _artifact(tmp_path),
        "paper-comprehension",
        [_resolved(point="key-result")],
        log_dir=tmp_path / "log",
        today="2026-07-18",
    )
    assert result.outcome == "resolved"


def test_record_gaps_passed_requires_sign_off(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    with pytest.raises(r.RecordError, match="requires a named"):
        r.record(
            artifact,
            "claim",
            [_gap("unanswered probe")],
            override=True,
            today="2026-07-18",
        )


def test_record_override_with_sign_off(tmp_path: Path) -> None:
    result = r.record(
        _artifact(tmp_path),
        "claim",
        [_gap("unanswered probe")],
        override=True,
        signed_off_by="D. Runje",
        log_dir=tmp_path / "log",
        today="2026-07-18",
    )
    assert result.outcome == "overridden"


def test_record_per_gap_acknowledgement(tmp_path: Path) -> None:
    result = r.record(
        _artifact(tmp_path),
        "claim",
        [_gap("gap one")],
        acknowledgements=[{"gap": "gap one", "by": "D. Runje"}],
        signed_off_by="D. Runje",
        log_dir=tmp_path / "log",
        today="2026-07-18",
    )
    assert result.outcome == "acknowledged-per-gap"


def test_record_writes_transcript(tmp_path: Path) -> None:
    result = r.record(
        _artifact(tmp_path),
        "methodology",
        [_resolved()],
        transcript="Q: why TOST? A: ...",
        log_dir=tmp_path / "log",
        today="2026-07-18",
    )
    assert result.transcript is not None
    assert result.transcript.read_text(encoding="utf-8").startswith("Q: why TOST?")


def test_record_never_writes_a_verdict_field(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    r.record(artifact, "claim", [], log_dir=tmp_path / "log", today="2026-07-18")
    parsed = yaml.safe_load(artifact.read_text(encoding="utf-8").split("---")[1])
    # The verdict the artifact already had is untouched; record never sets it.
    assert parsed["status"]["verdict"] == "pending"


def test_record_unresolved_outcome(tmp_path: Path) -> None:
    result = r.record(
        _artifact(tmp_path),
        "claim",
        [_gap("gap")],
        log_dir=tmp_path / "log",
        today="2026-07-18",
    )
    assert result.outcome == "unresolved"


def test_record_log_dedup(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    r.record(artifact, "claim", [], log_dir=tmp_path / "log", today="2026-07-18")
    second = r.record(
        artifact, "claim", [], log_dir=tmp_path / "log", today="2026-07-18"
    )
    assert second.log_entry.name.endswith("-2.yml")


def test_patch_unterminated_frontmatter() -> None:
    with pytest.raises(r.RecordError, match="unterminated"):
        r.patch_understanding("---\nstatus:\n  x: 1\n", "ok", [], last_updated="d")


def test_patch_no_status_block() -> None:
    with pytest.raises(r.RecordError, match="no 'status:'"):
        r.patch_understanding(
            "---\nfoo: bar\n---\n\nbody\n", "ok", [], last_updated="d"
        )


def test_patch_blank_line_and_trailing_top_key() -> None:
    text = (
        "---\nstatus:\n\n  understanding: {status: pending, unresolved: []}\n"
        "foo: bar\n---\n\nbody\n"
    )
    out = r.patch_understanding(text, "ok", [], last_updated="2026-07-18")
    assert "foo: bar" in out
    assert '"status": "ok"' in out


def test_patch_zero_indent_line_after_status() -> None:
    text = "---\nstatus:\nfoo: bar\n  understanding: {status: pending, unresolved: []}\n---\nbody\n"
    out = r.patch_understanding(text, "ok", [], last_updated="2026-07-18")
    assert "foo: bar" in out


def test_patch_status_block_without_children() -> None:
    out = r.patch_understanding(
        "---\nstatus:\n---\n\nbody\n", "ok", [], last_updated="d"
    )
    assert "understanding" in out
    assert "last-updated" in out


# --- PointRecord / evidentiary log (ADR-0033) --------------------------------


def test_point_record_defaults_location_and_gap_note_to_none() -> None:
    point = r.PointRecord(
        point="limitations",
        source_quote="quote",
        reader_answer="answer",
        resolved=True,
    )
    assert point.location is None
    assert point.gap_note is None


def test_unresolved_gaps_prefers_gap_note_over_point() -> None:
    points = [_gap("could not explain the falsification probe", point="assumptions")]
    assert r._unresolved_gaps(points) == [
        "could not explain the falsification probe"
    ]


def test_unresolved_gaps_falls_back_to_point_name_without_gap_note() -> None:
    bare_gap = r.PointRecord(
        point="key-result",
        source_quote="quote",
        reader_answer="answer",
        resolved=False,
    )
    assert r._unresolved_gaps([bare_gap]) == ["key-result"]


def test_unresolved_gaps_skips_resolved_points() -> None:
    points = [_resolved(point="method"), _gap("gap", point="limitations")]
    assert r._unresolved_gaps(points) == ["gap"]


def test_record_log_carries_full_point_evidence(tmp_path: Path) -> None:
    resolved = r.PointRecord(
        point="key-result",
        source_quote="We achieve 99% accuracy (Table 2).",
        location="Table 2",
        reader_answer="They beat the baseline by a wide margin on the benchmark.",
        resolved=True,
    )
    gap = _gap("could not explain why non-convexity breaks it", point="limitations")
    result = r.record(
        _artifact(tmp_path),
        "paper-comprehension",
        [resolved, gap],
        log_dir=tmp_path / "log",
        today="2026-07-18",
    )
    entry = yaml.safe_load(result.log_entry.read_text(encoding="utf-8"))[0]
    assert entry["points"] == [
        {
            "point": "key-result",
            "source_quote": "We achieve 99% accuracy (Table 2).",
            "reader_answer": (
                "They beat the baseline by a wide margin on the benchmark."
            ),
            "resolved": True,
            "location": "Table 2",
            "gap_note": None,
        },
        {
            "point": "limitations",
            "source_quote": "the paper/artifact text grounding this point",
            "reader_answer": "an incomplete or wrong answer",
            "resolved": False,
            "location": None,
            "gap_note": "could not explain why non-convexity breaks it",
        },
    ]
    assert entry["status"] == "gaps"


# --- CLI ---------------------------------------------------------------------


def test_cli_record(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["outcome"] == "resolved"


def test_cli_record_transcript_from_stdin(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--transcript",
            "-",
            "--log-dir",
            str(tmp_path / "log"),
        ],
        input="piped transcript\n",
    )
    assert result.exit_code == 0
    assert (tmp_path / "log").exists()


def test_cli_record_unreadable_transcript_exits_1_cleanly(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--transcript",
            str(tmp_path / "missing.md"),  # unreadable transcript
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 1  # clean exit, not a traceback
    assert "defend record failed" in result.stderr
```

Note: the CLI tests `test_cli_record_gaps_without_sign_off_fails` and
`test_cli_record_with_transcript_and_acks` from today's file are **removed**
here (they used the retired `--gaps` flag) — Task 2 adds their `--points`
replacements.

- [ ] **Step 2: Run the tests to see the expected failures**

Run: `cd defendable-science && uv run pytest tests/test_record.py -v`
Expected: `AttributeError` / `TypeError` failures in the new `PointRecord`-based
tests (`r.PointRecord` doesn't exist yet, `r._unresolved_gaps` doesn't exist
yet), and the `_gap`/`_resolved` helpers fail wherever `record()` still expects
bare strings. The pre-existing `patch_*` tests should still pass (untouched
surface).

- [ ] **Step 3: Replace `defendable_science/defend/record.py` in full**

```python
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
```

- [ ] **Step 4: Run the tests to verify the non-CLI tests pass**

Run: `cd defendable-science && uv run pytest tests/test_record.py -v -k "not cli"`
Expected: PASS for every test except the three CLI tests kept in Step 1 (those
should already pass unchanged, since `test_cli_record`, the stdin transcript
test, and the unreadable-transcript test never used `--gaps`).

- [ ] **Step 5: Run the full file and check coverage**

Run: `cd defendable-science && uv run pytest tests/test_record.py -v`
Expected: all PASS. Full-suite coverage is checked in Task 2's final step
(after the CLI tests are back in place) and Task 10's verification pass.

- [ ] **Step 6: Commit**

```bash
git add defendable-science/defendable_science/defend/record.py defendable-science/tests/test_record.py
git commit -m "$(cat <<'EOF'
feat(defend): evidentiary per-point accountability records (ADR-0033)

record() moves from a bare gaps: list[str] to points: list[PointRecord],
carrying the exact quote grounding each probed load-bearing point and what
the reader/author actually said - resolved or not, not just failures. The
accountability log gets meaningfully checkable later without re-running the
session. Frontmatter shape is unchanged (progress's roll-up is unaffected).
TARGETS gains paper-comprehension for the upcoming digest skill (#68).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: CLI `defend record --points` (replaces `--gaps`)

**Files:**
- Modify: `defendable-science/defendable_science/cli.py:625-703` (the `# --- defend` section)
- Test: `defendable-science/tests/test_record.py` (append the CLI tests below)

**Interfaces:**
- Consumes: `record_mod.PointRecord`, `record_mod.record()` (Task 1).
- Produces: `defend record` CLI command taking `--points <file>` / `--points -`
  (JSON array of point objects) instead of `--gaps`; `_parse_points(raw: str) ->
  list[record_mod.PointRecord]` (new helper, mirrors `_parse_acks`).

- [ ] **Step 1: Write the failing CLI tests**

Append to `defendable-science/tests/test_record.py` (after
`test_cli_record_unreadable_transcript_exits_1_cleanly`, replacing nothing —
these are new):

```python
def _points_file(tmp_path: Path, points: list[dict[str, object]]) -> Path:
    path = tmp_path / "points.json"
    path.write_text(json.dumps(points), encoding="utf-8")
    return path


def test_cli_record_points_from_file(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    points = _points_file(
        tmp_path,
        [
            {
                "point": "assumptions",
                "source_quote": "quote",
                "reader_answer": "answer",
                "resolved": True,
            }
        ],
    )
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--points",
            str(points),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["outcome"] == "resolved"


def test_cli_record_points_without_sign_off_fails(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    points = _points_file(
        tmp_path,
        [
            {
                "point": "assumptions",
                "source_quote": "quote",
                "reader_answer": "wrong",
                "resolved": False,
                "gap_note": "unanswered probe",
            }
        ],
    )
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "claim",
            "--points",
            str(points),
            "--override",
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 1


def test_cli_record_points_with_transcript_and_acks(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    transcript = tmp_path / "t.md"
    transcript.write_text("Q: why? A: because.", encoding="utf-8")
    points = _points_file(
        tmp_path,
        [
            {
                "point": "assumptions",
                "source_quote": "quote",
                "reader_answer": "wrong",
                "resolved": False,
                "gap_note": "gap one",
            }
        ],
    )
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "claim",
            "--points",
            str(points),
            "--acks",
            "gap one::D. Runje",
            "--signed-off-by",
            "D. Runje",
            "--transcript",
            str(transcript),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["outcome"] == "acknowledged-per-gap"


def test_cli_record_points_from_stdin(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "paper-comprehension",
            "--points",
            "-",
            "--log-dir",
            str(tmp_path / "log"),
        ],
        input=json.dumps(
            [
                {
                    "point": "key-result",
                    "source_quote": "quote",
                    "reader_answer": "answer",
                    "resolved": True,
                }
            ]
        ),
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["outcome"] == "resolved"


def test_cli_record_unreadable_points_file_exits_1_cleanly(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--points",
            str(tmp_path / "missing.json"),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 1
    assert "defend record failed" in result.stderr


def test_cli_record_malformed_points_json_exits_1_cleanly(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    points = tmp_path / "points.json"
    points.write_text("not json", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--points",
            str(points),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 1
    assert "defend record failed" in result.stderr


def test_cli_record_points_not_a_json_array_exits_1_cleanly(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    points = tmp_path / "points.json"
    points.write_text(json.dumps({"point": "x"}), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--points",
            str(points),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 1
    assert "defend record failed" in result.stderr


def test_cli_record_points_item_not_an_object_exits_1_cleanly(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    points = tmp_path / "points.json"
    points.write_text(json.dumps(["not an object"]), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--points",
            str(points),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 1
    assert "defend record failed" in result.stderr


def test_cli_record_points_bad_shape_exits_1_cleanly(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    points = _points_file(tmp_path, [{"point": "x", "unexpected_key": "y"}])
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--points",
            str(points),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 1
    assert "defend record failed" in result.stderr
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_record.py -k points -v`
Expected: FAIL — `--points` is not a recognised option yet (Typer reports "no
such option").

- [ ] **Step 3: Replace the `# --- defend` CLI section**

In `defendable-science/defendable_science/cli.py`, replace the block from
`# --- defend (defendable-science#4) ----...` through the end of the `record`
function (currently lines 625–703) with:

```python
# --- defend (defendable-science#4, defendable-science#68) ----------------------------------
defend = typer.Typer(help="Defensibility record helpers.", no_args_is_help=True)
app.add_typer(defend, name="defend")


def _parse_acks(acks: str) -> list[dict[str, str]]:
    """Parse ``"gap::by||gap2::by2"`` into per-gap acknowledgement dicts."""
    result: list[dict[str, str]] = []
    for item in filter(None, (a.strip() for a in acks.split("||"))):
        gap, _, by = item.partition("::")
        result.append({"gap": gap.strip(), "by": by.strip()})
    return result


def _parse_points(raw: str) -> list[record_mod.PointRecord]:
    """Parse a JSON array of point-record objects into ``PointRecord``s (ADR-0033).

    :param raw: JSON text: ``[{"point": ..., "source_quote": ..., "reader_answer":
        ..., "resolved": ..., "location": ..., "gap_note": ...}, ...]`` —
        ``location``/``gap_note`` are optional per item; empty input means no
        points.
    :raises record_mod.RecordError: If `raw` isn't a JSON array of point objects
        with the expected fields.
    """
    if not raw.strip():
        return []
    try:
        data: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise record_mod.RecordError(f"--points is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise record_mod.RecordError("--points must be a JSON array")
    points: list[record_mod.PointRecord] = []
    for item in data:
        if not isinstance(item, dict):
            raise record_mod.RecordError("--points item must be a JSON object")
        try:
            points.append(record_mod.PointRecord(**item))
        except TypeError as exc:
            raise record_mod.RecordError(f"--points item is malformed: {exc}") from exc
    return points


@defend.command()
def record(
    artifact: Annotated[
        str, typer.Option("--artifact", help="Target markdown artifact.")
    ],
    target: Annotated[
        str,
        typer.Option(
            "--target", help="claim | cited-work | methodology | paper-comprehension."
        ),
    ],
    points: Annotated[
        str,
        typer.Option(
            "--points",
            help="Point records: a JSON-array file path, or '-' for stdin.",
        ),
    ] = "",
    signed_off_by: Annotated[str, typer.Option("--signed-off-by")] = "",
    override: Annotated[bool, typer.Option("--override")] = False,
    acks: Annotated[
        str, typer.Option("--acks", help="Per-gap sign-offs, 'gap::name||…'.")
    ] = "",
    transcript: Annotated[
        str, typer.Option("--transcript", help="Transcript file, or '-' for stdin.")
    ] = "",
    log_dir: Annotated[str, typer.Option("--log-dir")] = str(
        record_mod.DEFAULT_LOG_DIR
    ),
) -> None:
    """Record a ``defend``/``digest`` examination: patch understanding + log.

    Writes ``status.understanding`` into the artifact frontmatter and appends the
    full evidentiary point record (ADR-0033) to the accountability log. Records
    observed facts only — never a verdict, score, or answer key.

    :param artifact: The examined markdown artifact.
    :param target: ``claim`` / ``cited-work`` / ``methodology`` /
        ``paper-comprehension``.
    :param points: Point records — a JSON-array file path, or ``-`` for stdin;
        empty means none.
    :param signed_off_by: Named human; required when gaps are waved through.
    :param override: A blanket logged override of the surfaced gaps.
    :param acks: Per-gap acknowledgements, ``gap::name``, ``||``-separated.
    :param transcript: Transcript file path, or ``-`` for stdin.
    :param log_dir: Directory for the accountability log.
    :raises typer.Exit: Code 1 on a guard violation or malformed artifact/input.
    """
    try:
        transcript_text: str | None = None
        if transcript == "-":
            transcript_text = sys.stdin.read()
        elif transcript:
            # Inside the try so an unreadable transcript exits 1 cleanly rather
            # than tracebacking (it is an ``OSError`` like the other read paths).
            transcript_text = Path(transcript).read_text(encoding="utf-8")
        points_text = "[]"
        if points == "-":
            points_text = sys.stdin.read()
        elif points:
            points_text = Path(points).read_text(encoding="utf-8")
        point_list = _parse_points(points_text)
        result = record_mod.record(
            artifact,
            target,
            point_list,
            signed_off_by=signed_off_by or None,
            override=override,
            acknowledgements=_parse_acks(acks),
            transcript=transcript_text,
            log_dir=log_dir,
        )
    except (record_mod.RecordError, OSError) as exc:
        typer.echo(f"defend record failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        json.dumps(
            {
                "outcome": result.outcome,
                "artifact": str(result.artifact),
                "log_entry": str(result.log_entry),
                "transcript": str(result.transcript) if result.transcript else None,
            },
            indent=2,
        )
    )
    raise typer.Exit(code=0)
```

(Note: `--points -` together with `--transcript -` would both try to read
stdin; the second read gets nothing. This is a pre-existing class of
limitation — the prior code had the same issue if it had two stdin-capable
flags — and isn't exercised by any current caller, so no extra handling is
added here per YAGNI.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd defendable-science && uv run pytest tests/test_record.py -v`
Expected: all PASS (this is now the complete, final `test_record.py`).

- [ ] **Step 5: Run the full suite with coverage**

Run: `cd defendable-science && uv run pytest -q`
Expected: 100% statement+branch coverage, all tests pass. If any line/branch
in `_parse_points` or the updated `record` command is uncovered, add the
missing test case from Step 1's list (all documented failure branches should
already be covered — malformed JSON, non-array, non-object item, bad
kwargs/`TypeError`, unreadable file, stdin path).

- [ ] **Step 6: Lint and type-check**

Run: `cd defendable-science && uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: all clean.

- [ ] **Step 7: Commit**

```bash
git add defendable-science/defendable_science/cli.py defendable-science/tests/test_record.py
git commit -m "$(cat <<'EOF'
feat(cli): defend record --points replaces --gaps (ADR-0033)

--gaps took a '||'-delimited string of bare gap facts, which can't carry
structured or multiline evidence. --points takes a JSON-array file path (or
'-' for stdin) of PointRecord objects instead, mirroring the existing
--transcript stdin convention.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: ADR-0033 — evidentiary point records

**Files:**
- Create: `decisions/0033-evidentiary-point-records.md`
- Modify: `decisions/README.md` (append index row)
- Modify: `decisions/0015-defend-cross-cutting.md` (cross-link note)

**Interfaces:**
- Consumes: the shipped behavior from Tasks 1–2 (this ADR documents a decision
  already implemented, matching this repo's convention of ADRs recording
  decisions alongside or after their implementation commit).
- Produces: nothing code-facing — a documentation artifact other tasks/ADRs
  link to (`ADR-0033`).

- [ ] **Step 1: Create the ADR**

Create `decisions/0033-evidentiary-point-records.md`:

```markdown
# ADR-0033: Evidentiary per-point accountability records (`points`, not a bare pass/fail) for `defend` and `digest`

- Status: accepted · Date: 2026-07-27 · Deciders: Davor Runje

## Context

`defendable_science/defend/record.py`'s `record()` only ever stored the *failed*
load-bearing points, as bare strings (`gaps: list[str]`), deriving
`status.understanding: {status: ok|gaps, unresolved: [...]}`. The accountability
log (`docs/research/defend-log/*.yml`) inherited the same shape: a `gaps` list
of short strings, with no record of what grounded the point in the source, or
what the author/reader actually said when probed. This makes the log auditable
only at the coarsest level ("something didn't resolve") — a reviewer of the log
can't tell *what was checked*, *against which text*, or *what the person's
actual answer was*, without re-running the examination. Filing `digest`
(defendable-science#68, the inbound comprehension-verification skill) surfaced this
gap concretely: a meaningful accountability record for "did the reader
understand this paper" needs to show the exact quote grounding each
load-bearing point and the reader's own explanation, not just whether it
passed. The same gap applies to `defend`'s existing targets (`claim`,
`cited-work`, `methodology`) — a bare pass/fail is no more meaningful there.

## Decision drivers

- The accountability log should be independently checkable later — evidence of
  what was probed and what was said, not just an outcome flag.
- Apply uniformly to `defend` and the new `digest` skill — one record shape,
  not two divergent accountability formats for the same underlying mechanic.
- Don't bloat the artifact frontmatter `progress` reads — keep
  `status.understanding: {status, unresolved}` exactly as it is; put the
  richer evidence where the accountability trail already lives.
- Backward compatible — existing log entries are immutable, append-only,
  one file per examination; no migration should be required.

## Considered options

1. **Evidentiary `PointRecord` list in the log; frontmatter unchanged.**
   `record()` takes `points: list[PointRecord]` (`point`, `source_quote`,
   `location`, `reader_answer`, `resolved`, `gap_note`) covering every probed
   point, not just failures. The log entry carries the full list; frontmatter's
   `understanding.unresolved` is derived (`gap_note` or `point`, for
   `resolved: false` points). *(chosen)*
2. **Keep the bare `gaps: list[str]`, add a separate free-form transcript per
   examination.** The existing `transcript` field already allows this
   informally.
3. **Put the evidentiary detail directly in the artifact frontmatter.**

## Decision

Option 1. `record()`'s signature moves from `gaps: list[str]` to `points:
list[PointRecord]`. `TARGETS` gains `paper-comprehension` for `digest`'s use.
The CLI's `--gaps "a||b"` (a delimited bare-string flag, which can't carry
structured or multiline text) is replaced by `--points <file>` / `--points -`
(stdin), a JSON array of point objects — mirroring the existing `--transcript
-` stdin convention.

## Consequences

- The accountability log is now independently checkable: for any resolved or
  unresolved point, the log shows the exact quote that grounds it and what the
  person actually said, without re-running the examination.
- `defend` and `digest` share one record mechanism and one evidentiary shape —
  no divergence to maintain.
- `patch_understanding()` and the artifact frontmatter shape are **unchanged**
  — `progress`'s roll-up logic needs no changes for this ADR.
- Existing log entries (pre-dating this change) keep their old flat `gaps`
  shape; they are immutable, append-only files, so no migration is needed —
  only new entries use `points`.
- `defendable_science/defend/record.py`'s and `defendable_science/cli.py`'s existing
  tests needed updating for the new call shape (not a silent, invisible
  change — every caller of `record()` is affected).

## Rejected alternatives

- **Free-form transcript only (option 2)** — already possible today via the
  `transcript` field, but it's unstructured prose; nothing in the accountability
  *log* itself (the machine-checkable record `progress`/audits can rely on)
  captures the per-point evidence. Kept as a complementary, still-optional
  field, not a substitute.
- **Evidentiary detail in frontmatter (option 3)** — makes every artifact
  `defend`/`digest` touches (`findings.md`, `positioning.md`, `strategy.md`,
  every `digest.md`) carry substantial bulk that `progress`'s design
  deliberately keeps small and orthogonal; rejected to keep that invariant.

## Links

`defendable_science/defend/record.py` (`PointRecord`, `record`, `LogEntry`);
`defendable_science/cli.py` (`defend record`'s `--points`); ADR-0015 (the `defend`
record step this refines); defendable-science#68 (`digest`, the skill that
surfaced this gap).
```

- [ ] **Step 2: Add the index row**

In `decisions/README.md`, after the `[0032](0032-keys-store-outside-repo-by-default.md)` row, add:

```markdown
| [0033](0033-evidentiary-point-records.md) | Evidentiary per-point accountability records (`points`, not a bare pass/fail), shared by `defend` and `digest` | accepted |
```

- [ ] **Step 3: Cross-link from ADR-0015**

In `decisions/0015-defend-cross-cutting.md`, the file ends with:

```markdown
## Links

meta-spec §3.7; sub-spec 1 §6; digest `understanding-and-defense.md`.
```

Replace with:

```markdown
## Links

meta-spec §3.7; sub-spec 1 §6; digest `understanding-and-defense.md`.

> **Refined by ADR-0033.** The Record step's accountability log now carries
> the full per-point evidentiary record (the exact quote grounding each
> probed point + what the author actually said), not a bare pass/fail —
> shared with the `digest` skill (defendable-science#68).
```

- [ ] **Step 4: Verify**

Run: `./tools/validate-plugin.sh` (from repo root)
Expected: `✔ Validation passed` (ADRs aren't plugin-structural, but this
confirms nothing else broke).

Run: `grep -rn "ADR-0033" decisions/ | wc -l`
Expected: at least 2 (the new ADR's own header + the ADR-0015 cross-link).

- [ ] **Step 5: Commit**

```bash
git add decisions/0033-evidentiary-point-records.md decisions/README.md decisions/0015-defend-cross-cutting.md
git commit -m "$(cat <<'EOF'
docs(adr): ADR-0033 — evidentiary point records for defend + digest

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: New `skills/digest/SKILL.md`

**Files:**
- Create: `skills/digest/SKILL.md`

**Interfaces:**
- Consumes: `defend record --target paper-comprehension --points <file>` (Task
  2); the `literature` registry (`references.json`/`triage.yml`, unchanged);
  the mentor-persona framework documented in `skills/defend/SKILL.md`.
- Produces: the `digest` skill, referenced by Task 6 (defend's escalation
  note), Task 7 (literature's composition bullet), Task 8 (progress's
  roll-up), Task 9 (design docs).

- [ ] **Step 1: Create the skill file**

Create `skills/digest/SKILL.md`:

```markdown
---
name: digest
description: Use when you want to read an external paper with verified comprehension — an interactive probe-teach-reprobe loop that builds and checks your understanding of a paper's problem, method, key result, assumptions, and limitations, then emits a grounded digest. Also offered as a deeper remediation path when defend's cited-work probe finds you can't explain what a citation actually says.
---

The `digest` skill is the **inbound** counterpart to `defend`: it verifies the
reader's grasp of *someone else's* paper, the way `defend` verifies the
author's grasp of their own decisions. It reuses `defend`'s probe → teach →
re-probe mechanic (`../../docs/design/00-meta-spec.md` §2.2, the Understanding
principle) in the opposite direction — the paper's content is *established*
external knowledge, so `digest` teaches it freely; it never grades whether the
paper's own claims are right. Grounding:
`../../resources/references/understanding-and-defense.md`,
`../../resources/references/mentor-personas.md`.

This is the reading step that precedes literature triage, positioning, and
citing. It composes with `literature` (the paper must be a registry entry,
grounded in a mirrored PDF) and shares its accountability-log mechanism with
`defend` (ADR-0033) — the same evidentiary `points` record, not a bare
pass/fail.

## When to use

- **Self-invoked.** You've picked a paper to read — off a `scout`-produced
  reading list, a citation you're about to add, or general background — and
  want your understanding of it built and checked, not just summarized at you.
- **Escalation from `defend --target cited-work`.** `defend`'s cited-work probe
  ("does ref [12] actually support this sentence?") surfaces a gap: you can't
  explain what the source says, or your citation misrepresents/overstates it.
  `defend` **offers** to hand off into a full `digest` session on that paper —
  deeper remediation than teaching the one sentence inline.

Do **not** use `digest` to grade the paper's own claims, or to decide whether
it's novel/worth citing — that's `literature`'s `position` mode and the
human's call (see Guardrails).

## How it works

The core is the same retrieval-practice loop as `defend`, run per load-bearing
point until it holds or you elect to stop and record the gap.

1. **Scope.** Resolve the paper against the `literature` registry
   (`references.json`) — if it isn't there yet, `resolve`/`enrich` it first via
   the `literature` CLI, so the digest is grounded in a real registry entry +
   mirrored PDF (cache → mirror → source chain, SHA-256), never a bare URL or
   an unmirrored link.
2. **Probe** one load-bearing point at a time, open-ended: the problem it
   addresses, the method, the key result, its assumptions, its limitations,
   and — when you already have a hypothesis or paper this reading relates to —
   how it bears on your own work. (Skip the last point if there's no bound
   context yet, e.g. early scouting before you've committed to a claim.)
3. **Detect gap.** Judge whether you can *articulate* the point — not whether
   your first answer was right. A gap is an observed inability to explain
   ("couldn't state the method's key assumption"), never a verdict on the
   paper's correctness.
4. **Teach**, source-grounded, from the paper itself. Established external
   content → explain freely and point at the exact section, equation, or
   table. (Contrast a *novel claim* under `defend`, which never gets its
   answer key supplied — a published paper's content isn't that.)
5. **Re-probe** (possibly reframed) until you can state the point in your own
   words, or you explicitly park it as an unresolved gap.
6. **Record** (see below) and, if warranted, update the paper's `triage.yml`
   row.

**Out of scope.** One `digest` run covers one paper — for a reading list, run
it once per paper. `digest` never adjudicates whether the paper's own claims
are correct, contested, or wrong; a reader's disagreement with the paper
surfaces as a flagged, unresolved point, never a verdict.

## Record — evidentiary, not a pass flag

Uses the same `defendable-science defend record` CLI as `defend` (ADR-0033),
target `paper-comprehension`:

```
defendable-science defend record \
  --artifact docs/research/literature/digests/smith2024.md \
  --target paper-comprehension \
  --points points.json
```

`points.json` is a JSON array, one entry per probed load-bearing point:

```json
[
  {
    "point": "assumptions",
    "source_quote": "We assume the loss is Lipschitz-continuous (Eq. 3).",
    "location": "§3, Eq. 3",
    "reader_answer": "They need the loss to not change too fast so the bound in Thm 1 holds.",
    "resolved": true
  },
  {
    "point": "limitations",
    "source_quote": "Our analysis does not cover the non-convex case.",
    "location": "§5, final paragraph",
    "reader_answer": "Not sure why non-convexity breaks it.",
    "resolved": false,
    "gap_note": "could not explain why non-convexity breaks the analysis"
  }
]
```

This patches `status.understanding` in the digest's frontmatter — the same
`{status: ok|gaps, unresolved: [...]}` shape `progress` already reads — and
appends the full per-point record (source quote + your actual answer, for
every point, not just the failed ones) to the accountability log
(`docs/research/defend-log/`). The frontmatter stays small; the log is where
the evidence lives, independently checkable later without re-running the
session.

## Output artifact

`docs/research/literature/digests/<citekey>.md` — one file per digested
source paper, named by citekey so it joins trivially with
`references.json`/`triage.yml`. Git-tracked, citeable.

- **Frontmatter**: a `status:` block carrying `understanding` +
  `last-updated` (patched by `defend record`, above).
- **Body**: faithful summary; key equations/claims; assumptions; limitations;
  and, when applicable, an explicit "relation to my work" section.

**Triage update.** On completion, update the paper's `triage.yml` row —
`notes` and a `seeded` link back to the digest, `disposition` advanced if
warranted. This is a direct edit to the YAML (there is no CLI for
`triage.yml` today; `literature`'s CLI only exposes the graph primitives),
consistent with current practice.

## Composition

- **`literature`** is the substrate: `digest` resolves/grounds the paper
  against `references.json` and the mirrored PDF, and writes back to
  `triage.yml` on completion.
- **`defend`** shares the engine and the record mechanism (ADR-0033); its
  `cited-work` target escalates into `digest` on a comprehension gap (see
  When to use).
- **`progress`** surfaces digested-vs-unresolved counts from
  `docs/research/literature/digests/*.md` frontmatter as an independent
  "literature reading" view (`../progress/SKILL.md`), alongside — not folded
  into — the hypothesis/paper/thesis roll-ups.

## Mentor persona

Reuses `defend`'s persona framework and its three author-controllable levers
(self-selected / stage-suggested / feedback-calibrated — never inferred from
personality; `../../resources/references/mentor-personas.md`). **Default:
sounding board** — `digest` is a first-read/tutoring context, not a decision
defense, so the default leans exploratory rather than `defend`'s
critical-examiner default.

## Guardrails

Load-bearing rules, not preferences — mirrors `defend`'s stance in the inbound
direction.

- **Ask, don't grade the paper's substance.** Report observed facts ("couldn't
  state the key assumption"), never "this paper is wrong" — that's outside
  this skill's authority and outside its job. A reader's disagreement with the
  paper is recorded as an unresolved point, not adjudicated.
- **Teach the paper freely, source-grounded.** Its content is established
  external knowledge (unlike a novel claim under `defend`) — explain and
  quote it directly, point at the exact section/equation.
- **Verified, never self-attested.** `understanding.status: ok` only when the
  reader has demonstrated each load-bearing point against the probe — no
  "I've got it" shortcut (anti-Goodhart, same as `defend`).
- **Propose/surface, never adjudicate novelty or inclusion.** Whether a paper
  is worth citing, novel, or in-scope stays with `literature position` and the
  human's sign-off. `digest` feeds that judgment; it doesn't make it.
- **Non-blocking.** The `cited-work` escalation is stop/offer, never a hard
  block — the human can decline and proceed, same as `defend`'s guardrail
  semantics.

## Commit attribution

When you commit artifacts produced by this skill, add these git trailers —
discovery + provenance (see [`../../resources/commit-attribution.md`](../../resources/commit-attribution.md)):

```
Generated-with: defendable-science (https://github.com/davorrunje/defendable-science)
DefendableScience-Skill: digest
```
```

- [ ] **Step 2: Verify the plugin still validates**

Run: `./tools/validate-plugin.sh` (from repo root)
Expected: `✔ Validation passed` (confirms the new skill directory/frontmatter
is structurally valid).

- [ ] **Step 3: Commit**

```bash
git add skills/digest/SKILL.md
git commit -m "$(cat <<'EOF'
feat(skills): add the digest skill (#68)

Inbound counterpart to defend: verifies the reader's grasp of an external
paper via the same probe-teach-reprobe mechanic, in the opposite direction.
Self-invoked, or offered as an escalation from defend's cited-work gap.
Emits a digest artifact + an evidentiary understanding record (ADR-0033) and
updates the paper's triage.yml row.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: ADR-0034 — the `digest` skill

**Files:**
- Create: `decisions/0034-digest-skill.md`
- Modify: `decisions/README.md` (append index row)

**Interfaces:**
- Consumes: Task 4 (`skills/digest/SKILL.md`), ADR-0033 (Task 3), ADR-0015.
- Produces: nothing code-facing — cross-linked from Tasks 6–9's edits.

- [ ] **Step 1: Create the ADR**

Create `decisions/0034-digest-skill.md`:

```markdown
# ADR-0034: A dedicated `digest` skill for inbound paper comprehension (not a `defend` target)

- Status: accepted · Date: 2026-07-27 · Deciders: Davor Runje

## Context

`defend` verifies the author's grasp of their own material decisions and,
via `cited-work`, whether a citation supports a specific sentence. There is no
inbound counterpart: a skill for reading an external paper with *verified*
comprehension — building and checking understanding of the whole paper, not
just one cited sentence — before it's triaged, positioned, or cited.
defendable-science#68 filed this gap, motivated by `davorrunje/mononet`'s
`survey-monotonicity-ml` reading list (~21 method papers a `literature scout`
run surfaced, which must be genuinely read and understood, not skimmed) and
that consumer repo's existing hand-curated-digest convention.

## Decision drivers

- Reuse `defend`'s probe → teach → re-probe mechanic rather than reinventing
  it, since the underlying learning-science grounding
  (`understanding-and-defense.md`) is direction-agnostic.
- The *direction* is genuinely inverted from `defend`: verifying grasp of
  someone else's (established, external) content, vs. defending your own
  (possibly novel) decision. `defend`'s never-supply-a-novel-claim's-answer
  rule doesn't apply the same way — a published paper's content isn't a novel
  claim needing protection.
- The output differs materially: a new digest artifact + a `triage.yml`
  update, not an in-place patch to an existing lifecycle artifact.
  `defend`'s existing `TARGETS` enum (`claim`, `cited-work`, `methodology`)
  models three ways of probing *your own* material — an inbound direction
  doesn't fit that enum's semantics.

## Considered options

1. **Dedicated `digest` skill**, cross-cutting alongside `progress`/`defend`,
   with its own SKILL.md, own trigger conditions, own output shape — sharing
   `defend`'s accountability-record mechanism (ADR-0033) but not its skill
   file. *(chosen)*
2. **`defend --target paper-comprehension`** — extend `defend`'s existing
   `TARGETS` and SKILL.md instead of adding a new skill file.
3. **Fold into `literature`** as a third mode alongside `scout`/`position`.

## Decision

Option 1. `digest` is self-invoked (the author picks a paper to read) or
fired as an **escalation from `defend --target cited-work`** when that probe
finds the citation is misunderstood or misrepresented — reusing `defend`'s
existing guardrail stop/offer/log semantics rather than inventing a new
guardrail mechanism. Default persona is *sounding board* (a first-read/
tutoring context), not `defend`'s critical-examiner default. Output:
`docs/research/literature/digests/<citekey>.md` + a `triage.yml` update;
`progress` gains an independent "literature reading" roll-up view.

## Consequences

- `defend`'s SKILL.md needs only a small, additive edit (the `cited-work`
  target row gets the escalation note) — not a rewrite or a semantic
  overload of its `TARGETS` enum.
- One more skill file to maintain, but each of `defend`/`digest` stays legible
  on its own — a reader of `digest` doesn't have to parse `defend`'s
  outbound-direction guardrail semantics to understand it.
- `literature`'s `SKILL.md` and `progress`'s `SKILL.md` each need a small,
  additive edit (composition note; new roll-up section) — no restructuring.

## Rejected alternatives

- **`defend --target paper-comprehension` (option 2)** — would overload
  `TARGETS`' enum semantics (three outbound, one inbound) and mix `defend`'s
  guardrail-at-material-decision framing with a self-invoked, non-guardrail-by-
  default reading workflow; the shared record mechanism (ADR-0033) already
  gets the reuse benefit without this cost.
- **Fold into `literature` (option 3)** — `literature`'s two modes
  (`scout`/`position`) are both citation-graph operations; `digest`'s core is
  a Socratic loop, not a graph operation, even though it grounds in
  `literature`'s registry. Composition (`literature`'s Composition section)
  gets the benefit without conflating the two.

## Links

`skills/digest/SKILL.md`; `skills/defend/SKILL.md` (the `cited-work`
escalation note); `skills/literature/SKILL.md` (Composition);
`skills/progress/SKILL.md` (literature reading roll-up); ADR-0033 (the shared
evidentiary record mechanism); ADR-0015 (`defend`'s original design);
defendable-science#68.
```

- [ ] **Step 2: Add the index row**

In `decisions/README.md`, after the ADR-0033 row added in Task 3, add:

```markdown
| [0034](0034-digest-skill.md) | Dedicated `digest` skill for inbound paper comprehension, not a `defend` target | accepted |
```

- [ ] **Step 3: Verify and commit**

Run: `./tools/validate-plugin.sh`
Expected: `✔ Validation passed`

```bash
git add decisions/0034-digest-skill.md decisions/README.md
git commit -m "$(cat <<'EOF'
docs(adr): ADR-0034 — the digest skill (#68)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Edit `skills/defend/SKILL.md` — evidentiary record + `cited-work` escalation

**Files:**
- Modify: `skills/defend/SKILL.md`

**Interfaces:**
- Consumes: `skills/digest/SKILL.md` (Task 4), ADR-0033 (Task 3).

- [ ] **Step 1: Update the "Record" step and its tooling note**

Find this block (step 6 of "How it works", plus the tooling callout right
after it):

```markdown
6. **Record.** Write an `understanding` status to the artifact frontmatter
   (feeds the `progress` roll-up) and, optionally, an examination transcript.
   Unanswered probes and any logged overrides are the accountability trail. If
   fired as a guardrail, follow Guardrail semantics.

> **Tooling.** The record step is the `defendable-science defend record` CLI command
> (`defendable_science/defend/record.py`) — ensure via
> [`ensure-tooling`](../../resources/ensure-tooling.md); it appends the
> `understanding` frontmatter block and persists the transcript. By hand (if the CLI
> isn't available): under the `status:` block set `understanding: {status: ok|gaps,
> unresolved: [...]}` to match the schema `progress` reads (`../progress/SKILL.md`),
> and bump `status.last-updated` (do **not** nest a date inside `understanding`); if
> a transcript is kept, write it beside the artifact as `defend-<date>.md`.
```

Replace with:

```markdown
6. **Record.** Write an `understanding` status to the artifact frontmatter
   (feeds the `progress` roll-up) and, optionally, an examination transcript.
   The full evidentiary record — the exact quote grounding each probed point
   plus what the author actually said, resolved or not (ADR-0033) — goes to the
   accountability log, not just the frontmatter. Unanswered probes and any
   logged overrides are the accountability trail. If fired as a guardrail,
   follow Guardrail semantics.

> **Tooling.** The record step is the `defendable-science defend record` CLI command
> (`defendable_science/defend/record.py`) — ensure via
> [`ensure-tooling`](../../resources/ensure-tooling.md); it appends the
> `understanding` frontmatter block and the log entry, and persists the
> transcript. Pass the probed points as `--points <file>` (or `--points -` for
> stdin) — a JSON array of `{point, source_quote, reader_answer, resolved,
> location?, gap_note?}` objects, one per load-bearing point probed, not just
> the failures (ADR-0033). By hand (if the CLI isn't available): under the
> `status:` block set `understanding: {status: ok|gaps, unresolved: [...]}` to
> match the schema `progress` reads (`../progress/SKILL.md`), and bump
> `status.last-updated` (do **not** nest a date inside `understanding`); if a
> transcript is kept, write it beside the artifact as `defend-<date>.md`.
```

- [ ] **Step 2: Add the `cited-work` escalation note**

Find the Targets table:

```markdown
| Target | What it probes | Teach from |
|---|---|---|
| `claim` | the author's own scientific claim — entailments, assumptions, rivals, falsifiers, limitations | *how to reason/defend* only; never the answer key |
| `cited-work` | do the cited works actually support the claim; what each source really says | the author's citations + the source texts |
| `methodology` | the *why* behind a rigor-kit method, not the ritual | the methodology digests + authoritative refs |
```

Immediately after that table (before the "**Stage presets**" paragraph), add:

```markdown

On a `cited-work` gap — you can't explain what the source says, or the
citation misrepresents it — offer a deeper remediation than an inline
correction: a full `digest` session on that paper (`../digest/SKILL.md`).
Same guardrail stop/offer/log semantics; no new mechanism.
```

- [ ] **Step 3: Verify**

Run: `./tools/validate-plugin.sh`
Expected: `✔ Validation passed`

Run: `grep -n "digest\|ADR-0033" skills/defend/SKILL.md`
Expected: both the Record-step ADR-0033 mention and the `cited-work`
escalation's `digest` link are present.

- [ ] **Step 4: Commit**

```bash
git add skills/defend/SKILL.md
git commit -m "$(cat <<'EOF'
docs(defend): evidentiary record + cited-work escalation to digest (#68)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Edit `skills/literature/SKILL.md` — composition with `digest`

**Files:**
- Modify: `skills/literature/SKILL.md`

**Interfaces:**
- Consumes: `skills/digest/SKILL.md` (Task 4).

- [ ] **Step 1: Add the composition bullet**

Find the "## Composition" section:

```markdown
## Composition

- **`hypothesis-exploration` / `paper-exploration`** consume `scout` rows as
  proposals; they apply the idea-shaping lenses (gap-spotting vs. problematization;
  feasibility × interest) — `scout` does not.
- **`hypothesis-testing`** reads `position --level hypothesis` verdicts into
  `strategy.md`. **`paper-synthesis`** reads `position --level paper` into
  `positioning.md` and the baseline list. **`thesis`** reads
  `position --level thesis` into the kappa's independent related-work chapter.
- **`defend`** (target `cited-work`) draws on this registry to check "does ref [12]
  actually support this sentence?" — the same surface-don't-adjudicate posture.
- **Substrate**: shares the persistent-ID / mirror / fixity mechanism with
  `dataset`; both are front-ends over one substrate, not one shared file.
```

Replace the `defend` and `Substrate` bullets with (inserting a new `digest`
bullet between them):

```markdown
- **`defend`** (target `cited-work`) draws on this registry to check "does ref [12]
  actually support this sentence?" — the same surface-don't-adjudicate posture.
- **`digest`** grounds each paper it digests in this registry (a
  `references.json` entry + mirrored PDF) and writes back to the `triage.yml`
  row on completion — the reading step that precedes triage/positioning
  (`../digest/SKILL.md`).
- **Substrate**: shares the persistent-ID / mirror / fixity mechanism with
  `dataset`; both are front-ends over one substrate, not one shared file.
```

- [ ] **Step 2: Verify**

Run: `./tools/validate-plugin.sh`
Expected: `✔ Validation passed`

- [ ] **Step 3: Commit**

```bash
git add skills/literature/SKILL.md
git commit -m "$(cat <<'EOF'
docs(literature): note digest's composition with the registry (#68)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Edit `skills/progress/SKILL.md` — literature reading roll-up

**Files:**
- Modify: `skills/progress/SKILL.md`

**Interfaces:**
- Consumes: `skills/digest/SKILL.md` (Task 4), the `docs/research/literature/digests/<citekey>.md` frontmatter shape it writes.

- [ ] **Step 1: Update the Verbs table**

Find:

```markdown
| Verb | What it does |
|---|---|
| `status <level> [id]` | Read the frontmatter for one artifact (`id` given) or every artifact at a level (`hypothesis` \| `paper` \| `thesis`), roll it up per the rules below, and print a coverage + blockers view. No files written. |
| `dashboard` | Regenerate `docs/research/dashboard.md` as a **pure projection** of all status frontmatter. The only file progress writes — and it is machine-owned, never hand-edited. |
```

Replace the `status` row with:

```markdown
| `status <level> [id]` | Read the frontmatter for one artifact (`id` given) or every artifact at a level (`hypothesis` \| `paper` \| `thesis` \| `literature`), roll it up per the rules below, and print a coverage + blockers view. No files written. |
```

- [ ] **Step 2: Add the "Literature reading" section**

Find the end of "## Roll-up rules" (right before "## Anti-Goodhart"):

```markdown
Output shape everywhere: `{covered / total by state}` + `{explicit blockers}` +
`{stale?}`. No rolled-up number leaves this skill.

## Anti-Goodhart
```

Insert a new section between them:

```markdown
Output shape everywhere: `{covered / total by state}` + `{explicit blockers}` +
`{stale?}`. No rolled-up number leaves this skill.

## Literature reading

A fourth roll-up, independent of the hypothesis/paper/thesis hierarchy above
(`status literature`): scan `docs/research/literature/digests/*.md`
frontmatter directly — the `understanding` block the `digest` skill writes via
`defend record --target paper-comprehension` (ADR-0033) — and report, per
digested paper, `{digested & understood / gaps unresolved}`, joined against
`triage.yml` by citekey for context (role, disposition). Same anti-Goodhart
posture as everywhere else in this skill: coverage + named gaps, never a count
of "papers read" as a productivity signal.

## Anti-Goodhart
```

- [ ] **Step 3: Verify**

Run: `./tools/validate-plugin.sh`
Expected: `✔ Validation passed`

Run: `grep -n "Literature reading\|status literature" skills/progress/SKILL.md`
Expected: both present.

- [ ] **Step 4: Commit**

```bash
git add skills/progress/SKILL.md
git commit -m "$(cat <<'EOF'
docs(progress): add the literature-reading roll-up for digest (#68)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Design docs — skill tree, content layout, CLAUDE.md

**Files:**
- Modify: `docs/design/00-meta-spec.md`
- Modify: `docs/design/01-lifecycle.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: `skills/digest/SKILL.md` (Task 4).

- [ ] **Step 1: Add `digest` to the meta-spec skill tree**

In `docs/design/00-meta-spec.md`, find:

```
│   ├── progress/SKILL.md                 # status | dashboard (cross-cutting, read-only)
│   └── defend/SKILL.md                  # claim|cited-work|methodology; self + guardrail (cross-cutting)
```

Replace with:

```
│   ├── progress/SKILL.md                 # status | dashboard (cross-cutting, read-only)
│   ├── defend/SKILL.md                  # claim|cited-work|methodology; self + guardrail (cross-cutting)
│   └── digest/SKILL.md                  # inbound paper comprehension; self + defend escalation (cross-cutting)
```

- [ ] **Step 2: Add `digests/` to the lifecycle content layout and plugin-side list**

In `docs/design/01-lifecycle.md`, find:

```markdown
## 7. Content layout (consumer `docs/research/`)

Per meta-spec §5: `papers.md` registry; per-paper roots with
`hypotheses/<YYYY-MM-DD-slug>/{hypothesis,strategy,design,plan,findings}.md`,
`backlog.md`, `paper/{pitch,positioning,outline,ledger,decision,sections/}`;
`portfolio-backlog.md`; optional `thesis/{kappa,aims.md,milestones.yml}`;
`literature/{references.bib,triage.yml}`; generated `dashboard.md`. Status
frontmatter on every hypothesis/paper/thesis artifact feeds `progress`; examination
transcripts + logged overrides form the accountability trail.
```

Replace the `literature/{...}` clause with:

```markdown
## 7. Content layout (consumer `docs/research/`)

Per meta-spec §5: `papers.md` registry; per-paper roots with
`hypotheses/<YYYY-MM-DD-slug>/{hypothesis,strategy,design,plan,findings}.md`,
`backlog.md`, `paper/{pitch,positioning,outline,ledger,decision,sections/}`;
`portfolio-backlog.md`; optional `thesis/{kappa,aims.md,milestones.yml}`;
`literature/{references.bib,triage.yml,digests/<citekey>.md}`; generated
`dashboard.md`. Status frontmatter on every hypothesis/paper/thesis artifact
feeds `progress`; examination transcripts + logged overrides form the
accountability trail.
```

Then find, in "## 9. Plugin vs. consumer":

```markdown
- **Plugin:** the five pipeline skills + `progress` + `defend`; staged-doc + kappa
  templates; the rigor kit; the firewall/flywheel logic; the persona set. Depends
  only on the capability contracts (experiment backend, engineering backend,
  `literature`, `dataset`) and delegates engineering to the bound engineering
  backend via the engineering-delegation contract.
```

Replace with:

```markdown
- **Plugin:** the five pipeline skills + `progress` + `defend` + `digest`;
  staged-doc + kappa templates; the rigor kit; the firewall/flywheel logic; the
  persona set. Depends only on the capability contracts (experiment backend,
  engineering backend, `literature`, `dataset`) and delegates engineering to
  the bound engineering backend via the engineering-delegation contract.
```

- [ ] **Step 3: Update `CLAUDE.md`'s cross-cutting skill list**

In `CLAUDE.md`, find:

```markdown
Cross-cutting: `progress` (reads status frontmatter → dashboard; never a productivity score) and `defend` (Socratic tutor-examiner guardrail). Shared capabilities: `literature`, `dataset`. Onboarding: `research-init` (`init`/`adopt`). Two load-bearing principles run through everything: **agency** (the human makes and signs every material decision) and **understanding** (`defend` verifies + teaches before a decision is recorded). *Engineering* (design/plan/code) is deliberately **delegated** to a bound backend via the engineering-delegation contract (ADR-0023) — the plugin never implements it.
```

Replace with:

```markdown
Cross-cutting: `progress` (reads status frontmatter → dashboard; never a productivity score), `defend` (Socratic tutor-examiner guardrail), and `digest` (defend's inbound counterpart — verified comprehension of external papers). Shared capabilities: `literature`, `dataset`. Onboarding: `research-init` (`init`/`adopt`). Two load-bearing principles run through everything: **agency** (the human makes and signs every material decision) and **understanding** (`defend` verifies + teaches before a decision is recorded). *Engineering* (design/plan/code) is deliberately **delegated** to a bound backend via the engineering-delegation contract (ADR-0023) — the plugin never implements it.
```

- [ ] **Step 4: Verify**

Run: `./tools/validate-plugin.sh`
Expected: `✔ Validation passed`

Run: `grep -rln "digest" docs/design/00-meta-spec.md docs/design/01-lifecycle.md CLAUDE.md`
Expected: all three files listed.

- [ ] **Step 5: Commit**

```bash
git add docs/design/00-meta-spec.md docs/design/01-lifecycle.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(design): add digest to the skill tree, content layout, CLAUDE.md (#68)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Full verification pass + PR

**Files:** none (verification only)

**Interfaces:** none — this task confirms Tasks 1–9 compose correctly.

- [ ] **Step 1: Full package test suite with coverage**

Run: `cd defendable-science && uv run pytest -q`
Expected: 100% statement+branch coverage, all tests pass (no skips beyond the
pre-existing `@pytest.mark.live` ones).

- [ ] **Step 2: Lint, format, type-check**

Run: `cd defendable-science && uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: all clean.

- [ ] **Step 3: Plugin structural validation**

Run: `./tools/validate-plugin.sh` (from repo root)
Expected: `✔ Validation passed`.

- [ ] **Step 4: Pre-commit on the full changed set**

Run (from repo root): `pre-commit run --files $(git diff --name-only main)`
Expected: every hook (trailing whitespace, codespell, ruff lint/format, mypy,
plugin-validate, detect-secrets) passes.

- [ ] **Step 5: Cross-reference sanity check**

Run: `grep -rn "ADR-0031\b" --include="*.md" --include="*.py" . | grep -v "\.git/"`
Expected: every hit is genuinely about ADR-0031 (config-driven cache dir) —
none about keys or points/digest (guards against repeating the ADR-numbering
mix-up from PR #71).

Run: `grep -rln "paper-comprehension" defendable-science/defendable_science defendable-science/tests skills/`
Expected: `defendable_science/defend/record.py`, `defendable_science/cli.py`,
`tests/test_record.py`, `skills/digest/SKILL.md`.

- [ ] **Step 6: Open the PR**

Use the local `create-pr` skill (branch/commit/checks/body conventions,
`Closes #68` trailer, discovery trailers from `resources/commit-attribution.md`
if applicable — check whether this counts as a "skill-produced artifact"
commit or a plain maintainer commit before adding them). The branch is already
`design/68-digest-skill` with the spec commit at its base; Tasks 1–9's commits
land on top of it.

---

## Self-Review Notes

- **Spec coverage:** every `docs/superpowers/specs/2026-07-22-digest-skill-design.md`
  section maps to a task — §2/§3 shape → Task 4; §4 evidentiary record → Tasks
  1–3; §5 output artifact → Task 4; §6 progress → Task 8; §7 file layout →
  Tasks 1–9 collectively; §9 acceptance criteria → verified by Task 10's runs
  plus the new tests in Tasks 1–2 (comprehension loop termination and
  self-attestation are process guardrails documented in Task 4's SKILL.md
  text, not machine-testable — consistent with how `defend`'s own guardrails
  are unit-tested only at the `record()`/CLI layer, not the Socratic-loop
  layer itself).
- **Placeholder scan:** no TBD/TODO; every step shows complete file content or
  a complete diff, not a description of one.
- **Type consistency:** `PointRecord` fields (`point`, `source_quote`,
  `reader_answer`, `resolved`, `location`, `gap_note`) are identical across
  Task 1's dataclass, Task 2's CLI JSON schema and tests, and Task 4's
  SKILL.md example — checked by hand across all four.
