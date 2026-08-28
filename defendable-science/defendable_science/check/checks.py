"""The layout and table check families (#121).

Two questions nothing could answer before ``check`` existed: are the files a
defendable-science repo needs actually there, and do the tables everything else
reads actually parse with the right column profile? The failure is real — a
scaffolded ``portfolio-backlog.md`` whose header was
``['id', 'status', 'idea', 'rationale', 'ranked', 'promoted-to']`` carried none
of the columns the paper profile requires, and nothing surfaced it until an
unrelated ``backlog park`` tripped over it (#120, #121).

A *missing* required column is the defect; an extra one never is. ``papers.md``
and both backlogs are author-editable, and their writers deliberately preserve
whatever a host header carries beyond the profile (``Backlog.columns``,
``append_papers_registry``), so flagging a column an author added would make
``check`` nag about a documented extension point.

Every read goes through :func:`_read`, so a file that could not be read is
reported as ``unreadable`` — validity *unknown* — and never as a valid empty
one. Every column judgement is made against the profile its writer enforces
(:func:`columns_for`, :data:`REGISTRY_COLUMNS`), so a table these checks call
valid can never be one a mutation then refuses.

Nothing here looks at a verdict: a ``refuted`` hypothesis and a ``no-go`` paper
are successful science, not findings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from defendable_science.check.model import Finding
from defendable_science.exploration.backlog import (
    REGISTRY_COLUMNS,
    Backlog,
    BacklogError,
    columns_for,
)

if TYPE_CHECKING:
    from pathlib import Path

    from defendable_science.check.probe import Probe
    from defendable_science.exploration.backlog import Level, Row
    from defendable_science.scaffold.layout import Layout

#: The check family names carried on every finding these two emit.
LAYOUT_CHECK = "layout"
TABLES_CHECK = "tables"

_INIT_REMEDY = (
    "run `defendable-science init` — it creates the missing files and never "
    "overwrites existing ones"
)
_THESIS_REMEDY = (
    "run `defendable-science init --thesis` to scaffold the thesis tree, or "
    "remove the thesis directory if this repo has no thesis"
)


def _header(columns: list[str]) -> str:
    """Render `columns` as the markdown header row a remedy tells you to write."""
    return "| " + " | ".join(columns) + " |"


def _read(path: Path, layout: Layout, probe: Probe, check: str) -> str | Finding:
    """Read `path`, or return the ``unreadable`` finding describing why.

    Never conflates a read failure with an empty file: "0 references" and
    "could not read references.json" are different facts, and only one of them
    means the repo is fine.

    :param path: The absolute path to read.
    :param layout: The layout, used to render `path` repo-relative.
    :param probe: The filesystem seam.
    :param check: The emitting check family, recorded on the finding.
    :returns: The file's text, or an ``unreadable`` `Finding`. The union rather
        than a ``(text, finding)`` pair is deliberate: "text or the reason there
        is none" is then a fact the type checker enforces at every call site,
        instead of an empty string standing in for a failed read.
    """
    rel = layout.rel(path)
    try:
        return probe.read_text(path)
    except OSError as exc:
        return Finding(
            severity="unreadable",
            check=check,
            file=str(rel),
            message=f"could not read {rel}: {exc}",
            remedy=(
                f"restore {rel} (`git checkout -- {rel}`) or re-create it; until "
                "it can be read this repo's validity is unknown, not clean"
            ),
        )


def _parse_table(
    path: Path, text: str, layout: Layout, level: Level, profile: list[str]
) -> Backlog | Finding:
    """Locate the markdown table in `text`, or say why there is none to read.

    :param path: The file `text` came from, for the finding.
    :param text: The document's contents.
    :param level: The level :meth:`Backlog.loads` parses at. It selects only the
        fallback profile of a table-less document, which this rejects outright,
        so the registry — not a backlog — can be parsed at any level.
    :param profile: The columns this file must carry, named in the remedy.
    :param layout: The layout, used to render `path` repo-relative.
    :returns: The parsed table, or an ``invalid`` `Finding`. A document holding
        no table is a finding rather than an empty table: ``Backlog`` would
        otherwise hand back `profile` as the header, and a file with no table at
        all would read as a valid empty one.
    """
    rel = str(layout.rel(path))
    try:
        table = Backlog.loads(text, level)
    except BacklogError as exc:
        return Finding(
            severity="invalid",
            check=TABLES_CHECK,
            file=rel,
            message=str(exc),
            remedy=(
                f"repair the table in {rel}: a header row anchored by a `|---|` "
                "separator, and every data row as wide as the header"
            ),
        )
    if table.file_header is None:
        return Finding(
            severity="invalid",
            check=TABLES_CHECK,
            file=rel,
            message=f"{rel} holds no markdown table",
            remedy=(
                f"add the table back to {rel}: the header `{_header(profile)}` "
                "followed by a `|---|` separator row"
            ),
        )
    return table


# --- layout -----------------------------------------------------------------


def _required_files(layout: Layout, probe: Probe) -> list[tuple[Path, str]]:
    """Return every file this repo must hold, with the remedy for its absence.

    Thesis-ness is a fact on disk, never an assumption: ``aims.md`` and
    ``milestones.yml`` are required only once a thesis directory exists. A
    portfolio repo without a thesis tree is complete, not broken.

    :param layout: The resolved layout.
    :param probe: The filesystem seam, asked whether a thesis tree exists.
    :returns: ``(path, remedy)`` pairs, in report order.
    """
    required = [
        (path, _INIT_REMEDY)
        for path in (
            layout.papers_registry,
            layout.portfolio_backlog,
            layout.dashboard,
            layout.references,
            layout.triage,
            layout.datasets_manifest,
            layout.config_file,
        )
    ]
    if probe.exists(layout.thesis_dir):
        required += [(layout.aims, _THESIS_REMEDY), (layout.milestones, _THESIS_REMEDY)]
    return required


def check_layout(layout: Layout, probe: Probe) -> list[Finding]:
    """Report every required file this repo does not have.

    :param layout: The resolved layout — the one definition of where each file
        lives, so a repo with a non-default ``research_root`` is checked where
        its files actually are.
    :param probe: The filesystem seam.
    :returns: One ``invalid`` finding per missing file, in layout order.
    """
    return [
        Finding(
            severity="invalid",
            check=LAYOUT_CHECK,
            file=str(layout.rel(path)),
            message=f"required file {layout.rel(path)} is missing",
            remedy=remedy,
        )
        for path, remedy in _required_files(layout, probe)
        if not probe.exists(path)
    ]


# --- tables -----------------------------------------------------------------


def _check_backlog(
    layout: Layout, probe: Probe, path: Path, level: Level
) -> list[Finding]:
    """Report whether the backlog at `path` parses with `level`'s column profile.

    Only *missing* columns are a finding: ``Backlog`` deliberately preserves
    columns a host file carries beyond the profile, so an author's extra column
    is not a defect.

    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :param path: The backlog file, which the caller has confirmed exists.
    :param level: ``hypothesis`` for a paper's backlog, ``paper`` for the
        portfolio backlog.
    :returns: At most one finding — unreadable, unparsable, or missing columns.
    """
    text = _read(path, layout, probe, TABLES_CHECK)
    if isinstance(text, Finding):
        return [text]
    profile = columns_for(level)
    table = _parse_table(path, text, layout, level, profile)
    if isinstance(table, Finding):
        return [table]
    # `Backlog.columns` is the host file's own header — the very list the
    # backlog's pre-mutation guard compares the profile against — so this is the
    # same rule, read through the public API rather than a second definition of
    # it: a header this check passes can never be one `backlog park` refuses.
    missing = [column for column in profile if column not in table.columns]
    if missing:
        return [
            Finding(
                severity="invalid",
                check=TABLES_CHECK,
                file=str(layout.rel(path)),
                message=(
                    f"{level} backlog table is missing required column(s) "
                    f"{missing}: its header is {table.columns}"
                ),
                remedy=(
                    f"migrate the table to the {level} profile — the header "
                    f"`{_header(profile)}` — keeping each existing row's values"
                ),
            )
        ]
    return []


def _registry_columns(path: Path, layout: Layout, header: list[str]) -> list[Finding]:
    """Report the required registry columns `header` does not carry.

    Missing columns only. ``append_papers_registry`` raises on exactly this set
    and writes rows into any header that carries it, preserving the columns
    beyond it as the author's own ("written empty for the author to fill, never
    dropped"), so an extra column is an extension point rather than corruption.
    A missing one is what stops ``promote --scaffold`` registering a paper.

    :param path: The registry file, for the finding.
    :param layout: The resolved layout.
    :param header: The column order read from the file.
    :returns: One ``invalid`` finding if a required column is absent, else none.
    """
    missing = [column for column in REGISTRY_COLUMNS if column not in header]
    if not missing:
        return []
    return [
        Finding(
            severity="invalid",
            check=TABLES_CHECK,
            file=str(layout.rel(path)),
            message=(
                f"registry table is missing required column(s) {missing}: its "
                f"header is {header}"
            ),
            remedy=(
                f"add the missing column(s) to the registry header — it must "
                f"carry `{_header(list(REGISTRY_COLUMNS))}` for "
                "`backlog promote --scaffold` to append a row"
            ),
        )
    ]


def registry_rows(layout: Layout, probe: Probe) -> tuple[list[Row], list[Finding]]:
    """Read ``papers.md`` and return its rows alongside findings about the table.

    The rows are the entry point every per-paper check walks, so this is public:
    each family reads the registry once, through one validator.

    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :returns: The registry's rows and the findings about the registry file. The
        rows are empty whenever the table could not be interpreted — a header
        this could not read must not yield rows that look authoritative — and a
        registry that is merely *absent* yields no findings at all, because
        :func:`check_layout` owns "a required file is missing".
    """
    path = layout.papers_registry
    if not probe.exists(path):
        return [], []
    text = _read(path, layout, probe, TABLES_CHECK)
    if isinstance(text, Finding):
        return [], [text]
    table = _parse_table(path, text, layout, "paper", list(REGISTRY_COLUMNS))
    if isinstance(table, Finding):
        return [], [table]
    return table.rows, _registry_columns(path, layout, table.columns)


def _check_registered_paper(layout: Layout, probe: Probe, row: Row) -> list[Finding]:
    """Report what one registry row promises that the repo does not deliver.

    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :param row: One ``papers.md`` row.
    :returns: The findings for this row. An unbound backend is a ``gap`` —
        incomplete science in a valid file — while a root that is missing or
        outside the repository, and a backlog the registry implies but the repo
        does not have, are ``invalid``.
    """
    registry = str(layout.rel(layout.papers_registry))
    paper_id = row.get("paper-id", "").strip()
    root = row.get("root", "").strip()
    if not paper_id:
        return [
            Finding(
                severity="invalid",
                check=TABLES_CHECK,
                file=registry,
                message=(
                    f"a registry row has no paper-id (root {root!r}); the paper-id "
                    "keys the paper across its backlog, the dashboard and `progress`"
                ),
                remedy="give the row a stable paper-id, or delete the row",
            )
        ]
    if not root:
        return [
            Finding(
                severity="invalid",
                check=TABLES_CHECK,
                file=registry,
                message=f"registered paper {paper_id!r} has no root",
                remedy=(
                    "set the row's root to the paper's directory, e.g. "
                    f"{layout.rel(layout.paper_dir(paper_id))}"
                ),
            )
        ]
    # Mirrors `scaffold.layout._relative`: an absolute value, or one that walks
    # out with `..`, would point `check` — and every command that follows this
    # row — at a tree outside the work tree, which an integrity tool must not do.
    paper_root = (layout.repo_root / root).resolve()
    if paper_root != layout.repo_root and layout.repo_root not in paper_root.parents:
        return [
            Finding(
                severity="invalid",
                check=TABLES_CHECK,
                file=registry,
                message=(
                    f"registered paper {paper_id!r} has root {root}, which is "
                    f"outside the repository ({paper_root})"
                ),
                remedy=(
                    "make the row's root a repo-relative path inside the "
                    "repository, e.g. "
                    f"{layout.rel(layout.paper_dir(paper_id))}"
                ),
            )
        ]
    if not probe.exists(paper_root):
        return [
            Finding(
                severity="invalid",
                check=TABLES_CHECK,
                file=registry,
                message=(
                    f"registered paper {paper_id!r} has root {root}, which does "
                    "not exist"
                ),
                remedy=(
                    f"correct the row's root, create {root}, or remove the row if "
                    "the paper was never scaffolded"
                ),
            )
        ]
    findings = []
    # Only when the header actually carries the column. A registry missing
    # `backend` altogether is one reported header defect, not an unbound backend
    # per row: that gap would be an artifact of the header, not of the science.
    if "backend" in row and not row["backend"].strip():
        findings.append(
            Finding(
                severity="gap",
                check=TABLES_CHECK,
                file=registry,
                message=(
                    f"registered paper {paper_id!r} has no experiment backend bound"
                ),
                remedy=(
                    "record the paper's experiment-backend binding in the "
                    "registry's backend column; until then the paper cannot "
                    "produce the run-refs its evidence needs"
                ),
            )
        )
    # The registry's own `root`, not the derived path: it is what the registry
    # promises, and it is the directory just confirmed to exist.
    backlog = paper_root / "backlog.md"
    if not probe.exists(backlog):
        findings.append(
            Finding(
                severity="invalid",
                check=TABLES_CHECK,
                file=str(layout.rel(backlog)),
                message=f"registered paper {paper_id!r} has no backlog.md",
                remedy=(
                    f"create {layout.rel(backlog)} with the hypothesis header "
                    f"`{_header(columns_for('hypothesis'))}` and a `|---|` "
                    "separator row"
                ),
            )
        )
    else:
        findings.extend(_check_backlog(layout, probe, backlog, "hypothesis"))
    return findings


def check_tables(layout: Layout, probe: Probe) -> list[Finding]:
    """Report every registry and backlog table that does not parse as its profile.

    Covers ``papers.md``, ``portfolio-backlog.md`` and one ``backlog.md`` per
    registered paper — every table the rest of the tooling reads. A file that is
    simply absent is left to :func:`check_layout`, so a missing file is reported
    once rather than twice.

    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :returns: The findings, registry first, then the portfolio backlog, then one
        registered paper at a time.
    """
    rows, findings = registry_rows(layout, probe)
    if probe.exists(layout.portfolio_backlog):
        findings.extend(
            _check_backlog(layout, probe, layout.portfolio_backlog, "paper")
        )
    for row in rows:
        findings.extend(_check_registered_paper(layout, probe, row))
    return findings
