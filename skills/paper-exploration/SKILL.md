---
name: paper-exploration
description: Use when deciding what paper to write next — mining finished or in-flight work for candidate application and follow-up papers, filling or grooming the portfolio backlog, or wiring a new paper into the project registry. Proposes candidate papers (never commits to writing one); the human promotes the pick to paper-synthesis.
---

Paper-exploration is the **generate** skill at the **portfolio level** — the
paper-level mirror of `hypothesis-exploration` one level down (see
`../../docs/design/00-meta-spec.md` §3.1 and `../hypothesis-exploration/SKILL.md`).
Where `hypothesis-exploration` proposes hypotheses into a paper's `backlog.md`,
paper-exploration proposes *candidate papers* — application spin-offs and
follow-ups — into the portfolio's `docs/research/portfolio-backlog.md`. A paper
starts as a one-line pitch here and, once the human promotes it, is handed to
`paper-synthesis` (the **resolve** skill) which drives it through
pitch → positioning → outline/plan → decision → sections (ADR-0006,
`../../decisions/0006-two-skills-per-level.md`).

The portfolio is the second of three nested loops: hypotheses accumulate into a
paper; papers accumulate into a portfolio; the portfolio (optionally) covers a
thesis's aims. The portfolio sits **under** the optional `thesis` level (see
`../thesis/SKILL.md`) — in a repo that is not a thesis, the portfolio *is* the
top. This skill **proposes only**; the human decides what gets written
(agency principle, `../../docs/design/00-meta-spec.md` §2.1).

## When to use

- A paper's hypotheses are resolving and you want to see what *next* papers the
  evidence, the mechanism, or the leftover limitations suggest.
- The portfolio backlog is empty, thin, or stale and needs a generation pass.
- A reviewer comment, a rival's result, or a new application domain lands and you
  want it parked as a candidate before it is lost.
- You want the backlog re-ranked by feasibility × interest, or a candidate
  promoted to `paper-synthesis` (or dropped).
- You are registering a newly promoted paper into `docs/research/papers.md`.

Do **not** use this skill to *develop* a paper (that is `paper-synthesis`), to
decide *whether to publish* (that is the `decision.md` gate inside
`paper-synthesis`), or to make any commitment on the author's behalf.

## Verbs

| Verb | Does | Firewall |
|---|---|---|
| `park` | Capture a raw paper idea as a backlog row with its origin, verbatim, before it is lost — no ranking, no judgment. | proposes |
| `generate` | Run the generation lenses (below), optionally seeded by `literature scout --level paper`, and emit ranked candidate rows into `portfolio-backlog.md`. | proposes |
| `rank` | (Re)score existing candidates by **feasibility × interest** and reorder; surface the current top of the backlog. | proposes |
| `promote` | Hand a chosen candidate to `paper-synthesis`: scaffold the paper root, seed `paper/pitch.md` from the backlog row, and register the paper in `papers.md`. **Requires the human's explicit pick.** | human disposes |
| `drop` | Retire a candidate (superseded, out of scope, done elsewhere) with a recorded reason; keeps the file-drawer honest rather than silently deleting. | proposes |

`park`, `generate`, `rank`, and `drop` never commit the author to writing a
paper. Only `promote` moves a candidate out of exploration, and only on an
explicit human pick — the exploration/resolution firewall
(`../../docs/design/00-meta-spec.md` §2.3).

