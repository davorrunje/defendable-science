"""`defendable-science progress dashboard` end to end (#130)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path  # noqa: TC003

import pytest  # noqa: TC002
from typer.testing import CliRunner

from defendable_science.cli import app
from defendable_science.progress.render import artifact_ids
from defendable_science.scaffold.layout import Layout

runner = CliRunner()


def _init(root: Path, *, thesis: bool = False) -> None:
    args = ["init", "--root", str(root)] + (["--thesis"] if thesis else [])
    assert runner.invoke(app, args).exit_code == 0


def _dashboard(root: Path) -> Path:
    return Layout.default(root).dashboard


def _pitch(root: Path, paper: str, body: str) -> None:
    directory = Layout.default(root).paper_docs_dir(paper)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "pitch.md").write_text(body, encoding="utf-8")


def test_a_freshly_initialized_thesis_repo_projects_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The acceptance case: empty sections, a valid file, and exit 0."""
    monkeypatch.chdir(tmp_path)
    _init(tmp_path, thesis=True)

    result = runner.invoke(app, ["progress", "dashboard"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["counts"] == {"invalid": 0, "unreadable": 0, "gap": 0}
    assert payload["changed"] is True
    assert payload["dashboard_path"] == "docs/research/dashboard.md"
    assert payload["generated_on"] == date.today().isoformat()
    # A scaffolded `aims.md` is a real thesis artifact whose id is not yet set.
    assert payload["artifact_count"] == 1
    assert payload["artifacts"] == [
        {"level": "thesis", "id": None, "link": "thesis/aims.md"}
    ]
    text = _dashboard(tmp_path).read_text(encoding="utf-8")
    assert "## Hypotheses" in text
    assert "_No hypothesis artifacts yet._" in text
    assert "_No paper artifacts yet._" in text


def test_a_portfolio_repo_with_no_artifacts_projects_an_empty_dashboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)

    result = runner.invoke(app, ["progress", "dashboard"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["artifact_count"] == 0
    assert payload["artifacts"] == []
    assert "## Milestones" not in _dashboard(tmp_path).read_text(encoding="utf-8")


def test_running_twice_leaves_the_file_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path, thesis=True)
    _pitch(tmp_path, "dc", "---\nstatus:\n  level: paper\n  id: dc\n---\n")

    first = runner.invoke(app, ["progress", "dashboard"])
    written = _dashboard(tmp_path).read_bytes()
    second = runner.invoke(app, ["progress", "dashboard"])

    assert first.exit_code == second.exit_code == 0
    assert json.loads(first.stdout)["changed"] is True
    assert json.loads(second.stdout)["changed"] is False
    assert _dashboard(tmp_path).read_bytes() == written


def test_dry_run_reports_the_change_without_writing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    before = _dashboard(tmp_path).read_text(encoding="utf-8")

    result = runner.invoke(app, ["progress", "dashboard", "--dry-run"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["changed"] is True
    assert _dashboard(tmp_path).read_text(encoding="utf-8") == before


def test_the_generated_dashboard_satisfies_the_stale_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of #130: the never-hand-edit rule becomes enforceable."""
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    _pitch(tmp_path, "dc", "---\nstatus:\n  level: paper\n  id: dc\n---\n")

    stale = runner.invoke(app, ["check"])
    stale_gaps = [
        f
        for f in json.loads(stale.stdout)["findings"]
        if f["file"] == "docs/research/dashboard.md"
    ]
    assert [f["message"] for f in stale_gaps] == [
        "artifact 'dc' exists but is not mentioned in the dashboard"
    ]
    assert "defendable-science progress dashboard" in stale_gaps[0]["remedy"]

    assert runner.invoke(app, ["progress", "dashboard"]).exit_code == 0

    fresh = runner.invoke(app, ["check"])
    assert fresh.exit_code == 0
    assert [
        f
        for f in json.loads(fresh.stdout)["findings"]
        if f["file"] == "docs/research/dashboard.md"
    ] == []
    assert artifact_ids(_dashboard(tmp_path).read_text(encoding="utf-8")) == {"dc"}


def test_the_configured_gate_list_reaches_the_dashboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path, thesis=True)
    Layout.default(tmp_path).milestones.write_text(
        "milestones:\n  - name: transfer-report\n    status: scheduled\n",
        encoding="utf-8",
    )

    assert runner.invoke(app, ["progress", "dashboard"]).exit_code == 0

    text = _dashboard(tmp_path).read_text(encoding="utf-8")
    assert "| transfer-report | scheduled | — | — |" in text
    assert "candidacy" not in text


def test_an_unreadable_artifact_is_written_as_unknown_and_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    _pitch(tmp_path, "dc", "---\nstatus:\n  level: paper\n  id: dc\n---\n")
    Layout.default(tmp_path).paper_docs_dir("dc").joinpath("pitch.md").write_bytes(
        b"\xff\xfe\x00"
    )

    result = runner.invoke(app, ["progress", "dashboard"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["counts"]["unreadable"] == 1
    assert payload["findings"][0]["check"] == "progress"
    # The row is still written, visibly unknown: dropping it would be a
    # projection that lies about what the repo holds.
    text = _dashboard(tmp_path).read_text(encoding="utf-8")
    assert "| unknown | unknown |" in text
    assert "pitch.md could not be read" in text


def test_a_dashboard_that_cannot_be_written_is_reported_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    dashboard = _dashboard(tmp_path)
    dashboard.unlink()
    dashboard.mkdir()

    result = runner.invoke(app, ["progress", "dashboard"])

    assert result.exit_code == 1
    assert "could not write docs/research/dashboard.md" in result.stderr
    assert "still shows the previous projection" in result.stderr


def test_a_root_that_is_not_a_directory_is_refused(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["progress", "dashboard", "--root", str(tmp_path / "x")]
    )

    assert result.exit_code == 1
    assert "does not exist" in result.stderr


def test_an_invalid_layout_block_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    Layout.default(tmp_path).config_file.write_text(
        "layout:\n  nope: x\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["progress", "dashboard"])

    assert result.exit_code == 1
    assert "unknown layout key" in result.stderr


def test_the_command_is_documented_in_help() -> None:
    top = runner.invoke(app, ["--help"])
    group = runner.invoke(app, ["progress", "--help"])
    command = runner.invoke(app, ["progress", "dashboard", "--help"])

    assert "progress" in top.stdout
    assert "dashboard" in group.stdout
    assert "--root" in command.stdout
    assert "--dry-run" in command.stdout
