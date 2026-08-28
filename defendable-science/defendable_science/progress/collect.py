"""Read the repo's status frontmatter into a :class:`Projection` (#130).

Discovery, grouping and field extraction — everything the pure renderer must not
do. It reads through ``check``'s :class:`~defendable_science.check.probe.Probe`
seam and reuses ``check``'s document discovery, its reader and its finding
model, so a dashboard can never disagree with ``check`` about which artifacts
exist, and a file neither can read is reported the same way by both.

The unit is the **artifact**, not the staged document: a paper with a pitch and
a decision is one row, projected from its authoritative document (the verdict
source) with the lighter ``understanding`` blocks of its siblings surfaced
alongside. Before the authoritative document exists, the furthest stage that
does stands in — an artifact mid-flight is reported where it actually is.

Nothing here judges: a ``refuted`` verdict, an unsigned decision and an
uncovered aim are all read and passed on as facts. The only findings this
module emits are about text it could not read or parse, because a projection
that silently dropped an artifact would be a projection that lies.
"""

from __future__ import annotations

import dataclasses
import os
from typing import TYPE_CHECKING, Any

import yaml

from defendable_science.check.checks import (
    aim_ids,
    is_file,
    read_or_finding,
    staged_documents,
)
from defendable_science.check.model import Finding
from defendable_science.progress.model import (
    Artifact,
    Milestone,
    Milestones,
    Projection,
)
from defendable_science.scaffold import status as st
from defendable_science.scaffold.layout import AUTHORITATIVE_DOCUMENTS, STAGED_DOCUMENTS

if TYPE_CHECKING:
    from pathlib import Path

    from defendable_science.check.probe import Probe
    from defendable_science.scaffold.layout import Layout

#: The check family every finding this module emits is attributed to.
PROGRESS_CHECK = "progress"

#: Stage order within a level, taken from the one list that declares it, so a
#: new staged document is picked up here without a second edit.
_STAGE_ORDER: dict[str, int] = {name: n for n, name in enumerate(STAGED_DOCUMENTS)}

_REGENERATE = "run `defendable-science progress dashboard` again once it can be read"


# --- frontmatter field coercion ------------------------------------------------


def _strings(value: object) -> tuple[str, ...]:
    """Coerce a frontmatter collection field into a tuple of strings.

    Tolerant on purpose: the field is hand-written, and an author who typed
    ``blockers: awaiting the rerun`` instead of a list meant exactly what they
    wrote. Dropping it because the YAML type was not the expected one would
    hide a blocker, which is the one thing the dashboard exists to show.

    :param value: The raw frontmatter value.
    :returns: Its entries as strings; empty for ``None``, an empty collection,
        or a string holding only whitespace.
    """
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    text = str(value).strip()
    return (text,) if text else ()


