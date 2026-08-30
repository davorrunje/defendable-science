# Design — devcontainer for maintainer development

**Date:** 2026-08-30
**Author:** Davor Runje
**Status:** Approved design; not yet implemented.
**Scope:** maintainer tooling only — this is not a shipped artifact (per `CLAUDE.md`'s
"Development posture") and must not touch the plugin's domain-neutral content.
**ADR:** [`decisions/0044-devcontainer-for-maintainer-development.md`](../../../decisions/0044-devcontainer-for-maintainer-development.md)
records this as a material design decision, per `CLAUDE.md`'s Conventions section.

> Revised 2026-08-30 over three code-review rounds. Every candidate finding was checked
> against this repo, the real mononet scripts (`/home/davor/projects/PhD/mononet`), this
> machine's `~/.claude/projects/`, and the containers.dev spec before being acted on;
> changes are marked "(revised)" or "(reviewed, fixed)" inline. Two rounds overturned an
> earlier round's conclusion, so the reasoning is kept rather than silently replaced.
>
> - **Round 2** overturned round 1's dismissal of the session-slug finding. (Round 1 had
>   conflated it with the separate, correct point that worktree *scoping* is intended.)
> - **Round 3** overturned round 2's slug fix in turn: `[/._]` is still wrong — a real
>   worktree path here contains `+`, which Claude Code also maps to `-`. The rule is
>   `[^a-zA-Z0-9]`. Round 3 also found the load-bearing constraint in §2.1 (git worktrees
>   cannot cross the container boundary), that `pre-commit install` would corrupt
>   host-side commits through the shared `.git`, that guarding the `rm` alone still let
>   `ln` silently half-succeed, and that the `${devcontainerId}`-suffixed token name
>   added in round 2 was a net negative — now reverted.
>
> Findings checked and confirmed **not** to apply: the pre-existing-session-directory
> claim, the `${devcontainerId}`-timing claim, the `mounts`+compose-incompatibility
> claim, and the marketplace-name-mismatch claim — reasoning kept in place so they are
> not re-opened.

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
- **Not a worktree-per-container workflow.** See the constraint below — the devcontainer
  is opened on the **main clone**, once.

### 2.1 Load-bearing constraint: git worktrees do not cross the container boundary

A linked worktree's `.git` is a *file* holding an **absolute** path, e.g.
`gitdir: /home/davor/projects/PhD/defendable-science/.git/worktrees/agent-a091f09…`
(verified against every current worktree in this repo). Absolute host paths do not
resolve inside the container, where the repo is at `/workspaces/defendable-science`. So:

- Opening the devcontainer **on a worktree folder** breaks git entirely inside it —
  every git command reports "not a git repository", which also takes out `pre-commit`,
  `create-pr`, and committing. This is not supported.
- Even from a main-clone-mounted container, the worktrees nested under
  `.claude/worktrees/` are visible but non-functional, for the same reason.
- The converse also holds: a worktree created *inside* the container records a
  `/workspaces/...` gitdir and is then broken on the host.

