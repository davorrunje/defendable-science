"""The single definition of the consumer content layout (#122, ADR-0039).

Every path a ``defendable-science`` command reads or writes is derived here.
Four roots are recordable in ``.defendable-science/config.yml``; everything
inside a paper is derived, so ``progress``, ``check`` and the skills always know
where a paper's parts are. Pure: no filesystem access, so thesis-ness is a fact
the caller probes, never something this module decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: The four keys ``config.yml``'s ``layout:`` block accepts.
LAYOUT_KEYS: tuple[str, ...] = (
    "research_root",
    "literature_dir",
    "datasets_manifest",
    "thesis_dir",
)

#: Fixed, deliberately: it holds ``config.yml`` itself, so it cannot be
#: relocated by ``config.yml``.
CONFIG_DIR = Path(".defendable-science")

DEFAULT_RESEARCH_ROOT = Path("docs/research")
DEFAULT_DATASETS_MANIFEST = Path("datasets.yml")

#: Staged-document filenames that must carry a status block, and their level.
#: One list, read by ``init``, ``check`` and the template drift guard.
STAGED_DOCUMENTS: dict[str, str] = {
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


class LayoutError(ValueError):
    """Raised on an invalid ``layout:`` block."""


@dataclass(frozen=True)
class Layout:
    """The resolved consumer layout, as absolute paths.

    :param repo_root: The repository root every other field is joined onto.
    :param research_root: Holds ``papers.md``, the portfolio backlog, the
        dashboard, and one directory per paper.
    :param literature_dir: Holds ``references.json`` and ``triage.yml``.
    :param datasets_manifest: The dataset registry (repo-level).
    :param thesis_dir: Where a thesis tree lives if this repo has one.
    """

    repo_root: Path
    research_root: Path
    literature_dir: Path
    datasets_manifest: Path
    thesis_dir: Path

    @classmethod
    def default(cls, repo_root: Path) -> Layout:
        """Build the packaged default layout under `repo_root`.

        :param repo_root: The repository root.
        :returns: The default layout.
        """
        research = repo_root / DEFAULT_RESEARCH_ROOT
        return cls(
            repo_root=repo_root,
            research_root=research,
            literature_dir=research / "literature",
            datasets_manifest=repo_root / DEFAULT_DATASETS_MANIFEST,
            thesis_dir=research / "thesis",
        )

    # --- research-root artifacts ---

    @property
    def papers_registry(self) -> Path:
        """The ``papers.md`` registry."""
        return self.research_root / "papers.md"

    @property
    def portfolio_backlog(self) -> Path:
        """The paper-level backlog."""
        return self.research_root / "portfolio-backlog.md"

    @property
    def dashboard(self) -> Path:
        """The generated dashboard projection."""
        return self.research_root / "dashboard.md"

    # --- literature ---

    @property
    def references(self) -> Path:
        """The CSL-JSON bibliography."""
        return self.literature_dir / "references.json"

    @property
    def triage(self) -> Path:
        """The triage decision sidecar."""
        return self.literature_dir / "triage.yml"

    # --- config ---

    @property
    def config_dir(self) -> Path:
        """The fixed ``.defendable-science/`` directory."""
        return self.repo_root / CONFIG_DIR

    @property
    def config_file(self) -> Path:
        """The project config file."""
        return self.config_dir / "config.yml"

    # --- thesis ---

    @property
    def aims(self) -> Path:
        """The thesis aims document."""
        return self.thesis_dir / "aims.md"

    @property
    def milestones(self) -> Path:
        """The configurable program gates."""
        return self.thesis_dir / "milestones.yml"

    @property
    def kappa_dir(self) -> Path:
        """The framing-chapter directory."""
        return self.thesis_dir / "kappa"

    # --- per-paper (derived, never configurable) ---

    def paper_dir(self, paper_id: str) -> Path:
        """Return the root directory of `paper_id`."""
        return self.research_root / paper_id

    def backlog(self, paper_id: str) -> Path:
        """Return the hypothesis backlog of `paper_id`."""
        return self.paper_dir(paper_id) / "backlog.md"

    def hypotheses_dir(self, paper_id: str) -> Path:
        """Return the hypotheses directory of `paper_id`."""
        return self.paper_dir(paper_id) / "hypotheses"

    def paper_docs_dir(self, paper_id: str) -> Path:
        """Return the staged-document directory of `paper_id`."""
        return self.paper_dir(paper_id) / "paper"

    def hypothesis_dir(self, paper_id: str, slug: str) -> Path:
        """Return one hypothesis folder of `paper_id`."""
        return self.hypotheses_dir(paper_id) / slug

    def rel(self, path: Path) -> Path:
        """Render `path` relative to the repo root for display.

        :param path: The path to render.
        :returns: The repo-relative path, or `path` unchanged when it lies
            outside the repo (a finding must never hide where a file really is).
        """
        try:
            return path.relative_to(self.repo_root)
        except ValueError:
            return path
