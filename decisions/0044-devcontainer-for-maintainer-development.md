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
  and background agents run against this repo at once, per established practice) — which
  turns out to mean keeping worktrees *out* of the container, see Consequences.

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
**Features** rather than hand-rolled install scripts, so every tool in the container is
declared and pinned in one place. This decision *requires* adding a
`package-ecosystem: "devcontainers"` entry to `.github/dependabot.yml`: ADR-0036 scoped
Dependabot to `uv`, `github-actions`, and `pre-commit` only, so without that fourth
entry the Feature pins would drift exactly like the curl install they replace.

Two independent mechanisms carry over from mononet, adapted:

- **Config persistence**: `~/.claude` is a named Docker volume, not the container's
  writable layer, so `devcontainer rebuild` doesn't wipe installed plugins/auth.
- **Session sharing**: a host-side `initializeCommand` script points a
  `${devcontainerId}`-scoped stable path at the *real* host Claude project directory
  for the cwd the devcontainer was opened from (via `mkdir -p` + `ln -sfn` — the real
  directory is only ever the symlink's *target*, never replaced, so a directory that
  already holds real session data is untouched and safe; the stable path itself is
  removed only when it is a symlink, so a fallback directory holding real transcripts is
  never `rm -rf`'d the way mononet's unconditional removal would). That stable path is
  bind-mounted onto the container's own project slug.

  **Two** directories are wired, not one. Claude Code keys transcripts by the directory
  a session was *launched from*, and CLAUDE.md prescribes `cd defendable-science` for
  package work — so wiring only the workspace root would leave the repo's primary
  working directory silently unshared. Sharing is therefore scoped to those two
  directories of the exact host path the container was opened from. Opening from a git
  worktree would share with that worktree rather than the main clone, matching Claude
  Code's own per-directory project model (verified: worktrees already get distinct
  directories under `~/.claude/projects/`, independent of any devcontainer) — though
  §2.1's constraint means the container is opened on the main clone anyway.

  The host-path→project-directory encoding is **every non-alphanumeric character** →
  `-` (`sed 's#[^a-zA-Z0-9]#-#g'`), not mononet's slash-only `sed 's#/#-#g'` and not the
  narrower `[/._]` an intermediate revision of this ADR recorded. Verified against two
  real entries under this machine's `~/.claude/projects/`: a path containing `/.` yields
  a *double* dash, and one containing `+` yields `-` — the latter rules out `[/._]`
  outright. Since the encoding is inferred from observed behavior rather than a
  documented contract, the script warns explicitly when the computed directory did not
  already exist, so a future divergence surfaces instead of silently sharing nothing
  (`CLAUDE.md` failure-honesty rule).

Full design, file layout, and the per-script adaptation-from-mononet details are in
`docs/superpowers/specs/2026-08-30-devcontainer-design.md`.

## Consequences

- A maintainer can `uv run --python 3.11..3.14` any CI leg locally (from
  `defendable-science/`, matching CI's own `working-directory`) with no host Python
  management.
- Plugins/auth survive rebuilds; session history is continuous across host/container
  boundaries for a given host path.
- Using Features for `uv`/`git`/`github-cli`/`rclone` puts their versions in one
  declared, pinnable place instead of a shell script — **conditional on** the new
  `devcontainers` Dependabot ecosystem landing with it (ADR-0036's scope does not
  currently cover Features) **and** on the Features being pinned to exact versions.
  A floating `:1`/`:2` tag has no minor/patch component for a `["minor","patch"]` group
  to match, so floating pins would leave the ecosystem entry tracking nothing — the very
  drift it was added to prevent.
- Three named volumes beyond `~/.claude` are needed: the project's `.venv` (container-
  private, avoids colliding with the bind-mounted source tree), `uv`'s state dir
  (`~/.local/share/uv`, with `UV_CACHE_DIR` redirected inside it so the wheel cache is
  covered too), and `~/.cache/pre-commit` (hook environments). Without them a rebuild
  re-downloads the whole interpreter matrix, rebuilds every wheel, and rebuilds every
  pre-commit hook environment — the last is why `ci.yml` caches that exact path.