def _text(value: object) -> str | None:
    """Return `value` as display text, or ``None`` when it is not yet set."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _understanding(name: str, value: object) -> tuple[str, ...]:
    """Return the unresolved understanding gaps `value` records, each named.

    Surfaced, never scored (ADR-0014): the gaps are listed by name rather than
    counted, so the reader sees *what* is unresolved instead of how many things
    are. A block recording no gaps adds nothing — an artifact nobody has
    examined yet is not a finding, it is simply one nobody has examined.

    :param name: The document that recorded the block, so a gap on a sibling is
        attributable rather than floating.
    :param value: The raw ``status.understanding`` value.
    :returns: The gaps, each prefixed with `name`.
    """
    if value is None:
        return ()
    if not isinstance(value, dict):
        return (f"{name}: understanding block is not a mapping",)
    gaps = _strings(value.get("unresolved"))
    if gaps:
        return tuple(f"{name}: {gap}" for gap in gaps)
    if value.get("status") == "gaps":
        return (f"{name}: gaps recorded, none named",)
    return ()


# --- locating artifacts --------------------------------------------------------


def _paper_of(layout: Layout, path: Path) -> str | None:
    """Return the paper directory `path` sits in, or ``None`` when it sits outside.

    Derived from the layout rather than from a hard-coded tree: a paper's
    directory is the first segment under ``research_root``, which is exactly
    what :meth:`Layout.paper_dir` builds from a paper id.

    :param layout: The resolved layout.
    :param path: A staged document's absolute path.
    :returns: The paper directory's name, or ``None`` for a document that is
        not inside one.
    """
    try:
        parts = path.relative_to(layout.research_root).parts
    except ValueError:
        return None
    if len(parts) < 2:
        return None
    candidate = parts[0]
    if layout.paper_dir(candidate) == layout.thesis_dir:
        return None
    return candidate


def _link(layout: Layout, path: Path) -> str:
    """Render `path` relative to the dashboard, so a row is clickable in a forge.

    :param layout: The resolved layout.
    :param path: The document the row projects.
    :returns: The relative path, POSIX-separated. ``os.path.relpath`` rather
        than :meth:`Path.relative_to` because a ``thesis_dir`` configured
        outside ``research_root`` needs the ``..`` hop that only it produces.
    """
    return os.path.relpath(path, layout.dashboard.parent).replace(os.sep, "/")


class _Group:
    """One artifact's staged documents, gathered before any of them is read.

    :param level: ``hypothesis`` | ``paper`` | ``thesis``.
    :param directory: The directory the documents were grouped on.
    :param paper: The paper directory the artifact sits in, if any.
    """

    def __init__(self, level: str, directory: Path, paper: str | None) -> None:
        self.level = level
        self.directory = directory
        self.paper = paper
        self.documents: list[Path] = []

    @property
    def primary(self) -> Path:
        """The document whose verdict block this artifact is projected from.

        The authoritative document when it exists, else the furthest stage
        present: a paper with only a pitch is reported at the pitch, not
        omitted for lacking a decision.
        """
        authoritative = AUTHORITATIVE_DOCUMENTS[self.level]
        for path in self.documents:
            if path.name == authoritative:
                return path
        return self.documents[-1]

    @property
    def label(self) -> str:
        """The artifact's directory name, shown when its id is not yet set."""
        if self.level == "paper":
            return self.paper or self.directory.name
        return self.directory.name


def _groups(layout: Layout, probe: Probe) -> list[_Group]:
    """Gather every staged document into the artifact it belongs to.

    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :returns: One group per artifact, its documents in stage order. A thesis's
        documents are keyed on ``thesis_dir`` because ``kappa.md`` lives one
        level below ``aims.md`` and the two describe the same artifact; every
        other level groups on the directory its documents share.
    """
    groups: dict[Path, _Group] = {}
    for path in staged_documents(layout, probe):
        level = STAGED_DOCUMENTS[path.name]
        key = layout.thesis_dir if level == "thesis" else path.parent
        paper = None if level == "thesis" else _paper_of(layout, path)
        groups.setdefault(key, _Group(level, key, paper)).documents.append(path)
    for group in groups.values():
        group.documents.sort(key=lambda p: _STAGE_ORDER[p.name])
    return [groups[key] for key in sorted(groups)]


# --- projecting one artifact ---------------------------------------------------


def _status_of(path: Path, layout: Layout, probe: Probe) -> dict[str, Any] | Finding:
    """Read one document's status block, or say why it could not be read.

    :param path: The document to read.
    :param layout: The resolved layout, used to render `path` repo-relative.
    :param probe: The filesystem seam.
    :returns: The status mapping, or the finding explaining why there is none.
        The union rather than a pair, matching :func:`read_or_finding`: "the
        block, or the reason there is none" is then a fact the type checker
        enforces, instead of an empty mapping standing in for a failed read. A
        document with no ``status:`` block at all yields an empty mapping and no
        finding — its fields are unset, which the dashboard reports honestly,
        and ``check`` owns the defect.
    """
    text = read_or_finding(path, layout, probe, PROGRESS_CHECK)
    if isinstance(text, Finding):
        return text
    try:
        return st.parse(text) or {}
    except st.StatusError as exc:
        rel = layout.rel(path)
        return Finding(
            severity="invalid",
            check=PROGRESS_CHECK,
            file=str(rel),
            message=f"could not read the status block of {rel}: {exc}",
            remedy=(
                f"repair the frontmatter of {rel}; until it parses this artifact's "
                f"state is unknown, not empty — then {_REGENERATE}"
            ),
        )


