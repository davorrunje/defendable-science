# Devcontainer for Maintainer Development — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single-flavor Python 3.14 devcontainer to this repo whose Claude Code plugins/auth survive `devcontainer rebuild` and whose session transcripts are shared with host-side Claude sessions on the same checkout.

**Architecture:** `.devcontainer/` holds one `devcontainer.json` (compose-based) plus seven shell scripts split by lifecycle phase: `host-init.sh` runs on the **host** before the container exists (forwards the `gh` token, wires the session symlink); `setup.sh` runs as `updateContentCommand` (tool install + Python matrix + `uv sync`); `post-create.sh` runs as `postCreateCommand` (hook environments, shell prompt, Claude plugins). The one piece of non-trivial logic — deriving Claude Code's project-directory name from a host path — is isolated in its own file, `claude-project-slug.sh`, so it can be unit-tested without Docker. Four named volumes carry the state that must outlive a rebuild.

**Tech Stack:** Dev Containers spec (`dockerComposeFile`, `mounts`, `containerEnv`, `${devcontainerId}`), Docker Compose, devcontainer Features (`common-utils`, `git`, `github-cli`, `rclone`, `uv`), `uv`, `pre-commit`, `gh`, `bash`, ShellCheck.

**Spec:** [`docs/superpowers/specs/2026-08-30-devcontainer-design.md`](../specs/2026-08-30-devcontainer-design.md) — approved, and revised over three review rounds. **Read it before starting**; it records the *why* for every decision below, including several that look arbitrary but are not (the slug rule, `install-hooks` vs `install`, the unsuffixed token filename). ADR: [`decisions/0044-devcontainer-for-maintainer-development.md`](../../../decisions/0044-devcontainer-for-maintainer-development.md).

## Global Constraints

- **Never commit to `main`.** Work continues on the existing branch `feature/devcontainer-design`, which already carries the spec + ADR commits (`f0f0acc`, `58987a7`, `b3b113d`, `88a449d`, `c1bd5c6`). Open a PR at the end; do not merge it.
- **Commit attribution:** author `Davor Runje <davor@synthpop.ai>` with a `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` trailer. Conventional-Commits subjects (`feat`, `build`, `ci`, `docs`, `test`).
- **This is maintainer tooling, not a shipped artifact.** Nothing in `.devcontainer/` may leak into the plugin's domain-neutral content (`skills/`, `resources/`, `.claude-plugin/`). Do not bump `.claude-plugin/plugin.json`.
- **No Python package source changes.** `defendable-science/` is untouched except `pyproject.toml`'s `lint` group (Task 3 only). The 100%-coverage gate is therefore unaffected — but still run `cd defendable-science && uv run pytest -q` before the PR.
- **Exact container paths** (used verbatim in many files; a typo silently disables a feature):
  - workspace: `/workspaces/defendable-science`
  - package/venv: `/workspaces/defendable-science/defendable-science/.venv`
  - Claude config: `/home/vscode/.claude`
  - session bind target: `/home/vscode/.claude/projects/-workspaces-defendable-science`
  - `uv` state: `/home/vscode/.local/share/uv` · `uv` cache: `/home/vscode/.local/share/uv/cache`
  - pre-commit cache: `/home/vscode/.cache/pre-commit`
  - host secrets (read-only): `/var/run/devcontainer-host-secrets`
- **Exact host paths:** secrets dir `${HOME}/.config/defendable-science-devcontainer`; token `${HOME}/.config/defendable-science-devcontainer/gh-token` (**no** `${devcontainerId}` suffix); session link `${HOME}/.config/defendable-science-devcontainer/claude-session-${devcontainerId}` (**with** the suffix).
- **The slug rule is `sed 's#[^a-zA-Z0-9]#-#g'`.** Not `s#/#-#g` (mononet's), not `s#[/._]#-#g`. Both narrower rules were tried and falsified against real directories on this machine. See spec §3.3.
- **`pre-commit install-hooks`, never `pre-commit install`.** `.git` is bind-mounted and shared with the host; `install` writes a hook embedding a container-only interpreter path and breaks host-side `git commit`.
- **Every lifecycle script is failure-honest.** `host-init.sh` and `provision-claude-plugins.sh` must never block container start — they warn to stderr and `exit 0`. `setup.sh`/`post-create.sh` use `set -euo pipefail` and *are* allowed to fail loudly. Never let a broken state look like a working one (repo `CLAUDE.md` rule).
- **Reference material:** mononet's originals are checked out locally at `/home/davor/projects/PhD/mononet/.devcontainer/shared/`. Read them, but do not copy any file verbatim without applying the adaptations the spec names.
- Repo checks before the PR: `pre-commit run --all-files` and `./tools/validate-plugin.sh` from the repo root.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `.devcontainer/claude-project-slug.sh` | create | **Pure function.** Prints Claude Code's project-directory name for a filesystem path. The only non-obvious logic in the feature; isolated so it is unit-testable with no Docker. |
| `.devcontainer/host-init.sh` | create | Host-side `initializeCommand`. Forwards the `gh` token; points the session stable-path at the real host project dir. Best-effort, never blocks. |
| `.devcontainer/tests/test-claude-project-slug.sh` | create | Table-driven tests for the slug rule, including the two adversarial real paths. |
| `.devcontainer/tests/test-host-init.sh` | create | Tests `host-init.sh` against a fake `$HOME`: token write/remove, symlink create/replace, and the must-not-destroy branches. |
| `.devcontainer/docker-compose.yml` | create | One service, the base image, the workspace bind mount. |
| `.devcontainer/devcontainer.json` | create | Features, the four named volumes + two host binds, `containerEnv`, lifecycle hooks, VS Code customizations. |
| `.devcontainer/install_common_tools.sh` | create | Claims ownership of root-owned volume mountpoints; installs interactive-shell tooling; authenticates `gh`; installs the `claude` CLI. |
| `.devcontainer/setup.sh` | create | `updateContentCommand`: calls `install_common_tools.sh`, prefetches the CI Python matrix, `uv sync`. |
| `.devcontainer/shell-prompt.sh` | create | Git-aware prompt + completion, sourced by shell rc files. |
| `.devcontainer/install-shell-prompt.sh` | create | Idempotently wires the above into `~/.bashrc` / `~/.zshrc`. |
| `.devcontainer/claude-plugins.txt` | create | Two-column plugin manifest. |
| `.devcontainer/provision-claude-plugins.sh` | create | Reads the manifest, adds marketplaces, installs plugins. Non-fatal. |
| `.devcontainer/post-create.sh` | create | `postCreateCommand`: hook environments, shell prompt, plugin provisioning. |
| `tools/shellcheck.sh` | create | Repo-root ShellCheck entry point, matching `tools/lint.sh`'s shape. |
| `.pre-commit-config.yaml` | modify | Add a local `shellcheck` hook. |
| `defendable-science/pyproject.toml` | modify | Add `shellcheck-py` to the `lint` group (single version pin, per ADR-0036/issue #79). |
| `.github/workflows/ci.yml` | modify | New `devcontainer-scripts` job; add it to `check.needs`. |
| `.github/dependabot.yml` | modify | Add the `devcontainers` ecosystem (required by ADR-0044). |
| `CONTRIBUTING.md` | modify | Short "Devcontainer" section pointing at the spec and stating the worktree constraint. |

Deliberately unchanged: all package source, `skills/`, `resources/`, `.claude-plugin/`, `.claude/settings.json`.

---

### Task 1: `claude-project-slug.sh` and its tests

The slug rule was got wrong twice during design review. It gets its own file and its own table-driven test so a third mistake is caught in one second, with no Docker.

**Files:**
- Create: `.devcontainer/claude-project-slug.sh`
- Test: `.devcontainer/tests/test-claude-project-slug.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: an executable that prints the slug for its `$1` (defaulting to `$PWD`) on stdout, exit 0. Task 2's `host-init.sh` calls it as `"${SCRIPT_DIR}/claude-project-slug.sh" "${PWD}"`.

- [ ] **Step 1: Write the failing test**

Create `.devcontainer/tests/test-claude-project-slug.sh`:

```bash
#!/usr/bin/env bash
# Tests for claude-project-slug.sh.
#
# The slug rule is inferred from Claude Code's observed behaviour, not from a
# documented contract, so the cases below are anchored on REAL directory names
# seen under ~/.claude/projects. Two of them are adversarial on purpose:
#   - a path containing '/.' must collapse to a DOUBLE dash
#   - a path containing '+'  must map the '+' to '-'
# Those two falsify the two rules that were tried and rejected during design
# review ('/'-only, and '[/._]'). See the design spec, section 3.3.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SLUG="${SCRIPT_DIR}/../claude-project-slug.sh"

failures=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n     expected: %s\n     actual:   %s\n' "$1" "$2" "$3"; failures=$((failures + 1)); }

assert_slug() {
    local desc=$1 input=$2 expected=$3 actual
    actual="$("${SLUG}" "${input}")"
    if [ "${actual}" = "${expected}" ]; then pass "${desc}"; else fail "${desc}" "${expected}" "${actual}"; fi
}

echo "== claude-project-slug.sh =="

assert_slug "plain repo path" \
    "/home/davor/projects/PhD/defendable-science" \
    "-home-davor-projects-PhD-defendable-science"

assert_slug "nested package dir" \
    "/home/davor/projects/PhD/defendable-science/defendable-science" \
    "-home-davor-projects-PhD-defendable-science-defendable-science"

# '/.claude' -> '--claude': the dot becomes a second dash.
assert_slug "dot-directory yields a double dash" \
    "/home/davor/projects/PhD/defendable-science/.claude/worktrees/curried-plotting-harp" \
    "-home-davor-projects-PhD-defendable-science--claude-worktrees-curried-plotting-harp"

# '+' is neither '/' nor '.' nor '_' -- this is the case that rules out [/._].
assert_slug "plus sign becomes a dash" \
    "/home/davor/projects/PhD/defendable-science/.claude/worktrees/scope+arxiv-query-escaping" \
    "-home-davor-projects-PhD-defendable-science--claude-worktrees-scope-arxiv-query-escaping"

assert_slug "underscore becomes a dash" \
    "/home/davor/my_projects/defendable-science" \
    "-home-davor-my-projects-defendable-science"

assert_slug "space becomes a dash" \
    "/home/davor/My Projects/defendable-science" \
    "-home-davor-My-Projects-defendable-science"

assert_slug "existing dashes and digits survive" \
    "/workspaces/defendable-science" \
    "-workspaces-defendable-science"

assert_slug "case is preserved" \
    "/home/davor/projects/PhD" \
    "-home-davor-projects-PhD"

# Defaults to $PWD when given no argument.
actual="$(cd / && "${SLUG}")"
if [ "${actual}" = "-" ]; then pass "defaults to \$PWD"; else fail "defaults to \$PWD" "-" "${actual}"; fi

# ---------------------------------------------------------------------------
# Corroboration against real directories, when this machine has them.
#
# Every directory under ~/.claude/projects was produced by Claude Code itself,
# so re-deriving one from its known source path is the strongest check
# available. The two paths below are the ADVERSARIAL ones: they are exactly
# what falsified the '/'-only rule and then the '[/._]' rule during design
# review. Skipped, not failed, on a machine without them (e.g. CI).
# ---------------------------------------------------------------------------
projects="${HOME}/.claude/projects"
repo_root="${HOME}/projects/PhD/defendable-science"
corroborated=0
for real in \
    "${repo_root}/.claude/worktrees/curried-plotting-harp" \
    "${repo_root}/.claude/worktrees/scope+arxiv-query-escaping"
do
    slug="$("${SLUG}" "${real}")"
    # The -n guard matters: an empty slug makes the -d test resolve to
    # "${projects}/" -- which exists -- so a broken or missing SLUG script would
    # otherwise report a false "ok" here.
    if [ -n "${slug}" ] && [ -d "${projects}/${slug}" ]; then
        pass "adversarial real path resolves: $(basename "${real}")"
        corroborated=$((corroborated + 1))
    fi
done
if [ "${corroborated}" -eq 0 ]; then
    echo "  skip corroboration (no known adversarial paths under ${projects})"
fi

echo
if [ "${failures}" -gt 0 ]; then echo "FAILED: ${failures}"; exit 1; fi
echo "all passed"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
bash .devcontainer/tests/test-claude-project-slug.sh
```

Expected: fails immediately — `claude-project-slug.sh` does not exist, so every `assert_slug` reports an empty actual value.

- [ ] **Step 3: Write the minimal implementation**

Create `.devcontainer/claude-project-slug.sh`:

```bash
#!/usr/bin/env bash
# Print Claude Code's project-directory name for a filesystem path.
#
# Claude Code stores each project's transcripts under
# ~/.claude/projects/<slug>, where <slug> is the absolute path with every
# NON-ALPHANUMERIC character replaced by '-'. So
#   /home/u/p/.claude/worktrees/a+b  ->  -home-u-p--claude-worktrees-a-b
# (note the double dash from '/.', and the '+' mapped to '-').
#
# This rule is inferred from observed behaviour, not a documented contract.
# Two narrower rules were tried during design review and falsified against real
# directories on the author's machine: mononet's '/'-only substitution, and
# '[/._]'. Anything narrower than "every non-alphanumeric" will eventually be
# wrong again, so the rule is deliberately the widest one consistent with all
# observations. host-init.sh warns when a computed slug names a directory that
# does not already exist, which is how a future divergence surfaces.
#
# Usage: claude-project-slug.sh [PATH]   (PATH defaults to $PWD)
set -euo pipefail

printf '%s' "${1:-${PWD}}" | sed 's#[^a-zA-Z0-9]#-#g'
```

- [ ] **Step 4: Make it executable and run the tests**

```bash
chmod +x .devcontainer/claude-project-slug.sh
bash .devcontainer/tests/test-claude-project-slug.sh
```

Expected: `all passed`. The "real path maps to an existing project dir" line should report `ok` for the repo you are standing in.

- [ ] **Step 5: Commit**

```bash
git add .devcontainer/claude-project-slug.sh .devcontainer/tests/test-claude-project-slug.sh
git commit -m "feat(devcontainer): add claude-project-slug helper with tests"
```

---

### Task 2: `host-init.sh` and its tests

Runs on the host, before the container exists. Two jobs, both best-effort. Every failure path must still leave the session mount source existing, because a `type=bind` mount with a missing source **fails container start** — and blocking container start over an optional convenience is exactly the failure mode this repo's honesty rule forbids in the other direction too: it must warn, not die, and must never destroy transcripts.

**Files:**
- Create: `.devcontainer/host-init.sh`
- Test: `.devcontainer/tests/test-host-init.sh`

**Interfaces:**
- Consumes: `.devcontainer/claude-project-slug.sh` (Task 1).
- Produces: `${HOME}/.config/defendable-science-devcontainer/` containing `gh-token` (mode 0600, only when the host has a token), `claude-session-<id>` and `claude-session-pkg-<id>` (symlinks to the real host project dirs for the workspace root and the package subdirectory, or plain directories in the degraded case). Also pre-creates the host-side `defendable-science/.venv`. Task 4's `devcontainer.json` mounts all three paths. Invoked as `bash .devcontainer/host-init.sh <devcontainerId>`.

- [ ] **Step 1: Write the failing test**

Create `.devcontainer/tests/test-host-init.sh`:

```bash
#!/usr/bin/env bash
# Tests for host-init.sh, run against a throwaway $HOME and a stubbed `gh`.
#
# The destructive-branch tests are the important ones: an earlier draft of the
# design would have deleted real session transcripts (unconditional `rm -rf`),
# and the draft after that would have silently created a symlink INSIDE a real
# directory (`ln -sfn` succeeds against a directory), leaving the script
# exiting 0 with sharing quietly dead. Both are pinned below.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_INIT="${SCRIPT_DIR}/../host-init.sh"

failures=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s: %s\n' "$1" "$2"; failures=$((failures + 1)); }

# run_host_init <fake-home> <workdir> <devcontainer-id> <gh-mode>
#   gh-mode: "absent"          -> no gh on PATH at all
#            "unauthenticated" -> gh exists but `gh auth token` fails
#            <anything else>   -> gh returns that string as the token
#
# PATH is rebuilt from EMPTY, containing only this stub dir with the handful of
# real binaries host-init.sh needs symlinked in. Inheriting the caller's PATH
# would leave the maintainer's real /usr/bin/gh visible, so "absent" would
# exercise the opposite branch AND write a live OAuth token into this
# throwaway HOME. `env -i` additionally drops GH_TOKEN/GITHUB_TOKEN, which
# `gh auth token` would otherwise honour.
run_host_init() {
    local home=$1 workdir=$2 id=$3 mode=$4
    local bindir="${home}/.stub-bin"
    mkdir -p "${bindir}"

    local tool
    for tool in bash sed mkdir chmod rm ln dirname; do
        [ -e "${bindir}/${tool}" ] || ln -s "$(command -v "${tool}")" "${bindir}/${tool}"
    done

    rm -f "${bindir}/gh"
    case "${mode}" in
        absent) : ;;
        unauthenticated)
            printf '%s\n' '#!/usr/bin/env bash' 'exit 1' > "${bindir}/gh"
            chmod +x "${bindir}/gh" ;;
        *)
            # shellcheck disable=SC2016  # the stub's $1/$2 must NOT expand here
            { printf '%s\n' '#!/usr/bin/env bash'
              printf '%s\n' '[ "$1 $2" = "auth token" ] || exit 1'
              printf 'printf %%s %s\n' "${mode}"
            } > "${bindir}/gh"
            chmod +x "${bindir}/gh" ;;
    esac

    ( cd "${workdir}" \
        && env -i HOME="${home}" PATH="${bindir}" \
             bash "${HOST_INIT}" "${id}" 2>"${home}/stderr.log" )
}

