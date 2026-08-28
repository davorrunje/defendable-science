---
name: thesis
description: Use when a research program is (optionally) bound into a doctoral thesis — to frame the aims and choose which portfolio papers compose it, or to assemble the kappa framing chapter and clear the defensibility gate. The optional top level above papers; skip it entirely for a repo that is not a thesis.
---

Thesis is the **optional top level** of the three-level mirror
(`../../docs/design/00-meta-spec.md` §3.1): `thesis ⊃ papers ⊃ hypotheses`. A repo
that is not a doctoral thesis simply omits it — its top is the portfolio. Where it
exists, the thesis binds a subset of the portfolio's papers into one examinable
document via a synthesizing framing chapter (the Nordic **"kappa"**), plus the
appended papers themselves.

It is deliberately a **partial mirror** (ADR-0005,
`../../decisions/0005-three-level-mirror.md`). The lower levels have a
generate/resolve pair driving a high-throughput flywheel; a thesis has no such
flywheel — there is *one* thesis, framed once and refined. So `framing` (the
degenerate generate) and `synthesis` (the resolve) are **one `thesis` skill**, not
two. The roll-up target is **narrative coverage of the aims**, never a paper count
(there is no universal N; the binding norm is scope). A **monograph** is the
degenerate case: one paper spanning the whole thesis.

## When to use

- **`framing` (occasional).** Establish or refine the thesis aims and narrative
  through-line, and decide *which* portfolio papers compose the thesis. Run this
  once early (a prospectus/proposal), then only when the scope shifts.
- **`synthesis` (the resolve).** Assemble the kappa framing chapter over the
  chosen papers, then clear the **defensibility** gate. Run as submission and
  defense approach.
- **Never**, for a repo that is not a thesis. The top level is optional; do not
  scaffold a `thesis/` folder unless the author is writing a doctoral thesis.

This skill does **not** create new scientific findings, adjudicate paper quality,
or aggregate across repositories (cross-repo aggregation is out of scope,
`../../docs/design/00-meta-spec.md` §1).

## Modes

### framing (occasional)

Define the **aims** — the small set of overarching questions/objectives the thesis
answers — and the **narrative through-line** that makes the papers read as one
project rather than a stapled stack. Then map which portfolio papers compose the
thesis and which aim(s) each supports.

- Lives in the thesis aims file (for illustration: `docs/research/thesis/aims.md`): the aims, the through-line, and the
  chapter↔paper map (aim → supporting paper-ids drawn from the papers registry).
- *Proposes and records the author's framing; it does not select papers on the
  author's behalf.* Which work belongs in the thesis is a scoping judgment the
  author makes and signs.
- Refined, not churned. Re-run when the program's scope genuinely shifts (a new
  aim, a paper dropped from scope), not per paper.

### synthesis (the resolve)

Assemble the **kappa** (see below) over the framed papers, then run the
**defensibility gate**. This mode reads the portfolio state and the aims, drafts
the framing chapter, surfaces coverage gaps, and stages the mock viva — the author
authors the prose and decides defensibility.

The full thesis-level staged progression spans **both** modes — the first three
are `framing` outputs, the last is this mode:
`prospectus → aims/narrative → chapter↔paper map → kappa + defensibility`.

## The kappa

The kappa (Swedish "overcoat") is the synthesizing framing chapter that turns a
stack of papers into one thesis. It is **more than concatenated introductions** and
**introduces no new findings** — it recontextualizes existing, already-resolved
work. Draft it in the thesis kappa directory (for illustration: `docs/research/thesis/kappa/`). Components (the artifact schema):

| Component | What it holds |
|---|---|
| Introduction / background | the problem space the aims sit in |
| Unifying narrative / aims | the through-line from `aims.md`; how the papers cohere |
| Independent related work | an **extensive** related-works synthesis at thesis scope — broader than any single paper's positioning; draw on `literature position --level thesis` |
| Per-paper summary + contribution statement | for each appended paper, a summary **and an explicit statement of the candidate's own contribution** to co-authored work |
| Unifying discussion | the comprehensive concluding discussion across all papers — the original contribution to knowledge |
| Future work | where the program goes next |

Then the **appended papers** themselves. The per-paper **contribution statement**
is load-bearing for co-authored papers (authorship/credit norms) and is the
author's to write — the skill drafts a scaffold, never asserts the split.

**Hard constraint: no new findings in the kappa.** If synthesis would require a
result the papers do not already establish, that is a hypothesis for
`hypothesis-testing` inside a paper, not kappa prose.

