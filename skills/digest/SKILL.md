---
name: digest
description: Use when you want to read an external paper with verified comprehension — an interactive probe-teach-reprobe loop that builds and checks your understanding of a paper's problem, method, key result, assumptions, and limitations, then emits a grounded digest. Also offered as a deeper remediation path when defend's cited-work probe finds you can't explain what a citation actually says.
---

The `digest` skill is the **inbound** counterpart to `defend`: it verifies the
reader's grasp of *someone else's* paper, the way `defend` verifies the
author's grasp of their own decisions. It reuses `defend`'s probe → teach →
re-probe mechanic (`../../docs/design/00-meta-spec.md` §2.2, the Understanding
principle) in the opposite direction — the paper's content is *established*
external knowledge, so `digest` teaches it freely; it never grades whether the
paper's own claims are right. Grounding:
`../../resources/references/understanding-and-defense.md`,
`../../resources/references/mentor-personas.md`.

This is the reading step that precedes literature triage, positioning, and
citing. It composes with `literature` (the paper must be a registry entry,
grounded in a mirrored PDF) and shares its accountability-log mechanism with
`defend` (ADR-0033) — the same evidentiary `points` record, not a bare
pass/fail.

## When to use

- **Self-invoked.** You've picked a paper to read — off a `scout`-produced
  reading list, a citation you're about to add, or general background — and
  want your understanding of it built and checked, not just summarized at you.
- **Escalation from `defend --target cited-work`.** `defend`'s cited-work probe
  ("does ref [12] actually support this sentence?") surfaces a gap: you can't
  explain what the source says, or your citation misrepresents/overstates it.
  `defend` **offers** to hand off into a full `digest` session on that paper —
  deeper remediation than teaching the one sentence inline.

Do **not** use `digest` to grade the paper's own claims, or to decide whether
it's novel/worth citing — that's `literature`'s `position` mode and the
human's call (see Guardrails).

## How it works

The core is the same retrieval-practice loop as `defend`, run per load-bearing
point until it holds or you elect to stop and record the gap.

1. **Scope.** Resolve the paper against the `literature` registry
   (`references.json`) — `literature resolve` it if absent, then `literature
   fetch <citekey>` to acquire and record the PDF (cache → mirror → source
   chain, SHA-256). `literature verify <citekey>` re-checks the bytes offline
   on a later run. If `fetch` reports the paper in `manual[]` (the
   acquisition ladder found nothing), acquire it by hand and record it with
   `literature confirm <citekey> --file <path>`. This grounds the digest in a
   real registry entry + mirrored PDF, never a bare URL or an unmirrored
   link.
