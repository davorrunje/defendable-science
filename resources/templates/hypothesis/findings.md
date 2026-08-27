---
status:
  level: hypothesis
  id: null                     # <YYYY-MM-DD-slug> — matches the hypothesis folder name
  verdict: null                # confirmed | refuted | inconclusive — refuted is a valid, done outcome
  readiness: resolved          # resolved once a signed verdict + evidence exist
  signed-off-by: null          # REQUIRED — named human; verdict is not real until set
  signed-off-date: null        # REQUIRED — date of sign-off
  evidence: []                 # run-refs backing the verdict — never hand-copied numbers
  covers: []
  load-bearing: null           # true | false — does refutation block the parent paper's claim?
  understanding: {status: ok, unresolved: []}     # from the `defend` guardrail before sign-off
  blockers: []
  last-updated: null           # <YYYY-MM-DD>
---

# Findings: <slug>

<!-- THE VERDICT — a material decision. Not real until `signed-off-by` +
     `signed-off-date` are set above. The `defend` guardrail fires BEFORE sign-off:
     it stops, surfaces any gap, offers to examine/teach, records; the human may
     override and the override is logged. A gap is never passed silently. -->

## Results

<!-- Reference the backend RUN-REFS that carry the evidence — never hand-copy
     numbers. Result tables/figures are written by the backend `tables` capability
     as managed, regenerable blocks. List every run-ref in `evidence` above. -->

- **Run-refs:** `run-ref://<...>`, `run-ref://<...>`
- <!-- tables-managed result block goes here; do not type numbers by hand -->

## Verdict

**`<confirmed | refuted | inconclusive>`**

<!-- Tie the verdict to the decision rule and severity argument in strategy.md.
     - confirmed: the decisive comparison met the pre-set rule with severity.
     - refuted: it did not — a successful, completed result. State what was learned.
     - inconclusive: underpowered / assumptions unmet; say what a decisive re-run needs. -->

*<Reasoning, referencing strategy.md's decision rule and the cited run-refs.>*

## Rigor closeout

<!-- Confirm the strategy's rigor commitments held through to results:
     confirmatory tag honored (no analysis changed after seeing outcomes), power/MDE
     met (or the null flagged uninformative), TOST bound cleared for any null claim,
     full disclosure of all runs incl. nulls, and the red-team pass repeated on the
     findings. -->

## Staleness

<!-- Before sign-off, check `is-current` on every cited run-ref. A stale run-ref is
     surfaced here; the human decides whether to re-run — the backend never does. -->

## Examination checkpoint + sign-off

<!-- Guardrail examination outcome (gaps surfaced / resolved / overridden-with-log), then
     the named human records the verdict by setting signed-off-by + signed-off-date
     above. -->
