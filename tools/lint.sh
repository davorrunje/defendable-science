#!/usr/bin/env bash
set -euo pipefail

# Lint the honest-scholar package with ruff (check + format verification).
# `../tools` (the maintainer build tooling, e.g. `build_docs_site.py`) is
# checked explicitly too: ruff's `include` glob in pyproject.toml only
# *filters* files already discovered under its target path(s) — it does not
# expand discovery outside the directory `ruff check .` was pointed at — so
# `tools/` must be passed as an extra path for it to actually be scanned
# (see issue #56).
cd "$(dirname "$0")/../honest-scholar"

echo "Running ruff linter..."
uv run ruff check . ../tools

echo "Running ruff formatter (check only)..."
uv run ruff format --check . ../tools
