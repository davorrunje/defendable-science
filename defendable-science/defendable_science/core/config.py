"""Reading of the per-project ``.defendable-science/config.yml`` file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(".defendable-science/config.yml")


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
        try:
            data = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            msg = f"{config_path}: invalid YAML: {exc}"
            raise ValueError(msg) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        msg = f"{config_path}: expected a YAML mapping, got {type(data).__name__}"
        raise ValueError(msg)
    return data