def _artifact(
    group: _Group, layout: Layout, probe: Probe
) -> tuple[Artifact, list[Finding]]:
    """Project one group of staged documents into one dashboard row.

    :param group: The artifact's documents.
    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :returns: The row and the findings raised while reading it. A sibling that
        could not be read leaves a note on the row; the *authoritative* one
        leaves the row's state visibly ``unknown`` rather than blank.
    """
    findings: list[Finding] = []
    understanding: list[str] = []
    notes: list[str] = []
    primary = group.primary
    fields: dict[str, Any] = {}
    unreadable = False

    for path in group.documents:
        status = _status_of(path, layout, probe)
        if isinstance(status, Finding):
            findings.append(status)
            notes.append(f"{path.name} could not be read")
            unreadable = unreadable or path == primary
            continue
        understanding += _understanding(path.name, status.get("understanding"))
        if path == primary:
            fields = status

    return (
        Artifact(
            level=group.level,
            label=group.label,
            link=_link(layout, primary),
            artifact_id=_text(fields.get("id")),
            paper=group.paper,
            verdict=_text(fields.get("verdict")),
            readiness=_text(fields.get("readiness")),
            signed_off=_text(fields.get("signed-off-by")) is not None,
            last_updated=_text(fields.get("last-updated")),
            load_bearing=fields.get("load-bearing") is True,
            covers=_strings(fields.get("covers")),
            blockers=_strings(fields.get("blockers")),
            understanding=tuple(understanding),
            unreadable=unreadable,
            notes=tuple(notes),
        ),
        findings,
    )


# --- the cross-artifact chain --------------------------------------------------


def _blocked_by(artifact: Artifact, artifacts: list[Artifact]) -> tuple[str, ...]:
    """Name the load-bearing refutations that block `artifact`'s claim.

    A single refuted ``load-bearing: true`` hypothesis invalidates its paper's
    claim however many siblings resolved cleanly, so it is named rather than
    averaged away. An *unsigned* refutation names nothing: until a human signs
    it, it is not yet decided, and reporting it as a blocker would be the
    dashboard deciding.

    :param artifact: The paper being described.
    :param artifacts: Every artifact projected, hypotheses included.
    :returns: One entry per blocking hypothesis, in projection order.
    """
    return tuple(
        f"{other.artifact_id or other.label} (load-bearing, refuted)"
        for other in artifacts
        if other.level == "hypothesis"
        and other.paper == artifact.label
        and other.load_bearing
        and other.verdict == "refuted"
        and other.signed_off
    )


def _uncovered(artifacts: list[Artifact], declared: frozenset[str]) -> tuple[str, ...]:
    """Return the declared aims no paper covers, named and never counted.

    :param artifacts: Every artifact projected.
    :param declared: The aim ids ``aims.md`` declares.
    :returns: The uncovered aims, sorted so two runs agree byte for byte.
    """
    covered = {aim for a in artifacts if a.level == "paper" for aim in a.covers}
    return tuple(sorted(declared - covered))


def _rolled_up(
    artifact: Artifact, artifacts: list[Artifact], uncovered: tuple[str, ...]
) -> Artifact:
    """Attach the chain facts an artifact cannot know about itself.

    Semantic, never arithmetic: a paper learns which of its load-bearing
    hypotheses is refuted, and a thesis learns which of its aims nothing
    covers. Neither learns a percentage.

    :param artifact: The artifact to complete.
    :param artifacts: Every artifact projected.
    :param uncovered: The declared aims no paper covers.
    :returns: The artifact, with its chain facts filled in.
    """
    if artifact.level == "paper":
        return dataclasses.replace(
            artifact, blocked_by=_blocked_by(artifact, artifacts)
        )
    if artifact.level == "thesis":
        return dataclasses.replace(artifact, uncovered_aims=uncovered)
    return artifact


def _declared_aims(layout: Layout, probe: Probe) -> frozenset[str]:
    """Return the aim ids ``aims.md`` declares, or none when it cannot be read.

    An unreadable aims file yields no declared aims rather than a guess, so no
    aim is reported uncovered on the strength of a file nobody could read. The
    read failure itself is already a finding: ``aims.md`` is a staged document,
    so :func:`_artifact` reported it before this runs.

    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :returns: The declared aim ids.
    """
    if not is_file(probe, layout.aims):
        return frozenset()
    text = read_or_finding(layout.aims, layout, probe, PROGRESS_CHECK)
    if isinstance(text, Finding):
        return frozenset()
    return frozenset(aim_ids(text))


