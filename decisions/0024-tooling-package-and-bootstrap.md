# ADR-0024: Supporting tooling ships as one package (Typer CLI, optional MCP), bootstrapped by a markdown `ensure-tooling` procedure

- Status: accepted · Date: 2026-07-18 · Deciders: Davor Runje

## Context

The supporting-script TODOs (literature citation-graph client, dataset manifest +
retrieval/mirror, defend record, exploration backlog) were first drafted as loose
`scripts/*.py`. Loose scripts don't handle dependencies, versioning, testing, or
config, and each reinvents HTTP/caching/arg-parsing. Meanwhile the plugin is
**pure-markdown** (no runtime), and consumer environments are unknown — `uv` may
be absent, and Python itself can't be assumed.

## Decision drivers

- Proper dependency + version management for the executable tooling.
- **Isolation:** must not pollute a consumer's ML environment (the light-dep rule).
- Keep the plugin pure-markdown (no build step baked into the plugin).
- Work across unknown/heterogeneous environments, degrading honestly.

## Considered options

1. Loose `scripts/*.py`.
2. **One `defendable-science` package — `core` + a Typer CLI (authoritative) + an
   optional thin MCP wrapper — installed in an isolated env, bootstrapped by a
   markdown `ensure-tooling` procedure the agent runs.**
3. A plugin install/build hook that provisions the env.
4. An MCP-server-only design.

## Decision

Option 2. **CLI-first** (`defendable-science …`, Typer); the **MCP server is a later, thin
wrapper** over the same `core` (nothing depends on MCP alone). The five script
proposals become **modules** of `defendable-science`. Bootstrap is a shared markdown
[`ensure-tooling`](../resources/ensure-tooling.md) procedure: detect
`uv`→`pipx`→`python3`, install the package **isolated** (prefer `uv tool install`,
which also provisions Python), record the CLI path in `.defendable-science/config.yml`, and
**stop with instructions** when the environment can't self-heal. Installing
`uv`/Python itself requires user consent (no unprompted `curl|sh`).

## Consequences

- The plugin stays markdown-authored but gains a runtime dependency (the CLI),
  set up on demand, isolated per-user.
- Distribution is **PyPI-first**: `defendable-science` is published to PyPI (release
  candidates validated on TestPyPI first) and installed from there by default; the
  git-subdirectory install from the repo is the versioned fallback.
- Skills call `defendable-science <group> <cmd>` via Bash after `ensure-tooling`.
- Supersedes the loose-script framing in the five proposals (now modules).

## Rejected alternatives

- **Loose scripts** — no dep/version management; doesn't scale past one file.
- **Install/build hook** — assumes a toolchain; less transparent and adaptive
  than an agent-run detect-and-install procedure across unknown envs.
- **MCP-only** — runtime-heavy; a CLI is simpler, portable, testable, and usable
  outside Claude Code. MCP is additive, not foundational.

## Links

`docs/design/proposals/tooling-package.md`; `resources/ensure-tooling.md`;
the five module proposals in `docs/design/proposals/`; ADR-0013 (experiment
contract, also Typer); ADR-0023 (engineering contract).
