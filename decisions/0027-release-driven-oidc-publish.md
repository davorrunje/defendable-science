# ADR-0027: Publish the package via GitHub Releases + PyPI Trusted Publishing

- Status: accepted · Date: 2026-07-19 · Deciders: Davor Runje

## Context

The `defendable-science` package (ADR-0024) is distributed on PyPI, with release
candidates validated on TestPyPI first. Publishing needs a trigger (when does a
build go out?) and credentials (how does CI authenticate to the index?). Long-lived
PyPI API tokens stored as repo secrets are a standing exfiltration risk and drift
out of rotation; an ad-hoc "push a tag and hope CI runs" flow gives no human
gate between merging a version bump and shipping it.

## Decision drivers

- **No long-lived secrets** — a leaked token can publish arbitrary releases.
- A clear, auditable **human gate**: publishing to real PyPI should be a
  deliberate, recorded act, not a side effect of a merge.
- Keep **TestPyPI validation** cheap and on-demand before a real release.
- Reuse GitHub-native primitives; avoid bespoke release scripts.

## Considered options

1. **GitHub Release (published) → PyPI via Trusted Publishing (OIDC); manual
   `workflow_dispatch` → TestPyPI/PyPI.** Publishing a GitHub Release fires
   `publish.yml`, which mints a short-lived OIDC token scoped to the repo +
   workflow + environment and uploads to PyPI. A manual dispatch targets the chosen
   index (default TestPyPI) for pre-release validation.
2. **Tag-triggered publish with a stored `PYPI_API_TOKEN`.**
3. **Fully manual `uv publish` from a maintainer's machine.**

## Decision

Option 1. `.github/workflows/publish.yml` runs on `release: [published]` (real
PyPI) and on `workflow_dispatch` with a `target` input (`testpypi` default,
`pypi`), authenticating with **PyPI Trusted Publishing (OIDC)** — no tokens.
Registered trusted publishers exist for both indexes (environments `testpypi` /
`pypi`). The Docker-based `pypa/gh-action-pypi-publish` step stays at the job top
level (it cannot be nested in a local composite action); a pure-shell composite
action annotates the run with the published version.

## Consequences

- Zero long-lived publishing secrets; every upload uses an ephemeral, scoped token.
- The GitHub Release *is* the human gate and the changelog anchor; pre-releases
  (a/b/rc) publish when the Release is marked as such.
- TestPyPI dry-runs are a one-click `workflow_dispatch` before cutting a Release.
- Requires the trusted-publisher registration to be maintained on both indexes.

## Rejected alternatives

- **Stored API token** — long-lived secret; broader blast radius; rotation burden.
- **Manual local publish** — unauditable, non-reproducible, bypasses CI.

## Links

`.github/workflows/publish.yml`; `.github/actions/report-published/`;
`RELEASING.md`; ADR-0024 (tooling package); ADR-0026 (independent versioning).
