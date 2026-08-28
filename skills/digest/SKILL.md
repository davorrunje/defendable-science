---
name: digest
description: Use when you want to read an external paper with verified comprehension — an interactive probe-teach-reprobe loop that builds and checks your understanding of a paper's problem, method, key result, assumptions, and limitations, then emits a grounded digest. Also offered as a deeper remediation path when defend's cited-work probe finds you can't explain what a citation actually says. Has a second, breadth mode — extraction — for survey-scale reading: it fills the concept matrix's cells from many papers, each cell carrying a source locator, and certifies something deliberately weaker than comprehension.
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

## Two modes, two claims

`digest` has a **depth** mode and an **extraction** mode. They are not
interchangeable, and the whole reason both exist is that they certify different
things:

| Mode | Certifies |
|---|---|
| `depth` (the probe → teach → re-probe loop below) | the reader understands this paper |
| `extract` (breadth reading for a survey) | the agent extracted these cells, each carrying a locator; the human verified a deterministic sample of them against the sources |

Extraction does **not** certify comprehension — not the agent's, and certainly
not the reader's. It certifies that cells were recorded with locators, and that
a human spot-checked a sample of them against the actual papers. Never state,
render, or roll it up as anything stronger.

The two modes write **different frontmatter keys** on the same artifact
(`status.understanding` vs `status.extraction`) precisely so nothing downstream
can read one as the other. The reasoning, with the rejected alternatives, is
ADR-0040 (`../../decisions/0040-digest-extraction-mode.md`).

### The tier ladder

Which tool to reach for, cheapest first. A survey does not need the bottom of
this ladder for every paper — it needs the right rung per paper.

| tier | activity | tool |
|---|---|---|
| screen | abstract + venue → in/out | `literature position` triage |
| extract | fill the matrix row | `digest` extraction mode |
| digest | verified comprehension | `digest` depth mode |
| reproduce | run it | experiment backend |

Depth mode costs an hour or two per paper; forty papers at that cost is a
semester. Extraction exists so a survey can fill its comparison matrix without
either paying that or pretending it did.

## When to use

- **Self-invoked.** You've picked a paper to read — off a `scout`-produced
  reading list, a citation you're about to add, or general background — and
  want your understanding of it built and checked, not just summarized at you.
- **Escalation from `defend --target cited-work`.** `defend`'s cited-work probe
  ("does ref [12] actually support this sentence?") surfaces a gap: you can't
  explain what the source says, or your citation misrepresents/overstates it.
  `defend` **offers** to hand off into a full `digest` session on that paper —
  deeper remediation than teaching the one sentence inline.
- **Extraction mode**, when you have a screened set of papers and a concept
  matrix waiting for rows — a survey, a related-work section, a positioning
  document. You want each paper's cells, located, not each paper understood.
  See *Extraction mode*, below.

Do **not** use `digest` to grade the paper's own claims, or to decide whether
it's novel/worth citing — that's `literature`'s `position` mode and the
human's call (see Guardrails).

## How it works — depth mode

The core is the same retrieval-practice loop as `defend`, run per load-bearing
point until it holds or you elect to stop and record the gap.

1. **Scope.** Resolve the paper against the `literature` registry
   (`references.json`) — `literature resolve` it if absent, then `literature
   fetch <citekey>` to acquire and record the PDF (cache → mirror → source
   chain, SHA-256). `literature verify <citekey>` re-checks the bytes offline
   on a later run. If `fetch` reports the paper in `manual[]` (the
   acquisition ladder found nothing), acquire it by hand and record it with
   `literature confirm <citekey> --file <path>`. This grounds the digest in a
   real registry entry + mirrored PDF, never a bare URL or an unmirrored
   link.
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
   row. On the **first digest** of a paper, create the digest artifact with
   a minimal seed frontmatter block (see Output artifact, below) before
   running `defend record`.

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
every point, not just the failed ones) to the accountability log (for
illustration: `docs/research/defend-log/`). The frontmatter stays small; the log is where
the evidence lives, independently checkable later without re-running the
session.

