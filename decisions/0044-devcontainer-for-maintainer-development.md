# ADR-0044: A single-flavor devcontainer for maintainer development, with Claude Code session sharing between host and container

- Status: accepted · Date: 2026-08-30 · Deciders: Davor Runje

## Context

There was no devcontainer for this repo. Development happened directly on the host:
no reproducible, isolated toolchain across machines; Claude Code session/plugin state
lived only in the host's single `~/.claude`; and there was no container-local place to
exercise the full CI Python matrix (3.11–3.14, `defendable-science/pyproject.toml`)
without touching the host's own Python installs. The author has a working pattern in
`davorrunje/mononet` (`.devcontainer/{default,shared}/`), built for a much larger
project (multiple GPU flavors, Node, Docker-in-Docker).

This repo is maintainer-only tooling — CLAUDE.md's "Development posture" section is
explicit that this is not a shipped artifact, unlike the plugin/package split it
documents — so the bar is "works well for the one maintainer," not general-purpose
portability.

## Decision drivers

- Reproduce CI's Python matrix locally without touching the host's Python installs.
- Persist Claude Code plugins/auth across `devcontainer rebuild`.
- Share Claude Code session transcripts between host-side and container-side work on
  the same repo, not just persist the container's own copy.
- Reuse the proven mononet pattern where it fits; drop everything it needs that this
  repo does not (GPU flavors, Node, Docker-in-Docker).
- Stay correct for this repo's actual concurrent-worktree workflow (several sessions
  and background agents run against this repo at once, per established practice).

## Considered options

1. **No devcontainer** — status quo. Rejected outright; this ADR exists because the
   drivers above are unmet.
2. **Copy mononet's multi-flavor layout (`default/` + `shared/`) wholesale.** The split
   exists there solely so GPU flavors can share scripts with the CPU flavor; this repo
   has one toolchain, so copying the split would be structure with no second flavor to
   justify it.
3. **Single-flavor devcontainer, mononet's persistence/sharing mechanisms adapted down
   to this repo's needs.** *(chosen)*

## Decision

A single `.devcontainer/` (no flavor split), `mcr.microsoft.com/devcontainers/python:3.14`
base image (matches `pyproject.toml`'s `requires-python = ">=3.11,<3.15"` upper bound),
with `common-utils`, `git`, `github-cli`, `rclone`, and `uv` supplied as devcontainer
**Features** rather than hand-rolled install scripts, matching this repo's existing
preference for tool-managed dependencies (Dependabot tracks Feature versions the same
way it tracks Actions, per ADR-0036).

Two independent mechanisms carry over from mononet, adapted:

- **Config persistence**: `~/.claude` is a named Docker volume, not the container's
  writable layer, so `devcontainer rebuild` doesn't wipe installed plugins/auth.
- **Session sharing**: a host-side `initializeCommand` script points a
  `${devcontainerId}`-scoped stable path at the *real* host Claude project directory
  for the cwd the devcontainer was opened from (via `mkdir -p` + `ln -sfn` — the real
  directory is only ever the symlink's *target*, never replaced, so a directory that
  already holds real session data is untouched and safe). That stable path is bind-
  mounted onto the container's own project slug. Sharing is therefore scoped to the
  **exact host path** the container was opened from — opening from a git worktree
  shares with sessions run from that worktree, not from the main clone, which matches
  Claude Code's own existing per-directory project model (verified: worktrees already
  get distinct directories under `~/.claude/projects/`, independent of any devcontainer
  involvement).

Full design, file layout, and the per-script adaptation-from-mononet details are in
`docs/superpowers/specs/2026-08-30-devcontainer-design.md`.

## Consequences

- A maintainer can `uv run --python 3.11..3.14` any CI leg locally (from
  `defendable-science/`, matching CI's own `working-directory`) with no host Python
  management.
- Plugins/auth survive rebuilds; session history is continuous across host/container
  boundaries for a given host path.
- Using Features for `uv`/`git`/`github-cli`/`rclone` means their versions are
  Dependabot-tracked (ADR-0036) instead of hand-maintained in a shell script.
- Two named volumes beyond `~/.claude` are needed: the project's `.venv` (container-
  private, avoids colliding with the bind-mounted source tree) and `uv`'s Python-
  install cache (`~/.local/share/uv`) — without the latter, every rebuild re-downloads
  the whole interpreter matrix.
- The forwarded `gh` auth token is scoped by `${devcontainerId}` (not a single shared
  file) so concurrent devcontainers opened from different worktrees don't race to
  overwrite each other's token.
- Known, accepted limitation: the container's `vscode` user is a fixed uid 1000: this
  only works cleanly when the host user is also uid 1000 (true for this repo's sole
  maintainer; Linux's `updateRemoteUserUID` default mitigates the general case).

## Rejected alternatives

- **Skip session sharing; only persist the container's own `~/.claude`.** Rejected:
  explicitly wanted — continuity between host-side and container-side sessions on the
  same repo, not just survival across rebuilds.
- **Pin one Python version instead of the full CI matrix.** Rejected: the package ships
  to PyPI across 3.11–3.14 and CI tests all four; a devcontainer that reproduces only
  one of those legs leaves three untestable locally.
- **Hand-install `uv` via its curl script (mononet's approach).** Rejected in favor of
  the `devcontainers-extra/features/uv` Feature: this repo already uses Features for
  `git`/`github-cli`/`rclone`, and a Feature gets picked up by the same Dependabot
  update path as the rest of the toolchain, instead of drifting silently in a script.
- **Ship the prompt/completion setup via the devcontainer `dotfiles` mechanism instead
  of a repo-committed script.** Rejected: `dotfiles.repository` pulls a *personal*
  dotfiles repo, so a second person (or the author on a machine without that repo
  configured) opening this devcontainer wouldn't get the prompt at all. A script
  committed to `.devcontainer/` ships with the repo and works for anyone who opens it.

## Links

`docs/superpowers/specs/2026-08-30-devcontainer-design.md` (the design); ADR-0036
(Dependabot tracks Feature/Action versions); `davorrunje/mononet` `.devcontainer/`
(source pattern this adapts from); containers.dev devcontainer.json reference
(`${devcontainerId}` support matrix; `mounts` as "cross-orchestrator") consulted
2026-08-30.