2. **Probe** one load-bearing point at a time, open-ended: the problem it
   addresses, the method, the key result, its assumptions, its limitations,
   and — when you already have a hypothesis or paper this reading relates to —
   how it bears on your own work. (Skip the last point if there's no bound
   context yet, e.g. early scouting before you've committed to a claim.)
3. **Detect gap.** Judge whether you can *articulate* the point — not whether
   your first answer was right. A gap is an observed inability to explain
   ("couldn't state the method's key assumption"), never a verdict on the
   paper's correctness.
4. **Teach**, source-grounded, from the paper itself. Established external
   content → explain freely and point at the exact section, equation, or
   table. (Contrast a *novel claim* under `defend`, which never gets its
   answer key supplied — a published paper's content isn't that.)
5. **Re-probe** (possibly reframed) until you can state the point in your own
   words, or you explicitly park it as an unresolved gap.
6. **Record** (see below) and, if warranted, update the paper's `triage.yml`
   row. On the **first digest** of a paper, create the digest artifact with
   a minimal seed frontmatter block (see Output artifact, below) before
   running `defend record`.

**Out of scope.** One `digest` run covers one paper — for a reading list, run
it once per paper. `digest` never adjudicates whether the paper's own claims
are correct, contested, or wrong; a reader's disagreement with the paper
surfaces as a flagged, unresolved point, never a verdict.

## Record — evidentiary, not a pass flag

Uses the same `defendable-science defend record` CLI as `defend` (ADR-0033),
target `paper-comprehension`:

```
defendable-science defend record \
  --artifact docs/research/literature/digests/smith2024.md \
  --target paper-comprehension \
  --points points.json
```

`points.json` is a JSON array, one entry per probed load-bearing point:

```json
[
  {
    "point": "assumptions",
    "source_quote": "We assume the loss is Lipschitz-continuous (Eq. 3).",
    "location": "§3, Eq. 3",
    "reader_answer": "They need the loss to not change too fast so the bound in Thm 1 holds.",
    "resolved": true
  },
  {
    "point": "limitations",
    "source_quote": "Our analysis does not cover the non-convex case.",
    "location": "§5, final paragraph",
    "reader_answer": "Not sure why non-convexity breaks it.",
    "resolved": false,
    "gap_note": "could not explain why non-convexity breaks the analysis"
  }
]
```

This patches `status.understanding` in the digest's frontmatter — the same
`{status: ok|gaps, unresolved: [...]}` shape `progress` already reads — and
appends the full per-point record (source quote + your actual answer, for
every point, not just the failed ones) to the accountability log
(`docs/research/defend-log/`). The frontmatter stays small; the log is where
the evidence lives, independently checkable later without re-running the
session.

## Output artifact

`docs/research/literature/digests/<citekey>.md` — one file per digested
source paper, named by citekey so it joins trivially with
`references.json`/`triage.yml`. Git-tracked, citeable.

- **Frontmatter**: a `status:` block carrying `understanding` +
  `last-updated`. The block must be seeded before the Record step runs
  (not already patched by `defend record`). Minimal seed:
  ```yaml
  ---
  status:
    understanding: {status: pending, unresolved: []}
    last-updated: YYYY-MM-DD
  ---
  ```
- **Body**: faithful summary; key equations/claims; assumptions; limitations;
  and, when applicable, an explicit "relation to my work" section.

**Triage update.** On completion, update the paper's `triage.yml` row —
`notes` and a `seeded` link back to the digest, `disposition` advanced if
warranted. This is a direct edit to the YAML (there is no CLI for
`triage.yml` today; `literature`'s CLI only exposes the graph primitives),
consistent with current practice.

## Composition

- **`literature`** is the substrate: `digest` resolves/grounds the paper
  against `references.json` and the mirrored PDF, and writes back to
  `triage.yml` on completion.
- **`defend`** shares the engine and the record mechanism (ADR-0033); its
  `cited-work` target escalates into `digest` on a comprehension gap (see
  When to use).
- **`progress`** surfaces digested-vs-unresolved counts from
  `docs/research/literature/digests/*.md` frontmatter as an independent
  "literature reading" view (`../progress/SKILL.md`), alongside — not folded
  into — the hypothesis/paper/thesis roll-ups.

## Mentor persona

Reuses `defend`'s persona framework and its three author-controllable levers
(self-selected / stage-suggested / feedback-calibrated — never inferred from
personality; `../../resources/references/mentor-personas.md`). **Default:
sounding board** — `digest` is a first-read/tutoring context, not a decision
defense, so the default leans exploratory rather than `defend`'s
critical-examiner default.

## Guardrails

Load-bearing rules, not preferences — mirrors `defend`'s stance in the inbound
direction.

- **Ask, don't grade the paper's substance.** Report observed facts ("couldn't
  state the key assumption"), never "this paper is wrong" — that's outside
  this skill's authority and outside its job. A reader's disagreement with the
  paper is recorded as an unresolved point, not adjudicated.
- **Teach the paper freely, source-grounded.** Its content is established
  external knowledge (unlike a novel claim under `defend`) — explain and
  quote it directly, point at the exact section/equation.
- **Verified, never self-attested.** `understanding.status: ok` only when the
  reader has demonstrated each load-bearing point against the probe — no
  "I've got it" shortcut (anti-Goodhart, same as `defend`).
- **Propose/surface, never adjudicate novelty or inclusion.** Whether a paper
  is worth citing, novel, or in-scope stays with `literature position` and the
  human's sign-off. `digest` feeds that judgment; it doesn't make it.
- **Non-blocking.** The `cited-work` escalation is stop/offer, never a hard
  block — the human can decline and proceed, same as `defend`'s guardrail
  semantics.

## Commit attribution

When you commit artifacts produced by this skill, add these git trailers —
discovery + provenance (see [`../../resources/commit-attribution.md`](../../resources/commit-attribution.md)):

```
Generated-with: defendable-science (https://github.com/davorrunje/defendable-science)
DefendableScience-Skill: digest
```
