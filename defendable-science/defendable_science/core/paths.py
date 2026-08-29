"""Guard for externally-derived identifiers joined onto a filesystem path.

A citekey, paper id, or accountability-log stem is a single path *segment* —
never a sub-path — but each arrives from outside the process (a CLI option, a
CSL-JSON field, backlog data) with nothing checked. Joining one unvalidated
onto a path lets ``..`` or an absolute-looking value escape the directory it
was meant to stay inside (defendable-science#182). This is deliberately
stricter than :func:`~defendable_science.scaffold.layout._relative`, which
resolves and checks containment for a *configured path* that may legitimately
have subdirectories — an identifier never should.

The backslash check makes Windows nominally in scope, so a Windows *drive*
(``"C:PWNED"``, drive-relative — no separator at all, so escapes the other
checks) is rejected too, via :mod:`ntpath` rather than :mod:`os.path`: the
latter is a no-op for drive detection on the POSIX hosts this test suite
actually runs on, which would make the check silently do nothing everywhere
it is exercised.
"""

from __future__ import annotations

import ntpath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_UNSAFE = frozenset({"", ".", ".."})


def require_path_segment(
    value: str, *, what: str, error: Callable[[str], Exception]
) -> str:
    """Reject `value` unless it is safe as a single filesystem path segment.

    :param value: The externally-derived identifier (citekey, paper id, log stem).
    :param what: What is being validated, for the error message (e.g. ``"citekey"``).
    :param error: The calling module's own error type (e.g. ``LayoutError``,
        ``RecordError``) — never a bare ``ValueError`` leaking past the caller's
        module boundary.
    :returns: `value` unchanged.
    :raises Exception: `error`, naming `what` and the offending value, if `value`
        is empty, ``.``/``..``, contains a path separator, contains a control
        character (e.g. an embedded NUL), or is a Windows drive-relative value
        (``"C:PWNED"``) — anything that would either address more than one
        path segment or reach the OS call as a raw, uncaught error instead of
        this function's own signal.
    """
    if (
        value in _UNSAFE
        or "/" in value
        or "\\" in value
        or any(c < " " for c in value)
        or ntpath.splitdrive(value)[0]
    ):
        raise error(f"{what} is not a valid path segment: {value!r}")
    return value