## Output artifact

The digest artifact (for illustration: `docs/research/literature/digests/<citekey>.md`) — one file per digested
source paper, named by citekey so it joins trivially with
`references.json`/`triage.yml`. Git-tracked, citeable.

- **Frontmatter**: a `status:` block carrying `understanding` +
  `last-updated`. The block must be seeded before the Record step runs
  (not already patched by `defend record`). Minimal seed:
  ```yaml
  ---
  status:
    understanding: {status: pending, unresolved: []}
    last-updated: YYYY-MM-DD
  ---
  ```
- **Body**: faithful summary; key equations/claims; assumptions; limitations;
  and, when applicable, an explicit "relation to my work" section.

**Triage update.** On completion, update the paper's `triage.yml` row —
`notes` and a `seeded` link back to the digest, `disposition` advanced if
warranted. This is a direct edit to the YAML (there is no CLI for
`triage.yml` today for depth mode; `literature`'s CLI only exposes the graph
primitives), consistent with current practice. Extraction mode is the one
exception: `digest extract record` writes `extracted` and `extraction-cells`
itself — and only those, never `disposition`.

## Extraction mode

Breadth reading, driven by the concept matrix `literature position --level
paper` already wrote. The matrix's own column headers are the question set:
read each paper against exactly those axes, then stop. No probing, no teaching,
no comprehension claim.

All four commands live under one CLI group (bootstrap first via
[`../../resources/ensure-tooling.md`](../../resources/ensure-tooling.md)):

```
defendable-science digest extract axes   [--paper ID] [--positioning PATH]
defendable-science digest extract record --cells FILE|-  [--paper ID] [--positioning PATH] [--log-dir PATH]
defendable-science digest extract sample (--citekey KEY ...| --all) [--size N] [--verdict verified|failed] [--log-dir PATH]
defendable-science digest extract render [--citekey KEY ...] [--paper ID] [--positioning PATH]
```

`--paper` and `--positioning` are inferred from the recorded layout and the cwd
when omitted (ADR-0039); pass them only when running from outside a paper
directory or against a document the layout does not own.

### 1. `axes` — get the question set, before reading anything

```
defendable-science digest extract axes
```

Prints `{"positioning": …, "axes": [...]}` — the matrix header minus its first
column. Run it **first**. It refuses (exit 1) rather than letting a batch be
read against a matrix that is not ready. The refusals, in full: **no
positioning document at that path**; no concept-matrix section; more than one
section carrying that heading; no table in the section; **more than one table
inside the section**; a missing `|---|` separator; ragged rows; unreplaced
`<attr N>` placeholders; an unnamed column; no axes beyond the row label; two
columns sharing a name. Every refusal names
the file and the repair. Fix the matrix with the human; do not work around it.

The `**This paper**` row is the author's own delta, never a paper to extract.

### 2. Read, then `record` — validation and writing are one action

Resolve each paper's PDF through the `literature` registry exactly as depth
mode's step 1 does (`fetch` / `confirm`), so the bytes you read are the
checksummed mirrored ones. A paper with no obtainable PDF is **skipped and
reported** — it gets no `status.extraction` block at all, because an artifact
saying "extracted: 0 cells" reads like a finding about the paper.

Cells go in as a JSON array (a file path, or `-` for stdin):

```json
[
  {"citekey": "sill1997monotonic", "axis": "guarantee type",
   "value": "architectural — monotone by construction", "locator": "§2, Eq. (3)"},

  {"citekey": "sill1997monotonic", "axis": "partial monotonicity",
   "value": "not-addressed",
   "justification": "scoped to fully-monotone inputs in §1; never revisited"}
]
```

```
defendable-science digest extract record --cells cells.json
```

There is **no way to write a cell without validating it** — the validator is
the only writer. The rules:

1. Every cell carries a `locator` whose *shape* matches the configured pattern
   set, **or** has `value: "not-addressed"` with a non-empty `justification`.
   Shape validation proves the locator is well-formed, not that the claim is
   where it says — that is `defend --target cited-work`'s job, which is the
   whole reason the locator is mandatory.
