# Design — `digest` extraction mode (breadth reading for a survey)

**Date:** 2026-08-28
**Author:** Davor Runje
**Status:** Approved design; not yet implemented.
**Scope:** [#100](https://github.com/davorrunje/defendable-science/issues/100) — Gap 2 of
[#97](https://github.com/davorrunje/defendable-science/issues/97), restated against the
literature registry layer that Gap 1 built.

> Sits alongside the depth-first loop in [`skills/digest/SKILL.md`](../../../skills/digest/SKILL.md).
> Builds on the registry layer specified in
> [`2026-08-27-literature-asset-acquisition-design.md`](2026-08-27-literature-asset-acquisition-design.md)
> and on the host-preserving markdown-table reader that landed with #94/#95.
> Governed by the meta-spec's **agency** principle (§2.1) and the repo's failure-honesty rule.

## 1. Problem

`digest` is depth-first by design: probe → detect gap → teach → re-probe, per load-bearing
point, per paper. It is the right tool for a paper whose claims you will *assert*, and it costs
on the order of an hour or two each.

A survey has a different need. The monotonicity run behind #97 resolved 73 works and proposed 40
for inclusion. At depth-mode cost that is a semester. But the survey does not need comprehension
of 40 papers — it needs, for each one, the cells of the concept-centric matrix that
`literature position --level paper` has already defined. Eight specific questions, then stop.

So the plugin's reading skill is unusable for the exact task its sibling skill sets up, and
`position`'s own output already specifies the question set a breadth mode would ask.

**What changed since #97 filed this.** Gap 1 built the registry layer — `load_registry`,
`patch_asset`, `load_triage`, `patch_triage`, `Asset.files` — so extraction now has real
interfaces to resolve PDFs and write back through. And #94/#95 replaced the markdown-table
machinery in `exploration/backlog.py` with a host-preserving, header-driven reader, which is
what makes writing into an author's `positioning.md` safe rather than reckless.

## 2. Goals and non-goals

**Goals.**

1. An extraction mode driven by `positioning.md`'s own matrix columns.
2. Mandatory per-cell locators, **enforced** — extraction refuses to record a cell without one.
3. Batch operation over a triage-filtered set.
4. Writeback through the registry APIs, with an explicit human-surfaced path for the
   `patch_triage` comment refusal.
5. A sampled comprehension check whose contract is explicitly weaker than depth mode's, and
   which cannot be mistaken for it.
6. The tier ladder (screen → extract → digest → reproduce) documented, so a survey author knows
   which tool to reach for.

**Non-goals.**

- PDF parsing in the CLI. The agent reads PDFs natively; the CLI never needs a parser, and
  adding one would breach the light-dependency posture (same reasoning as the acquisition
  spec's §2).
- Verifying a locator's *correctness*. Shape validation proves a locator is well-formed, not
  that the claim is where it says. What catches that is `defend --target cited-work`, which is
  why the locator is mandatory in the first place.
- Automatic deletion of matrix rows. See §6.
- Gap 3 (survey-shaped templates) — tracked separately as #101.

## 3. Decisions

Five, settled during brainstorming, each recorded here with the reasoning because each has a
plausible alternative.

### 3.1 Extraction is a second mode of `digest`, not a third `literature` mode

`literature` is deliberately a graph-and-metadata capability: its entire surface is OpenAlex/S2
plus the registry, and it never opens a PDF. Extraction is *reading a paper and producing claims
about it*, which is `digest`'s domain, and the sampled check reuses `digest`'s probe mechanic.
#97's own framing agrees ("filed as a `digest` mode because the reading loop is the reusable
part").

**Consequence to handle:** `digest` has no CLI group of its own today — it borrows
`defend record`. Extraction's commands therefore land as a new `digest` group, keeping skill and
namespace aligned:

```
defendable-science digest extract axes    [--positioning PATH]
defendable-science digest extract record  --cells FILE|-   [--positioning PATH]
defendable-science digest extract sample  (--citekey KEY ... | --all)  [--size N]
                                          [--verdict verified|failed]
defendable-science digest extract render  [--positioning PATH]
```

`axes` prints the question set (§6.1) so the agent knows what to extract before reading
anything. `record` is the validating writer of §3.3. `sample` draws the deterministic sample and
drives the check. `render` performs the `positioning.md` merge of §9.

*Amended during implementation.* `sample` takes its batch as repeated `--citekey` options or
`--all` (every artifact under `digests/` carrying a `status.extraction` block), not the
`--batch FILE|-` this section first sketched. A file of citekeys is a caller-supplied
membership set, and since the draw is a deterministic function of membership, handing the
caller that file hands them the sample — the anti-gaming property of §8 defeated by its own
input. Recording the human's verdict is a second invocation of the same command with
`--verdict`, on the same membership, rather than an interactive prompt: the questioning is the
skill's job, and the CLI stays scriptable and testable.

*Rejected:* a third `literature` mode (would make `literature` open PDFs for the first time and
sits badly against its "propose and surface, never adjudicate" guardrail); a new fourth skill
(cleanest contract separation, but adds a reading-adjacent surface to a plugin whose value
depends on a researcher holding the whole shape in their head).

### 3.2 A separate frontmatter key and a separate `progress` row

`progress status literature` scans `docs/research/literature/digests/*.md` and reports each
paper as `{digested & understood / gaps unresolved}` from its `understanding` block
(`skills/progress/SKILL.md:140-143`). So a paper that had eight cells extracted and was never
read would be counted as "digested & understood" — the guarantee-inflation #97 warns against,
and a concrete harm rather than a theoretical one.

Extraction writes `status.extraction`, **never** `status.understanding`, and `progress` gains a
second, clearly-labelled row so a survey author sees "extracted 40 / digested 3" rather than one
blended number.

*Rejected:* one key with a `mode:` discriminator — the two contracts would share a field name,
and anything reading it without knowing about `mode` silently inflates the weaker into the
stronger.

### 3.3 Validation and writing are one command

A SKILL.md sentence saying "you must include a locator" enforces nothing on the agent following
it, and #100 asks for enforcement, not documentation. So the validating command is also the
*only* writer: there is no code path that records an unvalidated cell.

This is the same move that made `_bind` the single writer of an asset spine in Gap 1 — fusing
the check to the write so the two cannot drift apart.

*Rejected:* extending `defend record` with an extraction target (maximum reuse, but that
command's job is certifying understanding, and it would then also write a key that deliberately
means something weaker); a separate validator the skill is told to run (the skill could write
without validating, which returns the constraint to documented-as-expected).

### 3.4 Locators are shape-validated against a configurable pattern set

A non-empty-string check is satisfied by "see paper", and an agent filling 320 cells will
discover that immediately. Shape validation catches the vague-filler failure mode cheaply.

The pattern set **ships as a default and is configurable**, for the same reason
`venue_resolvers` is: a set built around `§`, `Eq.`, `Thm.` encodes a maths-and-CS citation
culture, and a survey of clinical trials or case law locates claims differently. A fixed set
would be a domain assumption in a plugin that forbids them.

### 3.5 The human checks the sample; selection is deterministic

In depth mode the human reads and the agent probes them. In extraction the agent reads — that is
the premise. So if the agent also checks the sample, extraction certifies nothing: it is
self-attestation, which `digest`'s "verified, never self-attested" guardrail forbids and the
agency principle rules out.

Selection is seeded from the sorted citekey set, so the agent cannot steer it toward papers it
found easy, **and re-running the same batch re-checks the same papers** — a freshly-random
sample per run would let anyone re-roll until an easy draw came up, hollowing the check out.

## 4. The contract, stated exactly

Two modes, two claims, and the wording matters because the whole point is that they are not
interchangeable.

| Mode | Certifies |
|---|---|
| `depth` (today) | the reader understands this paper |
| `extract` (new) | the agent extracted these cells, each carrying a locator; the human verified a deterministic sample of them against the sources |

`skills/digest/SKILL.md` states both, and **carves the "verified, never self-attested"
guardrail explicitly** so it reads as covering depth mode only. Extraction says something
weaker and must say it in its own words rather than by omission.

### 4.1 The tier ladder

Documented in the skill so the depth/breadth choice is guided rather than invented:

| tier | activity | tool |
|---|---|---|
| screen | abstract + venue → in/out | `literature position` triage |
| extract | fill the matrix row | `digest` extraction mode |
| digest | verified comprehension | `digest` depth mode |
| reproduce | run it | experiment backend |

## 5. Artifacts

**One artifact per paper, two status keys.** Extraction writes to the same
`docs/research/literature/digests/<citekey>.md` depth mode uses:

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

*Amended 2026-08-28, during implementation.* This block originally carried inline `#`
comments on `in-sample` and `batch-check` explaining each. That made the documented shape
**unwritable**: an annotated child inside a block mapping is refused by the frontmatter writer,
which will not silently destroy a comment it cannot round-trip. A reader copying this example
verbatim would have hit that refusal. The explanations now live in prose below — `in-sample`
records whether a human actually checked *this* paper's cells, and `batch-check` is the verdict
on the whole extraction run, one of `pending` | `verified` | `failed`.

*Amended again, during implementation.* `in-sample` first read "was drawn into the sample", the
nomination meaning. It is set at **verdict** time, not draw time, so it means *a human checked
these cells* — a draw never followed by a verdict has established nothing, and a field that
says otherwise overstates the record. It is also monotone within a set of cells: nothing sets it
back to `false`, so it accumulates across re-samples of the same batch. That is safe because
`record` rewrites the whole block with `in-sample: false` on every re-extraction, so the flag
can never outlive the cells it certified.

Two fields rather than one, because they answer different questions and conflating them
produces nonsense. `in-sample` is a fact about this paper. `batch-check` is the verdict on the
extraction run it belongs to — and since a failed sample is evidence about the *population*
(§8), an unsampled paper in a failed batch must also read `failed`. A single `sampled:` field
would have to say `failed` for a paper that was never checked, which reads as a finding about
that paper and is exactly the kind of misleading status this design exists to avoid.

The file becomes *the paper's reading record at whatever depth it has been read*. A survey
extracts 40 papers, so 40 artifacts exist carrying cells and no prose body; three later get
digested properly and grow an `understanding` block and a written summary. Nothing is
duplicated, nothing is migrated, and the two claims coexist visibly because they are genuinely
different claims about the same paper.

**The cells are the durable record; the matrix row is a projection.** Each cell — axis, value,
locator — lives in the per-paper artifact as structured content. `positioning.md`'s row is
rendered from those, never authored independently.

That does real work beyond tidiness: it gives `defend --target cited-work` something exact to
check later without parsing a markdown table out of the author's prose, and it means a change to
how the matrix is rendered never risks the underlying evidence.

## 6. The extraction loop

### 6.1 Question set

The axes are `positioning.md`'s matrix header minus the first column. Two refusals:

- **Unreplaced placeholders.** The template ships `| Method | <attr 1> | <attr 2> | <attr 3> |`.
  If the header still carries `<attr N>`, the author has not chosen their comparison axes, and
  extracting 40 papers against `<attr 1>` is worse than useless. Stop and say so.
- **No table at all.** Same.

The `**This paper**` row is a self-reference, never a paper to extract.

### 6.2 Table machinery is promoted

#94/#95 left `exploration/backlog.py` with a genuinely generic core — `_Document(preamble,
header, rows, postamble)`, `_parse_document`, `_render_table`, `_splice`, `_escape`,
`_split_cells`, `_is_separator` — all header-driven and level-agnostic. `Backlog` is
`columns_for(level)` sitting on top.

That core moves to **`core/mdtable.py`** and `backlog.py` re-imports, exactly as `core/fixity.py`
and `core/mirror.py` were promoted in Gap 1. One markdown-table implementation in the repo, not
two — which is what stops #94's class of bug being reintroduced somewhere new.

### 6.3 PDF resolution

Each paper resolves via `Asset.files[0]` to `blob_path(cache_dir, sha256)`, and the bytes are
**verified against the recorded checksum before the agent reads them**. Nearly free, and it
closes an obvious hole: extracting from a corrupt or truncated PDF produces confidently-wrong
claims carrying valid-looking locators, which is precisely what the locator requirement exists
to prevent.

### 6.4 A paper with no asset

Skipped, reported with the reason and its `landing_urls`, mirroring `fetch --all`'s `manual[]`
bucket. The real run had roughly ten of fifty paywalled, so blocking the batch on them would
make extraction unusable.

**A skipped paper gets no `status.extraction` block at all.** An artifact that says nothing is
honest; one that says "extracted: 0 cells" reads like a finding about the paper.

### 6.5 `not-addressed`

"The paper does not address this axis" is a legitimate and common cell value, and demanding a
locator for it is incoherent — there is no section to point at. But making it locator-exempt
hands the agent an obvious way out: 8 axes × 40 papers is 320 chances to write "not addressed"
and skip the hard part.

So `not-addressed` is a distinguished value requiring a **justification** in place of a locator
— checked only for presence and non-emptiness, since no automated check can judge whether an
absence is real — and the report **counts them per paper and in aggregate**. The count is the anti-gaming
signal: a paper with 8/8 not-addressed is visible at a glance, and so is a run where 60% of all
cells came back empty. That is cheaper and more honest than trying to make the checker
adjudicate whether an absence is real, which it cannot do without reading the paper itself.

## 7. Enforcement

### 7.1 The cells file

A JSON array, path or `-` for stdin, mirroring `defend record --points`:

```json
[
  {"citekey": "sill1997monotonic", "axis": "guarantee type",
   "value": "architectural — monotone by construction", "locator": "§2, Eq. (3)"},

  {"citekey": "sill1997monotonic", "axis": "partial monotonicity",
   "value": "not-addressed",
   "justification": "scoped to fully-monotone inputs in §1; never revisited"}
]
```

A `Cell` dataclass rather than reusing `PointRecord` — the fields genuinely differ (axis/value
against point/source_quote/reader_answer) — but `defend/record.py`'s accountability-log
machinery is reused as a library, so extraction lands in the same log depth mode writes to.

### 7.2 Validation rules

1. Every axis carries a locator matching the pattern set, **or** is `not-addressed` with a
   justification.
2. **Every axis in the matrix header is present for each paper.** Without this, `not-addressed`
   is unnecessary — an agent finding an axis hard just omits the cell, and a short row looks
   like a clean row. Completeness forces every axis to be *accounted for* and pushes the dodge
   into `not-addressed`, which is counted and visible.
3. No invented axes; an axis absent from the header is refused, since it would silently widen
   the matrix.
4. **Rejection is per paper, not per batch.** A paper with a bad cell is rejected whole, no
   partial row is written, and the run continues. Same posture as `fetch_all`: one bad entry
   does not abort a 40-paper sweep, and nothing half-lands.

### 7.3 Locator pattern set

Default: `§3` / `§3.2` / `§3.2.1`, `Section 3` / `Sec. 3`, `p. 7` / `pp. 7-9` / `page 7`,
`Eq. (4)` / `Equation 4`, `Table 2`, `Fig. 5` / `Figure 5`, `Alg. 1`, `Thm. 2` / `Theorem 2` /
`Lemma 3` / `Def. 1`, and comma-joined combinations (`§3, Eq. (4)`).

Extended via `literature.extraction.locator_patterns` in `.defendable-science/config.yml`.

*Amended during implementation — "or replaced" was never built, and should not be.*
`compile_locator_patterns` appends the configured patterns to the defaults; there is
deliberately no way to drop one. Widening only ever admits a locator shape that would
otherwise have been rejected, so it cannot cause a false negative on a locator the author
meant; allowing removal would let a misconfiguration reject locators the author wrote, which
is the failure with no signal. A pattern set that cannot be combined raises `ExtractionError`
rather than silently narrowing.

### 7.4 Refusal

Exit `0` all recorded, `1` anything rejected or incomplete, `2` left to Click (see #106/#119 —
reusing 2 for a domain outcome collides with usage errors and makes both unreadable).

Refusals name the offending cells, not just a count. "3 cells rejected" sends the reader
hunting; `sill1997monotonic / partial monotonicity: locator "see paper" matches no known form`
does not.

### 7.5 The `patch_triage` comment refusal

If the sidecar carries YAML comments, the triage writeback refuses (`registry.py`'s
`_has_comments`), because `pyyaml` cannot round-trip them and the `rationale` fields *are* the
PRISMA audit trail.

That must not discard the extraction. Cells are already durably in the per-paper artifact, so
the run reports `triage not updated for ⟨citekeys⟩; set ⟨fields⟩ by hand`, exits 1 because
something genuinely did not complete, and leaves the human's annotations intact. This honours
`patch_triage`'s docstring rather than working around it.

## 8. The sampled check

**Selection.** Sort the batch's citekeys, hash that list to seed the PRNG, draw `k`. Size is a
parameter defaulting to `max(3, 10%)`.

**The check.** For each cell in a sampled paper, the human is shown the axis, the recorded
value, and the locator, and asked one thing: *does the source at that locator actually say
this?* Not "do you understand this paper" — extraction never claimed that, and asking it would
smuggle depth mode's guarantee back in through the UX.

**A failed sample is evidence about the batch, not one paper.** If the human finds a cell that
misrepresents its source, the honest inference is not "fix that cell" — a process that produced
one confidently-wrong cell in a sample of three probably produced more in the other
thirty-seven. Every artifact in the run — sampled or not — gets `batch-check: failed`, the report says so in
those terms, and nothing downstream may treat the batch as verified until it is re-extracted or
fully checked.

Silently repairing the one caught cell would be the worst outcome available: it converts a
signal about the population into a tidy-looking local fix.

Per-cell check records append to the same accountability log depth mode writes to, so the
evidence is independently reviewable later without re-running the session.

*Amended during implementation — two refusals this section did not anticipate.* Both come from
the same asymmetry: `failed` is a **finding** and must land whatever else went wrong, but
`verified` is a **claim** and may only be written for what was actually established.

- **A `verified` verdict is refused when the drawn sample's cells could not all be read.** The
  run exits 1 and writes nothing. Otherwise the durable record reads `batch-check: verified`
  with no paper marked checked — a self-contradictory state whose only honest signal is a
  transient exit code that no later reader ever sees.
- **`--all` aborts before drawing or writing if membership cannot be fully determined.** An
  unreadable artifact would otherwise be dropped from the population silently, and since the
  draw is a deterministic function of membership, *making one file unreadable re-rolls the
  sample* — sample-shopping through a route that looks like a routine file problem. A verdict
  is a statement about a population, so a run that cannot determine the population has nothing
  to say about it. The `--citekey` path needs no such guard: membership is explicit there, and
  a missing member is reported against its own citekey.

## 9. Writeback into `positioning.md`

A merge, not a rewrite, via `core/mdtable.py`. The author's taxonomy prose, PRISMA log,
per-branch delta and section comments survive by construction.

- **Rows are keyed by citekey** in the first column, so re-rendering is idempotent. Cost to
  state in the skill: a hand-edited row label is overwritten on the next render. That is the
  price of the row being a projection.

  *Amended during implementation — this is not what happens, and the skill must say the true
  thing.* Row lookup is exact label equality, so a hand-edited label does not get overwritten;
  it stops matching, and the next render adds a **second** row for the same paper. Safer than
  the documented behaviour, since nothing the author wrote is lost, but noisier, and the remedy
  is different: restore the label rather than re-edit it. Two further costs the section did not
  name — the matrix is re-emitted canonically, so an author's column padding is collapsed and
  GFM alignment specifiers (`|:---:|`) are dropped.
- **`**This paper**` is never touched** — it is the author's own delta.
- **Render never deletes a row.** Insert or update only; if a paper leaves the survey, the
  author removes its row by hand. Automatic deletion is the one operation here with no safe
  failure mode — a bug that drops rows loses the author's work silently, and #94 is a live
  reminder of how that goes.

## 10. Error handling

Consistent with the rest of the capability: `RegistryError` and the `patch_triage` refusal
surface with the citekey and the fields that needed setting; a corrupt or missing PDF is a skip
with a reason, never a silent empty row; no tracebacks at the CLI boundary.

## 11. Testing

100% statement + branch coverage, hermetic. The weight goes on **negative** assertions: this
project has been bitten four times by defects that passed a 100%-coverage suite because every
test asserted what *should* happen.

- A cell with no locator, or with `"see paper"`, cannot be recorded.
- An omitted axis cannot produce a written row (the anti-omission guard, §7.2 rule 2).
- An invented axis is refused.
- Re-running the same batch selects the **same** sample — no sample-shopping.
- Render preserves preamble, postamble, `**This paper**`, and every row it did not write; it
  never deletes.
- A paper with no asset gets **no** `status.extraction` block.
- Extraction **never** writes `status.understanding` — the guarantee-inflation guard, tested
  directly.
- A failed sample sets `batch-check: failed` on **every** artifact in the run, including
  unsampled ones, and does not quietly repair the caught cell.
- The `patch_triage` comment refusal leaves the sidecar byte-identical and the cells recorded.

Fixtures: a synthetic `positioning.md` with author prose around a three-axis matrix, and one
with unreplaced `<attr N>` placeholders to pin the refusal.

## 12. Implementation shape

Larger than it looks — a CLI group, a promoted module, a new artifact contract, a `progress`
change, and a human-in-the-loop step. Comparable to the acquisition work, which ran 17 tasks.
It splits into four independently reviewable pieces:

1. **Promote the table core** to `core/mdtable.py`; `backlog.py` re-imports. Pure refactor —
   the review criterion is that `backlog` behaviour is unchanged.
2. **Question set + cells model + validation** — matrix header parsing with its two refusals,
   the `Cell` dataclass, the locator pattern set, the validation rules, as a pure library with
   no writer. This does not weaken §3.3: the fusion of validation to writing is a property of
   the CLI surface built in piece 3, which has no path to a write that bypasses this library.
   Separating them here is what lets the rules be tested exhaustively without touching a file.
3. **The `digest extract` CLI group** — record (validate + write, inseparably), the artifact
   contract, the triage refusal path.
4. **Sampling, render, and docs** — deterministic selection, the check loop, the
   `positioning.md` merge, `skills/digest/SKILL.md`'s two contracts and the tier ladder, the
   `progress` second row.

## 13. Follow-ups to file

1. `defend --target cited-work` consuming extraction cells directly — the locators exist
   precisely so it can, and wiring it is what closes the loop from extraction to verification.
   **Filed as [#141](https://github.com/davorrunje/defendable-science/issues/141).**
2. Rendering a matrix row for a paper whose cells came from depth mode rather than extraction —
   a depth digest also produces locatable claims, and today they cannot feed the matrix.
   **Filed as [#142](https://github.com/davorrunje/defendable-science/issues/142).**

*Added during implementation — four defects the reviews surfaced, none of which this section
anticipated:* [#143](https://github.com/davorrunje/defendable-science/issues/143) (`patch_triage`
and YAML anchors), [#144](https://github.com/davorrunje/defendable-science/issues/144) (orphan
`.tmp` on a failed atomic replace), [#145](https://github.com/davorrunje/defendable-science/issues/145)
(fence-handling gaps in `core/mdtable.py` and the extraction heading probe), and
[#146](https://github.com/davorrunje/defendable-science/issues/146) (the extraction log entry
named from the artifact stem rather than the citekey).

## 14. Open questions

None blocking. One judgement recorded for the implementer: the sample size default
(`max(3, 10%)`) is a guess, not a derived figure. It should be a parameter from day one so a
real survey can calibrate it, and the skill should say plainly that it is a convention rather
than a statistical guarantee.
