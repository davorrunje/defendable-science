# Scaffold / Check / Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a `defendable-science` repo scaffolded from one authoritative source and verifiable by one command, so a fresh `init` is never dead on arrival and a broken repo is never silently broken.

**Architecture:** The package gains two pure sub-packages — `scaffold/` (a single `Layout` definition, a single status-frontmatter renderer, and renderers for every machine-read file) and `check/` (a checker kernel over an injected filesystem `Probe`). Two new top-level CLI commands, `init` and `check`, are thin adapters over them. The plugin's skills stop typing files from prose and shell out instead; `resources/templates/` keeps only the human-authored prose skeletons.

**Tech Stack:** Python 3.11+, Typer, PyYAML, stdlib `dataclasses`. No new dependencies. Pytest + `pytest-cov` with a 100% statement+branch gate. Plugin side is pure markdown.

**Spec:** `docs/superpowers/specs/2026-08-27-scaffold-check-layout-design.md` — read it before Task 1; every task argues from it.

## Global Constraints

- **Never commit to `main`.** Each PR gets its own branch off `main`, opened with the `create-pr` skill. PRs land in order: PR1 → PR2 → PR3 → PR4.
- **Package work runs from the `defendable-science/` subdirectory.** `cd defendable-science` first; `uv run pytest -q`, `uv run mypy`, `uv run ruff check`, `uv run ruff format`.
- **100% statement+branch coverage is a hard gate** (`fail_under = 100`, ADR-0028). Every error and degradation branch needs a test. `# pragma: no cover` only for genuinely unreachable code, with a stated reason.
- **No Pydantic.** Deliberately rejected; use stdlib `dataclasses`. No new runtime dependencies at all in this work.
- **MyST field-list docstrings** on every public function/class: `:param:` / `:returns:` / `:raises:`. Types come from annotations, never repeated in the docstring. Line length 88. Strict mypy.
- **Failure honesty** (`CLAUDE.md`): never let a failure or uncertain condition report as a legitimate empty/negative/complete result; never surface a raw traceback. "Failed to read" must be distinguishable from "valid and empty".
- **Domain neutrality:** no ML-, monotonic-network- or consumer-specific assumptions anywhere in the plugin or package.
- **Absence means "not yet set," never zero.** Every machine-read field is `null` / `[]` when unset — **never** an unreplaced `<...>` placeholder string. This is the invariant the whole milestone enforces.
- **A `refuted` hypothesis or a `no-go` paper is successful science.** Nothing in `check` may report either as a failure, a warning, or a gap.
- **Exit codes:** `0` clean or gaps-only, `1` any `invalid` or `unreadable` finding, `2` CLI usage error (Typer default).
- **Every material design decision gets a MADR ADR** in `decisions/`, appended to `decisions/README.md`.
- **Commits** are authored `Davor Runje <davor@synthpop.ai>` with a `Co-Authored-By: Claude …` trailer.

## Decisions this plan locks in

Discovered while gathering signatures; each is a real choice, recorded here so no
task re-litigates it:

1. **`Layout` stores absolute paths.** `repo_root` joined into every field, with a
   `rel(path)` helper for display in findings. Mixing absolute and
   repo-relative paths in one dataclass is the bug this avoids.
2. **The literature paths get an explicit precedence.** `cli.py:389-390` hard-code
   `docs/research/literature/{references.json,triage.yml}` and
   `config.yml literature.registry` / `literature.triage` already override them.
   Precedence becomes: `literature.registry` (explicit) → `layout.literature_dir /
   "references.json"` → packaged default. `check` reads through the same resolver
   so it validates the file the CLI actually uses.
3. **The experiment-backend config key is `experiment_backend:`.** It is currently
   named nowhere — only `engineering_backend:` is documented (meta-spec § 5,
   `resources/contracts/engineering.md`). `init` must write some key, so it writes
   the snake_case sibling, and the docs are updated to name it.
4. **All nine templates move their unset machine-read fields to `null`**, with the
   enum guidance moved into the trailing comment. This is the placeholder rule
   applied consistently, not just to `kappa.md`'s `readiness`. Comments are
   stripped before comparison, so guidance is preserved for the human reader.
5. **The two embedded Python literals stop containing a status block.**
   `_HYPOTHESIS_TEMPLATE` / `_PAPER_TEMPLATE` interpolate `status.render(...)`, so
   drift on the code path becomes structurally impossible and the test guards only
   the shipped templates.
6. **`Layout` has no `is_thesis_repo()`.** It is pure and does no I/O; thesis-ness
   is decided by `check`/`init` through the `Probe`.

## File Structure

**Created (package):**

| Path | Responsibility |
|---|---|
| `defendable_science/scaffold/__init__.py` | Re-export `Layout`, `resolve_layout`, `LayoutError`. |
| `defendable_science/scaffold/layout.py` | The ONE definition of the consumer tree: defaults, the four recordable keys, derived accessors, `STAGED_DOCUMENTS`, `resolve_layout`. |
| `defendable_science/scaffold/status.py` | The ONE definition of the status frontmatter: field order, per-level enums, per-level defaults, `TEMPLATE_FORMS`, `render`, `parse`. |
| `defendable_science/scaffold/render.py` | One pure renderer per machine-read file `init` writes. |
| `defendable_science/scaffold/init_repo.py` | The writer: `Layout` + options → `list[Action]`; idempotence and the `.gitignore` merge. |
| `defendable_science/check/__init__.py` | Re-export `run_checks`, `Report`, `Finding`. |
| `defendable_science/check/model.py` | `Severity`, `Finding`, `Report` (counts, `ok`, `exit_code`, `to_json`). |
| `defendable_science/check/probe.py` | `Probe` protocol + `FsProbe`; the only filesystem seam. |
| `defendable_science/check/checks.py` | The six check families, each a pure function, plus `run_checks`. |

**Modified (package):**

| Path | Change |
|---|---|
| `defendable_science/core/config.py` | Add `find_repo_root`. `load_config` signature unchanged. |
| `defendable_science/exploration/backlog.py` | Add `registry_dumps`; route `_registry_root` / `scaffold_paper` / `scaffold_hypothesis` through `Layout`; the two literals interpolate `status.render`. |
| `defendable_science/literature/registry.py` | Promote `_triage_mapping` to public `triage_mapping`. |
| `defendable_science/cli.py` | Add `init` and `check` commands and `_layout_or_exit`; make `--backlog` / `--paper-root` / `--research-root` layout-defaulted; route `_DEFAULT_REGISTRY_PATH` / `_DEFAULT_TRIAGE_PATH` through the resolver. |

**Created (tests):** `tests/test_layout.py`, `tests/test_status.py`, `tests/test_render.py`, `tests/test_init_repo.py`, `tests/test_check.py`, `tests/test_check_cli.py`, `tests/test_plugin_content.py`.

**Modified (plugin):** `resources/templates/**` (nine status blocks), `resources/templates/README.md`, `resources/ensure-tooling.md`, all eight `skills/*/SKILL.md`, `docs/design/00-meta-spec.md`, `docs/design/01-lifecycle.md`, `decisions/0039-*.md`, `decisions/README.md`.

**`file:line` anchors an implementer will need** (verified against `origin/main` at `8fc328b`):

- `exploration/backlog.py:24` `HYPOTHESIS_COLUMNS`, `:36` `PAPER_COLUMNS`, `:48` `REGISTRY_COLUMNS`, `:63` `columns_for`, `:234` `_splice`, `:297` `Backlog.loads`, `:331` `dumps`, `:493` `_HYPOTHESIS_TEMPLATE`, `:539` `_PAPER_TEMPLATE`, `:584` `scaffold_hypothesis`, `:623` `append_papers_registry`, `:666` `_registry_root`, `:675` `scaffold_paper`
- `cli.py:104` `doctor`, `:129` `_load_config_or_exit`, `:145` `_cache_root`, `:389` `_DEFAULT_REGISTRY_PATH`, `:427` `_lit_registry_paths`, `:855` `dataset validate`, `:1249` `_open_backlog`, `:1267` `park`, `:1379` `_check_scaffold_opts`, `:1404` `_scaffold_promoted`, `:1454` `promote`
- `tests/test_backlog.py:833` `_REPO_ROOT`, `:852` the drift guard being generalized

---

# PR1 — Layout resolver, status renderer, ADR (closes #122)

Branch: `feat/layout-resolver`

### Task 1: The `Layout` dataclass and the default tree

**Files:**
- Create: `defendable-science/defendable_science/scaffold/__init__.py`
- Create: `defendable-science/defendable_science/scaffold/layout.py`
- Test: `defendable-science/tests/test_layout.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `LayoutError(ValueError)`; `LAYOUT_KEYS: tuple[str, ...]`; `CONFIG_DIR: Path`; `STAGED_DOCUMENTS: dict[str, str]`; `Layout` frozen dataclass with fields `repo_root, research_root, literature_dir, datasets_manifest, thesis_dir` (all absolute `Path`), properties `papers_registry, portfolio_backlog, dashboard, references, triage, config_dir, config_file, aims, milestones, kappa_dir`, methods `paper_dir(paper_id) -> Path`, `backlog(paper_id) -> Path`, `hypotheses_dir(paper_id) -> Path`, `paper_docs_dir(paper_id) -> Path`, `hypothesis_dir(paper_id, slug) -> Path`, `rel(path) -> Path`, and classmethod `default(repo_root) -> Layout`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_layout.py
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd defendable-science && uv run pytest tests/test_layout.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'defendable_science.scaffold'`

- [ ] **Step 3: Write the minimal implementation**

```python
# defendable_science/scaffold/layout.py
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
LAYOUT_KEYS = ("research_root", "literature_dir", "datasets_manifest", "thesis_dir")

#: Fixed, deliberately: it holds ``config.yml`` itself, so it cannot be
#: relocated by ``config.yml``.
CONFIG_DIR = Path(".defendable-science")

DEFAULT_RESEARCH_ROOT = Path("docs/research")
DEFAULT_DATASETS_MANIFEST = Path("datasets.yml")

#: Staged-document filenames that must carry a status block, and their level.
#: One list, read by ``init``, ``check`` and the template drift guard.
STAGED_DOCUMENTS = {
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
```

```python
# defendable_science/scaffold/__init__.py
"""Scaffolding kernels: the layout, the status block, and the file renderers."""

from __future__ import annotations

from defendable_science.scaffold.layout import (
    LAYOUT_KEYS,
    STAGED_DOCUMENTS,
    Layout,
    LayoutError,
)

__all__ = ["LAYOUT_KEYS", "STAGED_DOCUMENTS", "Layout", "LayoutError"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd defendable-science && uv run pytest tests/test_layout.py -v && uv run mypy && uv run ruff check`
Expected: PASS, no mypy or ruff errors.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/scaffold/ tests/test_layout.py
git commit -m "feat(scaffold): define the consumer layout in one place"
```

### Task 2: `resolve_layout` and its validation branches

**Files:**
- Modify: `defendable-science/defendable_science/scaffold/layout.py`
- Test: `defendable-science/tests/test_layout.py`

**Interfaces:**
- Consumes: `Layout`, `LayoutError`, `LAYOUT_KEYS` from Task 1.
- Produces: `resolve_layout(config: Mapping[str, Any], repo_root: Path) -> Layout`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_layout.py
from typing import Any


def test_an_empty_config_resolves_to_the_default_layout() -> None:
    assert lay.resolve_layout({}, Path("/repo")) == lay.Layout.default(Path("/repo"))


def test_a_missing_layout_block_resolves_to_the_default_layout() -> None:
    config: dict[str, Any] = {"cache_dir": ".defendable-science/cache/"}
    assert lay.resolve_layout(config, Path("/repo")) == lay.Layout.default(Path("/repo"))


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


def test_a_non_string_layout_value_is_an_error() -> None:
    with pytest.raises(lay.LayoutError, match="must be a string"):
        lay.resolve_layout({"layout": {"research_root": 7}}, Path("/repo"))


@pytest.mark.parametrize("bad", ["/etc/passwd", "../outside", "writing/../../outside"])
def test_a_path_escaping_the_repo_is_refused(bad: str) -> None:
    with pytest.raises(lay.LayoutError, match="must stay inside the repository"):
        lay.resolve_layout({"layout": {"research_root": bad}}, Path("/repo"))


def test_a_null_layout_value_falls_back_to_the_default() -> None:
    out = lay.resolve_layout({"layout": {"thesis_dir": None}}, Path("/repo"))
    assert out.thesis_dir == Path("/repo/docs/research/thesis")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_layout.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'resolve_layout'`

- [ ] **Step 3: Write the minimal implementation**

Add to `layout.py` (imports: `from collections.abc import Mapping`, `from typing import Any`):

```python
def _relative(key: str, raw: object, default: Path, repo_root: Path) -> Path:
    """Resolve one ``layout:`` value into an absolute path under `repo_root`.

    :param key: The layout key, for error messages.
    :param raw: The configured value; ``None`` means "use the default".
    :param default: The absolute default for this key.
    :param repo_root: The repository root.
    :returns: The absolute resolved path.
    :raises LayoutError: If `raw` is not a string, or points outside the repo.
        A key pointing outside the work tree would let ``init`` and ``check``
        read and write beyond the repository, which an integrity tool must not do.
    """
    if raw is None:
        return default
    if not isinstance(raw, str):
        msg = f"layout.{key} must be a string, got {type(raw).__name__}"
        raise LayoutError(msg)
    candidate = Path(raw)
    if candidate.is_absolute():
        msg = f"layout.{key} must stay inside the repository: {raw!r} is absolute"
        raise LayoutError(msg)
    resolved = (repo_root / candidate).resolve()
    root = repo_root.resolve()
    if resolved != root and root not in resolved.parents:
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
    default = Layout.default(repo_root)
    raw = config.get("layout")
    if raw is None:
        return default
    if not isinstance(raw, dict):
        msg = f"layout: must be a mapping of {list(LAYOUT_KEYS)}"
        raise LayoutError(msg)
    unknown = sorted(k for k in raw if k not in LAYOUT_KEYS)
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
            "literature_dir", raw.get("literature_dir"), research / "literature",
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
```

Note the ordering that makes `test_research_root_override_carries_literature_and_thesis_with_it` pass: `literature_dir` and `thesis_dir` default off the *resolved* `research`, not off `default`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd defendable-science && uv run pytest tests/test_layout.py -v --cov=defendable_science.scaffold.layout --cov-report=term-missing --no-cov-on-fail`
Expected: PASS, and `layout.py` at 100% statement + branch coverage.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/scaffold/layout.py tests/test_layout.py
git commit -m "feat(scaffold): resolve the layout from config.yml, defaults omitted"
```

