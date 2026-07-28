#!/usr/bin/env bash
set -euo pipefail

# Type-check the defendable-science package with mypy (strict).
cd "$(dirname "$0")/../defendable-science"

echo "Running mypy..."
uv run mypy
