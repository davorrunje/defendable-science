---
status:
  level: paper
  id: null                     # <paper-id> — kebab-case slug from the papers.md registry
  verdict: null                # publish | no-go — the material decision; no-go is a valid, done outcome
  readiness: drafting          # → under-review → published as the manuscript progresses
  signed-off-by: null          # REQUIRED — named human; decision is not real until set
  signed-off-date: null        # REQUIRED
  evidence: []                 # run-refs (via the ledger) backing the contribution
  covers: []                   # thesis aims this paper supports, if any
  load-bearing: null
  understanding: {status: ok, unresolved: []}        # from the `defend` guardrail before sign-off
  blockers: []
  last-updated: null           # <YYYY-MM-DD>
---

# Decision: <paper-id>

<!-- THE PUBLISH / NO-GO VERDICT — a material decision, the paper-level mirror of a
     hypothesis findings verdict. Not real until `signed-off-by` + `signed-off-date`
     are set. The `defend` guardrail fires BEFORE sign-off across positioning
     (novelty), cited-work (sources support claims), and the ledger claims: it
     surfaces gaps; the human may override, override logged — a stop-and-confirm,
     not a hard block. The AI never adjudicates publish-worthiness. -->

## Question

Does the accumulated hypothesis evidence support the contribution `pitch.md`
claims, and does `positioning.md` show a defensible delta against prior work?

## Evidence summary

<!-- Point at the ledger claims and their run-refs; do NOT restate numbers here.
     Confirm every load-bearing claim resolves to grounds (run-refs), and note any
     refuted load-bearing hypothesis (a blocker the human must weigh). -->

- **Ledger:** `ledger.md` — claims C1…Cn, run-refs cited therein
- **Load-bearing hypotheses:** *<resolved? any refuted?>*

## Staleness check

<!-- `is-current` on the cited run-refs before deciding. Stale evidence is surfaced;
     the human decides whether to re-run. -->

## Decision

**`<publish | no-go>`**

<!-- Reasoning tied to the evidence and positioning.
     - publish: contribution supported, delta defensible, bar met.
     - no-go: not yet / not this framing — a valid, completed outcome; note what a
       future paper would need (feeds paper-exploration's limitation-driven lens). -->

*<Reasoning.>*

## Red-team + disclosure closeout

<!-- Adversarial pass before sign-off: strongest reviewer objection and the answer;
     confirm full disclosure (all conditions/runs, incl. nulls). -->

## Examination checkpoint + sign-off

<!-- Guardrail examination outcome (gaps surfaced / resolved / overridden-with-log), then
     the named human records the decision by setting signed-off-by + signed-off-date
     above. -->
