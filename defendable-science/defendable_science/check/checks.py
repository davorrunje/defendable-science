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
from defendable_science.core.config import load_config_text
from defendable_science.dataset import manifest as mf
from defendable_science.exploration.backlog import (
    REGISTRY_COLUMNS,
    Backlog,
    BacklogError,
    columns_for,
)
from defendable_science.literature import registry as reg
from defendable_science.scaffold import render as r
from defendable_science.scaffold import status as st
from defendable_science.scaffold.layout import (
    STAGED_DOCUMENTS,
    LayoutError,
    resolve_layout,
)

if TYPE_CHECKING:
    from pathlib import Path

    from defendable_science.check.probe import Probe
    from defendable_science.exploration.backlog import Level, Row
    from defendable_science.scaffold.layout import Layout

#: The check family names carried on every finding these two emit.
LAYOUT_CHECK = "layout"
TABLES_CHECK = "tables"
FRONTMATTER_CHECK = "frontmatter"

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


# --- frontmatter checks -------------------------------------------------------


def staged_documents(layout: Layout, probe: Probe) -> list[Path]:
    """Return every staged document that exists in the layout's research tree.

    Staged documents are those listed in ``STAGED_DOCUMENTS``. The thesis tree
    lives under ``research_root`` by default; if ``thesis_dir`` is elsewhere,
    both locations are globbed and results are de-duplicated.

    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :returns: Sorted absolute paths to staged documents.
    """
    documents: dict[Path, None] = {}

    # Glob for staged documents under research_root
    for path in probe.glob(layout.research_root, "**/*.md"):
        basename = path.name
        if basename in STAGED_DOCUMENTS:
            documents[path] = None

    # If thesis_dir is outside research_root, glob it too and de-duplicate
    try:
        layout.thesis_dir.relative_to(layout.research_root)
        # thesis_dir is under research_root, so we already found it above
    except ValueError:
        # thesis_dir is outside research_root, glob it too
        for path in probe.glob(layout.thesis_dir, "**/*.md"):
            basename = path.name
            if basename in STAGED_DOCUMENTS:  # pragma: no branch
                documents[path] = None

    return sorted(documents.keys())


def _check_unknown_fields(
    findings: list[Finding], rel: str, status_block: dict[str, object]
) -> None:
    """Check for unknown status fields. Append findings for any."""
    unknown_fields = sorted(k for k in status_block if k not in st.FIELD_ORDER)
    findings.extend(
        Finding(
            severity="invalid",
            check=FRONTMATTER_CHECK,
            file=rel,
            message=f"{rel} has unknown status field {field!r}",
            remedy=f"remove {field!r} from the status block; valid fields are {list(st.FIELD_ORDER)}",
        )
        for field in unknown_fields
    )


def _collect_placeholder_fields(
    findings: list[Finding], rel: str, status_block: dict[str, object]
) -> set[str]:
    """Scan for placeholder values and return their field names. Append findings for each."""
    placeholder_fields: set[str] = set()
    for field, value in status_block.items():
        if isinstance(value, str) and value.startswith("<"):
            placeholder_fields.add(field)
            findings.append(
                Finding(
                    severity="invalid",
                    check=FRONTMATTER_CHECK,
                    file=rel,
                    message=f"{rel} has placeholder in `{field}`: {value!r}",
                    remedy=(
                        f"set `{field}` to `null` until it is real, "
                        "and keep the guidance in a comment"
                    ),
                )
            )
    return placeholder_fields


def _check_enum_field(
    findings: list[Finding],
    rel: str,
    field_name: str,
    field_value: str | None,
    expected_level: str,
    enum_map: dict[str, frozenset[str]],
) -> None:
    """Check if field_value is in enum_map[expected_level]. Append finding if not."""
    if (
        field_value is not None
        and expected_level in enum_map
        and field_value not in enum_map[expected_level]
    ):
        findings.append(
            Finding(
                severity="invalid",
                check=FRONTMATTER_CHECK,
                file=rel,
                message=f"{rel} has `{field_name}: {field_value!r}`, which is not valid for {expected_level!r}; valid {field_name}s are {sorted(enum_map[expected_level])}",
                remedy=f"set `{field_name}` to one of {sorted(enum_map[expected_level])}, or set it to `null` if not yet determined",
            )
        )