# The fake workdir carries the repo marker host-init.sh checks for, so the
# happy-path cases exercise the real code rather than the refuse-to-act guard.
new_case() {
    local tmp; tmp="$(mktemp -d)"
    mkdir -p "${tmp}/home/.claude/projects" "${tmp}/work/.claude-plugin"
    printf '{}' > "${tmp}/work/.claude-plugin/plugin.json"
    printf '%s' "${tmp}"
}

echo "== host-init.sh =="

# --- 1. happy path: token written 0600, session symlink created -------------
t="$(new_case)"
run_host_init "${t}/home" "${t}/work" "abc123" "gho_testtoken"
secrets="${t}/home/.config/defendable-science-devcontainer"
if [ -f "${secrets}/gh-token" ] && [ "$(cat "${secrets}/gh-token")" = "gho_testtoken" ]; then
    pass "writes the gh token"
else
    fail "writes the gh token" "missing or wrong contents"
fi
if [ "$(stat -c '%a' "${secrets}/gh-token")" = "600" ]; then
    pass "gh token is mode 0600"
else
    fail "gh token is mode 0600" "got $(stat -c '%a' "${secrets}/gh-token")"
fi
if [ -L "${secrets}/claude-session-abc123" ]; then
    pass "creates the session symlink"
else
    fail "creates the session symlink" "not a symlink"
fi
slug="$(bash "${SCRIPT_DIR}/../claude-project-slug.sh" "${t}/work")"
if [ "$(readlink "${secrets}/claude-session-abc123")" = "${t}/home/.claude/projects/${slug}" ]; then
    pass "symlink points at the slug-derived project dir"
else
    fail "symlink points at the slug-derived project dir" "$(readlink "${secrets}/claude-session-abc123")"
fi

# The package subdirectory is wired too -- CLAUDE.md prescribes working from
# there, so a workspace-root-only link would leave the primary working
# directory silently unshared.
pkg_slug="$(bash "${SCRIPT_DIR}/../claude-project-slug.sh" "${t}/work/defendable-science")"
if [ "$(readlink "${secrets}/claude-session-pkg-abc123")" = "${t}/home/.claude/projects/${pkg_slug}" ]; then
    pass "package subdirectory session link is wired"
else
    fail "package subdirectory session link is wired" "$(readlink "${secrets}/claude-session-pkg-abc123")"
fi

# The host-side venv dir must be pre-created so Docker does not, as root.
if [ -d "${t}/work/defendable-science/.venv" ]; then
    pass "pre-creates the host-side .venv directory"
else
    fail "pre-creates the host-side .venv directory" "missing"
fi
rm -rf "${t}"

# --- 2. no gh on the host: token absent, container start still possible -----
t="$(new_case)"
run_host_init "${t}/home" "${t}/work" "abc123" absent
secrets="${t}/home/.config/defendable-science-devcontainer"
if [ ! -e "${secrets}/gh-token" ]; then
    pass "no token file when the host has no gh"
else
    fail "no token file when the host has no gh" "file exists"
fi
if [ -d "${secrets}" ]; then
    pass "secrets dir still exists (bind-mount source must exist)"
else
    fail "secrets dir still exists" "missing"
fi
if [ -e "${secrets}/claude-session-abc123" ] && [ -e "${secrets}/claude-session-pkg-abc123" ]; then
    pass "both session mount sources still exist"
else
    fail "both session mount sources still exist" "missing"
fi
rm -rf "${t}"

# --- 2b. gh present but not authenticated: same outcome, different branch ---
t="$(new_case)"
run_host_init "${t}/home" "${t}/work" "abc123" unauthenticated
if [ ! -e "${t}/home/.config/defendable-science-devcontainer/gh-token" ]; then
    pass "no token file when gh is present but unauthenticated"
else
    fail "no token file when gh is present but unauthenticated" "file exists"
fi
rm -rf "${t}"

# --- 3. a stale token is removed when the host loses its gh auth ------------
t="$(new_case)"
run_host_init "${t}/home" "${t}/work" "abc123" "gho_first"
run_host_init "${t}/home" "${t}/work" "abc123" absent
if [ ! -e "${t}/home/.config/defendable-science-devcontainer/gh-token" ]; then
    pass "stale token is removed on a later run"
else
    fail "stale token is removed on a later run" "still present"
fi
rm -rf "${t}"

# --- 4. a pre-existing, populated project dir is never touched --------------
t="$(new_case)"
slug="$(bash "${SCRIPT_DIR}/../claude-project-slug.sh" "${t}/work")"
real="${t}/home/.claude/projects/${slug}"
mkdir -p "${real}"
echo "precious transcript" > "${real}/session.jsonl"
run_host_init "${t}/home" "${t}/work" "abc123" "gho_x"
if [ -f "${real}/session.jsonl" ] && [ "$(cat "${real}/session.jsonl")" = "precious transcript" ]; then
    pass "pre-existing transcripts survive"
else
    fail "pre-existing transcripts survive" "modified or deleted"
fi
if [ ! -L "${real}" ]; then
    pass "the real project dir is not replaced by a symlink"
else
    fail "the real project dir is not replaced by a symlink" "it became a symlink"
fi
rm -rf "${t}"

# --- 5. a stale SYMLINK at the stable path is replaced ----------------------
t="$(new_case)"
secrets="${t}/home/.config/defendable-science-devcontainer"
mkdir -p "${secrets}" "${t}/elsewhere"
ln -s "${t}/elsewhere" "${secrets}/claude-session-abc123"
run_host_init "${t}/home" "${t}/work" "abc123" "gho_x"
slug="$(bash "${SCRIPT_DIR}/../claude-project-slug.sh" "${t}/work")"
if [ "$(readlink "${secrets}/claude-session-abc123")" = "${t}/home/.claude/projects/${slug}" ]; then
    pass "a stale symlink is repointed"
