---
status:
  level: paper
  id: null                     # <paper-id> — kebab-case slug from the papers.md registry
  verdict: null                # the ledger backs the decision; the verdict lives in decision.md
  readiness: drafting
  signed-off-by: null
  signed-off-date: null
  evidence: []                 # union of the run-refs cited in the grounds column below
  covers: []
  load-bearing: null
  understanding: {status: pending, unresolved: []}
  blockers: []
  last-updated: null           # <YYYY-MM-DD>
---

# Claim → evidence ledger: <paper-id>

<!-- The backbone of the manuscript. Each row is ONE paper-level claim as a Toulmin
     SEXTET, so every assertion traces to evidence and its limits are explicit. The
     backend `tables` capability is the only writer of result numbers into
     sections/ — the ledger cites RUN-REFS, never hand-copied numbers. Every
     load-bearing claim must resolve to grounds that resolve to exact bytes via the
     provenance stamp (config hash, code provenance, dataset id+version+sha256). -->

## Sextet fields

| Field | Answers |
|---|---|
| **claim** | what the paper asserts |
| **grounds** | the evidence — **run-refs**, never numbers |
| **warrant** | why the grounds support the claim (the inferential bridge) |
| **backing** | what justifies the warrant — prior work (literature registry), theory, method |
| **qualifier** | strength / scope ("on the two in-distribution benchmarks", "under matched tuning") |
| **rebuttal** | conditions under which it would fail — threats to validity, standing counter-argument |

## Ledger

<!-- One block per claim. Duplicate the block. Keep grounds as run-refs; check
     `is-current` on them before the decision and before assembling sections. -->

### C1 — <short claim label>

- **claim:** *<...>*
- **grounds:** `run-ref://<...>`, `run-ref://<...>` — *<matched split/seed note>*
- **warrant:** *<why those grounds support the claim>*
- **backing:** *<prior work cited via the literature registry / theory / method>*
- **qualifier:** *<scope and strength>*
- **rebuttal:** *<what would make it fail; the guarding ablation>*

<!-- Worked shape (delete once you have real rows):
### C0 — method beats strongest baseline
- claim: Method M improves the primary metric over the strongest baseline.
- grounds: run-ref://rr-a91f (M), run-ref://rr-7c02 (baseline), matched split/seed.
- warrant: paired improvement under matched conditions isolates M as the cause.
- backing: matched-tuning protocol from positioning.md's baseline list.
- qualifier: holds on the two in-distribution benchmarks tested, not OOD.
- rebuttal: fails if the baseline was under-tuned — hence the isolating ablation
  and the shared tuning budget recorded in the provenance stamp.
-->