def _check_frontmatter_document(
    path: Path, rel: str, expected_level: str, layout: Layout, probe: Probe
) -> list[Finding]:
    """Check one staged document's frontmatter. Return all findings for it."""
    findings: list[Finding] = []

    # Read the document
    text = _read(path, layout, probe, FRONTMATTER_CHECK)
    if isinstance(text, Finding):
        return [text]

    # Parse the frontmatter
    try:
        status_block = st.parse(text)
    except st.StatusError as exc:
        return [
            Finding(
                severity="invalid",
                check=FRONTMATTER_CHECK,
                file=rel,
                message=str(exc),
                remedy=(
                    f"fix the YAML in {rel}'s frontmatter block, "
                    "or remove the status block if the document doesn't belong in a discoverable location"
                ),
            )
        ]

    # Check for missing status block
    if status_block is None:
        return [
            Finding(
                severity="invalid",
                check=FRONTMATTER_CHECK,
                file=rel,
                message=f"{rel} has no `status:` block",
                remedy=(
                    f"add a status block to {rel}'s frontmatter: "
                    "`---\\nstatus:\\n  level: ...\\n---`"
                ),
            )
        ]

    # Check for unknown fields
    _check_unknown_fields(findings, rel, status_block)

    # Check for unreplaced placeholders and collect their field names
    placeholder_fields = _collect_placeholder_fields(findings, rel, status_block)

    # Check that level matches the filename (skip if level has a placeholder)
    if "level" not in placeholder_fields:
        level = status_block.get("level")
        if level != expected_level:
            findings.append(
                Finding(
                    severity="invalid",
                    check=FRONTMATTER_CHECK,
                    file=rel,
                    message=f"{rel} declares `level: {level!r}`, but {path.name!r} is a {expected_level!r} document",
                    remedy=f"change `level` to {expected_level!r}, or move the file to the correct document type",
                )
            )

    # Check verdict enum (if not a placeholder)
    if "verdict" not in placeholder_fields:
        _check_enum_field(
            findings,
            rel,
            "verdict",
            status_block.get("verdict"),
            expected_level,
            st.VERDICTS,
        )

    # Check readiness enum (if not a placeholder)
    if "readiness" not in placeholder_fields:
        readiness = status_block.get("readiness")
        if (
            readiness is not None
            and expected_level in st.READINESS
            and readiness not in st.READINESS[expected_level]
        ):
            findings.append(
                Finding(
                    severity="invalid",
                    check=FRONTMATTER_CHECK,
                    file=rel,
                    message=f"{rel} has `readiness: {readiness!r}`, which is not valid for {expected_level!r}; valid values are {sorted(st.READINESS[expected_level])}",
                    remedy=f"set `readiness` to one of {sorted(st.READINESS[expected_level])}, or set it to `null` if not yet set",
                )
            )

    return findings


def check_frontmatter(layout: Layout, probe: Probe) -> list[Finding]:
    """Report every staged document's status frontmatter that is invalid.

    Checks:
    1. The document is readable.
    2. The frontmatter block is present and parseable YAML.
    3. No fields are unknown (not in ``FIELD_ORDER``).
    4. No field values are unreplaced placeholders (starting with ``<``).
    5. The ``level`` matches the filename's documented level.
    6. ``verdict`` is in ``VERDICTS[level]`` or ``None``.
    7. ``readiness`` is in ``READINESS[level]`` or ``None``.

    Nothing here judges which verdict value a document carries; ``refuted``,
    ``no-go``, etc. are valid and pass exactly as successful verdicts do.

    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :returns: Findings in document order, one finding per issue.
    """
    findings: list[Finding] = []

    for path in staged_documents(layout, probe):
        rel = str(layout.rel(path))
        basename = path.name
        expected_level = STAGED_DOCUMENTS[basename]
        findings.extend(
            _check_frontmatter_document(path, rel, expected_level, layout, probe)
        )

    return findings


# --- registries checks -------------------------------------------------------

REGISTRIES_CHECK = "registries"


def check_registries(layout: Layout, probe: Probe) -> list[Finding]:
    """Report every problem with references, triage, and datasets registries.

    Reuses the real loaders to avoid reimplementing validation rules.

    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :returns: Findings for each registry. Severity is ``invalid`` for structural
        violations and loader errors, ``unreadable`` for read failures, and
        ``gap`` for soft validation issues (manifest warnings).
    """
    findings: list[Finding] = []

    # Check references.json
    findings.extend(_check_references(layout, probe))

    # Check triage.yml
    findings.extend(_check_triage(layout, probe))

    # Check datasets.yml
    findings.extend(_check_datasets(layout, probe))

    return findings