else
    fail "a stale symlink is repointed" "$(readlink "${secrets}/claude-session-abc123")"
fi
rm -rf "${t}"

# --- 6. a real DIRECTORY at the stable path is preserved, and NOT linked into
# This is the regression test for the two destructive drafts.
t="$(new_case)"
secrets="${t}/home/.config/defendable-science-devcontainer"
mkdir -p "${secrets}/claude-session-abc123"
echo "fallback transcript" > "${secrets}/claude-session-abc123/session.jsonl"
run_host_init "${t}/home" "${t}/work" "abc123" "gho_x"
if [ -f "${secrets}/claude-session-abc123/session.jsonl" ]; then
    pass "a fallback directory's transcripts are not deleted"
else
    fail "a fallback directory's transcripts are not deleted" "deleted"
fi
if [ -z "$(find "${secrets}/claude-session-abc123" -maxdepth 1 -type l)" ]; then
    pass "no symlink is created inside the fallback directory"
else
    fail "no symlink is created inside the fallback directory" "ln -sfn leaked a link inside"
fi
if grep -q "WARNING" "${t}/home/stderr.log"; then
    pass "warns about the disabled sharing"
else
    fail "warns about the disabled sharing" "no WARNING on stderr"
fi
# Regression: the venv pre-creation must NOT be skipped by the degraded
# session-sharing path. It used to sit after this branch's early exit, so every
# open after the first degraded one silently re-armed the root-owned-.venv trap.
if [ -d "${t}/work/defendable-science/.venv" ]; then
    pass "still pre-creates .venv when session sharing is degraded"
else
    fail "still pre-creates .venv when session sharing is degraded" "missing"
fi
rm -rf "${t}"

# --- 7. a first-ever path warns that the slug may have changed --------------
t="$(new_case)"
run_host_init "${t}/home" "${t}/work" "abc123" "gho_x"
if grep -q "slug" "${t}/home/stderr.log"; then
    pass "warns when the computed project dir did not already exist"
else
    fail "warns when the computed project dir did not already exist" "no warning"
fi
rm -rf "${t}"

# --- 7b. refuses to act on a directory that is not the repo root ------------
t="$(new_case)"
mkdir -p "${t}/elsewhere"
run_host_init "${t}/home" "${t}/elsewhere" "abc123" "gho_x"
secrets="${t}/home/.config/defendable-science-devcontainer"
if [ ! -e "${t}/elsewhere/defendable-science" ]; then
    pass "does not create a stray defendable-science/ outside the repo"
else
    fail "does not create a stray defendable-science/ outside the repo" "created one"
fi
if [ -d "${secrets}/claude-session-abc123" ] && [ ! -L "${secrets}/claude-session-abc123" ]; then
    pass "leaves plain directories so container start still succeeds"
else
    fail "leaves plain directories so container start still succeeds" "symlinked or missing"
fi
if grep -q "not the defendable-science repo root" "${t}/home/stderr.log"; then
    pass "warns that it refused to wire the wrong directory"
else
    fail "warns that it refused to wire the wrong directory" "no warning"
fi
rm -rf "${t}"

# --- 8. always exits 0, even when everything is degraded --------------------
t="$(new_case)"
run_host_init "${t}/home" "${t}/work" "" absent
rc=$?
if [ "${rc}" -eq 0 ]; then pass "exits 0 in the degraded case"; else fail "exits 0 in the degraded case" "rc=${rc}"; fi
rm -rf "${t}"

echo
if [ "${failures}" -gt 0 ]; then echo "FAILED: ${failures}"; exit 1; fi
echo "all passed"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
bash .devcontainer/tests/test-host-init.sh
```

Expected: every case fails — `host-init.sh` does not exist yet.

- [ ] **Step 3: Write the implementation**

Create `.devcontainer/host-init.sh`:

```bash
#!/usr/bin/env bash
# Runs on the HOST (not in the container) via devcontainer.json's
# `initializeCommand`, before the container is created. Two jobs:
#
#   1. Copy the host's gh CLI OAuth token into a directory the devcontainer
#      bind-mounts read-only, so `gh` works inside the container without a
#      second login.
#   2. Point a stable, per-devcontainer path at this checkout's REAL host
#      Claude session directory. The container bind-mounts that stable path
#      onto its own project slug, so host-side and container-side `claude`
#      sessions write to the same place.
#
# Everything here is best-effort: this script must NEVER block container start.
# It warns on stderr and exits 0. But it must also never leave a declared mount
# source missing -- a `type=bind` mount whose source does not exist fails
# container start -- so every degraded path still creates something at
# SESSION_LINK.
#
# `set -u` only (no -e): a failure in one half must not skip the other.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_DIR="${HOME}/.config/defendable-science-devcontainer"
TOKEN_FILE="${SECRETS_DIR}/gh-token"
CLAUDE_PROJECTS="${HOME}/.claude/projects"

warn() { echo "WARNING: host-init.sh: $*" >&2; }

if ! mkdir -p "${SECRETS_DIR}"; then
    warn "could not create ${SECRETS_DIR}."
    # Be explicit rather than reassuring: devcontainer.json bind-mounts this
    # directory, and a bind mount with a missing source is a hard container
    # start failure. Nothing this script can do fixes that, so say exactly what
    # is about to happen instead of implying it degraded gracefully.
    warn "the devcontainer bind-mounts that path, so CONTAINER START WILL FAIL."
    warn "fix the permissions on ${HOME}/.config and re-open the container."
    exit 0
fi
chmod 700 "${SECRETS_DIR}" || true

# ---------------------------------------------------------------------------
# 1. gh token
#
# A single, unsuffixed filename on purpose. `gh auth token` is a property of
# the host USER, not of a checkout, so concurrent devcontainers would write
# identical bytes -- there is no race worth naming around. The read-only bind
# mount exposes the whole directory anyway, so a per-container filename would
# imply an isolation that does not exist, and nothing would ever reclaim the
# accumulated files. Unsuffixed self-cleans: the else-branch below removes it.
# ---------------------------------------------------------------------------
if command -v gh >/dev/null 2>&1 && token="$(gh auth token 2>/dev/null)" && [ -n "${token}" ]; then
    (umask 077 && printf '%s' "${token}" > "${TOKEN_FILE}")
    chmod 600 "${TOKEN_FILE}" || true
else
    rm -f "${TOKEN_FILE}"
fi
unset token

devcontainer_id="${1:-}"
if [ -z "${devcontainer_id}" ]; then
    warn "no devcontainerId argument; devcontainer.json must call:"
    warn "  bash .devcontainer/host-init.sh \${devcontainerId}"
fi

# ---------------------------------------------------------------------------
# 2. Refuse to act on the wrong directory.
#
# EVERY side effect below is derived from $PWD: the .venv pre-creation and both
# session slugs. `initializeCommand` runs with cwd set to the workspace folder,
# but nothing enforces that -- invoked by hand from elsewhere, this script would
# create a stray <cwd>/defendable-science/.venv and silently point the container
# at the WRONG host project directory, because devcontainer.json's bind targets
# are hard-coded container slugs that cannot notice.
#
# Sharing is disabled rather than done wrongly. The stable paths are still
# created as plain directories, because a bind mount with a missing source
# fails container start and this script must not cause that.
# ---------------------------------------------------------------------------
if [ ! -f "${PWD}/.claude-plugin/plugin.json" ]; then
    warn "cwd (${PWD}) is not the defendable-science repo root"
    warn "(expected to find .claude-plugin/plugin.json there)."
    warn "session sharing is DISABLED rather than risk wiring the wrong host directory."
    mkdir -p "${SECRETS_DIR}/claude-session-${devcontainer_id}" \
             "${SECRETS_DIR}/claude-session-pkg-${devcontainer_id}" \
        || warn "could not create the session mount sources; container start may fail."
    exit 0
fi

# ---------------------------------------------------------------------------
# 3. Pre-create the host-side venv directory.
#
# devcontainer.json mounts a named volume at
# <workspace>/defendable-science/.venv, a path that resolves THROUGH the
# workspace bind mount. Docker creates a missing mount destination, and that
# creation lands in the host tree owned by ROOT -- after which the host's own
# `cd defendable-science && uv sync` fails with a permission error. It is
# gitignored, so `git status` stays clean and nothing else notices.
#
# This runs BEFORE session sharing on purpose: the session block has several
# legitimate early-`exit 0` paths (a degraded fallback directory is a normal
# steady state), and leaving this last would mean the hazard silently returns
# on every open after the first degraded one.
# ---------------------------------------------------------------------------
if ! mkdir -p "${PWD}/defendable-science/.venv"; then
    warn "could not pre-create ${PWD}/defendable-science/.venv; Docker may create it root-owned,"
    warn "which would break host-side 'uv sync' in that directory."
fi

# ---------------------------------------------------------------------------
# 4. Session sharing
#
# Keyed by ${devcontainerId} ($1) because, unlike the token, the TARGET
# genuinely differs per checkout.
#
# TWO directories are wired, not one. Claude Code keys transcripts by the
# working directory it was launched from, and CLAUDE.md prescribes
# `cd defendable-science` for all package work -- so wiring only the workspace
# root would leave the repo's *primary* working directory silently unshared.
# ---------------------------------------------------------------------------

# wire_session_dir <host-dir> <stable-link-path>
#
# Point <stable-link-path> at the real host Claude project directory for
# <host-dir>. Always leaves SOMETHING at <stable-link-path>, because
# devcontainer.json bind-mounts it and a missing bind source fails container
# start. Never returns non-zero.
wire_session_dir() {
    local host_dir=$1 link=$2
    local slug target
    slug="$(bash "${SCRIPT_DIR}/claude-project-slug.sh" "${host_dir}")"
    target="${CLAUDE_PROJECTS}/${slug}"

    # Not existing is legitimate on a first-ever session for this path -- but
    # it is ALSO what a change in Claude Code's slug rule looks like. Say so
    # rather than silently sharing an empty directory.
    if [ ! -d "${target}" ]; then
        warn "computed session dir ${target} did not exist."
        warn "if you have used Claude Code in ${host_dir} before, the project-slug"
        warn "rule may have changed and those sessions may NOT be shared."
    fi

    if ! mkdir -p "${target}"; then
        warn "could not create ${target}; falling back to a standalone directory (sessions NOT shared)."
        mkdir -p "${link}" || warn "could not create ${link}; container start may fail."
        return 0
    fi

    # Replace only a symlink. A real directory here is a previous run's
    # degraded fallback and may hold real transcripts: never delete it, and
    # never `ln` into it either -- `ln -sfn` against an existing DIRECTORY
    # silently creates the link *inside* it, which would leave this script
    # exiting 0 with sharing dead.
    if [ -L "${link}" ]; then
        rm -f "${link}"
    elif [ -e "${link}" ]; then
        warn "${link} exists and is not a symlink; leaving it untouched."
        warn "session sharing for ${host_dir} is DISABLED until it is removed by hand."
        return 0
    fi

    if ! ln -sfn "${target}" "${link}" 2>/dev/null; then
        warn "could not link ${link} -> ${target}; using a standalone directory (sessions NOT shared)."
        mkdir -p "${link}" || warn "could not create ${link}; container start may fail."
    fi
    return 0
}

# The dash before ${devcontainer_id} is UNCONDITIONAL so these names match
# devcontainer.json's mount sources byte-for-byte even when the id is empty.
wire_session_dir "${PWD}" \
                 "${SECRETS_DIR}/claude-session-${devcontainer_id}"
