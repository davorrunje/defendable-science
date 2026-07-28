# Releasing

`defendable-science` ships **two independently-versioned artifacts**:

| Artifact | What | Distributed via | Version source |
|---|---|---|---|
| **Plugin** | the Claude Code plugin (skills + docs) | this repo's git **marketplace** | `.claude-plugin/plugin.json` (semver) |
| **Package** | the `defendable-science` CLI tooling (`defendable-science/`) | **PyPI** | `defendable-science/pyproject.toml` (PEP 440) |

They version **independently** — a skill edit needn't cut a PyPI release, and a
CLI fix needn't re-cut the plugin. The plugin declares a *compatible range* of
the package (`defendable-science>=<min>,<<next>`) in
[`resources/ensure-tooling.md`](resources/ensure-tooling.md); that pin is the
coupling, not a shared version string.

> **`v<version>` tags / GitHub Releases are _package_ releases** (PEP 440
> spelling, e.g. `v0.1.0rc1`) and trigger the PyPI publish. Because a Release is
> a whole-repo snapshot, it also doubles as a pinnable point for the plugin.

---

## Releasing the package (PyPI)

Driven by three workflows — no local build / `twine` needed:

| Workflow | Role |
|---|---|
| **Bump version** (`bump-version.yml`) | compute the next PEP 440 version, open a release PR |
| **CI** (`ci.yml`) | lint + types + tests (100% coverage gate) on every PR |
| **Publish** (`publish.yml`) | build + upload to TestPyPI / PyPI via Trusted Publishing (OIDC) |

1. **Bump the version.** Actions → **Bump version** → *Run workflow* on `main`:
   - `release`: `none` / `patch` / `minor` / `major` (a release bump clears any prerelease)
   - `pre`: `keep` / `alpha` / `beta` / `rc` / `final`

   | want | release | pre | result (from `0.0.0a1`) |
   |---|---|---|---|
   | next alpha | none | alpha | `0.0.0a2` |
   | promote to rc | none | rc | `0.0.0rc0` |
   | cut the final | none | final | `0.0.0` |
   | start 0.1.0's alpha | minor | alpha | `0.1.0a0` |
   | patch release | patch | keep | `0.0.1` |

   It edits `pyproject.toml` and opens a **`release: defendable-science v<version>`** PR.

2. **Review & merge the release PR** into `main` (wait for CI).

3. **Validate on TestPyPI.** Actions → **Publish** → *Run workflow* with
   `target: testpypi` (the default). Check the run **summary** for the link, then
   optionally smoke-test (the extra index resolves the runtime deps, which live
   on real PyPI; `--prerelease=allow` is needed for an a/b/rc version):
   ```bash
   uv tool install \
     --index-url https://test.pypi.org/simple/ \
     --extra-index-url https://pypi.org/simple/ \
     --prerelease=allow defendable-science==<version>
   defendable-science --version
   ```

4. **Publish to PyPI — create a GitHub Release.** The published Release creates
   the tag, writes a changelog, and triggers Publish → PyPI:
   ```bash
   git switch main && git pull
   gh release create v<version> --generate-notes                # final
   gh release create v<version> --generate-notes --prerelease   # a / b / rc
   ```
   (or use the Releases UI — tick *"Set as a pre-release"* for `a`/`b`/`rc`). The
   Publish run's summary/annotation shows
   `https://pypi.org/project/defendable-science/<version>/`.

   > Re-running a publish without a new Release (e.g. after a transient failure):
   > Actions → **Publish** → `target: pypi`. Don't push a bare `v*` tag — the
   > trigger is the **Release**, not the tag.

---

## Releasing the plugin

The plugin has **no build or upload step** — it's served from git through the
marketplace (`/plugin marketplace add davorrunje/defendable-science`). A "release" is
just a versioned, validated snapshot users can pin.

1. **Bump** `.claude-plugin/plugin.json` `version` (semver: `patch` / `minor` /
   `major`).
2. **Re-pin the package if needed.** If the plugin's skills now rely on a newer
   CLI capability, raise the compatibility floor in
   [`resources/ensure-tooling.md`](resources/ensure-tooling.md)
   (`defendable-science>=<min>`).
3. **Validate:** `claude plugin validate .`.
4. **Open a PR and merge to `main`.**
5. **How users pin it.** In their `.claude/settings.json` marketplace source,
   users either track the default branch or pin `"ref": "v<version>"` — a package
   `v*` Release is a whole-repo snapshot, so it pins the plugin at that commit
   too. For a **plugin-only** release (no package change), do **not** create a
   `v*` Release (it would re-trigger a package publish of an unchanged version →
   PyPI 409); if you want a dedicated pin marker, tag `plugin-v<version>`.

> There's no automated plugin-bump action yet (the **Bump version** action bumps
> only the package). Bump `plugin.json` by hand for now.

---

## One-time setup (already done; for reference)

- **Trusted Publishing (OIDC, no tokens)** — registered publishers on PyPI and
  TestPyPI for repo `davorrunje/defendable-science`, workflow `publish.yml`,
  environments `testpypi` / `pypi`.
- **`RELEASE_PAT` secret** — a fine-grained PAT (Contents: read/write, Pull
  requests: read/write) so **Bump version** can open the release PR *and* have CI
  run on it.

## Notes / gotchas

- **Immutable versions.** PyPI/TestPyPI reject re-uploading an existing version —
  bump to a new one rather than re-publishing.
- **Prereleases** (`aN`/`bN`/`rcN`) publish like any version but aren't installed
  by default (`pip`/`uv` need `--prerelease=allow` or an explicit `==<prerelease>`).
- **Two artifacts, two cadences.** Keep the plugin and package versions moving on
  their own schedules; the `ensure-tooling` pin is what keeps them compatible.