def _check_references(layout: Layout, probe: Probe) -> list[Finding]:
    """Check ``references.json`` for structural validity.

    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :returns: One finding per issue, or none if the registry is valid.
    """
    path = layout.references
    rel = str(layout.rel(path))

    text = _read(path, layout, probe, REGISTRIES_CHECK)
    if isinstance(text, Finding):
        return [text]

    # Use the text-level loader to validate structure and ids
    try:
        reg.load_registry_text(text, path)
    except reg.RegistryError as exc:
        return [
            Finding(
                severity="invalid",
                check=REGISTRIES_CHECK,
                file=rel,
                message=str(exc),
                remedy="repair the registry: it must be a JSON array of CSL-JSON objects with required 'id' fields",
            )
        ]

    return []


def _check_triage(layout: Layout, probe: Probe) -> list[Finding]:
    """Check ``triage.yml`` for structural validity and consistency with refs.

    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :returns: Findings for YAML parsing, non-mapping rows, and orphan keys.
    """
    path = layout.triage
    rel = str(layout.rel(path))

    text = _read(path, layout, probe, REGISTRIES_CHECK)
    if isinstance(text, Finding):
        return [text]

    # Parse the triage mapping
    try:
        triage_rows = reg.triage_mapping(path, text)
    except reg.RegistryError as exc:
        return [
            Finding(
                severity="invalid",
                check=REGISTRIES_CHECK,
                file=rel,
                message=str(exc),
                remedy=f"repair {rel}: it must be a YAML mapping of citekey → row",
            )
        ]

    findings: list[Finding] = []

    # Check for non-mapping rows
    for key, value in triage_rows.items():
        if not isinstance(value, dict):
            findings.append(
                Finding(
                    severity="invalid",
                    check=REGISTRIES_CHECK,
                    file=rel,
                    message=(
                        f"triage row {key!r} is not a mapping (got "
                        f"{type(value).__name__}); load_triage silently skips such "
                        "rows"
                    ),
                    remedy=(
                        f"make {key!r} a mapping with fields like 'disposition', "
                        f"or remove it"
                    ),
                )
            )

    # Get the set of valid ids from references.json
    ref_path = layout.references
    ref_rel = str(layout.rel(ref_path))
    ref_text = _read(ref_path, layout, probe, REGISTRIES_CHECK)
    valid_ids: set[str] = set()
    if not isinstance(ref_text, Finding):
        try:
            registry = reg.load_registry_text(ref_text, ref_path)
            valid_ids = {entry.citekey for entry in registry.entries}
        except reg.RegistryError:
            # If references.json is invalid, the references check will flag it;
            # we still check triage keys, but against an empty set
            pass

    # Check for orphan keys (triage keys with no matching reference id)
    findings.extend(
        Finding(
            severity="invalid",
            check=REGISTRIES_CHECK,
            file=rel,
            message=(f"triage key {key!r} has no matching entry in {ref_rel}"),
            remedy=(
                f"add an entry with id {key!r} to {ref_rel}, "
                f"or remove the {key!r} row from {rel}"
            ),
        )
        for key in triage_rows
        if key not in valid_ids
    )

    return findings


def _check_datasets(layout: Layout, probe: Probe) -> list[Finding]:
    """Check ``datasets.yml`` for structural validity and semantic correctness.

    Parses the YAML and builds a manifest for validation, reusing the
    manifest module's validation rules.

    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :returns: One finding per structural error or validation error/warning.
    """
    path = layout.datasets_manifest
    rel = str(layout.rel(path))

    text = _read(path, layout, probe, REGISTRIES_CHECK)
    if isinstance(text, Finding):
        return [text]

    # Use the text-level loader to validate structure and decode entries
    try:
        manifest = mf.load_text(text, path)
    except mf.ManifestError as exc:
        return [
            Finding(
                severity="invalid",
                check=REGISTRIES_CHECK,
                file=rel,
                message=str(exc),
                remedy=(
                    f"repair {rel}: {str(exc).lower()} — check the schema for "
                    "required and conditional fields"
                ),
            )
        ]

    # Validate the manifest
    report = mf.validate(manifest)

    findings: list[Finding] = []

    # Each error is invalid
    findings.extend(
        Finding(
            severity="invalid",
            check=REGISTRIES_CHECK,
            file=rel,
            message=error_msg,
            remedy=(
                f"correct {rel}: {error_msg.lower()} — consult the schema for "
                "required and conditional fields"
            ),
        )
        for error_msg in report.errors
    )

    # Each warning is a gap (soft issue)
    findings.extend(
        Finding(
            severity="gap",
            check=REGISTRIES_CHECK,
            file=rel,
            message=warning_msg,
            remedy=(
                f"complete {rel}: {warning_msg.lower()} to make the metadata "
                "more useful"
            ),
        )
        for warning_msg in report.warnings
    )

    return findings


# --- config checks ---------------------------------------------------------------

CONFIG_CHECK = "config"


