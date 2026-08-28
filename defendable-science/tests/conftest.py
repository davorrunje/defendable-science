"""Shared, hermetic test fixtures.

Nothing here is test-specific logic — only environment guards so the suite
never touches a real developer's home directory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _isolated_xdg_config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point ``HOME``/``XDG_CONFIG_HOME`` at a throwaway directory for every test.

    The key store now defaults to an XDG config location outside any repo
    (defendable-science#66, ADR-0032) — resolved from ``$XDG_CONFIG_HOME`` or
    ``~/.config`` when a test does not pass an explicit store path. Without this
    guard, any test that exercises that default path (directly via
    ``defendable_science.core.keys``, or indirectly via the ``keys``/``doctor``/
    ``literature`` CLI commands) would read or write a real developer's
    ``~/.config/defendable-science/keys.json``. Every test gets its own empty,
    disposable ``$XDG_CONFIG_HOME`` instead.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / ".config"))
    monkeypatch.delenv("DEFENDABLE_SCIENCE_KEYS_PATH", raising=False)
