"""The single definition of the consumer tree (#122)."""

from __future__ import annotations

from pathlib import Path

import pytest

from defendable_science.scaffold import layout as lay


def test_default_layout_derives_every_path_from_the_repo_root() -> None:
    out = lay.Layout.default(Path("/repo"))

    assert out.research_root == Path("/repo/docs/research")
    assert out.papers_registry == Path("/repo/docs/research/papers.md")
    assert out.portfolio_backlog == Path("/repo/docs/research/portfolio-backlog.md")
    assert out.dashboard == Path("/repo/docs/research/dashboard.md")
    assert out.literature_dir == Path("/repo/docs/research/literature")
    assert out.references == Path("/repo/docs/research/literature/references.json")
    assert out.triage == Path("/repo/docs/research/literature/triage.yml")
    assert out.datasets_manifest == Path("/repo/datasets.yml")
    assert out.thesis_dir == Path("/repo/docs/research/thesis")
    assert out.aims == Path("/repo/docs/research/thesis/aims.md")
    assert out.milestones == Path("/repo/docs/research/thesis/milestones.yml")
    assert out.kappa_dir == Path("/repo/docs/research/thesis/kappa")
    assert out.config_file == Path("/repo/.defendable-science/config.yml")


def test_paper_paths_are_derived_from_the_paper_id() -> None:
    out = lay.Layout.default(Path("/repo"))

    assert out.paper_dir("depth-collapse") == Path("/repo/docs/research/depth-collapse")
    assert out.backlog("depth-collapse") == Path(
        "/repo/docs/research/depth-collapse/backlog.md"
    )
    assert out.hypotheses_dir("depth-collapse") == Path(
        "/repo/docs/research/depth-collapse/hypotheses"
    )
    assert out.paper_docs_dir("depth-collapse") == Path(
        "/repo/docs/research/depth-collapse/paper"
    )
    assert out.hypothesis_dir("depth-collapse", "2026-03-04-monotone") == Path(
        "/repo/docs/research/depth-collapse/hypotheses/2026-03-04-monotone"
    )


def test_rel_renders_a_path_for_display_and_tolerates_an_outside_path() -> None:
    out = lay.Layout.default(Path("/repo"))

    assert out.rel(out.papers_registry) == Path("docs/research/papers.md")
    assert out.rel(Path("/elsewhere/x.md")) == Path("/elsewhere/x.md")


def test_layout_is_frozen() -> None:
    out = lay.Layout.default(Path("/repo"))
    with pytest.raises(AttributeError):
        out.research_root = Path("/other")  # type: ignore[misc]


def test_staged_documents_maps_each_known_filename_to_its_level() -> None:
    assert lay.STAGED_DOCUMENTS == {
        "hypothesis.md": "hypothesis",
        "strategy.md": "hypothesis",
        "findings.md": "hypothesis",
        "pitch.md": "paper",
        "positioning.md": "paper",
        "ledger.md": "paper",
        "decision.md": "paper",
        "aims.md": "thesis",
        "kappa.md": "thesis",
    }
