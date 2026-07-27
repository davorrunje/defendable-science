"""Tests for the ``defend record`` helper (honest-scholar#4, honest-scholar#68)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import yaml
from typer.testing import CliRunner

from honest_scholar.cli import app
from honest_scholar.defend import record as r

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

_ARTIFACT = """\
---
status:
  level: hypothesis
  id: 2026-07-18-x
  verdict: pending
  understanding: {status: pending, unresolved: []}   # written by the defend skill
  last-updated: 2026-01-01
---

# Hypothesis: x

Body stays intact.
"""


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / "findings.md"
    path.write_text(_ARTIFACT, encoding="utf-8")
    return path


def _resolved(point: str = "assumptions") -> r.PointRecord:
    """Build a minimal resolved point record for tests that don't care about content."""
    return r.PointRecord(
        point=point,
        source_quote="the paper/artifact text grounding this point",
        reader_answer="a correct, articulated answer",
        resolved=True,
    )


def _gap(note: str, *, point: str = "assumptions") -> r.PointRecord:
    """Build a minimal unresolved point record carrying a specific gap fact."""
    return r.PointRecord(
        point=point,
        source_quote="the paper/artifact text grounding this point",
        reader_answer="an incomplete or wrong answer",
        resolved=False,
        gap_note=note,
    )


def test_patch_sets_understanding_and_preserves_rest() -> None:
    out = r.patch_understanding(_ARTIFACT, "ok", [], last_updated="2026-07-18")
    parsed = yaml.safe_load(out.split("---")[1])
    assert parsed["status"]["understanding"] == {"status": "ok", "unresolved": []}
    assert str(parsed["status"]["last-updated"]) == "2026-07-18"
    # Body and unrelated frontmatter untouched.
    assert "Body stays intact." in out
    assert "verdict: pending" in out
    assert "# written by the defend skill" in out  # comment preserved


def test_patch_records_gaps() -> None:
    out = r.patch_understanding(
        _ARTIFACT,
        "gaps",
        ["no answer to the falsification probe"],
        last_updated="2026-07-18",
    )
    parsed = yaml.safe_load(out.split("---")[1])
    assert parsed["status"]["understanding"]["status"] == "gaps"
    assert parsed["status"]["understanding"]["unresolved"] == [
        "no answer to the falsification probe"
    ]


def test_patch_inserts_missing_fields() -> None:
    minimal = "---\nstatus:\n  level: hypothesis\n---\n\n# body\n"
    out = r.patch_understanding(minimal, "ok", [], last_updated="2026-07-18")
    parsed = yaml.safe_load(out.split("---")[1])
    assert parsed["status"]["understanding"] == {"status": "ok", "unresolved": []}
    assert str(parsed["status"]["last-updated"]) == "2026-07-18"


def test_patch_rejects_bad_status() -> None:
    with pytest.raises(r.RecordError, match="status must be"):
        r.patch_understanding(_ARTIFACT, "great", [], last_updated="2026-07-18")


def test_patch_requires_frontmatter() -> None:
    with pytest.raises(r.RecordError, match="no YAML frontmatter"):
        r.patch_understanding("# no frontmatter\n", "ok", [], last_updated="x")


def test_patch_is_idempotent() -> None:
    once = r.patch_understanding(_ARTIFACT, "ok", [], last_updated="2026-07-18")
    twice = r.patch_understanding(once, "ok", [], last_updated="2026-07-18")
    assert once == twice