## Milestones

Program milestones are a small, **configurable, time-based** list in
the thesis milestones file (for illustration: `docs/research/thesis/milestones.yml`) — institution gates vary and are
deadline-driven, so they are never hard-coded. A typical progression:

```
proposal → candidacy → annual review → submission → defense
```

Track per milestone: `status` (not-started / scheduled / passed), `date`, and the
next binding deadline. These are calendar gates, distinct from the
coverage/defensibility state below — `progress` surfaces both. Milestones are
reported, never scored: an overdue milestone is a surfaced gap, not a penalty
(anti-Goodhart, `../../docs/design/00-meta-spec.md` §3.6).

## Defensibility gate

The thesis is **done** when it is *defensible*: every aim is covered by ≥1 paper
**and** the kappa states a coherent through-line + the original contribution. The
roll-up target is **narrative coverage of the aims** (does each aim have supporting
papers; is the through-line stated) — **not** a paper count, never a percentage or
average (`../../resources/references/thesis-and-progress-tracking.md`, Part A).

Defensibility is a **material human decision, recorded with a named human sign-off**
(`../../docs/design/00-meta-spec.md` §2.1; lifecycle §8). Before it is recorded,
the **`defend` skill runs a full MOCK VIVA** (`../defend/SKILL.md`;
`../../docs/design/01-lifecycle.md` §6) across all three targets
(`claim | cited-work | methodology`).

This gate is **non-blocking but escalated** (ADR-0021,
`../../decisions/0021-thesis-gate-per-gap-confirmation.md`). As the highest-stakes,
least-reversible decision, it replaces the single blanket override used at other
gates with **per-gap acknowledged sign-off**: the author must explicitly
acknowledge *each* surfaced gap in writing before proceeding.

- The AI **never** adjudicates a gap as "critical" and **never** hard-blocks — it
  surfaces gaps as observed facts; the human acknowledges each and decides.
- Waving a thesis through with known gaps is therefore deliberate and fully on
  record, per gap.

## Composition

- **Reads down** — the `papers.md` registry and each paper's `decision`/status
  frontmatter (which papers are done), and `portfolio-backlog.md`. It consumes
  resolved papers; it does not resolve them.
- **`literature position --level thesis`** — for the kappa's extensive independent
  related-works synthesis (thesis scope, unioned/deduplicated across every aim and
  paper, broader than a single paper's positioning).
- **`defend`** — the mock viva at the defensibility gate; also self-invokable on any
  aim or contribution statement.
- **`progress`** — reads the thesis status block in `aims.md` (readiness /
  defensibility + the aim list + `last-updated`) and rolls it into `dashboard.md`
  as a pure projection. Thesis status = uncovered-aims list + through-line-stated
  flag + milestone state, never a score.
- **The engineering backend** — thesis prose is authored, not engineered, so
  there is nothing to delegate at this level (unlike a paper's outline/plan).

## Guardrails

Hard rules, not preferences.

- **Optional top level.** Do not scaffold or invoke thesis for a non-thesis repo.
  Its absence is the normal case; the portfolio is the top.
- **No new findings.** The kappa recontextualizes resolved work only. Any needed
  new result routes back to `hypothesis-testing` within a paper.
- **Coverage, not count.** Report narrative coverage of the aims and the
  through-line; never a paper count, %-complete, or productivity score. No
  universal N — the binding norm is scope.
- **Author authors, skill drafts.** The aims, the scope (which papers compose the
  thesis), the per-paper contribution statements, and the defensibility judgment
  are the author's. The skill drafts scaffolds and surfaces gaps.
- **Defensibility is a signed human decision.** The mock viva must fire first; the
  gate is non-blocking with **per-gap acknowledged sign-off** (ADR-0021). The AI
  never grades a novel claim's substance or decides a gap is "critical."
- **No cross-repo aggregation.** Papers living in a separate repo are out of scope
  (`../../docs/design/00-meta-spec.md` §1); each repo's top level is self-contained.
  A possible future extension is sketched in
  `../../docs/design/proposals/cross-repo-thesis-aggregation.md`.

## Commit attribution

When you commit artifacts produced by this skill, add these git trailers —
discovery + provenance (see [`../../resources/commit-attribution.md`](../../resources/commit-attribution.md)):

```
Generated-with: defendable-science (https://github.com/davorrunje/defendable-science)
DefendableScience-Skill: thesis
```
