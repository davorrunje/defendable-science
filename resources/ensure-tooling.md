# ensure-tooling — bootstrap the `defendable-science` CLI

Skills that call the `defendable-science` CLI **must first ensure it is installed**, by
following this procedure. It is markdown the agent executes via the shell — the
plugin ships no build step. Goal: get an isolated, pinned `defendable-science`
install with **zero footprint on the consumer's project environment**, adapting
to whatever toolchain is present, and **stopping honestly** when it can't.

Design principles: **idempotent** (never reinstall if already present),
**isolated** (its own env, never the consumer's ML env), **consent for
environment changes** (installing `uv`/Python is the user's call), **honest stop**
(explicit instructions rather than a cryptic failure).

## Procedure

1. **Fast path.** If a recorded invocation exists (`.defendable-science/config.yml →
   tooling.cli`) or `defendable-science` is on `PATH`, run `defendable-science --version`. If it matches
   the pinned version → **done**.
2. **Detect a toolchain**, in priority order:
   - `uv` (preferred — a single binary that can also provision Python),
   - else `pipx`,
   - else `python3` (with `venv` + `pip`).
3. **Install, isolated** — **PyPI-first**. The primary source is the published
   package `defendable-science` on PyPI, pinned to a **compatible range**
   (`defendable-science>=0.3.0,<0.4.0` — the minimum package version this plugin
   release requires, up to the next incompatible boundary; see the *Version
   pinning* note):
   - `uv tool install defendable-science` — installs Python + deps in an isolated tool
     env; or run ad hoc with `uvx defendable-science …` (no persistent install).
   - else `pipx install defendable-science`.
   - else `python3 -m venv "$XDG_STATE_HOME/defendable-science/venv-<ref>"` (fallback:
     `~/.local/state/defendable-science/…`) then that venv's `pip install defendable-science`.
   - **Pre-release validation:** install release candidates from **TestPyPI**
     (`uv tool install --index https://test.pypi.org/simple/ defendable-science`, or
     `pip install --index-url https://test.pypi.org/simple/ defendable-science`) before
     a real release.
   - **Fallback — git subdirectory** (an unreleased `<ref>`, or PyPI unreachable):
     install from the plugin repo's `defendable-science/` subdirectory, pinned to
     `<ref>` — a git tag/commit. Let
     `SRC="git+https://github.com/davorrunje/defendable-science.git@<ref>#subdirectory=defendable-science"`
     and use `uv tool install "$SRC"` / `uvx --from "$SRC" defendable-science …` /
     `pipx install "$SRC"` / venv + `pip install "$SRC"`.
4. **Record** the resolved invocation under `.defendable-science/config.yml`
   (`tooling: { cli: "<path-or-command>", version: "<version>" }`) so later calls
   skip detection.
5. **Environment changes need consent.** If neither `uv`/`pipx` nor Python is
   present, do **not** silently `curl … | sh` or mutate the system. Show the
   official install command (e.g. the `uv` installer one-liner) and ask the user
   to run it (or confirm) — then resume.
6. **Honest stop.** If the environment can't be provisioned (offline, locked
   down, no toolchain and consent declined) → stop and print copy-pasteable
   instructions. Never fake tooling output.

## Notes

- **Isolation:** the install lives in a `uv`/`pipx` tool env or a per-user state
  venv — never the consumer repo's project env. This is what lets `defendable-science`
  depend freely on `typer` / `requests` / `pyyaml` / `pooch` without touching
  anyone's torch/jax install.
- **Idempotency:** step 1 must be cheap; only steps 2–3 touch the network.
- **Version pinning:** the plugin and the `defendable-science` package are versioned
  **independently** (ADR-0026). The plugin pins a *compatible range* (currently
  `>=0.3.0,<0.4.0`), not an exact string-lock — the lower bound is the minimum
  package version the plugin's skills need, the upper bound the next incompatible
  boundary. Bump the lower bound deliberately, when a skill starts calling a CLI
  capability an earlier release did not have. **Why it reads `0.3.0`:** that is
  the release carrying the `literature fetch | confirm | verify | mirror` verbs,
  which moved the bound past `0.2.x`, together with `research-init`'s
  `defendable-science init` and the repo-validation `check` alongside it — so the
  bound already covers all of them and does not move again for them. The
  `digest extract axes | record | sample | render` group that extraction mode
  calls lands in that same unreleased `0.3.0` line, so it needs **no** further
  move of the lower bound; it does mean a consumer on a published `0.2.x` will
  not have those verbs, which is exactly what the `>=0.3.0` floor already tells
  them. The
  package's own releases (PEP 440, `v*` tags → PyPI) proceed on their own
  cadence.
- **rclone** (the private-mirror engine) is a separate single static binary — **not
  a Python dependency**; `defendable-science` shells out to it. It is **optional**: only
  private-mirror operations need it (Tier-A git/LFS and Tier-B `pooch` fetch do
  not). Ensure it by the same **detect → ensure/instruct** pattern: check `rclone`
  on `PATH`; if missing, prefer an OS package (`apt`/`brew`), else offer to fetch
  the **checksum-verified** static binary into `$XDG_STATE_HOME/defendable-science/bin/` **with
  consent**, else **honest stop** with the official install command (never a silent
  `curl | sh`). `defendable-science doctor` reports Python / `uv` / `rclone` presence + versions.
