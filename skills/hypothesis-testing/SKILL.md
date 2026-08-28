---
name: hypothesis-testing
description: Use when driving one promoted hypothesis from a claim to a signed verdict — the resolve skill at the hypothesis level. Runs the staged pipeline hypothesis → strategy → design/plan → findings, does the SCIENCE (strategy, rigor, verdict) and delegates the ENGINEERING to the bound engineering backend. Invoke when a backlog item is promoted, or when returning to an in-flight hypothesis folder.
---

# Hypothesis Testing

The **resolve** skill at the hypothesis level. It takes one promoted claim and
drives it through staged documents to a human-signed **verdict** —
confirmed / refuted / inconclusive — backed by cited experimental evidence.

**Core principle — SCIENCE BEFORE ENGINEERING.** The scientific thinking (how you
would confirm or refute the claim, what rival explanations exist, which rigor
choices apply) is settled in `strategy.md` *before* any code is designed. Only
then is the engineering — design, plan, implementation — delegated to the bound
engineering backend via the engineering-delegation contract. This skill does not
do engineering.

It also honors the two governing principles:

- **Agency** — the verdict is a *material decision*: the researcher decides it and
  signs it by name. The experiment backend stamps evidence; it never adjudicates.
- **Understanding** — a **refuted** hypothesis is a successful, *done* result, not
  a failure. The point is to learn the truth of the claim, whichever way it falls.

## When to use

