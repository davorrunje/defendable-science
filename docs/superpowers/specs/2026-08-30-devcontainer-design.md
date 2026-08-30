# Design — devcontainer for maintainer development

**Date:** 2026-08-30
**Author:** Davor Runje
**Status:** Approved design; not yet implemented.
**Scope:** maintainer tooling only — this is not a shipped artifact (per `CLAUDE.md`'s
"Development posture") and must not touch the plugin's domain-neutral content.
**ADR:** [`decisions/0044-devcontainer-for-maintainer-development.md`](../../../decisions/0044-devcontainer-for-maintainer-development.md)
records this as a material design decision, per `CLAUDE.md`'s Conventions section.

> Revised 2026-08-30 over two code-review rounds. Each candidate finding was verified
> against this repo, the actual mononet scripts (`/home/davor/projects/PhD/mononet`),
> and the containers.dev spec before being acted on; changes are marked "(revised)" or
> "(reviewed, fixed)" inline.
>
> Round 2 found that round 1's dismissal of the **session-slug** finding was wrong: the
> worktree-*scoping* point it was conflated with is indeed intended behavior, but the
> slug *computation* really is broken for worktree paths, which is this repo's default
> posture. §3.3 now carries the corrected `[/._]` rule, plus an explicit warning path so
> a future divergence in Claude Code's encoding cannot fail silently. Round 2 also
> caught that a mechanical `/workspaces/mononet` path substitution yields the **wrong**
> `.venv` path here (the package lives one level below the repo root, unlike mononet).
>
> Findings checked and confirmed **not** to apply: the pre-existing-session-directory
> claim, the `${devcontainerId}`-timing claim, the `mounts`+compose-incompatibility
> claim, and the marketplace-name-mismatch claim — reasoning kept in place so they are
> not re-opened. A `.gitignore` finding is unrelated to this design and out of scope
> here.

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
   directory (see the slug rule below) and does `mkdir -p ~/.claude/projects/<host-slug>`
   (a no-op if that directory already exists and holds real session data — the real
   directory is only ever the symlink's *target* below, never removed or replaced),
   then points a disposable, `${devcontainerId}`-scoped stable path,
   `~/.config/defendable-science-devcontainer/claude-session-${devcontainerId}`, at it
   with `ln -sfn`. That stable path is then bind-mounted into the container at
   `/home/vscode/.claude/projects/-workspaces-defendable-science` — the slug the
   container's own `claude` CLI computes for its cwd, `/workspaces/defendable-science`.
   A `claude` session opened on the host in this repo and one opened inside the
   container therefore write transcripts into the same host directory: sessions are
   shared, not merely persisted.

   **Slug rule (revised — mononet's is wrong for this repo's workflow).** mononet's
   `host-init.sh:44` uses `sed 's#/#-#g'` (slashes only). Claude Code's real encoding
   also maps `.` (and, by the same rule, `_`) to `-`, so the transform must be
   `sed 's#[/._]#-#g'`. Verified empirically on this machine: the worktree path
   `…/defendable-science/.claude/worktrees/curried-plotting-harp` has the real project
   directory `-home-davor-projects-PhD-defendable-science--claude-worktrees-curried-plotting-harp`
   (note the **double** dash, from `/.claude`), which only the `[/._]` transform
   reproduces; mononet's slash-only rule yields `…-science-.claude-worktrees-…` and
   matches nothing. No directory under this machine's `~/.claude/projects/` retains a
   `.` or `_`, consistent with the wider rule. This matters because opening the
   devcontainer from a worktree under `.claude/worktrees/` is this repo's **default**
   working posture, not an edge case — under mononet's rule, every worktree-opened
   container would silently `mkdir` a brand-new empty project directory and share
   nothing.

   **Failure honesty (added).** Because the slug rule is inferred from observed
   behavior rather than a documented contract, `host-init.sh` must not fail silently if
   Claude Code's encoding changes: after computing `<host-slug>`, if the directory did
   **not** already exist, it prints an explicit `WARNING: … computed session dir did not
   exist (slug rule may have changed); sessions may not be shared` before creating it.
   A first-ever use of a given path legitimately hits this too, so it is a warning, not
   an error — but a silent mismatch becomes visible instead of looking like the feature
   merely "doesn't work". This follows `CLAUDE.md`'s failure-honesty rule: never let a
   failure surface as a legitimate-looking empty result.

   **Fallback must not destroy transcripts (revised).** mononet's `host-init.sh:45` does
   `rm -rf "${SESSION_LINK}"` unconditionally before re-linking. That is unsafe here
   given the documented fallback: if a first open cannot create the symlink, a **plain
   directory** is created at `SESSION_LINK` and the container writes real transcripts
   into it; a later open's `rm -rf` would then delete them. This design instead removes
   the stable path only when it is actually a symlink (`[ -L "${SESSION_LINK}" ] && rm -f`),
   and if a *non-symlink* directory is found there, leaves it in place and warns rather
   than deleting. Container start is still never blocked — sharing is simply unavailable
   until the situation is resolved by hand.

   **Sharing is scoped to the exact host path the container was opened from**, not to
   "this repo" in the abstract: opening the devcontainer from a git worktree computes a
   different `<host-slug>` than opening it from the main clone, so it shares with
   sessions run from that worktree, not the main clone. This is intended, and matches
   Claude Code's own existing per-directory project model — verified: this repo's
   worktrees already have distinct directories under `~/.claude/projects/`, independent
   of any devcontainer. (This is a separate question from whether the slug is *computed*
   correctly, which the rule above fixes.)

   **(reviewed, verified safe)** A review pass claimed the design breaks when
   `~/.claude/projects/<host-slug>` already holds real data — verified false: `mkdir -p`
   on an existing directory is a no-op success, and the script never runs `ln`/`rm` against
   that path, only against the disposable stable path under
   `~/.config/defendable-science-devcontainer/`. Confirmed against this machine, which
   already has a populated `~/.claude/projects/-home-davor-projects-PhD-defendable-science/`.

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
`/var/run/devcontainer-host-secrets/gh-token-${DEVCONTAINER_ID}`. **(revised)** this is
a *change* to mononet's script, not a carry-over: mononet hardcodes
`HOST_TOKEN_FILE="/var/run/devcontainer-host-secrets/gh-token"` at
`install_common_tools.sh:95`, and leaving that line unchanged would look for a filename
that this design never writes — every container would silently fall through to the
unauthenticated warning. Because the mounted path is always a directory that exists, a
host with no `gh` token simply has no such file inside it — not a missing bind-mount
source — so the `[ -s "${HOST_TOKEN_FILE}" ]` check degrades cleanly.
`gh`/`create-pr`/`create-issue` then work inside the container without
re-authenticating; non-fatal if the host has no `gh` token.

**`containerEnv` (three variables, all required).** `${devcontainerId}` substitution is
supported here, per the containers.dev variables reference:

| Variable | Value | Why |
| --- | --- | --- |
| `CLAUDE_CONFIG_DIR` | `/home/vscode/.claude` | Carried over from mononet's `default/devcontainer.json`. The volume-ownership loop in `install_common_tools.sh` reads `"${CLAUDE_CONFIG_DIR:-}"` behind an `[ -n … ]` guard, so if this is unset the root-owned `~/.claude` volume is **silently** never chowned — no error, then a failing Claude-CLI install and plugin provisioning later in `post-create.sh`. |
| `DEVCONTAINER_ID` | `${devcontainerId}` | Lets `install_common_tools.sh` locate its own `gh-token-…` file in the shared read-only secrets directory. |
| `UV_CACHE_DIR` | `/home/vscode/.local/share/uv/cache` | Redirects `uv`'s wheel/download cache (default `~/.cache/uv`) **into** the persisted `uv` volume of §3.4, so a rebuild doesn't re-download and re-build every wheel. One volume then covers both interpreters and the wheel cache; no third volume needed. |

**(accepted limitation)** The container's `vscode` user is a fixed uid 1000
(`common-utils`, §3.2), so the bind-mounted, 0600 token file is only readable by a
container process when the host user is also uid 1000. True for this repo's sole
maintainer; Dev Containers' `updateRemoteUserUID` (default `true` on Linux) remaps the
container user's uid/gid to match the host user's for exactly this class of problem, so
this only matters on non-Linux hosts or where that default has been turned off.

### 3.4 Python version matrix

`setup.sh` (`updateContentCommand`) delegates most of the work to
`install_common_tools.sh`, adapted from mononet's script of the same name.

**The volume-ownership loop must be rewritten, not path-substituted (revised).** Named
Docker volumes are created root-owned, so the non-root `vscode` user cannot write to
them until each is chowned; mononet does this with
`for _vol in "${CLAUDE_CONFIG_DIR:-}" /workspaces/mononet/.venv` (`install_common_tools.sh:20`).
A mechanical `/workspaces/mononet` → `/workspaces/defendable-science` rename is **wrong
here**: in mononet the repo root *is* the Python project root, whereas in this repo the
package lives one level down, so the venv volume's target is
`/workspaces/defendable-science/defendable-science/.venv` (§3.4 below), not
`/workspaces/defendable-science/.venv`. The substituted path would simply not exist,
`[ -d "${_vol}" ]` would be false, the chown would be skipped, and the first `uv sync`
would fail with a permission error — exactly the failure the loop exists to prevent.
The loop must also gain the **new `uv` volume**, whose mountpoint
(`/home/vscode/.local/share/uv`) does not exist in the base image and is therefore
created root-owned by Docker; without it, `uv python install` fails with `EACCES` on a
fresh container. The correct list is all three:

```bash
for _vol in "${CLAUDE_CONFIG_DIR:-}" \
            /workspaces/defendable-science/defendable-science/.venv \
            /home/vscode/.local/share/uv; do
```

The `MONONET_EXTRAS`-driven `install_dependencies.sh` call is dropped (this repo has one
dependency set, installed directly via `uv sync`, not mononet's per-flavor extras
matrix); `git-lfs` is dropped from the apt package list (unused — no `.gitattributes`
LFS rules in this repo); the `curl`-based `uv` install step is dropped (now a Feature,
§3.2); the `HOST_TOKEN_FILE` line gains the `${DEVCONTAINER_ID}` suffix (§3.3). The
remaining `cd /workspaces/mononet` is repointed at `/workspaces/defendable-science`, and
the interactive-shell tooling install (`bash-completion`, `vim`, `less`, `jq`, `tree`,
`fzf`, `htop`, `btop` — `nvtop` dropped, GPU-only), the `$GITHUB_TOKEN`-or-host-token
`gh` authentication logic, and the `claude` CLI install carry over unchanged.

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
`source=defendable-science-uv-${devcontainerId},target=/home/vscode/.local/share/uv,type=volume`,
caches `uv`'s own downloaded interpreters and tool venvs. Without it, `~/.local/share/uv`
sits in the container's writable layer, which `devcontainer rebuild` discards — turning
the "prefetch once" claim above into a full four-interpreter re-download on every
rebuild. `UV_CACHE_DIR` is pointed at `/home/vscode/.local/share/uv/cache` (§3.3's
`containerEnv` table) so `uv`'s *wheel* cache — default `~/.cache/uv`, otherwise also in
the discarded writable layer, causing every wheel to be re-downloaded and re-built on
each rebuild — lands inside this same volume rather than needing a third one. This
volume's mountpoint does not exist in the base image, so it must be in the ownership-
claiming loop above.

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
- **Slug rule, in isolation and before any container is built:** run `host-init.sh`'s
  slug transform against this machine's real project directories and assert every
  computed slug names an existing directory under `~/.claude/projects/` — in particular
  for a path under `.claude/worktrees/`, where the `[/._]`-vs-`/`-only difference shows
  up. This is the check that catches §3.3's slug bug; it needs no Docker.
- Open the devcontainer **from a git worktree** (this repo's default posture), run a
  `claude` session inside it, and confirm the transcript appears in the host's
  `~/.claude/projects/<worktree-slug>/` — not in a freshly-created empty directory.
  Confirm no `WARNING: … slug rule may have changed` was printed for an already-used
  path.
- Open a second devcontainer instance from a different worktree concurrently with the
  first; confirm both `gh-token-${devcontainerId}` files exist independently under
  `~/.config/defendable-science-devcontainer/` and neither container's `gh auth status`
  is disrupted by the other starting or stopping.
- **Fallback safety:** with a plain (non-symlink) directory placed at a
  `claude-session-*` stable path, re-run `host-init.sh` and confirm the directory and
  its contents still exist afterwards and a warning was printed — i.e. the `rm` is
  symlink-guarded and cannot delete transcripts.
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