# --- the configurable program gates --------------------------------------------


def _unknown_gates(
    rel: Path, message: str, remedy: str
) -> tuple[Milestones, list[Finding]]:
    """Report the gate list as unknown, never as an empty one."""
    return Milestones(unknown=True), [
        Finding(
            severity="invalid",
            check=PROGRESS_CHECK,
            file=str(rel),
            message=message,
            remedy=remedy,
        )
    ]


def _milestones(
    layout: Layout, probe: Probe
) -> tuple[Milestones | None, list[Finding]]:
    """Read the configurable program gates, or say why they are unknown.

    The list is the author's. Institution gates vary and are deadline-driven,
    so whatever ``milestones:`` holds is what is projected and the packaged
    starting list (``render.PROGRAM_GATES``) is never assumed.

    :param layout: The resolved layout.
    :param probe: The filesystem seam.
    :returns: The gates and any findings; ``None`` gates when the repo has no
        milestones file, which is the ordinary state of a paper portfolio and
        not a defect.
    """
    path = layout.milestones
    if not is_file(probe, path):
        return None, []
    rel = layout.rel(path)
    text = read_or_finding(path, layout, probe, PROGRESS_CHECK)
    if isinstance(text, Finding):
        return Milestones(unknown=True), [text]
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return Milestones(unknown=True), [
            Finding(
                severity="unreadable",
                check=PROGRESS_CHECK,
                file=str(rel),
                message=f"could not parse {rel}: {exc}",
                remedy=f"repair the YAML in {rel}, then {_REGENERATE}",
            )
        ]
    if data is None:
        return Milestones(), []
    if not isinstance(data, dict) or "milestones" not in data:
        return _unknown_gates(
            rel,
            f"{rel} holds no `milestones:` list, so the program gates are unknown",
            f"give {rel} a top-level `milestones:` list of gates, then {_REGENERATE}",
        )
    entries = data["milestones"]
    if entries is None:
        return Milestones(), []
    if not isinstance(entries, list):
        return _unknown_gates(
            rel,
            f"{rel} holds `milestones: {type(entries).__name__}`, not a list of "
            "gates, so the program gates are unknown",
            f"make `milestones:` in {rel} a list of gates, each with a name / "
            f"status / date / next-deadline, then {_REGENERATE}",
        )
    return Milestones(entries=tuple(_milestone(entry) for entry in entries)), []


def _milestone(entry: object) -> Milestone:
    """Project one gate, however the author wrote it.

    :param entry: One item of the ``milestones:`` list.
    :returns: The gate. An entry that is not a mapping is rendered as its own
        text rather than dropped — a gate nobody can see is a gate nobody meets.
    """
    if not isinstance(entry, dict):
        return Milestone(name=_text(entry))
    return Milestone(
        name=_text(entry.get("name")),
        status=_text(entry.get("status")),
        date=_text(entry.get("date")),
        next_deadline=_text(entry.get("next-deadline")),
    )


# --- the entry point -----------------------------------------------------------


def collect(layout: Layout, probe: Probe) -> Projection:
    """Read every artifact's status frontmatter into one projection.

    :param layout: The resolved layout — the one definition of where artifacts
        live, so a repo with a non-default ``research_root`` is projected from
        where its files actually are.
    :param probe: The filesystem seam.
    :returns: The projection, with a finding for every document that could not
        be read or parsed. A repo holding no artifacts yields no artifacts and
        no findings — legitimately empty, and distinguishable from a repo whose
        files could not be read, because that one carries findings.
    """
    findings: list[Finding] = []
    artifacts: list[Artifact] = []
    for group in _groups(layout, probe):
        artifact, group_findings = _artifact(group, layout, probe)
        artifacts.append(artifact)
        findings += group_findings

    uncovered = _uncovered(artifacts, _declared_aims(layout, probe))
    milestones, milestone_findings = _milestones(layout, probe)
    return Projection(
        artifacts=tuple(_rolled_up(a, artifacts, uncovered) for a in artifacts),
        milestones=milestones,
        findings=tuple(findings + milestone_findings),
    )
