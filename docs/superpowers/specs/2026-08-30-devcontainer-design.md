# Design — devcontainer for maintainer development

**Date:** 2026-08-30
**Author:** Davor Runje
**Status:** Approved design; not yet implemented.
**Scope:** maintainer tooling only — this is not a shipped artifact (per `CLAUDE.md`'s
"Development posture") and must not touch the plugin's domain-neutral content.
**ADR:** [`decisions/0044-devcontainer-for-maintainer-development.md`](../../../decisions/0044-devcontainer-for-maintainer-development.md)
records this as a material design decision, per `CLAUDE.md`'s Conventions section.

> Revised 2026-08-30 after a code review of the first draft. Each candidate finding was
> verified against this repo, the actual mononet scripts, and the containers.dev spec
> before being acted on; changes are marked "(reviewed, fixed)" inline. A few candidate
> findings were checked and found **incorrect** — the pre-existing-session-directory
> claim, the `${devcontainerId}`-timing claim, the `mounts`+compose-incompatibility
> claim, the marketplace-name-mismatch claim, and the worktree-slug "bug" — these are
> marked "(reviewed, verified safe)" or clarified in place, with the reasoning kept so
> the question isn't re-opened later. One finding (a `.gitignore` line unrelated to this
> design) was left alone as out of scope.

## 1. Problem

There is currently no devcontainer for this repo. Development happens directly on the
host, which means: no reproducible, isolated toolchain across machines; Claude Code
session/plugin state lives only in the host's single `~/.claude`; and there is no
container-local place to exercise the full CI Python matrix (3.11–3.14) without touching
the host's Python installs.

The author has an existing, working pattern in `davorrunje/mononet`
(`.devcontainer/{default,shared}/`) built for a much larger project (multiple GPU
flavors, Node, Docker-in-Docker). This design reuses its two genuinely reusable ideas —
persisting `~/.claude` across rebuilds via a named volume, and sharing a project's Claude
session transcripts between host and container via a host-side symlink — while dropping
everything mononet needs that this repo does not.

## 2. Non-goals

- No GPU/multi-flavor split. This repo has one toolchain (`uv` + Python).
- No Node.js, no Docker-in-Docker. Nothing in the repo (outside the unrelated Mintlify
  docs-publish CI job) needs either; add on request if the docs site needs local preview.
- Not a replacement for CI. CI (`ci.yml`) remains the source of truth; the devcontainer
  exists to reproduce it locally, not to change what it checks.

## 3. Decision

### 3.1 Layout

Single-flavor `.devcontainer/` (no `default/`/`gpu-*` split — mononet needs that split
because it has multiple flavors; this repo has one):

```
.devcontainer/
  devcontainer.json
  docker-compose.yml
  claude-plugins.txt
  host-init.sh              # runs on the HOST via initializeCommand
  install_common_tools.sh   # volume ownership, gh auth, claude CLI, interactive-shell tooling
  install-shell-prompt.sh   # wires shell-prompt.sh into ~/.bashrc / ~/.zshrc
  shell-prompt.sh           # git-aware prompt + completion, sourced by the above
  setup.sh                  # updateContentCommand: python matrix prefetch + uv sync
  post-create.sh            # postCreateCommand: pre-commit install, plugin provisioning
  provision-claude-plugins.sh
```

### 3.2 Base image and features

- Image: `mcr.microsoft.com/devcontainers/python:3.14` (confirmed to exist:
  `3.14`/`3.14-bookworm`/`3.14-trixie` tags are published). Matches
  `defendable-science/pyproject.toml`'s `requires-python = ">=3.11,<3.15"` upper bound.
