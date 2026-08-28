---
name: paper-synthesis
description: Use when developing a committed paper from its constituent hypotheses toward a publish/no-go decision and a submitted manuscript — situating it against prior work, structuring it, and assembling its sections from evidence. Drives one paper through staged documents (pitch → positioning → outline/plan → decision → sections) to a human-signed publish decision, assembling claims from a Toulmin-sextet ledger that cites experiment-backend run-refs. Drafts proposals; the author authors and decides.
---

Paper-synthesis is the **resolve** skill at the **paper** level: it drives one
committed paper from its accumulated hypothesis evidence, through a defensible
position against prior work, to a **publish / no-go** decision and an assembled
manuscript. It is the exact mirror, one level up, of `hypothesis-testing`
(`../hypothesis-testing/SKILL.md`): where that skill takes a hypothesis to a
`findings` verdict, this one takes a paper to a `decision` verdict, and the same
firewall holds — the skill drafts, keeps the accounts, and advises; the **author
authors and decides** (see `../../docs/design/00-meta-spec.md` §2.1). You cannot
"run" this skill to produce a paper; you drive it.

## When to use

- After a paper has been **promoted** from `portfolio-backlog.md` (by
  `paper-exploration`, `../paper-exploration/SKILL.md`) and registered in
  the papers registry (resolved from the repo's layout) — it is a committed deliverable, not a candidate.
- When its constituent hypotheses have accumulated enough evidence
  (`findings.md` verdicts, backed by run-refs) that a **publish decision** is in
  reach, or to develop the manuscript incrementally as they resolve.
- **Not** for generating paper ideas — that is `paper-exploration` (generate
  proposes; resolve disposes). Do not use this skill to adjudicate a hypothesis;
  that is `hypothesis-testing` one level down.

## Staged documents

All staged docs live in the paper's staged-documents directory (resolved from the repo's layout)
(`../../docs/design/00-meta-spec.md` §5). Each carries a status frontmatter block
feeding the `progress` roll-up (`../progress/SKILL.md`). The pipeline, in order:

| Stage | File | What it is | Analog in `hypothesis-testing` |
|---|---|---|---|
| pitch | `pitch.md` | the paper's thesis, contribution, and target venue — the committed framing carried over from the backlog | `hypothesis.md` |
| positioning | `positioning.md` | related-works synthesis: where this paper sits and what its delta is | `strategy.md` |
| outline / plan | `outline.md` / `plan.md` | the manuscript **structure** — engineering, **delegated to the bound engineering backend** | `design.md` / `plan.md` |
| decision | `decision.md` | the **publish / no-go verdict** — a material decision with a named human sign-off | `findings.md` verdict |
| sections | `sections/` + `ledger.md` | the drafted manuscript, assembled from a claim→evidence ledger | (the paper *is* the roll-up of findings) |

The stages are a **flow, not a gate sequence you can automate through**: each is
a document the author fills, drafted as a proposal by the skill. Positioning may
be revisited as hypotheses resolve; the decision is gated on the whole.

## How it works

1. **Pitch.** Carry the promoted backlog row into `pitch.md`: the central claim,
   the intended contribution, the target venue and its bar. Confirm which
   hypotheses (resolved from the repo's layout) are load-bearing for this
   paper.
2. **Positioning.** Invoke `literature position --level paper`
   (`../literature/SKILL.md`, `../../docs/design/02-literature.md` §3) to produce
   `positioning.md`. At paper level this is the full treatment, not the
   hypothesis-level rapid review: a **taxonomy** of the field, a
   **concept-centric matrix** (rows = methods, cols = the attributes the paper's
   delta turns on), a **PRISMA-style include/exclude log** (the
   anti-cherry-picking audit trail, sourced from the triage sidecar), a
   **per-branch delta** paragraph, and a derived **baseline list** (one strong
   tuned representative per branch + current SOTA + the most-likely-cited-against
   + a simplest floor). The closest-prior-work paragraph and the isolating
   ablation guard against overclaimed novelty.
3. **Outline / plan — delegated.** Structuring the manuscript is **engineering**,
   so hand it to the engineering backend bound in `.defendable-science/config.yml`
   (`engineering_backend:`) — its `design` → `plan` capabilities — exactly as
   `hypothesis-testing` delegates `design.md`/`plan.md`.
   Store the resulting
   `outline.md` / `plan.md` in the paper's staged-documents directory (resolved from the repo's layout). This skill owns
   the *scientific* framing; it does not reimplement engineering planning.
