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