- Features: `ghcr.io/devcontainers/features/common-utils:2` (zsh + oh-my-zsh, uid/gid
  1000, user `vscode`), `ghcr.io/devcontainers/features/git:1`,
  `ghcr.io/devcontainers/features/github-cli:1`,
  `ghcr.io/devcontainers-extra/features/rclone:1` (so the opt-in live dataset-retrieval
  tests, `DEFENDABLE_SCIENCE_LIVE=1 uv run pytest -m live --no-cov` per `CLAUDE.md`, can
  exercise real rclone), and `ghcr.io/devcontainers-extra/features/uv:1` — **(revised)**
  a Feature instead of mononet's hand-rolled `curl -LsSf https://astral.sh/uv/install.sh`
  step: this repo already gets `git`/`github-cli`/`rclone` from Features, whose versions
  Dependabot tracks the same way it tracks Actions (ADR-0036); a curl-installed `uv`
  would drift silently outside that mechanism instead. See ADR-0044's rejected
  alternatives.
- Explicitly **not** included: `node`, `docker-in-docker` — no reference to either in the
  repo outside the unrelated docs-publish workflow.

### 3.3 Claude Code config persistence and session sharing

Two independent mechanisms, both adapted from mononet:

1. **Config surviving image rebuilds.** `~/.claude` inside the container is the named
   Docker volume `defendable-science-claude-config-${devcontainerId}`, mounted via
   `devcontainer.json`'s `mounts`, not baked into the container's writable layer.
   `devcontainer rebuild` recreates the container but not the volume, so installed
   plugins, auth, and settings persist across rebuilds.
