# ADR-0033: Evidentiary per-point accountability records (`points`, not a bare pass/fail) for `defend` and `digest`

- Status: accepted · Date: 2026-07-27 · Deciders: Davor Runje

## Context

`honest_scholar/defend/record.py`'s `record()` only ever stored the *failed*
load-bearing points, as bare strings (`gaps: list[str]`), deriving
`status.understanding: {status: ok|gaps, unresolved: [...]}`. The accountability
log (`docs/research/defend-log/*.yml`) inherited the same shape: a `gaps` list
of short strings, with no record of what grounded the point in the source, or
what the author/reader actually said when probed. This makes the log auditable
only at the coarsest level ("something didn't resolve") — a reviewer of the log
can't tell *what was checked*, *against which text*, or *what the person's
actual answer was*, without re-running the examination. Filing `digest`
(honest-scholar#68, the inbound comprehension-verification skill) surfaced this
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
- `honest_scholar/defend/record.py`'s and `honest_scholar/cli.py`'s existing
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

`honest_scholar/defend/record.py` (`PointRecord`, `record`, `LogEntry`);
`honest_scholar/cli.py` (`defend record`'s `--points`); ADR-0015 (the `defend`
record step this refines); honest-scholar#68 (`digest`, the skill that
surfaced this gap).