def test_record_ok_writes_log(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    result = r.record(
        artifact,
        "methodology",
        [_resolved()],
        log_dir=tmp_path / "log",
        today="2026-07-18",
    )
    assert result.outcome == "resolved"
    assert result.log_entry.is_file()
    entry = yaml.safe_load(result.log_entry.read_text(encoding="utf-8"))[0]
    assert entry["target"] == "methodology"
    assert entry["status"] == "ok"


def test_record_bad_target_raises(tmp_path: Path) -> None:
    with pytest.raises(r.RecordError, match="target must be"):
        r.record(_artifact(tmp_path), "vibes", [], today="2026-07-18")


def test_record_paper_comprehension_target_accepted(tmp_path: Path) -> None:
    result = r.record(
        _artifact(tmp_path),
        "paper-comprehension",
        [_resolved(point="key-result")],
        log_dir=tmp_path / "log",
        today="2026-07-18",
    )
    assert result.outcome == "resolved"


def test_record_gaps_passed_requires_sign_off(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    with pytest.raises(r.RecordError, match="requires a named"):
        r.record(
            artifact,
            "claim",
            [_gap("unanswered probe")],
            override=True,
            today="2026-07-18",
        )


def test_record_override_with_sign_off(tmp_path: Path) -> None:
    result = r.record(
        _artifact(tmp_path),
        "claim",
        [_gap("unanswered probe")],
        override=True,
        signed_off_by="D. Runje",
        log_dir=tmp_path / "log",
        today="2026-07-18",
    )
    assert result.outcome == "overridden"


def test_record_per_gap_acknowledgement(tmp_path: Path) -> None:
    result = r.record(
        _artifact(tmp_path),
        "claim",
        [_gap("gap one")],
        acknowledgements=[{"gap": "gap one", "by": "D. Runje"}],
        signed_off_by="D. Runje",
        log_dir=tmp_path / "log",
        today="2026-07-18",
    )
    assert result.outcome == "acknowledged-per-gap"


def test_record_writes_transcript(tmp_path: Path) -> None:
    result = r.record(
        _artifact(tmp_path),
        "methodology",
        [_resolved()],
        transcript="Q: why TOST? A: ...",
        log_dir=tmp_path / "log",
        today="2026-07-18",
    )
    assert result.transcript is not None
    assert result.transcript.read_text(encoding="utf-8").startswith("Q: why TOST?")


def test_record_never_writes_a_verdict_field(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    r.record(artifact, "claim", [], log_dir=tmp_path / "log", today="2026-07-18")
    parsed = yaml.safe_load(artifact.read_text(encoding="utf-8").split("---")[1])
    # The verdict the artifact already had is untouched; record never sets it.
    assert parsed["status"]["verdict"] == "pending"


def test_record_unresolved_outcome(tmp_path: Path) -> None:
    result = r.record(
        _artifact(tmp_path),
        "claim",
        [_gap("gap")],
        log_dir=tmp_path / "log",
        today="2026-07-18",
    )
    assert result.outcome == "unresolved"


def test_record_log_dedup(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    r.record(artifact, "claim", [], log_dir=tmp_path / "log", today="2026-07-18")
    second = r.record(
        artifact, "claim", [], log_dir=tmp_path / "log", today="2026-07-18"
    )
    assert second.log_entry.name.endswith("-2.yml")


def test_patch_unterminated_frontmatter() -> None:
    with pytest.raises(r.RecordError, match="unterminated"):
        r.patch_understanding("---\nstatus:\n  x: 1\n", "ok", [], last_updated="d")


def test_patch_no_status_block() -> None:
    with pytest.raises(r.RecordError, match="no 'status:'"):
        r.patch_understanding(
            "---\nfoo: bar\n---\n\nbody\n", "ok", [], last_updated="d"
        )


def test_patch_blank_line_and_trailing_top_key() -> None:
    text = (
        "---\nstatus:\n\n  understanding: {status: pending, unresolved: []}\n"
        "foo: bar\n---\n\nbody\n"
    )
    out = r.patch_understanding(text, "ok", [], last_updated="2026-07-18")
    assert "foo: bar" in out
    assert '"status": "ok"' in out


def test_patch_zero_indent_line_after_status() -> None:
    text = "---\nstatus:\nfoo: bar\n  understanding: {status: pending, unresolved: []}\n---\nbody\n"
    out = r.patch_understanding(text, "ok", [], last_updated="2026-07-18")
    assert "foo: bar" in out


def test_patch_status_block_without_children() -> None:
    out = r.patch_understanding(
        "---\nstatus:\n---\n\nbody\n", "ok", [], last_updated="d"
    )
    assert "understanding" in out
    assert "last-updated" in out


# --- PointRecord / evidentiary log (ADR-0033) --------------------------------


def test_point_record_defaults_location_and_gap_note_to_none() -> None:
    point = r.PointRecord(
        point="limitations",
        source_quote="quote",
        reader_answer="answer",
        resolved=True,
    )
    assert point.location is None
    assert point.gap_note is None


def test_unresolved_gaps_prefers_gap_note_over_point() -> None:
    points = [_gap("could not explain the falsification probe", point="assumptions")]
    assert r._unresolved_gaps(points) == ["could not explain the falsification probe"]


def test_unresolved_gaps_falls_back_to_point_name_without_gap_note() -> None:
    bare_gap = r.PointRecord(
        point="key-result",
        source_quote="quote",
        reader_answer="answer",
        resolved=False,
    )
    assert r._unresolved_gaps([bare_gap]) == ["key-result"]


def test_unresolved_gaps_skips_resolved_points() -> None:
    points = [_resolved(point="method"), _gap("gap", point="limitations")]
    assert r._unresolved_gaps(points) == ["gap"]


def test_record_log_carries_full_point_evidence(tmp_path: Path) -> None:
    resolved = r.PointRecord(
        point="key-result",
        source_quote="We achieve 99% accuracy (Table 2).",
        location="Table 2",
        reader_answer="They beat the baseline by a wide margin on the benchmark.",
        resolved=True,
    )
    gap = _gap("could not explain why non-convexity breaks it", point="limitations")
    result = r.record(
        _artifact(tmp_path),
        "paper-comprehension",
        [resolved, gap],
        log_dir=tmp_path / "log",
        today="2026-07-18",
    )
    entry = yaml.safe_load(result.log_entry.read_text(encoding="utf-8"))[0]
    assert entry["points"] == [
        {
            "point": "key-result",
            "source_quote": "We achieve 99% accuracy (Table 2).",
            "reader_answer": (
                "They beat the baseline by a wide margin on the benchmark."
            ),
            "resolved": True,
            "location": "Table 2",
            "gap_note": None,
        },
        {
            "point": "limitations",
            "source_quote": "the paper/artifact text grounding this point",
            "reader_answer": "an incomplete or wrong answer",
            "resolved": False,
            "location": None,
            "gap_note": "could not explain why non-convexity breaks it",
        },
    ]
    assert entry["status"] == "gaps"


# --- CLI ---------------------------------------------------------------------


def test_cli_record(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["outcome"] == "resolved"


def test_cli_record_transcript_from_stdin(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--transcript",
            "-",
            "--log-dir",
            str(tmp_path / "log"),
        ],
        input="piped transcript\n",
    )
    assert result.exit_code == 0
    assert (tmp_path / "log").exists()


def test_cli_record_unreadable_transcript_exits_1_cleanly(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--transcript",
            str(tmp_path / "missing.md"),  # unreadable transcript
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 1  # clean exit, not a traceback
    assert "defend record failed" in result.stderr


def _points_file(tmp_path: Path, points: list[dict[str, object]]) -> Path:
    path = tmp_path / "points.json"
    path.write_text(json.dumps(points), encoding="utf-8")
    return path


def test_cli_record_points_from_file(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    points = _points_file(
        tmp_path,
        [
            {
                "point": "assumptions",
                "source_quote": "quote",
                "reader_answer": "answer",
                "resolved": True,
            }
        ],
    )
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--points",
            str(points),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["outcome"] == "resolved"


def test_cli_record_points_without_sign_off_fails(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    points = _points_file(
        tmp_path,
        [
            {
                "point": "assumptions",
                "source_quote": "quote",
                "reader_answer": "wrong",
                "resolved": False,
                "gap_note": "unanswered probe",
            }
        ],
    )
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "claim",
            "--points",
            str(points),
            "--override",
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 1


def test_cli_record_points_with_transcript_and_acks(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    transcript = tmp_path / "t.md"
    transcript.write_text("Q: why? A: because.", encoding="utf-8")
    points = _points_file(
        tmp_path,
        [
            {
                "point": "assumptions",
                "source_quote": "quote",
                "reader_answer": "wrong",
                "resolved": False,
                "gap_note": "gap one",
            }
        ],
    )
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "claim",
            "--points",
            str(points),
            "--acks",
            "gap one::D. Runje",
            "--signed-off-by",
            "D. Runje",
            "--transcript",
            str(transcript),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["outcome"] == "acknowledged-per-gap"


def test_cli_record_points_from_stdin(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "paper-comprehension",
            "--points",
            "-",
            "--log-dir",
            str(tmp_path / "log"),
        ],
        input=json.dumps(
            [
                {
                    "point": "key-result",
                    "source_quote": "quote",
                    "reader_answer": "answer",
                    "resolved": True,
                }
            ]
        ),
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["outcome"] == "resolved"


def test_cli_record_unreadable_points_file_exits_1_cleanly(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--points",
            str(tmp_path / "missing.json"),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 1
    assert "defend record failed" in result.stderr


def test_cli_record_malformed_points_json_exits_1_cleanly(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    points = tmp_path / "points.json"
    points.write_text("not json", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--points",
            str(points),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 1
    assert "defend record failed" in result.stderr


def test_cli_record_points_not_a_json_array_exits_1_cleanly(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    points = tmp_path / "points.json"
    points.write_text(json.dumps({"point": "x"}), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--points",
            str(points),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 1
    assert "defend record failed" in result.stderr


def test_cli_record_points_item_not_an_object_exits_1_cleanly(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    points = tmp_path / "points.json"
    points.write_text(json.dumps(["not an object"]), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--points",
            str(points),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 1
    assert "defend record failed" in result.stderr


def test_cli_record_points_bad_shape_exits_1_cleanly(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    points = _points_file(tmp_path, [{"point": "x", "unexpected_key": "y"}])
    result = runner.invoke(
        app,
        [
            "defend",
            "record",
            "--artifact",
            str(artifact),
            "--target",
            "methodology",
            "--points",
            str(points),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )
    assert result.exit_code == 1
    assert "defend record failed" in result.stderr
