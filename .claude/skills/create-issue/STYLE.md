# Issue Style

The standard format for issues on `davorrunje/defendable-science`. Every issue is
**self-contained**: completable from the repository content plus the issue text
alone.

## Title

`<area>: <concise imperative>`

- `<area>` mirrors this repo's commit-scope vocabulary: `docs`, `ci`, `build`,
  `skills`, `core`, `literature`, `dataset`, `defend`, `backlog`, `plugin`,
  `dx`, `test`. (`skills` = the shipped plugin skills under `skills/`; `dx` =
  maintainer tooling like `.claude/skills/`.)
- Imperative and specific: `dataset: harden non-numeric size/year decoding`, not
  `dataset bug`.
- No trailing period.

## Body

Use these sections, in this order. Omit a section only when it genuinely does not
apply (keep **Context**, **Goal**, **Where**, and **Acceptance criteria** always).

```markdown
## Context

Why this exists and where it came from, for someone with no prior context: one
short paragraph of background, then the trigger — link the spec, ADR, docs page,
merged PR, or commit that deferred it (by number/path, e.g. #40,
`docs/design/00-meta-spec.md`, ADR-0026). State what currently happens.

## Goal

What "done" looks like, in one or two sentences.

## Where

The exact repository anchors: file paths, function/class names, line references
where the work lands or where the relevant code lives. Prefer
`defendable-science/defendable_science/literature/graph.py:resolve` — clickable and
stable across line drift. (Remember the package dir is `defendable-science/` and the
module is `defendable_science/`.)

## Proposed approach   (optional)

A sketch of how, if there's a sensible one — enough to save rediscovery without
over-prescribing. Note trade-offs or a cheaper/costlier variant if relevant.
Split "core (this milestone)" vs "follow-up" here when scope is layered.

## Acceptance criteria

A checklist of verifiable conditions:

- [ ] concrete, testable outcomes
- [ ] tests added and the 100% coverage gate held, where package code is touched
- [ ] any command to reproduce or verify

## References

Committed artifacts: spec/ADR/docs paths, PR/issue numbers, relevant commits.
```

## Labels & milestone

Labels are optional (the repo leans on milestones). Add a type label when it
clarifies (`bug`, `enhancement`, `documentation`) — check `gh label list` first.
Set the **milestone** when the work is release-relevant (e.g.
`v0.1.0 — first final`); leave it off for post-release / future-direction work.

## Closing convention

A closed issue records **how** it was resolved (see SKILL.md § Closing):

- Resolved by a merged PR → the PR body's `Closes #NN` closes and links it
  (nothing else needed). This is the mirror of the [`create-pr`](../create-pr/STYLE.md)
  standard — keep the two in sync.
- Resolved otherwise, or superseded → `gh issue close <N> --comment "Resolved in
  <ref> — <one line>."` (add `--reason "not planned"` for won't-do/superseded).
- Never close silently; never close a checklist/umbrella issue with open,
  un-re-filed boxes.

## Self-containment check

Before creating, confirm every answer is "yes":

- Could someone who never saw this session start the work from the issue + a
  fresh clone?
- Does every reference point at **committed** content (paths, symbols, merged
  PRs) — nothing ephemeral ("the branch we were on", "the run earlier", "as
  discussed")?
- Are the file/function anchors named explicitly, not gestured at?
- Are the acceptance criteria verifiable without insider knowledge?

If any is "no", the issue is not ready — add the missing context.

## Scope

One deliverable per issue. Split multi-part follow-ups into separate issues that
can each be completed and closed independently.