> **Tooling.** Row append/transition is the shared `defendable-science backlog
> park|add|list|rank|promote|drop` CLI group
> (`defendable_science/exploration/backlog.py`, shared with `hypothesis-exploration`)
> — ensure via [`ensure-tooling`](../../resources/ensure-tooling.md),
> operating on `portfolio-backlog.md` at the paper level. `add` realizes the
> `generate` verb's row-append; `list` is a read-only inspection command. The
> `promote --scaffold --level paper --research-root <docs/research> --backend
> <name>` scaffolds the paper root and writes the `papers.md` registry row in the
> same call, reporting the created paths as JSON; `--backend` is required there
> because the plugin bundles no default. Scaffolding runs before the backlog is
> written, so a refused scaffold leaves the row `ranked` and retryable. The
> table's host document is preserved — a heading and prose around the table
> survive every verb, and columns your repo adds beyond the standard order are
> kept (left empty on new rows). By hand (if the CLI isn't available): edit the
> `portfolio-backlog.md` table directly, keeping the column order.

## Generation lenses

Three lenses turn *finished or in-flight work* into candidate papers. Each
emitted candidate names the lens it came from, so the backlog is auditable.

- **Mechanism-transfer** — take a mechanism that worked *here* and ask where else
  it applies. "The construction that gave monotonicity in domain A — does it
  transfer to domain B?" Application/spin-off papers. Cross-check novelty with
  `literature scout --level paper` before parking (someone may already have
  transferred it).
- **Limitation-driven** — read the *limitations / threats-to-validity / future
  work* of a resolved paper (and its refuted or inconclusive hypotheses) and turn
  each into a follow-up that removes the limitation. Refuted load-bearing
  hypotheses are especially fertile: the negative result often *is* the next
  paper.
- **Result-driven** — take a confirmed result and ask what *new question* it now
  makes askable — a scaling study, an ablation-as-its-own-paper, a
  head-to-head against a rival the result now beats, a new dataset the result
  unlocks.

Shaping heuristics (applied here, not by `scout`): gap-spotting vs.
problematization (Sandberg & Alvesson 2011 — prefer candidates that challenge an
assumption over those that merely fill a hole) and feasibility × interest
(Alon 2009). See `../../resources/references/citation-scouting.md` §5.

**Prioritization — feasibility × interest.** Score every candidate on two axes
and rank by their product:

- *Feasibility* — do we have (or can cheaply get) the data, backend, and compute?
  Does an existing bound backend already cover it? How many unresolved hypotheses
  stand between here and a submittable claim?
- *Interest* — venue fit, novelty vs. prior work, size of the audience, and
  whether it advances a thesis aim (if the portfolio sits under a `thesis`).

Neither axis is a productivity score; the product orders *proposals* the human
triages. A high-interest / low-feasibility candidate is parked, not discarded —
feasibility often changes.

### Seeding from `literature scout`

`generate` may call the `literature` skill in `scout` mode at
`--level paper` (recall-oriented: large citing set, skim metadata, co-citation
clustering + research-front / burst detection dominate — see
`../../docs/design/02-literature.md` §2 and
`../../resources/references/citation-scouting.md` §4). Scout returns ranked idea
rows, each carrying **mandatory provenance**
(`idea | type | source-paper id | citing-context snippet | why-it-matters | est. feasibility`).
A scout-seeded candidate keeps that provenance line so every parked paper traces
back to who-cited-what. Scout *proposes* leads; this skill folds them through the
lenses and the human triages — scout adjudicates nothing.

## The papers registry

Paper-exploration owns `docs/research/papers.md` — the portfolio's index of
paper roots and their experiment-backend binding.

- **What it holds.** One row per paper: `paper-id` → its root path under
  `docs/research/<paper>/` + a `backend:` field naming the bound experiment
  backend (**required — the plugin bundles no default**; each repo supplies its own
  implementation of the contract; ADR-0013,
  `../../decisions/0013-experiment-backend-contract.md`;
  `../../docs/design/04-substrate-and-contract.md` §3.1). Pipeline skills resolve
  the backend from this binding and contain no backend-specific logic, so
  `backend:` is set here at registration time.
- **When it is written.** `promote --scaffold` adds the registry row and
  scaffolds the paper root (`hypotheses/`, `backlog.md`, `paper/`); plain
  `promote` only flips the backlog row's status. The row is spliced into the
  registry table wherever that table sits, so `papers.md` can carry prose around
  it, and columns you add beyond `paper-id | root | backend` are preserved and
  left empty for you to fill. A candidate in
  `portfolio-backlog.md` is *not* in `papers.md` — the backlog is proposals; the
  registry is committed papers.
- **paper-id.** A stable, human-readable slug (kebab-case), assigned at promotion
  and never reused; it keys the paper across the backlog, the registry, the
  dashboard, and `progress`.

## Composition

- **Down-mirror:** `hypothesis-exploration` (`../hypothesis-exploration/SKILL.md`)
  is the same shape one level down — same verbs, same firewall, same
  proposes-only stance. Reading either explains the other.
- **Hand-off:** `promote` → `paper-synthesis` (`../paper-synthesis/SKILL.md`),
  which develops the promoted candidate to a publish/no-go `decision.md`.
- **Seeding:** `literature scout --level paper` (`../literature/SKILL.md`) feeds
  candidate rows; `defend`'s `cited-work` target later audits their citations.
- **Up-mirror:** the portfolio feeds the optional `thesis` level
  (`../thesis/SKILL.md`); when a `thesis` exists, *interest* scoring weighs
  coverage of a thesis aim.
- **Reporting:** `progress` (`../progress/SKILL.md`) reads the `papers.md` registry
  and each artifact's status frontmatter — not the `portfolio-backlog.md` table; it
  never re-ranks or scores.

## Guardrails

Hard rules — load-bearing, not preferences.

- **Proposes only; the human promotes.** Every verb but `promote` stays inside
  exploration. `promote` requires an explicit human pick and is the *only* path
  out. The skill never decides which paper to write, and *never* touches a
  `decision.md` publish verdict — that gate lives in `paper-synthesis` and is a
  material decision with a named human sign-off (`../../docs/design/00-meta-spec.md`
  §2.1, §2.3).
- **Firewall.** Exploration proposes; resolution (`paper-synthesis`) disposes;
  synthesis reports. This skill sits wholly on the *propose* side.
- **File-drawer discipline.** `drop` records a reason; candidates are retired, not
  silently deleted, so the exploration history stays auditable (rigor kit,
  `../../docs/design/01-lifecycle.md` §3).
- **Provenance is mandatory.** A scout-seeded candidate keeps its citing-context
  snippet + source-paper id. A hand-parked candidate records its origin (which
  result / limitation / mechanism it came from).
- **No scores.** Feasibility × interest orders *proposals*; it is not a
  productivity metric and never rolls up into one (anti-Goodhart,
  `../../docs/design/00-meta-spec.md` §3.6).
- **Domain-neutral.** No monotonic-network or ML assumptions live here; the lenses
  and the registry are generic. Domain content comes from the consuming repo.

## Commit attribution

When you commit artifacts produced by this skill, add these git trailers —
discovery + provenance (see [`../../resources/commit-attribution.md`](../../resources/commit-attribution.md)):

```
Generated-with: defendable-science (https://github.com/davorrunje/defendable-science)
DefendableScience-Skill: paper-exploration
```
