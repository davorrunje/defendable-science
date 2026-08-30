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
