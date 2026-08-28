"""Every machine-read file `init` writes, checked with its own loader (#120)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from defendable_science import cli
from defendable_science.core.config import load_config
from defendable_science.dataset import manifest as manifest_mod
from defendable_science.exploration import backlog as b
from defendable_science.literature import registry as reg
from defendable_science.scaffold import layout as lay
from defendable_science.scaffold import render as r
from defendable_science.scaffold.layout import Layout

#: The repo checkout, which carries the plugin-side templates the wheel cannot.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_cache_dir_is_the_cli_cache_root() -> None:
    """One location: the .gitignore entry, config.yml value and runtime cache."""
    assert Path(r.DEFAULT_CACHE_DIR) == cli._DEFAULT_CACHE_ROOT


def test_rendered_papers_registry_accepts_a_promote(tmp_path: Path) -> None:
    """The registry `promote --scaffold` could not write into (#120)."""
    path = tmp_path / "papers.md"
    path.write_text(r.render_papers_registry(), encoding="utf-8")

    b.append_papers_registry(path, "an-idea", "docs/research/an-idea", "bench")

    assert "| an-idea | docs/research/an-idea | bench |" in path.read_text(
        encoding="utf-8"
    )


def test_rendered_backlogs_carry_the_canonical_column_profiles() -> None:
    portfolio = b.Backlog.loads(r.render_portfolio_backlog(), "paper")
    paper = b.Backlog.loads(r.render_paper_backlog(), "hypothesis")

    assert portfolio.columns == b.PAPER_COLUMNS
    assert paper.columns == b.HYPOTHESIS_COLUMNS
    assert portfolio.rows == []
    assert paper.rows == []


def test_a_scaffolded_papers_backlog_is_the_rendered_one(tmp_path: Path) -> None:
    """One artifact, one shape: `init` and a promotion write the same file."""
    layout = Layout.default(tmp_path)
    layout.research_root.mkdir(parents=True)

    root = b.scaffold_paper(layout, "depth-collapse", "a follow-up paper")

    scaffolded = (root / "backlog.md").read_text(encoding="utf-8")

    assert scaffolded == r.render_paper_backlog()


def test_rendered_portfolio_backlog_accepts_a_park(tmp_path: Path) -> None:
    """The exact failure quoted in #120 and #121."""
    path = tmp_path / "portfolio-backlog.md"
    path.write_text(r.render_portfolio_backlog(), encoding="utf-8")

    board = b.Backlog.load(path, "paper")
    row = board.park("An idea", "smoke")
    board.save(path)

    assert row["one-line"] == "An idea"
    assert row["provenance"] == "smoke"


def test_rendered_references_is_a_loadable_empty_csl_json(tmp_path: Path) -> None:
    path = tmp_path / "references.json"
    path.write_text(r.render_references(), encoding="utf-8")

    assert json.loads(path.read_text(encoding="utf-8")) == []
    assert reg.load_registry(path).entries == []


def test_rendered_triage_is_a_loadable_empty_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "triage.yml"
    path.write_text(r.render_triage(), encoding="utf-8")

    assert reg.load_triage(path) == {}


def test_rendered_manifest_validates_clean(tmp_path: Path) -> None:
    path = tmp_path / "datasets.yml"
    path.write_text(r.render_datasets_manifest(), encoding="utf-8")

    parsed = manifest_mod.load(path)
    report = manifest_mod.validate(parsed)

    assert report.ok
    assert report.errors == []
    assert parsed.datasets == []


def test_rendered_config_loads_and_holds_nulls_not_placeholders(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(r.render_config(), encoding="utf-8")

    config = load_config(path)

    assert config["cache_dir"] == r.DEFAULT_CACHE_DIR
    assert config["experiment_backend"] is None
    assert config["engineering_backend"] is None
    assert config["literature"]["anchors"] == []
    assert config["literature"]["mailto"] is None
    assert "layout" not in config  # a default repo records nothing

    def _no_placeholder(node: object) -> None:
        if isinstance(node, str):
            assert not node.startswith("<"), node
        elif isinstance(node, dict):
            for value in node.values():
                _no_placeholder(value)
        elif isinstance(node, list):
            for value in node:
                _no_placeholder(value)

    _no_placeholder(config)


def test_rendered_milestones_carries_every_gate_unstarted_and_undated() -> None:
    """A gate is undated until the author dates it — never a placeholder string."""
    gates = yaml.safe_load(r.render_milestones())["milestones"]

    assert [gate["name"] for gate in gates] == list(r.PROGRAM_GATES)
    for gate in gates:
        assert set(gate) == {"name", "status", "date", "next-deadline"}
        assert gate["status"] == "not-started"
        assert gate["date"] is None
        assert gate["next-deadline"] is None


def test_rendered_milestones_matches_the_shipped_template() -> None:
    """One artifact, one shape — whichever side scaffolded it (#120).

    Prose deliberately differs (the shipped template is the fuller authoring
    skeleton); the parsed structure must not, and nothing at runtime can enforce
    that because the wheel ships only ``defendable_science`` (ADR-0026).
    """
    shipped = _REPO_ROOT / "resources" / "templates" / "thesis" / "milestones.yml"
    assert shipped.is_file(), (
        f"{shipped} is missing; the drift guard cannot run. These tests are meant "
        "to run from a repo checkout, which has both artifacts."
    )

    assert yaml.safe_load(r.render_milestones()) == yaml.safe_load(
        shipped.read_text(encoding="utf-8")
    )


def test_rendered_dashboard_says_it_has_no_generator_yet() -> None:
    text = r.render_dashboard()

    assert "GENERATED" in text
    assert "progress" in text
    assert "0" not in text.split("\n")[0]  # never a fabricated count
    # `progress` is a skill; there is no `progress dashboard` command. A shipped
    # file naming one sends the reader straight to a shell error.
    assert "progress dashboard" not in text


def test_rendered_rclone_example_carries_no_credentials() -> None:
    text = r.render_rclone_example()

    assert "[research-mirror]" in text
    for secret in ("key", "secret", "password", "token"):
        assert f"{secret} =" not in text.lower()


def test_gitignore_entries_track_the_configured_cache_dir() -> None:
    assert r.gitignore_entries(".cache/ds/") == [
        ".cache/ds/",
        ".defendable-science/rclone.conf",
        ".defendable-science/keys.json",
    ]


def test_merge_gitignore_appends_only_what_is_missing() -> None:
    existing = "# python\n__pycache__/\n.defendable-science/rclone.conf\n"

    merged = r.merge_gitignore(
        existing, r.gitignore_entries(".defendable-science/cache/")
    )

    assert merged.startswith(existing)
    assert merged.count(".defendable-science/rclone.conf") == 1
    assert ".defendable-science/cache/" in merged
    assert "__pycache__/" in merged


def test_merge_gitignore_is_a_noop_when_every_entry_is_present() -> None:
    entries = r.gitignore_entries(".defendable-science/cache/")
    existing = "\n".join(entries) + "\n"

    assert r.merge_gitignore(existing, entries) == existing


def test_merge_gitignore_handles_a_file_without_a_trailing_newline() -> None:
    merged = r.merge_gitignore("build/", [".defendable-science/keys.json"])

    assert merged == "build/\n\n# defendable-science\n.defendable-science/keys.json\n"


def test_merge_gitignore_from_empty() -> None:
    merged = r.merge_gitignore("", [".defendable-science/keys.json"])

    assert merged == "# defendable-science\n.defendable-science/keys.json\n"


def test_rendered_config_records_a_divergent_layout(tmp_path: Path) -> None:
    """The block it writes must be the block `resolve_layout` reads back (#133)."""
    path = tmp_path / "config.yml"
    path.write_text(
        r.render_config(
            layout_block={"research_root": "writing", "literature_dir": "my bib: 1"}
        ),
        encoding="utf-8",
    )

    config = load_config(path)

    assert config["layout"] == {
        "research_root": "writing",
        "literature_dir": "my bib: 1",
    }
    assert config["cache_dir"] == r.DEFAULT_CACHE_DIR


def test_a_recorded_layout_round_trips_through_the_resolver(tmp_path: Path) -> None:
    resolved = lay.layout_from_overrides(
        {"research_root": "writing", "literature_dir": "bib"}, tmp_path
    )
    path = tmp_path / "config.yml"
    path.write_text(
        r.render_config(layout_block=lay.recorded_layout(resolved)), encoding="utf-8"
    )

    assert lay.resolve_layout(load_config(path), tmp_path) == resolved


def test_an_empty_layout_block_renders_the_default_config() -> None:
    assert r.render_config(layout_block={}) == r.render_config()
