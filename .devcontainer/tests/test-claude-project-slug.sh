#!/usr/bin/env bash
# Tests for claude-project-slug.sh.
#
# The slug rule is inferred from Claude Code's observed behaviour, not from a
# documented contract, so the cases below are anchored on REAL directory names
# seen under ~/.claude/projects. Two of them are adversarial on purpose:
#   - a path containing '/.' must collapse to a DOUBLE dash
#   - a path containing '+'  must map the '+' to '-'
# Those two falsify the two rules that were tried and rejected during design
# review ('/'-only, and '[/._]'). See the design spec, section 3.3.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SLUG="${SCRIPT_DIR}/../claude-project-slug.sh"

failures=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n     expected: %s\n     actual:   %s\n' "$1" "$2" "$3"; failures=$((failures + 1)); }

assert_slug() {
    local desc=$1 input=$2 expected=$3 actual
    actual="$("${SLUG}" "${input}")"
    if [ "${actual}" = "${expected}" ]; then pass "${desc}"; else fail "${desc}" "${expected}" "${actual}"; fi
}

echo "== claude-project-slug.sh =="

assert_slug "plain repo path" \
    "/home/davor/projects/PhD/defendable-science" \
    "-home-davor-projects-PhD-defendable-science"

assert_slug "nested package dir" \
    "/home/davor/projects/PhD/defendable-science/defendable-science" \
    "-home-davor-projects-PhD-defendable-science-defendable-science"

# '/.claude' -> '--claude': the dot becomes a second dash.
assert_slug "dot-directory yields a double dash" \
    "/home/davor/projects/PhD/defendable-science/.claude/worktrees/curried-plotting-harp" \
    "-home-davor-projects-PhD-defendable-science--claude-worktrees-curried-plotting-harp"

# '+' is neither '/' nor '.' nor '_' -- this is the case that rules out [/._].
assert_slug "plus sign becomes a dash" \
    "/home/davor/projects/PhD/defendable-science/.claude/worktrees/scope+arxiv-query-escaping" \
    "-home-davor-projects-PhD-defendable-science--claude-worktrees-scope-arxiv-query-escaping"

assert_slug "underscore becomes a dash" \
    "/home/davor/my_projects/defendable-science" \
    "-home-davor-my-projects-defendable-science"

assert_slug "space becomes a dash" \
    "/home/davor/My Projects/defendable-science" \
    "-home-davor-My-Projects-defendable-science"

assert_slug "existing dashes and digits survive" \
    "/workspaces/defendable-science" \
    "-workspaces-defendable-science"

assert_slug "case is preserved" \
    "/home/davor/projects/PhD" \
    "-home-davor-projects-PhD"

# Defaults to $PWD when given no argument.
actual="$(cd / && "${SLUG}")"
if [ "${actual}" = "-" ]; then pass "defaults to \$PWD"; else fail "defaults to \$PWD" "-" "${actual}"; fi

# ---------------------------------------------------------------------------
# Corroboration against real directories, when this machine has them.
#
# Every directory under ~/.claude/projects was produced by Claude Code itself,
# so re-deriving one from its known source path is the strongest check
# available. The two paths below are the ADVERSARIAL ones: they are exactly
# what falsified the '/'-only rule and then the '[/._]' rule during design
# review. Skipped, not failed, on a machine without them (e.g. CI).
# ---------------------------------------------------------------------------
projects="${HOME}/.claude/projects"
repo_root="${HOME}/projects/PhD/defendable-science"
corroborated=0
for real in \
    "${repo_root}/.claude/worktrees/curried-plotting-harp" \
    "${repo_root}/.claude/worktrees/scope+arxiv-query-escaping"
do
    slug="$("${SLUG}" "${real}")"
    # The -n guard matters: an empty slug makes the -d test resolve to
    # "${projects}/" -- which exists -- so a broken or missing SLUG script would
    # otherwise report a false "ok" here.
    if [ -n "${slug}" ] && [ -d "${projects}/${slug}" ]; then
        pass "adversarial real path resolves: $(basename "${real}")"
        corroborated=$((corroborated + 1))
    fi
done
if [ "${corroborated}" -eq 0 ]; then
    echo "  skip corroboration (no known adversarial paths under ${projects})"
fi

echo
if [ "${failures}" -gt 0 ]; then echo "FAILED: ${failures}"; exit 1; fi
echo "all passed"
