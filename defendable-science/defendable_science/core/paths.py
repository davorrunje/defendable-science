"""Guard for externally-derived identifiers joined onto a filesystem path.

A citekey, paper id, or accountability-log stem is a single path *segment* —
never a sub-path — but each arrives from outside the process (a CLI option, a
CSL-JSON field, backlog data) with nothing checked. Joining one unvalidated
onto a path lets ``..`` or an absolute-looking value escape the directory it
was meant to stay inside (defendable-science#182). This is deliberately
stricter than :func:`~defendable_science.scaffold.layout._relative`, which
resolves and checks containment for a *configured path* that may legitimately
have subdirectories — an identifier never should.
"""

from __future__ import annotations

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
        is empty, ``.``/``..``, or contains a path separator — anything that
        would make it address more than one path segment and let it escape the
        directory it is joined into.
    """
    if value in _UNSAFE or "/" in value or "\\" in value:
        raise error(f"{what} is not a valid path segment: {value!r}")
    return value