wire_session_dir "${PWD}/defendable-science" \
                 "${SECRETS_DIR}/claude-session-pkg-${devcontainer_id}"

exit 0
```

- [ ] **Step 4: Make it executable and run the tests**

```bash
chmod +x .devcontainer/host-init.sh
bash .devcontainer/tests/test-host-init.sh
```

Expected: `all passed`.

- [ ] **Step 5: Run it for real, then confirm it was non-destructive**

```bash
ls -la ~/.claude/projects/-home-davor-projects-PhD-defendable-science | head -3   # before
bash .devcontainer/host-init.sh manual-smoke-test
ls -la ~/.config/defendable-science-devcontainer/
ls -la ~/.claude/projects/-home-davor-projects-PhD-defendable-science | head -3   # after: unchanged
```

Expected: `claude-session-manual-smoke-test` is a symlink to the real project directory; the real directory still holds its transcripts; **no** slug warning is printed (this path has been used before). Then clean up the smoke-test artifact:

```bash
rm -f ~/.config/defendable-science-devcontainer/claude-session-manual-smoke-test
```

- [ ] **Step 6: Commit**

```bash
git add .devcontainer/host-init.sh .devcontainer/tests/test-host-init.sh
git commit -m "feat(devcontainer): add host-init.sh with gh-token and session-sharing setup"
```

---

### Task 3: ShellCheck gate and the CI job

Everything in this feature is shell. The repo gates Python with ruff/mypy/100% coverage and has no shell gate at all; add one now, while there are two scripts to fix rather than nine.

**Files:**
- Create: `tools/shellcheck.sh`
- Modify: `defendable-science/pyproject.toml` (the `lint` dependency group)
- Modify: `.pre-commit-config.yaml`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the scripts from Tasks 1–2 (and, as later tasks land, the rest of `.devcontainer/`).
- Produces: `./tools/shellcheck.sh` (repo-root entry point, exit non-zero on any finding) and a CI job named `devcontainer-scripts`.

- [ ] **Step 1: Add `shellcheck-py` to the `lint` group**

This repo pins every `lint` tool with `==`, exactly once, in `pyproject.toml` (ADR-0036 / issue #79) — an unconstrained entry would silently get no Dependabot bumps. Do **not** use `--frozen` here: it suppresses resolution, so `uv` has no version to write and would land a bare `"shellcheck-py"`.

Confirm the current release, then add it with an explicit pin:

```bash
python3 -c "import urllib.request,json; print(json.load(urllib.request.urlopen('https://pypi.org/pypi/shellcheck-py/json'))['info']['version'])"
cd defendable-science && uv add --group lint "shellcheck-py==0.11.0.1" && cd ..
```

`0.11.0.1` was the current release when this plan was written (verified 2026-08-30); if the command above prints something newer, use that instead. Then confirm the entry matches its neighbours' style:

```bash
grep -A1 -B1 shellcheck defendable-science/pyproject.toml
```

Expected: a `"shellcheck-py==<version>",` line inside `[dependency-groups].lint`.

- [ ] **Step 2: Write the failing check**

Create `tools/shellcheck.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# ShellCheck every shell script in the repo. Mirrors tools/lint.sh's shape: run
# from the repo root, invoke the tool through the package's `lint` group so the
# version is pinned in exactly one place (defendable-science/pyproject.toml).
#
# `.devcontainer/` is the only shell in the tree today; the glob is deliberately
# repo-wide so a future script elsewhere is covered without editing this file.
cd "$(dirname "$0")/.."

# Two sources, because pre-commit's `types: [shell]` is SHEBANG-based while a
# bare '*.sh' glob is extension-based. If the hook can fire on a file this
# script never passes to shellcheck, the hook reports success without having
# checked the file that triggered it.
#
# --cached --others --exclude-standard, not a bare `git ls-files`: the default
# lists TRACKED files only, so a newly written, not-yet-added script would be
# silently skipped and the gate would report success on a file it never read.
# --exclude-standard keeps gitignored paths (e.g. .venv/) out.
#
# The shebang test MUST look at line 1 only. `git grep -E '^#!...'` matches that
# pattern on ANY line, which sweeps in every Markdown document containing a
# fenced `#!/usr/bin/env bash` block -- including this repo's own plan files --
# and shellcheck then fails on them with SC2148/SC1036. That is also what
# pre-commit's `identify` actually does: first line, not any line.
mapfile -t scripts < <(
    { git ls-files --cached --others --exclude-standard '*.sh'
      git ls-files --cached --others --exclude-standard -- ':!*.sh' | while IFS= read -r _f; do
          [ -f "${_f}" ] || continue
          if head -n 1 -- "${_f}" 2>/dev/null | grep -qaE '^#!.*\b(ba)?sh\b'; then
              printf '%s\n' "${_f}"
          fi
      done
    } | sort -u
)

if [ "${#scripts[@]}" -eq 0 ]; then
    echo "No shell scripts found."
    exit 0
fi

echo "Running shellcheck on ${#scripts[@]} script(s)..."
uv run --project defendable-science --group lint shellcheck --severity=style "${scripts[@]}"
```

Make it executable, then check **what it selected** before checking that it passes — a discovery bug here silently either skips files or feeds ShellCheck documents it cannot parse:

```bash
chmod +x tools/shellcheck.sh
bash -x tools/shellcheck.sh 2>&1 | grep -E "^Running shellcheck"
# and confirm no Markdown slipped in:
{ git ls-files --cached --others --exclude-standard '*.sh'
  git ls-files --cached --others --exclude-standard -- ':!*.sh' | while IFS= read -r f; do
      [ -f "${f}" ] || continue
      head -n 1 -- "${f}" 2>/dev/null | grep -qaE '^#!.*\b(ba)?sh\b' && printf '%s\n' "${f}"
  done
} | sort -u | grep -E '\.md$' && echo "FAIL: markdown selected" || echo "OK: no markdown"
./tools/shellcheck.sh
```

Expected: `OK: no markdown`, the five existing `tools/*.sh` plus this task's new files selected, and the run passes. If it reports findings in the Task 1–2 scripts, **fix the scripts** (do not lower `--severity`). Two likely ones and their correct fixes:
- `SC2086` (unquoted expansion) — add the quotes.
- `SC1091` (can't follow a non-constant source) — add `# shellcheck disable=SC1091` with a one-line reason, only where the sourced path genuinely isn't resolvable at check time.

- [ ] **Step 3: Add the pre-commit hook**

In `.pre-commit-config.yaml`, add this as a new `repo: local` block after the existing `typecheck` hook (local, not remote, so the version stays pinned only in `pyproject.toml` — the ADR-0036 / issue #79 rule):

```yaml
-   repo: local
    hooks:
    -   id: shellcheck
        name: Shell lint (shellcheck)
        stages: [pre-commit, pre-merge-commit, manual]
        entry: "tools/shellcheck.sh"
        language: system
        types: [shell]
        pass_filenames: false
        require_serial: true
        verbose: true
```

- [ ] **Step 4: Add the CI job**

In `.github/workflows/ci.yml`, add a new job after `plugin-validate`:

```yaml
  devcontainer-scripts:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.0.1
      - name: Sync defendable-science (lint group)
        run: uv sync --project defendable-science --group lint
      - name: ShellCheck
        run: ./tools/shellcheck.sh
      - name: Devcontainer script tests
        run: |
          bash .devcontainer/tests/test-claude-project-slug.sh
          bash .devcontainer/tests/test-host-init.sh
      - name: Validate devcontainer.json is parseable JSON-with-comments
        run: |
          if [ -f .devcontainer/devcontainer.json ]; then
            python3 -c "import json,re,sys; s=open('.devcontainer/devcontainer.json').read(); s=re.sub(r'^\s*//.*$','',s,flags=re.M); json.loads(s); print('devcontainer.json parses')"
          else
            echo "devcontainer.json not present yet; skipping"
          fi
```

Then add the job to the aggregate gate — change `check.needs` from
`needs: [pre-commit, test, plugin-validate]` to:

```yaml
    needs: [pre-commit, test, plugin-validate, devcontainer-scripts]
```

- [ ] **Step 5: Verify the whole gate locally**

```bash
./tools/shellcheck.sh
bash .devcontainer/tests/test-claude-project-slug.sh
bash .devcontainer/tests/test-host-init.sh
pre-commit run shellcheck --all-files
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ci.yml parses')"
```

Expected: all pass; `ci.yml` parses.

- [ ] **Step 6: Commit**

```bash
git add tools/shellcheck.sh .pre-commit-config.yaml .github/workflows/ci.yml \
        defendable-science/pyproject.toml defendable-science/uv.lock
git commit -m "ci: gate shell scripts with shellcheck and run the devcontainer tests"
```

---

### Task 4: `docker-compose.yml` and `devcontainer.json`

The container definition itself. Nothing here executes yet — the payoff is that `docker compose config` and a JSON parse can both validate it before anything is built.

**Files:**
- Create: `.devcontainer/docker-compose.yml`
- Create: `.devcontainer/devcontainer.json`

**Interfaces:**
- Consumes: `host-init.sh` (Task 2), and — by name only, they land in later tasks — `setup.sh` and `post-create.sh`.
- Produces: the service name `defendable-science-dev`; the four volume names `defendable-science-{claude-config,venv,uv,precommit}-${devcontainerId}`; the two `containerEnv` variables `CLAUDE_CONFIG_DIR` and `UV_CACHE_DIR`, which `install_common_tools.sh` (Task 5) reads.

- [ ] **Step 1: Write the compose file**

Create `.devcontainer/docker-compose.yml`:

```yaml
# One service. No `version:` key -- it is obsolete in Compose v2 and warns.
#
# The compose project name is fixed rather than derived, which assumes ONE
# devcontainer for this repo at a time. That is not a limitation in practice:
# git worktrees cannot cross the container boundary (their .git holds an
# absolute host gitdir path), so the devcontainer is opened on the main clone,
# once. See section 2.1 of the design spec.
name: defendable-science-devcontainer

services:
  defendable-science-dev:
    image: mcr.microsoft.com/devcontainers/python:3.14
    # No `pull_policy: always`. Two reasons: it would make every start depend
    # on the registry (an offline `devcontainer up` would fail outright, which
    # defeats a design whose selling point is that rebuilds are cheap), and
    # because `features` are declared the devcontainer CLI substitutes a
    # locally-built image for this service -- asking Compose to always pull an
    # image that exists only locally. Compose's default (`missing`) is right.
    volumes:
      # The repo root, one level above .devcontainer/.
      - ../:/workspaces/defendable-science:cached
    command: sleep infinity
