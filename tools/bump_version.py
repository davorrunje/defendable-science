#!/usr/bin/env python3
"""Bump the ``honest-scholar`` PyPI package version (PEP 440).

Composes a release-segment bump (``major``/``minor``/``patch``) with a
pre-release phase (``alpha``/``beta``/``rc``/``final``), so a single run can
express "start the next minor's alpha" (``--release minor --pre alpha`` ->
``0.1.0a0``), "advance the current prerelease" (``--pre alpha`` -> ``…a{n+1}``),
"promote to the next phase" (``--pre rc`` on an alpha -> ``…rc0``), or "cut the
final" (``--pre final`` -> drop the prerelease).

Edits ``[project].version`` in ``honest-scholar/pyproject.toml`` in place (the
package's source of truth; the runtime ``__version__`` derives from the installed
metadata) and prints the new version to stdout.

This bumps **only the package**. The Claude Code plugin (`.claude-plugin/plugin.json`)
is versioned independently (per the versioning policy); it pins a *compatible*
package version via `ensure-tooling`, it is not kept string-locked to it.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PYPROJECT = _ROOT / "honest-scholar" / "pyproject.toml"

# Matches the [project] version line (line-anchored; no other `^version = "..."`).
_VERSION_LINE = re.compile(r'(?m)^version\s*=\s*"([^"]+)"')
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?$")
_PHASES = ("a", "b", "rc")  # PEP 440 ascending order
_PRE_TO_PHASE = {"alpha": "a", "beta": "b", "rc": "rc"}


class BumpError(ValueError):
    """Raised on a malformed version or an illegal (non-monotonic) bump."""


def parse_version(raw: str) -> tuple[int, int, int, str | None, int]:
    """Parse ``X.Y.Z[{a|b|rc}N]`` into ``(major, minor, patch, phase, num)``.

    :param raw: The version string.
    :returns: Release triple plus the pre-release phase (``None`` if final) and
        its number.
    :raises BumpError: If `raw` is not a supported version shape.
    """
    match = _VERSION.fullmatch(raw.strip())
    if match is None:
        raise BumpError(f"unsupported version {raw!r} (want X.Y.Z[{{a|b|rc}}N])")
    major, minor, patch, phase, num = match.groups()
    return int(major), int(minor), int(patch), phase, int(num or 0)


def format_version(
    major: int, minor: int, patch: int, phase: str | None, num: int
) -> str:
    """Render a parsed version back to a PEP 440 string."""
    base = f"{major}.{minor}.{patch}"
    return f"{base}{phase}{num}" if phase else base


def bump(current: str, release: str, pre: str) -> str:
    """Compute the next version from `current` given a release + pre-release bump.

    :param release: ``none`` / ``patch`` / ``minor`` / ``major`` — a release-segment
        bump clears any existing prerelease.
    :param pre: ``keep`` / ``alpha`` / ``beta`` / ``rc`` / ``final``.
    :returns: The new PEP 440 version string.
    :raises BumpError: If nothing would change, or a pre-release bump would move
        backwards (e.g. ``rc`` -> ``alpha``).
    """
    if release == "none" and pre == "keep":
        raise BumpError("nothing to bump: pass --release and/or --pre")

    major, minor, patch, phase, num = parse_version(current)

    if release == "major":
        major, minor, patch, phase, num = major + 1, 0, 0, None, 0
    elif release == "minor":
        minor, patch, phase, num = minor + 1, 0, None, 0
    elif release == "patch":
        patch, phase, num = patch + 1, None, 0
    elif release != "none":
        raise BumpError(f"unknown --release {release!r}")

    if pre == "final":
        phase, num = None, 0
    elif pre in _PRE_TO_PHASE:
        target = _PRE_TO_PHASE[pre]
        if phase is None or _PHASES.index(phase) < _PHASES.index(target):
            phase, num = target, 0
        elif phase == target:
            num += 1
        else:
            raise BumpError(
                f"cannot move backwards from prerelease {phase!r} to {target!r}"
            )
    elif pre != "keep":
        raise BumpError(f"unknown --pre {pre!r}")

    return format_version(major, minor, patch, phase, num)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: bump the manifest version in place and print it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release", choices=["none", "patch", "minor", "major"], default="none"
    )
    parser.add_argument(
        "--pre", choices=["keep", "alpha", "beta", "rc", "final"], default="keep"
    )
    parser.add_argument("--pyproject", type=Path, default=_DEFAULT_PYPROJECT)
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the new version, do not write."
    )
    args = parser.parse_args(argv)

    text = args.pyproject.read_text(encoding="utf-8")
    match = _VERSION_LINE.search(text)
    if match is None:
        print(f"no 'version = \"...\"' line in {args.pyproject}", file=sys.stderr)
        return 2
    try:
        new = bump(match.group(1), args.release, args.pre)
    except BumpError as exc:
        print(f"bump failed: {exc}", file=sys.stderr)
        return 2

    if not args.dry_run:
        updated = text[: match.start(1)] + new + text[match.end(1) :]
        args.pyproject.write_text(updated, encoding="utf-8")
    print(new)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
