"""The ``digest extract`` CLI surface — axes, and the validating writer.

The weight is on the negative assertions (spec §11): a rejected cell must leave
**nothing** on disk, and there must be no path at this surface that records a
cell without validating it first (spec §3.3). `test_write_extraction_is_reached_
only_through_validate` pins that structurally, so a later bypass fails a test
rather than shipping.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml
from typer.testing import CliRunner

from defendable_science import cli as cli_mod
from defendable_science.cli import app
from defendable_science.core.frontmatter import split_frontmatter
from defendable_science.digest.artifact import read_cells
from defendable_science.scaffold.layout import Layout

if TYPE_CHECKING:
    from defendable_science.digest.extraction import Cell

runner = CliRunner()

POSITIONING = """# Positioning — p1

Author prose that must survive untouched.

## Concept matrix

| Method | guarantee type | partial monotonicity |
|---|---|---|
| **This paper** | architectural | yes |

More prose.
"""

PLACEHOLDER_POSITIONING = """# Positioning — p1

## Concept matrix

| Method | <attr 1> | <attr 2> |
|---|---|---|
| **This paper** | a | b |
"""

GOOD_CELLS: list[dict[str, Any]] = [
    {
        "citekey": "sill1997monotonic",
        "axis": "guarantee type",
        "value": "architectural — monotone by construction",
        "locator": "§2, Eq. (3)",
    },
    {
        "citekey": "sill1997monotonic",
        "axis": "partial monotonicity",
        "value": "not-addressed",
        "justification": "scoped to fully-monotone inputs in §1; never revisited",
    },
]


def _repo(
    tmp_path: Path,
    *,
    config: str = "",
    positioning: str = POSITIONING,
) -> Path:
    """Build a minimal onboarded repo with one paper's positioning document."""
    (tmp_path / ".defendable-science").mkdir()
    (tmp_path / ".defendable-science" / "config.yml").write_text(
        config, encoding="utf-8"
    )
    docs = tmp_path / "docs" / "research" / "p1" / "paper"
    docs.mkdir(parents=True)
    (docs / "positioning.md").write_text(positioning, encoding="utf-8")
    return tmp_path


def _cells_file(tmp_path: Path, payload: object) -> str:
    """Write a ``--cells`` JSON file and return its path."""
    target = tmp_path / "cells.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return str(target)