- Every named volume is created root-owned, so each must be listed in
  `install_common_tools.sh`'s ownership-claiming loop — **and so must every parent
  directory Docker had to create on the way to one**, since the chown is non-recursive:
  `${CLAUDE_CONFIG_DIR}/projects` (parent of the nested session bind-mountpoints),
  `~/.local` and `~/.local/share` (parents of the `uv` volume), and `~/.cache` (parent
  of the pre-commit volume). `~/.local` matters twice over, because the Claude CLI
  installer writes to `~/.local/bin`. Note also that the package
  lives one level below the repo root here (unlike mononet, where they coincide), so
  mononet's script cannot be adapted by path substitution alone — the `.venv` path
  differs structurally, not just by name.
- The forwarded `gh` auth token uses a **single** filename (as in mononet), not a
  `${devcontainerId}`-suffixed one: the token is a property of the host *user*, so
  concurrent writers write identical bytes; the read-only bind mount exposes the whole
  directory anyway, so per-ID naming would imply an isolation that does not exist; and
  unsuffixed names self-clean instead of accumulating plaintext tokens forever.
- The base image's `PATH` omits `~/.local/bin`, where the Claude CLI installs, so it is
  prepended via `remoteEnv` *and* exported inside `install_common_tools.sh`, which then
  asserts `command -v claude` rather than trusting it. Without this the container would
  build green with no plugins at all, since every consumer of `claude` downstream is
  non-fatal by design.
- `~/.claude/settings.json` is bind-mounted from the host so both sides share one file
  (theme, `env`, enabled plugins). That is only coherent alongside a second, **read-only**
  bind of the repo at its own host path (`${localWorkspaceFolder}` → identical target):
  `settings.json` records this repo's plugin marketplace as an absolute `"directory"`
  path, and one file cannot hold two. Read-only because the `.venv` volume is mounted
  under the `/workspaces` view only, so the second view would otherwise expose the host's
  `.venv` for writing.
- `post-create.sh` runs `pre-commit install-hooks`, **not** `pre-commit install`:
  `.git` is shared with the host, and an installed hook embeds a container-only
  `INSTALL_PYTHON` path that would break host-side `git commit`. Building the hook
  environments is the part worth doing centrally; registering git hooks stays a
  per-side choice.
- Known, accepted limitation: the container's `vscode` user is a fixed uid 1000: this
  only works cleanly when the host user is also uid 1000 (true for this repo's sole
  maintainer; Linux's `updateRemoteUserUID` default mitigates the general case).

**Load-bearing constraint discovered during review:** a linked worktree's `.git` is a
file holding an *absolute* gitdir path, which cannot resolve inside the container. So the
devcontainer is opened on the **main clone, once**; worktree parallelism stays a
host-side workflow, and inside the container one works on branches. This is also what
bounds the `${devcontainerId}`-keyed volumes to a single set.

## Rejected alternatives

- **Skip session sharing; only persist the container's own `~/.claude`.** Rejected:
  explicitly wanted — continuity between host-side and container-side sessions on the
  same repo, not just survival across rebuilds.
- **Pin one Python version instead of the full CI matrix.** Rejected: the package ships
  to PyPI across 3.11–3.14 and CI tests all four; a devcontainer that reproduces only
  one of those legs leaves three untestable locally.
- **Hand-install `uv` via its curl script (mononet's approach).** Rejected in favor of
  the `devcontainers-extra/features/uv` Feature: this repo already uses Features for
  `git`/`github-cli`/`rclone`, so Features keep every tool declared in one place. The
  version-tracking benefit is not automatic: it requires the `devcontainers` Dependabot
  ecosystem this ADR mandates adding, since ADR-0036 covers only three ecosystems.
- **Ship the prompt/completion setup via the devcontainer `dotfiles` mechanism instead
  of a repo-committed script.** Rejected: `dotfiles.repository` pulls a *personal*
  dotfiles repo, so a second person (or the author on a machine without that repo
  configured) opening this devcontainer wouldn't get the prompt at all. A script
  committed to `.devcontainer/` ships with the repo and works for anyone who opens it.

## Links

`docs/superpowers/specs/2026-08-30-devcontainer-design.md` (the design); ADR-0036
(Dependabot scope — extended here by a required `devcontainers` ecosystem entry);
`davorrunje/mononet` `.devcontainer/`
(source pattern this adapts from); containers.dev devcontainer.json reference
(`${devcontainerId}` support matrix; `mounts` as "cross-orchestrator") consulted
2026-08-30.