4. **Decision.** When the evidence and positioning are in, draft `decision.md` as
   a **publish / no-go** proposal: does the accumulated hypothesis evidence
   support the contribution the pitch claims, and does the positioning show a
   defensible delta? This is a **material decision** — see Guardrails. The skill
   marshals the evidence and recommends; the author decides and signs.
5. **Sections.** Assemble `sections/` from the claim→evidence ledger (below).
   Draft prose as proposals; every reported number is written by the backend
   `tables` capability, never typed by hand.
6. **Disclose (finalize, publish only).** Once the decision is **publish** *and* the
   sections are assembled, **proactively propose** an *AI-use disclosure* + a
   citation for the manuscript's *Use of AI* / Acknowledgments — drafted **from the
   provenance record** (who signed off which decisions, which `run-ref`s back which
   results, what the skills drafted), so it is truthful, not boilerplate. This is
   opt-in and author-owned: the author edits, adopts, or declines; never
   auto-insert. Surfacing it here — automatically, at the moment it matters — is
   deliberate (see [`../../DISCLOSURE.md`](../../DISCLOSURE.md), ADR-0025). Keep it
   humble: it discloses what was done and links the record; it does **not** certify
   honesty. On a **no-go** decision there is nothing to disclose — the paper is not
   submitted — so this step is skipped.

## The claim→evidence ledger

The claim→evidence ledger (for illustration: `<paper>/paper/ledger.md`) is the backbone of the manuscript: each
row is one paper-level claim recorded as a **Toulmin sextet**, so that every
assertion the paper makes is traceable to the evidence and its limits are
explicit. The six fields:

| Field | The question it answers |
|---|---|
| **claim** | what the paper asserts |
| **grounds** | the evidence for it — **experiment-backend run-refs** (never hand-copied numbers) |
| **warrant** | why the grounds support the claim (the inferential bridge) |
| **backing** | what justifies the warrant — prior work (cited via the literature registry), theory, or method |
| **qualifier** | the strength / scope of the claim ("on tabular benchmarks," "under matched tuning") |
| **rebuttal** | the conditions under which it would fail — threats to validity, the standing counter-argument |

Rules for the ledger:

- **Grounds cite run-refs, not numbers.** A run-ref is the citable unit of
  evidence from the experiment-backend contract
  (`../../docs/design/04-substrate-and-contract.md` §3). The backend `tables`
  capability is the **only writer of result numbers** into `sections/` — it
  renders managed, regenerable result blocks from the run-refs a claim cites.
  Hand-copied numbers are forbidden: they cannot be re-verified and break when
  evidence is re-run.
- **Every load-bearing claim must resolve to grounds** that resolve to exact
  bytes via the provenance stamp (config hash, code/symbol provenance, dataset
  `id+version+sha256`). A claim with no run-ref backing is a claim with no
  evidence.
- **Staleness is honest.** Before the decision and before assembly, check
  `is-current` on the cited run-refs; a stale run-ref surfaces the gap but the
  human decides whether to re-run (the backend never decides for you).
- **Backing draws on the literature registry** so the `defend cited-work` target
  can verify that a cited source actually supports the sentence it backs.

A worked row (domain-neutral shape):