```

Validate it:

```bash
docker compose -f .devcontainer/docker-compose.yml config >/dev/null && echo "compose OK"
```

Expected: `compose OK`, with no `version is obsolete` warning.

- [ ] **Step 2: Write `devcontainer.json`**

Create `.devcontainer/devcontainer.json`:

```jsonc
{
  "name": "defendable-science",
  "dockerComposeFile": ["./docker-compose.yml"],
  "service": "defendable-science-dev",
  "shutdownAction": "stopCompose",
  "workspaceFolder": "/workspaces/defendable-science",
  "remoteUser": "vscode",

  // Runs on the HOST before the container exists: forwards the gh token and
  // wires the session symlink. ${devcontainerId} is supported here per the
  // containers.dev variables reference, and is stable across rebuilds.
  "initializeCommand": "bash .devcontainer/host-init.sh ${devcontainerId}",
  "updateContentCommand": "bash .devcontainer/setup.sh",
  "postCreateCommand": "bash .devcontainer/post-create.sh",

  // Prepend ~/.local/bin for interactive shells and lifecycle commands: the
  // base image's PATH omits it, and that is where the Claude CLI installs.
  // ${containerEnv:...} is only expandable in remoteEnv, which is why this is
  // not folded into containerEnv below.
  "remoteEnv": {
    "PATH": "/home/vscode/.local/bin:${containerEnv:PATH}"
  },

  "containerEnv": {
    // install_common_tools.sh reads this to chown the root-owned ~/.claude
    // volume. If it is unset that chown is SILENTLY skipped (the script guards
    // with [ -n ... ]) and the Claude CLI install fails later.
    "CLAUDE_CONFIG_DIR": "/home/vscode/.claude",
    // Keep uv's wheel cache inside the persisted uv volume instead of the
    // container's writable layer, which a rebuild discards.
    "UV_CACHE_DIR": "/home/vscode/.local/share/uv/cache"
  },

  // Features are pinned to EXACT versions, not floating majors (`:1`/`:2`).
  // A floating major has no minor/patch component to bump, so Dependabot's
  // minor+patch group would match nothing and the entry ADR-0044 calls
  // load-bearing would track nothing. Exact pins also make a rebuild
  // reproducible, and match how every other tool in this repo is pinned.
  // Versions verified against GHCR on 2026-08-30; Dependabot moves them from here.
  "features": {
    "ghcr.io/devcontainers/features/common-utils:2.5.9": {
      "installZsh": true,
      "installOhMyZsh": true,
      "configureZshAsDefaultShell": true,
      "username": "vscode",
      "userUid": "1000",
      "userGid": "1000"
    },
    "ghcr.io/devcontainers/features/git:1.3.8": {},
    "ghcr.io/devcontainers/features/github-cli:1.1.1": {},
    // rclone: exercised by the opt-in live dataset-retrieval tests.
    "ghcr.io/devcontainers-extra/features/rclone:1.0.15": {},
    // uv as a Feature rather than a curl install, so every tool is declared in
    // one place. Requires the `devcontainers` Dependabot ecosystem (Task 10).
    "ghcr.io/devcontainers-extra/features/uv:1.0.2": {}
  },

  "mounts": [
    // Survives `devcontainer rebuild`: plugins, auth, settings.
    "source=defendable-science-claude-config-${devcontainerId},target=/home/vscode/.claude,type=volume",
    // Nested INSIDE the volume above: the host's real project dir for this
    // checkout, so host and container sessions share transcripts. Its source
    // is created by host-init.sh; a missing bind source fails container start.
    "source=${localEnv:HOME}/.config/defendable-science-devcontainer/claude-session-${devcontainerId},target=/home/vscode/.claude/projects/-workspaces-defendable-science,type=bind",
    // The SECOND session bind: Claude Code keys transcripts by the directory it
    // was launched from, and CLAUDE.md prescribes `cd defendable-science` for
    // package work. Without this, sessions started there land in the
    // container-local volume and are silently unshared.
    "source=${localEnv:HOME}/.config/defendable-science-devcontainer/claude-session-pkg-${devcontainerId},target=/home/vscode/.claude/projects/-workspaces-defendable-science-defendable-science,type=bind",
    // The whole secrets DIRECTORY, read-only. Mounting the directory (not the
    // file) means a host with no gh token is simply a directory without that
    // file, rather than a missing mount source.
    "source=${localEnv:HOME}/.config/defendable-science-devcontainer,target=/var/run/devcontainer-host-secrets,type=bind,readonly",
    // Container-private venv: isolates it from any host-side .venv on the
    // bind-mounted source tree. NOTE the doubled path segment -- the package
    // lives one level below the repo root.
    "source=defendable-science-venv-${devcontainerId},target=/workspaces/defendable-science/defendable-science/.venv,type=volume",
    // uv's downloaded interpreters + (via UV_CACHE_DIR) its wheel cache.
    "source=defendable-science-uv-${devcontainerId},target=/home/vscode/.local/share/uv,type=volume",
    // pre-commit hook environments; ci.yml caches this same path.
    "source=defendable-science-precommit-${devcontainerId},target=/home/vscode/.cache/pre-commit,type=volume"
  ],

  "customizations": {
    "vscode": {
      "settings": {
        "python.testing.pytestEnabled": true,
        "editor.formatOnSave": true,
        "editor.rulers": [88],
        "terminal.integrated.defaultProfile.linux": "zsh",
        "terminal.integrated.profiles.linux": {
          "zsh": { "path": "/bin/zsh" }
        }
      },
      "extensions": [
        "ms-python.python",
        "ms-python.vscode-pylance",
        "charliermarsh.ruff",
        "anthropic.claude-code"
      ]
    }
  }
}
```

- [ ] **Step 3: Verify it parses and the paths are self-consistent**

```bash
python3 - <<'PY'
import json, re
raw = open(".devcontainer/devcontainer.json").read()
cfg = json.loads(re.sub(r'^\s*//.*$', '', raw, flags=re.M))

assert cfg["service"] == "defendable-science-dev"
assert cfg["workspaceFolder"] == "/workspaces/defendable-science"
assert cfg["containerEnv"]["CLAUDE_CONFIG_DIR"] == "/home/vscode/.claude"

targets = [m.split("target=")[1].split(",")[0] for m in cfg["mounts"]]
expected = {
    "/home/vscode/.claude",
    "/home/vscode/.claude/projects/-workspaces-defendable-science",
    "/home/vscode/.claude/projects/-workspaces-defendable-science-defendable-science",
    "/var/run/devcontainer-host-secrets",
    "/workspaces/defendable-science/defendable-science/.venv",
    "/home/vscode/.local/share/uv",
    "/home/vscode/.cache/pre-commit",
}
assert set(targets) == expected, set(targets) ^ expected

# Both session bind targets must equal the slugs of the directories a `claude`
# session is actually started from inside the container.
import subprocess
for d in (cfg["workspaceFolder"], cfg["workspaceFolder"] + "/defendable-science"):
    slug = subprocess.run(
        ["bash", ".devcontainer/claude-project-slug.sh", d],
        capture_output=True, text=True, check=True).stdout
    assert f"/home/vscode/.claude/projects/{slug}" in targets, (d, slug)

# remoteEnv must put ~/.local/bin ahead of the image PATH, or `claude` is
# unreachable and plugin provisioning silently no-ops.
assert cfg["remoteEnv"]["PATH"].startswith("/home/vscode/.local/bin:"), cfg["remoteEnv"]

# Features must carry EXACT versions. A floating `:1` has no minor/patch to
# bump, so Dependabot's group would silently track nothing (see Task 10).
import re as _re
for feat in cfg["features"]:
    tag = feat.rsplit(":", 1)[1]
    assert _re.fullmatch(r"\d+\.\d+\.\d+", tag), f"{feat} is not pinned to an exact version"

# UV_CACHE_DIR must sit inside the uv volume, or a rebuild loses the wheels.
assert cfg["containerEnv"]["UV_CACHE_DIR"].startswith("/home/vscode/.local/share/uv/")
print("devcontainer.json is self-consistent")
PY
```

Expected: `devcontainer.json is self-consistent`. The Feature-pin assertion is what keeps Task 10's Dependabot entry meaningful. This is the check that catches a mistyped container path — which would otherwise fail silently as a feature that just doesn't work.

- [ ] **Step 4: Commit**

```bash
git add .devcontainer/docker-compose.yml .devcontainer/devcontainer.json
git commit -m "feat(devcontainer): add compose service and devcontainer.json"
```

---

### Task 5: `install_common_tools.sh`

Adapted from `/home/davor/projects/PhD/mononet/.devcontainer/shared/install_common_tools.sh`. **Read the original first.** The adaptation is not a path substitution: the package lives one level below the repo root here, so the `.venv` path differs structurally, and two mountpoints mononet never had must be claimed.

**Files:**
- Create: `.devcontainer/install_common_tools.sh`

**Interfaces:**
- Consumes: `CLAUDE_CONFIG_DIR` from `containerEnv` (Task 4); `/var/run/devcontainer-host-secrets/gh-token` from `host-init.sh` (Task 2).
- Produces: an authenticated `gh`, an installed `claude` CLI, writable volume mountpoints. Called by `setup.sh` (Task 6).

- [ ] **Step 1: Write the script**

Create `.devcontainer/install_common_tools.sh`:

```bash
#!/usr/bin/env bash
# Container-side tool setup, called by setup.sh (updateContentCommand).
#
# Adapted from mononet's shared/install_common_tools.sh. Differences, all
# deliberate (see design spec section 3.4):
#   - the ownership loop covers FOUR paths, and the .venv one is not a
#     search-and-replace of mononet's: the package lives one level below the
#     repo root here.
#   - no git-lfs (no .gitattributes LFS rules in this repo).
#   - no nvtop (GPU-only).
#   - no uv install (it is a devcontainer Feature now).
#   - no MONONET_EXTRAS / install_dependencies.sh (one dependency set here).
set -euo pipefail

cd /workspaces/defendable-science

echo -e "\033[36m=== Installing common tools ===\033[0m"

# ---------------------------------------------------------------------------
# Claim the root-owned mountpoints AND the parents Docker had to create.
#
# Docker creates named-volume mountpoints -- and every missing parent directory
# on the way to one -- root-owned. This chown is NOT recursive, so the list has
# to name the parents explicitly rather than rely on the leaves:
#
#   ~/.claude/projects        created as the PARENT of the nested session bind
#                             mount, so claiming ~/.claude never reaches it.
#                             Without it, `cd defendable-science && claude` --
#                             the working dir CLAUDE.md prescribes -- hits
#                             EACCES creating its project directory.
#   ~/.local, ~/.local/share  parents of the uv volume. Also where the Claude
#                             CLI installer writes (~/.local/bin), so a
#                             root-owned ~/.local kills this very script below.
#   ~/.cache                  parent of the pre-commit volume.
#
# CLAUDE_CONFIG_DIR is dereferenced ONCE, up front. Writing
# "${CLAUDE_CONFIG_DIR:-}/projects" inline would expand to the literal
# "/projects" when the variable is unset -- sailing past an [ -n ] guard and
# creating a root-owned directory at the filesystem root, while the chown that
# actually mattered still never happened.
# ---------------------------------------------------------------------------
_claim_paths=()
if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
  _claim_paths+=("${CLAUDE_CONFIG_DIR}" "${CLAUDE_CONFIG_DIR}/projects")
else
  echo -e "\033[1;33mWARNING: CLAUDE_CONFIG_DIR is unset; the ~/.claude volume cannot be claimed and the Claude CLI install will fail.\033[0m"
fi
_claim_paths+=(
  /home/vscode/.local
  /home/vscode/.local/share
  /home/vscode/.local/share/uv
  /home/vscode/.cache
  /home/vscode/.cache/pre-commit
  /workspaces/defendable-science/defendable-science/.venv
)

for _vol in "${_claim_paths[@]}"; do
  # A volume whose mountpoint Docker has not created yet fails [ -w ]; make it
  # first so the writability test below is meaningful.
  sudo mkdir -p "${_vol}"
  if [ ! -w "${_vol}" ]; then
    echo "Claiming ownership of ${_vol}..."
    sudo chown "$(id -u):$(id -g)" "${_vol}"
  fi
done
unset _vol _claim_paths

# ---------------------------------------------------------------------------
# Interactive-shell tooling. The base image is minimised and ships none of it:
#   bash-completion  the completion scripts exist but the loader does not
#   vim              no editor at all, so `git commit` without -m fails
#   less             no pager; git/gh dump unpaged
#   jq tree          routine CLI work
#   fzf htop btop    fuzzy history/file search, process views
# Only the missing ones are installed, in one apt-get, so re-runs are cheap.
# ---------------------------------------------------------------------------
_shell_pkgs=()
[ -r /usr/share/bash-completion/bash_completion ] || _shell_pkgs+=(bash-completion)
for _entry in vim less jq tree fzf htop btop; do
  command -v "${_entry}" >/dev/null 2>&1 || _shell_pkgs+=("${_entry}")
