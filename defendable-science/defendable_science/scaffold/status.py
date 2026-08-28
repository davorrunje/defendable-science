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
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Field order, verbatim as it appears in every artifact.
FIELD_ORDER: tuple[str, ...] = (
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
VERDICTS: dict[str, frozenset[str]] = {
    "hypothesis": frozenset({"pending", "confirmed", "refuted", "inconclusive"}),
    "paper": frozenset({"no-go", "publish"}),
    "thesis": frozenset({"n/a"}),
}

#: Allowed ``readiness`` values per level.
READINESS: dict[str, frozenset[str]] = {
    "hypothesis": frozenset({"pending", "resolved"}),
    "paper": frozenset({"drafting", "under-review", "published"}),
    "thesis": frozenset({"framing", "synthesis", "defensible"}),
}

#: Readiness values that are themselves a **material decision**, and so carry
#: the named-human sign-off requirement of meta-spec §2.1 exactly as a verdict
#: does. A thesis has no verdict axis (``verdict: n/a``), so ``defensible`` *is*
#: its decision — the highest-stakes claim in the methodology, and the one that
#: read as complete with nobody having signed anything until this existed.
#:
#: ``published`` is deliberately absent: ``drafting → under-review → published``
#: are sub-states of a paper's *done*, not extra gates, and the paper's decision
#: is its ``verdict: publish|no-go``. Written here, beside the enums, because
#: both ``check`` and ``progress`` must apply one rule.
SIGNED_READINESS: frozenset[str] = frozenset({"defensible"})

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
    """Raised on an unknown level or field, or unparsable frontmatter."""


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