> **claim** Method M improves the primary metric over the strongest baseline.
> **grounds** run-refs `rr-a91f` (M) and `rr-7c02` (baseline), matched split/seed.
> **warrant** paired improvement under matched conditions isolates the method as
> the cause. **backing** the matched-tuning protocol from `positioning.md`'s
> baseline list; comparison discipline per `[Webster & Watson]`. **qualifier**
> holds on the two in-distribution benchmarks tested, not out-of-distribution.
> **rebuttal** fails if the baseline was under-tuned — hence the isolating
> ablation and the shared tuning budget recorded in the provenance stamp.

Every number in the assembled section for this claim is rendered by `tables`
from `rr-a91f` / `rr-7c02`; the author never types them.

## Composition

- **Feeds from:** `paper-exploration` (the promoted pitch) and the paper's
  resolved hypotheses (`hypothesis-testing` `findings.md` verdicts + their
  run-refs).
- **Calls:** `literature position --level paper` for `positioning.md`; the
  engineering backend bound in `.defendable-science/config.yml` (`engineering_backend:`)
  for `outline.md`/`plan.md`; and the experiment backend (from the paper's `backend:` field in the papers registry, resolved from the repo's layout) — `tables` / `evidence` / `is-current` —
  for result blocks and staleness.
- **Examined by:** `defend` (`../defend/SKILL.md`), whose `paper-synthesis` preset
  targets **positioning** (novelty vs. prior work) and **cited-work** (do the
  cited sources support the claims), plus the **claim** target over the ledger.
  The guardrail fires automatically before the `decision.md` sign-off.
- **Reported by:** `progress` (`../progress/SKILL.md`), which reads the decision
  and section frontmatter; a paper is **done** when its hypotheses are resolved
  *and* it is submission-ready. A no-go decision reads as **done**, not failed —
  verdict and readiness are distinct axes.
- **Feeds up to:** the `thesis` level, where a paper becomes a chapter mapped to
  the aims (`../thesis/SKILL.md`).

## Guardrails

Hard rules — the load-bearing constraints, not preferences.

- **Drafting is assistive; the author authors.** The skill drafts pitch,
  positioning, ledger rows, and section prose as **proposals**. The scientific
  claims and their wording are the author's. Anywhere a scientific judgement is
  required, stop and ask rather than deciding (`../../docs/design/00-meta-spec.md`
  §2.1). You cannot produce a paper by "running" this skill.
- **The publish decision is material and human-signed.** `decision.md` names its
  human decision-maker and date; it is gated on accumulated hypothesis evidence +
  positioning, the paper-level mirror of a `findings` verdict
  (`../../docs/design/01-lifecycle.md` §8). The **`defend` guardrail fires before
  the sign-off** (positioning + cited-work + claim): it stops, surfaces gaps,
  offers to examine/teach, and records. The human may override; the override is
  logged — a stop-and-confirm, **not a hard block**. The AI never adjudicates
  publish-worthiness.
- **Numbers come from the backend, always.** Only `tables` writes result blocks
  into `sections/`; the ledger cites run-refs. If a number cannot be traced to a
  run-ref, it does not go in the paper.
- **Understanding gates the claims.** The author must be able to defend the
  positioning's novelty argument and each ledger claim to a reviewer's standard;
  unmet, `defend` surfaces it (`../../docs/design/00-meta-spec.md` §2.2).
- **Firewall.** Explore proposes, resolve disposes, synthesize reports. This
  skill develops and assembles a committed paper; it does not generate paper
  ideas and does not adjudicate its own decision.
- **Follow-ups become issues, not TODOs** — a deferred check or a known gap in the
  record is captured as a self-contained GitHub issue, not left in a doc's margin.

## Commit attribution

When you commit artifacts produced by this skill, add these git trailers —
discovery + provenance (see [`../../resources/commit-attribution.md`](../../resources/commit-attribution.md)):

```
Generated-with: defendable-science (https://github.com/davorrunje/defendable-science)
DefendableScience-Skill: paper-synthesis
```
