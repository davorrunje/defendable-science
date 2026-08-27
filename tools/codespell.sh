#!/usr/bin/env bash
set -euo pipefail

# Spell-check the files pre-commit hands us, using the `codespell` pinned in
# `defendable-science/pyproject.toml`'s `lint` group.
#
# This is a `repo: local` hook rather than the upstream remote hook so the
# version is authored in exactly one place. As a remote hook it carried its own
# `rev:`, which Dependabot's `pre-commit` ecosystem bumped independently of the
# `uv` ecosystem bumping the `==` pin — two schedules for one version, which
# drifted once already (see issue #79, ADR-0036).
#
# Run from the repo root and *do not* cd: pre-commit passes file paths relative
# to it, and `--ignore-words` resolves against it too. `uv run --project` gets
# the pinned tool without moving.
cd "$(dirname "$0")/.."

exec uv run --project defendable-science codespell \
    --ignore-words=.codespell-whitelist.txt "$@"
