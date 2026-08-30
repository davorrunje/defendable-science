#!/usr/bin/env bash
set -euo pipefail

# ShellCheck every shell script in the repo. Mirrors tools/lint.sh's shape: run
# from the repo root, invoke the tool through the package's `lint` group so the
# version is pinned in exactly one place (defendable-science/pyproject.toml).
#
# `.devcontainer/` is the only shell in the tree today; the glob is deliberately
# repo-wide so a future script elsewhere is covered without editing this file.
cd "$(dirname "$0")/.."

# Two sources, because pre-commit's `types: [shell]` is SHEBANG-based while a
# bare '*.sh' glob is extension-based. If the hook can fire on a file this
# script never passes to shellcheck, the hook reports success without having
# checked the file that triggered it.
#
# The shebang test MUST look at line 1 only. `git grep -E '^#!...'` matches that
# pattern on ANY line, which sweeps in every Markdown document containing a
# fenced `#!/usr/bin/env bash` block -- including this repo's own plan files --
# and shellcheck then fails on them with SC2148/SC1036. That is also what
# pre-commit's `identify` actually does: first line, not any line.
mapfile -t scripts < <(
    { git ls-files '*.sh'
      git ls-files -- ':!*.sh' | while IFS= read -r _f; do
          [ -f "${_f}" ] || continue
          if head -n 1 -- "${_f}" 2>/dev/null | grep -qaE '^#!.*\b(ba)?sh\b'; then
              printf '%s\n' "${_f}"
          fi
      done
    } | sort -u
)

if [ "${#scripts[@]}" -eq 0 ]; then
    echo "No shell scripts found."
    exit 0
fi

echo "Running shellcheck on ${#scripts[@]} script(s)..."
uv run --project defendable-science --group lint shellcheck --severity=style "${scripts[@]}"
