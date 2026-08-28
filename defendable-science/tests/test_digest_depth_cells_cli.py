"""``digest depth cells record`` — matrix cells from a depth-mode reading (#142).

Mirrors ``tests/test_digest_cli.py``'s coverage of ``digest extract record``
wherever the two commands share behaviour (validation, per-paper rejection,
the report shape) and adds the provenance-specific negatives: no
``status.extraction`` is ever written, ``triage.yml`` is never touched, an
artifact with no ``status.understanding`` is refused, and an
already-extracted artifact is refused in the other direction.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import yaml
from typer.testing import CliRunner

from defendable_science.cli import app
from defendable_science.core.frontmatter import split_frontmatter
from defendable_science.digest.artifact import read_cells
from defendable_science.scaffold.layout import Layout

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()

CITEKEY = "sill1997monotonic"

POSITIONING = """# Positioning — p1

Author prose that must survive untouched.

## Concept matrix

| Method | guarantee type | partial monotonicity |
|---|---|---|
| **This paper** | architectural | yes |

More prose.
"""

DEPTH_SEED = (
    "---\n"
    "status:\n"
    '  understanding: {status: gaps, unresolved: ["why convexity matters"]}'
    "  # defend\n"
    "  last-updated: 2026-08-01\n"
    "---\n"
    "\n"
    f"# {CITEKEY}\n"
    "\n"
    "The author's own summary prose.\n"
)

GOOD_CELLS: list[dict[str, Any]] = [
    {
        "citekey": CITEKEY,
        "axis": "guarantee type",
        "value": "architectural — monotone by construction",
        "locator": "§2, Eq. (3)",
    },
    {
        "citekey": CITEKEY,
        "axis": "partial monotonicity",
        "value": "not-addressed",
        "justification": "scoped to fully-monotone inputs in §1; never revisited",
    },
]


def _repo(tmp_path: Path, *, config: str = "", positioning: str = POSITIONING) -> Path:
    (tmp_path / ".defendable-science").mkdir()
    (tmp_path / ".defendable-science" / "config.yml").write_text(
        config, encoding="utf-8"
    )
    docs = tmp_path / "docs" / "research" / "p1" / "paper"
    docs.mkdir(parents=True)
    (docs / "positioning.md").write_text(positioning, encoding="utf-8")
    return tmp_path


def _seed_depth_digest(
    root: Path, citekey: str = CITEKEY, seed: str = DEPTH_SEED
) -> Path:
    """Write a depth-mode reading record — ``status.understanding``, no cells."""
    layout = Layout.default(root.resolve())
    artifact = layout.digest(citekey)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(seed, encoding="utf-8")
    return artifact


def _cells_file(tmp_path: Path, payload: object) -> str:
    target = tmp_path / "cells.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return str(target)


def _record(
    root: Path, cells: object, *extra: str, monkeypatch: pytest.MonkeyPatch
) -> Any:
    monkeypatch.chdir(root)
    return runner.invoke(
        app,
        [
            "digest",
            "depth",
            "cells",
            "record",
            "--paper",
            "p1",
            "--cells",
            _cells_file(root, cells),
            *extra,
        ],
    )


# --- the happy path --------------------------------------------------------------


def test_record_writes_the_artifact_the_layout_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _seed_depth_digest(root)
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.stderr
    layout = Layout.default(root.resolve())
    artifact = layout.digest(CITEKEY)
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["recorded"] == [
        {
            "citekey": CITEKEY,
            "artifact": str(artifact),
            "cells": 2,
            "not_addressed": 1,
            "log_entry": payload["recorded"][0]["log_entry"],
        }
    ]
    assert payload["rejected"] == []
    assert payload["errors"] == []


def test_record_round_trips_through_read_cells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _seed_depth_digest(root)
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0
    cells = read_cells(Layout.default(root.resolve()).digest(CITEKEY))
    assert [c.axis for c in cells] == ["guarantee type", "partial monotonicity"]
    assert cells[0].locator == "§2, Eq. (3)"
    assert cells[1].value == "not-addressed"


def test_record_never_writes_status_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    artifact = _seed_depth_digest(root)
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0

    fm, _ = split_frontmatter(artifact.read_text(encoding="utf-8"))
    status = yaml.safe_load("\n".join(fm))["status"]
    assert set(status) == {"understanding", "last-updated"}
    assert "extraction" not in status


def test_record_never_touches_triage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`extracted` / `extraction-cells` describe extraction's own regime."""
    root = _repo(tmp_path)
    _seed_depth_digest(root)
    triage = root / "docs" / "research" / "literature" / "triage.yml"
    assert not triage.exists()
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0
    assert not triage.exists()


def test_record_leaves_understanding_and_prose_byte_identical_except_cells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    artifact = _seed_depth_digest(root)
    before_fm, before_body = split_frontmatter(DEPTH_SEED)
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0

    after_fm, after_body = split_frontmatter(artifact.read_text(encoding="utf-8"))
    assert [ln for ln in before_fm if "last-updated" not in ln] == [
        ln for ln in after_fm if "last-updated" not in ln
    ]
    assert [ln for ln in before_body if ln.strip()] == [
        ln
        for ln in after_body[
            : after_body.index(
                "<!-- defendable-science: extracted cells (generated) -->"
            )
        ]
        if ln.strip()
    ]


