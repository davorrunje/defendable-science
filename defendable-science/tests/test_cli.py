"""CLI smoke tests for the ``defendable-science`` Typer app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from defendable_science import __version__, cli
from defendable_science.cli import app

if TYPE_CHECKING:
    import pytest

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_groups() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in ("literature", "dataset", "defend", "backlog"):
        assert group in result.stdout


def test_doctor_runs() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "python" in result.stdout.lower()
    assert "rclone" in result.stdout.lower()
    assert "uv" in result.stdout.lower()


class _Proc:
    def __init__(self, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr


def test_tool_report_found_with_version(monkeypatch: pytest.MonkeyPatch) -> None:
    # Deterministic — does not depend on any tool actually being on PATH.
    monkeypatch.setattr(
        "defendable_science.cli.shutil.which", lambda name: f"/usr/bin/{name}"
    )
    monkeypatch.setattr(
        "defendable_science.cli.subprocess.run", lambda *a, **k: _Proc("mytool 1.2.3\n")
    )
    report = cli._tool_report("mytool")
    assert "1.2.3" in report
    assert "/usr/bin/mytool" in report


def test_tool_report_found_but_no_version_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("defendable_science.cli.shutil.which", lambda name: "/bin/x")
    monkeypatch.setattr("defendable_science.cli.subprocess.run", lambda *a, **k: _Proc())
    assert "version unknown" in cli._tool_report("x")


def test_tool_report_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("defendable_science.cli.shutil.which", lambda name: None)
    assert cli._tool_report("nope") == "nope: not found"


def test_dataset_command_tree_matches_audited_specs() -> None:
    result = runner.invoke(app, ["dataset", "--help"])
    assert result.exit_code == 0
    for command in ("validate", "ingest", "emit", "fetch", "verify", "mirror", "audit"):
        assert command in result.stdout


def test_backlog_command_tree_matches_audited_specs() -> None:
    result = runner.invoke(app, ["backlog", "--help"])
    assert result.exit_code == 0
    for command in ("park", "add", "list", "rank", "promote", "drop"):
        assert command in result.stdout