### Task 3: `find_repo_root`

**Files:**
- Modify: `defendable-science/defendable_science/core/config.py`
- Test: `defendable-science/tests/test_config.py`

**Interfaces:**
- Consumes: `CONFIG_DIR` from `scaffold.layout`.
- Produces: `find_repo_root(start: Path | None = None) -> Path`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_config.py
from defendable_science.core.config import find_repo_root


def test_find_repo_root_walks_up_to_the_config_dir(tmp_path: Path) -> None:
    (tmp_path / ".defendable-science").mkdir()
    nested = tmp_path / "docs" / "research" / "depth-collapse"
    nested.mkdir(parents=True)

    assert find_repo_root(nested) == tmp_path.resolve()


def test_find_repo_root_returns_the_start_when_there_is_no_config_dir(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    assert find_repo_root(nested) == nested.resolve()


def test_find_repo_root_defaults_to_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".defendable-science").mkdir()
    monkeypatch.chdir(tmp_path)

    assert find_repo_root() == tmp_path.resolve()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_config.py -k repo_root -v`
Expected: FAIL — `ImportError: cannot import name 'find_repo_root'`

- [ ] **Step 3: Write the minimal implementation**

```python
# defendable_science/core/config.py
def find_repo_root(start: Path | None = None) -> Path:
    """Find the repository root by walking up for ``.defendable-science/``.

    Layout paths are repo-root-relative, so a command run from a subdirectory
    must still resolve against the repository rather than against the cwd.

    :param start: Where to start; the current directory when omitted.
    :returns: The first ancestor containing ``.defendable-science/``, or the
        resolved `start` when none does (an un-onboarded directory is not an
        error — ``init`` is exactly the command you run there).
    """
    from defendable_science.scaffold.layout import CONFIG_DIR

    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / CONFIG_DIR).is_dir():
            return candidate
    return here
```

The import is function-local to keep `core` free of an import-time dependency on `scaffold` (`scaffold.layout` imports nothing from `core`, so there is no cycle today; the local import keeps it that way if that changes).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd defendable-science && uv run pytest tests/test_config.py -v && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/core/config.py tests/test_config.py
git commit -m "feat(core): discover the repo root so commands work from a subdir"
```

### Task 4: The status-frontmatter renderer, and the templates it now owns

This is the task that ends the three-copies problem. It changes nine plugin
templates as well as package code, because the renderer and the artifacts it
renders must agree in the same commit.

**Files:**
- Create: `defendable-science/defendable_science/scaffold/status.py`
- Test: `defendable-science/tests/test_status.py`
- Modify: `resources/templates/hypothesis/{hypothesis,strategy,findings}.md`, `resources/templates/paper/{pitch,positioning,ledger,decision}.md`, `resources/templates/thesis/{aims,kappa}.md` — frontmatter only
- Modify: `defendable-science/tests/test_backlog.py:833-878` — replace the two-template drift guard with the nine-template one

**Interfaces:**
- Consumes: nothing.
- Produces: `StatusError(ValueError)`; `FIELD_ORDER: tuple[str, ...]`; `VERDICTS: dict[str, frozenset[str]]`; `READINESS: dict[str, frozenset[str]]`; `LEVEL_DEFAULTS: dict[str, dict[str, str]]`; `TEMPLATE_FORMS: dict[str, dict[str, str]]`; `render(level: str, fields: Mapping[str, str] | None = None) -> str`; `parse(text: str) -> dict[str, Any] | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_status.py
"""The single definition of the status frontmatter block (#120)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from defendable_science.scaffold import status as st

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_render_emits_the_documented_hypothesis_block() -> None:
    assert st.render("hypothesis") == (
        "status:\n"
        "  level: hypothesis\n"
        "  id: null\n"
        "  verdict: pending\n"
        "  readiness: pending\n"
        "  signed-off-by: null\n"
        "  signed-off-date: null\n"
        "  evidence: []\n"
        "  covers: []\n"
        "  load-bearing: null\n"
        "  understanding: {status: pending, unresolved: []}\n"
        "  blockers: []\n"
        "  last-updated: null\n"
    )


def test_render_applies_per_level_defaults() -> None:
    paper = yaml.safe_load(st.render("paper"))["status"]
    assert paper["verdict"] is None
    assert paper["readiness"] == "drafting"

    thesis = yaml.safe_load(st.render("thesis"))["status"]
    assert thesis["verdict"] == "n/a"
    assert thesis["readiness"] is None


def test_render_applies_overrides_in_field_order() -> None:
    text = st.render(
        "hypothesis",
        {"id": "2026-03-04-monotone", "last-updated": "2026-03-04", "verdict": "refuted"},
    )
    status = yaml.safe_load(text)["status"]

    assert status["id"] == "2026-03-04-monotone"
    assert status["verdict"] == "refuted"
    assert status["last-updated"] == "2026-03-04"
    keys = [line.split(":")[0].strip() for line in text.splitlines()[1:]]
    assert keys == list(st.FIELD_ORDER)


def test_render_rejects_an_unknown_level() -> None:
    with pytest.raises(st.StatusError, match="unknown level"):
        st.render("chapter")


def test_render_rejects_an_unknown_field() -> None:
    with pytest.raises(st.StatusError, match="unknown status field"):
        st.render("paper", {"priority": "high"})


def test_render_never_emits_a_placeholder() -> None:
    for level in ("hypothesis", "paper", "thesis"):
        assert "<" not in st.render(level)


def test_parse_returns_the_status_mapping() -> None:
    text = "---\nstatus:\n  level: paper\n  id: x\n---\n\n# Pitch\n"
    assert st.parse(text) == {"level": "paper", "id": "x"}


def test_parse_returns_none_without_frontmatter() -> None:
    assert st.parse("# Pitch\n\nno frontmatter here\n") is None


def test_parse_returns_none_when_frontmatter_is_unterminated() -> None:
    assert st.parse("---\nstatus:\n  level: paper\n") is None


def test_parse_raises_on_invalid_yaml() -> None:
    with pytest.raises(st.StatusError, match="invalid YAML"):
        st.parse("---\nstatus: [unclosed\n---\n")


def test_parse_returns_none_when_there_is_no_status_key() -> None:
    assert st.parse("---\ntitle: x\n---\n") is None


def test_parse_raises_when_status_is_not_a_mapping() -> None:
    with pytest.raises(st.StatusError, match="'status' must be a mapping"):
        st.parse("---\nstatus: draft\n---\n")


# --- the drift guard over every shipped template ----------------------------


def _status_block(text: str) -> str:
    """Return the frontmatter's status block, inline comments and blanks stripped."""
    match = re.search(r"\A---\n(.*?)^---\n", text, re.S | re.M)
    assert match is not None, "no terminated YAML frontmatter"
    lines = []
    for line in match.group(1).splitlines():
        stripped = re.sub(r"\s+#.*$", "", line).rstrip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("relpath", sorted(st.TEMPLATE_FORMS))
def test_every_shipped_template_matches_the_renderer(relpath: str) -> None:
    """The status block is what `progress` projects; a drift makes work vanish.

    Prose deliberately differs — the shipped template is the fuller authoring
    skeleton — but the frontmatter must not, and nothing at runtime can enforce
    that because the wheel ships only ``defendable_science`` (ADR-0026).
    """
    shipped = _REPO_ROOT / "resources" / "templates" / relpath
    assert shipped.is_file(), (
        f"{shipped} is missing; the drift guard cannot run. These tests are meant "
        "to run from a repo checkout, which has both artifacts."
    )
    form = st.TEMPLATE_FORMS[relpath]
    expected = st.render(form["level"], {k: v for k, v in form.items() if k != "level"})

    assert _status_block(shipped.read_text(encoding="utf-8")) == expected


@pytest.mark.parametrize("relpath", sorted(st.TEMPLATE_FORMS))
def test_no_shipped_template_carries_a_placeholder_in_a_machine_read_field(
    relpath: str,
) -> None:
    """`readiness: <synthesis | defensible>` parses as a real value (#121)."""
    shipped = _REPO_ROOT / "resources" / "templates" / relpath
    status = yaml.safe_load(_status_block(shipped.read_text(encoding="utf-8")))["status"]

    placeholders = {
        key: value
        for key, value in status.items()
        if isinstance(value, str) and value.startswith("<")
    }
    assert placeholders == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_status.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'defendable_science.scaffold.status'`

- [ ] **Step 3: Write the minimal implementation**

```python
# defendable_science/scaffold/status.py
"""The single definition of the status frontmatter block (#120).

Every hypothesis / paper / thesis artifact carries one ``status:`` block — the
source of truth ``progress`` projects. The field set, the per-level enums, and
each staged document's initial form are written here and nowhere else; the
shipped templates under ``resources/templates/`` are guarded against this module
by ``tests/test_status.py``, because the wheel cannot read plugin content
(ADR-0026).

Grounding: ``resources/templates/README.md`` § Status-frontmatter convention.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import yaml

#: Field order, verbatim as it appears in every artifact.
FIELD_ORDER = (
    "level",
    "id",
    "verdict",
    "readiness",
    "signed-off-by",
    "signed-off-date",
    "evidence",
    "covers",
    "load-bearing",
    "understanding",
    "blockers",
    "last-updated",
)

#: Allowed ``verdict`` values per level. A thesis has no verdict axis — it uses
#: ``readiness: defensible`` — so ``n/a`` is its only legal value.
VERDICTS = {
    "hypothesis": frozenset({"pending", "confirmed", "refuted", "inconclusive"}),
    "paper": frozenset({"no-go", "publish"}),
    "thesis": frozenset({"n/a"}),
}

#: Allowed ``readiness`` values per level.
READINESS = {
    "hypothesis": frozenset({"pending", "resolved"}),
    "paper": frozenset({"drafting", "under-review", "published"}),
    "thesis": frozenset({"framing", "synthesis", "defensible"}),
}

#: The base block per level. Anything absent renders ``null`` — absence means
#: "not yet set," never zero, and never a ``<placeholder>`` string.
LEVEL_DEFAULTS: dict[str, dict[str, str]] = {
    "hypothesis": {"verdict": "pending", "readiness": "pending"},
    "paper": {"readiness": "drafting"},
    "thesis": {"verdict": "n/a"},
}

_EMPTY: dict[str, str] = {
    "evidence": "[]",
    "covers": "[]",
    "understanding": "{status: pending, unresolved: []}",
    "blockers": "[]",
}

#: Each shipped template's initial status form, keyed by its path under
#: ``resources/templates/``. Read by the drift guard and by the scaffolders, so
#: "what a fresh findings.md looks like" is defined once.
TEMPLATE_FORMS: dict[str, dict[str, str]] = {
    "hypothesis/hypothesis.md": {"level": "hypothesis"},
    "hypothesis/strategy.md": {"level": "hypothesis"},
    "hypothesis/findings.md": {
        "level": "hypothesis",
        "verdict": "null",
        "readiness": "resolved",
        "understanding": "{status: ok, unresolved: []}",
    },
    "paper/pitch.md": {"level": "paper"},
    "paper/positioning.md": {"level": "paper"},
    "paper/ledger.md": {"level": "paper"},
    "paper/decision.md": {
        "level": "paper",
        "understanding": "{status: ok, unresolved: []}",
    },
    "thesis/aims.md": {"level": "thesis", "readiness": "framing"},
    "thesis/kappa.md": {
        "level": "thesis",
        "understanding": "{status: ok, unresolved: []}",
    },
}


class StatusError(ValueError):
    """Raised on an unknown level or field, or unparseable frontmatter."""


def render(level: str, fields: Mapping[str, str] | None = None) -> str:
    """Render a ``status:`` block.

    :param level: ``hypothesis`` | ``paper`` | ``thesis``.
    :param fields: Field name (hyphenated, as written in the file) to
        already-YAML-rendered value; merged over the level defaults. Anything
        unspecified renders ``null`` or its empty collection.
    :returns: The block, newline-terminated, with no frontmatter delimiters and
        no comments.
    :raises StatusError: On an unknown `level` or an unknown field name.
    """
    if level not in LEVEL_DEFAULTS:
        msg = f"unknown level {level!r}; expected one of {sorted(LEVEL_DEFAULTS)}"
        raise StatusError(msg)
    supplied = dict(fields or {})
    unknown = sorted(k for k in supplied if k not in FIELD_ORDER)
    if unknown:
        msg = f"unknown status field(s) {unknown}; fields are {list(FIELD_ORDER)}"
        raise StatusError(msg)

    values = {"level": level, **_EMPTY, **LEVEL_DEFAULTS[level], **supplied}
    lines = ["status:"]
    lines.extend(f"  {name}: {values.get(name, 'null')}" for name in FIELD_ORDER)
    return "\n".join(lines) + "\n"


def parse(text: str) -> dict[str, Any] | None:
    """Extract the ``status`` mapping from a document's YAML frontmatter.

    :param text: The whole document.
    :returns: The status mapping, or ``None`` when the document has no
        terminated frontmatter or carries no ``status`` key. ``None`` means
        *absent*, which the caller reports as a missing block — it never means
        "valid and empty".
    :raises StatusError: If the frontmatter is not valid YAML, or ``status`` is
        present but is not a mapping.
    """
    match = re.search(r"\A---\n(.*?)^---\s*$", text, re.S | re.M)
    if match is None:
        return None
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        msg = f"invalid YAML in frontmatter: {exc}"
        raise StatusError(msg) from exc
    if not isinstance(data, dict) or "status" not in data:
        return None
    status = data["status"]
    if not isinstance(status, dict):
        msg = f"'status' must be a mapping, got {type(status).__name__}"
        raise StatusError(msg)
    return status
```

- [ ] **Step 4: Update the nine shipped templates**

For each template, replace the `status:` block so it matches `render(...)` once
inline comments are stripped: every unset machine-read field becomes `null`, and
the guidance that used to sit *in* the value moves into the trailing comment.
`resources/templates/thesis/kappa.md` is the worked example — its `readiness` is
the bug #121 quotes:

