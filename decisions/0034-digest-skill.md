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
