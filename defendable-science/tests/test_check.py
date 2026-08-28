"""The repo-wide checker (#121)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from defendable_science.check import model as m
from defendable_science.check.probe import FsProbe

if TYPE_CHECKING:
    from pathlib import Path


def _finding(severity: str) -> m.Finding:
    return m.Finding(
        severity=severity,  # type: ignore[arg-type]
        check="tables",
        file="docs/research/papers.md",
        message="something is wrong",
        remedy="run `defendable-science init`",
    )


def test_a_clean_report_is_ok_and_exits_zero() -> None:
    report = m.Report(findings=[])

    assert report.ok is True
    assert report.exit_code == 0
    assert report.counts == {"invalid": 0, "unreadable": 0, "gap": 0}


def test_gaps_alone_do_not_fail_the_run() -> None:
    report = m.Report(findings=[_finding("gap")])

    assert report.ok is True
    assert report.exit_code == 0
    assert report.counts["gap"] == 1


@pytest.mark.parametrize("severity", ["invalid", "unreadable"])
def test_invalid_and_unreadable_both_fail_the_run(severity: str) -> None:
    report = m.Report(findings=[_finding(severity)])

    assert report.ok is False
    assert report.exit_code == 1


def test_to_json_is_shaped_like_the_other_commands() -> None:
    payload = m.Report(findings=[_finding("invalid")]).to_json()

    assert payload["ok"] is False
    assert payload["counts"]["invalid"] == 1
    assert payload["findings"] == [
        {
            "severity": "invalid",
            "check": "tables",
            "file": "docs/research/papers.md",
            "message": "something is wrong",
            "remedy": "run `defendable-science init`",
        }
    ]


def test_fs_probe_reads_globs_and_reports_existence(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.md").write_text("hello", encoding="utf-8")
    probe = FsProbe()

    assert probe.exists(tmp_path / "a" / "x.md") is True
    assert probe.exists(tmp_path / "a" / "nope.md") is False
    assert probe.read_text(tmp_path / "a" / "x.md") == "hello"
    assert probe.glob(tmp_path, "**/*.md") == [tmp_path / "a" / "x.md"]


def test_fs_probe_globs_nothing_under_a_missing_root(tmp_path: Path) -> None:
    assert FsProbe().glob(tmp_path / "absent", "**/*.md") == []


def test_fs_probe_read_text_raises_oserror_for_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(OSError, match=r"absent\.md"):
        FsProbe().read_text(tmp_path / "absent.md")


def test_fs_probe_read_text_raises_oserror_for_a_binary_file(tmp_path: Path) -> None:
    # `UnicodeDecodeError` subclasses `ValueError`, not `OSError`, so it would
    # sail past every `except OSError:` in the checks and surface as a raw
    # traceback. `FsProbe` re-raises it so each check has one error branch.
    binary = tmp_path / "binary.md"
    binary.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(OSError, match="is not valid UTF-8"):
        FsProbe().read_text(binary)
