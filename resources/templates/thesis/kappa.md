---
status:
  level: thesis
  id: null                     # <thesis-slug> — fill when the thesis is framed
  verdict: n/a                 # thesis has no verdict axis; readiness carries it
  readiness: null              # framing | synthesis | defensible (defensible only once signed)
  signed-off-by: null          # REQUIRED for defensibility — named human; not defensible until set
  signed-off-date: null        # REQUIRED
  evidence: []                 # the kappa introduces NO new findings — papers carry all evidence
  covers: []
  load-bearing: null
  understanding: {status: ok, unresolved: []}   # from the mock viva before sign-off
  blockers: []                 # e.g. uncovered aims surfaced by progress
  last-updated: null           # <YYYY-MM-DD>
---

# Kappa: <thesis title>

<!-- The synthesizing framing chapter ("overcoat") that turns a stack of papers
     into one thesis. It RECONTEXTUALIZES already-resolved work — it introduces NO
     new findings. If synthesis seems to need a new result, that is a hypothesis for
     hypothesis-testing inside a paper, not kappa prose. The author authors; the
     skill drafts scaffolds. -->

## Introduction / background

<!-- The problem space the aims sit in. -->

## Unifying narrative / aims

<!-- The through-line from aims.md: how the papers cohere into one project. -->

## Independent related work

<!-- An EXTENSIVE related-works synthesis at thesis scope — broader than any single
     paper's positioning. Draw on `literature position`. -->

## Per-paper summary + contribution statement

<!-- For EACH appended paper: a summary AND an explicit statement of the candidate's
     own contribution to co-authored work. The contribution statement is
     load-bearing (authorship/credit norms) and is the author's to write — the skill
     never asserts the split. -->

### <paper-id>

- **Summary:** *<...>*
- **Candidate's contribution:** *<author-written>*

## Unifying discussion

<!-- The comprehensive concluding discussion across all papers — the original
     contribution to knowledge. -->

## Future work

<!-- Where the program goes next (feeds paper-exploration). -->

---

## Defensibility gate

<!-- THE MATERIAL DECISION at the thesis level. The thesis is done when DEFENSIBLE:
     every aim covered by ≥1 paper AND the kappa states a coherent through-line +
     the original contribution. Roll-up target is NARRATIVE COVERAGE of the aims —
     never a paper count or percentage. -->

- **Aim coverage:** *<every aim covered? list any uncovered — a blocker>*
- **Through-line stated:** *<yes / no>*
- **Original contribution stated:** *<yes / no>*

### Mock viva + per-gap sign-off

<!-- ESCALATED gate (ADR-0021): before defensibility is recorded, `defend` runs a
     full MOCK VIVA across all three targets (claim | cited-work | methodology).
     This gate is non-blocking but escalated — instead of one blanket override, the
     author must ACKNOWLEDGE EACH surfaced gap IN WRITING before proceeding. The AI
     never adjudicates a gap as "critical" and never hard-blocks. -->

| Surfaced gap | Acknowledged by | Date |
|---|---|---|
| *<gap>* | *<named human>* | *<YYYY-MM-DD>* |

<!-- Defensibility is real only once signed-off-by + signed-off-date are set above
     and every gap row is acknowledged. -->
