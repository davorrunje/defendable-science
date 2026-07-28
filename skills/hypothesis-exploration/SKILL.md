---
name: hypothesis-exploration
description: Use when generating, capturing, ranking, or triaging candidate hypotheses for a paper — a raw idea to stash, citation-seeded leads to mine, a data pattern worth chasing, or a backlog to prioritize and thin. Runs an origin-agnostic idea pipeline into the paper's backlog and hands promoted items off to hypothesis-testing. Proposes only; never tests or adjudicates a claim.
---

Hypothesis-exploration is the **generate** skill at the hypothesis level — the
first flywheel of the three-level mirror (see `../../docs/design/01-lifecycle.md`
§1). It runs an **origin-agnostic idea pipeline**: raw hunches, citation-seeded
leads, and data-driven observations all land as rows in the paper's
`backlog.md`, get ranked, and are either **promoted** into a hypothesis folder
(handed to `hypothesis-testing`) or **dropped** with a recorded reason.

It sits on the *explore* side of the firewall (`../../docs/design/00-meta-spec.md`
§2.3): **exploration proposes, resolution disposes, synthesis reports.** This
skill only proposes. It never tests a hypothesis, never assigns a verdict, and
never decides what the author pursues. The human promotes; the skill advises
(agency principle, §2.1). Grounding:
`../../resources/references/citation-scouting.md`.

## When to use

- **Park** a raw idea mid-flow so it is not lost, without committing to work it.
- **Generate** candidate hypotheses for a paper: mine the citation graph via
  `literature scout`, run exploratory data analysis, or apply the generation
  moves below.
- **Rank** a backlog to decide what is worth a testing slot.
- **Promote** a ranked item into a hypothesis folder to begin `hypothesis-testing`.
- **Drop** an item that will not be pursued, recording why (file-drawer discipline).

Do **not** use this skill to test, confirm, refute, or score a hypothesis — that
is `hypothesis-testing`'s job, gated by a human sign-off (`findings.md` verdict).

## Verbs

The pipeline is a small state machine over `backlog.md` rows:
`parked → candidate → ranked → promoted | dropped`.

| Verb | Does | Row transition |
|---|---|---|
| `park` | stash a one-line raw idea, no analysis | → `parked` (new row) |
| `generate` | produce candidate hypotheses (scout / EDA / moves) | → `candidate` (new rows) |
| `rank` | score candidates against the rubric, flag their framing | `candidate/parked` → `ranked` |
| `promote` | scaffold a hypothesis folder, hand off to testing | `ranked` → `promoted` |
| `drop` | record a reason and retire the row (keep it) | any → `dropped` |

`promote` and `drop` are terminal but **never delete** a row — dropped ideas stay
on record (see Guardrails: file-drawer discipline). `park` is deliberately
frictionless; `generate` and `rank` do the analytic work.

### Backlog row schema

Every row (a line in the `backlog.md` table under `docs/research/<paper>/`)
carries provenance so any candidate can be traced to where it came from:

```
| id | one-line hypothesis | move/type | provenance | EIG | feas | interest | frame | status | note |
```

- **provenance** — the origin, mandatory:
  - scouted → `source-paper-id` + a **citing-context snippet** (verbatim, from
    `literature scout`; the auditable link back to who-cited-what);
  - EDA → `eda:<dataset-id>` + the observed pattern;
  - own → `own` (a parked hunch or a generation-move idea).
- **frame** — `gap-spotting` or `problematization` (see Ranking).
- **note** — for a dropped row, the recorded drop reason.

