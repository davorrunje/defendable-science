"""defendable-science — supporting CLI/tooling for the defendable-science research plugin.

The authoritative interface is the ``defendable-science`` Typer CLI
(:mod:`defendable_science.cli`); an optional MCP wrapper over the same modules may
follow later (see ADR-0024).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("defendable-science")
except PackageNotFoundError:  # pragma: no cover - not installed (e.g. source tree)
    __version__ = "0.0.0"

__all__ = ["__version__"]
