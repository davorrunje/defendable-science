# Proposal: Cross-repo thesis aggregation

`Status: draft (for discussion) · Date: 2026-07-18 · Tracks: mononet#132`

## Context

A thesis is the optional top level of the three-level mirror (`../00-meta-spec.md`
§3.1): `thesis ⊃ papers ⊃ hypotheses`. Today the thesis and every paper it binds
must live in **one** repo — the top level is self-contained. ADR-0018
(`../../../decisions/0018-git-native-source-of-truth.md`) explicitly puts
cross-repo aggregation **out of scope for v1**: work-research and a doctoral
thesis routinely live in separate repos with separate lives, and coupling them
was judged premature.

The recurring real case: a paper resolved in a company/work-research repo needs to
be a chapter of a thesis whose kappa and aims live in a *different* repo. Copying
the paper (and its `findings`/`decision` provenance) into the thesis repo breaks
the git-native single-source-of-truth invariant — the evidence now has two homes
that drift. This proposal sketches how a thesis in one repo could **reference and
read** papers that remain authoritative in other repos, without ever writing to
them, so that `thesis`, `progress`, and the kappa can operate across the boundary.

This is a design proposal for later discussion, not a decision. It presents
options with trade-offs and does not pick one.

## Goal

Let a thesis repo aggregate papers whose source of truth is a *separate* repo,
while preserving every governing invariant:

- **Agency + understanding** (`../00-meta-spec.md` §2.1–2.2) — no cross-repo read
  weakens the named-human sign-off on any material decision, and the defensibility
  mock-viva still examines the aggregated work.
- **Git-native provenance** (ADR-0018) — no external service becomes the source of
  truth; the authoritative record stays a committed file in *some* repo.
- **No cross-repo writes** — the thesis repo only ever *reads* external repos;
  a paper's verdict/decision is mutated only in the repo that owns it.

## Design sketch

Two layers: a **manifest** that names external papers (how the thesis points at
them), and **read-only aggregation** (how `progress` and the kappa consume them).

### (a) Thesis-level external-paper manifest

Extend the thesis level with a manifest — call it
`docs/research/thesis/external-papers.yml` — that maps each externally-sourced
chapter to its owning repo at a **pinned commit**. Sketch:

```yaml
# read-only references to papers whose source of truth is another repo
- paper-id: mono-depth-collapse
  repo: https://github.com/example/work-research
  commit: 3f9a1c0            # pinned; never a moving branch
  path: docs/research/depth-collapse/    # paper root within that repo
  covers: [aim-2]            # which thesis aim(s) this chapter supports
  acquired: 2026-07-18       # when the pin was last advanced (staleness clock)
```

Two mechanisms could realize the pin; both keep provenance git-native:

| Option | How it reads the external repo | Trade-offs |
|---|---|---|
| **A1 — manifest + shallow fetch** | Tooling fetches the pinned commit into a gitignored cache (e.g. `.defendable-science/external/<paper-id>@<commit>/`) and reads the committed `papers.md`, `findings.md`, `decision.md`, and status frontmatter read-only. | Loosest coupling; the thesis repo history stays clean (only the small YAML is committed). Requires a fetch step + cache; the pin lives in YAML, not in git's own object graph. |
| **A2 — git submodule** | Each external paper root is a submodule pinned to a commit; git records the pin in `.gitmodules` + the gitlink. | Pin is enforced by git itself and survives clone; familiar tooling. But submodules are notoriously sharp (detached HEADs, partial clones, recursive auth), and a whole external repo is heavier than one paper root. |

Either way the thesis repo reads **only committed artifacts** of the external
repo — the same `papers.md` registry, `findings`/`decision` docs, and status
frontmatter it would read locally — so the aggregation surface is identical to the
in-repo case; only the *retrieval* differs.

### (b) Read-only roll-up and kappa over pinned external state

`progress` (`../../../skills/progress/SKILL.md`) already rolls up **semantically**
from each artifact's status frontmatter (coverage + blockers, never a score). For
an external paper it reads the frontmatter *as pinned* and treats it exactly like a
local paper for the paper→thesis roll-up: "all aims covered by ≥1 paper AND the
kappa states the through-line." The dashboard marks the paper's origin
(`repo@commit`) and its **pin age**, but computes no new number.

The `thesis` skill (`../../../skills/thesis/SKILL.md`) reads down into external
paper roots the same way it reads local ones: the kappa's per-paper summary +
**contribution statement** is drafted from the pinned `decision`/positioning, and
the defensibility mock-viva examines the aggregated set. The hard constraints hold
unchanged — no new findings in the kappa, and the contribution statement (load-
bearing for co-authored work) is still the author's to write, drafted only as a
scaffold. Crucially, **no external verdict is re-adjudicated here**: the thesis
consumes an external paper's *signed* verdict; it never signs on the owning repo's
behalf.