> **Tooling.** Row append/transition is the `defendable-science backlog
> park|add|list|rank|promote|drop` CLI group
> (`defendable_science/exploration/backlog.py`) — ensure via
> [`ensure-tooling`](../../resources/ensure-tooling.md); shared with
> `paper-exploration`. `add` realizes the `generate` verb's row-append; `list` is a
> read-only inspection command. By hand (if the CLI isn't available): edit the
> `backlog.md` table directly, keeping the column order above so the `backlog`
> verbs (`rank`, `promote`, `list`) can parse it.

## Generation moves

`generate` produces candidates three ways; all land as `candidate` rows with
provenance.

1. **Scout-seeded** — call `literature scout --level hypothesis` (see
   `../../docs/design/02-literature.md` §2). It returns ranked leads, each with
   `type | source-paper-id | citing-context snippet | why-it-matters | est.
   feasibility`. Copy that provenance verbatim into the row; do not paraphrase
   the snippet. Scout classifies each lead into an idea type — extension,
   contradiction, new-domain, transferable-technique, methodological-gap — which
   maps onto the moves below.
2. **EDA** — surface a pattern, anomaly, or unexpected correlation in available
   data and phrase it as a falsifiable claim. Record the dataset id and the
   observation as provenance. (Exploratory by construction — the eventual test
   must be tagged confirmatory-vs-exploratory in `strategy.md`; this skill does
   not run it.)
3. **Generation moves** — author-side lenses for turning a starting point into a
   claim:

| Move | Turn … into a claim by | Pairs with scout type |
|---|---|---|
| **Extend** | pushing a result to a new regime, scale, or condition | extension |
| **Contradict** | attempting to refute or bound a claim others rely on | contradiction |
| **Transfer** | porting a technique from an adjacent domain | transferable-technique |
| **Probe-failure** | finding where a known method breaks and why | methodological-gap |
| **Mechanism** | proposing *why* a known effect occurs (causal story) | — |
| **Compose** | predicting the interaction of two established effects | new-domain |

Each move yields *one falsifiable sentence*, not a topic. If it cannot be
written as "X will/does Y under Z," it is a theme, not a hypothesis — keep it
`parked` until it sharpens.

## Ranking

`rank` scores each candidate on three axes and attaches a framing flag. Scores
are **advisory inputs to the human's ordering**, not an automatic gate.

- **Expected information gain (EIG)** — how much a resolved verdict would move
  belief *regardless of direction*. High EIG discriminates between live rival
  explanations; a foregone-conclusion test is low-EIG even if easy. This is the
  primary ranking axis (the flywheel selects for belief-moving tests —
  `../../docs/design/01-lifecycle.md` §1).
- **Feasibility × Interest** (Alon 2009,
  `../../resources/references/citation-scouting.md` §5) — feasibility: can it be
  tested with the data, backends, and time on hand; interest: does the answer
  matter to the paper's thesis or the field. Score each; the product guards
  against both infeasible-but-fascinating and trivially-easy-but-pointless.
- **Framing flag — gap-spotting vs. problematization** (Sandberg & Alvesson
  2011, same digest §5). Flag each candidate:
  - *gap-spotting* — fills a hole others left open (incremental; fine, but common);
  - *problematization* — challenges an assumption the field takes for granted.

  The flag is **not disqualifying** — it is surfaced so the author sees the mix.
  When interest is comparable, problematization typically carries higher EIG.
  Never auto-rank problematization above gap-spotting; present the flag and let
  the human weigh it.

Output is an ordered `backlog.md` (rows set to `ranked`) plus a one-line
rationale per top candidate. The skill recommends; it does not select the
testing slate.

## Composition

- **Upstream:** `literature scout` (`../../docs/design/02-literature.md`) feeds
  citation-seeded candidates; EDA and the generation moves feed the rest. All
  origins converge on the one `backlog.md`.
- **Downstream — `promote`:** scaffold `docs/research/<paper>/hypotheses/<YYYY-MM-DD-slug>/`
  and write `hypothesis.md` (the free-form claim — the first staged doc of
  `hypothesis-testing`, `../../docs/design/01-lifecycle.md` §2.2), carrying the
  backlog provenance forward. Set the backlog row to `promoted` with a link to
  the folder. Control then passes to `hypothesis-testing`, which builds
  `strategy.md` → design/plan → `findings.md`.
- **Understanding.** A promoted hypothesis may be **examined at the strategy
  stage** of testing (`defend` on `strategy`: assumptions, entailments,
  falsifiers, rival explanations — `../../skills/defend/SKILL.md`). Exploration
  does not examine; it hands off a claim clean enough to be defended later.
- **Progress.** Only *promoted* items become artifacts (`hypothesis.md` +
  downstream), and those carry the status frontmatter `progress` rolls up — the
  `backlog.md` table itself is **not** projected into the dashboard (`progress`
  reads artifact frontmatter, not the backlog). Backlog depth stays visible in
  `backlog.md` directly; a large backlog or many dropped rows is not "bad" and is
  never scored (`../../docs/design/00-meta-spec.md` §3.6).

## Guardrails

- **Proposes only — the firewall.** This skill generates and ranks; it never
  tests, never assigns a verdict, never decides what is pursued. Promotion is a
  human act (`../../docs/design/00-meta-spec.md` §2.1, §2.3;
  ADR-0006 `../../decisions/0006-two-skills-per-level.md`).
- **Provenance is mandatory.** No candidate row without an origin. Scouted rows
  must carry the source-paper id **and** the verbatim citing-context snippet;
  fabricating or paraphrasing a snippet is a firewall violation (automation-bias /
  citation-fabrication risk, §2.1).
- **File-drawer discipline.** `drop` records a reason and retires the row — it
  never deletes it. Dropped and parked ideas remain visible so the selection
  history is auditable and the file drawer cannot silently swallow inconvenient
  ideas.
- **A hypothesis is a falsifiable claim, not a topic.** Refuse to promote a row
  that cannot be stated as a testable sentence; keep it `parked`.
- **Ranking advises, never selects.** EIG / feasibility×interest / the framing
  flag are inputs the human weighs. Do not auto-promote the top row and do not
  rank problematization above gap-spotting by fiat.
- **No premature testing talk.** Do not sketch experiments, pick baselines, or
  estimate effects here — that is `strategy.md`/design in `hypothesis-testing`.
  Exploration stops at the claim.

## Commit attribution

When you commit artifacts produced by this skill, add these git trailers —
discovery + provenance (see [`../../resources/commit-attribution.md`](../../resources/commit-attribution.md)):

```
Generated-with: defendable-science (https://github.com/davorrunje/defendable-science)
DefendableScience-Skill: hypothesis-exploration
```
