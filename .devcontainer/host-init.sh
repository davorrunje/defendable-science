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
# 0. The shared settings.json must exist.
#
# devcontainer.json bind-mounts ${HOME}/.claude/settings.json so host and
# container share one file. A bind mount whose source is missing is a HARD
# container start failure, and Claude Code does not create settings.json until
# it first needs to write one -- so on a fresh host this file legitimately does
# not exist yet. Create a minimal valid one rather than let the container
# refuse to start.
#
# Only ever created, never overwritten: an existing file is the user's.
# ---------------------------------------------------------------------------
CLAUDE_SETTINGS="${HOME}/.claude/settings.json"
if [ ! -e "${CLAUDE_SETTINGS}" ]; then
    if mkdir -p "${HOME}/.claude" && printf '{}\n' > "${CLAUDE_SETTINGS}"; then
        warn "created an empty ${CLAUDE_SETTINGS} (the devcontainer bind-mounts it)."
    else
        warn "could not create ${CLAUDE_SETTINGS}."
        warn "the devcontainer bind-mounts that file, so CONTAINER START WILL FAIL."
    fi
fi

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