2. **Every axis in the header must be present for each paper.** Omission is not
   an option; an axis you cannot fill goes to `not-addressed`, where it is
   counted.
3. An axis that is not in the header is refused — it would silently widen the
   matrix.
4. **Rejection is per paper, not per batch.** A paper with one bad cell is
   rejected whole (no partial row, no artifact, no log entry) and the rest of
   the batch still lands.

Default locator shapes: `§3` / `§3.2.1`, `Section 3` / `Sec. 3`, `p. 7` /
`pp. 7-9`, `Eq. (4)` / `Equation 4`, `Table 2`, `Fig. 5`, `Alg. 1`, `Thm. 2` /
`Lemma 3` / `Def. 1`, and comma-joined combinations. **Extend** them under
`literature.extraction.locator_patterns` in `.defendable-science/config.yml` —
a set built around `§` and `Eq.` encodes one citation culture, and a survey of
trials or case law locates claims differently. Configured patterns are
**appended to the defaults, never replacing them**: there is no way to drop
`§`/`Eq.`/`Thm.` from the accepted set. The cost of that is only extra accepted
shapes, never a rejected locator the author meant.

**`not-addressed` and the anti-gaming count.** "The paper does not address this
axis" is a legitimate, common cell value, and demanding a locator for it is
incoherent — there is no section to point at. So it takes a justification
instead, checked only for presence: no automated check can judge whether an
absence is real. What keeps it honest is that the report **counts them, per
paper and in aggregate** (`recorded[].not_addressed` and the top-level
`not_addressed`). A paper with 8/8 not-addressed, or a run where 60% of all
cells came back empty, is visible at a glance. Surface those counts to the
human; do not bury them.

**Reading the report.** Exit 0 only when everything landed. Exit 1 for anything
else, and the report has **three separate buckets that a reader must not
conflate**:

- `rejected[]` — cells that failed validation. Nothing was written for that
  paper. Fix the cells and re-run.
- `errors[]` — papers whose artifact write failed part-way through the batch.
  Disjoint from `recorded[]`: `recorded` names what landed, `errors` names what
  did not. The batch is not aborted, so both lists can be non-empty in one run.
- `triage_not_updated[]` — the cells landed, but the paper's `triage.yml` row
  did not. Each entry carries a `kind`:
  - `"refused"` — the sidecar has YAML comments, and the triage writer will not
    destroy PRISMA rationales it cannot round-trip. **The human edits the
    sidecar by hand**; the message names the fields.
  - `"failed"` — the write itself did not happen (an OS-level failure). Repair
    and re-run.

Report all three. "3 cells rejected" sends the reader hunting; name the paper
and the axis.

**What `record` writes to `triage.yml`**: exactly two factual fields per
recorded paper — `extracted: <date>` and `extraction-cells: <int>`. It **never
writes `disposition`**. The disposition state machine is the human's decision;
a machine advancing it is precisely the agency violation this plugin exists to
prevent.

### 3. `sample` — the human checks; the agent never checks its own work

In depth mode the human reads and the agent probes them. In extraction the
agent reads. So if the agent also checked the sample, extraction would certify
**nothing** — it would be self-attestation, which this skill's guardrail
forbids and the agency principle rules out. The human checks the sample. That
is the only thing standing behind extraction's claim.

Two invocations, deliberately.

```
defendable-science digest extract sample --all              # draw
defendable-science digest extract sample --all --verdict verified   # record the answer
```

The batch is either explicit (`--citekey KEY`, repeatable) or discovered
(`--all` — every digest artifact carrying a `status.extraction` block). Exactly
one of the two is required.

**The draw writes nothing.** It reports, for each drawn paper, every cell's
axis, value and locator — which is exactly what the human is shown. Ask them
one question, per cell: *does the source at that locator actually say this?*
Not "do you understand this paper": extraction never claimed that, and asking
it would smuggle depth mode's guarantee back in through the conversation.