```yaml
---
status:
  level: thesis
  id: null                     # <thesis-slug> — fill when the thesis is framed
  verdict: n/a                 # thesis has no verdict axis; readiness carries it
  readiness: null              # framing | synthesis | defensible (defensible only once signed)
  signed-off-by: null          # REQUIRED for defensibility — named human; not defensible until set
  signed-off-date: null        # REQUIRED
  evidence: []                 # the kappa introduces NO new findings — papers carry all evidence
  covers: []
  load-bearing: null
  understanding: {status: ok, unresolved: []}   # from the mock viva before sign-off
  blockers: []                 # e.g. uncovered aims surfaced by progress
  last-updated: null           # <YYYY-MM-DD>
---
```

The other eight follow the same rule. The complete set of value changes:

| Template | Field | Was | Becomes |
|---|---|---|---|
| all nine | `id` | `<YYYY-MM-DD-slug>` / `<paper-id>` / `<thesis-slug>` | `null` (format in the comment) |
| all nine | `last-updated` | `<YYYY-MM-DD>` | `null` (format in the comment) |
| `hypothesis/findings.md` | `verdict` | `<confirmed \| refuted \| inconclusive>` | `null` |
| `hypothesis/findings.md` | `load-bearing` | `<true \| false>` | `null` |
| `paper/decision.md` | `verdict` | `<publish \| no-go>` | `null` |
| `paper/decision.md` | `readiness` | `drafting` | `drafting` (unchanged) |
| `thesis/aims.md` | `readiness` | `framing` | `framing` (unchanged) |
| `thesis/kappa.md` | `readiness` | `<synthesis \| defensible>` | `null` |

- [ ] **Step 5: Replace the old two-template drift guard**

Delete `tests/test_backlog.py:833-878` — `_REPO_ROOT`, `_status_block`,
`_placeholderless`, and `test_code_template_status_block_matches_the_shipped_template`
— together with the now-unused `re` import if nothing else in the file uses it.
The nine-template guard in `tests/test_status.py` supersedes it. Keep
`test_scaffolded_pitch_has_status_frontmatter`; it asserts behaviour, not shape.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd defendable-science && uv run pytest tests/test_status.py tests/test_backlog.py -v`
Expected: PASS — all 9 parametrizations of both template guards green.

- [ ] **Step 7: Commit**

```bash
cd defendable-science
git add defendable_science/scaffold/status.py tests/test_status.py tests/test_backlog.py
cd ..
git add resources/templates/
git commit -m "feat(scaffold): render the status block from one definition

