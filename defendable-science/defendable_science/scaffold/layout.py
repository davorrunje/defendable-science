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

from defendable_science.core.paths import require_path_segment

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

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

#: The one staged document per level that carries the *authoritative* verdict /
#: readiness / sign-off block. The others may carry their own lighter
#: ``understanding`` and ``last-updated`` (written by ``defend``), which
#: ``progress`` surfaces but never treats as the adjudication source.
#:
#: A thesis is adjudicated by ``kappa.md``: that is where the shipped template
#: marks ``signed-off-by`` *REQUIRED for defensibility*, and ``aims.md``'s own
#: template says the sign-off is not there. ``aims.md`` keeps a different job —
#: it owns the aim list each paper's ``covers:`` is matched against — so both
#: are read, for different reasons. Before a kappa exists the thesis is
#: legitimately framing-only and is projected from ``aims.md``
#: (``progress.collect``'s furthest-stage rule).
#:
#: Written out rather than derived from :data:`STAGED_DOCUMENTS`' order, which
#: it currently coincides with: which document adjudicates is a fact about the
#: methodology, not about a position in a list, and a new staged document
#: appended to a level must not silently become its verdict source.
AUTHORITATIVE_DOCUMENTS: dict[str, str] = {
    "hypothesis": "findings.md",
    "paper": "decision.md",
    "thesis": "kappa.md",
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
        """Return the digest artifact of `citekey`.

        :raises LayoutError: If `citekey` is not a single path segment — see
            :func:`~defendable_science.core.paths.require_path_segment`
            (defendable-science#182).
        """
        citekey = require_path_segment(citekey, what="citekey", error=LayoutError)
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
        """Return the root directory of `paper_id`.

        :raises LayoutError: If `paper_id` is not a single path segment — see
            :func:`~defendable_science.core.paths.require_path_segment`
            (defendable-science#182). Every other per-paper path derives from
            this one, so guarding it here covers them all.
        """
        paper_id = require_path_segment(paper_id, what="paper_id", error=LayoutError)
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
        """Return one hypothesis folder of `paper_id`.

        :raises LayoutError: If `paper_id` or `slug` is not a single path
            segment (defendable-science#182).
        """
        slug = require_path_segment(slug, what="slug", error=LayoutError)
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


@dataclass(frozen=True)
class LayoutConflict:
    """One key whose requested value contradicts the recorded one.

    :param key: The layout key, as it is written in ``config.yml``.
    :param recorded: The absolute path ``config.yml`` records for it.
    :param requested: The absolute path the caller asked for.
    """

    key: str
    recorded: Path
    requested: Path


def layout_from_overrides(
    overrides: Mapping[str, str | None], repo_root: Path
) -> Layout:
    """Resolve a layout from caller-supplied overrides (``init``'s options).

    A thin front door onto :func:`resolve_layout`, so an option gets **exactly**
    the validation a ``layout:`` block gets — relative, inside the repository, no
    ``..`` escape — rather than a second copy of the rule that could drift from
    it.

    :param overrides: Layout key → value; a ``None`` value means "not given" and
        falls back to the default, matching an omitted block key.
    :param repo_root: The repository root.
    :returns: The resolved layout.
    :raises LayoutError: On an unknown key or an invalid value, identically to a
        ``layout:`` block carrying the same value.
    """
    block = {key: value for key, value in overrides.items() if value is not None}
    return resolve_layout({"layout": block}, repo_root)


def recorded_layout(layout: Layout) -> dict[str, str]:
    """Return the ``layout:`` block that records `layout`, defaults omitted.

    ADR-0039's defaults-omitted rule, applied in the writing direction: a repo
    matching the default records nothing, and a key whose value is what the
    resolver would have derived anyway is left out. Derived defaults follow the
    **resolved** ``research_root``, so recording ``research_root: writing`` does
    not also write the ``writing/literature`` and ``writing/thesis`` it carries.

    :param layout: A resolved layout.
    :returns: Repo-relative POSIX paths, keyed in :data:`LAYOUT_KEYS` order —
        the inverse of :func:`resolve_layout`, so the block it returns resolves
        back to `layout`.
    """
    default = Layout.default(layout.repo_root)
    derived = {
        "research_root": default.research_root,
        "literature_dir": layout.research_root / "literature",
        "datasets_manifest": default.datasets_manifest,
        "thesis_dir": layout.research_root / "thesis",
    }
    return {
        key: layout.rel(getattr(layout, key)).as_posix()
        for key in LAYOUT_KEYS
        if getattr(layout, key) != derived[key]
    }


def layout_conflicts(
    recorded: Layout, requested: Layout, keys: Iterable[str]
) -> list[LayoutConflict]:
    """Report the `keys` on which `requested` contradicts `recorded`.

    Only the keys the caller actually asked for are compared: an option nobody
    passed cannot contradict anything.

    :param recorded: The layout ``config.yml`` resolves to.
    :param requested: The layout the caller's options resolve to.
    :param keys: The layout keys the caller supplied.
    :returns: One conflict per disagreeing key, in :data:`LAYOUT_KEYS` order;
        empty when every supplied key agrees.
    """
    asked = set(keys)
    return [
        LayoutConflict(
            key=key,
            recorded=getattr(recorded, key),
            requested=getattr(requested, key),
        )
        for key in LAYOUT_KEYS
        if key in asked and getattr(recorded, key) != getattr(requested, key)
    ]
