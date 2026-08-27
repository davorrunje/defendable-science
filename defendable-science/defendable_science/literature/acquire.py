"""PDF acquisition for the literature registry — the ladder and the match gate.

Unlike ``dataset``, which verifies bytes against a checksum it already trusts,
this front-end *establishes* the checksum on first acquisition. The metadata gate
below stands where ``dataset`` has a pre-known hash, so it is load-bearing rather
than a nicety: a wrong PDF bound to a citekey is strictly worse than no PDF,
because ``digest``'s comprehension check verifies understanding of the bytes it
was given and will pass on the wrong paper.

Design: ``docs/superpowers/specs/2026-08-27-literature-asset-acquisition-design.md``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from defendable_science.literature.registry import Entry

# --- rungs ------------------------------------------------------------------

RUNG_OA_BEST = "openalex-best"
RUNG_OA_LOCATIONS = "openalex-locations"
RUNG_OA_LANDING = "openalex-landing"
RUNG_SIBLING = "sibling-version"
RUNG_ARXIV_SEARCH = "arxiv-search"
RUNG_VENUE = "venue-resolver"
RUNG_MANUAL = "manual"

#: Rungs whose candidates come from a *search* and therefore must pass the gate.
#: Rungs 1-3 are identity-derived — their URLs come from the OpenAlex work the
#: citekey already resolves to, so there is nothing to verify.
GATED_RUNGS = frozenset({RUNG_SIBLING, RUNG_ARXIV_SEARCH, RUNG_VENUE})

# --- verdicts ---------------------------------------------------------------

#: An ungated rung: identity was established by resolution, not by matching.
IDENTITY = "identity"
#: Gated and passed — bind the bytes.
ACCEPT = "accept"
#: Gated and plausible — land in quarantine, await a human ``confirm``.
QUARANTINE = "quarantine"
#: Gated and rejected — bind nothing.
REFUSE = "refuse"

#: Year windows: exact-or-±1 accepts; up to ±5 quarantines (preprint/journal lag).
ACCEPT_YEAR_WINDOW = 1
QUARANTINE_YEAR_WINDOW = 5

_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_SPACE = re.compile(r"\s+")


@dataclass
class Candidate:
    """A possible PDF for a registry entry, as reported by one rung.

    :param url: Where the bytes would come from.
    :param rung: Which rung produced it.
    :param title: The candidate's title, when the rung reported one.
    :param year: The candidate's publication year, when reported.
    :param first_author_family: The candidate's first-author family name.
    :param openalex: The candidate's OpenAlex id, when it has one.
    """

    url: str
    rung: str
    title: str | None = None
    year: int | None = None
    first_author_family: str | None = None
    openalex: str | None = None

    def as_json(self) -> dict[str, Any]:
        """Return the candidate as a JSON-ready object for the audit trail."""
        return {
            "url": self.url,
            "rung": self.rung,
            "title": self.title,
            "year": self.year,
            "first_author_family": self.first_author_family,
            "openalex": self.openalex,
        }


@dataclass
class MatchRecord:
    """The gate's verdict, per axis, so a refusal is explainable.

    :param verdict: :data:`IDENTITY` | :data:`ACCEPT` | :data:`QUARANTINE` |
        :data:`REFUSE`.
    :param title: ``exact`` | ``containment`` | ``mismatch``, or ``None`` when the
        axis was not evaluated.
    :param author: ``exact`` | ``mismatch``, or ``None``.
    :param year: ``exact`` | ``within-1`` | ``within-5`` | ``mismatch``, or ``None``.
    :param reason: A human-readable explanation, set on any non-accepting verdict.
    """

    verdict: str
    title: str | None = None
    author: str | None = None
    year: str | None = None
    reason: str | None = None

    def as_json(self) -> dict[str, Any]:
        """Return the record as a JSON-ready object for the audit trail."""
        return {
            "verdict": self.verdict,
            "title": self.title,
            "author": self.author,
            "year": self.year,
            "reason": self.reason,
        }


def normalize_title(title: str) -> str:
    """Normalize a title for comparison — casefold, strip punctuation, collapse space.

    :param title: The raw title.
    :returns: The normalized form.
    """
    folded = unicodedata.normalize("NFKD", title).casefold()
    return _SPACE.sub(" ", _PUNCT.sub(" ", folded)).strip()


def fold_name(name: str) -> str:
    """Fold a personal name for comparison — casefold and drop diacritics.

    :param name: The raw name.
    :returns: The folded form.
    """
    decomposed = unicodedata.normalize("NFKD", name.strip().casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _title_axis(entry_title: str, candidate_title: str) -> str:
    """Compare titles: ``exact`` | ``containment`` | ``mismatch``.

    Containment is deliberately a **word-prefix** relationship, not a bare
    substring test: "Monotonic Networks" is a legitimate prefix of "Monotonic
    Networks for Tabular Data" (a main-title/subtitle pair), but it is also a
    trailing *substring* of "Smooth Min-Max Monotonic Networks" — an unrelated
    2023 paper by a different author. A naive ``in`` check on the normalized
    strings would call that second case "containment" too, which is exactly the
    false positive this gate exists to refuse. Word-prefix matching accepts the
    first and refuses the second.
    """
    left = normalize_title(entry_title)
    right = normalize_title(candidate_title)
    if left == right:
        return "exact"
    left_words = left.split()
    right_words = right.split()
    if left_words and right_words:
        shorter, longer = sorted((left_words, right_words), key=len)
        if longer[: len(shorter)] == shorter:
            return "containment"
    return "mismatch"


def _year_axis(entry_year: int, candidate_year: int) -> str:
    """Compare years: ``exact`` | ``within-1`` | ``within-5`` | ``mismatch``."""
    delta = abs(entry_year - candidate_year)
    if delta == 0:
        return "exact"
    if delta <= ACCEPT_YEAR_WINDOW:
        return "within-1"
    if delta <= QUARANTINE_YEAR_WINDOW:
        return "within-5"
    return "mismatch"


def evaluate_match(entry: Entry, candidate: Candidate) -> MatchRecord:
    """Judge a search-derived candidate against the registry entry.

    **First-author family name is a hard gate**: no candidate is ever accepted or
    quarantined across an author mismatch. That single rule is what refuses
    Igel 2023 for Sill 1997 while still accepting a genuine preprint/journal pair
    one year apart.

    Thin metadata on either side is a **refusal**, not a title-only guess — an
    unverifiable candidate is exactly the case this gate exists for.

    :param entry: The registry entry the bytes would be bound to.
    :param candidate: The candidate under consideration.
    :returns: The per-axis record and the verdict.
    """
    if (
        entry.title is None
        or entry.year is None
        or entry.first_author_family is None
        or candidate.title is None
        or candidate.year is None
        or candidate.first_author_family is None
    ):
        return MatchRecord(
            verdict=REFUSE,
            reason=(
                "insufficient metadata to verify a search-derived candidate "
                "(title, year and first author are all required on both sides)"
            ),
        )

    title = _title_axis(entry.title, candidate.title)
    author = (
        "exact"
        if fold_name(entry.first_author_family)
        == fold_name(candidate.first_author_family)
        else "mismatch"
    )
    year = _year_axis(entry.year, candidate.year)
    record = MatchRecord(verdict=REFUSE, title=title, author=author, year=year)

    if author != "exact":
        record.reason = (
            f"first author {candidate.first_author_family!r} does not match "
            f"{entry.first_author_family!r} — a different paper, not a version"
        )
        return record
    if title == "exact" and year in ("exact", "within-1"):
        record.verdict = ACCEPT
        return record
    if title == "exact" and year == "within-5":
        record.verdict = QUARANTINE
        record.reason = (
            f"same title and author but {abs(entry.year - candidate.year)} years "
            "apart — plausibly a preprint, needs a human look"
        )
        return record
    if title == "containment" and year in ("exact", "within-1"):
        record.verdict = QUARANTINE
        record.reason = (
            "titles overlap but are not equal — plausibly the same work under a "
            "different subtitle, needs a human look"
        )
        return record
    record.reason = (
        f"title {title} and year {year} against the registry entry — not the same work"
    )
    return record
