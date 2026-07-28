# Proposal: `defend record` — a helper to persist understanding status + the accountability trail

`Status: implemented (designed 2026-07-18) · Skill: defend`

## Context

The `defend` skill's record step (SKILL.md step 6) currently has no tooling. Its
§ *Tooling* note (`../../../skills/defend/SKILL.md`) marks it unimplemented.
**Interim (until the module is implemented):** the skill
orchestrates the write by hand — editing the target artifact's frontmatter to add an
`understanding` block, and (if a transcript is kept) dropping it beside the artifact
as `defend-<date>.md`; once `defendable-science` is installed (via
[`ensure-tooling`](../../../resources/ensure-tooling.md)) the skill calls
`defendable-science defend record …` instead. Two problems with the manual path:

- **Drift-prone frontmatter.** `progress` rolls up the `understanding` field
  (`../../../skills/progress/SKILL.md`, "Status frontmatter"); a hand-edited block
  that doesn't match the schema silently breaks the roll-up.
- **No durable accountability trail.** The guardrail semantics require logged
  overrides, and the thesis gate (ADR-0021,
  `../../../decisions/0021-thesis-gate-per-gap-confirmation.md`) requires a
  *per-gap acknowledged sign-off*. Today those exist only in the conversation.

The lifecycle (§7, `../01-lifecycle.md`) already names the artifact "examination
transcripts + logged overrides form the accountability trail" — but nothing writes
it consistently.

## Goal

A single small module, `defendable_science/defend/record.py` (exposed as
`defendable-science defend record`), that a `defend` session invokes at step 6 to
(a) append/update the `understanding` status block in a target artifact's markdown
**frontmatter** so `progress` can roll it up, and (b) append the transcript plus
any logged overrides / per-gap acknowledgements to an accountability log. It
records **observed facts**, never a substantive verdict.

## Design sketch

**Inputs** (CLI args / a small call struct):

- `--artifact <path>` — the target markdown artifact whose frontmatter is written.
- `--target <claim|cited-work|methodology>` — the examination target type (SKILL.md
  "Targets").
- `--gaps` — the surfaced gaps, each an *observed fact* string ("no answer to the
  falsification probe"), not a judgement.
- `--status <ok|gaps>` — derived: `ok` when no unresolved gaps remain, else `gaps`.
- `--override` / `--ack <gap-id>` — a blanket logged override, or (thesis gate) one
  acknowledgement per surfaced gap, each with the acknowledging human's name.
- `--transcript <path|->` — optional transcript to persist.
- `--signed-off-by` — named human for any override/ack (agency, meta-spec §2.1).

**Frontmatter it writes** — exactly the `progress` schema
(`../../../skills/progress/SKILL.md`, "Status frontmatter"):

```yaml
status:
  understanding: {status: ok, unresolved: []}   # written by the `defend` skill; surfaced, never scored
```

- `status ∈ {ok, gaps}`; `unresolved` is the list of still-open gap facts (empty
  when `ok`). The helper only ever touches `status.understanding` — it must not
  write `verdict`, `readiness`, `signed-off-*`, or any other field (those belong to
  the resolve skills / human sign-off). It reads the existing frontmatter, merges
  the one sub-key, and writes back, preserving key order and the rest of the doc.

**Log location / format.** Append-only, versioned in git under the consumer
`docs/research/` tree (lifecycle §7). Proposed: `docs/research/defend-log/` with one
entry per examination, and the full transcript beside the artifact as `defend-<date>.md`
(matching the interim convention). Each log entry is a small YAML/markdown record:

```yaml
- date: 2026-07-18
  artifact: hypotheses/2026-07-17-monotone-depth/findings.md
  target: claim
  gaps: ["no answer to the falsification probe"]
  outcome: overridden          # resolved | overridden | acknowledged-per-gap
  acknowledgements:            # thesis gate (ADR-0021): one per surfaced gap
    - gap: "no answer to the falsification probe"
      by: "D. Runje"
  signed-off-by: "D. Runje"
  transcript: defend-2026-07-18.md
```

**Invariants (load-bearing, from SKILL.md "Guardrails"):**

- **Ask, don't grade.** Every recorded gap is phrased as an observed inability to
  explain ("unanswered probe"), never "wrong about X". The helper takes gap text
  verbatim from the caller and does no substance evaluation.
- **Never assert a novel claim's answer key.** The helper stores no "correct
  answer" field; there is nowhere in the schema to put one.
- **Never fabricate a verdict.** It writes only `understanding` (status + gaps); it
  never sets or infers `verdict`/`decision`/`defensible`, and never computes a
  score, percentage, or pass/fail (anti-Goodhart, both skills).
- **Non-blocking.** It records outcomes including override/ack; it never decides a
  gap is "critical" and never blocks.

## Dependencies & posture

- **Light-dep:** `pyyaml` + Python stdlib only. No new heavy dependency; frontmatter
  parse/emit via `yaml.safe_load` / `yaml.safe_dump` on the `---`-delimited block.
- **Idempotent:** re-running on the same artifact updates the single
  `understanding` sub-key in place rather than duplicating it.
- **Read-mostly on the artifact:** only `status.understanding` is mutated; body and
  other frontmatter round-trip untouched.
- Consumes/produces plain git-versioned markdown; no runtime state, no network.

## Open questions

- **Log granularity:** one growing file (`defend-log.md`) vs. per-entry files under
  `defend-log/`? Per-entry avoids merge conflicts across parallel sessions.
- **Gap identity for ADR-0021 acks:** free-text match, or does the helper assign a
  stable `gap-id` so an acknowledgement provably binds to a surfaced gap?
- **`status` vocabulary:** is `{ok, gaps}` enough, or is a third value
  (`overridden`) needed in the frontmatter so `progress` can surface "gaps waved
  through"? Leaning toward keeping frontmatter minimal and putting `outcome` only in
  the log.
- **Transcript redaction:** transcripts may quote sources/citations — any policy
  before they land in git?

## Acceptance criteria

- Writing a `status.understanding` block to a fixture artifact yields frontmatter
  that matches the `progress` schema exactly and round-trips the rest of the doc
  byte-for-byte (except the one sub-key).
- `progress status` rolls up the written `understanding` field without error.
- An override and a per-gap acknowledgement each append a well-formed log entry with
  the named human; nothing is recorded without a `signed-off-by` when an
  override/ack is present.
- The helper has no field for and never writes a verdict, decision, score, or a
  claim's answer; a test asserts these keys are never emitted.
- Re-running is idempotent (no duplicated `understanding` block).
- `pyyaml` + stdlib only; unit-tested; no network access.

## Links

- `defend` skill (record step + § *Tooling*): `../../../skills/defend/SKILL.md`
- Progress skill (frontmatter schema, `understanding`): `../../../skills/progress/SKILL.md`
- Understanding & defense digest: `../../../resources/references/understanding-and-defense.md`
- ADR-0021 thesis gate per-gap confirmation: `../../../decisions/0021-thesis-gate-per-gap-confirmation.md`
- ADR-0015 defend cross-cutting (logged override): `../../../decisions/0015-defend-cross-cutting.md`
- Lifecycle §7 (accountability trail): `../01-lifecycle.md`
- Meta-spec §2.1/§2.2 (agency + understanding): `../00-meta-spec.md`