### Cross-repo `is-current`

`is-current` (`../04-substrate-and-contract.md` §3) reports evidence staleness for
a run-ref against current code/config/data. Across repos there are **two distinct
staleness axes**, and the proposal keeps them separate:

1. **Pin staleness** — the external repo's `main` has advanced past the pinned
   commit (the paper may have a newer verdict). Surfaced by comparing the pin to
   the remote ref; the human decides whether to advance the pin (agency §2.1).
2. **Evidence staleness** — within the pinned commit, the paper's own run-refs may
   already be flagged stale by *its* backend. The thesis repo cannot re-run another
   repo's experiments; it can only **report** the external paper's committed
   `is-current` result. Re-running is the owning repo's job.

`progress` surfaces both as gaps; it never resolves either. This matches the
existing rule that staleness is orthogonal to verdict and the human decides
whether to re-run.

## Dependencies & posture

- **Supersedes-if-accepted:** the "out of scope" clause of ADR-0018 and
  `../00-meta-spec.md` §1 (No cross-repo aggregation). This proposal would need a
  new ADR to change that posture; until then the invariant stands.
- **Builds on:** the thesis skill's read-down composition
  (`../../../skills/thesis/SKILL.md`), the `progress` semantic roll-up
  (`../../../skills/progress/SKILL.md`), and the experiment-backend `is-current`
  contract (`../04-substrate-and-contract.md`).
- **Preserved invariants:** agency + understanding (§2.1–2.2), git-native
  single-source-of-truth (ADR-0018), no cross-repo writes, anti-Goodhart (no new
  score is introduced by aggregation).

## Open questions

- **Authentication to private repos.** Work-research repos are typically private.
  Read access needs credentials the thesis repo must *not* commit — reuse the
  `.defendable-science/` gitignored-config pattern (a token / SSH agent / `gh auth`), or defer
  to the host's ambient git auth. How does tooling degrade when a referenced repo
  is unreachable (offline, revoked token) — hard error, or read last-cached pin
  with a staleness warning?
- **A1 vs A2** (manifest+fetch vs submodule) — which coupling is worth its cost?
- **Pin advancement policy** — manual only (author advances the pin as a recorded
  act) vs an assisted "pin is N commits behind" nudge. Manual keeps it a human
  decision; an auto-advance would risk silently changing what the thesis claims.
- **Whole paper vs paper root** — reference a paper subtree, or require the
  external repo expose a stable paper-root path? Submodules pull a whole repo.
- **Provenance of the aggregated verdict** — the external `signed-off-by` names a
  human who signed in *another* repo. Does the thesis surface that original
  sign-off as-is, and does defensibility require the *thesis author* to additionally
  attest they understand and vouch for the external chapter (understanding §2.2)?
- **Identity collisions** — paper-ids/citekeys may clash across repos; the manifest
  likely needs a per-source namespace.
- **Cache location & fixity** — where the fetched pin lives, and whether it gets a
  checksum like other mirrored assets (substrate spine, `../04-substrate-and-contract.md`).

## Acceptance criteria

A future design that resolves this proposal should:

- [ ] Define the external-paper manifest schema (or the submodule convention) with
      URL + **pinned commit** + aim coverage, committed in the thesis repo.
- [ ] Specify read-only retrieval of the external repo's committed `papers.md`,
      `findings`/`decision`, and status frontmatter — with **zero writes** to the
      external repo, verified.
- [ ] Show `progress status thesis` and `dashboard` rolling up external pinned
      papers into aim coverage + blockers, with origin (`repo@commit`) and pin age
      surfaced and **no new score**.
- [ ] Show the `thesis` kappa/defensibility flow consuming external papers, with the
      external verdict *not* re-adjudicated and the contribution statement authored.
- [ ] Define **cross-repo `is-current`** for both pin staleness and (reported)
      evidence staleness, and the human-decides re-run/advance behavior.
- [ ] Define private-repo auth via gitignored `.defendable-science/` config, and the
      unreachable-repo degradation path.
- [ ] Land a new ADR that revisits ADR-0018's cross-repo-out-of-scope clause.

## Links

- mononet#132 — cross-repo thesis aggregation (tracking issue).
- ADR-0018 (`../../../decisions/0018-git-native-source-of-truth.md`) — git-native
  source of truth; cross-repo out of scope for v1.
- Meta-spec `../00-meta-spec.md` §1 (non-goals), §5 (layout), §10 (deferred:
  cross-repo thesis aggregation).
- Lifecycle `../01-lifecycle.md` §2.5 (thesis), §5 (progress roll-up).
- `../../../skills/thesis/SKILL.md`, `../../../skills/progress/SKILL.md`.
- Experiment-backend contract `../04-substrate-and-contract.md` (`is-current`).
