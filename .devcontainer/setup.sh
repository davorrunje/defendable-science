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