**Therefore the devcontainer is opened on the main clone, once.** Worktree-based
parallelism (this repo's established host-side posture) stays a **host-side** workflow;
inside the container, work on branches. This is a property of git's absolute worktree
links, not something the devcontainer configuration can paper over — the only
workarounds are mounting the host clone at its identical absolute host path (hardcodes
one machine's layout) or rewriting gitdir pointers on entry (fragile, and corrupts the
host's view). Neither is worth it.

This constraint is what makes the `${devcontainerId}`-keyed volumes below bounded:
one devcontainer per checkout, one stable ID across rebuilds, one set of volumes.

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
  post-create.sh            # postCreateCommand: pre-commit install-hooks, plugin provisioning
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
  exercise real rclone), and `ghcr.io/devcontainers-extra/features/uv:1` — a Feature
  instead of mononet's hand-rolled `curl -LsSf https://astral.sh/uv/install.sh` step, so
  every tool in the container is declared and pinned in one place rather than one of
  them drifting inside a shell script. (Both `devcontainers-extra` Features were
  confirmed to exist on GHCR.)
- **Required companion change (reviewed, fixed).** Earlier drafts justified the Feature
  choice by saying Dependabot already tracks Feature versions "the same way it tracks
  Actions". That is **false as written**: `.github/dependabot.yml` declares only `uv`,
  `github-actions`, and `pre-commit`, and ADR-0036 scopes Dependabot to exactly those
  three. Without a fourth entry the `:1`/`:2` Feature pins drift exactly like the curl
  install they replaced. Implementing this design therefore **must** add
  `package-ecosystem: "devcontainers"` (`directory: "/"`) to `.github/dependabot.yml`,
  following the cooldown/grouping conventions ADR-0036 established for the other three.
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

   **Slug rule: `sed 's#[^a-zA-Z0-9]#-#g'` (twice revised).** mononet's
   `host-init.sh:44` uses `sed 's#/#-#g'` (slashes only), which is wrong. An earlier
   revision of this spec narrowed the fix to `[/._]`, which is *also* wrong — Claude
   Code replaces **every** non-alphanumeric character, not a fixed set. Two empirical
   checks against this machine's real `~/.claude/projects/`:

   | Host path | Real project directory |
   | --- | --- |
   | `…/defendable-science/.claude/worktrees/curried-plotting-harp` | `-home-…-defendable-science-`**`-`**`claude-worktrees-curried-plotting-harp` (double dash, from `/.`) |
   | `…/.claude/worktrees/scope`**`+`**`arxiv-query-escaping` | `…-claude-worktrees-scope`**`-`**`arxiv-query-escaping` (the `+` became `-`) |

   The second case rules out `[/._]` outright — that rule leaves the `+` intact and
   matches nothing. `[^a-zA-Z0-9]` reproduces both directory names exactly and is a
   strict superset of everything observed, so it is what the script uses. (The `_` case
   is untested — no path on this machine contains one — but it is covered by the
   general rule rather than assumed away.)

   This also protects paths containing a space, `@`, or `~`, none of which the narrower
   rules handle.

   **Failure honesty (added).** Because the slug rule is inferred from observed
   behavior rather than a documented contract, `host-init.sh` must not fail silently if
   Claude Code's encoding changes: after computing `<host-slug>`, if the directory did
   **not** already exist, it prints an explicit `WARNING: … computed session dir did not
   exist (slug rule may have changed); sessions may not be shared` before creating it.
   A first-ever use of a given path legitimately hits this too, so it is a warning, not
   an error — but a silent mismatch becomes visible instead of looking like the feature
   merely "doesn't work". This follows `CLAUDE.md`'s failure-honesty rule: never let a
   failure surface as a legitimate-looking empty result.

   **Fallback must not destroy transcripts, and must not silently half-succeed
   (revised twice).** mononet's `host-init.sh:45` does `rm -rf "${SESSION_LINK}"`
   unconditionally before re-linking. That is unsafe here given the documented fallback:
   if a first open cannot create the symlink, a **plain directory** is created at
   `SESSION_LINK` and the container writes real transcripts into it; a later open's
   `rm -rf` would then delete them. So the removal is symlink-guarded.

   But guarding the `rm` alone is not enough, and the previous revision stopped there:
   with a plain directory left in place, a following `ln -sfn TARGET "${SESSION_LINK}"`
   **succeeds** — `-n` only prevents dereferencing when the destination is itself a
   symlink-to-directory, so against a real directory `ln` just creates the link *inside*
   it (`${SESSION_LINK}/<basename-of-target>`). The script would exit 0 looking wired up
   while the bind mount serves the plain directory and sharing is quietly dead. The
   required logic is therefore three-branch:

   ```bash
   if [ -L "${SESSION_LINK}" ]; then
       rm -f "${SESSION_LINK}"                 # stale link: replace it
   elif [ -e "${SESSION_LINK}" ]; then         # real dir/file: never delete, never ln
       echo "WARNING: ${SESSION_LINK} exists and is not a symlink; leaving it in place." >&2
       echo "WARNING: host/container session sharing is DISABLED until it is resolved." >&2
       exit 0
   fi
   ln -sfn "${CLAUDE_PROJECTS}/${host_slug}" "${SESSION_LINK}"
   ```

   Container start is still never blocked — sharing is simply, and *visibly*,
   unavailable until resolved by hand.

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
`~/.config/defendable-science-devcontainer/gh-token` (mode 0600) — **(reverted)** a
single filename, as in mononet, *not* the `${devcontainerId}`-suffixed name a previous
revision introduced. That suffix was added to prevent concurrent devcontainers from
overwriting each other's token, and on review it bought nothing while costing two real
things:

- **It solved a non-problem.** `gh auth token` is a property of the *host user*, not of
  a checkout: every devcontainer writes the identical value, so a "race" between two
  writers is two processes writing the same bytes.
- **It implied an isolation that does not exist.** What is bind-mounted read-only is
  the whole **directory**, so a per-ID filename never hid one container's token from
  another; any container could read every `gh-token-*`. Per-ID naming would have
  advertised a boundary that isn't there.
- **It leaked.** Nothing ever reclaimed the suffixed files, so plaintext OAuth tokens
  would accumulate one per devcontainer ID, forever. The single-filename scheme
  self-cleans: mononet's `host-init.sh:22` `rm -f`s the token when the host has none,
  and every run overwrites it otherwise.

The `claude-session-${devcontainerId}` symlink **keeps** its per-ID suffix, because
unlike the token its *target* genuinely differs per checkout.

**The directory** (not an individual file) is
what's bind-mounted **read-only** into the container, at
`/var/run/devcontainer-host-secrets`; `install_common_tools.sh` reads
`/var/run/devcontainer-host-secrets/gh-token` — mononet's
`HOST_TOKEN_FILE="/var/run/devcontainer-host-secrets/gh-token"`
(`install_common_tools.sh:95`) now carries over **unchanged**, since the filename is
once again unsuffixed. Because the mounted path is always a directory that exists, a
host with no `gh` token simply has no such file inside it — not a missing bind-mount
source — so the `[ -s "${HOST_TOKEN_FILE}" ]` check degrades cleanly.
`gh`/`create-pr`/`create-issue` then work inside the container without
re-authenticating; non-fatal if the host has no `gh` token.

**`containerEnv` (two variables, both required).**

| Variable | Value | Why |
| --- | --- | --- |
| `CLAUDE_CONFIG_DIR` | `/home/vscode/.claude` | Carried over from mononet's `default/devcontainer.json`. The volume-ownership loop in `install_common_tools.sh` reads `"${CLAUDE_CONFIG_DIR:-}"` behind an `[ -n … ]` guard, so if this is unset the root-owned `~/.claude` volume is **silently** never chowned — no error, then a failing Claude-CLI install and plugin provisioning later in `post-create.sh`. |
| `UV_CACHE_DIR` | `/home/vscode/.local/share/uv/cache` | Redirects `uv`'s wheel/download cache (default `~/.cache/uv`) **into** the persisted `uv` volume of §3.4, so a rebuild doesn't re-download and re-build every wheel. One volume then covers both interpreters and the wheel cache; no third volume needed. **Accepted cost:** this puts the cache on a different mount from the `.venv` volume, and `linkat` returns `EXDEV` across mounts, so `uv sync` cannot hardlink cache→venv and prints "Failed to hardlink files; falling back to full copy" on each sync. Downloads and wheel *builds* are still cached — only the final copy is not free. Colocating them would mean giving up either the container-private `.venv` or the persisted cache; the copy is the cheaper concession. |

A `DEVCONTAINER_ID` variable is **no longer needed** — it existed only to let
`install_common_tools.sh` find a `${devcontainerId}`-suffixed token file, and that
suffix is reverted above.

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
fresh container.

It must further gain **`${CLAUDE_CONFIG_DIR}/projects`**, which is easy to miss because
it is not itself a mount. Docker creates it as the *parent* of the nested session
bind-mountpoint (`…/projects/-workspaces-defendable-science`, §3.3), so it materializes
root-owned inside the `~/.claude` volume — and mononet's chown is **non-recursive**
(`install_common_tools.sh:23`, `sudo chown "$(id -u):$(id -g)" "${_vol}"`), so chowning
`/home/vscode/.claude` does not reach it. Concrete failure: `cd defendable-science &&
claude` — the working directory `CLAUDE.md` prescribes for package work, and one this
machine already has a host project directory for — makes Claude Code try to create
`~/.claude/projects/-workspaces-defendable-science-defendable-science` and get `EACCES`.

**And it must claim the parents, not just the leaves.** Docker creates every
missing directory on the way to a mountpoint, also root-owned, and this chown is
non-recursive. `/home/vscode/.local` and `/home/vscode/.local/share` (parents of the
`uv` volume) and `/home/vscode/.cache` (parent of the pre-commit volume) are therefore
in scope too — and `~/.local` doubly so, because the Claude CLI installer writes to
`~/.local/bin`, so a root-owned `~/.local` kills `install_common_tools.sh` itself.

`CLAUDE_CONFIG_DIR` must be dereferenced **once, up front**, never interpolated inline:
`"${CLAUDE_CONFIG_DIR:-}/projects"` expands to the literal `/projects` when the variable
is unset, which sails past an `[ -n … ]` guard and creates a root-owned directory at the
filesystem root while the chown that mattered still never runs.

The full list is seven paths — three volume mountpoints, three parents, and the
non-mount `projects/` directory (the `~/.claude` volume itself is the fourth mountpoint,
added conditionally). Each needs `mkdir -p` before the writability test, since `[ -w ]`
is false for a mountpoint Docker has not created yet:

```bash
_claim_paths=()
if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
  _claim_paths+=("${CLAUDE_CONFIG_DIR}" "${CLAUDE_CONFIG_DIR}/projects")
else
  echo "WARNING: CLAUDE_CONFIG_DIR unset; the ~/.claude volume cannot be claimed." >&2
fi
_claim_paths+=(
  /home/vscode/.local
  /home/vscode/.local/share
  /home/vscode/.local/share/uv
  /home/vscode/.cache
  /home/vscode/.cache/pre-commit
  /workspaces/defendable-science/defendable-science/.venv
)
```

The `MONONET_EXTRAS`-driven `install_dependencies.sh` call is dropped (this repo has one
dependency set, installed directly via `uv sync`, not mononet's per-flavor extras
matrix); `git-lfs` is dropped from the apt package list (unused — no `.gitattributes`
LFS rules in this repo); the `curl`-based `uv` install step is dropped (now a Feature,
§3.2). The `HOST_TOKEN_FILE` line is left **unchanged** (§3.3 reverted the per-ID token
suffix, so mononet's unsuffixed path is correct again). The
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
own `.venv` volume.

**Host-side hazard.** This target nests *inside* the workspace bind mount, so on a
checkout where `defendable-science/.venv` does not yet exist, Docker creates the mount
destination in the **host** tree, owned by root — after which the host's own
`cd defendable-science && uv sync` fails with a permission error. The directory is
gitignored, so `git status` never shows it. `host-init.sh` therefore pre-creates it as
the host user, and the verification plan checks its ownership. Switching `--python` versions against this shared venv makes `uv`
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

**(reviewed, fixed)** A third named volume,
`source=defendable-science-precommit-${devcontainerId},target=/home/vscode/.cache/pre-commit,type=volume`,
persists the `pre-commit` hook environments built by §3.5's `install-hooks`. Same
argument as the `uv` volume, and `ci.yml:29` caches this exact path for the same reason:
without it every `devcontainer rebuild` rebuilds every hook environment from scratch.
It too is in the ownership-claiming loop above, along with its parent
`/home/vscode/.cache`.

**Volume inventory (four).** All are keyed by `${devcontainerId}`; §2.1's one-container
constraint is what keeps that bounded, since the ID is stable across rebuilds:
`…-claude-config-*` (`~/.claude`), `…-venv-*` (the project venv), `…-uv-*` (interpreters
+ wheel cache), `…-precommit-*` (hook environments). Should a devcontainer ever be
created for a second checkout, its volumes are independent and are reclaimed with
`docker volume rm` — nothing in the lifecycle scripts prunes them automatically.

### 3.5 Claude plugin provisioning

`post-create.sh` (`postCreateCommand`, which runs after the workspace is bind-mounted —
`pre-commit` needs to read `.pre-commit-config.yaml` from the checkout, though note it
deliberately does *not* write into `.git`, see below) runs, in order:

1. `uv run --project defendable-science --group lint pre-commit install-hooks` (from the
   repo root, so `pre-commit` reads `.pre-commit-config.yaml` there — the working
   directory `ci.yml`'s `pre-commit` job uses).

   **(revised) `install-hooks`, deliberately not `install`.** `pre-commit install`
   writes `.git/hooks/pre-commit`, and `.git` is on the **bind-mounted, host-shared**
   checkout. The generated hook embeds an absolute
   `INSTALL_PYTHON = '/workspaces/defendable-science/defendable-science/.venv/bin/python'`
   — a path that does not exist on the host. Running the container once would therefore
   degrade *host-side* `git commit`, which is a direct regression against this design's
   premise of concurrent host and container work on one checkout. `pre-commit
   install-hooks` is the right primitive: it builds the hook **environments** (the
   expensive part) and touches nothing in `.git`. Whichever side wants git-triggered
   hooks runs `pre-commit install` there itself, once, and owns that choice.

   Two corrections to earlier drafts that stand: `ci.yml` never runs `pre-commit
   install` at all (only `pre-commit run --hook-stage manual --all-files`), so no
   "matches CI" claim applies to it; and had we kept `install`, a bare invocation
   registers only the `pre-commit` hook type, while `.pre-commit-config.yaml`'s
   `default_stages: [pre-commit, pre-merge-commit]` would additionally require
   `--hook-type pre-merge-commit`.

   `install-hooks` writes to `~/.cache/pre-commit`, which needs its own named volume
   (§3.4) — `ci.yml:29` caches exactly that path because rebuilding every hook
   environment (ruff, mypy, codespell, bandit, detect-secrets, pyupgrade) is expensive,
   and otherwise `devcontainer rebuild` would redo all of it every time.
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
  without re-downloading (proves the `uv` volume persisted); and
  `pre-commit run --all-files` starts without rebuilding hook environments (proves the
  `pre-commit` cache volume persisted).
- **Slug rule, in isolation and before any container is built** (no Docker needed, and
  the check that would have caught two rounds of slug bugs): run `host-init.sh`'s
  transform over *every* real directory this machine has under `~/.claude/projects/`
  and assert each computed slug names an existing directory. The corpus must include
  the two adversarial paths already present here — one containing `/.` (double dash)
  and one containing `+` — since those are exactly what falsify the slash-only and
  `[/._]` rules respectively.
- **Fallback safety, both branches:**
  - With a plain (non-symlink) directory placed at a `claude-session-*` stable path,
    re-run `host-init.sh`; confirm the directory and its contents still exist, that a
    warning was printed, and — critically — that **no symlink was created inside it**
    (the `ln` must be skipped, not merely the `rm`).
  - With a stale *symlink* there, re-run and confirm it is silently replaced.
- **Shared-`.git` safety:** after `postCreateCommand` completes, confirm on the **host**
  that `.git/hooks/pre-commit` is either absent or still the host's own — i.e. the
  container ran `install-hooks` and never wrote a container-only `INSTALL_PYTHON` path
  into the shared checkout. Then run `git commit` on the host and confirm it behaves
  exactly as before the container existed.
- **Worktree constraint (§2.1), documented rather than supported:** confirm that opening
  the devcontainer on a `.claude/worktrees/*` folder does fail as described (git reports
  "not a git repository"), so the constraint is a known, reproducible property rather
  than a surprise for a future maintainer.
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
  `git`/`github-cli`/`rclone` as Features, so one declaration site covers every tool
  instead of one drifting inside a shell script. Note this only *becomes* a version-
  tracking argument once `.github/dependabot.yml` gains a `devcontainers` ecosystem
  (§3.2, required companion change) — today it tracks only `uv`, `github-actions`, and
  `pre-commit`.
- **Wire the shell prompt via the devcontainer `dotfiles` mechanism instead of a
  committed script.** Rejected: `dotfiles.repository` pulls a *personal* dotfiles repo
  — a second person, or the author on a machine without that repo configured, opening
  this devcontainer would get no prompt at all. A script committed under
  `.devcontainer/` ships with the repo and works for anyone who opens it.
- **Separate `.venv` per Python version instead of one shared, rebuilt-in-place venv.**
  Rejected as unneeded complexity: switching `--python` only happens when deliberately
  reproducing a specific CI leg, not routinely: a rebuild-in-place cost on those
  occasions is acceptable against the cost of managing four persistent venvs.