**Selection is deterministic**, seeded from the sorted citekey set. The same
batch draws the same papers, in every process, forever — so the agent cannot
steer the draw toward papers it found easy, and nobody can re-roll until an
easy sample comes up. Size defaults to `max(3, 10%)` of the batch and is
adjustable with `--size`. That default is a **convention, not a statistical
guarantee**; say so if anyone treats it as one.

Because both the draw and the batch are deterministic, the verdict call
re-draws: **give it the same members and the same `--size`**. A different
membership set or size is a different batch and marks a different set of papers
as checked.

Reading the sample report: `size` counts the papers *drawn*, `sampled[]` lists
the ones whose cells could actually be shown, and `not_shown[]` names the
difference. Do not diff two lists to find it, and do not report a draw as a
check.

**A failed sample is evidence about the batch, not about one paper.** A process
that produced one confidently-wrong cell in a sample of three probably produced
more in the other thirty-seven. So `--verdict failed` writes `batch-check:
failed` on **every** member, sampled or not, and touches no cell. Do not
silently repair the caught cell: that converts a signal about the population
into a tidy-looking local fix. Nothing downstream may treat the batch as
verified until it is re-extracted or checked in full.

Two refusals, both from the same asymmetry — `failed` is a **finding** and must
land whatever else went wrong, while `verified` is a **claim** and may only be
written for what was actually established:

- **`--verdict verified` is refused outright** (nothing written, exit 1) if any
  drawn paper's cells could not be read. The human cannot have verified what
  they were never shown. Repair and re-run, or record `failed`.
- **`--all` aborts before drawing** if any artifact under the digests directory
  cannot be read. Membership would be unknowable, and since the draw is a
  function of membership, dropping an unreadable member *re-rolls the sample* —
  sample-shopping dressed as a routine file problem. `--citekey` needs no such
  guard and deliberately behaves differently: membership is explicit there, so
  an unreadable member is reported against its own citekey and the run
  continues.

### 4. `render` — project the cells into the matrix

```
defendable-science digest extract render
```

A **merge, not a rewrite**, into the concept matrix. The author's taxonomy
prose, PRISMA log, per-branch delta and section comments survive by
construction — only the table's own lines are re-emitted. Rows are keyed by
citekey in the matrix's first column, so re-rendering is idempotent.

- **Render never deletes a row.** Insert or update only. A row this run has no
  cells for is left exactly as it is; a paper leaving the survey is removed by
  hand. Automatic deletion is the one operation here with no safe failure mode.
- **`**This paper**` is never touched** — it is the author's own delta. Asking
  to write it is refused, not silently skipped.
- `not-addressed` renders as `*not addressed*`, never as an empty cell: an
  empty cell reads as *not yet extracted*, which is a different claim.

**Three costs to state plainly before the first render.** They are real, and
the last two are irreversible-by-hand tidying:

1. **A hand-edited row label is not overwritten — it is orphaned.** Row lookup
   is exact label equality, so an edited label stops matching and the next
   render adds a **second** row for that paper. Nothing you wrote is lost, but
   the matrix now has two rows about one paper. The remedy is to **restore the
   label**, not to re-edit it. **Nothing detects this for you**: the two rows
   carry different labels, so no later run refuses, warns, or reconciles them.
   The duplicate simply stays until a human notices it.
2. **The matrix is re-emitted canonically**, so hand-aligned column padding is
   collapsed.
3. **GFM alignment specifiers (`|:---:|`) are dropped** from the separator row.

Refusals leave the file **byte-identical** rather than writing at a guess.
`render` reads the matrix the same way `axes` does, so it performs **every
refusal in the `axes` list above** — including a missing document, unreplaced
`<attr N>` placeholders, a duplicate column name, and both ambiguous-matrix
cases — plus three of its own:

- **a recorded cell naming an axis the matrix no longer has.** This is the one
  you will actually hit: rename or delete a column between `record` and
  `render` and the whole merge refuses, because writing the cell would need a
  column that does not exist and dropping it would lose a recorded cell
  silently. The remedy is the human's call — restore the column name, or
  re-extract against the new axes — so surface it rather than guessing;
