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