- A `backlog.md` item has just been **promoted** and needs to be resolved.
- You are resuming an in-flight hypothesis (pick up at the first
  unfinished staged doc in its folder, resolved from the repo's layout).
- You need to re-check whether a resolved hypothesis's evidence has gone stale
  (`is-current` on its run-refs). Revising a signed verdict is itself a **material
  decision** — it re-triggers the `defend` guardrail and a new named sign-off, not
  a silent flip.

Do **not** use it to *generate* candidate hypotheses — that is
[`hypothesis-exploration`](../hypothesis-exploration/SKILL.md) (explore proposes,
resolve disposes; the firewall). One skill never both proposes and adjudicates the
same claim.

## Staged documents

All produced **in order** in the hypothesis folder (resolved from the repo's layout). Each carries a status frontmatter block that feeds
[`progress`](../progress/SKILL.md). Templates live in
[`../../resources/templates/`](../../resources/templates/).

1. **`hypothesis.md`** — the free-form claim, carried over from the promoted
   backlog item. State the claim, why it matters, and what a confirming vs.
   refuting outcome would look like. No method yet.

2. **`strategy.md`** — *the science, before any engineering.* This is the heart of
   the skill:
   - How the claim will be **confirmed or refuted** — the decisive comparison, the
     measured quantity, the decision rule.
   - **Rival hypotheses + discriminating tests** — at least one competing
     explanation and a result that would separate it from your claim.
   - The **rigor-kit choices** (below): confirmatory-vs-exploratory tag,
     preregistered analysis, power/MDE, severity argument, equivalence bounds if
     the claim is a null.
   - Calls [`literature position --level hypothesis`](../literature/SKILL.md) — an
     adversarial precedent rapid-review answering *"would a reviewer say this is
     already known?"* Cite the precedent that would undercut novelty.
   - Declares the **datasets** it will use; materialize/verify them via the
     [`dataset`](../dataset/SKILL.md) skill so their fingerprints are pinned.
   - **`defend` fires here** on the `strategy` target — assumptions, entailments,
     falsifiers, rival explanations, and the methodology it invokes. Resolve
     surfaced gaps before proceeding to engineering. See
     [`../defend/SKILL.md`](../defend/SKILL.md).

   > *e.g.* claim: "pruning to 50% sparsity doesn't hurt accuracy." Strategy —
   > decisive comparison: pruned vs. dense test accuracy; it is a **null claim**, so
   > **TOST** against a pre-registered ±1% equivalence bound, powered for it; rival:
   > "the task is too easy to separate them," discriminated by a harder split; tag:
   > confirmatory.

3. **`design.md` / `plan.md`** — *the engineering, delegated.* Hand off to the
   engineering backend bound in `.defendable-science/config.yml` (`engineering_backend:`)
   via the engineering-delegation contract: `design` → `plan` → `implement`. Store
   the design and plan under this hypothesis folder (`design.md`, `plan.md`);
   `implement` builds the experiment harness/code. `defendable-science` does not design
   experiments, write plans, or implement — it composes with the engineering backend
   for all of that. The *experiment* backend's `run` (below) then executes the built
   harness to produce the runs.

4. **`findings.md`** — *the verdict, a material decision.*
   - Report results by citing the experiment backend's **run-refs** — **never**
     hand-copied numbers. Result tables/figures are written by the backend's
     `tables` capability as managed, regenerable blocks.
   - State the **verdict**: `confirmed` | `refuted` | `inconclusive`, with the
     reasoning tied to the strategy's decision rule and severity argument.
   - The verdict is recorded with a **named human sign-off + date**. The
     **`defend` guardrail fires before sign-off** (findings-verdict checkpoint):
     stop, surface any gap, offer to examine/teach, record; the human may override,
     override logged. Not a hard block — but a gap can never be passed silently.

## How it works

The pipeline is sequential but resumable: on entry, find the first staged doc that
is missing or unfinished and continue from there. Never skip forward — a
`findings.md` written before an examined `strategy.md` violates the science-first
discipline and the explore/confirm firewall (letting the results choose the test is
exactly what invalidates a confirmatory claim).

Evidence flows through the **experiment-backend contract**
([`../../resources/contracts/experiment-backend.md`](../../resources/contracts/experiment-backend.md)),
resolved from the `backend:` binding in the paper registry (which the CLI resolves from the repo's layout):

| Capability | Use in this skill |
|---|---|
| `run` | execute (or resume) an experiment for a config → returns a **run-ref** (the citable unit of evidence) |
| `evidence` | fetch results for a run-ref → structured results + a **provenance stamp** (config hash, code/symbol provenance, dataset `id+version+sha256`, timestamps, hardware) |
| `tables` | render results into the result blocks `findings.md` cites (the only writer of numbers into docs) |
| `is-current` | check whether a run-ref's evidence is still valid → `current` \| `stale(reasons)` |

Because every reported number resolves to an exact `id+version+sha256`, results are
reproducible and staleness is honest. `is-current` reports staleness; it does **not**
decide to re-run — the researcher does.

## Rigor kit

Applied in `strategy.md` (chosen before outcomes) and enforced through
`findings.md`. Every element is also a [`defend`](../defend/SKILL.md) `methodology`
target — you must be able to explain *why*, not merely perform the ritual (checklists
live in [`../../resources/rigor/`](../../resources/rigor/); the *why* is grounded in
[`../../resources/references/understanding-and-defense.md`](../../resources/references/understanding-and-defense.md)).

- **Confirmatory vs. exploratory / preregistration** — fix the analysis before
  outcomes; curbs HARKing and shrinks the forking-paths garden. Does not forbid
  exploration, only *mislabeling* it.
- **Rival hypotheses + discriminating tests** — a competing explanation plus a
  result that separates it.
- **Severity** — passing counts as evidence only if the test would probably have
  *failed* were the claim false.
- **Power / MDE** — set before data; a null from an underpowered test is
  uninformative, not evidence of no effect.
- **TOST / equivalence** — a non-significant *p* is *not* "no effect"; a null claim
  needs a pre-set equivalence bound. (The most cargo-culted null claim.)
- **Disclosure checklist + file-drawer** — report all runs and analyses; selective
  reporting is what corrupts the record.
- **Per-dataset datasheets** — Gebru-style, produced via the
  [`dataset`](../dataset/SKILL.md) skill for every dataset the strategy declares.
- **Red-team pass** — adversarial self-review of the strategy and the findings
  before the verdict is signed.

## Composition

- [`hypothesis-exploration`](../hypothesis-exploration/SKILL.md) — upstream; a
  promoted backlog item seeds `hypothesis.md`.
- [`literature`](../literature/SKILL.md) — `position --level hypothesis` in the
  strategy stage (adversarial precedent review).
- [`dataset`](../dataset/SKILL.md) — materialize, verify, and datasheet every
  declared dataset.
- The bound **engineering backend** — `design` → `plan` (and `implement`) for the
  `design.md`/`plan.md` stage, via the engineering-delegation contract. All
  engineering lives here (ADR-0002, refined by ADR-0023).
- The bound **experiment backend** — `run` / `evidence` / `tables` / `is-current`.
- [`defend`](../defend/SKILL.md) — strategy target (during strategy) and guardrail
  (before the findings sign-off).
- [`progress`](../progress/SKILL.md) — reads this hypothesis's status frontmatter;
  a resolved hypothesis (any verdict) rolls up as **done/green**.

## Guardrails

- **Science before engineering.** No `design.md`/`plan.md` until `strategy.md` is
  written and examined. No numbers in `findings.md` until runs exist.
- **Never hand-copy results.** Cite **run-refs** and let `tables` write the result
  blocks. A number without a run-ref is not evidence.
- **The verdict is the human's.** It is a material decision recorded with a named
  human sign-off; the backend stamps evidence but never adjudicates. The `defend`
  guardrail fires before sign-off and any override is logged.
- **Refuted is done, not failed.** Verdict and readiness are distinct axes; a
  refuted claim is a successful result. Do not treat it as a red mark or bury it —
  file-drawer discipline forbids that.
- **Don't do engineering here.** Delegate design/plan/implementation to the bound
  engineering backend; this skill owns only the scientific stages.
- **Stay behind the firewall.** This skill resolves; it does not generate
  candidate hypotheses, and it does not adjudicate without the researcher's recorded
  decision.
- **Follow-ups become issues, not TODOs** — a deferred check or a known gap in the
  record is captured as a self-contained GitHub issue, not left in a doc's margin.

## Commit attribution

When you commit artifacts produced by this skill, add these git trailers —
discovery + provenance (see [`../../resources/commit-attribution.md`](../../resources/commit-attribution.md)):

```
Generated-with: defendable-science (https://github.com/davorrunje/defendable-science)
DefendableScience-Skill: hypothesis-testing
```