done
if [ ${#_shell_pkgs[@]} -gt 0 ]; then
  echo -e "\033[32mInstalling shell tooling: ${_shell_pkgs[*]}\033[0m"
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends "${_shell_pkgs[@]}"
fi
unset _shell_pkgs _entry

# /etc/dpkg/dpkg.cfg.d/excludes drops /usr/share/doc/*, and Debian ships fzf's
# key bindings there rather than anywhere sourced. Pull just those back in.
if command -v fzf >/dev/null 2>&1 &&
  [ ! -r /usr/share/doc/fzf/examples/key-bindings.bash ]; then
  echo -e "\033[32mRestoring fzf shell key bindings...\033[0m"
  sudo apt-get install -y --reinstall \
    -o DPkg::Options::="--path-include=/usr/share/doc/fzf/examples/*" fzf
fi

echo "uv: $(uv --version)"   # installed by the devcontainer Feature

# ---------------------------------------------------------------------------
# ~/.local/bin on PATH.
#
# The base image's PATH is /usr/local/python/current/bin:/usr/local/py-utils/bin:
# /usr/local/jupyter:/usr/local/share/nvm/current/bin:/usr/local/bin:/usr/local/
# sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin -- verified by reading the
# image config blob. It does NOT include ~/.local/bin, which is where the Claude
# CLI installer below puts `claude`. Debian's ~/.profile adds that directory only
# if it already exists when the shell starts, and it does not: this script
# creates it. Without this export, `command -v claude` fails for the rest of the
# build, provision-claude-plugins.sh (non-fatal by design) warns and exits 0, and
# the container reports a successful setup with no plugins installed at all.
# devcontainer.json's remoteEnv covers interactive shells; this covers the
# remainder of THIS script.
# ---------------------------------------------------------------------------
export PATH="${HOME}/.local/bin:${PATH}"

# ---------------------------------------------------------------------------
# Authenticate gh. Two token sources, in order:
#   1. $GITHUB_TOKEN (Codespaces injects this).
#   2. the host token forwarded by host-init.sh via initializeCommand.
# The filename is unsuffixed -- see host-init.sh for why.
# ---------------------------------------------------------------------------
echo -e "\033[32mAuthenticating GitHub CLI (if a token is available)...\033[0m"
HOST_TOKEN_FILE="/var/run/devcontainer-host-secrets/gh-token"
gh_token=""
if [ -n "${GITHUB_TOKEN:-}" ]; then
  gh_token="${GITHUB_TOKEN}"
elif [ -s "${HOST_TOKEN_FILE}" ] && [ -r "${HOST_TOKEN_FILE}" ]; then
  gh_token="$(cat "${HOST_TOKEN_FILE}")"
fi

if [ -n "${gh_token}" ]; then
  if printf '%s' "${gh_token}" | gh auth login --with-token; then
    echo -e "\033[32mGitHub CLI authenticated.\033[0m"
  else
    echo -e "\033[1;33mWARNING: GitHub CLI authentication failed.\033[0m"
  fi
else
  echo -e "\033[1;33mWARNING: no GitHub token available (neither \$GITHUB_TOKEN nor a host-forwarded token); gh is unauthenticated.\033[0m"
fi
unset gh_token HOST_TOKEN_FILE

# Claude Code, only when missing (the ~/.claude volume persists it).
if command -v claude >/dev/null 2>&1; then
  echo "claude already installed: $(claude --version || echo 'version unavailable')"
else
  echo -e "\033[32mInstalling Claude Code...\033[0m"
  curl -fsSL https://claude.ai/install.sh | bash
fi

# Assert rather than assume. Everything downstream that uses `claude` is
# non-fatal by design, so a failed install would otherwise surface as a
# perfectly green build with no plugins -- the precise "failure reported as a
# legitimate result" CLAUDE.md forbids. This IS a real failure, so fail here.
if ! command -v claude >/dev/null 2>&1; then
  echo -e "\033[1;31mERROR: claude is not on PATH after installation.\033[0m" >&2
  echo "PATH=${PATH}" >&2
  ls -la "${HOME}/.local/bin" 2>&1 >&2 || true
  exit 1
fi
echo "claude on PATH: $(command -v claude)"

echo -e "\033[32m✓ Common tools installed\033[0m"
```

- [ ] **Step 2: Check it**

```bash
chmod +x .devcontainer/install_common_tools.sh
./tools/shellcheck.sh
bash -n .devcontainer/install_common_tools.sh && echo "syntax OK"
```

Expected: shellcheck clean, `syntax OK`. Do **not** try to execute it on the host — it `sudo chown`s container paths.

- [ ] **Step 3: Assert the ownership loop covers every mount**

This guards the exact defect review found: a volume added to `devcontainer.json` but forgotten in the chown loop, which fails at runtime with a bare `EACCES`.

```bash
python3 - <<'PY'
import json, re
cfg = json.loads(re.sub(r'^\s*//.*$', '', open(".devcontainer/devcontainer.json").read(), flags=re.M))
script = open(".devcontainer/install_common_tools.sh").read()

vols = [m.split("target=")[1].split(",")[0] for m in cfg["mounts"] if "type=volume" in m]
missing = [v for v in vols if v not in script
           and not (v == cfg["containerEnv"]["CLAUDE_CONFIG_DIR"] and "CLAUDE_CONFIG_DIR" in script)]
assert not missing, f"volumes never chowned: {missing}"

# The parents Docker creates root-owned on the way to a volume are as important
# as the volumes themselves; match them as whole lines so that, e.g.,
# "/home/vscode/.local" is not satisfied by "/home/vscode/.local/share/uv".
# Compare against CODE only: the script's comments deliberately quote the
# rejected "${CLAUDE_CONFIG_DIR:-}/projects" form to explain why it is wrong,
# and a naive substring test would match that explanation and fail.
code = "\n".join(l for l in script.splitlines() if not l.lstrip().startswith("#"))
lines = {l.strip() for l in code.splitlines()}

assert '"${CLAUDE_CONFIG_DIR}" "${CLAUDE_CONFIG_DIR}/projects")' in code, \
    "the nested projects/ parent is not claimed"
for parent in ("/home/vscode/.local", "/home/vscode/.local/share", "/home/vscode/.cache"):
    assert parent in lines, f"parent {parent} is not claimed"
assert '"${CLAUDE_CONFIG_DIR:-}/projects"' not in code, \
    "unset CLAUDE_CONFIG_DIR would expand to the literal /projects"
print(f"all {len(vols)} volume mountpoints and their parents are claimed")
PY
```

Expected: `all 4 volume mountpoints and their parents are claimed`.

- [ ] **Step 4: Commit**

```bash
git add .devcontainer/install_common_tools.sh
git commit -m "feat(devcontainer): add install_common_tools.sh"
```

---

### Task 6: `setup.sh`

**Files:**
- Create: `.devcontainer/setup.sh`

**Interfaces:**
- Consumes: `install_common_tools.sh` (Task 5).
- Produces: the four prefetched interpreters and a synced `.venv`. Wired as `updateContentCommand` in Task 4's `devcontainer.json`.

- [ ] **Step 1: Write the script**

Create `.devcontainer/setup.sh`:

```bash
#!/usr/bin/env bash
# updateContentCommand: everything that depends only on the source tree.
#
# Unlike host-init.sh this is allowed to fail loudly -- a container whose
# toolchain did not install is not a container anyone should get a shell in.
set -euo pipefail

cd /workspaces/defendable-science

bash .devcontainer/install_common_tools.sh

# Prefetch the interpreters ci.yml's test matrix uses, so any CI leg is
# reproducible locally. These land in the persisted uv volume, so a rebuild
# does not re-download them.
echo ">>> prefetching the CI Python matrix (3.11-3.14)"
uv python install 3.11 3.12 3.13 3.14

# The default dev environment. --group lint so ruff/mypy/pre-commit are present.
echo ">>> syncing the default (3.14) environment"
uv sync --project defendable-science --group lint

echo ">>> setup.sh done"
```

- [ ] **Step 2: Check it**

```bash
chmod +x .devcontainer/setup.sh
./tools/shellcheck.sh
bash -n .devcontainer/setup.sh && echo "syntax OK"
```

- [ ] **Step 3: Verify the matrix matches CI, mechanically**

A drift between this list and `ci.yml`'s matrix is the whole point of the task; assert it rather than eyeballing it.

```bash
python3 - <<'PY'
import re, yaml
ci = yaml.safe_load(open(".github/workflows/ci.yml"))
matrix = [str(v) for v in ci["jobs"]["test"]["strategy"]["matrix"]["python-version"]]
setup = open(".devcontainer/setup.sh").read()
line = re.search(r"uv python install ([\d\.\s]+)", setup).group(1).split()
assert sorted(line) == sorted(matrix), f"setup.sh {line} != ci.yml {matrix}"
print(f"setup.sh prefetches exactly ci.yml's matrix: {matrix}")
PY
```

Expected: `setup.sh prefetches exactly ci.yml's matrix: ['3.11', '3.12', '3.13', '3.14']`.

- [ ] **Step 4: Commit**

```bash
git add .devcontainer/setup.sh
git commit -m "feat(devcontainer): add setup.sh with CI-matrix prefetch"
```

---

### Task 7: the shell prompt

Adapted from mononet's `shell-prompt.sh` + `install-shell-prompt.sh`. Behaviour is unchanged; every `mononet` identifier is renamed. Read both originals under `/home/davor/projects/PhD/mononet/.devcontainer/shared/` and apply exactly these renames:

| mononet | here |
|---|---|
| `/workspaces/mononet` | `/workspaces/defendable-science` |
| `# >>> mononet devcontainer prompt >>>` | `# >>> defendable-science devcontainer prompt >>>` |
| `_mononet_comp_cache` | `_defsci_comp_cache` |
| `_mononet_completion` | `_defsci_completion` |
| `_mononet_bc` / `_mononet_gitprompt` / `_mononet_fzf` / `_mononet_precmd` | `_defsci_*` |
| `${XDG_CACHE_HOME:-$HOME/.cache}/mononet-shell` | `${XDG_CACHE_HOME:-$HOME/.cache}/defsci-shell` |
| the `(mononet)` virtualenv-prefix comment | `(defendable-science)` |

Also drop the `shared/` path segment: the files sit directly in `.devcontainer/`.

**Files:**
- Create: `.devcontainer/shell-prompt.sh`
- Create: `.devcontainer/install-shell-prompt.sh`

**Interfaces:**
- Consumes: nothing at runtime (guards every tool with `command -v`).
- Produces: `install-shell-prompt.sh`, called by `post-create.sh` (Task 9).

- [ ] **Step 1: Copy and rename**

```bash
cp /home/davor/projects/PhD/mononet/.devcontainer/shared/shell-prompt.sh .devcontainer/shell-prompt.sh
cp /home/davor/projects/PhD/mononet/.devcontainer/shared/install-shell-prompt.sh .devcontainer/install-shell-prompt.sh

sed -i \
  -e 's#/workspaces/mononet/.devcontainer/shared/#/workspaces/defendable-science/.devcontainer/#g' \
  -e 's#/workspaces/mononet#/workspaces/defendable-science#g' \
  -e 's#mononet devcontainer prompt#defendable-science devcontainer prompt#g' \
  -e 's#_mononet_#_defsci_#g' \
  -e 's#mononet-shell#defsci-shell#g' \
  -e 's#the mononet devcontainer#the defendable-science devcontainer#g' \
  -e 's#(mononet)#(defendable-science)#g' \
  .devcontainer/shell-prompt.sh .devcontainer/install-shell-prompt.sh
```

- [ ] **Step 2: Verify no `mononet` reference survives *in these two files***

```bash
if grep -n "mononet" .devcontainer/shell-prompt.sh .devcontainer/install-shell-prompt.sh; then
    echo "FAIL: mononet references remain"
else
    echo "clean"
fi
grep -n "PROMPT_FILE=" .devcontainer/install-shell-prompt.sh
```

Expected: `clean`, and `PROMPT_FILE="/workspaces/defendable-science/.devcontainer/shell-prompt.sh"` — the path must point at the file's real new location, with no `shared/` segment.

Scope this to the two prompt files, **not** `grep -rn mononet .devcontainer/`: `claude-project-slug.sh` and `install_common_tools.sh` both carry deliberate provenance comments naming mononet (this plan mandates them), and a directory-wide grep would flag those and push you to delete load-bearing documentation.

- [ ] **Step 2b: Add the ShellCheck disables this file needs**

`shell-prompt.sh` is sourced by **both** bash and zsh, so ShellCheck — which parses it as bash — necessarily misreads the zsh half. Verified: as copied it produces five findings and exits 1, which would fail the gate Task 3 just added. All five are inherent to the dual-shell design, so they are pre-authorised here as specific, permanent disables (this is *not* licence to lower `--severity`). Insert immediately after the existing `# shellcheck shell=bash` line at the top:

```bash
#
# ShellCheck: this file is sourced by BOTH bash and zsh, so shellcheck (which
# parses it as bash) necessarily misreads the zsh half. Each disable below is
# specific and permanent, not a way around the gate:
# shellcheck disable=SC2059  # __git_ps1 fallback: the format string IS the argument
# shellcheck disable=SC2154  # debian_chroot is exported by Debian's /etc/bash.bashrc
# shellcheck disable=SC2034  # SAVEHIST/PROMPT are read by zsh, invisible to shellcheck
# shellcheck disable=SC2016  # zsh PROMPT relies on PROMPT_SUBST: it must NOT expand here
```

These four were confirmed sufficient: with them the file exits 0 at `--severity=style`. If ShellCheck reports anything *else*, fix the code rather than extending this list.

- [ ] **Step 3: Check and smoke-test**

```bash
chmod +x .devcontainer/install-shell-prompt.sh
./tools/shellcheck.sh
bash -n .devcontainer/shell-prompt.sh && bash -n .devcontainer/install-shell-prompt.sh && echo "syntax OK"

# Sourcing it must not break a shell, even where none of the tools exist.
bash -c 'set -e; . .devcontainer/shell-prompt.sh; echo "sourced OK"'
```

Expected: shellcheck exits 0 (thanks to Step 2b's disables), `syntax OK`, `sourced OK`. If ShellCheck still reports findings, they are new ones the copied file did not have — fix the code rather than adding disables.

- [ ] **Step 3b: Make the file safe to source under `set -e`**

The bash branch's last statement is `[ -r /usr/share/doc/fzf/examples/key-bindings.bash ] && . …`. When fzf's bindings are absent — the normal case on a fresh container, before `install_common_tools.sh` reinstalls them — the test fails, the `&&` short-circuits, and the whole file returns 1. Sourcing it from anything running under `set -e` then aborts. (mononet has the same latent issue; rc files are not run under `set -e`, so it never surfaced there.) Append to the very end of `shell-prompt.sh`:

```bash

# Always leave a zero exit status. The last statement in the bash branch above
# is a short-circuit `[ -r ... ] && . ...` whose test fails whenever fzf's
# key-bindings file is absent -- which would make `. shell-prompt.sh` return 1
# and abort any caller running under `set -e`. (Carried over from mononet,
# which has the same latent issue.)
:
```

Re-run the source check from Step 3; it must now print `sourced OK`.

- [ ] **Step 4: Verify `install-shell-prompt.sh` is idempotent**

```bash
tmp="$(mktemp -d)"
HOME="${tmp}" bash .devcontainer/install-shell-prompt.sh
HOME="${tmp}" bash .devcontainer/install-shell-prompt.sh
n="$(grep -c 'defendable-science devcontainer prompt' "${tmp}/.bashrc")"
[ "${n}" -eq 2 ] && echo "idempotent (one begin+end marker pair)" || echo "FAIL: ${n} marker lines"
rm -rf "${tmp}"
```

Expected: `idempotent (one begin+end marker pair)` — two lines, because the block has a begin and an end marker; running twice must not add a second block.

- [ ] **Step 5: Commit**

```bash
git add .devcontainer/shell-prompt.sh .devcontainer/install-shell-prompt.sh
git commit -m "feat(devcontainer): add git-aware shell prompt adapted from mononet"
```

---

### Task 8: the Claude plugin manifest and provisioner

**Files:**
- Create: `.devcontainer/claude-plugins.txt`
- Create: `.devcontainer/provision-claude-plugins.sh`

**Interfaces:**
- Consumes: the `claude` CLI (Task 5) and the container-local `~/.claude` volume.
- Produces: `provision-claude-plugins.sh`, called by `post-create.sh` (Task 9).

- [ ] **Step 1: Write the manifest**

Create `.devcontainer/claude-plugins.txt`:

```
# Claude Code plugins provisioned into the container-local ~/.claude volume by
# provision-claude-plugins.sh. The host's ~/.claude is never touched.
#
# Format: <marketplace-source>  <plugin>@<marketplace-name>
#
# The marketplace NAME is the one the source repo declares for itself in its
# own .claude-plugin/marketplace.json -- not a local alias. Verified:
# obra/superpowers declares "superpowers-dev", matching .claude/settings.json.
https://github.com/obra/superpowers.git  superpowers@superpowers-dev

# This repo's own plugin, from a local marketplace source, so the skills it
# ships are testable inside the container immediately.
#
# The source MUST be the absolute path, not ".". The provisioner's idempotency
# check is `grep -qF "${src}"` against `claude plugin marketplace list`, and a
# lone "." matches almost any line (URLs, versions and paths all contain a
# dot), so "." would read as already-known on the first run and the marketplace
# would silently never be added.
/workspaces/defendable-science  defendable-science@defendable-science
```

- [ ] **Step 2: Write the provisioner**

Copy mononet's, which needs no logic changes — only the manifest path (no `shared/` segment):

```bash
cp /home/davor/projects/PhD/mononet/.devcontainer/shared/provision-claude-plugins.sh \
   .devcontainer/provision-claude-plugins.sh
sed -i 's#MANIFEST="${SCRIPT_DIR}/../claude-plugins.txt"#MANIFEST="${SCRIPT_DIR}/claude-plugins.txt"#' \
   .devcontainer/provision-claude-plugins.sh
grep -n 'MANIFEST=' .devcontainer/provision-claude-plugins.sh
```

Expected: `MANIFEST="${SCRIPT_DIR}/claude-plugins.txt"`.

- [ ] **Step 3: Verify the manifest parses the way the script reads it**

```bash
chmod +x .devcontainer/provision-claude-plugins.sh
./tools/shellcheck.sh

while IFS= read -r line || [ -n "${line}" ]; do
    line="${line%%#*}"
    [ -z "${line//[[:space:]]/}" ] && continue
    src="$(printf '%s' "${line}" | awk '{print $1}')"
    plugin="$(printf '%s' "${line}" | awk '{print $2}')"
    echo "src=[${src}] plugin=[${plugin}] base=[${plugin%@*}] market=[${plugin#*@}]"
done < .devcontainer/claude-plugins.txt
```

Expected exactly two lines:
```
src=[https://github.com/obra/superpowers.git] plugin=[superpowers@superpowers-dev] base=[superpowers] market=[superpowers-dev]
src=[/workspaces/defendable-science] plugin=[defendable-science@defendable-science] base=[defendable-science] market=[defendable-science]
```

- [ ] **Step 4: Confirm the marketplace names are real**

```bash
curl -s https://raw.githubusercontent.com/obra/superpowers/main/.claude-plugin/marketplace.json | python3 -c "import json,sys; print('upstream name:', json.load(sys.stdin)['name'])"
python3 -c "import json; m=json.load(open('.claude-plugin/marketplace.json')); print('local name:', m['name'], '| plugins:', [p['name'] for p in m['plugins']])"
```

Expected: `upstream name: superpowers-dev`, and a local name of `defendable-science` with `defendable-science` among its plugins. If either differs, fix the manifest — a mismatch makes `claude plugin install` fail, and the provisioner is non-fatal, so it would fail *silently*.

- [ ] **Step 5: Commit**

```bash
git add .devcontainer/claude-plugins.txt .devcontainer/provision-claude-plugins.sh
git commit -m "feat(devcontainer): provision superpowers and this repo's own plugin"
```

---

### Task 9: `post-create.sh`

**Files:**
- Create: `.devcontainer/post-create.sh`

**Interfaces:**
- Consumes: `install-shell-prompt.sh` (Task 7), `provision-claude-plugins.sh` (Task 8).
- Produces: nothing later tasks read. Wired as `postCreateCommand` in Task 4.

- [ ] **Step 1: Write the script**

Create `.devcontainer/post-create.sh`:

```bash
#!/usr/bin/env bash
# postCreateCommand: the steps that need the workspace bind mount in place.
set -euo pipefail

cd /workspaces/defendable-science

# `install-hooks`, NOT `install`.
#
# .git is bind-mounted and SHARED WITH THE HOST. `pre-commit install` writes
# .git/hooks/pre-commit with an absolute INSTALL_PYTHON pointing at the
# container's venv -- a path that does not exist on the host -- so running it
# here would degrade host-side `git commit` from then on. `install-hooks` only
# builds the hook ENVIRONMENTS (the slow part, cached in a named volume) and
# touches nothing in .git. Whoever wants git-triggered hooks runs
# `pre-commit install` on their own side and owns that choice.
echo ">>> building pre-commit hook environments (not installing git hooks)"
uv run --project defendable-science --group lint pre-commit install-hooks

echo ">>> installing the git-aware shell prompt"
bash .devcontainer/install-shell-prompt.sh

echo ">>> provisioning Claude Code plugins"
bash .devcontainer/provision-claude-plugins.sh

echo ">>> post-create.sh done"
```

- [ ] **Step 2: Check it, and assert it never runs bare `pre-commit install`**

```bash
chmod +x .devcontainer/post-create.sh
./tools/shellcheck.sh
bash -n .devcontainer/post-create.sh && echo "syntax OK"

if grep -E 'pre-commit install($|[^-])' .devcontainer/post-create.sh; then
    echo "FAIL: bare 'pre-commit install' would corrupt the host's .git/hooks"
else
    echo "OK: only install-hooks is used"
fi
```

Expected: `syntax OK` and `OK: only install-hooks is used`.

- [ ] **Step 3: Verify every lifecycle script referenced by devcontainer.json exists**

```bash
python3 - <<'PY'
import json, os, re
cfg = json.loads(re.sub(r'^\s*//.*$', '', open(".devcontainer/devcontainer.json").read(), flags=re.M))
for key in ("initializeCommand", "updateContentCommand", "postCreateCommand"):
    cmd = cfg[key]
    path = re.search(r'(\.devcontainer/[\w.-]+\.sh)', cmd).group(1)
    assert os.path.isfile(path), f"{key} -> missing {path}"
    assert os.access(path, os.X_OK), f"{key} -> {path} is not executable"
    print(f"{key}: {path} ok")
PY
```

Expected: three `ok` lines.

- [ ] **Step 4: Commit**

```bash
git add .devcontainer/post-create.sh
git commit -m "feat(devcontainer): add post-create.sh"
```

---

### Task 10: the `devcontainers` Dependabot ecosystem

Required by ADR-0044: the Features chosen in Task 4 are pinned at `:1`/`:2` and nothing currently updates them. `.github/dependabot.yml` covers only `uv`, `github-actions`, and `pre-commit`.

**Files:**
- Modify: `.github/dependabot.yml`

**Interfaces:**
- Consumes: the Feature pins in `.devcontainer/devcontainer.json` (Task 4).
- Produces: nothing other tasks read.

- [ ] **Step 1: Add the entry**

Append to the `updates:` list in `.github/dependabot.yml`, matching the conventions of the three existing entries exactly (weekly / monday / 07:00 / Etc/UTC, `cooldown.default-days: 7`, limit 5, the `dependencies` label, one catch-all minor+patch group):

```yaml
  # ── Devcontainer Features (ADR-0044) ────────────────────────────────────
  # Keeps the exact Feature pins in .devcontainer/devcontainer.json current.
  # This only works because Task 4 pins them to exact versions: a floating
  # `:1`/`:2` tag has no minor/patch component, so the group below would match
  # nothing and the entry would track nothing.
  - package-ecosystem: "devcontainers"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "07:00"
      timezone: "Etc/UTC"
    cooldown:
      default-days: 7
    open-pull-requests-limit: 5
    commit-message:
      prefix: "build(deps)"
    labels: ["dependencies"]
    groups:
      devcontainer-features:
        applies-to: version-updates
        patterns: ["*"]
        update-types: ["minor", "patch"]
```

- [ ] **Step 2: Validate**

```bash
python3 - <<'PY'
import yaml
cfg = yaml.safe_load(open(".github/dependabot.yml"))
ecos = [u["package-ecosystem"] for u in cfg["updates"]]
assert "devcontainers" in ecos, ecos
entry = next(u for u in cfg["updates"] if u["package-ecosystem"] == "devcontainers")
assert entry["directory"] == "/"
assert entry["schedule"]["interval"] == "weekly"
assert entry["labels"] == ["dependencies"]
print("ecosystems:", ecos)
PY
```

Expected: `ecosystems: ['uv', 'github-actions', 'pre-commit', 'devcontainers']`.

- [ ] **Step 3: Confirm the entry can actually match the pins**

The group restricts to `["minor", "patch"]`, following the three existing entries. That is only meaningful against exact pins:

```bash
python3 - <<'PY'
import json, re
cfg = json.loads(re.sub(r'^\s*//.*$', '', open(".devcontainer/devcontainer.json").read(), flags=re.M))
floating = [f for f in cfg["features"] if not re.fullmatch(r"\d+\.\d+\.\d+", f.rsplit(":", 1)[1])]
assert not floating, f"floating pins the minor/patch group can never match: {floating}"
print("all Feature pins are exact; the Dependabot group can match them")
PY
```

Expected: `all Feature pins are exact; the Dependabot group can match them`. Majors still arrive as their own ungrouped PR, matching how the other three ecosystems behave.

- [ ] **Step 4: Confirm `cooldown` is actually supported here**

ADR-0036 records that `cooldown`'s sub-options are ecosystem-dependent (`semver-*-days` need a version-based ecosystem). Check GitHub's reference for the `devcontainers` ecosystem:

```bash
gh api /repos/davorrunje/defendable-science/dependabot/alerts >/dev/null 2>&1 || true
echo "Open https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference and confirm 'devcontainers' supports 'cooldown.default-days'."
```

If it is **not** supported, delete the two `cooldown` lines from this entry only and add a comment saying so — mirroring the existing comment on the `github-actions` entry, which already documents exactly this class of exception. Do not remove `cooldown` from the other entries.

- [ ] **Step 5: Commit**

```bash
git add .github/dependabot.yml
git commit -m "build(deps): track devcontainer Feature versions with Dependabot"
```

---

### Task 11: Documentation, end-to-end verification, and the PR

**Files:**
- Modify: `CONTRIBUTING.md`

**Interfaces:**
- Consumes: everything above.
- Produces: the PR.

- [ ] **Step 1: Document it in `CONTRIBUTING.md`**

Add this section (place it after the existing setup/commands material, before the ADR guidance):

```markdown
## Devcontainer (optional)

A devcontainer is provided for maintainer development: Python 3.14, the full CI
interpreter matrix prefetched, `uv`/`gh`/`rclone`/Claude Code installed, and your
Claude Code plugins, auth and session transcripts shared with the host and
preserved across rebuilds. Open the repo in VS Code and choose *Reopen in
Container*, or run `devcontainer up --workspace-folder .`.

Design and rationale: [`docs/superpowers/specs/2026-08-30-devcontainer-design.md`](docs/superpowers/specs/2026-08-30-devcontainer-design.md)
and [ADR-0044](decisions/0044-devcontainer-for-maintainer-development.md).

Claude Code keys transcripts by the directory a session was started from, so
two directories are wired for sharing: the repo root and `defendable-science/`
(the one this guide prescribes for package work). A session started from some
*other* subdirectory is container-local and not shared with the host.

**Open it on the main clone, not on a git worktree.** A linked worktree's `.git`
is a file holding an *absolute* host path, which does not resolve inside the
container, so git — and therefore `pre-commit`, committing and `gh` — breaks
entirely. Worktree-based parallelism stays a host-side workflow; work on
branches inside the container.

The container runs `pre-commit install-hooks`, not `pre-commit install`: `.git`
is shared with the host, and an installed hook would embed a container-only
interpreter path. Run `pre-commit install` yourself on whichever side you want
git-triggered hooks.
```

- [ ] **Step 2: Run every local gate**

```bash
cd /home/davor/projects/PhD/defendable-science
./tools/shellcheck.sh
bash .devcontainer/tests/test-claude-project-slug.sh
bash .devcontainer/tests/test-host-init.sh
docker compose -f .devcontainer/docker-compose.yml config >/dev/null && echo "compose OK"
pre-commit run --all-files
./tools/validate-plugin.sh
cd defendable-science && uv run pytest -q && cd ..
```

Expected: everything passes. `pytest` should be unaffected — no package source changed.

- [ ] **Step 3: Build and open the container**

```bash
devcontainer up --workspace-folder .    # or VS Code: Reopen in Container
```

If the `devcontainer` CLI is absent, install it (`npm i -g @devcontainers/cli`) or use VS Code. Expected: `initializeCommand`, `updateContentCommand` and `postCreateCommand` all exit 0.

- [ ] **Step 4: Verify inside the container**

```bash
cd /workspaces/defendable-science/defendable-science && uv run pytest -q
uv run --python 3.11 pytest -q          # a different CI leg, from the package dir
cd /workspaces/defendable-science
claude plugin list                       # superpowers AND defendable-science
gh auth status                           # authenticated, if the host was
rclone version
uv python list                           # all four interpreters
touch /home/vscode/.claude/projects/.write-probe && echo "projects/ is writable" \
  && rm /home/vscode/.claude/projects/.write-probe
```

Expected: tests pass under both interpreters; both plugins listed; `projects/ is writable` (this is the nested-mount ownership fix from Task 5 — if it fails, that chown loop is wrong).

- [ ] **Step 5: Verify the host was not damaged**

The single most important check, because a failure here is silent and persistent:

```bash
# On the HOST, not in the container.
ls -la .git/hooks/pre-commit 2>/dev/null || echo "no host pre-commit hook (fine)"
grep -l "workspaces/defendable-science" .git/hooks/* 2>/dev/null && echo "FAIL: container paths leaked into host hooks" || echo "OK: host hooks are clean"
git status --short
# --soft, NOT --hard: this repo's primary tree is routinely dirty with other
# concurrent sessions' work, and `git reset --hard` would discard it. --soft
# removes the probe commit and leaves the working tree exactly as it was.
git commit --allow-empty -m "probe" && git reset --soft HEAD~1
ls ~/.claude/projects/-home-davor-projects-PhD-defendable-science/ | head -3

# The venv volume nests inside the workspace bind mount, so Docker will create
# this directory root-owned if host-init.sh did not get there first.
ls -ld defendable-science/.venv
[ -w defendable-science/.venv ] && echo "OK: host .venv is writable" || echo "FAIL: host .venv is root-owned"
```

Expected: no container path in any host hook, host `git commit` still works, and the host's session transcripts are intact.

- [ ] **Step 6: Verify persistence across a rebuild**

```bash
devcontainer up --workspace-folder . --remove-existing-container
# then, inside:
claude plugin list        # still both, without re-provisioning
uv python list            # still four, no re-download
pre-commit run --all-files   # hook envs not rebuilt
```

Expected: all three cheap. Any one of them being slow means its named volume is not persisting.

- [ ] **Step 7: Verify session sharing**

```bash
# In the container:
claude          # start a session, exit
# On the host:
ls -lt ~/.claude/projects/-home-davor-projects-PhD-defendable-science/ | head -3
```

Expected: the container's transcript appears in the **host's** project directory.

- [ ] **Step 8: Open the PR**

Use the repo's `create-pr` skill. The body should state: what it adds, the worktree constraint (§2.1) and the `install-hooks` decision as the two non-obvious calls, the new `devcontainers` Dependabot ecosystem, and the new `devcontainer-scripts` CI job. Reference the spec and ADR-0044.

- [ ] **Step 9: File follow-ups as issues, not TODOs**

Per `CLAUDE.md`, anything deferred becomes a self-contained GitHub issue via the `create-issue` skill. At minimum, file one if either turned out true:
- `cooldown` is unsupported for the `devcontainers` ecosystem (Task 10 Step 3) — issue to revisit when GitHub adds it.
- `uv sync` prints the `EXDEV` hardlink-fallback warning (expected per spec §3.3; file an issue only if the copy cost is actually noticeable, with measurements).

---

## Self-Review

Checked against the spec, 2026-08-30:

**Spec coverage.** §2.1 worktree constraint → Task 4 (compose comment), Task 11 (CONTRIBUTING). §3.1 layout → Tasks 1–9 create all eleven files. §3.2 image + Features + Dependabot companion → Tasks 4, 10. §3.3 config volume, slug rule, warning, three-branch fallback, unsuffixed token, `containerEnv`, uid caveat → Tasks 1, 2, 4, 5. §3.4 ownership loop (four paths incl. `projects/`), matrix prefetch, venv/uv/pre-commit volumes, `UV_CACHE_DIR` → Tasks 4, 5, 6. §3.5 `install-hooks`, prompt renames, manifest with absolute source → Tasks 7, 8, 9. §3.6 compose → Task 4. §4 verification: slug corpus → Task 1; both fallback branches → Task 2; shared-`.git` safety → Task 11 Step 5; rebuild persistence → Task 11 Step 6; worktree constraint → documented rather than tested, since asserting a *failure* mode in CI would need Docker-in-Docker.

**Placeholders.** None: every step carries the literal file content or the exact command. The two unknowable values are handled as discovery commands, not blanks — the `shellcheck-py` version (Task 3 Step 1) and the `cooldown` support question (Task 10 Step 3), each with an explicit branch for either answer.

**Type/name consistency.** `claude-project-slug.sh` is created in Task 1 and consumed by name in Tasks 2 and 4. The service name `defendable-science-dev` matches between `docker-compose.yml` and `devcontainer.json` (Task 4). The four volume names in Task 4 are the four paths asserted in Task 5 Step 3. `CLAUDE_CONFIG_DIR`/`UV_CACHE_DIR` are declared in Task 4 and read in Task 5. `MANIFEST` in Task 8 matches the file created in the same task. The `devcontainer-scripts` CI job (Task 3) names exactly the two test files from Tasks 1–2.

**Scope.** One coherent subsystem; no decomposition needed. Tasks 1–2 are independently valuable and testable with no Docker, which is deliberate: they hold the only logic that has been got wrong before.
