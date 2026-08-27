#!/usr/bin/env bash
set -euo pipefail

# Scan the files pre-commit hands us for secrets, using the `detect-secrets`
# pinned in `defendable-science/pyproject.toml`'s `lint` group.
#
# A `repo: local` hook for the same single-source-of-truth reason as
# `codespell.sh` (issue #79, ADR-0036). `detect-secrets-hook` — not
# `detect-secrets` — is the entry point the upstream hook uses; the bare CLI
# scans and prints rather than failing on a new finding.
#
# Run from the repo root and *do not* cd: pre-commit passes file paths relative
# to it, and `--baseline` resolves against it too.
cd "$(dirname "$0")/.."

exec uv run --project defendable-science detect-secrets-hook \
    --baseline .secrets.baseline "$@"
