# `defend`: the examination you have to pass before you sign

A task-oriented guide to the guardrail that makes the *understanding* principle
mechanical. `defend` probes whether you can actually defend a claim, a citation,
or a method — Socratically, one question at a time — teaches when it finds a gap,
and records what happened as evidence.

If you have not met `defendable-science` yet, read the
[User Guide](../USER-GUIDE.md) first.

## 1. Two kinds of instruction, and how to tell them apart

- **The examination is a skill.** You *ask the assistant* for it, in prose, and it
  is a conversation. There is no `defendable-science defend claim <id>` command,
  and there cannot be — the whole thing is dialogue.
- **`defendable-science defend record` is a CLI**, with exactly one command. It
  writes the *outcome* of an examination into the artifact's frontmatter and
  appends the evidentiary record to the accountability log. The skill calls it for
  you at the end of a session.

> **Ask the assistant.** Examine me on the claim in
> `docs/research/aug-policy-robustness/hypotheses/2026-03-04-aug-ood/strategy.md`
> before I sign it — critical examiner, and push on the rival explanations.

```bash
# The CLI half: recording what the examination found.
defendable-science defend record \
    --artifact docs/research/.../strategy.md --target claim --signed-off-by "Your Name"
```

## 2. Two ways it fires

**Self-invoked, on demand.** Any time you want to rehearse — before a supervisor
meeting, before a submission, when you suspect you are hand-waving. This is the
cheap, no-stakes use, and it is the one most people under-use.

**Automatically, as a guardrail.** Before *every* material sign-off, `defend`
fires whether you asked for it or not: the strategy in `hypothesis-testing`, the
verdict in `findings.md`, the publish/no-go in `decision.md`, and — escalated to a
full mock viva — the defensibility gate in `thesis`.

The guardrail **surfaces gaps; it does not block you.** You may override and sign
anyway. But the override is logged, with the gap it overrode. That is the whole
design: the tool cannot and should not stop a researcher from making a call, but
it can make sure the call is on the record as having been made knowingly.

At the thesis gate the escalation is per-gap: you acknowledge *each* surfaced gap
in writing, not one blanket override.

## 3. Three targets, and what is off-limits in each

| Target | What it probes | What it may teach |
|---|---|---|
| `claim` | your own scientific claim — entailments, assumptions, rivals, falsifiers, limitations | *how to reason and defend*, only — **never the answer key** |
| `cited-work` | do the cited works actually support the claim; what each source really says | your citations plus the source texts |
| `methodology` | the *why* behind a rigor-kit choice, not the ritual | the methodology digests and authoritative references |

The asymmetry in that last column is the most important thing on this page.

`defend` **teaches established knowledge freely.** If you cannot say why a
paired test is appropriate here, or what a TOST bound is for, it will explain,
with sources, and then re-ask. That is not cheating; it is what a good supervisor
does.

`defend` **never supplies the answer key to your novel claim.** It will ask you
what would falsify your hypothesis. It will not tell you. It does not grade the
substance of your contribution — that is your science, and a tool that supplied
it would be making the contribution instead of you.

So a `claim` examination can feel harder than a `methodology` one, and that is
correct.

## 4. Mentor personas: chosen, never inferred

The examination voice has four settings, derived from supervision typologies
(Lee × Gatfield) — **not** from personality theory:

- **Sounding board** — high autonomy-support, exploratory. Early stage.
- **Critical examiner** — **the default**. Calibrated difficulty.
- **Directive editor** — concrete, process-level feedback. Deadline-driven.
- **Devil's advocate** — *opt-in*, time-boxed, explicit challenge to the argument.

Three levers pick one, all of them yours:

1. **You choose** (the default).
2. **The stage suggests** one — early draft → sounding board, near-submission →
   examiner — always overridable, and keyed to the *work*, never to you.
3. **Your feedback calibrates** it: "too harsh", "push harder".

**Inferring a persona from your personality is forbidden.** It is unsupported (the
learning-styles myth) and it is an agency violation — the tool does not get to
decide what kind of person you are. Autonomy-support is constant across all four;
only directiveness and challenge intensity vary. Feedback targets the argument and
the process, never you.

> **Ask the assistant.** Switch to devil's advocate for ten minutes on the
> positioning section — I want the strongest version of the objection a reviewer
> would raise.

## 5. What gets recorded, and why it is not a score

An examination ends in an **evidentiary point record** (ADR-0033), not a mark.
Per point: what was asked, what was observed, whether a gap remains. The
`status.understanding` block in the artifact's frontmatter carries the summary —
`{status, unresolved: [...]}` — and the full record is appended to
`docs/research/defend-log/`.

```bash
defendable-science defend record \
    --artifact docs/research/.../findings.md \
    --target claim \
    --points points.json \
    --signed-off-by "Your Name" \
    --transcript -
```

The flags that matter:

- `--points` — the point records, as a JSON array file or on stdin.
- `--override` with `--acks 'gap::name||gap::other'` — sign despite named gaps.
  Each gap is acknowledged individually; there is no way to wave at all of them
  at once.
- `--transcript` — the session transcript, file or stdin, so the record is
  auditable rather than a summary you have to trust.
- `--log-dir` — defaults to `docs/research/defend-log`.

**Records observed facts only — never a verdict, a score, or an answer key.** The
`understanding` block feeds the [`progress`](progress.md) roll-up as coverage and
named gaps, which is the only thing it is allowed to become.

## 6. `digest` is the same machinery, pointed inward

`defend` verifies you understand *your own* work before you sign it. Its inbound
counterpart, [`digest`](../../skills/digest/SKILL.md), verifies you understand a
paper *someone else* wrote before you cite it — same evidentiary record, via
`defend record --target paper-comprehension`.

That is why `progress status literature` can report "digested and understood"
versus "gaps unresolved" per paper, rather than a count of papers read.

## Where to go next

- [`skills/defend/SKILL.md`](../../skills/defend/SKILL.md) — the capability in the
  plugin's own words, including the worked methodology probe and the hard
  constraints.
- [`docs/guides/progress.md`](progress.md) — where the `understanding` block
  surfaces, and why it never becomes a number.
- [ADR-0033](../../decisions/0033-evidentiary-point-records.md) — why per-point
  records rather than a pass/fail.
- [`resources/references/mentor-personas.md`](../../resources/references/mentor-personas.md)
  — the supervision-typology sources behind the four personas.
