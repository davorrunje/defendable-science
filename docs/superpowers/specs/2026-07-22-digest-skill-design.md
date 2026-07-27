# `digest` skill — design

**Date:** 2026-07-22
**Author:** Davor Runje (design session with Claude)
**Status:** Draft — pending review
**Resolves:** [#68](https://github.com/davorrunje/honest-scholar/issues/68)

## 1. Problem

`honest-scholar` has `defend` for verifying the author's grasp of *their own*
material decisions (findings verdict, publish decision, thesis defensibility) and,
via its `cited-work` target, whether a specific citation supports a specific
sentence. There is no **inbound** counterpart: a skill for digesting an
*external* paper with verified comprehension — sitting the reader down with a
paper, probing, teaching where shaky, and continuing until they can actually
explain it, then capturing a grounded digest. This is the reading step that
precedes literature triage, positioning, and citing, and today happens ad hoc.

Motivating case: `davorrunje/mononet`'s `survey-monotonicity-ml` reading list
(~21 method papers from a `literature scout` run) that must be genuinely read and
understood before triage/citation, plus the consumer repo's existing
hand-curated-digest convention (`docs/references/<paper>.md`).

## 2. Shape & placement

A new **cross-cutting skill**, `skills/digest/SKILL.md`, alongside `progress` and
`defend` — not nested under `literature`, not a new `defend` target. It documents
its own probe→teach→re-probe loop in parallel prose to `defend`'s: same mechanic,
inverted direction. `defend` verifies the author's grasp of *their own* decisions;
`digest` verifies the author's grasp of *someone else's* paper.

### Invocation — two paths

1. **Self-invoked.** The author explicitly runs `digest` on a paper they've
   chosen to read (e.g. working through a `scout`-produced reading list).
2. **Escalation from `defend --target cited-work`.** `defend`'s existing
   cited-work probe ("does ref [12] actually support this sentence?") already
   asks the author to explain what the source says. When that probe surfaces a
   gap — the author can't explain it, or the citation misrepresents/overstates
   the source's claim — `defend` **offers** to hand off into a full `digest`
   session on that paper, as deeper remediation than teaching the one sentence
   inline. This reuses `defend`'s existing guardrail stop/offer/log semantics; no
   new guardrail mechanism. `digest` stays non-blocking (stop/offer, never a hard
   block), consistent with agency.

`digest` requires a small, additive edit to `skills/defend/SKILL.md` (the
`cited-work` target row gets the escalation note) — not a rewrite.

### Persona

Reuses `defend`'s mentor-persona framework (sounding board / critical examiner /
directive editor / opt-in devil's advocate) and its three author-controllable
levers (self-selected / stage-suggested / feedback-calibrated — never inferred
from personality). **Default: sounding board**, not `defend`'s critical-examiner
default — `digest` is a first-read/tutoring context, not a decision defense.

## 3. The loop and load-bearing points

Same probe → detect-gap → teach → re-probe → record mechanic as `defend`, written
in `digest`'s own SKILL.md scoped to this direction (not copy-pasted).

1. **Scope.** Resolve the target paper against the `literature` registry
   (`references.json`) — if absent, resolve/enrich it via the `literature` CLI
   first, so the digest is grounded in a real registry entry + mirrored PDF
   (cache → mirror → source chain, SHA-256), never a bare URL.
2. **Probe** each load-bearing point: problem, method, key result, assumptions,
   limitations, and *relation to the reader's own work* — the last skipped/
   deferred when there's no bound hypothesis/paper context yet (e.g. early
   scouting, before committing to a claim it relates to).
3. **Detect gap** — an observed inability to articulate, never a verdict on the
   paper's correctness (mirrors `defend`'s standard exactly).
4. **Teach**, source-grounded from the paper itself (established external
   content → teach freely, unlike a novel claim). Point at the exact
   section/equation/table.
5. **Re-probe** until the reader can state each point in their own words, or
   explicitly parks a named gap.
6. **Record** (see §4).

**Out of scope for v1:** batch/multi-paper digesting in one run (one `digest` run
= one paper); grading the paper's own claims (mirrors `defend`'s never-grade-
substance stance — a misunderstood-or-wrong paper surfaces as the reader's
*unresolved* gap or a flagged disagreement, never an adjudication).

## 4. Record — evidentiary, not a pass flag

This changes the **shared** `honest_scholar/defend/record.py` used by both
`defend` and `digest` — not just adding a target.

Today, `record()` takes `gaps: list[str]` (only the *failed* points, as bare
strings) and derives `status: ok|gaps`. This is not meaningful enough as an
accountability record: it says whether something passed, not what was actually
checked or against which text.

**New shape.** `record()` moves from `gaps: list[str]` to `points:
list[PointRecord]`, covering *every* probed load-bearing point (resolved or not).
Each `PointRecord`:

| Field | Meaning |
|---|---|
| `point` | Which load-bearing point (e.g. `assumptions`, `key-result`, `cited-work-support`) |
| `source_quote` | The exact quote grounding it — from the *paper* for `digest`, from the *author's own artifact/claim* for `defend` |
| `location` | Where the quote lives (section/equation/sentence), when locatable |
| `reader_answer` | What the reader/author actually said, in their own words |
| `resolved` | Whether the point held after teaching + re-probe |
| `gap_note` | Short free-text gap fact when `resolved: false` (e.g. "no answer to the falsification probe") — carries forward exactly what today's bare `gaps: list[str]` entries held |

