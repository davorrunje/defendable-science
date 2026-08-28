"""Reading of the per-project ``.defendable-science/config.yml`` file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(".defendable-science/config.yml")


class RootError(ValueError):
    """Raised when an explicitly-named repository root cannot be used."""


def resolve_root(root: str) -> Path:
    """Resolve an explicitly-named repository root, requiring it to be there.

    The explicit counterpart of :func:`find_repo_root`, and deliberately the
    stricter of the two. ``Path(root).resolve()`` does not require existence,
    and ``init``'s writers ``mkdir(parents=True)``, so ``init --root
    /typo/path`` silently built a whole tree at the typo; ``check --root
    /typo/path`` reported every required file as missing, which is a verdict on
    a repository nobody ever looked at (#132). An explicitly-named root is a
    deliberate statement about an *existing* repository; a non-existent one is
    almost always a slip of the keyboard, and the genuine "scaffold into a new
    directory" case is one ``mkdir -p`` away — which is why there is no
    ``--allow-new-root``: a flag for a rare intent is surface for little value.

    Discovery is untouched. With no ``--root``, :func:`find_repo_root` still
    walks up for ``.defendable-science/`` and falls back to the current
    directory, because an un-onboarded directory is exactly where ``init`` is
    run.

    :param root: The value passed to ``--root``.
    :returns: The canonical absolute path of the root directory.
    :raises RootError: If `root` does not exist, or exists as something other
        than a directory. The two are distinguished: reporting a file as
        missing would send the author looking for the wrong problem.
    """
    path = Path(root).resolve()
    if path.is_dir():
        return path
    if path.exists():
        msg = (
            f"--root {path} is not a directory; --root must name an existing "
            "repository root. Point it at the repository's directory, or omit "
            "--root to use the repository discovered from the current directory."
        )
        raise RootError(msg)
    msg = (
        f"--root {path} does not exist; --root must name an existing directory. "
        f"Correct the path, or create it first (`mkdir -p {path}`) and re-run — "
        "or omit --root to use the repository discovered from the current "
        "directory."
    )
    raise RootError(msg)


def find_repo_root(start: Path | None = None) -> Path:
    """Find the repository root by walking up for ``.defendable-science/``.

    Layout paths are repo-root-relative, so a command run from a subdirectory
    must still resolve against the repository rather than against the cwd.

    :param start: Where to start; the current directory when omitted.
    :returns: The first ancestor containing ``.defendable-science/``, or the
        resolved `start` when none does (an un-onboarded directory is not an
        error — ``init`` is exactly the command you run there).
    """
    from defendable_science.scaffold.layout import CONFIG_DIR

    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / CONFIG_DIR).is_dir():
            return candidate
    return here


def load_config_text(text: str) -> dict[str, Any]:
    """Parse config YAML from text.

    Validates that the text is valid YAML and contains a mapping (or is empty/null).

    :param text: The config file contents.
    :returns: The parsed configuration mapping (empty if blank or null).
    :raises ValueError: If the text is not valid YAML, or does not contain a YAML
        mapping.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"expected a YAML mapping, got {type(data).__name__}")
    return data


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load the defendable-science project configuration.

    Reads a YAML mapping from ``.defendable-science/config.yml`` (or the given path). A
    missing file yields an empty configuration rather than an error, so callers
    can treat an unconfigured project as "all defaults".

    :param path: Path to the config file; defaults to ``.defendable-science/config.yml``.
    :returns: The parsed configuration mapping (empty if the file is absent or
        blank).
    :raises ValueError: If the file exists but is not valid YAML, or does not
        contain a YAML mapping.
    """
    config_path = Path(path)
    if not config_path.is_file():
        return {}
    with config_path.open(encoding="utf-8") as handle:
        text = handle.read()
    try:
        return load_config_text(text)
    except ValueError as exc:
        # Re-raise with the path in the message so callers know which file failed
        raise ValueError(f"{config_path}: {exc}") from exc
