---
status:
  level: hypothesis
  id: null                     # <YYYY-MM-DD-slug> — matches the hypothesis folder name
  verdict: pending             # still pending — the verdict is decided in findings.md
  readiness: pending
  signed-off-by: null
  signed-off-date: null
  evidence: []                 # run-refs appear once runs exist; none here yet
  covers: []
  load-bearing: null
  understanding: {status: pending, unresolved: []}   # `defend` fires on `strategy` — record gaps here
  blockers: []
  last-updated: null           # <YYYY-MM-DD>
---

# Strategy: <slug>

<!-- THE SCIENCE, BEFORE ANY ENGINEERING. Settle everything here before design.md
     / plan.md. Letting the results choose the test is exactly what invalidates a
     confirmatory claim. `defend --target strategy` fires at the end of this doc;
     resolve surfaced gaps before delegating engineering to the bound engineering
     backend. -->

## Decisive comparison

<!-- How the claim is confirmed or refuted: the comparison made, the quantity
     measured, and the DECISION RULE stated in advance (thresholds, direction,
     conditions). No results yet. -->

- **Measured quantity:** *<...>*
- **Comparison:** *<... vs. ...>*
- **Decision rule (pre-registered):** *<confirm if ...; refute if ...>*

## Rigor kit

<!-- Fill every applicable item. Each is also a `defend --target methodology` seed:
     you must be able to explain WHY it works, not just perform it. Full checklist:
     ../../rigor/rigor-kit.md. -->

### Confirmatory vs. exploratory

- **Tag:** `confirmatory` | `exploratory`
- <!-- If confirmatory: the analysis above is fixed before outcomes. If
       exploratory: say so honestly — the point is not to forbid exploration, only
       to avoid MISLABELING it as confirmation (HARKing / forking paths). -->

### Rival hypotheses + discriminating tests

<!-- At least one competing explanation, plus a result that would separate it from
     the focal claim. A "limitation" no analysis could ever change is not a
     discriminating test. -->

| Rival explanation | Discriminating test | Outcome under rival vs. focal |
|---|---|---|
| *<...>* | *<...>* | *<...>* |

### Severity

<!-- Argue that a PASS would be evidence: the test would very probably have FAILED
     were the claim false. A test the claim passes regardless carries no weight. -->

### Power / MDE

<!-- Set the minimum detectable effect and target power BEFORE data. A null from an
     underpowered design is uninformative, not evidence of no effect. -->

- **MDE:** *<...>*  **Target power:** *<...>*  **Implied sample/seeds/runs:** *<...>*

### Equivalence (TOST) — only if the claim is a null / "no effect"

<!-- A non-significant p is NOT "no effect." State the pre-set equivalence bound and
     the two one-sided tests. Absence of evidence ≠ evidence of absence. Delete this
     block if the claim is not a null. -->

- **Equivalence bound:** *<±...>*

### Disclosure / file-drawer

<!-- Pre-commit to reporting ALL runs, conditions, exclusions, and analyses —
     including nulls. Selective reporting is what corrupts the record. -->

### Red-team pass

<!-- Adversarial self-review of this strategy before any engineering: where is it
     weakest, what would a hostile reviewer attack? "You must not fool yourself —
     and you are the easiest person to fool." -->

## Datasets

<!-- Declare each dataset; materialize/verify via the `dataset` skill so its
     id+version+sha256 fingerprint is pinned and it carries a Gebru-style
     datasheet. -->

- *<dataset-id>* — *<role in the test>*

## Literature position

<!-- Call `literature position --level hypothesis` — an adversarial precedent
     rapid-review: "would a reviewer say this is already known?" Cite the precedent
     that would most undercut novelty. -->

## Examination checkpoint

<!-- `defend --target strategy` outcome: assumptions, entailments, falsifiers, rival
     explanations, and the methodology invoked. Record unresolved gaps in the
     `understanding` frontmatter above; resolve them before design/plan. -->