- two rows in the file already carrying the **same** citekey — which row is
  *the* row cannot be guessed, so merge or delete the duplicates by hand first;
- asking to render the `**This paper**` row, which is the author's own delta.

A paper whose artifact cannot be read is reported in `errors[]` and its row
left alone — the rest of the batch still lands, because skipping it changes
nothing on disk while refusing the whole merge would strand every other
paper's cells.

### The extraction artifact

Same file depth mode uses, one per paper (for illustration: `docs/research/literature/digests/<citekey>.md`),
with a **second, separate** status key:

```yaml
---
status:
  understanding: {status: pending, unresolved: []}    # depth mode; untouched by extract
  extraction:
    cells: 8
    locators: ok
    in-sample: false
    batch-check: pending
  last-updated: 2026-08-28
---
```

Do not put YAML comments *inside* the `extraction` block — an annotated child
of a block mapping is refused by the frontmatter writer rather than silently
destroyed.

- `cells` — how many cells were recorded for this paper.
- `locators` — `ok`; a cell without one cannot be recorded.
- `in-sample` — **a human checked this paper's cells.** Not "was drawn": a draw
  never followed by a verdict has established nothing, so only a `--verdict`
  run sets it true. (It is monotone within a set of cells — nothing sets it
  back to false, so it accumulates across re-samples. That is safe because
  `record` rewrites the whole block with `in-sample: false` on every
  re-extraction, so the flag can never outlive the cells it certified.)
- `batch-check` — `pending` | `verified` | `failed`, the verdict on the *run*
  this paper belongs to. Separate from `in-sample` because they answer
  different questions: one field would have to read `failed` for a paper nobody
  checked, which parses as a finding about that paper.

The body carries the cells themselves in a delimited, generated block — that is
the durable record. **The matrix row is a projection of it**, never authored
independently, which is what lets `defend --target cited-work` check a cell
later without parsing a table out of the author's prose.

The file is the paper's reading record *at whatever depth it has been read*. A
survey extracts forty papers; three later get digested properly and grow an
`understanding` block and a written body. Nothing is migrated, and the two
claims coexist visibly because they are genuinely different claims.

## Composition

- **`literature`** is the substrate: `digest` resolves/grounds the paper
  against `references.json` and the mirrored PDF, and writes back to
  `triage.yml` on completion.
- **`defend`** shares the engine and the record mechanism (ADR-0033); its
  `cited-work` target escalates into `digest` on a comprehension gap (see
  When to use).
- **`progress`** surfaces digested-vs-unresolved counts from
  digest artifacts (for illustration: `docs/research/literature/digests/*.md`) frontmatter as an independent
  "literature reading" view (`../progress/SKILL.md`), alongside — not folded
  into — the hypothesis/paper/thesis roll-ups. It reports extraction as a
  **second, separate row** (`extracted N / digested M`) — never summed with the
  digested count, because the two mean different things.
- **`literature position --level paper`** owns the concept matrix extraction
  fills. Extraction reads its header as the question set and renders rows back
  into it; it never invents an axis.

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
- **Verified, never self-attested — depth mode.** `understanding.status: ok`
  only when the reader has demonstrated each load-bearing point against the
  probe — no "I've got it" shortcut (anti-Goodhart, same as `defend`). This
  guardrail is about *comprehension*, and it covers depth mode only, because
  depth mode is the only mode that claims comprehension.
- **Extraction claims less, and must say so in its own words.** Extraction
  certifies that cells were recorded with locators and that a human checked a
  deterministic sample of them against the sources. It does not certify that
  the agent understood any paper, that the unsampled cells are right, or that a
  locator points where it says. Never describe an extracted paper as read,
  digested, or understood; never write `status.understanding` from extraction;
  never let the two counts be summed.
- **The human checks the sample, never the agent.** The agent did the
  extracting, so an agent-checked sample certifies nothing. If the human is not
  available to check, the batch stays `batch-check: pending` — which is honest
  — rather than being marked verified.
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
