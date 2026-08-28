"""Scaffold a consumer repo from the renderers (#120).

Idempotent and non-destructive: an existing file is reported and left alone,
never overwritten, so re-running fills gaps only (``research-init``'s guardrail).
``.gitignore`` is the one exception, and it is merged append-only.

Every status this reports is a fact about the filesystem, not an intention: a
file already present is ``exists``, never ``created``, and ``--dry-run`` produces
exactly the report a real run would while writing nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from defendable_science.core.gitignore import check_ignore
from defendable_science.scaffold import render as r
from defendable_science.scaffold import status
from defendable_science.scaffold.layout import recorded_layout

if TYPE_CHECKING:
    from pathlib import Path

    from defendable_science.scaffold.layout import Layout

#: The tracked stub of ``resources/templates/thesis/aims.md``. Only the status
#: frontmatter and the template's comment prompts — the shipped template stays
#: the fuller authoring skeleton, and seeding prose the author did not write
#: would cut against the agency principle (meta-spec §2.1). The block is
#: interpolated from :func:`defendable_science.scaffold.status.render`, so it
#: cannot drift from what ``progress`` projects.
_AIMS_TEMPLATE = """\
---
{status}---

# Thesis aims & narrative

## Aims

<!-- The overarching questions this thesis answers. Keep the set small. Each aim
     takes a stable id (aim-1, aim-2, …) that papers' `covers` field points at. -->

## Narrative through-line

<!-- The one-paragraph story that unifies the aims — why these questions form a
     single coherent program, and what the original contribution is. -->

## Chapter ↔ paper map

<!-- Which registered papers compose the thesis, and which aim(s) each supports.
     Coverage — not paper count — is the binding norm; an uncovered aim is a
     surfaced gap for `progress` to report, not a score. -->
"""

_AIMS_STUB = _AIMS_TEMPLATE.format(
    status=status.render("thesis", {"readiness": "framing"})
)


@dataclass(frozen=True)
class Action:
    """One path ``init`` considered — a file, or the kappa directory.

    :param path: The absolute path.
    :param status: ``created`` (written), ``exists`` (left alone), or ``merged``
        (append-only edit). Never ``overwritten``.
    """

    path: Path
    status: str


def _write(path: Path, text: str, actions: list[Action], *, dry_run: bool) -> None:
    """Create `path` with `text` unless it exists; record the action."""
    if path.exists():
        actions.append(Action(path=path, status="exists"))
        return
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    actions.append(Action(path=path, status="created"))


def _mkdir(path: Path, actions: list[Action], *, dry_run: bool) -> None:
    """Create directory `path` unless it exists; record the action."""
    if path.exists():
        actions.append(Action(path=path, status="exists"))
        return
    if not dry_run:
        path.mkdir(parents=True)
    actions.append(Action(path=path, status="created"))


def _merge_gitignore(
    layout: Layout, cache_dir: str, actions: list[Action], *, dry_run: bool
) -> None:
    """Append any missing ignore entries to ``.gitignore``.

    An entry already covered by git — under any spelling, not just a literal
    line — is not appended again (#139). ``check_ignore`` needs a real work
    tree; when `layout.repo_root` is not one (``init`` may run before
    ``git init``), it answers ``None`` for every entry, which degrades to
    exactly the pre-#139 literal-membership behaviour: append if not
    literally present. That must never error or silently skip the merge.
    """
    path = layout.repo_root / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    already_covered = [
        entry
        for entry in r.gitignore_entries(cache_dir)
        if check_ignore(layout.repo_root, entry) is True
    ]
    merged = r.merge_gitignore(
        existing, r.gitignore_entries(cache_dir), already_covered=already_covered
    )
    if merged == existing:
        actions.append(Action(path=path, status="exists"))
        return
    if not dry_run:
        path.write_text(merged, encoding="utf-8")
    actions.append(Action(path=path, status="merged"))


def init_repo(
    layout: Layout,
    *,
    thesis: bool = False,
    dry_run: bool = False,
    cache_dir: str = r.DEFAULT_CACHE_DIR,
) -> list[Action]:
    """Scaffold the consumer layout under `layout`.

    :param layout: The resolved layout to scaffold into.
    :param thesis: Also scaffold the optional thesis tree.
    :param dry_run: Report what would happen without writing anything.
    :param cache_dir: The cache root to record in config and gitignore.
    :returns: One action per file considered, in a stable order.
    """
    actions: list[Action] = []
    _write(layout.papers_registry, r.render_papers_registry(), actions, dry_run=dry_run)
    _write(
        layout.portfolio_backlog, r.render_portfolio_backlog(), actions, dry_run=dry_run
    )
    _write(layout.dashboard, r.render_dashboard(), actions, dry_run=dry_run)
    _write(layout.references, r.render_references(), actions, dry_run=dry_run)
    _write(layout.triage, r.render_triage(), actions, dry_run=dry_run)
    _write(
        layout.datasets_manifest, r.render_datasets_manifest(), actions, dry_run=dry_run
    )
    # The config records the layout it was scaffolded into, so a divergent tree
    # is written *and* recorded by one run — never a tree the next command
    # cannot find (defendable-science#133).
    _write(
        layout.config_file,
        r.render_config(cache_dir, recorded_layout(layout)),
        actions,
        dry_run=dry_run,
    )
    _write(
        layout.config_dir / "rclone.conf.example",
        r.render_rclone_example(),
        actions,
        dry_run=dry_run,
    )
    if thesis:
        _write(layout.aims, _AIMS_STUB, actions, dry_run=dry_run)
        _write(layout.milestones, r.render_milestones(), actions, dry_run=dry_run)
        _mkdir(layout.kappa_dir, actions, dry_run=dry_run)
    _merge_gitignore(layout, cache_dir, actions, dry_run=dry_run)
    return actions
