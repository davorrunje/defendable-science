"""The finding model every ``check`` family emits (#121).

Three severities, and the exit code keys off *severity*, not count:

``invalid``
    The file violates a shape this package owns. Exits ``1``.
``unreadable``
    It could not be read or parsed, so its validity is **unknown**. Exits ``1``
    — a failed read must never render as "valid and empty" (failure honesty).
``gap``
    A valid file holding incomplete science: an unsigned verdict, empty
    evidence, an unbound experiment backend. Reported, but exits ``0``.

The exit code is keyed to invalid *files*, never to incomplete *science*: a
``refuted`` hypothesis or a ``no-go`` paper is successful science and is not a
finding of any kind.

Stdlib only — ``dataclasses``, not ``pydantic``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["invalid", "unreadable", "gap"]

#: Every severity, in report order. `Report.counts` always carries all three.
SEVERITIES: tuple[Severity, ...] = ("invalid", "unreadable", "gap")

#: The severities that fail the run. `gap` is deliberately absent.
FAILING: frozenset[Severity] = frozenset({"invalid", "unreadable"})


@dataclass(frozen=True)
class Finding:
    """One thing a check observed about one file.

    :param severity: ``invalid`` / ``unreadable`` / ``gap`` — see the module
        docstring; only the first two fail the run.
    :param check: The emitting check family (e.g. ``tables``, ``frontmatter``),
        so a reader can tell which rule fired.
    :param file: The repo-relative path the finding is about.
    :param message: What is wrong, stated as an observed fact.
    :param remedy: The concrete next action that would resolve it.
    """

    severity: Severity
    check: str
    file: str
    message: str
    remedy: str


@dataclass
class Report:
    """Everything the checks observed in one run.

    :param findings: The findings, in the order the checks emitted them.
    """

    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether the repo is in a valid state — gaps alone keep this ``True``."""
        return not any(finding.severity in FAILING for finding in self.findings)

    @property
    def exit_code(self) -> int:
        """The process exit code: ``0`` when `ok`, else ``1``."""
        return 0 if self.ok else 1

    @property
    def counts(self) -> dict[str, int]:
        """Findings per severity.

        :returns: A count for **every** severity, including zeroes — a missing
            key would read as "no such severity" rather than "none found".
        """
        counts: dict[str, int] = dict.fromkeys(SEVERITIES, 0)
        for finding in self.findings:
            counts[finding.severity] += 1
        return counts

    def to_json(self) -> dict[str, Any]:
        """Render the report as the JSON payload the CLI prints.

        :returns: ``ok`` / ``counts`` / ``findings``, matching the
            ``{"ok": ...}``-first shape the other commands emit.
        """
        return {
            "ok": self.ok,
            "counts": self.counts,
            "findings": [asdict(finding) for finding in self.findings],
        }
