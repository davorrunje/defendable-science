# ADR-0040: `digest` extraction mode — a second, weaker claim, kept structurally separate from comprehension

- Status: accepted · Date: 2026-08-28 · Deciders: Davor Runje

## Context

`digest` is depth-first by construction: probe → detect gap → teach → re-probe,
per load-bearing point, per paper. It is the right instrument for a paper whose
claims the author will *assert*, and it costs on the order of an hour or two
each.

A survey has a different need, and #97 (Gap 2, refiled as #100) named it from a
real run: 73 works resolved, 40 proposed for inclusion. At depth-mode cost that
is a semester. But the survey does not need comprehension of 40 papers — it
needs, for each one, the cells of the concept-centric matrix that `literature
position --level paper` has *already defined*. Eight specific questions, then
stop.

So the plugin's only reading skill was unusable for the exact task its sibling
skill sets up, while `position`'s own output already specified the question set
a breadth mode would ask.

Two things made this tractable now rather than earlier. Gap 1 (ADR-0037) built
the registry layer — `load_registry`, `patch_asset`, `load_triage`,
`patch_triage`, `Asset.files` — so extraction has real interfaces to resolve
PDFs and write back through. And #94/#95 replaced the markdown-table machinery
with a host-preserving, header-driven reader, which is what makes writing into
an author's hand-written `positioning.md` safe rather than reckless.

The hazard the whole design is organized against is **guarantee inflation**.
Extraction's honest claim is strictly weaker than depth mode's, and every place
the two can blur — a shared field name, a summed count, a UX question, a
"helpful" repair — is a place the weaker claim silently becomes the stronger
one. #97 filed that as the harm, not as a theoretical risk.

## Decision drivers

- **Failure honesty** (repo-wide). "The agent extracted these cells" and "the
  reader understands this paper" are different claims; a design in which the
  first can be read as the second is dishonest by construction, not merely
  imprecise.
- **Agency** (meta-spec §2.1). Every material decision stays the human's. A
  machine may record facts about a run; it may not advance a human's decision
  state machine, and it may not certify its own work.
- **Anti-Goodhart.** An agent asked for 320 cells will find the cheapest legal
  way to produce 320 cells. Every affordance has to be priced accordingly.
- **Enforcement over documentation.** #100 asks for enforced locators. A
  SKILL.md sentence saying "you must include a locator" enforces nothing on the
  agent following it.
- **Domain-neutrality.** A locator pattern set built around `§`, `Eq.`, `Thm.`
  encodes a maths-and-CS citation culture; a survey of clinical trials or case
  law locates claims differently.
- **Never lose an author's work.** `positioning.md` is hand-written prose with a
  table in it. #94 is a live reminder of how a table writer loses work quietly.

## Considered options

Five axes, each with a genuinely plausible alternative. Chosen options marked;
each rejection is argued in *Rejected alternatives* below.

**Where extraction lives.**

1. A third `literature` mode.
2. A new, fourth skill.
3. **A second mode of the existing `digest` skill.** *(chosen)*

**How the weaker claim is represented.**

1. One `status.understanding` key with a `mode:` discriminator.
2. A separate `status.extraction` key with a single `sampled:` field.
3. **A separate `status.extraction` key with `in-sample` and `batch-check` as
   two fields, plus a second, never-summed `progress` row.** *(chosen)*

**Who checks the sample.**

1. The agent re-reads its own extraction and checks it.
2. Nobody — record the cells and rely on the mandatory locator alone.
3. **The human, asked per cell whether the source at that locator says this.**
   *(chosen)*

**How the sample is drawn, and how the verdict is given.**

1. A fresh random draw per run, with an interactive CLI prompt for the verdict.
2. A caller-supplied membership file (`--batch FILE|-`) seeding the draw.
3. **A draw seeded from the sorted membership set, with the verdict as a second
   invocation of the same command.** *(chosen)*

**What a failed sample means.**

1. A finding about the caught cell: repair it and continue.
2. A finding about the sampled papers only.
3. **A finding about the batch: `batch-check: failed` on every artifact in the
   run, with no route to repair the caught cell.** *(chosen)*

**How the rules are enforced** (the mechanisms recorded under decision 5).

1. A SKILL.md instruction the agent is asked to follow.
2. A separate validator the skill is told to run before writing.
3. **Validation fused to the only writer, with a locator pattern set that is
   extensible but not replaceable.** *(chosen)*

## Decision

Five material decisions, each recorded with its rejected alternative because
each had a plausible one.

### 1. Extraction is a second **mode of `digest`**, not a third `literature` mode

`literature` is deliberately a graph-and-metadata capability: its entire surface
is OpenAlex/S2 plus the registry, and it never opens a PDF. Extraction is
*reading a paper and producing claims about it*, which is `digest`'s domain, and
the sampled check reuses `digest`'s probe mechanic. #97's own framing agrees.

Consequence handled: `digest` had no CLI group, borrowing `defend record`. The
commands land as a new `digest extract` group — `axes | record | sample |
render` — keeping skill and namespace aligned.

