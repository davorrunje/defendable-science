# ADR-0026: Independent plugin/package versioning with a compatibility pin

- Status: accepted · Date: 2026-07-19 · Deciders: Davor Runje

## Context

`defendable-science` ships two artifacts on different release cadences: the **plugin**
(markdown skills, distributed via the git self-marketplace) and the
**`defendable-science` package** (the Typer CLI the skills call, published to PyPI,
ADR-0024). A skill change and a CLI change rarely land together, and the plugin has
no build step while the package follows PEP 440. Locking the two to one version
number would force empty "release" bumps on whichever artifact didn't change and
couple two independent audiences (plugin users vs. `pip`/`uv` installers).

## Decision drivers

- The two artifacts change independently; a shared version invents false churn.
- A skill still needs *some* guarantee that the CLI it shells out to speaks the
  commands it expects — independence must not mean silent drift.
- Keep the release mechanics simple and each version scheme idiomatic (semver for
  the plugin manifest; PEP 440 for the Python package).

## Considered options

1. **Independent versions + a compatibility pin** — the plugin (`plugin.json`,
   semver) and the package (`pyproject.toml`, PEP 440) version separately; the
   skills' `ensure-tooling` bootstrap pins a compatible package range
   (`defendable-science>=<min>,<<next-major>`).
2. **Locked versions** — one number bumped in lockstep across both.
3. **No pin** — independent, with skills tolerating any installed CLI version.

## Decision

Option 1. The plugin and package version independently. The
[`ensure-tooling`](../resources/ensure-tooling.md) bootstrap installs/upgrades the
package to a **compatible range** so a skill never runs against a CLI that predates
a command it needs. The version-bump automation touches only the package
(`.github/workflows/bump-version.yml`); the plugin manifest is bumped by hand when
skills change.

## Consequences

- Each artifact releases on its own cadence with an idiomatic version scheme.
- The compat range is the contract seam: widen the lower bound when a skill starts
  relying on a newly added command; bump the upper bound at a CLI major.
- `CITATION.cff` tracks the **package** version (the citable artifact); it must be
  kept in step with `pyproject.toml` at release (currently manual).

## Rejected alternatives

- **Locked versions** — forces no-op bumps on the unchanged artifact and couples
  two unrelated release audiences.
- **No pin** — reintroduces the silent-drift failure mode (a skill invoking a
  command an older CLI doesn't have).

## Links

`resources/ensure-tooling.md`; `.claude-plugin/plugin.json`;
`defendable-science/pyproject.toml`; `.github/workflows/bump-version.yml`; ADR-0024
(tooling package + bootstrap).
