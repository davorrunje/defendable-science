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

from typing import TYPE_CHECKING

from defendable_science.exploration.backlog import Backlog, registry_dumps

if TYPE_CHECKING:
    from collections.abc import Sequence

#: Mirrors ``core.config``'s cache default (ADR-0031); written explicitly so the
#: scaffolded ``.gitignore`` and the runtime cache path cannot drift.
DEFAULT_CACHE_DIR = ".defendable-science/cache/"

#: The program gates the ``thesis`` skill documents. Institution gates vary and
#: are deadline-driven, so this is the starting list an author edits, never a
#: fixed one.
PROGRAM_GATES: tuple[str, ...] = (
    "proposal",
    "candidacy",
    "annual-review",
    "submission",
    "defense",
)

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


def render_milestones() -> str:
    """Render ``thesis/milestones.yml`` — the program gates, each undated.

    A gate maps to ``null`` until the author dates it: absence means "not yet
    set", so an undated gate cannot be read as a passed one. Gates are surfaced,
    never scored — an overdue gate is a gap, not a penalty (meta-spec §3.6).

    :returns: The milestones file text.
    """
    gates = "".join(f"{gate}: null\n" for gate in PROGRAM_GATES)
    return (
        "# Thesis program gates — configurable and time-based. Institution gates\n"
        "# vary, so edit this list to match yours. A gate's value is `null` until\n"
        "# you date it (the scheduled or passed date). These are calendar gates,\n"
        "# distinct from the defensibility state in the thesis status block;\n"
        "# `progress` reports both and scores neither.\n"
        "\n" + gates
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
