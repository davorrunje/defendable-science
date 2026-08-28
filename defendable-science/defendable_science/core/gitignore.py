"""Ask git, not a hand-rolled matcher, whether a path is gitignored (#138, #139).

`check`'s cache_dir rule and `scaffold.render.merge_gitignore` each answered
"is this path already gitignored?" with their own literal-line matcher —
stripped-line equality plus a parent-directory prefix test. Neither understood
real gitignore semantics: a `.gitignore` that legitimately covered a path
through `**/`, a leading `/`, or a wildcard like `*.ext/` was told it did not.
For `check` that produced a false ``invalid`` finding from the tool whose job
is telling the truth about repo health; for `scaffold` it produced a redundant
duplicate line on the first ``init`` into an already-correctly-configured repo.

``git check-ignore`` is the actual authority on gitignore semantics: it also
honours negations (``!pattern``), nested ``.gitignore`` files, ``.git/info/exclude``,
and the global excludes file — none of which a hand-rolled matcher, or the
``pathspec`` package (which only evaluates the text it is handed), would ever
cover. Shelling out costs one subprocess per check and only works inside a
git work tree; this repo already shells out to external tools elsewhere
(``rclone`` in :mod:`defendable_science.core.mirror`, ``git`` itself in
:mod:`defendable_science.core.keys`), and CLAUDE.md's light-wheel constraint is
about not adding new *runtime dependencies* (that is why Pydantic was
rejected), not about avoiding calls to a tool a git work tree already has.
"""

from __future__ import annotations

import subprocess  # nosec B404 - git is a trusted, fixed-arg subprocess
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path


class _GitProc(Protocol):
    """The minimal completed-process shape a git runner must return."""

    @property
    def returncode(self) -> int:
        """The process exit code."""


#: A ``git`` subprocess runner with the ``subprocess.run`` shape (injectable
#: for tests, mirroring :data:`defendable_science.core.mirror.Runner`), so no
#: test ever spawns a real ``git`` process or depends on the test process's
#: own git state.
GitRunner = Callable[..., _GitProc]


def check_ignore(
    root: Path, path: str, *, run: GitRunner = subprocess.run
) -> bool | None:
    """Ask git whether `path` (relative to `root`) is gitignored there.

    Delegates to ``git check-ignore --quiet``, git's own answer, rather than
    reimplementing gitignore-pattern matching.

    :param root: The git work tree to check inside — ``git check-ignore`` runs
        with this as its ``cwd``, regardless of the caller's own working
        directory, so the check always uses *that* repository.
    :param path: The path to check, relative to `root`.
    :param run: The subprocess runner (defaults to :func:`subprocess.run`;
        injectable so tests never spawn a real ``git`` process).
    :returns: ``True`` if `path` is ignored, ``False`` if it is not, or
        ``None`` if the question cannot be answered — git is absent, `root`
        is not a git work tree, or git exits with any other code. Callers
        must treat ``None`` as its own outcome and never collapse it into
        either ``True`` or ``False`` (CLAUDE.md's failure-honesty rule): an
        uncertain condition is not a definite negative.
    """
    try:
        proc = run(  # nosec B603 - fixed git args, no shell
            ["git", "check-ignore", "--quiet", "--", path],
            capture_output=True,
            check=False,
            cwd=str(root),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode in (0, 1):
        return proc.returncode == 0
    return None
