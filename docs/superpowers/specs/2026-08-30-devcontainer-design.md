# Design — devcontainer for maintainer development

**Date:** 2026-08-30
**Author:** Davor Runje
**Status:** Approved design; not yet implemented.
**Scope:** maintainer tooling only — this is not a shipped artifact (per `CLAUDE.md`'s
"Development posture") and must not touch the plugin's domain-neutral content.

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
  install_common_tools.sh   # uv, gh auth, claude CLI, interactive-shell tooling
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
  tests, `DEFENDABLE_SCIENCE_LIVE=1 uv run pytest -m live`, can exercise real rclone).
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
   directory (`pwd` with `/` → `-`) and symlinks
   `~/.claude/projects/<host-slug>` to a stable path,
   `~/.config/defendable-science-devcontainer/claude-session-${devcontainerId}`. That
   stable path is then bind-mounted into the container at
   `/home/vscode/.claude/projects/-workspaces-defendable-science` — the slug the
   container's own `claude` CLI computes for its cwd, `/workspaces/defendable-science`.
   A `claude` session opened on the host in this repo and one opened inside the
   container therefore write transcripts into the same host directory: sessions are
   shared, not merely persisted. Best-effort: if the symlink can't be created, it falls
   back to a plain directory so container start is never blocked by this — sharing is
   just unavailable until the symlink can be made.

`host-init.sh` also extracts the host's `gh auth token` (if any) into
`~/.config/defendable-science-devcontainer/gh-token` (mode 0600), bind-mounted
**read-only** into the container at `/var/run/devcontainer-host-secrets/gh-token`, so
`gh`/`create-pr`/`create-issue` work inside the container without re-authenticating.
Non-fatal if the host has no `gh` token.

### 3.4 Python version matrix

`setup.sh` (`updateContentCommand`) delegates most of the work to
`install_common_tools.sh`, adapted from mononet's script of the same name: the
`cd /workspaces/mononet` is repointed at `/workspaces/defendable-science`, the
`MONONET_EXTRAS`-driven `install_dependencies.sh` call is dropped (this repo has one
dependency set, installed directly via `uv sync`, not mononet's per-flavor extras
matrix), and `git-lfs` is dropped from the apt package list (unused — no `.gitattributes`
LFS rules in this repo). The named-volume-ownership claiming, interactive-shell tooling
install (`bash-completion`, `vim`, `less`, `jq`, `tree`, `fzf`, `htop`, `btop` — `nvtop`
dropped, GPU-only), `uv` install, `gh` authentication (`$GITHUB_TOKEN` or the
host-forwarded token), and `claude` CLI install are carried over unchanged.

`ci.yml`'s `test` job runs the matrix `["3.11", "3.12", "3.13", "3.14"]` via
`uv sync --project defendable-science --python ${{ matrix.python-version }}`, using
`uv`'s own managed Python installs rather than system packages. `setup.sh`
(`updateContentCommand`) runs `uv python install 3.11 3.12 3.13 3.14` once to prefetch
the full matrix, then `uv sync --project defendable-science --group lint` for the
default (3.14) dev venv. Any CI job is then reproducible locally, e.g.
`uv run --project defendable-science --python 3.11 pytest`, with no extra setup. The
venv lives in a named volume,
`source=defendable-science-venv-${devcontainerId},target=/workspaces/defendable-science/defendable-science/.venv`,
so it is container-private (isolated from any host-side `.venv`) and survives rebuilds
independently of the bind-mounted source tree — mirroring mononet's rationale for its
own `.venv` volume.

### 3.5 Claude plugin provisioning

`post-create.sh` (`postCreateCommand`, runs after the workspace is bind-mounted, since
it needs `.git` for `pre-commit install`) runs, in order:

1. `uv run --project defendable-science pre-commit install --install-hooks` (from the
   repo root — matches how `ci.yml`'s `pre-commit` job invokes it).
2. `install-shell-prompt.sh` (git-aware shell prompt). `install-shell-prompt.sh` and
   `shell-prompt.sh` are adapted from mononet's, not copied verbatim: every
   `mononet`-specific identifier (the `/workspaces/mononet` path, the
   `mononet devcontainer prompt` rc marker, the `_mononet_*` cache dir/function
   prefixes) is renamed to `defendable-science`/`_defsci_*`. The prompt behavior itself
   (branch-aware `PS1`/`PROMPT`, `gh`/`uv` completion caching, fzf bindings, history
   tuning) is unchanged.
3. `provision-claude-plugins.sh`, reading `claude-plugins.txt`:

   ```
   https://github.com/obra/superpowers.git superpowers@superpowers-dev
   .                                        defendable-science@defendable-science
   ```

   The first line matches `.claude/settings.json`'s `enabledPlugins` today. The second
   self-installs this repo's own plugin from a local marketplace source (`.`, since
   `post-create.sh` runs with cwd `/workspaces/defendable-science`), so the skills this
   repo ships are testable inside the container immediately after creation. Both writes
   land only in the container-local `~/.claude` volume; the host's `~/.claude` is never
   touched. Non-fatal throughout (missing `claude` CLI, no network, or an install
   failure warn and continue) — matches mononet's `provision-claude-plugins.sh`
   verbatim in structure, reused without modification beyond the manifest contents.

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
  authenticated (if the host was); `rclone version` succeeds.
- Rebuild the container (`devcontainer rebuild`) and confirm `claude plugin list` still
  shows both plugins without re-provisioning (proves the named volume persisted) and
  that a `claude` session started before the rebuild is still visible via
  `claude --resume` after it.
- From the host (outside the container), start a `claude` session in this repo, then
  start one inside the container; confirm both appear under the same project in
  `claude --resume` history (proves session sharing).

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
