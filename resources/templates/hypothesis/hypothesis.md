---
status:
  level: hypothesis
  id: null                     # <YYYY-MM-DD-slug> — matches the hypothesis folder name
  verdict: pending             # pending | confirmed | refuted | inconclusive (set in findings.md)
  readiness: pending           # pending | resolved
  signed-off-by: null          # named human — set only at the findings verdict
  signed-off-date: null
  evidence: []                 # backend run-refs — set in findings.md, never hand-copied numbers
  covers: []                   # n/a at hypothesis level (paper→thesis field)
  load-bearing: null           # does refutation block the parent paper's claim? (true|false)
  understanding: {status: pending, unresolved: []}   # written by the `defend` skill; never scored
  blockers: []
  last-updated: null           # <YYYY-MM-DD>
---

# Hypothesis: <one-line claim>

<!-- The free-form claim, carried over from the promoted backlog row. No method
     yet — that is strategy.md. State it as a falsifiable sentence: "X does/will Y
     under Z." -->

## Claim

*<State the single falsifiable claim in one or two sentences.>*

## Why it matters

<!-- What does resolving this move? Which paper claim does it feed, and is it
     load-bearing (would refutation invalidate the parent's claim)? Set
     `load-bearing` above accordingly. -->

## What confirmation vs. refutation looks like

<!-- Sketch, in plain language, the observable outcome that would COUNT AS
     confirming and the one that would count as refuting. Both are valid, done
     outcomes — refuted is successful science, not failure. Detailed decision
     rules belong in strategy.md. -->

- **Confirming:** *<...>*
- **Refuting:** *<...>*

## Provenance

<!-- Carried from the backlog row: origin (scouted / EDA / own) + the verbatim
     citing-context snippet or observed pattern. -->
