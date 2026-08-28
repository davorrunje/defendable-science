"""The value objects the dashboard projects (#130).

Everything here is a *fact read from frontmatter*, never a judgement about it.
There is deliberately no aggregate, no score and no completion field: the
dashboard surfaces state, coverage and named gaps, and a rolled-up number is the
one thing it must never grow (meta-spec §3.6, ADR-0014).

Absence is modelled as ``None`` / the empty tuple and means **"not yet set"**;
it never means zero. A document that could not be read is modelled separately
(:attr:`Artifact.unreadable`, :attr:`Milestones.unknown`), because "we do not
know" and "there is nothing" are different facts and only one of them is fine.

Stdlib only — ``dataclasses``, not ``pydantic``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from defendable_science.check.model import Finding

#: The artifact levels, in the order the dashboard renders their sections.
LEVELS: tuple[str, ...] = ("hypothesis", "paper", "thesis")


@dataclass(frozen=True)
class Artifact:
    """One artifact's state — one row of the dashboard, plus its detail line.

    An *artifact* is the whole hypothesis / paper / thesis, not one staged
    document: its verdict comes from the authoritative document
    (``AUTHORITATIVE_DOCUMENTS``) when that exists, and its
    ``understanding`` gaps are collected from every staged document it owns.

    :param level: ``hypothesis`` | ``paper`` | ``thesis``.
    :param label: The artifact's directory name, shown when `artifact_id` is
        unset so the row still points somewhere real.
    :param link: The projected document's path, relative to the dashboard, so
        the row is clickable in a git forge.
    :param artifact_id: The ``status.id`` of the projected document, or ``None``
        when it is not yet set. Only a real id is rendered as one.
    :param paper: The paper directory this artifact sits in, linking a
        hypothesis to its paper. ``None`` when it sits outside any paper.
    :param verdict: The recorded verdict, or ``None`` when unset.
    :param readiness: The recorded readiness, or ``None`` when unset.
    :param signed_off: Whether ``signed-off-by`` names a human. A verdict
        without one is *not yet decided* (meta-spec §2.1).
    :param last_updated: The projected document's ``last-updated``.
    :param load_bearing: Whether refuting this hypothesis invalidates its
        paper's claim.
    :param covers: The thesis aims this artifact supports.
    :param blockers: The free-text blockers its author flagged.
    :param understanding: Unresolved understanding gaps, each already
        attributed to the document that recorded it.
    :param blocked_by: Load-bearing refutations that block this paper, named
        rather than counted.
    :param uncovered_aims: Aims this thesis declares that no paper covers.
    :param unreadable: Whether the projected document could not be read or
        parsed, making this row's state *unknown* rather than unset.
    :param notes: Anything else the reader needs to interpret the row, notably
        which sibling documents could not be read.
    """

    level: str
    label: str
    link: str
    artifact_id: str | None = None
    paper: str | None = None
    verdict: str | None = None
    readiness: str | None = None
    signed_off: bool = False
    last_updated: str | None = None
    load_bearing: bool = False
    covers: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    understanding: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
    uncovered_aims: tuple[str, ...] = ()
    unreadable: bool = False
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Milestone:
    """One program gate, exactly as ``thesis/milestones.yml`` records it.

    Calendar gates, distinct from the defensibility state above: surfaced,
    never scored, and never assumed — the list is the author's to edit, so
    whatever the file holds is what is rendered.

    :param name: The gate's name, or ``None`` when the entry does not name one.
    :param status: ``not-started`` | ``scheduled`` | ``passed``, as written.
    :param date: The scheduled or passed date.
    :param next_deadline: The next binding deadline.
    """

    name: str | None
    status: str | None = None
    date: str | None = None
    next_deadline: str | None = None


@dataclass(frozen=True)
class Milestones:
    """The gate list, and whether it could be read at all.

    :param entries: The gates, in the order the file lists them — that order is
        the author's progression, so it is preserved rather than sorted.
    :param unknown: The file is there but could not be read or does not hold a
        ``milestones:`` list. An empty `entries` with this set means *we do not
        know the gates*, which is not the same as *there are none*.
    """

    entries: tuple[Milestone, ...] = ()
    unknown: bool = False


@dataclass(frozen=True)
class Projection:
    """Everything one dashboard render needs, and nothing the renderer computes.

    :param artifacts: Every artifact found, in any order — the renderer sorts.
    :param milestones: The gate list, or ``None`` when the repo has no
        milestones file (a paper portfolio without a thesis is complete).
    :param findings: What could not be read, in ``check``'s finding shape so a
        degradation is reported the same way everywhere and never as a clean
        empty result.
    """

    artifacts: tuple[Artifact, ...] = ()
    milestones: Milestones | None = None
    findings: tuple[Finding, ...] = ()
