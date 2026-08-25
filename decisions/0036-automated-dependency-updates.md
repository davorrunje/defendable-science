# ADR-0036: Automated dependency updates — Dependabot for the dev toolchain and Actions, a scheduled autoupdate for hook revs, no auto-merge

- Status: accepted · Date: 2026-08-25 · Deciders: Davor Runje

## Context

Dependency maintenance was manual: PR #78 bumped six tool pins and 21 locked
versions by hand. The repo carries three independent version surfaces — the
package's `dev`/`lint` pins plus `uv.lock`, the action refs in
`.github/workflows/**`, and the remote hook `rev:` pins in
`.pre-commit-config.yaml` — and each drifts on its own schedule. The
`codespell` hook rev had already drifted from the `lint` group's pin.

The package is a **library** installed beside a consumer's own environment, so
`[project.dependencies]` are deliberately wide floors (`typer>=0.12`,
`requests>=2.31`, `pyyaml>=6.0`, `pooch>=1.8`). Raising them would narrow what
consumers can co-install for no benefit.

## Decision drivers

- Automate the mechanical part without surrendering the review decision.
- Never narrow the runtime floors.
- Batch enough to stay reviewable on a solo-maintained repo; isolate the bumps
  that actually break things.
- Don't review a release the same day it ships — yanked and compromised
  releases are usually caught within days.
- One pattern for Action-created PRs, not two (`bump-version.yml` already
  established it).

## Considered options

1. **Dependabot scoped to development dependencies, minors/patches grouped with
   `ruff`+`mypy` split out, majors ungrouped, 7-day cooldown, plus a scheduled
   `pre-commit autoupdate` workflow. No auto-merge.**
2. Dependabot with `versioning-strategy: increase` across all dependencies,
   floors included.
3. Ungrouped Dependabot — one PR per dependency.
4. Patch-level auto-merge once CI is green.
5. No Dependabot: a scheduled `uv lock --upgrade` workflow that opens a PR.

## Decision

Option 1.

- **Scope:** `allow: dependency-type: "development"` on the `uv` entry, so only
  the `dev`/`lint` `==` pins and `uv.lock` move. The runtime floors are never
  rewritten.
- **Grouping:** minors and patches are grouped; `ruff` and `mypy` form their own
  group ahead of the catch-all. Plain semver misplaces the risk for this
  toolchain — `ruff` is 0.x and `mypy` majors move fast, so a *minor* bump
  (ruff 0.15.21 → 0.16.4) is the one that rewrites files or surfaces new
  errors repo-wide. Majors are excluded from every group and therefore arrive
  one PR at a time.
- **Cadence:** weekly, Mondays 07:00 UTC, with `cooldown: default-days: 7` on
  the Python side. `cooldown` is unsupported for `github-actions`, so that entry
  has no freshness delay.
- **Hook revs:** `.github/workflows/pre-commit-autoupdate.yml` runs
  `pre-commit autoupdate` weekly (Mondays 08:00 UTC), runs the updated hooks so
  their autofixes land in the same PR, and opens a PR through
  `peter-evans/create-pull-request@v7` with the same `RELEASE_PAT || github.token`
  fallback `bump-version.yml` uses.
- **No auto-merge**, of any update type. `main` is protected, merging is the
  maintainer's action, and the agency principle says the human signs material
  decisions — a green tool bump is still a decision.

## Consequences

- At most three or four dependency PRs a week, each reviewable as a unit, each
  through the full green gate.
- A formatter or type-checker change is never buried in a batch with type stubs.
- The runtime install surface stays as wide as authored; Dependabot cannot
  narrow it.
- A CVE fix published on a Tuesday waits up to a week on the version-update
  path. Security *alerts* are unaffected — this is a version-update policy.
- `codespell` and `detect-secrets` remain pinned in two places, now bumped by
  two independent automations; the durable fix (making the `lint` pins the
  single source) is tracked as a follow-up issue.
- Dependabot PRs deviate from the house `<area>/<slug>` branch and
  commit-attribution conventions. Accepted: those govern human PRs.

## Rejected alternatives

- **Option 2 (floors included)** — would rewrite `typer>=0.12` to the latest
  release, narrowing consumer co-installation for no gain, and would need
  reverting on most PRs.
- **Option 3 (ungrouped)** — maximum bisectability at roughly 6–10 PRs per
  cycle, each demanding the full gate. Too much review load for a
  solo-maintained repo.
- **Option 4 (patch auto-merge)** — even with a 100% coverage gate and strict
  mypy, a green tool bump can change formatting or lint semantics. Landing it
  in `main` unseen contradicts the agency principle for a saving measured in
  seconds.
- **Option 5 (`uv lock --upgrade` workflow)** — hand-rolls what Dependabot's
  `uv` support already does and gives up per-dependency changelogs,
  compatibility scores, and security-update PRs.