def test_record_reads_the_cells_from_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _seed_depth_digest(root)
    monkeypatch.chdir(root)
    result = runner.invoke(
        app,
        ["digest", "depth", "cells", "record", "--paper", "p1", "--cells", "-"],
        input=json.dumps(GOOD_CELLS),
    )
    assert result.exit_code == 0, result.stderr


def test_record_honours_the_positioning_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _seed_depth_digest(root)
    other = root / "elsewhere.md"
    other.write_text(POSITIONING, encoding="utf-8")
    monkeypatch.chdir(root)
    result = runner.invoke(
        app,
        [
            "digest",
            "depth",
            "cells",
            "record",
            "--positioning",
            "elsewhere.md",
            "--cells",
            _cells_file(root, GOOD_CELLS),
        ],
    )
    assert result.exit_code == 0, result.stderr


# --- refusals ----------------------------------------------------------------------


def test_record_refuses_a_missing_depth_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    assert "digest artifact not found" in result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["errors"][0]["citekey"] == CITEKEY


def test_record_refuses_an_artifact_with_no_understanding_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _seed_depth_digest(root, seed="---\nstatus:\n---\n")
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    assert "no 'status.understanding' block" in result.stderr


def test_record_refuses_an_already_extracted_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    extract_result = runner.invoke(
        app,
        [
            "digest",
            "extract",
            "record",
            "--paper",
            "p1",
            "--cells",
            _cells_file(root, GOOD_CELLS),
        ],
    )
    assert extract_result.exit_code == 0, extract_result.stderr

    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    assert "already carries a 'status.extraction'" in result.stderr


def test_record_rejects_a_locator_the_same_way_extraction_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same `extraction.is_valid_locator` path as `extract record` (#142)."""
    root = _repo(tmp_path)
    _seed_depth_digest(root)
    bad = [
        {
            "citekey": CITEKEY,
            "axis": "guarantee type",
            "value": "architectural",
            "locator": "somewhere in the paper",
        },
        GOOD_CELLS[1],
    ]
    result = _record(root, bad, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["recorded"] == []
    assert any("matches no known form" in r["reason"] for r in payload["rejected"])
    artifact = Layout.default(root.resolve()).digest(CITEKEY)
    assert "extracted cells" not in artifact.read_text(encoding="utf-8")


def test_record_rejects_per_paper_and_records_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(
        tmp_path,
        positioning=POSITIONING.replace(
            "| **This paper** | architectural | yes |",
            "| other2020 | x | y |\n| **This paper** | architectural | yes |",
        ),
    )
    _seed_depth_digest(root, CITEKEY)
    _seed_depth_digest(
        root,
        "other2020",
        seed=DEPTH_SEED.replace(CITEKEY, "other2020"),
    )
    cells = [
        *GOOD_CELLS,
        {
            "citekey": "other2020",
            "axis": "guarantee type",
            "value": "learned",
            "locator": None,
        },
    ]
    result = _record(root, cells, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert [r["citekey"] for r in payload["recorded"]] == [CITEKEY]
    assert any(r["citekey"] == "other2020" for r in payload["rejected"])


def test_record_still_emits_a_report_when_the_input_is_unusable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _seed_depth_digest(root)
    result = _record(root, [], monkeypatch=monkeypatch)
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["axes"] is None
    assert payload["error"] is not None
    assert payload["recorded"] == []


def test_record_refuses_a_malformed_cells_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _seed_depth_digest(root)
    cells_path = root / "cells.json"
    cells_path.write_text("not json", encoding="utf-8")
    monkeypatch.chdir(root)
    result = runner.invoke(
        app,
        [
            "digest",
            "depth",
            "cells",
            "record",
            "--paper",
            "p1",
            "--cells",
            str(cells_path),
        ],
    )
    assert result.exit_code == 1
    assert "not valid JSON" in result.stderr


def test_record_reports_an_unreadable_cells_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _seed_depth_digest(root)
    monkeypatch.chdir(root)
    result = runner.invoke(
        app,
        [
            "digest",
            "depth",
            "cells",
            "record",
            "--paper",
            "p1",
            "--cells",
            "nope.json",
        ],
    )
    assert result.exit_code == 1
    assert "Traceback" not in (result.stdout + result.stderr)


def test_record_outside_a_paper_exits_2_naming_the_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _seed_depth_digest(root)
    monkeypatch.chdir(root)
    result = runner.invoke(
        app,
        [
            "digest",
            "depth",
            "cells",
            "record",
            "--cells",
            _cells_file(root, GOOD_CELLS),
        ],
    )
    assert result.exit_code == 2
    assert "--paper" in result.stderr


def test_record_refuses_the_self_row_as_a_citekey(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rejected by `validate` before any artifact is touched — no seed needed."""
    root = _repo(tmp_path)
    cells = [
        {
            "citekey": "**This paper**",
            "axis": "guarantee type",
            "value": "architectural",
            "locator": "§2",
        },
        {
            "citekey": "**This paper**",
            "axis": "partial monotonicity",
            "value": "yes",
            "locator": "§2",
        },
    ]
    result = _record(root, cells, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["recorded"] == []
    assert "author's own delta" in payload["rejected"][0]["reason"]
    digests = root / "docs" / "research" / "literature" / "digests"
    assert not digests.exists() or not list(digests.glob("*.md"))
