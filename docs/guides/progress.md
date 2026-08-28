# `progress`: coverage and blockers, and deliberately no score

A task-oriented guide to the reporting side of `defendable-science`. `progress`
reads the status frontmatter every other skill writes and tells you where the work
actually stands — what is covered, what is blocked, what has gone stale. It will
never tell you that you are 73% done, and this page explains why that is a feature.

If you have not met `defendable-science` yet, read the
[User Guide](../USER-GUIDE.md) first.

## 1. `status` is a reading; `dashboard` is a command

`status` is a thing you **ask the assistant for**: there is no CLI verb for it,
because the roll-up is a semantic reading of frontmatter, which is agent work.

> **Ask the assistant.** Where do all our hypotheses stand (`progress` in
> `status hypothesis` mode)? Call out anything blocked or stale.

`dashboard` is not. It is a real command —
`defendable-science progress dashboard` — and it is the **only** writer of
`docs/research/dashboard.md`. The assistant runs it and relays what it wrote; it
does not compose the file, because two projections that can disagree is exactly
what the generated banner exists to prevent.

> **Ask the assistant.** Regenerate the dashboard (`progress` in `dashboard`
> mode).

The dashboard is a **pure projection** of status frontmatter, and it is
machine-owned — **never hand-edit it**, because the next regeneration silently
discards whatever you typed. If something in the dashboard is wrong, the
frontmatter it projects is wrong; fix that. There is no timestamp in the file,
so re-running on an unchanged repo produces a byte-identical file and leaves
your `git status` clean — which is what lets `defendable-science check` tell a
stale dashboard from a current one.

## 2. Four roll-ups

`status <level> [id]` reads one artifact when given an id, or every artifact at a
level when not. Levels: `hypothesis`, `paper`, `thesis`, `literature`.

**hypothesis → paper.** Done means "all constituent hypotheses *resolved* AND the
claim is written." A single **refuted `load-bearing: true`** hypothesis is a
**blocker** on its paper — it invalidates the claim no matter how many siblings
resolved cleanly. So the report reads:

```
covered: 4/5 resolved; BLOCKED by aug-ood-transfer (load-bearing, refuted)
```

and not `80%`. An average would hide exactly the one thing you need to know.

**paper → thesis.** Done means "all aims covered by ≥1 paper AND the kappa states
the through-line." The roll-up is **uncovered aims** plus **through-line stated?**
— the two things an examiner actually checks. Paper *count* is never the target;
there is no universal N, and the binding norm is scope.

**literature.** Independent of the hierarchy above: it reads the `understanding`
block in `docs/research/literature/digests/*.md` — written by
[`digest`](../../skills/digest/SKILL.md) via `defend record --target
paper-comprehension` — and reports, per digested paper, `{digested & understood /
gaps unresolved}`, joined against `triage.yml` by citekey for role and
disposition. Not a count of "papers read".

**staleness is orthogonal.** An artifact whose evidence the backend reports as
not-current (`is-current`, see [the experiment-backend
guide](experiment-backend.md)) is flagged stale regardless of its verdict.
`progress` surfaces it; **you** decide whether to re-run.

The output shape is the same everywhere: `{covered / total by state}` +
`{explicit blockers}` + `{stale?}`. No rolled-up number leaves this skill.

## 3. Two readings that catch people out

**A refuted hypothesis reads as done and green.** Verdict and readiness are
distinct axes, and refutation is successful science. A dashboard that showed
refuted work in red would be punishing honest negative results — a modelling
error, and one that quietly incentivises not looking too hard.

**A resolved hypothesis can still block its paper.** See the load-bearing rule
above. "All my hypotheses are resolved" and "my paper is unblocked" are different
statements.

## 4. Why there is no progress number

This is a hard design invariant (ADR-0014), documented so it cannot later be
"improved" into a score by someone who thinks it is a missing feature.

A self-tracking research tool is *especially* Goodhart-prone, because the same
person sets and games the metric. So `progress` surfaces state, gaps and
staleness — open hypotheses, uncovered aims, stale evidence, unresolved
understanding gaps — and never a single number.

It does **not** count or compute: word counts, paper counts, citation or impact
proxies, commit counts, %-complete on unresolved work, or a hypothesis "success
rate."

The grounding is cited so it stays honest: Goodhart's law and Campbell's law (a
measure that becomes a target stops measuring), and the DORA (2012) / Leiden
Manifesto (Hicks & Wouters et al., 2015) principle that metrics *support* rather
than *replace* qualitative judgement. See
[`resources/references/thesis-and-progress-tracking.md`](../../resources/references/thesis-and-progress-tracking.md)
Part B.

If you want a number for a supervisor meeting, the honest answer is the coverage
line plus the blockers — which is more informative than a percentage anyway, and
takes the same breath to say.

## 5. Keeping the frontmatter true

`progress` is only as good as what it reads, and it reads what the other skills
wrote. Two habits keep it accurate:

- **Never hand-edit `dashboard.md`.** It is generated by
  `defendable-science progress dashboard`. Fix the source frontmatter and
  regenerate; `defendable-science check` flags a dashboard whose artifact set
  no longer matches what is on disk.
- **A verdict is real only once `signed-off-by` + `signed-off-date` are set.** An
  unsigned `findings.md` with a verdict typed in is not resolved, and `progress`
  is right to report it as open.

> **Ask the assistant.** Read the status frontmatter across
> `docs/research/aug-policy-robustness` and tell me which hypotheses are
> unsigned, which are stale, and which single one is blocking the paper.

## Where to go next

- [`skills/progress/SKILL.md`](../../skills/progress/SKILL.md) — the capability in
  the plugin's own words, including the full status-frontmatter schema.
- [ADR-0014](../../decisions/0014-progress-cross-cutting.md) — the anti-Goodhart
  decision and the alternatives rejected.
- [`docs/guides/defend.md`](defend.md) — where the `understanding` block comes
  from.
- [`docs/design/01-lifecycle.md`](../design/01-lifecycle.md) §5 — status in
  frontmatter, and the dashboard as a pure projection.