def _cache_dir_in_gitignore(cache_dir: str, gitignore_text: str) -> bool:
    """Check if a cache_dir entry is covered by .gitignore rules.

    Handles three covering cases:
    1. Exact match after normalizing trailing slashes.
    2. A parent directory (e.g., ``.defendable-science/`` covers
       ``.defendable-science/cache/``).

    Skips blank lines and comment lines (first non-space character is ``#``).
    Does NOT evaluate gitignore glob or wildcard patterns — only literal
    matches and parent-directory containment.

    :param cache_dir: The configured cache directory (e.g.,
        ``.defendable-science/cache/``).
    :param gitignore_text: The ``.gitignore`` file contents.
    :returns: ``True`` if the cache_dir is covered by an active rule, else
        ``False``.
    """
    # Normalize cache_dir by removing trailing slash for comparison
    normalized_cache = cache_dir.rstrip("/")

    for line in gitignore_text.splitlines():
        stripped = line.strip()
        # Skip blank lines and comments
        if not stripped or stripped[0] == "#":
            continue

        # Normalize the gitignore line by removing trailing slash
        normalized_line = stripped.rstrip("/")

        # Check exact match
        if normalized_cache == normalized_line:
            return True

        # Check parent directory covering
        # e.g., ".defendable-science/" covers ".defendable-science/cache/"
        if normalized_cache.startswith(normalized_line + "/"):
            return True

    return False


def check_config(layout: Layout, probe: Probe) -> list[Finding]:
    """Report problems with the project configuration.

    Checks:
    1. The config file is readable.
    2. The file is valid YAML and contains a mapping.
    3. The ``layout:`` block (if present) contains only valid keys.
    4. The ``cache_dir`` is gitignored.
    5. The ``.gitignore`` file exists.
    6. The ``experiment_backend`` is bound (a null backend is a gap).

    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :returns: Findings for each issue: ``invalid`` for structural errors,
        ``unreadable`` for read failures, and ``gap`` for an unbound backend.
    """
    findings: list[Finding] = []

    # Read config file
    config_path = layout.config_file
    rel_config = str(layout.rel(config_path))
    text = _read(config_path, layout, probe, CONFIG_CHECK)
    if isinstance(text, Finding):
        return [text]

    # Parse config using same rules as load_config_text
    try:
        config = load_config_text(text)
    except ValueError as exc:
        return [
            Finding(
                severity="invalid",
                check=CONFIG_CHECK,
                file=rel_config,
                message=str(exc),
                remedy="fix the YAML syntax in the config file",
            )
        ]

    # Validate layout block
    try:
        resolve_layout(config, layout.repo_root)
    except LayoutError as exc:
        findings.append(
            Finding(
                severity="invalid",
                check=CONFIG_CHECK,
                file=rel_config,
                message=str(exc),
                remedy="correct the layout block in the config file to match a valid layout key",
            )
        )

    # Check cache_dir is gitignored
    cache_dir_config = config.get("cache_dir", r.DEFAULT_CACHE_DIR)
    gitignore_path = layout.repo_root / ".gitignore"
    rel_gitignore = str(layout.rel(gitignore_path))

    # Read .gitignore
    if probe.exists(gitignore_path):
        gitignore_text = _read(gitignore_path, layout, probe, CONFIG_CHECK)
        if isinstance(gitignore_text, Finding):
            findings.append(gitignore_text)
        else:
            # Check if cache_dir is covered by .gitignore
            if not _cache_dir_in_gitignore(cache_dir_config, gitignore_text):
                findings.append(
                    Finding(
                        severity="invalid",
                        check=CONFIG_CHECK,
                        file=rel_config,
                        message=(
                            f"cache_dir is set to {cache_dir_config!r}, "
                            f"but it is not in .gitignore"
                        ),
                        remedy=(f"add this line to .gitignore:\n{cache_dir_config}"),
                    )
                )
    else:
        findings.append(
            Finding(
                severity="invalid",
                check=CONFIG_CHECK,
                file=rel_gitignore,
                message=".gitignore is missing",
                remedy=(
                    "create .gitignore at the repository root and add:\n"
                    f"{cache_dir_config}"
                ),
            )
        )

    # Check experiment_backend
    experiment_backend = config.get("experiment_backend")
    if experiment_backend is None:
        findings.append(
            Finding(
                severity="gap",
                check=CONFIG_CHECK,
                file=rel_config,
                message=(
                    "experiment_backend is not bound; the repo cannot produce "
                    "the run-refs that evidence: requires"
                ),
                remedy=(
                    "set experiment_backend to the repo-local harness implementing "
                    "the experiment-backend contract (see "
                    "resources/contracts/experiment-backend.md)"
                ),
            )
        )

    return findings