- **Accountability log** (`docs/research/defend-log/*.yml`) carries the full
  `points` list — independently checkable later without re-running the session:
  it shows both what grounds the point and what the person actually said.
- **Frontmatter is unchanged in shape**: `status.understanding: {status: ok|gaps,
  unresolved: [...]}`, with `unresolved` derived from `points` as `[p.gap_note or
  p.point for p in points if not p.resolved]` — falls back to the bare point name
  only if no `gap_note` was given, so today's minimal-caller behavior still works.
  `progress`'s roll-up logic doesn't change; no bloat on the artifact.
- **Backward compatible.** Log entries are immutable, append-only, one file per
  examination — existing entries (old flat `gaps: list[str]`) simply predate the
  richer schema. No migration.

**CLI change (`defend record`).** `--gaps "a||b"` (delimited bare strings) can't
carry structured, possibly-multiline quotes. Replace with `--points <file>` or
`--points -` (stdin), a JSON array of `PointRecord` objects — mirrors the existing
`--transcript -` stdin convention. `TARGETS` gains a new value, `paper-
comprehension`, for `digest`'s use.

**Design note (not this design's job to resolve, flagging for writing-plans):**
this is a real behavior change to `defend`'s already-shipped, ADR-0015 record
step. It needs its own ADR, cross-linked to/from ADR-0015 (extends, doesn't
replace, its "Record" step) — not folded silently into the digest ADR.

## 5. Output artifact

`docs/research/literature/digests/<citekey>.md` — one file per digested source
paper, named by citekey so it joins trivially with `references.json`/
`triage.yml`.

- **Frontmatter**: a `status:` block carrying `understanding` + `last-updated`,
  the same shape `progress` already reads.
- **Body**: faithful summary, key equations/claims, assumptions, limitations, and
  an explicit "relation to my work" section (when applicable) — matches the
  `mononet` curated-digest convention.

**Triage update on completion.** The paper's `triage.yml` row gets `notes` + a
`seeded` link back to the digest, and `disposition` advanced if warranted. This
is a **direct YAML edit** by the skill/agent — there is no CLI for `triage.yml`
today (the `literature` CLI only exposes graph primitives: `resolve / cites /
refs / enrich / neighbors`), so this matches current practice, not a regression.

## 6. `progress` integration

`progress` needs no new code — it has **no CLI/Python module at all** today;
`status`/`dashboard` are purely agent-executed instructions reading frontmatter
directly (confirmed against the current codebase). The new roll-up is a
**`skills/progress/SKILL.md` prose addition only**: a "literature reading"
view, independent of the hypothesis/paper/thesis hierarchy, scanning
`docs/research/literature/digests/*.md` frontmatter and reporting
`{digested & understood / gaps unresolved}` counts per paper — same anti-Goodhart
posture as the rest of `progress` (coverage + blockers, never a score).

## 7. File/module layout summary

- `skills/digest/SKILL.md` — new.
- `skills/defend/SKILL.md` — edit: `cited-work` row gets the escalation-to-digest
  note; loop description reflects evidentiary `points`.
- `skills/progress/SKILL.md` — edit: new "literature reading" roll-up section.
- `skills/literature/SKILL.md` — edit: Composition section mentions `digest`.
- `honest_scholar/defend/record.py` — `PointRecord` dataclass; `points` replaces
  `gaps`; `TARGETS` gains `paper-comprehension`.
- `honest_scholar/cli.py` — `defend record`'s `--gaps` → `--points` (file/stdin
  JSON).
- Two new ADRs: (a) the `digest` skill itself; (b) the evidentiary-`points`
  record-schema change (cross-linked to/from ADR-0015).
- `docs/design/00-meta-spec.md` / `01-lifecycle.md` — add `digest` to the
  skill-tree diagram and `docs/research/literature/digests/` to the
  content-layout section.

**Known pre-existing conflict to resolve before ADR numbering here:** PR #70
(#65 fix) and PR #71 (#66 fix) each independently added a `decisions/0031-*.md`
— one needs renumbering at merge time before this design's ADRs claim a number.

## 8. Testing implications (detail deferred to the implementation plan)

- `honest_scholar/defend/record.py`'s existing test suite needs updating for the
  `points`-schema change; 100%-statement+branch coverage gate applies as usual
  (ADR-0028).
- New tests for `digest`'s CLI usage (`--target paper-comprehension`, `--points`
  file/stdin parsing).
- `./tools/validate-plugin.sh` must pass with the new `skills/digest/` directory.

## 9. Acceptance criteria (from #68, unchanged)

- [ ] A `digest` run conducts an interactive probe→teach→re-probe loop and
      terminates only when the load-bearing points are demonstrably understood
      (or the reader explicitly parks named gaps).
- [ ] Emits a git-tracked digest artifact + an `understanding` record in the
      shared frontmatter shape; both grounded in the `references.json`/PDF
      substrate.
- [ ] Updates the paper's `triage.yml` row (notes/disposition) on completion.
- [ ] `progress` can report understood-vs-unresolved from the record.
- [ ] Docs/SKILL state the governance (verified-not-attested; don't grade novel
      claims; proposes-not-adjudicates) and how it composes with `defend`,
      `literature`, and `progress`.
