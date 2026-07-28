# ADR-0028: 100% statement + branch coverage gate on the package

- Status: accepted · Date: 2026-07-19 · Deciders: Davor Runje

## Context

The `defendable-science` package (ADR-0024) is small, pure-functional at its core, and
built for **reproducibility and honesty** — it is the tooling an integrity-focused
plugin tells researchers to trust. Its modules parse untrusted input (manifests,
Croissant, backlog markdown, API JSON) and degrade across missing keys/binaries,
so the branch behaviour *is* the contract. A partial coverage target invites exactly
the untested error/degradation paths that later surface as tracebacks in front of a
user.

## Decision drivers

- The package is small enough that 100% is achievable, not aspirational.
- Error/degradation branches are the ones most likely to break and least likely to
  be exercised by hand — precisely what a branch-coverage gate forces.
- A hard gate keeps every PR honest about its own tests; no slow erosion.
- Genuinely unreachable/defensive lines shouldn't distort the number.

## Considered options

1. **Hard 100% statement + branch gate (`--cov-branch`, `fail_under = 100`),
   Codecov for reporting, `# pragma: no cover` on the few genuinely
   untestable branches (real network errors, the pooch fetch).**
2. A softer threshold (e.g. 90%) with a ratchet.
3. Coverage reported but not gated.

## Decision

Option 1. `pyproject.toml` sets `--cov-branch` and `fail_under = 100`; CI fails a
PR that drops below. Codecov (tokenless OIDC) provides the diff view. The **only**
exemptions are `# pragma: no cover` on branches that cannot be driven in-process
(an actual `requests` network exception; the real `pooch` fetch), each annotated
with the reason. New code arrives with the tests that cover it, including its
error and degradation paths.

## Consequences

- Every branch — including "no S2 key → degrade", "bad input → clean error",
  "binary absent → report" — is exercised by a test.
- The gate is load-bearing on the "honest tooling" claim: the CLI a researcher
  is told to trust is fully exercised.
- Contributors must test error paths, not just happy paths; the pragma list is the
  single audited place where that rule is relaxed.

## Rejected alternatives

- **Softer threshold / ratchet** — permits untested error branches indefinitely;
  the ratchet tends to stall just below 100%.
- **Ungated reporting** — coverage decays without a failing signal.

## Links

`defendable-science/pyproject.toml` (`[tool.pytest.ini_options]`, `[tool.coverage]`);
`codecov.yml`; `.github/workflows/ci.yml`; ADR-0024 (tooling package).