2. **Session sharing between host and container.** `host-init.sh` runs on the *host*
   (via `initializeCommand`, before the container starts, receiving `${devcontainerId}`
   as `$1`). It computes the host's Claude project slug for the current working
   directory (`pwd` with `/` → `-`) and does `mkdir -p ~/.claude/projects/<host-slug>`
   (a no-op if that directory already exists and holds real session data — the real
   directory is only ever the symlink's *target* below, never removed or replaced),
   then points a disposable, `${devcontainerId}`-scoped stable path,
   `~/.config/defendable-science-devcontainer/claude-session-${devcontainerId}`, at it
   with `ln -sfn` (only the disposable stable path itself is `rm -f`'d first, to make
   re-running idempotent). That stable path is then bind-mounted into the container at
   `/home/vscode/.claude/projects/-workspaces-defendable-science` — the slug the
   container's own `claude` CLI computes for its cwd, `/workspaces/defendable-science`.
   A `claude` session opened on the host in this repo and one opened inside the
   container therefore write transcripts into the same host directory: sessions are
   shared, not merely persisted. Best-effort: if the symlink can't be created, it falls
   back to a plain directory so container start is never blocked by this — sharing is
   just unavailable until the symlink can be made.

   **(reviewed, verified safe)** An earlier review pass claimed this breaks when
   `~/.claude/projects/<host-slug>` already holds real data — verified false: `mkdir -p`
   on an existing directory is a no-op success, and the script never runs `ln`/`rm -rf`
   against that path, only against the disposable stable path under
   `~/.config/defendable-science-devcontainer/`. Confirmed against this machine, which
   already has a populated `~/.claude/projects/-home-davor-projects-PhD-defendable-science/`.

   **Sharing is scoped to the exact host path the container was opened from**, not to
   "this repo" in the abstract: opening the devcontainer from a git worktree computes a
   different `<host-slug>` than opening it from the main clone, so it shares with
   sessions run from that worktree, not the main clone. This matches Claude Code's own
   existing per-directory project model — verified: this repo's worktrees already have
   distinct directories under `~/.claude/projects/`, independent of any devcontainer.

   `initializeCommand`, `mounts`, and `containerEnv` are all documented by the
   containers.dev spec as supporting `${devcontainerId}` substitution, and it is
   defined as "stable across rebuilds" — so the ID `host-init.sh` receives and the one
   substituted into `mounts`/`containerEnv` for the same container are the same value.
   `mounts` is separately documented as a "cross-orchestrator way to add additional
   mounts," so it applies the same way whether or not `dockerComposeFile` is set —
   this is exactly how mononet's own (working) `default/devcontainer.json` uses it
   alongside its compose file.

`host-init.sh` also unconditionally `mkdir -p`s
`~/.config/defendable-science-devcontainer` (so the directory always exists, whether
or not a token is available) and, if the host's `gh auth token` succeeds, writes it to
`~/.config/defendable-science-devcontainer/gh-token-${devcontainerId}` (mode 0600) —
suffixed per-`${devcontainerId}`, not a single shared filename, so two devcontainers
opened concurrently from different worktrees (this repo's normal workflow) don't race
to overwrite each other's token. **The directory** (not the individual token file) is
what's bind-mounted **read-only** into the container, at
`/var/run/devcontainer-host-secrets`; `install_common_tools.sh` reads
`/var/run/devcontainer-host-secrets/gh-token-${DEVCONTAINER_ID}` (`DEVCONTAINER_ID`
passed in via `containerEnv`, which also supports `${devcontainerId}` substitution).
Because the mounted path is always a directory that exists, a host with no `gh` token
simply has no such file inside it — not a missing bind-mount source — so
`install_common_tools.sh`'s `[ -s "${HOST_TOKEN_FILE}" ]` check degrades cleanly.
`gh`/`create-pr`/`create-issue` then work inside the container without
re-authenticating; non-fatal if the host has no `gh` token.

**(accepted limitation)** The container's `vscode` user is a fixed uid 1000
(`common-utils`, §3.2), so the bind-mounted, 0600 token file is only readable by a
container process when the host user is also uid 1000. True for this repo's sole
maintainer; Dev Containers' `updateRemoteUserUID` (default `true` on Linux) remaps the
container user's uid/gid to match the host user's for exactly this class of problem, so
this only matters on non-Linux hosts or where that default has been turned off.

### 3.4 Python version matrix

`setup.sh` (`updateContentCommand`) delegates most of the work to
`install_common_tools.sh`, adapted from mononet's script of the same name.
**(revised)** *every* literal `/workspaces/mononet` occurrence is repointed at
`/workspaces/defendable-science` — not just the leading `cd` line but also the
named-volume-ownership-claiming loop's `.venv` path check (mononet's script iterates
over `"${CLAUDE_CONFIG_DIR:-}" /workspaces/mononet/.venv`; missing the second occurrence
would leave the fresh, root-owned `.venv` volume unclaimed, and the first `uv sync`
would then fail with a permission error). The `MONONET_EXTRAS`-driven
`install_dependencies.sh` call is dropped (this repo has one dependency set, installed
directly via `uv sync`, not mononet's per-flavor extras matrix); `git-lfs` is dropped
from the apt package list (unused — no `.gitattributes` LFS rules in this repo); the
`curl`-based `uv` install step is dropped (now a Feature, §3.2). The named-volume-
ownership claiming, interactive-shell tooling install (`bash-completion`, `vim`,
`less`, `jq`, `tree`, `fzf`, `htop`, `btop` — `nvtop` dropped, GPU-only), `gh`
authentication (`$GITHUB_TOKEN` or the host-forwarded, `${DEVCONTAINER_ID}`-scoped
token), and `claude` CLI install are carried over unchanged.

`ci.yml`'s `test` job runs the matrix `["3.11", "3.12", "3.13", "3.14"]` via
`uv sync --project defendable-science --python ${{ matrix.python-version }}` (the
interpreter itself comes from `actions/setup-python` in CI; `uv sync --python X` only
needs *a* working Python X to link against, so prefetching via `uv python install`
instead reproduces the same test conditions). `setup.sh` (`updateContentCommand`) runs
`uv python install 3.11 3.12 3.13 3.14` once to prefetch the full matrix, then
`uv sync --project defendable-science --group lint` for the default (3.14) dev venv.
Any CI job is then reproducible locally with, e.g.,
`cd defendable-science && uv run --python 3.11 pytest` — **(reviewed, fixed)** the
`cd` is required, not optional: verified directly that running the equivalent command
from the repo root (`uv run --project defendable-science --python 3.11 pytest`, the
form in the previous draft) does not apply `defendable-science/pyproject.toml`'s
`[tool.pytest.ini_options]` at all (no `pytest.mark.live` registration, no coverage
gate) — `pytest`'s config discovery walks up from the *current directory*, and the
repo root has no `pyproject.toml` of its own. This matches `ci.yml`'s own
`working-directory: defendable-science` for the same step.

The venv lives in a named volume,
`source=defendable-science-venv-${devcontainerId},target=/workspaces/defendable-science/defendable-science/.venv`,
so it is container-private (isolated from any host-side `.venv`) and survives rebuilds
independently of the bind-mounted source tree — mirroring mononet's rationale for its
own `.venv` volume. Switching `--python` versions against this shared venv makes `uv`
rebuild it in place (expected, not a bug — just not "free" the way separate per-version
venvs would be; not worth the extra complexity for four rarely-alternated versions).

**(reviewed, fixed)** A second named volume,
`source=defendable-science-uv-python-${devcontainerId},target=/home/vscode/.local/share/uv,type=volume`,
caches `uv`'s own downloaded interpreters and tool venvs. Without it, `~/.local/share/uv`
sits in the container's writable layer, which `devcontainer rebuild` discards — turning
the "prefetch once" claim above into a full four-interpreter re-download on every
rebuild.

### 3.5 Claude plugin provisioning

`post-create.sh` (`postCreateCommand`, runs after the workspace is bind-mounted, since
it needs `.git` for `pre-commit install`) runs, in order:

1. `uv run --project defendable-science pre-commit install --install-hooks --hook-type
   pre-commit --hook-type pre-merge-commit` (from the repo root, so `pre-commit` reads
   `.pre-commit-config.yaml` there — matching the *working directory* `ci.yml`'s
   `pre-commit` job uses). **(reviewed, fixed)** the previous draft additionally claimed
   this "matches how `ci.yml`'s `pre-commit` job invokes it" — inaccurate beyond the
   working directory: `ci.yml` never runs `pre-commit install` at all, only
   `pre-commit run --hook-stage manual --all-files`; those are different commands doing
   different things (registering git hooks vs. executing them once). Separately, a bare
   `pre-commit install` only registers the `pre-commit` hook type — `.pre-commit-config.yaml`'s
   `default_stages: [pre-commit, pre-merge-commit]` means `pre-merge-commit` hooks never
   run locally without also passing `--hook-type pre-merge-commit`.
2. `install-shell-prompt.sh` (git-aware shell prompt). `install-shell-prompt.sh` and
   `shell-prompt.sh` are adapted from mononet's, not copied verbatim: every
   `mononet`-specific identifier (the `/workspaces/mononet` path, the
   `mononet devcontainer prompt` rc marker, the `_mononet_*` cache dir/function
   prefixes) is renamed to `defendable-science`/`_defsci_*`. The prompt behavior itself
   (branch-aware `PS1`/`PROMPT`, `gh`/`uv` completion caching, fzf bindings, history
   tuning) is unchanged.
3. `provision-claude-plugins.sh`, reading `claude-plugins.txt`:

   ```
   https://github.com/obra/superpowers.git              superpowers@superpowers-dev
   /workspaces/defendable-science                        defendable-science@defendable-science
   ```

   The first line matches `.claude/settings.json`'s `enabledPlugins` today; `superpowers-dev`
   is verified as the exact marketplace name `obra/superpowers`'s own
   `.claude-plugin/marketplace.json` declares for itself, not a locally-chosen alias —
   `claude plugin install superpowers@superpowers-dev` resolves correctly. The second
   line self-installs this repo's own plugin from a local marketplace source, so the
   skills this repo ships are testable inside the container immediately after creation.

   **(reviewed, fixed)** the source is the absolute path `/workspaces/defendable-science`,
   not `.` as in the previous draft: `provision-claude-plugins.sh`'s idempotency check is
   `grep -qF "${src}"` against `claude plugin marketplace list` output, and a single `.`
   in fixed-string mode matches almost any line (URLs, version strings, paths all contain
   a literal `.`) — the marketplace would read as "already known" on the very first run
   and silently never get added. The absolute path is specific enough not to collide.

   Both writes land only in the container-local `~/.claude` volume; the host's
   `~/.claude` is never touched. Non-fatal throughout (missing `claude` CLI, no network,
   or an install failure warn and continue) — `provision-claude-plugins.sh` itself is
   reused from mononet without modification; only the manifest contents differ.

### 3.6 `docker-compose.yml`

Single service, image built from the base above, repo bind-mounted at
`/workspaces/defendable-science:cached`, `command: sleep infinity`. No networks beyond
the default bridge (mononet's per-project network exists because multiple flavors need
to interoperate; not needed here).

## 4. Testing / verification plan

- `docker compose -f .devcontainer/docker-compose.yml config` validates compose syntax
  without building.
- Build and open the devcontainer (VS Code "Reopen in Container" or
  `devcontainer up --workspace-folder .`); confirm `updateContentCommand` and
  `postCreateCommand` both exit 0.
- Inside the container: `cd defendable-science && uv run pytest -q` passes; `claude
  plugin list` shows `superpowers` and `defendable-science`; `gh auth status` shows
  authenticated (if the host was); `rclone version` succeeds; `uv run --python 3.11
  pytest -q` (from `defendable-science/`) also passes without re-downloading anything
  beyond that interpreter's dependency resolution.
- Rebuild the container (`devcontainer rebuild`) and confirm: `claude plugin list`
  still shows both plugins without re-provisioning (proves the `~/.claude` volume
  persisted); a `claude` session started before the rebuild is still visible via
  `claude --resume` after it; `uv python list` still shows all four interpreters
  without re-downloading (proves the `uv`-python-cache volume persisted).
- Open a second devcontainer instance from a git worktree of this repo concurrently
  with the first; confirm both `gh-token-${devcontainerId}` files exist independently
  under `~/.config/defendable-science-devcontainer/` and neither container's `gh auth
  status` is disrupted by the other starting or stopping.
- From the host (outside the container), start a `claude` session in this repo, then
  start one inside the container opened from the same path; confirm both appear under
  the same project in `claude --resume` history (proves session sharing).

## 5. Rejected alternatives

- **Reuse mononet's multi-flavor layout wholesale (`default/` + `shared/`).** Rejected:
  this repo has one toolchain; the split exists in mononet solely to let GPU flavors
  share scripts with the CPU flavor. Copying the split here would be structure with no
  second flavor to justify it.
- **Skip session sharing; just persist the container's own `~/.claude`.** Rejected:
  explicitly requested — the author wants continuity between host-side and
  container-side sessions on the same repo, not just survival across rebuilds.
- **Pin a single Python version instead of prefetching the CI matrix.** Rejected: the
  package ships to PyPI across 3.11–3.14 (`pyproject.toml` classifiers) and CI tests
  all four; a devcontainer that can only reproduce one of those four jobs would leave
  three untestable locally.
- **Hand-install `uv` via curl (mononet's approach) instead of a Feature.** Rejected:
  `ghcr.io/devcontainers-extra/features/uv:1` exists, and this repo already sources
  `git`/`github-cli`/`rclone` as Features whose versions Dependabot tracks (ADR-0036);
  a curl-installed `uv` would be the one tool drifting outside that mechanism.
- **Wire the shell prompt via the devcontainer `dotfiles` mechanism instead of a
  committed script.** Rejected: `dotfiles.repository` pulls a *personal* dotfiles repo
  — a second person, or the author on a machine without that repo configured, opening
  this devcontainer would get no prompt at all. A script committed under
  `.devcontainer/` ships with the repo and works for anyone who opens it.
- **Separate `.venv` per Python version instead of one shared, rebuilt-in-place venv.**
  Rejected as unneeded complexity: switching `--python` only happens when deliberately
  reproducing a specific CI leg, not routinely: a rebuild-in-place cost on those
  occasions is acceptable against the cost of managing four persistent venvs.
