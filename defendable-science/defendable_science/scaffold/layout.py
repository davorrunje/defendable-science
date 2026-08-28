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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

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

    @property
    def digests_dir(self) -> Path:
        """The directory holding one ``digest`` artifact per read paper."""
        return self.literature_dir / "digests"

    def digest(self, citekey: str) -> Path:
        """Return the digest artifact of `citekey`."""
        return self.digests_dir / f"{citekey}.md"

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

    def positioning(self, paper_id: str) -> Path:
        """Return the positioning document of `paper_id`."""
        return self.paper_docs_dir(paper_id) / "positioning.md"

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


def _relative(key: str, raw: object, default: Path, repo_root: Path) -> Path:
    """Resolve one ``layout:`` value into an absolute path under `repo_root`.

    :param key: The layout key, for error messages.
    :param raw: The configured value; ``None`` means "use the default".
    :param default: The absolute default for this key.
    :param repo_root: The repository root (must be canonical).
    :returns: The absolute resolved path.
    :raises LayoutError: If `raw` is not a non-empty string, or points outside
        the repo. A key pointing outside the work tree would let ``init`` and
        ``check`` read and write beyond the repository, which an integrity tool
        must not do.
    """
    if raw is None:
        return default
    if not isinstance(raw, str):
        msg = f"layout.{key} must be a string, got {type(raw).__name__}"
        raise LayoutError(msg)
    if not raw:
        msg = f"layout.{key} must be a non-empty path"
        raise LayoutError(msg)
    candidate = Path(raw)
    if candidate.is_absolute():
        msg = f"layout.{key} must stay inside the repository: {raw!r} is absolute"
        raise LayoutError(msg)
    resolved = (repo_root / candidate).resolve()
    if resolved != repo_root and repo_root not in resolved.parents:
        msg = f"layout.{key} must stay inside the repository: {raw!r} escapes it"
        raise LayoutError(msg)
    return resolved


def resolve_layout(config: Mapping[str, Any], repo_root: Path) -> Layout:
    """Resolve the layout from a ``config.yml`` mapping.

    Resolution order is the ``layout:`` block, then the packaged default. A repo
    matching the default records nothing. Unknown keys are an error rather than a
    silent ignore: a typo that quietly did nothing would leave the author
    believing a divergent layout was recorded.

    :param config: The parsed ``config.yml`` mapping.
    :param repo_root: The repository root.
    :returns: The resolved layout.
    :raises LayoutError: On a non-mapping block, an unknown key, a non-string
        value, or a path that escapes the repository.
    """
    repo_root = repo_root.resolve()
    default = Layout.default(repo_root)
    raw = config.get("layout")
    if raw is None:
        return default
    # Check for dict only (not Mapping), which is deliberate: config always
    # arrives from yaml.safe_load(), which produces dict, not a Mapping subclass.
    if not isinstance(raw, dict):
        msg = f"layout: must be a mapping of {list(LAYOUT_KEYS)}"
        raise LayoutError(msg)
    unknown = sorted(str(k) for k in raw if k not in LAYOUT_KEYS)
    if unknown:
        msg = f"unknown layout key(s) {unknown}; valid keys are {list(LAYOUT_KEYS)}"
        raise LayoutError(msg)

    research = _relative(
        "research_root", raw.get("research_root"), default.research_root, repo_root
    )
    return Layout(
        repo_root=repo_root,
        research_root=research,
        literature_dir=_relative(
            "literature_dir",
            raw.get("literature_dir"),
            research / "literature",
            repo_root,
        ),
        datasets_manifest=_relative(
            "datasets_manifest",
            raw.get("datasets_manifest"),
            default.datasets_manifest,
            repo_root,
        ),
        thesis_dir=_relative(
            "thesis_dir", raw.get("thesis_dir"), research / "thesis", repo_root
        ),
    )
