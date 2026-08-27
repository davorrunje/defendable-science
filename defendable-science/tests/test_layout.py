"""The single definition of the consumer tree (#122)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


def test_an_empty_config_resolves_to_the_default_layout() -> None:
    assert lay.resolve_layout({}, Path("/repo")) == lay.Layout.default(Path("/repo"))


def test_a_missing_layout_block_resolves_to_the_default_layout() -> None:
    config: dict[str, Any] = {"cache_dir": ".defendable-science/cache/"}
    assert lay.resolve_layout(config, Path("/repo")) == lay.Layout.default(
        Path("/repo")
    )


def test_research_root_override_carries_literature_and_thesis_with_it() -> None:
    out = lay.resolve_layout({"layout": {"research_root": "writing/"}}, Path("/repo"))

    assert out.research_root == Path("/repo/writing")
    assert out.literature_dir == Path("/repo/writing/literature")
    assert out.thesis_dir == Path("/repo/writing/thesis")
    assert out.papers_registry == Path("/repo/writing/papers.md")
    # anchored at the repo root, not under research_root
    assert out.datasets_manifest == Path("/repo/datasets.yml")


def test_each_key_can_be_overridden_independently() -> None:
    out = lay.resolve_layout(
        {
            "layout": {
                "research_root": "writing/",
                "literature_dir": "bib/",
                "datasets_manifest": "data/datasets.yml",
                "thesis_dir": "phd/",
            }
        },
        Path("/repo"),
    )

    assert out.research_root == Path("/repo/writing")
    assert out.literature_dir == Path("/repo/bib")
    assert out.datasets_manifest == Path("/repo/data/datasets.yml")
    assert out.thesis_dir == Path("/repo/phd")


def test_an_unknown_layout_key_is_an_error_that_lists_the_valid_keys() -> None:
    with pytest.raises(lay.LayoutError) as excinfo:
        lay.resolve_layout({"layout": {"papers_dir": "x/"}}, Path("/repo"))

    message = str(excinfo.value)
    assert "papers_dir" in message
    for key in lay.LAYOUT_KEYS:
        assert key in message


def test_a_non_mapping_layout_block_is_an_error() -> None:
    with pytest.raises(lay.LayoutError, match="must be a mapping"):
        lay.resolve_layout({"layout": ["writing/"]}, Path("/repo"))


@pytest.mark.parametrize(
    ("bad_value", "expected_type"), [(7, "int"), (["writing/"], "list")]
)
def test_a_non_string_layout_value_is_an_error(
    bad_value: Any, expected_type: str
) -> None:
    with pytest.raises(lay.LayoutError) as excinfo:
        lay.resolve_layout({"layout": {"research_root": bad_value}}, Path("/repo"))

    message = str(excinfo.value)
    assert "must be a string" in message
    assert expected_type in message


@pytest.mark.parametrize("bad", ["/etc/passwd", "../outside", "writing/../../outside"])
def test_a_path_escaping_the_repo_is_refused(bad: str) -> None:
    with pytest.raises(lay.LayoutError, match="must stay inside the repository"):
        lay.resolve_layout({"layout": {"research_root": bad}}, Path("/repo"))


def test_a_null_layout_value_falls_back_to_the_default() -> None:
    out = lay.resolve_layout({"layout": {"thesis_dir": None}}, Path("/repo"))
    assert out.thesis_dir == Path("/repo/docs/research/thesis")


def test_a_mixed_type_key_set_is_an_error_that_lists_valid_keys() -> None:
    with pytest.raises(lay.LayoutError) as excinfo:
        lay.resolve_layout({"layout": {1: "x", "papers_dir": "y"}}, Path("/repo"))

    message = str(excinfo.value)
    # Both offending keys should be mentioned
    assert "1" in message
    assert "papers_dir" in message
    # Valid keys should be listed
    for key in lay.LAYOUT_KEYS:
        assert key in message


def test_an_empty_string_layout_value_is_an_error() -> None:
    with pytest.raises(lay.LayoutError, match="must be a non-empty path"):
        lay.resolve_layout({"layout": {"research_root": ""}}, Path("/repo"))


def test_research_root_as_dot_resolves_to_the_repo_root() -> None:
    out = lay.resolve_layout({"layout": {"research_root": "."}}, Path("/repo"))

    assert out.research_root == Path("/repo")
    assert out.literature_dir == Path("/repo/literature")
    assert out.thesis_dir == Path("/repo/thesis")


def test_repo_root_with_dotdot_is_canonicalized() -> None:
    # repo_root contains ".." which needs canonicalization for rel() to work.
    out = lay.resolve_layout(
        {"layout": {"research_root": "writing/"}},
        Path("/repo/sub/.."),
    )

    # All paths should be under the canonical /repo
    assert out.repo_root == Path("/repo")
    assert out.research_root == Path("/repo/writing")
    # rel() should work on all fields, returning them as repo-relative
    assert out.rel(out.research_root) == Path("writing")
    assert out.rel(out.literature_dir) == Path("writing/literature")
    assert out.rel(out.datasets_manifest) == Path("datasets.yml")
    assert out.rel(out.thesis_dir) == Path("writing/thesis")
