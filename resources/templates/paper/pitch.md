---
status:
  level: paper
  id: null                     # <paper-id> — kebab-case slug from the papers.md registry
  verdict: null                # no-go | publish — decided later in decision.md
  readiness: drafting          # drafting | under-review | published (sub-states of done)
  signed-off-by: null          # set at the decision.md publish/no-go sign-off
  signed-off-date: null
  evidence: []                 # run-refs accumulate via the ledger; none required at pitch
  covers: []                   # which thesis aims this paper supports (if under a thesis)
  load-bearing: null           # n/a at paper level (hypothesis→paper field)
  understanding: {status: pending, unresolved: []}
  blockers: []
  last-updated: null           # <YYYY-MM-DD>
---

# Pitch: <working title>

<!-- The committed framing carried over from the promoted portfolio-backlog row.
     Paper-level analog of hypothesis.md. -->

## Central claim

*<The one thing this paper asserts, in one or two sentences.>*

## Contribution

<!-- What is new here — the delta the paper adds to the record. Defended in detail
     in positioning.md against prior work. -->

## Target venue + bar

<!-- Intended venue and the standard it holds contributions to (rigor, novelty,
     baselines expected). Shapes scope and positioning. -->

## Load-bearing hypotheses

<!-- Which hypotheses under docs/research/<paper>/hypotheses/* must resolve for this
     claim to hold. A refuted load-bearing hypothesis blocks the paper (progress
     surfaces it) — that is honest, not failure. -->

- `<YYYY-MM-DD-slug>` — *<role in the claim>* — load-bearing: *<yes/no>*

## Provenance

<!-- Carried from the portfolio-backlog row: the generation lens it came from
     (mechanism-transfer / limitation-driven / result-driven) + the verbatim
     origin — which resolved paper, limitation, or result prompted it. -->
