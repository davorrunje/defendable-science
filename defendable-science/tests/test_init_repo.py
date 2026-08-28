"""Scaffolding a repo: idempotent, non-destructive, and immediately usable."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from defendable_science.scaffold import render as r
from defendable_science.scaffold import status
from defendable_science.scaffold.init_repo import init_repo
from defendable_science.scaffold.layout import Layout

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Return a pristine repo root.

    Its own directory rather than ``tmp_path``, which the autouse fake-``HOME``
    fixture already populates — the dry-run tests assert that *nothing* was
    written, and that assertion has to be exact to be worth anything.
    """
    root = tmp_path / "repo"
    root.mkdir()
    return root


def _init(root: Path, *, thesis: bool = False, dry_run: bool = False) -> list[str]:
    actions = init_repo(Layout.default(root), thesis=thesis, dry_run=dry_run)
    return [f"{a.status}:{a.path.relative_to(root)}" for a in actions]


def test_init_creates_the_default_layout(repo: Path) -> None:
    statuses = _init(repo)

    assert "created:docs/research/papers.md" in statuses
    assert "created:docs/research/portfolio-backlog.md" in statuses
    assert "created:docs/research/dashboard.md" in statuses
    assert "created:docs/research/literature/references.json" in statuses
    assert "created:docs/research/literature/triage.yml" in statuses
    assert "created:datasets.yml" in statuses
    assert "created:.defendable-science/config.yml" in statuses
    assert "created:.defendable-science/rclone.conf.example" in statuses
    assert "merged:.gitignore" in statuses
    for path in (
        "docs/research/papers.md",
        "datasets.yml",
        ".defendable-science/config.yml",
        ".gitignore",
    ):
        assert (repo / path).is_file()


def test_init_omits_the_thesis_tree_by_default(repo: Path) -> None:
    _init(repo)

    assert not (repo / "docs" / "research" / "thesis").exists()


def test_init_thesis_creates_the_thesis_tree(repo: Path) -> None:
    statuses = _init(repo, thesis=True)

    assert "created:docs/research/thesis/aims.md" in statuses
    assert "created:docs/research/thesis/milestones.yml" in statuses
    assert "created:docs/research/thesis/kappa" in statuses
    assert (repo / "docs" / "research" / "thesis" / "kappa").is_dir()


def test_scaffolded_milestones_are_the_rendered_ones(repo: Path) -> None:
    """One artifact, one shape: `init` writes exactly what `render` defines."""
    _init(repo, thesis=True)

    milestones = repo / "docs" / "research" / "thesis" / "milestones.yml"

    assert milestones.read_text(encoding="utf-8") == r.render_milestones()


def test_scaffolded_aims_carry_the_templates_status_form(repo: Path) -> None:
    """A stub `progress` cannot read is a thesis that never reaches the dashboard."""
    _init(repo, thesis=True)

    text = (repo / "docs" / "research" / "thesis" / "aims.md").read_text(
        encoding="utf-8"
    )
    form = status.TEMPLATE_FORMS["thesis/aims.md"]
    expected = status.render(
        form["level"], {k: v for k, v in form.items() if k != "level"}
    )

    assert status.parse(text) == yaml.safe_load(expected)["status"]


def test_init_is_idempotent_and_byte_identical(repo: Path) -> None:
    _init(repo)
    before = {p: p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file()}

    second = _init(repo)

    after = {p: p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file()}
    assert after == before
    assert all(entry.startswith(("exists:", "merged:")) for entry in second)


def test_init_thesis_is_idempotent(repo: Path) -> None:
    """Including the kappa directory: a second run must not report it created."""
    _init(repo, thesis=True)

    second = _init(repo, thesis=True)

    assert "exists:docs/research/thesis/aims.md" in second
    assert "exists:docs/research/thesis/kappa" in second
    assert all(entry.startswith("exists:") for entry in second)


def test_init_never_overwrites_author_content(repo: Path) -> None:
    papers = repo / "docs" / "research" / "papers.md"
    papers.parent.mkdir(parents=True)
    papers.write_text("MY OWN REGISTRY\n", encoding="utf-8")

    statuses = _init(repo)

    assert "exists:docs/research/papers.md" in statuses
    assert papers.read_text(encoding="utf-8") == "MY OWN REGISTRY\n"


def test_init_gitignore_merge_preserves_existing_rules(repo: Path) -> None:
    (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")

    _init(repo)

    text = (repo / ".gitignore").read_text(encoding="utf-8")
    assert "__pycache__/" in text
    assert r.DEFAULT_CACHE_DIR in text


def test_init_reports_gitignore_as_exists_when_nothing_is_missing(repo: Path) -> None:
    entries = r.gitignore_entries(r.DEFAULT_CACHE_DIR)
    (repo / ".gitignore").write_text("\n".join(entries) + "\n", encoding="utf-8")

    statuses = _init(repo)

    assert "exists:.gitignore" in statuses


def test_dry_run_writes_nothing(repo: Path) -> None:
    statuses = _init(repo, dry_run=True)

    assert "created:docs/research/papers.md" in statuses
    assert list(repo.iterdir()) == []


def test_dry_run_reports_the_thesis_tree_without_creating_it(repo: Path) -> None:
    statuses = _init(repo, thesis=True, dry_run=True)

    assert "created:docs/research/thesis/aims.md" in statuses
    assert "created:docs/research/thesis/kappa" in statuses
    assert list(repo.iterdir()) == []


def test_dry_run_leaves_an_existing_gitignore_alone(repo: Path) -> None:
    """The report is the one a real run would give; the file is not touched."""
    (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")

    statuses = _init(repo, dry_run=True)

    assert "merged:.gitignore" in statuses
    assert (repo / ".gitignore").read_text(encoding="utf-8") == "__pycache__/\n"


def test_init_respects_a_non_default_layout(repo: Path) -> None:
    layout = Layout(
        repo_root=repo,
        research_root=repo / "writing",
        literature_dir=repo / "bib",
        datasets_manifest=repo / "data" / "datasets.yml",
        thesis_dir=repo / "phd",
    )

    init_repo(layout, thesis=True)

    assert (repo / "writing" / "papers.md").is_file()
    assert (repo / "bib" / "references.json").is_file()
    assert (repo / "data" / "datasets.yml").is_file()
    assert (repo / "phd" / "aims.md").is_file()


def test_init_uses_the_configured_cache_dir_for_the_gitignore_entry(
    repo: Path,
) -> None:
    init_repo(Layout.default(repo), cache_dir=".cache/ds/")

    assert ".cache/ds/" in (repo / ".gitignore").read_text(encoding="utf-8")
