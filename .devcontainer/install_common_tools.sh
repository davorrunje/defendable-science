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