### 2. A separate `status.extraction` key and a separate `progress` row

`progress status literature` reported each paper as `{digested & understood /
gaps unresolved}` from its `understanding` block. A paper with eight cells
extracted and never read would have counted as "digested & understood" — the
guarantee inflation, concretely.

Extraction writes `status.extraction`, **never** `status.understanding`, and
`progress` gains a second, clearly-labelled row so a survey author sees
`extracted 40 / digested 3` rather than one blended number. The two rows are
never summed, and neither is the other's subset.

Within the block, `in-sample` (*a human checked **this** paper's cells*) and
`batch-check` (`pending | verified | failed`, the verdict on the **run**) are
two fields rather than one, because they answer different questions.

### 3. The **human** checks the sample; the agent never checks its own work

In depth mode the human reads and the agent probes them. In extraction the agent
reads — that is the premise. So if the agent also checked the sample, extraction
would certify *nothing*: it is self-attestation, which `digest`'s "verified,
never self-attested" guardrail forbids and agency rules out.

The check asks one question per cell: *does the source at that locator actually
say this?* Deliberately **not** "do you understand this paper" — extraction never
claimed that, and asking it would smuggle depth mode's guarantee back in through
the UX. The CLI therefore does not prompt: the draw reports the cells, the
questioning is the skill's job, and a second invocation records the verdict.

### 4. The sample is **deterministic**, seeded from the sorted membership set

Sort the batch's citekeys, SHA-256 that list to seed the PRNG, draw
`max(3, 10%)` (adjustable, and a convention rather than a statistical
guarantee). The same batch draws the same papers, in this process and every
future one.

Two refusals fall directly out of this, both from one asymmetry — `failed` is a
**finding** and must land whatever else went wrong, while `verified` is a
**claim** and may only be written for what was actually established:

- **A `verified` verdict is refused** — nothing written, exit 1 — when any drawn
  paper's cells could not be read. Otherwise the durable record says
  `batch-check: verified` with no paper marked checked, a self-contradictory
  state whose only honest signal is a transient exit code no later reader sees.
- **`--all` aborts before drawing** when membership cannot be fully determined.
  Since the draw is a function of membership, dropping an unreadable member
  *re-rolls the sample* — sample-shopping through a route that looks like a
  routine file problem. `--citekey` needs no such guard: membership is explicit
  there, and a missing member is reported against its own citekey.

### 5. A failed sample condemns the **batch**, not the paper

If the human finds a cell that misrepresents its source, the honest inference is
not "fix that cell": a process that produced one confidently-wrong cell in a
sample of three probably produced more in the other thirty-seven. Every artifact
in the run — sampled or not — gets `batch-check: failed`, and there is
deliberately **no route** to repair the one caught cell.

Two further mechanisms are recorded here — not because they follow from
batch-condemnation, which they do not, but because they are what answer the
*enforcement over documentation* and *agency* drivers, and because without them
the five decisions above are aspirational rather than enforced:

- **Validation and writing are one command.** The validating command is the
  *only* writer; there is no code path that records an unvalidated cell. Same
  move that made `_bind` the single writer of an asset spine in ADR-0037.
  Rules: a shape-checked locator, or the distinguished value `not-addressed`
  with a justification; **every** header axis accounted for per paper; no
  invented axes; rejection per paper, not per batch. `not-addressed` is counted
  per paper and in aggregate — that count is the anti-gaming signal, and it is
  cheaper and more honest than asking a checker to adjudicate whether an absence
  is real, which it cannot do without reading the paper.
- **`record` writes exactly two triage fields** — `extracted` and
  `extraction-cells` — and **never `disposition`**. The disposition state
  machine is the human's decision; a machine advancing it is precisely the
  agency violation this plugin exists to prevent. Where the sidecar carries YAML
  comments and `patch_triage` refuses (its rationales *are* the PRISMA log), the
  cells still land, the refusal is reported apart from write errors and carries
  a `kind` of `refused` or `failed`, and the run exits 1.

## Consequences

- The two claims coexist visibly on one artifact and cannot be conflated by
  anything reading the frontmatter, including a reader who has never heard of
  extraction: an absent key says "not read", which is true.
- A survey can fill a 40-paper comparison matrix in hours rather than a
  semester, without either paying depth mode's cost or pretending it did.
- Extraction's guarantee is bounded and stated: cells were recorded with
  locators, and a human checked a deterministic sample of them. It says nothing
  about the unsampled cells, nothing about comprehension, and nothing about
  whether a locator points where it claims — that last is `defend --target
  cited-work`'s job, which is *why* the locator is mandatory.
- The cells are the durable record and the matrix row is a projection of them,
  so `defend --target cited-work` has something exact to check later without
  parsing a table out of the author's prose.
- Costs the author carries, stated up front rather than discovered: the matrix
  is re-emitted canonically (column padding collapses, GFM alignment specifiers
  are dropped), and because row lookup is exact label equality, a hand-edited
  row label is not overwritten — it stops matching, and the next render adds a
  *second* row. Nothing is lost; the remedy is to restore the label.
- Render never deletes a row. A paper leaving the survey is removed by hand.
- A locked-open failure mode is accepted deliberately: a batch whose human is
  unavailable stays `batch-check: pending` forever. `pending` is honest, and
  there is no route to make it `verified` without a human.

## Rejected alternatives

- **A third `literature` mode.** Would make `literature` open a PDF for the
  first time and sits badly against its "propose and surface, never adjudicate"
  guardrail.
- **A new fourth skill.** Cleanest contract separation, but adds a
  reading-adjacent surface to a plugin whose value depends on a researcher
  holding the whole shape in their head.
- **One status key with a `mode:` discriminator.** The two contracts would share
  a field name, and anything reading it without knowing about `mode` silently
  inflates the weaker claim into the stronger one — the exact harm.
- **A single `sampled:` field** instead of `in-sample` + `batch-check`. It would
  have to read `failed` for a paper that was never checked, which parses as a
  finding about *that paper*. Misleading status is what this design exists to
  avoid.
- **A freshly-random sample per run.** Lets anyone re-roll until an easy draw
  comes up, and the run looks identical from the outside — the check hollowed
  out while appearing intact. (Seeding with Python's `hash()` was rejected for
  the same reason at implementation time: it is salted per interpreter, so the
  draw would change on every invocation while passing every same-process test.)
- **The agent checking its own extraction.** Self-attestation; certifies
  nothing.
- **No check at all — the mandatory locator as the whole guarantee.** A locator
  is shape-checked, not resolved: nothing in the pipeline opens the paper to see
  whether the cell's claim is at `§3`. Without a human check, extraction's claim
  collapses to "an agent wrote some strings in a well-formed shape", which is
  not worth a status key.
- **Treating a failed sample as a finding about the sampled papers only.**
  Splits the batch into checked-and-failed and unchecked-and-unmarked, which is
  the same misleading state a single `sampled:` field produces, one level up: a
  reader sees thirty-seven papers carrying no failure and infers they are fine,
  when the sample is precisely the evidence that they are not.
- **A SKILL.md instruction to include a locator, with no enforcement.** What
  #100 was filed against. It constrains nothing about what actually gets
  written, and the constraint's absence is invisible in the artifact.
- **An interactive CLI prompt for the verdict.** Puts the agent between the
  human and the sources, and makes the command unscriptable and untestable.
- **`--batch FILE|-` as the sample's membership input** (the original sketch).
  A caller-supplied membership file *is* the sample, since the draw is a
  deterministic function of membership — the anti-gaming property defeated by
  its own input.
- **Silently repairing the one caught cell.** The worst outcome available: it
  converts a signal about the population into a tidy-looking local fix.
- **Extending `defend record` with an extraction target.** Maximum reuse, but
  that command's job is certifying understanding, and it would then also write
  a key that deliberately means something weaker.
- **A separate validator the skill is told to run.** The skill could write
  without validating, which returns the constraint to documented-as-expected —
  exactly what #100 asked to move past.
- **A non-empty-string locator check.** Satisfied by `"see paper"`, which an
  agent filling 320 cells discovers immediately.
- **A closed locator pattern set.** A domain assumption in a plugin that forbids
  them; the set ships as a default and is **extensible** via
  `literature.extraction.locator_patterns`, for the same reason
  `venue_resolvers` is (ADR-0038). Extension is additive only — configured
  patterns are appended, and there is deliberately no way to *drop* a default.
  Widening the accepted set can only admit a shape that would otherwise have
  been rejected; letting a consumer remove `§` or `Eq.` would let a
  misconfiguration reject locators their own authors wrote, which is the
  costlier direction of the two.
- **Making `not-addressed` simply locator-exempt.** 8 axes × 40 papers is 320
  chances to write "not addressed" and skip the hard part. A justification plus
  a visible count prices it instead.
- **Allowing an axis to be omitted.** Without the completeness rule,
  `not-addressed` is unnecessary: an agent finding an axis hard just omits the
  cell, and a short row looks like a clean row.
- **Automatic deletion of matrix rows.** The one operation here with no safe
  failure mode — a bug that drops rows loses the author's work silently.
- **PDF parsing in the CLI.** The agent reads PDFs natively; a parser would
  breach the light-dependency posture for nothing (same reasoning as ADR-0037).

## Links

`docs/superpowers/specs/2026-08-28-digest-extraction-mode-design.md` (the full
design; note the `*Amended during implementation*` blocks in §3.1, §5, §8 and
§9 — the amendment is what shipped); `skills/digest/SKILL.md`;
`skills/progress/SKILL.md`; `skills/literature/SKILL.md`;
`defendable-science/defendable_science/digest/{extraction,artifact,sampling,render}.py`;
`defendable-science/defendable_science/core/mdtable.py`;
ADR-0033 (evidentiary point records, the shared accountability log), ADR-0034
(`digest` as a dedicated skill), ADR-0014 (`progress` anti-Goodhart),
ADR-0037 (the registry layer this builds on), ADR-0039 (recorded consumer
layout); #97 (Gap 2), #100, #101 (Gap 3, survey-shaped templates — separate).
