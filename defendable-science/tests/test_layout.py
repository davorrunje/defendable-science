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
    assert out.digests_dir == Path("/repo/docs/research/literature/digests")
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
    assert out.positioning("depth-collapse") == Path(
        "/repo/docs/research/depth-collapse/paper/positioning.md"
    )


def test_a_digest_is_named_for_its_citekey_and_follows_the_literature_dir() -> None:
    out = lay.resolve_layout({"layout": {"literature_dir": "refs"}}, Path("/repo"))

    assert out.digests_dir == Path("/repo/refs/digests")
    assert out.digest("smith2024monotone") == Path(
        "/repo/refs/digests/smith2024monotone.md"
    )


def test_positioning_is_a_staged_paper_document() -> None:
    out = lay.Layout.default(Path("/repo"))

    assert lay.STAGED_DOCUMENTS[out.positioning("p1").name] == "paper"
    assert out.positioning("p1").parent == out.paper_docs_dir("p1")


# --- gap 5: identifier-taking paths reject a traversal attempt (#182) -------

_TRAVERSAL = "../../../../../../tmp/dsaudit/PWNED"


def test_digest_rejects_a_traversal_citekey() -> None:
    """A citekey is a single path segment, not a sub-path.

    Reproduces #182: `Layout.digest(_TRAVERSAL).resolve()` used to land at
    `/tmp/dsaudit/PWNED.md`, outside `repo_root` entirely.
    """
    out = lay.Layout.default(Path("/repo"))
    with pytest.raises(lay.LayoutError, match="citekey"):
        out.digest(_TRAVERSAL)


def test_paper_dir_rejects_a_traversal_paper_id() -> None:
    """`paper_dir` is the shared root of the four derived per-paper methods.

    Guarding it here covers backlog/hypotheses_dir/paper_docs_dir/positioning
    too, since they all call through it.
    """
    out = lay.Layout.default(Path("/repo"))
    with pytest.raises(lay.LayoutError, match="paper_id"):
        out.paper_dir(_TRAVERSAL)


@pytest.mark.parametrize(
    "method",
    ["backlog", "hypotheses_dir", "paper_docs_dir", "positioning"],
)
def test_paper_dir_derived_methods_reject_a_traversal_paper_id(method: str) -> None:
    out = lay.Layout.default(Path("/repo"))
    with pytest.raises(lay.LayoutError, match="paper_id"):
        getattr(out, method)(_TRAVERSAL)


def test_hypothesis_dir_rejects_a_traversal_paper_id_or_slug() -> None:
    out = lay.Layout.default(Path("/repo"))
    with pytest.raises(lay.LayoutError, match="paper_id"):
        out.hypothesis_dir(_TRAVERSAL, "a-real-slug")
    with pytest.raises(lay.LayoutError, match="slug"):
        out.hypothesis_dir("depth-collapse", _TRAVERSAL)


def test_paper_id_containing_a_plain_slash_is_rejected_too() -> None:
    """Not just `..` — any embedded separator would address a sub-path."""
    out = lay.Layout.default(Path("/repo"))
    with pytest.raises(lay.LayoutError, match="paper_id"):
        out.paper_dir("depth-collapse/../../etc")


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


# --- recording a layout back into config.yml (#133) ------------------------


def test_a_default_layout_records_nothing() -> None:
    """ADR-0039's defaults-omitted rule: a matching repo records no key."""
    assert lay.recorded_layout(lay.Layout.default(Path("/repo"))) == {}


def test_recording_omits_the_keys_that_derive_from_the_research_root() -> None:
    """`literature_dir` and `thesis_dir` follow a moved research root."""
    out = lay.layout_from_overrides({"research_root": "writing"}, Path("/repo"))

    assert lay.recorded_layout(out) == {"research_root": "writing"}


def test_recording_keeps_every_divergent_key() -> None:
    out = lay.layout_from_overrides(
        {
            "research_root": "writing/",
            "literature_dir": "bib/",
            "datasets_manifest": "data/datasets.yml",
            "thesis_dir": "phd/",
        },
        Path("/repo"),
    )

    assert lay.recorded_layout(out) == {
        "research_root": "writing",
        "literature_dir": "bib",
        "datasets_manifest": "data/datasets.yml",
        "thesis_dir": "phd",
    }


def test_overrides_reuse_the_containment_rule() -> None:
    with pytest.raises(lay.LayoutError) as excinfo:
        lay.layout_from_overrides({"literature_dir": "../bib"}, Path("/repo"))

    assert "layout.literature_dir" in str(excinfo.value)
    assert "stay inside the repository" in str(excinfo.value)


def test_overrides_of_nothing_are_the_default_layout() -> None:
    assert lay.layout_from_overrides({}, Path("/repo")) == lay.Layout.default(
        Path("/repo")
    )


def test_no_conflict_when_the_requested_keys_agree_with_the_recorded_ones() -> None:
    recorded = lay.resolve_layout(
        {"layout": {"research_root": "writing"}}, Path("/repo")
    )
    requested = lay.layout_from_overrides({"research_root": "writing/"}, Path("/repo"))

    assert lay.layout_conflicts(recorded, requested, ["research_root"]) == []


def test_a_conflict_names_the_key_and_both_values() -> None:
    recorded = lay.Layout.default(Path("/repo"))
    requested = lay.layout_from_overrides(
        {"research_root": "writing", "literature_dir": "bib"}, Path("/repo")
    )

    conflicts = lay.layout_conflicts(
        recorded, requested, ["research_root", "literature_dir"]
    )

    assert conflicts == [
        lay.LayoutConflict(
            key="research_root",
            recorded=Path("/repo/docs/research"),
            requested=Path("/repo/writing"),
        ),
        lay.LayoutConflict(
            key="literature_dir",
            recorded=Path("/repo/docs/research/literature"),
            requested=Path("/repo/bib"),
        ),
    ]


def test_only_the_named_keys_are_compared() -> None:
    """An option the author did not pass cannot conflict with anything."""
    recorded = lay.Layout.default(Path("/repo"))
    requested = lay.layout_from_overrides({"thesis_dir": "phd"}, Path("/repo"))

    assert lay.layout_conflicts(recorded, requested, ["research_root"]) == []


def test_every_authoritative_document_is_a_staged_document_of_its_level() -> None:
    """A typo here would silently make an artifact unprojectable."""
    assert {
        name: lay.STAGED_DOCUMENTS[name]
        for name in lay.AUTHORITATIVE_DOCUMENTS.values()
    } == {"findings.md": "hypothesis", "decision.md": "paper", "kappa.md": "thesis"}
    assert set(lay.AUTHORITATIVE_DOCUMENTS) == set(lay.STAGED_DOCUMENTS.values())


def test_the_thesis_is_adjudicated_where_the_templates_sign_it() -> None:
    """The shipped templates are the source of truth, not prose about them.

    `kappa.md` marks `signed-off-by` REQUIRED for defensibility and `aims.md`
    says the sign-off is not there — so the document `progress` reads the
    verdict block from is `kappa.md`. This guard exists because the constant
    once said `aims.md`, following a stale line in `progress/SKILL.md`.
    """
    templates = Path(__file__).resolve().parents[2] / "resources" / "templates"
    kappa = (templates / "thesis" / "kappa.md").read_text(encoding="utf-8")
    aims = (templates / "thesis" / "aims.md").read_text(encoding="utf-8")

    assert lay.AUTHORITATIVE_DOCUMENTS["thesis"] == "kappa.md"
    assert "REQUIRED for defensibility" in kappa
    assert "the defensibility sign-off lives in kappa.md, not here" in aims
