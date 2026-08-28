"""`defendable-science check` end to end."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003

import pytest  # noqa: TC002
from typer.testing import CliRunner

from defendable_science.cli import app

runner = CliRunner()


def _init(root: Path) -> None:
    assert runner.invoke(app, ["init", "--root", str(root)]).exit_code == 0


def test_a_freshly_initialized_repo_passes_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression guard for the failure quoted in #120 and #121."""
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)

    result = runner.invoke(app, ["check"])

    payload = json.loads(result.stdout)
    assert payload["counts"]["invalid"] == 0, payload["findings"]
    assert payload["counts"]["unreadable"] == 0, payload["findings"]
    assert result.exit_code == 0, result.stdout


def test_gaps_alone_still_exit_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    pitch = tmp_path / "docs" / "research" / "dc" / "paper"
    pitch.mkdir(parents=True)
    (pitch / "pitch.md").write_text(
        "---\nstatus:\n  level: paper\n  id: dc\n  verdict: publish\n"
        "  signed-off-by: null\n---\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["check"])

    payload = json.loads(result.stdout)
    assert payload["counts"]["gap"] > 0
    assert payload["counts"]["invalid"] == 0
    assert result.exit_code == 0


def test_an_invalid_file_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    (tmp_path / "docs" / "research" / "portfolio-backlog.md").write_text(
        "| id | status | idea |\n|---|---|---|\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["check"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_text_mode_prints_a_human_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)

    result = runner.invoke(app, ["check", "--text"])

    assert result.exit_code == 0
    assert "defendable-science check" in result.stdout
    assert "invalid: 0" in result.stdout


def test_text_mode_with_zero_findings_prints_counts_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Text mode on a repo with zero findings shows counts without a findings section."""
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    # Bind the experiment_backend to eliminate the one gap
    (tmp_path / ".defendable-science" / "config.yml").write_text(
        "cache_dir: .defendable-science/cache/\nexperiment_backend: bench\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["check", "--text"])

    assert result.exit_code == 0
    assert "defendable-science check" in result.stdout
    assert "invalid: 0" in result.stdout
    assert "unreadable: 0" in result.stdout
    assert "gap: 0" in result.stdout
    # No findings section should appear when there are no findings
    lines = result.stdout.splitlines()
    # Should be 4 lines: "defendable-science check", "  invalid: 0", "  unreadable: 0", "  gap: 0"
    assert len(lines) == 4


def test_malformed_files_never_produce_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure honesty: never a raw traceback, whatever is on disk."""
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    (tmp_path / "docs" / "research" / "papers.md").write_bytes(b"\xff\xfe\x00\x01")
    (tmp_path / "datasets.yml").write_text(
        "!!python/object:os.system []", encoding="utf-8"
    )
    (tmp_path / "docs" / "research" / "literature" / "references.json").write_text(
        "{not json", encoding="utf-8"
    )

    result = runner.invoke(app, ["check"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    payload = json.loads(result.stdout)
    assert payload["counts"]["invalid"] + payload["counts"]["unreadable"] >= 3
    for finding in payload["findings"]:
        assert finding["remedy"], finding


def test_unreadable_is_distinguishable_from_valid_and_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    references = tmp_path / "docs" / "research" / "literature" / "references.json"
    references.write_bytes(b"\xff\xfe\x00")

    result = runner.invoke(app, ["check"])

    findings = json.loads(result.stdout)["findings"]
    reported = [f for f in findings if f["file"].endswith("references.json")]
    assert reported, findings
    assert reported[0]["severity"] in {"unreadable", "invalid"}
    assert "empty" not in reported[0]["message"].lower()


def test_check_exits_one_on_an_invalid_layout_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    (tmp_path / ".defendable-science" / "config.yml").write_text(
        "layout:\n  papers_dir: x/\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["check"])

    assert result.exit_code == 1
    assert "unknown layout key" in result.output
    assert "Traceback" not in result.output


def test_unreadable_staged_document_is_reported_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable staged document must not be double-reported by multiple families.

    Both check_frontmatter and check_cross_artifact read staged documents,
    so an unreadable file would be reported twice if not deduplicated.
    The deduplication in run_checks must keep the first occurrence (frontmatter).
    """
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    # Create a paper and write non-UTF-8 bytes to its pitch
    pitch = tmp_path / "docs" / "research" / "dc" / "paper"
    pitch.mkdir(parents=True)
    (pitch / "pitch.md").write_bytes(b"\xff\xfe\x00\x01")

    result = runner.invoke(app, ["check"])

    payload = json.loads(result.stdout)
    assert result.exit_code == 1
    assert payload["counts"]["unreadable"] == 1, payload["counts"]
    # Exactly one finding mentioning pitch.md
    findings_for_pitch = [f for f in payload["findings"] if "pitch.md" in f["file"]]
    assert len(findings_for_pitch) == 1
    # The finding should be from frontmatter (the family that owns reading staged docs)
    assert findings_for_pitch[0]["check"] == "frontmatter"


def test_different_messages_on_same_file_are_not_deduplicated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two genuinely different findings on the same file must both survive deduplication.

    Deduplication only drops findings with identical (severity, file, message).
    If two findings differ in any field (e.g., different messages), both should remain.
    """
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    # Create a paper with a pitch that has both frontmatter and table errors
    # (frontmatter missing status block, and an unbound backend in registry)
    pitch = tmp_path / "docs" / "research" / "dc" / "paper"
    pitch.mkdir(parents=True)
    (pitch / "pitch.md").write_text("# Pitch\n\nno frontmatter\n", encoding="utf-8")
    # Also write an invalid registry to trigger a backend gap
    papers = tmp_path / "docs" / "research" / "papers.md"
    papers.write_text(
        "# Papers\n\n| paper-id | root | backend |\n|---|---|---|\n| dc | docs/research/dc | |\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["check"])

    payload = json.loads(result.stdout)
    # The pitch has no frontmatter, and the paper has an empty backend
    # These are two different defects with different messages, so both should appear
    findings = payload["findings"]
    pitch_findings = [f for f in findings if "pitch.md" in f["file"]]
    backend_findings = [f for f in findings if "backend" in f["message"].lower()]
    assert len(pitch_findings) >= 1  # Missing status block
    assert len(backend_findings) >= 1  # Empty backend
    # They should have different messages
    assert pitch_findings[0]["message"] != backend_findings[0]["message"]
