---
status:
  level: paper
  id: null                     # <paper-id> — kebab-case slug from the papers.md registry
  verdict: null
  readiness: drafting
  signed-off-by: null
  signed-off-date: null
  evidence: []
  covers: []
  load-bearing: null
  understanding: {status: pending, unresolved: []}   # `defend` fires on `positioning` + `cited-work`
  blockers: []
  last-updated: null           # <YYYY-MM-DD>
---

# Positioning: <paper-id>

<!-- Related-works synthesis: where this paper sits and what its delta is.
     Paper-level analog of strategy.md. Produced via `literature position --level
     paper` — the full treatment, not the hypothesis-level rapid review. Examined on
     the `positioning` (novelty) and `cited-work` (do sources support the claims)
     targets. -->

## Field taxonomy

<!-- The branches of prior work this paper touches — how the field organizes. -->

## Concept matrix

<!-- Rows = methods/prior works; columns = the attributes the paper's delta turns
     on. The cell pattern should make the gap this paper fills visible. -->

| Method | <attr 1> | <attr 2> | <attr 3> |
|---|---|---|---|
| *<prior work>* | | | |
| **This paper** | | | |

## Include / exclude log (PRISMA-style)

<!-- The anti-cherry-picking audit trail: how the surveyed set was selected, what
     was excluded and why. Sourced from the literature triage sidecar. -->

## Per-branch delta

<!-- One paragraph per branch: what this paper adds beyond it. Include the
     CLOSEST-PRIOR-WORK paragraph explicitly — the work most likely cited against
     the novelty claim — and the isolating ablation that guards the claim. -->

## Baseline list

<!-- Derived from the above: one strong tuned representative per branch + current
     SOTA + the most-likely-cited-against + a simplest floor. These become the
     comparisons the ledger's grounds cite. -->

- *<baseline>* — *<branch / why included>*

## Examination checkpoint

<!-- `defend` outcome on positioning (novelty vs. prior work) and cited-work (each
     cited source actually supports the sentence it backs). Record unresolved gaps
     in the `understanding` frontmatter above. -->