def _record(
    root: Path, cells: object, *extra: str, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """Run ``digest extract record --paper p1`` over `cells` from `root`."""
    monkeypatch.chdir(root)
    return runner.invoke(
        app,
        [
            "digest",
            "extract",
            "record",
            "--paper",
            "p1",
            "--cells",
            _cells_file(root, cells),
            *extra,
        ],
    )


# --- axes ----------------------------------------------------------------------


def test_axes_prints_the_matrix_axes_as_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "axes", "--paper", "p1"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["axes"] == ["guarantee type", "partial monotonicity"]
    assert payload["positioning"].endswith("docs/research/p1/paper/positioning.md")


def test_axes_resolves_the_positioning_document_from_the_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--paper`` names the paper; the layout supplies the path (never the cwd)."""
    root = _repo(tmp_path, config="layout:\n  research_root: writing\n")
    moved = root / "writing" / "p1" / "paper"
    moved.mkdir(parents=True)
    (moved / "positioning.md").write_text(POSITIONING, encoding="utf-8")
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "axes", "--paper", "p1"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["positioning"] == str(moved / "positioning.md")


def test_axes_infers_the_paper_from_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root / "docs" / "research" / "p1" / "paper")
    result = runner.invoke(app, ["digest", "extract", "axes"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["axes"] == [
        "guarantee type",
        "partial monotonicity",
    ]


def test_axes_outside_a_paper_exits_2_naming_the_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "axes"])
    assert result.exit_code == 2
    assert "--paper" in result.stderr


def test_axes_positioning_option_overrides_the_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    other = root / "elsewhere.md"
    other.write_text(
        "## Concept matrix\n\n| Method | only axis |\n|---|---|\n", encoding="utf-8"
    )
    monkeypatch.chdir(root)
    result = runner.invoke(
        app, ["digest", "extract", "axes", "--positioning", "elsewhere.md"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["axes"] == ["only axis"]
    # The reported path is absolute whichever branch resolved it, even though a
    # relative --positioning is honoured as typed.
    assert payload["positioning"] == str(other.resolve())


def test_axes_refuses_a_placeholder_matrix_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, positioning=PLACEHOLDER_POSITIONING)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "axes", "--paper", "p1"])
    assert result.exit_code == 1
    assert "template placeholders" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)


def test_axes_reports_a_missing_positioning_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "axes", "--paper", "p2"])
    assert result.exit_code == 1
    assert "positioning document not found" in result.stderr


def test_axes_reports_an_invalid_layout_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, config="layout:\n  nope: x\n")
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["digest", "extract", "axes", "--paper", "p1"])
    assert result.exit_code == 1
    assert "unknown layout key" in result.stderr


# --- record: the happy path ------------------------------------------------------


def test_record_writes_the_artifact_the_layout_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The writer's path and ``Layout.digest`` must be the same file."""
    root = _repo(tmp_path)
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.stderr
    layout = Layout.default(root.resolve())
    artifact = layout.digest("sill1997monotonic")
    assert artifact.parent == layout.digests_dir
    assert artifact.is_file()
    payload = json.loads(result.stdout)
    assert payload["recorded"] == [
        {
            "citekey": "sill1997monotonic",
            "artifact": str(artifact),
            "cells": 2,
            "not_addressed": 1,
            "log_entry": payload["recorded"][0]["log_entry"],
        }
    ]
    assert payload["rejected"] == []
    assert payload["errors"] == []
    assert payload["not_addressed"] == 1
    assert payload["ok"] is True


def test_record_round_trips_through_read_cells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0
    cells: list[Cell] = read_cells(
        Layout.default(root.resolve()).digest("sill1997monotonic")
    )
    assert [c.axis for c in cells] == ["guarantee type", "partial monotonicity"]
    assert cells[0].locator == "§2, Eq. (3)"
    assert cells[1].value == "not-addressed"


def test_record_writes_extraction_and_never_understanding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0
    text = Layout.default(root.resolve()).digest("sill1997monotonic").read_text()
    fm_lines, _body = split_frontmatter(text)
    status = yaml.safe_load("\n".join(fm_lines))["status"]
    # The guarantee-inflation guard: extraction owns `extraction` and only it.
    assert set(status) == {"extraction", "last-updated"}
    assert status["extraction"] == {
        "cells": 2,
        "locators": "ok",
        "in-sample": False,
        "batch-check": "pending",
    }


def test_record_appends_the_accountability_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    result = _record(
        root, GOOD_CELLS, "--log-dir", str(root / "log"), monkeypatch=monkeypatch
    )
    assert result.exit_code == 0
    entries = sorted((root / "log").iterdir())
    assert len(entries) == 1
    assert "kind: extraction" in entries[0].read_text(encoding="utf-8")
    assert json.loads(result.stdout)["recorded"][0]["log_entry"] == str(entries[0])


def test_record_logs_under_the_layout_not_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run from inside a paper, the log must not land in that paper's tree."""
    root = _repo(tmp_path)
    cells = _cells_file(root, GOOD_CELLS)
    paper_dir = root / "docs" / "research" / "p1"
    monkeypatch.chdir(paper_dir)
    result = runner.invoke(app, ["digest", "extract", "record", "--cells", cells])
    assert result.exit_code == 0, result.stderr
    assert not (paper_dir / "docs").exists()
    entries = sorted((root / "docs" / "research" / "defend-log").iterdir())
    assert len(entries) == 1
    assert json.loads(result.stdout)["recorded"][0]["log_entry"] == str(entries[0])


def test_record_reads_the_cells_from_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(
        app,
        ["digest", "extract", "record", "--paper", "p1", "--cells", "-"],
        input=json.dumps(GOOD_CELLS),
    )
    assert result.exit_code == 0, result.stderr
    assert Layout.default(root.resolve()).digest("sill1997monotonic").is_file()


def test_record_creates_the_digests_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``init`` does not scaffold ``literature/digests/``; ``record`` must."""
    root = _repo(tmp_path)
    assert not Layout.default(root.resolve()).digests_dir.exists()
    assert _record(root, GOOD_CELLS, monkeypatch=monkeypatch).exit_code == 0
    assert Layout.default(root.resolve()).digests_dir.is_dir()


def test_record_honours_the_positioning_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    (root / "other.md").write_text(
        "## Concept matrix\n\n| Method | only axis |\n|---|---|\n", encoding="utf-8"
    )
    result = _record(
        root,
        [
            {
                "citekey": "a2020",
                "axis": "only axis",
                "value": "v",
                "locator": "p. 7",
            }
        ],
        "--positioning",
        "other.md",
        monkeypatch=monkeypatch,
    )
    assert result.exit_code == 0, result.stderr
    assert Layout.default(root.resolve()).digest("a2020").is_file()
    assert json.loads(result.stdout)["positioning"] == str(
        (root / "other.md").resolve()
    )


# --- record: refusal (nothing may land) -------------------------------------------

_BAD_BATCHES: list[tuple[str, list[dict[str, Any]], str]] = [
    (
        "no locator",
        [
            {"citekey": "a2020", "axis": "guarantee type", "value": "v"},
            {"citekey": "a2020", "axis": "partial monotonicity", "value": "w"},
        ],
        "has no locator",
    ),
    (
        "vague locator",
        [
            {
                "citekey": "a2020",
                "axis": "guarantee type",
                "value": "v",
                "locator": "see paper",
            },
            {
                "citekey": "a2020",
                "axis": "partial monotonicity",
                "value": "w",
                "locator": "§1",
            },
        ],
        "matches no known form",
    ),
    (
        "omitted axis",
        [
            {
                "citekey": "a2020",
                "axis": "guarantee type",
                "value": "v",
                "locator": "§1",
            }
        ],
        "is missing",
    ),
    (
        "invented axis",
        [
            {
                "citekey": "a2020",
                "axis": "guarantee type",
                "value": "v",
                "locator": "§1",
            },
            {
                "citekey": "a2020",
                "axis": "partial monotonicity",
                "value": "w",
                "locator": "§2",
            },
            {"citekey": "a2020", "axis": "invented", "value": "x", "locator": "§3"},
        ],
        "is not a matrix axis",
    ),
    (
        "duplicate axis",
        [
            {
                "citekey": "a2020",
                "axis": "guarantee type",
                "value": "v",
                "locator": "§1",
            },
            {
                "citekey": "a2020",
                "axis": "guarantee type",
                "value": "v2",
                "locator": "§2",
            },
            {
                "citekey": "a2020",
                "axis": "partial monotonicity",
                "value": "w",
                "locator": "§3",
            },
        ],
        "recorded 2 times",
    ),
    (
        "unjustified not-addressed",
        [
            {
                "citekey": "a2020",
                "axis": "guarantee type",
                "value": "not-addressed",
            },
            {
                "citekey": "a2020",
                "axis": "partial monotonicity",
                "value": "w",
                "locator": "§2",
            },
        ],
        "no justification",
    ),
]


@pytest.mark.parametrize(
    ("cells", "wanted"),
    [pytest.param(c, w, id=name) for name, c, w in _BAD_BATCHES],
)
def test_record_refuses_and_writes_nothing(
    cells: list[dict[str, Any]],
    wanted: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No rule may be satisfied by a write: a rejected paper leaves no trace."""
    root = _repo(tmp_path)
    result = _record(
        root, cells, "--log-dir", str(root / "log"), monkeypatch=monkeypatch
    )
    assert result.exit_code == 1
    assert wanted in result.stderr
    assert "a2020" in result.stderr
    assert not Layout.default(root.resolve()).digest("a2020").exists()
    assert not (root / "log").exists()
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["recorded"] == []
    assert [r["citekey"] for r in payload["rejected"]] == ["a2020"] * len(
        payload["rejected"]
    )
    assert all(r["axis"] for r in payload["rejected"])
    assert any(wanted in r["reason"] for r in payload["rejected"])


def test_record_rejects_per_paper_and_records_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One bad paper must not abort the sweep, and must not half-land."""
    root = _repo(tmp_path)
    cells = [
        *GOOD_CELLS,
        {"citekey": "bad2021", "axis": "guarantee type", "value": "v"},
    ]
    result = _record(root, cells, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    layout = Layout.default(root.resolve())
    assert layout.digest("sill1997monotonic").is_file()
    assert not layout.digest("bad2021").exists()
    payload = json.loads(result.stdout)
    assert [r["citekey"] for r in payload["recorded"]] == ["sill1997monotonic"]
    assert {r["citekey"] for r in payload["rejected"]} == {"bad2021"}


def test_record_reports_a_write_failure_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    artifact = Layout.default(root.resolve()).digest("sill1997monotonic")
    artifact.parent.mkdir(parents=True)
    artifact.write_text("no frontmatter here\n", encoding="utf-8")
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    assert "digest extract record failed for sill1997monotonic" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["recorded"] == []
    assert [e["citekey"] for e in payload["errors"]] == ["sill1997monotonic"]
    assert payload["errors"][0]["artifact"] == str(artifact)
    assert payload["errors"][0]["reason"]


def test_record_reports_what_landed_when_one_paper_fails_to_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A partly-landed batch must say what landed, not only that it failed.

    Aborting on the first write failure leaves the author knowing something went
    wrong but not which papers are already recorded — and re-running the whole
    batch to find out appends a second log entry for each of them.
    """
    root = _repo(tmp_path)
    layout = Layout.default(root.resolve())
    corrupt = layout.digest("zz2021")
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("no frontmatter here\n", encoding="utf-8")
    cells = [
        *GOOD_CELLS,
        {"citekey": "zz2021", "axis": "guarantee type", "value": "v", "locator": "§1"},
        {
            "citekey": "zz2021",
            "axis": "partial monotonicity",
            "value": "w",
            "locator": "§2",
        },
    ]
    result = _record(
        root, cells, "--log-dir", str(root / "log"), monkeypatch=monkeypatch
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert [r["citekey"] for r in payload["recorded"]] == ["sill1997monotonic"]
    assert [e["citekey"] for e in payload["errors"]] == ["zz2021"]
    assert payload["rejected"] == []
    # The good paper really did land, exactly as the report says.
    assert layout.digest("sill1997monotonic").is_file()
    assert len(list((root / "log").iterdir())) == 1


# --- record: malformed input -------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "wanted"),
    [
        pytest.param("{oops", "not valid JSON", id="not-json"),
        pytest.param('{"citekey": "a"}', "must be a JSON array", id="not-an-array"),
        pytest.param("[3]", "must be a JSON object", id="non-object-element"),
        pytest.param(
            '[{"citekey": "a", "axis": "b", "value": "c", "locater": "§1"}]',
            "unknown field",
            id="unknown-field",
        ),
        pytest.param(
            '[{"citekey": "a", "axis": "b", "value": 3}]',
            "must be a string",
            id="wrong-type",
        ),
        pytest.param('[{"axis": "b"}]', "malformed", id="missing-field"),
        pytest.param("[]", "empty", id="empty-array"),
        pytest.param("   ", "empty", id="blank"),
    ],
)
def test_record_refuses_a_malformed_cells_file(
    payload: str, wanted: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    target = root / "cells.json"
    target.write_text(payload, encoding="utf-8")
    monkeypatch.chdir(root)
    result = runner.invoke(
        app,
        ["digest", "extract", "record", "--paper", "p1", "--cells", str(target)],
    )
    assert result.exit_code == 1
    assert wanted in result.stderr
    assert "--cells" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)


def test_record_reports_an_unreadable_cells_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.chdir(root)
    result = runner.invoke(
        app, ["digest", "extract", "record", "--paper", "p1", "--cells", "nope.json"]
    )
    assert result.exit_code == 1
    assert "Traceback" not in (result.stdout + result.stderr)
    assert "nope.json" in result.stderr


def test_record_refuses_a_placeholder_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, positioning=PLACEHOLDER_POSITIONING)
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    assert "template placeholders" in result.stderr