Replaces the two-template drift guard with one covering all nine, and moves
every unset machine-read field to null — 'readiness: <synthesis | defensible>'
parsed as a real value, so progress read a bogus readiness (#121)."
```

### Task 5: Route the scaffolders and the CLI through the resolver

**Files:**
- Modify: `defendable-science/defendable_science/exploration/backlog.py:493,539,584,666,675`
- Modify: `defendable-science/defendable_science/cli.py:389-390,427,1249,1267,1294,1321,1339,1379,1404,1454,1536`
- Test: `defendable-science/tests/test_backlog.py`, `defendable-science/tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `Layout`, `resolve_layout` (Tasks 1-2), `find_repo_root` (Task 3), `status.render` (Task 4).
- Produces: `backlog.registry_root(layout, paper_root) -> str`; `cli._layout_or_exit() -> tuple[dict[str, Any], Layout]`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_backlog.py
from defendable_science.scaffold.layout import Layout


def test_registry_root_is_correct_under_a_non_default_research_root(
    tmp_path: Path,
) -> None:
    """`research.parent.parent` was wrong for any research_root but docs/research."""
    layout = Layout.default(tmp_path)
    flat = Layout(
        repo_root=tmp_path,
        research_root=tmp_path / "writing",
        literature_dir=tmp_path / "writing" / "literature",
        datasets_manifest=tmp_path / "datasets.yml",
        thesis_dir=tmp_path / "writing" / "thesis",
    )

    assert b.registry_root(layout, layout.paper_dir("dc")) == "docs/research/dc"
    assert b.registry_root(flat, flat.paper_dir("dc")) == "writing/dc"


def test_scaffolded_hypothesis_and_pitch_status_blocks_come_from_the_renderer(
    tmp_path: Path,
) -> None:
    research = tmp_path / "docs" / "research"
    research.mkdir(parents=True)
    root = b.scaffold_paper(
        research, "dc", "Depth collapse", backend="bench", provenance="p",
        today="2026-03-04",
    )
    pitch = (root / "paper" / "pitch.md").read_text(encoding="utf-8")
    target = b.scaffold_hypothesis(
        root, "2026-03-04-monotone", "Monotone depth", "p", today="2026-03-04"
    )
    hypothesis = target.read_text(encoding="utf-8")

    assert st.render("paper", {"id": "dc", "last-updated": "2026-03-04"}) in pitch
    assert (
        st.render(
            "hypothesis",
            {"id": "2026-03-04-monotone", "last-updated": "2026-03-04"},
        )
        in hypothesis
    )
```

```python
# append to tests/test_cli_commands.py
def test_park_resolves_the_backlog_from_the_layout(tmp_path, monkeypatch) -> None:
    (tmp_path / ".defendable-science").mkdir()
    (tmp_path / ".defendable-science" / "config.yml").write_text(
        "layout:\n  research_root: writing/\n", encoding="utf-8"
    )
    paper = tmp_path / "writing" / "dc"
    paper.mkdir(parents=True)
    (paper / "backlog.md").write_text(
        b.Backlog(level="hypothesis").dumps(), encoding="utf-8"
    )
    monkeypatch.chdir(paper)

    result = runner.invoke(
        app, ["backlog", "park", "An idea", "--provenance", "smoke"]
    )

    assert result.exit_code == 0, result.stdout
    assert "An idea" in (paper / "backlog.md").read_text(encoding="utf-8")


def test_promote_scaffold_needs_no_path_options(tmp_path, monkeypatch) -> None:
    (tmp_path / ".defendable-science").mkdir()
    research = tmp_path / "docs" / "research"
    research.mkdir(parents=True)
    (research / "portfolio-backlog.md").write_text(
        b.Backlog(level="paper").dumps(), encoding="utf-8"
    )
    (research / "papers.md").write_text(
        b.registry_dumps(), encoding="utf-8"
    ) if hasattr(b, "registry_dumps") else None
    monkeypatch.chdir(tmp_path)

    runner.invoke(
        app,
        ["backlog", "park", "Depth collapse", "--provenance", "p", "--level", "paper"],
    )
    runner.invoke(
        app, ["backlog", "rank", "depth-collapse", "--level", "paper", "--feas", "3"]
    )
    result = runner.invoke(
        app,
        [
            "backlog", "promote", "depth-collapse", "--level", "paper",
            "--scaffold", "--backend", "bench",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (research / "depth-collapse" / "paper" / "pitch.md").is_file()
```

The `rank` invocation's option names must match the real signature at
`cli.py:1339`; read it and adjust the score flags before running.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_backlog.py::test_registry_root_is_correct_under_a_non_default_research_root tests/test_cli_commands.py -k layout -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'registry_root'`, and the CLI tests fail because `--backlog` defaults to a bare `"backlog.md"`.

- [ ] **Step 3: Write the minimal implementation**

In `backlog.py`:

1. Replace `_registry_root(root, research)` (`:666`) with

```python
def registry_root(layout: Layout, paper_root: Path) -> str:
    """Render `paper_root` relative to the repo root for the registry row.

    :param layout: The resolved layout, which knows the repo root. Deriving it
        as ``research.parent.parent`` was correct only for the default
        ``docs/research`` and silently wrong for any other ``research_root``.
    :param paper_root: The paper's root directory.
    :returns: The repo-relative path as a string.
    """
    return str(layout.rel(paper_root))
```

Give `scaffold_paper` a `layout: Layout | None = None` keyword; when omitted,
build `Layout.default(Path(research_root).parent.parent)` so existing callers
keep working, and pass it to `registry_root`.

2. Rewrite the two literals so the status block is interpolated, not written out:

```python
_HYPOTHESIS_TEMPLATE = """\
---
{status}---

# Hypothesis: {one_line}
...
"""
```

and in `scaffold_hypothesis`, format with
`status=status.render("hypothesis", {"id": slug, "last-updated": today})`;
likewise `status.render("paper", {"id": paper_id, "last-updated": today})` in
`scaffold_paper`. Delete the `#: Mirrors resources/templates/paper/pitch.md`
docstring block at `:531-538` — the duplication it apologised for is gone — and
replace it with a one-line note that the block comes from `scaffold.status`.

In `cli.py`:

3. Add, next to `_cache_root` (`:145`):

```python
def _layout_or_exit() -> tuple[dict[str, Any], Layout]:
    """Load the config and resolve the layout, exiting 1 on an invalid block.

    :returns: The config mapping and the resolved layout.
    :raises typer.Exit: Code 1 if ``layout:`` is invalid.
    """
    config = _load_config_or_exit()
    repo_root = find_repo_root()
    try:
        return config, resolve_layout(config, repo_root)
    except LayoutError as exc:
        typer.echo(f"invalid .defendable-science/config.yml: {exc}", err=True)
        raise typer.Exit(code=1) from exc
```

4. Change `_DEFAULT_REGISTRY_PATH` / `_DEFAULT_TRIAGE_PATH` (`:389-390`) into
   layout-derived defaults inside `_lit_registry_paths` (`:427`): explicit
   `literature.registry` / `literature.triage` still win, then
   `layout.references` / `layout.triage`. Delete the two module-level string
   constants so the paths exist in one place.

5. Make `--backlog`, `--paper-root` and `--research-root` `None`-defaulted on
   `park` (`:1267`), `add` (`:1294`), `list_` (`:1321`), `rank` (`:1339`),
   `promote` (`:1454`) and `drop` (`:1536`). Resolve an omitted `--backlog` as:
   `layout.portfolio_backlog` at the paper level; at the hypothesis level, the
   `backlog.md` of the paper directory the cwd sits in — found by walking up from
   the cwd to the first directory that is a child of `research_root` — falling
   back to a clear error naming `--backlog` when the cwd is outside any paper.
   Relax `_check_scaffold_opts` (`:1379`) to demand only `--backend` at the paper
   level; paths now come from the layout.

- [ ] **Step 4: Run the full suite**

Run: `cd defendable-science && uv run pytest -q && uv run mypy && uv run ruff check`
Expected: PASS with 100% coverage.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/ tests/
git commit -m "refactor(cli): resolve every path from the layout, not from options

Fixes _registry_root deriving the repo root as research.parent.parent, which
was wrong for any research_root other than docs/research."
```

### Task 6: ADR-0039 and the PR

**Files:**
- Create: `decisions/0039-recorded-consumer-layout.md`
- Modify: `decisions/README.md`

- [ ] **Step 1: Write the ADR**

MADR format, matching the existing files in `decisions/`: context · decision
drivers · considered options · decision outcome · consequences · rejected
alternatives. Content comes from the spec's *Decisions* and *Rejected
alternatives* sections: the bounded four-key set, versus a fixed layout with a
single `research_root` override, versus a full per-file block with `{paper_id}`
interpolation. Record thesis-ness-as-a-fact-on-disk and the
inside-a-paper-is-not-configurable rule as consequences, and note ADR-0031
(`cache_dir`) as the config-driven-path precedent being mirrored.

- [ ] **Step 2: Append it to the index**

Add the row to `decisions/README.md` in the same format as ADR-0038.

- [ ] **Step 3: Run every gate**

```bash
cd defendable-science && uv run pytest -q && uv run mypy && uv run ruff check && cd ..
pre-commit run --all-files
./tools/validate-plugin.sh
```

Expected: all green. Fix anything `codespell` or `detect-secrets` flags.

- [ ] **Step 4: Commit and open the PR**

```bash
git add decisions/
git commit -m "docs(decisions): ADR-0039 — record the consumer layout"
```

Then use the `create-pr` skill. The body must state that it closes #122, and
must call out the `_registry_root` bug fix and the removal of
`_DEFAULT_REGISTRY_PATH` / `_DEFAULT_TRIAGE_PATH` as behaviour changes reviewers
should check.

---

# PR2 — `defendable-science init` (closes #120)

Branch: `feat/init-command`, off `main` after PR1 lands.

### Task 7: `registry_dumps` — an empty-but-valid `papers.md`

**Files:**
- Modify: `defendable-science/defendable_science/exploration/backlog.py` (after `REGISTRY_COLUMNS` at `:48`)
- Test: `defendable-science/tests/test_backlog.py`

**Interfaces:**
- Consumes: `REGISTRY_COLUMNS` (`:48`), `_splice` (`:234`).
- Produces: `registry_dumps() -> str`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_backlog.py
def test_registry_dumps_produces_a_registry_append_papers_registry_accepts(
    tmp_path: Path,
) -> None:
    """The 4th `state` column an agent invented is why promote could not register."""
    papers = tmp_path / "papers.md"
    papers.write_text(b.registry_dumps(), encoding="utf-8")

    b.append_papers_registry(papers, "depth-collapse", "docs/research/dc", "bench")

    text = papers.read_text(encoding="utf-8")
    header = [c.strip() for c in text.splitlines()[2].strip("|").split("|")]
    assert header == b.REGISTRY_COLUMNS
    assert "depth-collapse" in text


def test_registry_dumps_carries_a_heading_and_no_data_rows() -> None:
    text = b.registry_dumps()

    assert text.startswith("# Papers registry\n")
    assert "| paper-id | root | backend |" in text
    assert "|---" in text
    assert text.count("\n|") == 2  # header + separator only
```

Read the emitted text once before asserting on line indices — `_render_table`'s
exact spacing decides whether the header is line 2 or line 3, and the test must
match the renderer rather than an assumption about it.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd defendable-science && uv run pytest tests/test_backlog.py -k registry_dumps -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'registry_dumps'`

- [ ] **Step 3: Write the minimal implementation**

```python
_REGISTRY_PREAMBLE = """\
# Papers registry

<!-- paper-id → the paper's root + its experiment-backend binding.
     `defendable-science backlog promote --scaffold` appends rows; a paper-id is
     stable once written, because it keys the paper across the backlog, the
     dashboard and `progress`. -->

"""


def registry_dumps(preamble: str = _REGISTRY_PREAMBLE) -> str:
    """Render an empty-but-valid ``papers.md``.

    The header is rendered from :data:`REGISTRY_COLUMNS`, so a column added there
    cannot leave scaffolding behind — an invented 4th column is exactly why
    ``promote --scaffold`` could not register a paper into a hand-written
    registry.

    :param preamble: Host prose to place above the table.
    :returns: The whole document.
    """
    return _splice(preamble, "", list(REGISTRY_COLUMNS), [])
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd defendable-science && uv run pytest tests/test_backlog.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/exploration/backlog.py tests/test_backlog.py
git commit -m "feat(backlog): render an empty-but-valid papers.md from REGISTRY_COLUMNS"
```

### Task 8: `render.py` — every machine-read file

**Files:**
- Create: `defendable-science/defendable_science/scaffold/render.py`
- Test: `defendable-science/tests/test_render.py`

**Interfaces:**
- Consumes: `Backlog`, `registry_dumps` from `exploration.backlog`.
- Produces: `render_papers_registry() -> str`; `render_portfolio_backlog() -> str`; `render_paper_backlog() -> str`; `render_references() -> str`; `render_triage() -> str`; `render_datasets_manifest() -> str`; `render_config(cache_dir: str = DEFAULT_CACHE_DIR) -> str`; `render_rclone_example() -> str`; `render_dashboard() -> str`; `gitignore_entries(cache_dir: str) -> list[str]`; `merge_gitignore(existing: str, entries: Sequence[str]) -> str`; `DEFAULT_CACHE_DIR: str`.

- [ ] **Step 1: Write the failing test**

Every assertion runs the *real loader* over the rendered text. That is the point:
a renderer whose output its own loader rejects is the bug this milestone exists to
kill.

```python
# tests/test_render.py
"""Every machine-read file `init` writes, checked with its own loader (#120)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from defendable_science.dataset import manifest as manifest_mod
from defendable_science.exploration import backlog as b
from defendable_science.literature import registry as reg
from defendable_science.core.config import load_config
from defendable_science.scaffold import render as r


def test_rendered_backlogs_carry_the_canonical_column_profiles() -> None:
    portfolio = b.Backlog.loads(r.render_portfolio_backlog(), "paper")
    paper = b.Backlog.loads(r.render_paper_backlog(), "hypothesis")

    assert portfolio.columns == b.PAPER_COLUMNS
    assert paper.columns == b.HYPOTHESIS_COLUMNS
    assert portfolio.rows == []
    assert paper.rows == []


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


def test_rendered_dashboard_says_it_has_no_generator_yet() -> None:
    text = r.render_dashboard()

    assert "GENERATED" in text
    assert "progress" in text
    assert "0" not in text.split("\n")[0]  # never a fabricated count


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

    merged = r.merge_gitignore(existing, r.gitignore_entries(".defendable-science/cache/"))

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'defendable_science.scaffold.render'`

- [ ] **Step 3: Write the minimal implementation**

```python
# defendable_science/scaffold/render.py
"""Renderers for every machine-read file ``init`` writes (#120).

The package renders these — rather than the plugin templating them — because it
already owns their shapes: the column profiles in ``exploration.backlog`` and the
loaders in ``literature.registry``, ``dataset.manifest`` and ``core.config``.
Each renderer's output is asserted against its own loader in
``tests/test_render.py``.

Every unset field is ``null`` or its empty collection, never a ``<placeholder>``
string: a placeholder parses as a real value, which is how a scaffolded
``readiness: <synthesis | defensible>`` reached ``progress`` as a real readiness.
"""

from __future__ import annotations

from collections.abc import Sequence

from defendable_science.exploration.backlog import Backlog, registry_dumps

#: Mirrors ``core.config``'s cache default (ADR-0031); written explicitly so the
#: scaffolded ``.gitignore`` and the runtime cache path cannot drift.
DEFAULT_CACHE_DIR = ".defendable-science/cache/"

_GITIGNORE_MARKER = "# defendable-science"


def render_papers_registry() -> str:
    """Render an empty-but-valid ``papers.md``."""
    return registry_dumps()


def render_portfolio_backlog() -> str:
    """Render an empty-but-valid paper-level backlog."""
    return Backlog(
        level="paper",
        preamble=(
            "# Portfolio backlog\n\n"
            "<!-- Paper-level ideas: parked → candidate → ranked → promoted |\n"
            "     dropped. `defendable-science backlog` moves rows; promotion is a\n"
            "     human pick, never a computed one. -->\n\n"
        ),
    ).dumps()


def render_paper_backlog() -> str:
    """Render an empty-but-valid hypothesis-level backlog for one paper."""
    return Backlog(
        level="hypothesis",
        preamble=(
            "# Hypothesis backlog\n\n"
            "<!-- Hypotheses for this paper: parked → candidate → ranked →\n"
            "     promoted | dropped. -->\n\n"
        ),
    ).dumps()


def render_references() -> str:
    """Render an empty CSL-JSON bibliography."""
    return "[]\n"


def render_triage() -> str:
    """Render an empty triage sidecar (comments only — a valid empty mapping)."""
    return (
        "# Triage sidecar — our decisions about each reference, keyed by the\n"
        "# citekey in references.json (the bibliographic source of truth,\n"
        "# ADR-0020). One row per reference: role, disposition, rationale.\n"
    )


def render_datasets_manifest() -> str:
    """Render an empty-but-valid ``datasets.yml``."""
    return (
        "# Dataset registry. `defendable-science dataset register` appends entries;\n"
        "# license and tier are material classifications a human confirms.\n"
        "mirror: null\n"
        "datasets: []\n"
    )


def render_config(cache_dir: str = DEFAULT_CACHE_DIR) -> str:
    """Render ``.defendable-science/config.yml`` with the five consumer bindings.

    Every binding is ``null`` until the author sets it. ``layout:`` is written as
    a comment, not a key: a repo matching the default tree records nothing, so
    there is nothing to keep in step.

    :param cache_dir: The cache root to record (ADR-0031).
    :returns: The config file text.
    """
    return f"""\
# defendable-science project configuration.
#
# `null` means "not yet set" — never a placeholder string. A `<...>` value would
# parse as a real value and be read as a real binding.

# The CLI's dataset + HTTP caches both live under exactly this path (ADR-0031);
# the scaffolded .gitignore excludes it.
cache_dir: {cache_dir}

# The repo-local harness implementing the experiment-backend contract
# (resources/contracts/experiment-backend.md). The plugin ships no default, so
# until this is set the repo cannot produce the run-refs `evidence:` requires.
experiment_backend: null

# The design/plan/implement delegate engineering is handed off to
# (resources/contracts/engineering.md, ADR-0023).
engineering_backend: null

literature:
  # Seed works/authors the `literature` capability ranks around.
  anchors: []
  # Contact address sent to OpenAlex/Crossref as a courtesy.
  mailto: null
  # The private mirror. Credentials live in .defendable-science/rclone.conf
  # (gitignored) — only the logical remote name belongs here.
  mirror:
    remote: null
    base_path: null

# layout:
#   Only needed if this repo diverges from the default tree. Keys:
#   research_root, literature_dir, datasets_manifest, thesis_dir.
#   Omitted keys fall back to the default; an unknown key is an error.
"""


def render_rclone_example() -> str:
    """Render the committed rclone template (remote name and type only)."""
    return (
        "# Committed template. Copy to .defendable-science/rclone.conf (gitignored)\n"
        "# and fill in credentials there — never here.\n"
        "[research-mirror]\n"
        "type = s3\n"
    )


def render_dashboard() -> str:
    """Render the dashboard stub.

    Says plainly that no generator exists yet rather than projecting a fabricated
    state: the header claims the file is generated, and until ``progress`` has a
    CLI-backed generator, writing a plausible-looking dashboard here would be the
    dishonest option.
    """
    return (
        "<!-- GENERATED by `progress dashboard` — never hand-edited. -->\n\n"
        "# Research dashboard\n\n"
        "Not yet generated. This file is a pure projection of the status\n"
        "frontmatter in each hypothesis / paper / thesis artifact; run the\n"
        "`progress` skill to regenerate it. Nothing here is ground truth — if\n"
        "this file and the frontmatter disagree, the frontmatter wins.\n"
    )


def gitignore_entries(cache_dir: str) -> list[str]:
    """Return the entries a defendable-science repo must gitignore.

    :param cache_dir: The configured cache root, so the ignore entry and the
        runtime cache path cannot diverge.
    :returns: The entries, in the order they are appended.
    """
    return [
        cache_dir,
        ".defendable-science/rclone.conf",
        ".defendable-science/keys.json",
    ]


def merge_gitignore(existing: str, entries: Sequence[str]) -> str:
    """Append missing `entries` to an existing ``.gitignore``, verbatim otherwise.

    Append-only on purpose: a consumer's ``.gitignore`` is their file, and
    rewriting it to a template would discard rules the repo depends on.

    :param existing: The current file contents (``""`` when absent).
    :param entries: The entries that must be present.
    :returns: The merged contents; `existing` unchanged when nothing is missing.
    """
    present = {line.strip() for line in existing.splitlines()}
    missing = [entry for entry in entries if entry not in present]
    if not missing:
        return existing
    prefix = existing
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix:
        prefix += "\n"
    return prefix + _GITIGNORE_MARKER + "\n" + "".join(f"{e}\n" for e in missing)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd defendable-science && uv run pytest tests/test_render.py -v --cov=defendable_science.scaffold.render --cov-report=term-missing --no-cov-on-fail`
Expected: PASS at 100% coverage. If `Backlog(level=..., preamble=...)`'s output
puts the heading somewhere unexpected, fix the preamble string rather than the
assertion — `_splice` guarantees a table cannot start mid-line.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/scaffold/render.py tests/test_render.py
git commit -m "feat(scaffold): render every machine-read file from its owner"
```

### Task 9: `init_repo` — the writer

**Files:**
- Create: `defendable-science/defendable_science/scaffold/init_repo.py`
- Test: `defendable-science/tests/test_init_repo.py`

**Interfaces:**
- Consumes: `Layout` (Task 1), every renderer (Task 8).
- Produces: `Action` frozen dataclass with fields `path: Path`, `status: str` (`"created"` | `"exists"` | `"merged"`); `init_repo(layout: Layout, *, thesis: bool = False, dry_run: bool = False) -> list[Action]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_init_repo.py
"""Scaffolding a repo: idempotent, non-destructive, and immediately usable."""

from __future__ import annotations

from pathlib import Path

from defendable_science.scaffold import render as r
from defendable_science.scaffold.init_repo import init_repo
from defendable_science.scaffold.layout import Layout


def _init(root: Path, **kwargs: bool) -> list[str]:
    actions = init_repo(Layout.default(root), **kwargs)
    return [f"{a.status}:{a.path.relative_to(root)}" for a in actions]


def test_init_creates_the_default_layout(tmp_path: Path) -> None:
    statuses = _init(tmp_path)

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
        assert (tmp_path / path).is_file()


def test_init_omits_the_thesis_tree_by_default(tmp_path: Path) -> None:
    _init(tmp_path)

    assert not (tmp_path / "docs" / "research" / "thesis").exists()


def test_init_thesis_creates_the_thesis_tree(tmp_path: Path) -> None:
    statuses = _init(tmp_path, thesis=True)

    assert "created:docs/research/thesis/aims.md" in statuses
    assert "created:docs/research/thesis/milestones.yml" in statuses
    assert (tmp_path / "docs" / "research" / "thesis" / "kappa").is_dir()


def test_init_is_idempotent_and_byte_identical(tmp_path: Path) -> None:
    _init(tmp_path)
    before = {
        p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()
    }

    second = _init(tmp_path)

    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert after == before
    assert all(status.startswith(("exists:", "merged:")) for status in second)


def test_init_never_overwrites_author_content(tmp_path: Path) -> None:
    papers = tmp_path / "docs" / "research" / "papers.md"
    papers.parent.mkdir(parents=True)
    papers.write_text("MY OWN REGISTRY\n", encoding="utf-8")

    statuses = _init(tmp_path)

    assert "exists:docs/research/papers.md" in statuses
    assert papers.read_text(encoding="utf-8") == "MY OWN REGISTRY\n"


def test_init_gitignore_merge_preserves_existing_rules(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")

    _init(tmp_path)

    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "__pycache__/" in text
    assert r.DEFAULT_CACHE_DIR in text


def test_init_reports_gitignore_as_exists_when_nothing_is_missing(
    tmp_path: Path,
) -> None:
    entries = r.gitignore_entries(r.DEFAULT_CACHE_DIR)
    (tmp_path / ".gitignore").write_text("\n".join(entries) + "\n", encoding="utf-8")

    statuses = _init(tmp_path)

    assert "exists:.gitignore" in statuses


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    statuses = _init(tmp_path, dry_run=True)

    assert "created:docs/research/papers.md" in statuses
    assert list(tmp_path.iterdir()) == []


def test_init_respects_a_non_default_layout(tmp_path: Path) -> None:
    layout = Layout(
        repo_root=tmp_path,
        research_root=tmp_path / "writing",
        literature_dir=tmp_path / "bib",
        datasets_manifest=tmp_path / "data" / "datasets.yml",
        thesis_dir=tmp_path / "phd",
    )

    init_repo(layout, thesis=True)

    assert (tmp_path / "writing" / "papers.md").is_file()
    assert (tmp_path / "bib" / "references.json").is_file()
    assert (tmp_path / "data" / "datasets.yml").is_file()
    assert (tmp_path / "phd" / "aims.md").is_file()


def test_init_uses_the_configured_cache_dir_for_the_gitignore_entry(
    tmp_path: Path,
) -> None:
    init_repo(Layout.default(tmp_path), cache_dir=".cache/ds/")

    assert ".cache/ds/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_init_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'defendable_science.scaffold.init_repo'`

- [ ] **Step 3: Write the minimal implementation**

```python
# defendable_science/scaffold/init_repo.py
"""Scaffold a consumer repo from the renderers (#120).

Idempotent and non-destructive: an existing file is reported and left alone,
never overwritten, so re-running fills gaps only (``research-init``'s guardrail).
``.gitignore`` is the one exception, and it is merged append-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from defendable_science.scaffold import render as r
from defendable_science.scaffold.layout import Layout


@dataclass(frozen=True)
class Action:
    """One file `init` considered.

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


def _merge_gitignore(
    layout: Layout, cache_dir: str, actions: list[Action], *, dry_run: bool
) -> None:
    """Append any missing ignore entries to ``.gitignore``."""
    path = layout.repo_root / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    merged = r.merge_gitignore(existing, r.gitignore_entries(cache_dir))
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
        layout.datasets_manifest,
        r.render_datasets_manifest(),
        actions,
        dry_run=dry_run,
    )
    _write(layout.config_file, r.render_config(cache_dir), actions, dry_run=dry_run)
    _write(
        layout.config_dir / "rclone.conf.example",
        r.render_rclone_example(),
        actions,
        dry_run=dry_run,
    )
    if thesis:
        _write(layout.aims, _AIMS_STUB, actions, dry_run=dry_run)
        _write(layout.milestones, _MILESTONES_STUB, actions, dry_run=dry_run)
        if not dry_run:
            layout.kappa_dir.mkdir(parents=True, exist_ok=True)
        actions.append(Action(path=layout.kappa_dir, status="created"))
    _merge_gitignore(layout, cache_dir, actions, dry_run=dry_run)
    return actions
```

`_AIMS_STUB` and `_MILESTONES_STUB`: `aims.md` is a *prose* template, so its stub
is `"---\n" + status.render("thesis", {"readiness": "framing"}) + "---\n\n# Thesis aims\n\n<!-- ... -->\n"`,
mirroring how `scaffold_paper` seeds a tracked stub rather than drafted prose.
`milestones.yml` is machine-read; add a `render_milestones()` to `render.py` in
Task 8 emitting a valid YAML mapping of gate → `null`, with a test asserting
`yaml.safe_load` returns a mapping whose every value is `None`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd defendable-science && uv run pytest tests/test_init_repo.py -v --cov=defendable_science.scaffold --cov-report=term-missing --no-cov-on-fail`
Expected: PASS at 100% coverage.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/scaffold/init_repo.py tests/test_init_repo.py
git commit -m "feat(scaffold): scaffold a repo idempotently from the renderers"
```

### Task 10: The `init` CLI command

**Files:**
- Modify: `defendable-science/defendable_science/cli.py` (after `doctor` at `:104`)
- Test: `defendable-science/tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `init_repo`, `Action` (Task 9), `_layout_or_exit` (Task 5), `_cache_root` (`cli.py:145`).
- Produces: the `init` command; JSON `{"root": str, "thesis": bool, "dry_run": bool, "actions": [{"path": str, "status": str}], "counts": {"created": int, "exists": int, "merged": int}}`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_cli_commands.py
def test_init_scaffolds_and_reports_json(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["counts"]["created"] > 0
    assert payload["thesis"] is False
    paths = {action["path"] for action in payload["actions"]}
    assert "docs/research/papers.md" in paths  # repo-relative in the report
    assert (tmp_path / "docs" / "research" / "papers.md").is_file()


def test_init_is_idempotent_at_the_cli(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["counts"]["created"] == 0


def test_init_dry_run_writes_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "--dry-run"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["dry_run"] is True
    assert list(tmp_path.iterdir()) == []


def test_init_thesis_scaffolds_the_thesis_tree(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init", "--thesis"])

    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "docs" / "research" / "thesis" / "aims.md").is_file()


def test_init_honours_root_and_a_recorded_layout(tmp_path) -> None:
    (tmp_path / ".defendable-science").mkdir()
    (tmp_path / ".defendable-science" / "config.yml").write_text(
        "layout:\n  research_root: writing/\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["init", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "writing" / "papers.md").is_file()


def test_init_exits_1_on_an_invalid_layout_block(tmp_path, monkeypatch) -> None:
    (tmp_path / ".defendable-science").mkdir()
    (tmp_path / ".defendable-science" / "config.yml").write_text(
        "layout:\n  papers_dir: x/\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 1
    assert "unknown layout key" in result.output
    assert "research_root" in result.output
    assert "Traceback" not in result.output
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_cli_commands.py -k init -v`
Expected: FAIL — Typer exits 2 with "No such command 'init'".

- [ ] **Step 3: Write the minimal implementation**

Add an `init` command. `--root` overrides discovery; the layout comes from
`_layout_or_exit()` (which honours a recorded `layout:` block); `cache_dir` comes
from `_cache_root(config)` so the gitignore entry matches the runtime cache.
Report paths through `layout.rel(...)` so the JSON is repo-relative and stable
across machines. Exit 0 always on success; the only failure mode is an invalid
config, which `_layout_or_exit` already maps to exit 1.

Docstring must document `:param root:`, `:param thesis:`, `:param dry_run:` and
`:raises typer.Exit:`, and state that existing files are never overwritten.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd defendable-science && uv run pytest tests/test_cli_commands.py -v && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/cli.py tests/test_cli_commands.py
git commit -m "feat(cli): add \`defendable-science init\`"
```

### Task 11: The end-to-end acceptance smoke

This is the regression guard for the exact failure both issues quote. It is its
own task because it is the deliverable a reviewer checks first.

**Files:**
- Test: `defendable-science/tests/test_init_repo.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_init_repo.py
import json

from typer.testing import CliRunner

from defendable_science.cli import app

runner = CliRunner()


def test_a_fresh_scaffold_survives_the_whole_backlog_flow(
    tmp_path: Path, monkeypatch: object
) -> None:
    """#120/#121: on a scaffold from prose, `park` failed on the column profile.

    Every invocation below deliberately passes NO path options: the layout
    resolves them. That is what makes a fresh repo usable without the author
    knowing where anything lives.
    """
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    assert runner.invoke(app, ["init"]).exit_code == 0

    parked = runner.invoke(
        app,
        ["backlog", "park", "Depth collapse explains the OOD gap",
         "--provenance", "smoke", "--level", "paper"],
    )
    assert parked.exit_code == 0, parked.stdout
    paper_id = json.loads(parked.stdout)["id"]

    ranked = runner.invoke(
        app, ["backlog", "rank", paper_id, "--level", "paper", "--feas", "3"]
    )
    assert ranked.exit_code == 0, ranked.stdout

    promoted = runner.invoke(
        app,
        ["backlog", "promote", paper_id, "--level", "paper", "--scaffold",
         "--backend", "bench"],
    )
    assert promoted.exit_code == 0, promoted.stdout

    registry = (tmp_path / "docs" / "research" / "papers.md").read_text(
        encoding="utf-8"
    )
    assert paper_id in registry

    hypothesis_backlog = tmp_path / "docs" / "research" / paper_id / "backlog.md"
    parked_h = runner.invoke(
        app,
        ["backlog", "park", "Monotone depth drives it", "--provenance", "smoke",
         "--backlog", str(hypothesis_backlog)],
    )
    assert parked_h.exit_code == 0, parked_h.stdout

    validated = runner.invoke(app, ["dataset", "validate", "datasets.yml"])
    assert validated.exit_code == 0, validated.stdout
    assert json.loads(validated.stdout)["ok"] is True
```

Match `rank`'s real score-flag names from `cli.py:1339` before running, and
`dataset validate`'s real argument shape from `cli.py:855`.

- [ ] **Step 2: Run it to verify it fails, then passes**

Run: `cd defendable-science && uv run pytest tests/test_init_repo.py -k whole_backlog_flow -v`
Expected: FAIL before Tasks 7-10 land; PASS after. If it fails after, the bug is
real — fix the renderer or the resolver, never the assertion.

- [ ] **Step 3: Commit**

```bash
cd defendable-science
git add tests/test_init_repo.py
git commit -m "test: a fresh scaffold survives park/promote/validate end to end"
```

### Task 12: Plugin-side documentation and the PR

**Files:**
- Modify: `skills/research-init/SKILL.md:47-100` (`§ What it scaffolds`) and `§ Adopt: backfill workflow`
- Modify: `resources/templates/README.md` (`§ What produces what`, the intro, `§ Status-frontmatter convention`)
- Modify: `resources/ensure-tooling.md:25,63,66`

- [ ] **Step 1: Rewrite `§ What it scaffolds`**

Keep the layout tree as orientation. Delete every implied schema — the inline
comments describing columns and file contents. Replace the prose-driven
scaffolding with the actual call, after the `ensure-tooling` bootstrap:

```markdown
Both modes scaffold the layout by **calling the CLI**, not by writing files:

    defendable-science init            # add --thesis for a thesis-by-publication repo

`init` is idempotent and non-destructive: existing files are reported and left
alone. It renders every machine-read file — `papers.md`, both backlog tables,
`references.json`, `triage.yml`, `datasets.yml`, `config.yml`,
`rclone.conf.example`, `dashboard.md` — from the package that owns their shapes,
so two `init` runs agree and the files parse for every command that reads them.
Staged documents (the prose the author fills) come from
[`resources/templates/`](../../resources/templates/).
```

Name `experiment_backend:` explicitly in the bindings paragraph — it is currently
described only in prose, so the key name appears nowhere in the repo.

- [ ] **Step 2: Document the `layout:` block in `§ Adopt`**

Add the propose/confirm path: when inventory finds papers, references or datasets
outside the default tree, the skill *proposes* a `layout:` block for
`.defendable-science/config.yml` and the author confirms it, as an alternative to
relocating files. List the four keys. State that relocating files remains
available as the author's choice — it stops being the only option. Then correct
`§ Modes`, which currently says both modes "leave the repo in the identical
target layout"; that is no longer true and is exactly the sentence #122 quotes.

- [ ] **Step 3: Update the templates README**

- Intro: state that `resources/templates/` holds the **prose skeletons only**, and
  that machine-read files are rendered by `defendable-science init` because the
  package owns their columns and validators.
- `§ What produces what`: add a row per machine-read file with *Produced by* =
  `defendable-science init`.
- `§ Status-frontmatter convention`: keep the documented field set (it is the
  human-facing reference) and add a line naming
  `defendable_science/scaffold/status.py` as the definition it mirrors, with the
  drift guard in `tests/test_status.py` as the enforcement. Update the example
  block so no field carries a `<...>` placeholder, matching Task 4.

- [ ] **Step 4: Bump the tooling pin**

Read `CHANGELOG.md` and `defendable-science/pyproject.toml:7` to find whether
`0.3.0` has shipped. `init` must be covered by the lower bound in
`resources/ensure-tooling.md:25` and the rationale at `:63-66`. If 0.3.0 is
unreleased, the existing `>=0.3.0,<0.4.0` already covers it — say so in the
rationale rather than leaving the reader to infer it. If it has shipped, bump to
the next minor and note `init` as the reason the lower bound moved.

- [ ] **Step 5: Run every gate**

```bash
cd defendable-science && uv run pytest -q && uv run mypy && uv run ruff check && cd ..
pre-commit run --all-files
./tools/validate-plugin.sh
```

- [ ] **Step 6: Commit and open the PR**

```bash
git add skills/research-init/SKILL.md resources/
git commit -m "docs(skills): scaffold via \`defendable-science init\`, not from prose"
```

Then use the `create-pr` skill; the body closes #120 and must note that the nine
templates' frontmatter changed (`<...>` → `null`) and that `experiment_backend:`
is a newly-named config key.

---

# PR3 — `defendable-science check` (closes #121 core)

Branch: `feat/check-command`, off `main` after PR2 lands.

### Task 13: The finding model and the filesystem seam

**Files:**
- Create: `defendable-science/defendable_science/check/__init__.py`
- Create: `defendable-science/defendable_science/check/model.py`
- Create: `defendable-science/defendable_science/check/probe.py`
- Test: `defendable-science/tests/test_check.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Severity = Literal["invalid", "unreadable", "gap"]`; `Finding` frozen dataclass with fields `severity: Severity`, `check: str`, `file: str`, `message: str`, `remedy: str`; `Report` dataclass with `findings: list[Finding]`, properties `ok: bool` / `exit_code: int` / `counts: dict[str, int]`, method `to_json() -> dict[str, Any]`; `Probe` Protocol with `exists(path) -> bool`, `read_text(path) -> str`, `glob(root, pattern) -> list[Path]`; `FsProbe`; `FakeProbe` lives in the test module, not in the package.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check.py
"""The repo-wide checker (#121)."""

from __future__ import annotations

from pathlib import Path

import pytest

from defendable_science.check import model as m
from defendable_science.check.probe import FsProbe


def _finding(severity: str) -> m.Finding:
    return m.Finding(
        severity=severity,  # type: ignore[arg-type]
        check="tables",
        file="docs/research/papers.md",
        message="something is wrong",
        remedy="run `defendable-science init`",
    )


def test_a_clean_report_is_ok_and_exits_zero() -> None:
    report = m.Report(findings=[])

    assert report.ok is True
    assert report.exit_code == 0
    assert report.counts == {"invalid": 0, "unreadable": 0, "gap": 0}


def test_gaps_alone_do_not_fail_the_run() -> None:
    report = m.Report(findings=[_finding("gap")])

    assert report.ok is True
    assert report.exit_code == 0
    assert report.counts["gap"] == 1


@pytest.mark.parametrize("severity", ["invalid", "unreadable"])
def test_invalid_and_unreadable_both_fail_the_run(severity: str) -> None:
    report = m.Report(findings=[_finding(severity)])

    assert report.ok is False
    assert report.exit_code == 1


def test_to_json_is_shaped_like_the_other_commands() -> None:
    payload = m.Report(findings=[_finding("invalid")]).to_json()

    assert payload["ok"] is False
    assert payload["counts"]["invalid"] == 1
    assert payload["findings"] == [
        {
            "severity": "invalid",
            "check": "tables",
            "file": "docs/research/papers.md",
            "message": "something is wrong",
            "remedy": "run `defendable-science init`",
        }
    ]


def test_fs_probe_reads_globs_and_reports_existence(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.md").write_text("hello", encoding="utf-8")
    probe = FsProbe()

    assert probe.exists(tmp_path / "a" / "x.md") is True
    assert probe.exists(tmp_path / "a" / "nope.md") is False
    assert probe.read_text(tmp_path / "a" / "x.md") == "hello"
    assert probe.glob(tmp_path, "**/*.md") == [tmp_path / "a" / "x.md"]


def test_fs_probe_globs_nothing_under_a_missing_root(tmp_path: Path) -> None:
    assert FsProbe().glob(tmp_path / "absent", "**/*.md") == []


def test_fs_probe_read_text_raises_oserror_for_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        FsProbe().read_text(tmp_path / "absent.md")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_check.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'defendable_science.check'`

- [ ] **Step 3: Write the minimal implementation**

`model.py` — `Report.counts` returns all three keys always (a missing key would
read as "no such severity" rather than "none found"); `exit_code` is
`0 if self.ok else 1`; `ok` is `not (invalid or unreadable)`.

`probe.py`:

```python
class Probe(Protocol):
    """The filesystem seam. Every check reads through this, so error and
    degradation branches are unit-testable without building a fixture repo."""

    def exists(self, path: Path) -> bool: ...
    def read_text(self, path: Path) -> str: ...
    def glob(self, root: Path, pattern: str) -> list[Path]: ...


class FsProbe:
    """The real filesystem."""

    def exists(self, path: Path) -> bool:
        """Return whether `path` exists."""
        return path.exists()

    def read_text(self, path: Path) -> str:
        """Read `path` as UTF-8.

        :raises OSError: If it cannot be read. Callers turn this into an
            ``unreadable`` finding — never into "valid and empty".
        """
        return path.read_text(encoding="utf-8")

    def glob(self, root: Path, pattern: str) -> list[Path]:
        """Return sorted matches of `pattern` under `root` (empty if absent)."""
        if not root.is_dir():
            return []
        return sorted(root.glob(pattern))
```

A binary file makes `read_text` raise `UnicodeDecodeError`, which is an
`OSError`? It is **not** — `UnicodeDecodeError` subclasses `ValueError`. Catch
`(OSError, UnicodeDecodeError)` at every call site, or re-raise as `OSError` in
`FsProbe.read_text`. Choose the re-raise so each check has one `except OSError`
branch, and cover it with a test that writes `b"\xff\xfe\x00"` to a `.md` file.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd defendable-science && uv run pytest tests/test_check.py -v --cov=defendable_science.check --cov-report=term-missing --no-cov-on-fail`
Expected: PASS at 100%.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/check/ tests/test_check.py
git commit -m "feat(check): add the finding model and the filesystem seam"
```

### Task 14: Layout and table checks

**Files:**
- Create: `defendable-science/defendable_science/check/checks.py`
- Test: `defendable-science/tests/test_check.py`

**Interfaces:**
- Consumes: `Finding`, `Probe` (Task 13); `Layout` (Task 1); `Backlog.loads`, `BacklogError`, `REGISTRY_COLUMNS`, `columns_for` from `exploration.backlog`.
- Produces: `check_layout(layout, probe) -> list[Finding]`; `check_tables(layout, probe) -> list[Finding]`; `registry_rows(layout, probe) -> tuple[list[dict[str, str]], list[Finding]]`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_check.py
from defendable_science.check import checks as c
from defendable_science.exploration import backlog as b
from defendable_science.scaffold import render as r
from defendable_science.scaffold.layout import Layout


class FakeProbe:
    """A filesystem built from a ``{path: text}`` map. Directories are implied."""

    def __init__(self, files: dict[Path, str], unreadable: set[Path] | None = None):
        self.files = files
        self.unreadable = unreadable or set()

    def exists(self, path: Path) -> bool:
        return path in self.files or any(
            path in p.parents for p in self.files
        )

    def read_text(self, path: Path) -> str:
        if path in self.unreadable:
            raise OSError(f"{path}: simulated read failure")
        if path not in self.files:
            raise OSError(f"{path}: no such file")
        return self.files[path]

    def glob(self, root: Path, pattern: str) -> list[Path]:
        suffix = pattern.rsplit("/", 1)[-1].replace("*", "")
        return sorted(
            p for p in self.files
            if root in p.parents and p.name.endswith(suffix)
        )


ROOT = Path("/repo")
LAYOUT = Layout.default(ROOT)


def _scaffolded() -> dict[Path, str]:
    """The file map a clean `init` produces (the regression baseline)."""
    return {
        LAYOUT.papers_registry: r.render_papers_registry(),
        LAYOUT.portfolio_backlog: r.render_portfolio_backlog(),
        LAYOUT.dashboard: r.render_dashboard(),
        LAYOUT.references: r.render_references(),
        LAYOUT.triage: r.render_triage(),
        LAYOUT.datasets_manifest: r.render_datasets_manifest(),
        LAYOUT.config_file: r.render_config(),
        ROOT / ".gitignore": "\n".join(
            r.gitignore_entries(r.DEFAULT_CACHE_DIR)
        ) + "\n",
    }


def test_layout_check_is_silent_on_a_scaffolded_repo() -> None:
    assert c.check_layout(LAYOUT, FakeProbe(_scaffolded())) == []


def test_layout_check_names_each_missing_required_file() -> None:
    files = _scaffolded()
    del files[LAYOUT.papers_registry]

    findings = c.check_layout(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert findings[0].file == "docs/research/papers.md"
    assert "defendable-science init" in findings[0].remedy


def test_layout_check_does_not_require_a_thesis_tree() -> None:
    """Thesis-ness is a fact on disk; a portfolio repo is complete without one."""
    files = _scaffolded()
    del files[LAYOUT.papers_registry]  # one real finding, so the test is not vacuous

    findings = c.check_layout(LAYOUT, FakeProbe(files))

    assert [f.file for f in findings] == ["docs/research/papers.md"]
    assert not any("thesis" in f.file for f in findings)


def test_layout_check_requires_aims_once_a_thesis_dir_exists() -> None:
    files = _scaffolded()
    files[LAYOUT.thesis_dir / "kappa" / "kappa.md"] = "---\nstatus:\n  level: thesis\n---\n"

    findings = c.check_layout(LAYOUT, FakeProbe(files))

    assert any(f.file == "docs/research/thesis/aims.md" for f in findings)


def test_tables_check_is_silent_on_a_scaffolded_repo() -> None:
    assert c.check_tables(LAYOUT, FakeProbe(_scaffolded())) == []


def test_tables_check_flags_the_header_that_broke_park() -> None:
    """The exact malformed header quoted in #120 and #121."""
    files = _scaffolded()
    files[LAYOUT.portfolio_backlog] = (
        "| id | status | idea | rationale | ranked | promoted-to |\n"
        "|---|---|---|---|---|---|\n"
    )

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "one-line" in findings[0].message
    assert "provenance" in findings[0].message
    assert findings[0].file == "docs/research/portfolio-backlog.md"


def test_tables_check_flags_an_invented_registry_column() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = (
        "| paper-id | root | backend | state |\n|---|---|---|---|\n"
    )

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert any("state" in f.message for f in findings)


def test_tables_check_flags_a_missing_registry_column() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = "| paper-id | root |\n|---|---|\n"

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert any("backend" in f.message and f.severity == "invalid" for f in findings)


def test_tables_check_flags_a_registry_row_whose_root_is_missing() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = (
        "| paper-id | root | backend |\n|---|---|---|\n"
        "| dc | docs/research/dc | bench |\n"
    )

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert any(
        "docs/research/dc" in f.message and f.severity == "invalid" for f in findings
    )


def test_tables_check_flags_a_registry_row_with_an_empty_backend() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = (
        "| paper-id | root | backend |\n|---|---|---|\n"
        "| dc | docs/research/dc |  |\n"
    )
    files[LAYOUT.paper_dir("dc") / "backlog.md"] = r.render_paper_backlog()

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert any("backend" in f.message and "dc" in f.message for f in findings)


def test_tables_check_reads_each_registered_papers_backlog() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = (
        "| paper-id | root | backend |\n|---|---|---|\n"
        "| dc | docs/research/dc | bench |\n"
    )
    files[LAYOUT.paper_dir("dc") / "backlog.md"] = "| id | note |\n|---|---|\n"

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert any(f.file == "docs/research/dc/backlog.md" for f in findings)


def test_tables_check_reports_unreadable_separately_from_empty() -> None:
    files = _scaffolded()
    probe = FakeProbe(files, unreadable={LAYOUT.papers_registry})

    findings = c.check_tables(LAYOUT, probe)

    assert [f.severity for f in findings] == ["unreadable"]
    assert "could not read" in findings[0].message
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_check.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'defendable_science.check.checks'`

- [ ] **Step 3: Write the minimal implementation**

Write `checks.py` with a shared reader helper so the `unreadable` branch exists
once:

```python
def _read(
    path: Path, layout: Layout, probe: Probe, check: str
) -> tuple[str | None, Finding | None]:
    """Read `path`, or return the ``unreadable`` finding describing why.

    Never conflates a read failure with an empty file: "0 references" and
    "could not read references.json" are different facts, and only one of them
    means the repo is fine.
    """
```

`check_layout` iterates a required-set built from the layout — `papers_registry`,
`portfolio_backlog`, `dashboard`, `references`, `triage`, `datasets_manifest`,
`config_file` — and adds `aims` / `milestones` only when
`probe.exists(layout.thesis_dir)`. `check_tables` parses the two registries and
every registered paper's backlog via `Backlog.loads`, converting `BacklogError`
into an `invalid` finding whose message is the exception text (it already names
the missing columns and both profiles) and whose remedy points at the correct
profile. Registry columns beyond `REGISTRY_COLUMNS` are `invalid`, naming the
extra column — the invented `state` column is why `promote --scaffold` could not
register.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd defendable-science && uv run pytest tests/test_check.py -v --cov=defendable_science.check --cov-report=term-missing --no-cov-on-fail`
Expected: PASS at 100%.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/check/checks.py tests/test_check.py
git commit -m "feat(check): validate the layout and every backlog/registry table"
```

### Task 15: Frontmatter checks

**Files:**
- Modify: `defendable-science/defendable_science/check/checks.py`
- Test: `defendable-science/tests/test_check.py`

**Interfaces:**
- Consumes: `status.parse`, `status.VERDICTS`, `status.READINESS`, `status.FIELD_ORDER`, `status.StatusError`, `layout.STAGED_DOCUMENTS`.
- Produces: `check_frontmatter(layout, probe) -> list[Finding]`; `staged_documents(layout, probe) -> list[Path]`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_check.py
from defendable_science.scaffold import status as st


def _doc(level: str, **fields: str) -> str:
    return "---\n" + st.render(level, fields) + "---\n\n# Doc\n"


PITCH = LAYOUT.paper_docs_dir("dc") / "pitch.md"


def test_frontmatter_check_is_silent_on_a_valid_document() -> None:
    files = _scaffolded()
    files[PITCH] = _doc("paper", id="dc", **{"last-updated": "2026-03-04"})

    assert c.check_frontmatter(LAYOUT, FakeProbe(files)) == []


def test_frontmatter_check_flags_a_missing_status_block() -> None:
    files = _scaffolded()
    files[PITCH] = "# Pitch\n\nno frontmatter\n"

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "status:" in findings[0].message
    assert findings[0].file == "docs/research/dc/paper/pitch.md"


def test_frontmatter_check_flags_an_out_of_enum_verdict() -> None:
    files = _scaffolded()
    files[PITCH] = _doc("paper", id="dc", verdict="maybe")

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    assert any("verdict" in f.message and "maybe" in f.message for f in findings)
    assert all(f.severity == "invalid" for f in findings)


def test_frontmatter_check_flags_an_out_of_enum_readiness() -> None:
    files = _scaffolded()
    files[PITCH] = _doc("paper", id="dc", readiness="nearly")

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    assert any("readiness" in f.message and "nearly" in f.message for f in findings)


def test_frontmatter_check_flags_an_unreplaced_placeholder() -> None:
    """`readiness: <synthesis | defensible>` parses as a real value (#121)."""
    files = _scaffolded()
    kappa = LAYOUT.kappa_dir / "kappa.md"
    files[kappa] = (
        "---\nstatus:\n  level: thesis\n  id: t\n"
        "  readiness: <synthesis | defensible>\n---\n\n# Kappa\n"
    )

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    placeholder = [f for f in findings if "placeholder" in f.message]
    assert len(placeholder) == 1
    assert placeholder[0].severity == "invalid"
    assert "readiness" in placeholder[0].message
    assert "null" in placeholder[0].remedy


def test_frontmatter_check_flags_a_level_that_contradicts_the_filename() -> None:
    files = _scaffolded()
    files[PITCH] = _doc("hypothesis", id="dc")

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    assert any("level" in f.message for f in findings)


def test_frontmatter_check_flags_an_unknown_status_field() -> None:
    files = _scaffolded()
    files[PITCH] = "---\nstatus:\n  level: paper\n  priority: high\n---\n"

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    assert any("priority" in f.message for f in findings)


def test_frontmatter_check_reports_invalid_yaml_without_a_traceback() -> None:
    files = _scaffolded()
    files[PITCH] = "---\nstatus: [unclosed\n---\n"

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "invalid YAML" in findings[0].message


def test_frontmatter_check_reports_an_unreadable_document() -> None:
    files = _scaffolded()
    files[PITCH] = _doc("paper", id="dc")
    probe = FakeProbe(files, unreadable={PITCH})

    findings = c.check_frontmatter(LAYOUT, probe)

    assert [f.severity for f in findings] == ["unreadable"]


def test_frontmatter_check_ignores_a_file_that_is_not_a_staged_document() -> None:
    files = _scaffolded()
    files[LAYOUT.paper_dir("dc") / "notes.md"] = "# scratch notes, no frontmatter\n"

    assert c.check_frontmatter(LAYOUT, FakeProbe(files)) == []


def test_frontmatter_check_never_flags_a_refuted_hypothesis() -> None:
    """`refuted` is successful science, not a failure (meta-spec §2.1)."""
    files = _scaffolded()
    findings_path = LAYOUT.hypothesis_dir("dc", "2026-03-04-x") / "findings.md"
    files[findings_path] = _doc(
        "hypothesis",
        id="2026-03-04-x",
        verdict="refuted",
        readiness="resolved",
        **{"signed-off-by": "D. Runje", "signed-off-date": "2026-03-04"},
    )

    assert c.check_frontmatter(LAYOUT, FakeProbe(files)) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_check.py -k frontmatter -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'check_frontmatter'`

- [ ] **Step 3: Write the minimal implementation**

`staged_documents` globs `layout.research_root` for `**/*.md` and keeps basenames
in `STAGED_DOCUMENTS` (the thesis tree lives under `research_root` by default; if
`thesis_dir` is elsewhere, glob it too and de-duplicate). `check_frontmatter`
then, per document:

1. read (→ `unreadable`), 2. `status.parse` (`StatusError` → `invalid` naming the
YAML error; `None` → `invalid` "no `status:` block"), 3. unknown fields → `invalid`,
4. **placeholder scan**: any value that `isinstance(value, str)` and
`value.startswith("<")` → `invalid`, message naming the field and the literal
value, remedy "set it to `null` until it is real, and keep the guidance in a
comment", 5. `level` must match `STAGED_DOCUMENTS[filename]`, 6. `verdict` must be
in `VERDICTS[level]` or `None`; `readiness` must be in `READINESS[level]` or
`None`.

Nothing here inspects *which* verdict: `refuted` and `no-go` pass exactly as
`confirmed` and `publish` do.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd defendable-science && uv run pytest tests/test_check.py -v --cov=defendable_science.check --cov-report=term-missing --no-cov-on-fail`
Expected: PASS at 100%.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/check/checks.py tests/test_check.py
git commit -m "feat(check): validate status frontmatter, enums and placeholders"
```

### Task 16: Registry checks

**Files:**
- Modify: `defendable-science/defendable_science/literature/registry.py:463` (make `_triage_mapping` public)
- Modify: `defendable-science/defendable_science/check/checks.py`
- Test: `defendable-science/tests/test_check.py`, `defendable-science/tests/test_lit_registry.py`

**Interfaces:**
- Consumes: `load_registry`, `load_triage`, `RegistryError`, the new `triage_mapping`; `manifest.load`, `manifest.validate`, `ManifestError`.
- Produces: `registry.triage_mapping(target: Path, text: str) -> dict[Any, Any]` (public); `check_registries(layout, probe) -> list[Finding]`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_check.py
def test_registries_check_is_silent_on_a_scaffolded_repo() -> None:
    assert c.check_registries(LAYOUT, FakeProbe(_scaffolded())) == []


def test_registries_check_flags_invalid_csl_json() -> None:
    files = _scaffolded()
    files[LAYOUT.references] = '{"id": "smith2020"}\n'  # object, not an array

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert findings[0].file == "docs/research/literature/references.json"


def test_registries_check_flags_an_entry_without_an_id() -> None:
    files = _scaffolded()
    files[LAYOUT.references] = '[{"title": "no id here"}]\n'

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert any("id" in f.message for f in findings)


def test_registries_check_flags_a_triage_key_with_no_reference() -> None:
    files = _scaffolded()
    files[LAYOUT.references] = '[{"id": "smith2020"}]\n'
    files[LAYOUT.triage] = "jones2019:\n  disposition: include\n"

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert any("jones2019" in f.message and f.severity == "invalid" for f in findings)


def test_registries_check_flags_a_triage_row_that_is_not_a_mapping() -> None:
    """`load_triage` silently skips these, so nothing else would ever see it."""
    files = _scaffolded()
    files[LAYOUT.references] = '[{"id": "smith2020"}]\n'
    files[LAYOUT.triage] = "smith2020: include\n"

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert any("smith2020" in f.message and "mapping" in f.message for f in findings)


def test_registries_check_flags_invalid_triage_yaml() -> None:
    files = _scaffolded()
    files[LAYOUT.triage] = "smith2020: [unclosed\n"

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert any("invalid YAML" in f.message for f in findings)


def test_registries_check_reports_every_manifest_error() -> None:
    files = _scaffolded()
    files[LAYOUT.datasets_manifest] = (
        "datasets:\n  - id: cifar10\n    files: []\n"
    )

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    messages = " ".join(f.message for f in findings)
    assert "version" in messages
    assert "license" in messages
    assert all(f.file == "datasets.yml" for f in findings if "entry" in f.message)


def test_registries_check_flags_an_unparseable_manifest() -> None:
    files = _scaffolded()
    files[LAYOUT.datasets_manifest] = "- not: a mapping\n"

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert any(f.severity == "invalid" and f.file == "datasets.yml" for f in findings)


def test_registries_check_reports_each_unreadable_registry() -> None:
    probe = FakeProbe(_scaffolded(), unreadable={LAYOUT.references, LAYOUT.triage})

    findings = c.check_registries(LAYOUT, probe)

    assert sorted(f.file for f in findings if f.severity == "unreadable") == [
        "docs/research/literature/references.json",
        "docs/research/literature/triage.yml",
    ]
```

```python
# append to tests/test_lit_registry.py
def test_triage_mapping_is_public_and_returns_the_raw_rows() -> None:
    assert reg.triage_mapping(Path("triage.yml"), "a: include\nb: {x: 1}\n") == {
        "a": "include",
        "b": {"x": 1},
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_check.py -k registries tests/test_lit_registry.py -k triage_mapping -v`
Expected: FAIL — no `check_registries`, no public `triage_mapping`.

- [ ] **Step 3: Write the minimal implementation**

Rename `_triage_mapping` → `triage_mapping` in `registry.py` (update its two
internal call sites at `:505` and `:575`), and give it a public MyST docstring.
It has to be public because `load_triage` *skips* a row that is not a mapping —
correct for a reader, but it means a malformed row is invisible to every consumer,
and `check` is the one caller that must see what a reader would skip.

`check_registries` reads each of the three registries through `_read`, then:
`load_registry` / `RegistryError` → `invalid`; `triage_mapping` for the raw rows
(non-mapping row → `invalid`) plus a key-set difference against the registry ids
→ `invalid` per orphan key; `manifest.load` → `ManifestError` → `invalid`, then
`manifest.validate` with one `invalid` per `report.errors` entry and one `gap` per
`report.warnings` entry (a warning is a soft issue by that module's own
definition, so it must not fail the run).

The loaders take paths, not text. Feed them via a `tmp`-free seam: parse the text
directly where the module exposes a text-level function (`triage_mapping`), and
for `load_registry` / `manifest.load` call them with the real path and let the
`Probe` decide readability first, so a `FakeProbe` test still exercises the
error branches by supplying malformed *text* through a `tmp_path`-backed file.
Simplest consistent choice: give `checks.py` a small `_parse_json`/`_parse_yaml`
pair mirroring the loaders' validation, and assert in `tests/test_render.py`
(Task 8) that the real loaders accept what `init` renders — which is already
done. Prefer reusing the real loaders where they accept text; do not duplicate
validation rules that the loaders own.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd defendable-science && uv run pytest -q --cov=defendable_science.check --cov-report=term-missing --no-cov-on-fail`
Expected: PASS at 100%.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/ tests/
git commit -m "feat(check): validate references, triage and the dataset manifest"
```

### Task 17: Config checks

**Files:**
- Modify: `defendable-science/defendable_science/check/checks.py`
- Test: `defendable-science/tests/test_check.py`

**Interfaces:**
- Consumes: `load_config`, `resolve_layout`, `LayoutError`, `render.gitignore_entries`.
- Produces: `check_config(layout, probe) -> list[Finding]`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_check.py
def test_config_check_is_silent_on_a_scaffolded_repo_with_a_bound_backend() -> None:
    assert c.check_config(LAYOUT, FakeProbe(_scaffolded_with_backend("bench"))) == []


def test_config_check_flags_unparseable_yaml_without_a_traceback() -> None:
    files = _scaffolded()
    files[LAYOUT.config_file] = "cache_dir: [unclosed\n"

    findings = c.check_config(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "invalid YAML" in findings[0].message
    assert "Traceback" not in findings[0].message


def test_config_check_flags_a_non_mapping_config() -> None:
    files = _scaffolded()
    files[LAYOUT.config_file] = "- a\n- b\n"

    findings = c.check_config(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]


def test_config_check_flags_an_unknown_layout_key() -> None:
    files = _scaffolded()
    files[LAYOUT.config_file] = "layout:\n  papers_dir: x/\n"

    findings = c.check_config(LAYOUT, FakeProbe(files))

    assert any("papers_dir" in f.message and f.severity == "invalid" for f in findings)


def test_config_check_flags_a_cache_dir_that_is_not_gitignored() -> None:
    files = _scaffolded()
    files[ROOT / ".gitignore"] = "__pycache__/\n"

    findings = c.check_config(LAYOUT, FakeProbe(files))

    assert any(
        ".defendable-science/cache/" in f.message and f.severity == "invalid"
        for f in findings
    )
    assert any(".gitignore" in f.remedy for f in findings)


def test_config_check_flags_a_missing_gitignore() -> None:
    files = _scaffolded()
    del files[ROOT / ".gitignore"]

    findings = c.check_config(LAYOUT, FakeProbe(files))

    assert any(f.file == ".gitignore" for f in findings)


def test_config_check_surfaces_a_null_experiment_backend_as_a_gap() -> None:
    """A repo that cannot produce run-refs is incomplete, not invalid."""
    findings = c.check_config(LAYOUT, FakeProbe(_scaffolded_with_backend(None)))

    backend = [f for f in findings if "experiment_backend" in f.message]
    assert [f.severity for f in backend] == ["gap"]


def test_config_check_is_silent_once_a_backend_is_bound() -> None:
    findings = c.check_config(LAYOUT, FakeProbe(_scaffolded_with_backend("bench")))

    assert [f for f in findings if "experiment_backend" in f.message] == []


def test_config_check_reports_an_unreadable_config() -> None:
    probe = FakeProbe(_scaffolded(), unreadable={LAYOUT.config_file})

    findings = c.check_config(LAYOUT, probe)

    assert [f.severity for f in findings] == ["unreadable"]
```

Add the helper the two backend tests use:

```python
def _scaffolded_with_backend(backend: str | None) -> dict[Path, str]:
    files = _scaffolded()
    value = "null" if backend is None else backend
    files[LAYOUT.config_file] = (
        f"cache_dir: {r.DEFAULT_CACHE_DIR}\nexperiment_backend: {value}\n"
    )
    return files
```

Note `_scaffolded()` renders a config whose `experiment_backend` is `null`, so
`test_config_check_is_silent_on_a_scaffolded_repo` must expect the backend
**gap** — either assert `all(f.severity == "gap" for f in findings)` there, or
have that test bind a backend. Pick the second: keep "silent" meaning literally
no findings, and let the gap tests own that behaviour.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_check.py -k config -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'check_config'`

- [ ] **Step 3: Write the minimal implementation**

`check_config` reads the config text, parses it with the same YAML rules
`load_config` enforces (invalid YAML / non-mapping → `invalid`), runs
`resolve_layout` to surface `LayoutError` as `invalid`, resolves `cache_dir` the
way `_cache_root` does, and checks it appears in `.gitignore` (missing file or
missing entry → `invalid`, remedy quoting the exact line to add). A null or absent
`experiment_backend` is a `gap` whose message says the repo cannot produce the
run-refs `evidence:` requires.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd defendable-science && uv run pytest tests/test_check.py -v --cov=defendable_science.check --cov-report=term-missing --no-cov-on-fail`
Expected: PASS at 100%.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/check/checks.py tests/test_check.py
git commit -m "feat(check): validate config.yml, the layout block and the gitignore"
```

### Task 18: Cross-artifact gaps and the stale dashboard

**Files:**
- Modify: `defendable-science/defendable_science/check/checks.py`
- Test: `defendable-science/tests/test_check.py`

**Interfaces:**
- Consumes: `staged_documents`, `status.parse` (Task 15).
- Produces: `check_cross_artifact(layout, probe) -> list[Finding]`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_check.py
def test_an_unsigned_verdict_is_a_gap_not_a_failure() -> None:
    files = _scaffolded()
    decision = LAYOUT.paper_docs_dir("dc") / "decision.md"
    files[decision] = _doc("paper", id="dc", verdict="publish")

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    signed = [f for f in findings if "signed-off-by" in f.message]
    assert [f.severity for f in signed] == ["gap"]
    assert "not yet decided" in signed[0].message


def test_a_no_go_verdict_is_never_reported_as_a_problem() -> None:
    files = _scaffolded()
    decision = LAYOUT.paper_docs_dir("dc") / "decision.md"
    files[decision] = _doc(
        "paper",
        id="dc",
        verdict="no-go",
        **{"signed-off-by": "D. Runje", "signed-off-date": "2026-03-04"},
    )

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    assert [f for f in findings if "no-go" in f.message] == []


def test_empty_evidence_on_a_resolved_artifact_is_a_gap() -> None:
    files = _scaffolded()
    path = LAYOUT.hypothesis_dir("dc", "2026-03-04-x") / "findings.md"
    files[path] = _doc(
        "hypothesis",
        id="2026-03-04-x",
        verdict="confirmed",
        readiness="resolved",
        **{"signed-off-by": "D. Runje", "signed-off-date": "2026-03-04"},
    )

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    evidence = [f for f in findings if "evidence" in f.message]
    assert [f.severity for f in evidence] == ["gap"]


def test_a_covers_entry_with_no_such_aim_is_a_gap() -> None:
    files = _scaffolded()
    files[LAYOUT.aims] = _doc("thesis", id="t", readiness="framing") + (
        "\n## Aims\n\n- **aim-1** — the first aim\n"
    )
    files[PITCH] = "---\nstatus:\n  level: paper\n  id: dc\n  covers: [aim-2]\n---\n"

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    covers = [f for f in findings if "aim-2" in f.message]
    assert [f.severity for f in covers] == ["gap"]


def test_covers_is_not_checked_when_the_repo_has_no_thesis() -> None:
    files = _scaffolded()
    files[PITCH] = "---\nstatus:\n  level: paper\n  id: dc\n  covers: [aim-2]\n---\n"

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    assert [f for f in findings if "aim-2" in f.message] == []


def test_a_dashboard_missing_a_live_artifact_is_a_gap() -> None:
    files = _scaffolded()
    files[PITCH] = _doc("paper", id="dc")

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    stale = [f for f in findings if f.file == "docs/research/dashboard.md"]
    assert [f.severity for f in stale] == ["gap"]
    assert "dc" in stale[0].message
    assert "progress" in stale[0].remedy


def test_a_dashboard_naming_an_artifact_that_is_gone_is_a_gap() -> None:
    files = _scaffolded()
    files[LAYOUT.dashboard] = "# Research dashboard\n\n- paper `ghost` — drafting\n"

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    assert any("ghost" in f.message for f in findings)


def test_the_ungenerated_dashboard_stub_is_not_stale_on_an_empty_repo() -> None:
    assert c.check_cross_artifact(LAYOUT, FakeProbe(_scaffolded())) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_check.py -k cross_artifact -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'check_cross_artifact'`

- [ ] **Step 3: Write the minimal implementation**

Every finding this function emits is a `gap`. Four rules:

1. `verdict` set and `signed-off-by` null → gap, message "verdict … is not yet
   decided: `signed-off-by` is null", remedy naming the sign-off. The verdict's
   *value* is never judged.
2. `readiness` in `{"resolved", "published"}` and `evidence == []` → gap.
3. `covers` entries not declared in `aims.md`, **only when `aims.md` exists**.
   Parse declared aim ids as the `aim-\d+` tokens appearing in `aims.md`; a
   loose match is right here because the gap is advisory and a false negative
   costs less than nagging about a legitimately-formatted aims file.
4. Dashboard id-set comparison: ids from every staged document's `status.id` vs
   ids appearing anywhere in `dashboard.md`. Either direction is a gap. Skip
   entirely when the dashboard is the ungenerated stub (`render_dashboard()`'s
   "Not yet generated" marker) **and** no artifact ids exist — a fresh repo is
   not stale.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd defendable-science && uv run pytest tests/test_check.py -v --cov=defendable_science.check --cov-report=term-missing --no-cov-on-fail`
Expected: PASS at 100%.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/check/checks.py tests/test_check.py
git commit -m "feat(check): surface cross-artifact gaps without failing the run"
```

### Task 19: `run_checks`, the CLI command, and the honesty guarantees

**Files:**
- Modify: `defendable-science/defendable_science/check/checks.py`, `defendable-science/defendable_science/check/__init__.py`
- Modify: `defendable-science/defendable_science/cli.py` (after `init`)
- Test: `defendable-science/tests/test_check_cli.py`

**Interfaces:**
- Consumes: all six check families; `_layout_or_exit` (Task 5); `FsProbe` (Task 13).
- Produces: `run_checks(layout, probe) -> Report`; the `check` command.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_cli.py
"""`defendable-science check` end to end."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from defendable_science.cli import app

runner = CliRunner()


def _init(root: Path) -> None:
    assert runner.invoke(app, ["init", "--root", str(root)]).exit_code == 0


def test_a_freshly_initialized_repo_passes_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression guard for the failure quoted in #120 and #121."""
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)

    result = runner.invoke(app, ["check"])

    payload = json.loads(result.stdout)
    assert payload["counts"]["invalid"] == 0, payload["findings"]
    assert payload["counts"]["unreadable"] == 0, payload["findings"]
    assert result.exit_code == 0, result.stdout


def test_gaps_alone_still_exit_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    pitch = tmp_path / "docs" / "research" / "dc" / "paper"
    pitch.mkdir(parents=True)
    (pitch / "pitch.md").write_text(
        "---\nstatus:\n  level: paper\n  id: dc\n  verdict: publish\n"
        "  signed-off-by: null\n---\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["check"])

    payload = json.loads(result.stdout)
    assert payload["counts"]["gap"] > 0
    assert payload["counts"]["invalid"] == 0
    assert result.exit_code == 0


def test_an_invalid_file_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    (tmp_path / "docs" / "research" / "portfolio-backlog.md").write_text(
        "| id | status | idea |\n|---|---|---|\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["check"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_text_mode_prints_a_human_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)

    result = runner.invoke(app, ["check", "--text"])

    assert result.exit_code == 0
    assert "defendable-science check" in result.stdout
    assert "invalid: 0" in result.stdout


def test_malformed_files_never_produce_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure honesty: never a raw traceback, whatever is on disk."""
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    (tmp_path / "docs" / "research" / "papers.md").write_bytes(b"\xff\xfe\x00\x01")
    (tmp_path / "datasets.yml").write_text("!!python/object:os.system []", encoding="utf-8")
    (tmp_path / "docs" / "research" / "literature" / "references.json").write_text(
        "{not json", encoding="utf-8"
    )

    result = runner.invoke(app, ["check"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    payload = json.loads(result.stdout)
    assert payload["counts"]["invalid"] + payload["counts"]["unreadable"] >= 3
    for finding in payload["findings"]:
        assert finding["remedy"], finding


def test_unreadable_is_distinguishable_from_valid_and_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    references = tmp_path / "docs" / "research" / "literature" / "references.json"
    references.write_bytes(b"\xff\xfe\x00")

    result = runner.invoke(app, ["check"])

    findings = json.loads(result.stdout)["findings"]
    reported = [f for f in findings if f["file"].endswith("references.json")]
    assert reported, findings
    assert reported[0]["severity"] in {"unreadable", "invalid"}
    assert "empty" not in reported[0]["message"].lower()


def test_check_exits_one_on_an_invalid_layout_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _init(tmp_path)
    (tmp_path / ".defendable-science" / "config.yml").write_text(
        "layout:\n  papers_dir: x/\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["check"])

    assert result.exit_code == 1
    assert "unknown layout key" in result.output
    assert "Traceback" not in result.output
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd defendable-science && uv run pytest tests/test_check_cli.py -v`
Expected: FAIL — Typer exits 2 with "No such command 'check'".

- [ ] **Step 3: Write the minimal implementation**

`run_checks` concatenates the six families in a fixed order (layout, tables,
frontmatter, registries, config, cross-artifact) into a `Report`.

The `check` command: `--root PATH` and `--text`. JSON on stdout by default,
matching `dataset validate`; `--text` prints a `doctor`-style block with the three
counts and one line per finding (`severity  file — message`, remedy indented
beneath). `raise typer.Exit(code=report.exit_code)`.

An invalid `layout:` block is fatal for the whole run — the checker cannot know
where anything is — so `_layout_or_exit` handling it as exit 1 with a message is
correct, and the test asserts exactly that path.

- [ ] **Step 4: Run everything**

Run: `cd defendable-science && uv run pytest -q && uv run mypy && uv run ruff check`
Expected: PASS at 100% coverage.

- [ ] **Step 5: Commit**

```bash
cd defendable-science
git add defendable_science/ tests/test_check_cli.py
git commit -m "feat(cli): add \`defendable-science check\`"
```

### Task 20: Open the PR

- [ ] **Step 1: Run every gate**

```bash
cd defendable-science && uv run pytest -q && uv run mypy && uv run ruff check && cd ..
pre-commit run --all-files
./tools/validate-plugin.sh
```

- [ ] **Step 2: Open the PR**

Use the `create-pr` skill. The body closes #121, states plainly that `--fix` is
**deliberately out of scope** and links the follow-up issue from Task 24, and
quotes the `test_a_freshly_initialized_repo_passes_cleanly` result as the
regression evidence.

---

# PR4 — Skill wiring and the layout sweep

Branch: `docs/skills-resolve-layout`, off `main` after PR3 lands.

### Task 21: Wire `research-init` and `progress` to `check`

**Files:**
- Modify: `skills/research-init/SKILL.md` (`§ What it scaffolds`, `§ Composition`)
- Modify: `skills/progress/SKILL.md` (`§ Verbs`, `§ Guardrails`)

- [ ] **Step 1: Add the verification step to `research-init`**

At the end of *both* modes, after scaffolding and after `adopt`'s materialize
loop:

```markdown
Finally, **verify the repo** rather than declaring it working:

    defendable-science check

Report what it finds. `invalid` and `unreadable` findings mean the repo is not
yet usable — fix them before handing back. `gap` findings are honest incomplete
states (an unsigned verdict, no bound experiment backend) and are reported, not
fixed: they are the author's decisions to make.
```

- [ ] **Step 2: Make `progress` check before reporting**

In `§ Verbs`, prepend to both verbs: run `defendable-science check` first. In
`§ Guardrails`, add:

```markdown
- **An unreadable artifact is reported as unreadable, never as absent.** `check`
  distinguishes "failed to read" from "valid and empty"; a dashboard that
  silently drops an artifact it could not parse would be a projection that lies.
  Surface the finding and leave the row visibly unknown.
```

- [ ] **Step 3: Verify the plugin still validates**

Run: `./tools/validate-plugin.sh && pre-commit run --all-files`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add skills/research-init/SKILL.md skills/progress/SKILL.md
git commit -m "docs(skills): verify the repo with \`check\` instead of asserting it"
```

### Task 22: The hard-coded-path sweep and its guard

**Files:**
- Modify: `skills/{digest,hypothesis-exploration,hypothesis-testing,paper-exploration,paper-synthesis,thesis}/SKILL.md`
- Test: `defendable-science/tests/test_plugin_content.py`

- [ ] **Step 1: Write the failing guard test**

```python
# tests/test_plugin_content.py
"""Plugin-content guards. Run from a repo checkout, which has both artifacts.

These assert on the plugin's markdown rather than on the package, following the
precedent of the template drift guard in ``tests/test_status.py``: the wheel
ships only ``defendable_science``, so nothing at runtime can enforce these.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS = sorted((_REPO_ROOT / "skills").glob("*/SKILL.md"))

#: A concrete path is allowed when the line labels it as illustrative.
_ALLOWED = re.compile(r"for illustration|default layout|e\.g\.|<!--")


@pytest.mark.parametrize("skill", _SKILLS, ids=lambda p: p.parent.name)
def test_no_skill_hard_codes_the_research_tree(skill: Path) -> None:
    """The layout has one definition; a tenth prose copy is how it drifted."""
    offenders = [
        f"{skill.relative_to(_REPO_ROOT)}:{n}: {line.strip()}"
        for n, line in enumerate(skill.read_text(encoding="utf-8").splitlines(), 1)
        if "docs/research/" in line and not _ALLOWED.search(line)
    ]

    assert offenders == [], "\n".join(offenders)


def test_the_guard_actually_has_skills_to_check() -> None:
    """A glob that silently matched nothing would make the guard vacuous."""
    assert len(_SKILLS) >= 8
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd defendable-science && uv run pytest tests/test_plugin_content.py -v`
Expected: FAIL — every skill listing concrete `docs/research/` paths is reported
with its `file:line`, which is the worklist for Step 3.

- [ ] **Step 3: Sweep the six skills**

Work the failure list. For each offending line, either:

- replace the path with what the CLI resolves ("the paper's `backlog.md`, which
  the CLI resolves from the repo's layout"), and drop the now-redundant
  `--backlog` / `--paper-root` / `--research-root` flags from example invocations;
  or
- keep the concrete path where it genuinely aids comprehension and label it — the
  `_ALLOWED` pattern accepts `for illustration`, `default layout`, `e.g.` and
  comment lines.

`research-init`'s layout tree is a labelled illustration and stays; make sure its
fenced block is inside a `<!-- ... -->`-introduced or explicitly-labelled context
so the guard passes, rather than weakening the guard's pattern.

- [ ] **Step 4: Run it to verify it passes**

Run: `cd defendable-science && uv run pytest tests/test_plugin_content.py -v && cd .. && ./tools/validate-plugin.sh`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd defendable-science && git add tests/test_plugin_content.py && cd ..
git add skills/
git commit -m "docs(skills): resolve paths from the layout instead of hard-coding"
```

### Task 23: Point the design docs at the single definition

**Files:**
- Modify: `docs/design/00-meta-spec.md § 5` (the tree at `:430-443`)
- Modify: `docs/design/01-lifecycle.md § 7`

- [ ] **Step 1: Replace the restated trees**

Keep the narrative and the plugin-vs-consumer table. Replace each restated tree
with a pointer:

```markdown
The layout is defined once, in
`defendable-science/defendable_science/scaffold/layout.py`, and recorded per repo
in `.defendable-science/config.yml`'s optional `layout:` block
([ADR-0039](../../decisions/0039-recorded-consumer-layout.md)). It is scaffolded
by `defendable-science init` and validated by `defendable-science check`. The
tree below is the **default layout, for illustration** — the resolver is
authoritative.
```

Keep the illustrative tree beneath that sentence (it earns its place as
orientation) but delete the per-file schema comments, which are now the
renderers' business. Name `experiment_backend:` where § 5 currently describes the
binding without naming it.

- [ ] **Step 2: Verify**

Run: `pre-commit run --all-files && ./tools/validate-plugin.sh`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add docs/design/
git commit -m "docs(design): point the layout prose at its single definition"
```

### Task 24: File the follow-up issues and open the PR

- [ ] **Step 1: File the `check --fix` issue**

Use the `create-issue` skill. It must be completable cold, so include: the
dry-run-by-default requirement and the explicit write flag; the exact safe-repair
list (create missing directories and `.gitkeep`s, append a missing `.gitignore`
entry, migrate a table header to the correct profile when every existing row maps
losslessly); the prohibition list (`verdict`, `signed-off-by`, `evidence`, dataset
`license`, dataset `tier`) with `docs/design/00-meta-spec.md § 2.1` as the
grounding; the required test proving the refusal; `file:line` anchors into
`defendable_science/check/checks.py` and `cli.py`'s `check` command; and the
100%-coverage gate. Reference #121 as the parent.

- [ ] **Step 2: File the `progress dashboard` generator issue**

Include: that `render_dashboard()` currently writes an honest "not yet generated"
stub and why; that `skills/progress/SKILL.md` claims the file is generated; the
`gap` check in `check_cross_artifact` that becomes enforceable once a generator
exists; the projection rules from `progress/SKILL.md § Guardrails` (no scores, no
percentages, `refuted` is not failure); and the requirement that the generator be
a CLI verb so the never-hand-edit rule has a mechanism behind it.

- [ ] **Step 3: Run every gate and open the PR**

```bash
cd defendable-science && uv run pytest -q && uv run mypy && uv run ruff check && cd ..
pre-commit run --all-files
./tools/validate-plugin.sh
```

Then use the `create-pr` skill, linking both new issues in the body.

---

## Self-review notes

Checked against the spec after writing:

- **Spec coverage.** Every spec section maps to a task: § Architecture → Tasks 1,
  8, 13; PR1 → Tasks 1-6; PR2 → Tasks 7-12; PR3 → Tasks 13-20; PR4 → Tasks 21-23;
  § Follow-up issues → Task 24; § Testing → distributed across each task's test
  step, with the end-to-end acceptance smoke isolated as Task 11.
- **Two additions beyond the spec**, both forced by details found while gathering
  signatures, and both recorded in *Decisions this plan locks in*: routing
  `cli.py:389-390`'s hard-coded literature paths through the resolver (Task 5),
  and naming `experiment_backend:` as the config key (Tasks 8, 12, 23).
- **One spec deviation.** The spec's file list said `check/model.py` +
  `check/checks.py`; the plan adds `check/probe.py` so the filesystem seam is its
  own unit. Same boundaries, one more file.
- **`scaffold/init.py` renamed to `scaffold/init_repo.py`** — `init.py` inside a
  package directory reads like a typo'd `__init__.py`.
- **Type consistency.** `Layout`, `Finding`, `Report`, `Probe`, `Action`,
  `render`, `parse`, `registry_dumps`, `registry_root`, `triage_mapping`,
  `run_checks` are used under exactly the names their defining task produces.
  `Action.status` is a `str` with three documented values rather than a `Literal`,
  so the JSON adapter needs no cast.