# --- record: configured locator patterns --------------------------------------------


def test_record_accepts_a_configured_locator_pattern(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(
        tmp_path,
        config=(
            "literature:\n"
            "  extraction:\n"
            "    locator_patterns:\n"
            '      - "para\\\\. \\\\d+"\n'
        ),
    )
    cells = [
        {
            "citekey": "a2020",
            "axis": "guarantee type",
            "value": "v",
            "locator": "para. 4",
        },
        {
            "citekey": "a2020",
            "axis": "partial monotonicity",
            "value": "w",
            "locator": "§2",
        },
    ]
    result = _record(root, cells, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.stderr
    assert Layout.default(root.resolve()).digest("a2020").is_file()


@pytest.mark.parametrize(
    ("config", "wanted"),
    [
        pytest.param(
            "literature:\n  extraction: nope\n",
            "'literature.extraction' must be a mapping",
            id="extraction-not-a-mapping",
        ),
        pytest.param(
            "literature:\n  extraction:\n    locator_patterns: nope\n",
            "'literature.extraction.locator_patterns' must be a list",
            id="patterns-not-a-list",
        ),
        pytest.param(
            "literature:\n  extraction:\n    locator_patterns: [3]\n",
            "'literature.extraction.locator_patterns' must be a list",
            id="pattern-not-a-string",
        ),
        pytest.param(
            'literature:\n  extraction:\n    locator_patterns: ["([a-"]\n',
            "invalid locator pattern '([a-'",
            id="invalid-regex",
        ),
        pytest.param(
            'literature:\n  extraction:\n    locator_patterns: ["(?P<x>a)", "(?P<x>b)"]\n',
            "cannot be combined",
            id="colliding-group-names",
        ),
        pytest.param(
            "literature: nope\n",
            "'literature' must be a mapping",
            id="literature-not-a-mapping",
        ),
    ],
)
def test_record_refuses_bad_locator_pattern_config(
    config: str, wanted: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, config=config)
    result = _record(root, GOOD_CELLS, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    assert wanted in result.stderr
    assert not Layout.default(root.resolve()).digest("sill1997monotonic").exists()


# --- exit codes --------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["digest", "extract", "record"], id="missing-required-option"),
        pytest.param(["digest", "extract", "axes", "--nope"], id="unknown-option"),
        pytest.param(["digest", "extract", "nope"], id="unknown-subcommand"),
    ],
)
def test_a_usage_error_still_exits_2(
    argv: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2 belongs to Click. A domain outcome may never take it (#106/#119)."""
    monkeypatch.chdir(_repo(tmp_path))
    assert runner.invoke(app, argv).exit_code == 2


# --- the structural guarantee (spec §3.3) --------------------------------------------


def _callee(func: ast.expr) -> str | None:
    """Return the called name, whether it is bare or attribute-qualified."""
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _calls(node: ast.AST, name: str) -> list[ast.Call]:
    """Return every call to `name` inside `node`."""
    return [
        n for n in ast.walk(node) if isinstance(n, ast.Call) and _callee(n.func) == name
    ]


def test_write_extraction_is_reached_only_through_validate() -> None:
    """Validation and writing are one action — no bypass may be added.

    Pinned structurally, not by example: a flag, an env var or an early branch
    that wrote without validating would satisfy every behavioural test that
    exercises the validated path, and fail this one.

    **What this costs, so the next person does not loosen it by mistake.** The
    test also fails for a refactor that is *not* a bypass: extracting the write
    into a helper — even one called from exactly this loop — moves the call out
    of `extract_record` and out of the loop over the accepted cells, and this
    test cannot tell that apart from a second writer added elsewhere, because
    the two have the same shape. That is deliberate. If you hit it during an
    honest refactor, keep the write inline here; do not weaken the assertions to
    let a call site float free of the validation that produced its arguments.
    """
    tree = ast.parse(Path(cli_mod.__file__).read_text(encoding="utf-8"))
    writes = _calls(tree, "write_extraction")
    assert len(writes) == 1, "write_extraction must have exactly one call site"

    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    record_fn = functions["extract_record"]
    assert _calls(record_fn, "write_extraction") == writes

    # The accepted-cells name is whatever `validate`'s result is unpacked into.
    validations = [
        node
        for node in ast.walk(record_fn)
        if isinstance(node, ast.Assign) and _calls(node.value, "validate")
    ]
    assert len(validations) == 1
    target = validations[0].targets[0]
    assert isinstance(target, ast.Tuple)
    accepted = target.elts[0]
    assert isinstance(accepted, ast.Name)

    # …and the single write sits inside a loop over exactly that name.
    loops = [
        node
        for node in ast.walk(record_fn)
        if isinstance(node, ast.For)
        and accepted.id in ast.dump(node.iter)
        and _calls(node, "write_extraction")
    ]
    assert len(loops) == 1
