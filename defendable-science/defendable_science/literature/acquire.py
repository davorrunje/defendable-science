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

import json
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, cast

from defendable_science.core.download import DownloadError, FetchedBytes
from defendable_science.core.fixity import (
    RetrievalError,
    bare_sha256,
    blob_path,
    sha256_file,
    verified,
)
from defendable_science.core.mirror import MirrorUnreachableError
from defendable_science.literature.graph import OPENALEX, resolve
from defendable_science.literature.registry import (
    Acquisition,
    Asset,
    AssetFile,
    License,
    MirrorRef,
    RegistryError,
    load_registry,
    load_triage,
    patch_asset,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from defendable_science.core.download import BytesFetcher
    from defendable_science.core.http import HttpClient
    from defendable_science.core.mirror import Mirror
    from defendable_science.literature.registry import Entry, Registry, TriageRow

    class SearchClient(Protocol):
        """The subset of :class:`~defendable_science.core.http.HttpClient` rungs 4-6 need.

        A narrow structural type — like :class:`~defendable_science.core.http.Response`
        and :class:`~defendable_science.core.http.Session` in ``core.http`` — rather
        than a hard dependency on the concrete client, so a rung is exercised with any
        stand-in that shapes up, without touching the network. Named distinctly from
        ``core.http.HttpClient`` rather than reusing that name: the two would otherwise
        collide asymmetrically (that one imports at runtime, this one is
        TYPE_CHECKING-only), and Task 14's ``cli.py`` will reference this type directly.
        """

        def get_json(
            self, url: str, params: dict[str, str] | None = None, *, s2: bool = False
        ) -> Any:
            """Return decoded JSON for `url`."""

        def get_text(
            self,
            url: str,
            params: dict[str, str] | None = None,
            *,
            headers: dict[str, str] | None = None,
        ) -> str:
            """Return the raw response body for `url`."""

    class MirrorClient(Protocol):
        """The subset of :class:`~defendable_science.core.mirror.Mirror` `mirror_entry` needs.

        A narrow structural type — like `SearchClient` above — rather than a
        hard dependency on the concrete `Mirror` dataclass, so a probe-and-push
        maintenance sweep is exercised with any stand-in that shapes up
        (a fake in tests, `Mirror` itself in production) without a `cast` at
        every call site. `mirror_entry` only ever probes and pushes; it never
        resolves bytes, so `get` is deliberately not part of this shape.
        """

        def check(self, sha256: str) -> bool:
            """Return whether the mirror holds the key.

            A stand-in must keep `Mirror`'s contract: ``False`` only when the
            mirror answered that the key is absent, and a raise (a
            :class:`~defendable_science.core.mirror.MirrorUnreachableError`, say)
            when it could not be asked.
            """

        def put(self, local: str | Path, sha256: str) -> None:
            """Copy `local` to the content-addressed mirror key."""

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
    :param license: The raw license string observed on the record the URL came
        from, when it reported one. Carried per-candidate rather than read off
        the anchor work at the end, because rung 4 serves bytes from a *sibling*
        work: recording the anchor's license for a sibling's bytes would be a
        provenance lie, and licenses genuinely differ between a preprint and its
        published version.
    """

    url: str
    rung: str
    title: str | None = None
    year: int | None = None
    first_author_family: str | None = None
    openalex: str | None = None
    license: str | None = None

    def as_json(self) -> dict[str, Any]:
        """Return the candidate as a JSON-ready object for the audit trail.

        :returns: The JSON-ready object.
        """
        return {
            "url": self.url,
            "rung": self.rung,
            "title": self.title,
            "year": self.year,
            "first_author_family": self.first_author_family,
            "openalex": self.openalex,
            "license": self.license,
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
        """Return the record as a JSON-ready object for the audit trail.

        :returns: The JSON-ready object.
        """
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
    unverifiable candidate is exactly the case this gate exists for. That
    includes metadata that is present but *blank*: a title that normalizes to
    the empty string (e.g. all punctuation) or an author name that folds to
    the empty string carries no information to match on, so two such blanks
    must not be scored ``"exact"`` against each other. Refusing here does not
    lean on any other module's discipline about coercing blanks to ``None``
    — candidates from Task 9's arXiv/OpenAlex parsing carry no such guarantee.

    :param entry: The registry entry the bytes would be bound to.
    :param candidate: The candidate under consideration.
    :returns: The per-axis record and the verdict.
    """
    insufficient = MatchRecord(
        verdict=REFUSE,
        reason=(
            "insufficient metadata to verify a search-derived candidate "
            "(title, year and first author are all required on both sides)"
        ),
    )
    if (
        entry.title is None
        or entry.year is None
        or entry.first_author_family is None
        or candidate.title is None
        or candidate.year is None
        or candidate.first_author_family is None
    ):
        return insufficient
    if (
        not normalize_title(entry.title)
        or not normalize_title(candidate.title)
        or not fold_name(entry.first_author_family)
        or not fold_name(candidate.first_author_family)
    ):
        return insufficient

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


# --- observed license --------------------------------------------------------

#: What reported the license. Every observation here comes from the OpenAlex work
#: record (``best_oa_location`` / ``primary_location`` / ``locations[]``), so the
#: provenance recorded is the source, not the ladder rung: a rung only chooses
#: *which work's* record was read, which the candidate's own ``openalex`` id
#: already records.
LICENSE_SOURCE = "openalex"

#: SPDX ids whose licenses permit redistributing the bytes. Deliberately short and
#: **not configurable**: whether a license grants redistribution is a compliance
#: judgement, and a consumer overriding it in config would be the plugin quietly
#: sanctioning a republication it cannot vouch for (spec §6).
#:
#: Non-commercial variants are deliberately absent. "NC" is not a redistribution
#: grant for an in-repo copy of a paper, and an ``-nd`` (no-derivatives) or
#: ``-nc-nd`` id is not one either. Anything not listed — including an absent or
#: unparsable license, which is the *majority* case (36 of 50 works in the run
#: that motivated this feature carried no license field at all) — is
#: ``redistributable: false``.
PERMISSIVE_SPDX = frozenset(
    {
        "cc0-1.0",
        "cc-by",
        "cc-by-3.0",
        "cc-by-4.0",
        "cc-by-sa",
        "cc-by-sa-3.0",
        "cc-by-sa-4.0",
        "mit",
        "apache-2.0",
        "bsd-2-clause",
        "bsd-3-clause",
    }
)


def is_permissive(spdx: str | None) -> bool:
    """Return whether an SPDX id is on the shipped redistribution allowlist.

    Absent, blank, or unrecognized means ``False`` — the safe direction, and by
    far the common one. A license we do not recognize is not a license we may
    redistribute under.

    :param spdx: The reported SPDX id, in any case, or ``None``.
    :returns: Whether the bytes may be republished (e.g. copied into a repo).
    """
    if spdx is None:
        return False
    return spdx.strip().lower() in PERMISSIVE_SPDX


def _license_from_observed(raw: str | None) -> License:
    """Build the recorded license from a raw reported identifier.

    ``id`` is the reported identifier normalized (stripped, casefolded) — what
    the source *called* it. Recording it is not an assertion that it is a valid
    SPDX id, and it is never what drives redistribution: only
    :data:`PERMISSIVE_SPDX` does that, so an unrecognized id such as
    ``all-rights-reserved`` is preserved verbatim in ``observed`` while staying
    non-redistributable.

    :param raw: The license string as reported, or ``None`` when none was.
    :returns: The observed license (all-``None`` when nothing was reported).
    """
    if raw is None or not raw.strip():
        return License()
    return License(id=raw.strip().lower(), observed=raw.strip(), source=LICENSE_SOURCE)


def _observed_license(work: dict[str, Any], location: Any = None) -> str | None:
    """Return the license reported for the record a candidate's URL came from.

    When the URL was read out of a specific ``locations[]`` entry, **that
    entry's own ``license`` is authoritative, including its absence.** OpenAlex
    reports the license per location, so a work whose ``best_oa_location`` is
    ``cc-by`` may hold a second, unlicensed copy — and rungs 2 and 3 download
    exactly those other copies. Falling back to the work-level value there would
    manufacture a redistribution grant nobody gave, and ``committable[]`` is a
    rights assertion a human may act on by copying the bytes into a repository.
    An unlicensed location is therefore an *observation of no license*, never a
    gap to be filled from a sibling location.

    Only a caller with no originating location falls back to the work-level
    scan: rung 6's consumer-configured templates name the anchor *work* rather
    than one of its copies, so the work-level observation is the best there is.
    There, ``best_oa_location`` and ``primary_location`` come before the full
    ``locations[]`` array, being the records OpenAlex itself calls canonical.

    :param work: The OpenAlex work.
    :param location: The ``locations[]`` record the URL came from, if any.
    :returns: The raw license string, or ``None`` when none was reported.
    """
    if isinstance(location, dict):
        raw = location.get("license")
        return raw if isinstance(raw, str) and raw.strip() else None
    blocks: list[Any] = [work.get("best_oa_location"), work.get("primary_location")]
    locations = work.get("locations")
    if isinstance(locations, list):
        blocks += locations
    for block in blocks:
        if not isinstance(block, dict):
            continue
        raw = block.get("license")
        if isinstance(raw, str) and raw.strip():
            return raw
    return None


# --- identity-derived rungs (1-3) and PDF acceptance -------------------------

#: The PDF magic-byte prefix. Authoritative over ``Content-Type``, which lies.
PDF_MAGIC = b"%PDF-"


def looks_like_pdf(fetched: FetchedBytes) -> bool:
    """Return whether the landed bytes are a PDF.

    ``Content-Type: application/pdf`` is trusted, but its absence is not
    disqualifying: Sill 1997's ``papers.nips.cc`` landing URL serves a real PDF
    under ``text/html``, and that case is precisely what the landing-page rung
    exists to recover. So the magic-byte prefix is the fallback and the
    tie-breaker. An unreadable file is *not* a PDF rather than an exception — the
    ladder moves on.

    :param fetched: The landed bytes.
    :returns: Whether they should be treated as a PDF.
    """
    if fetched.media_type == "application/pdf":
        return True
    try:
        with fetched.path.open("rb") as handle:
            return handle.read(len(PDF_MAGIC)) == PDF_MAGIC
    except OSError:
        return False


def _short_id(url: str | None) -> str | None:
    """Reduce an OpenAlex entity URL to its bare id (``…/W123`` → ``W123``).

    :param url: The full OpenAlex entity URL, or ``None``.
    :returns: The bare id, or ``None`` when there was nothing to reduce.
    """
    if not url:
        return None
    return url.rstrip("/").rsplit("/", 1)[-1]


def _first_family_from_work(work: dict[str, Any]) -> str | None:
    """Return the first author's family name from an OpenAlex work.

    OpenAlex gives a single ``display_name`` per author, so the family name is
    taken as the last whitespace-separated token — correct for the overwhelming
    majority of Western-ordered names, and the gate compares it only against the
    registry's own ``family`` field, so a systematic parse quirk affects both
    sides of a real match equally.

    :param work: The OpenAlex work.
    :returns: The first author's family name, or ``None`` when it cannot be
        determined.
    """
    authorships = work.get("authorships")
    if not isinstance(authorships, list) or not authorships:
        return None
    first = authorships[0]
    if not isinstance(first, dict):
        return None
    author = first.get("author")
    if not isinstance(author, dict):
        return None
    display = author.get("display_name")
    if not isinstance(display, str) or not display.strip():
        return None
    return display.strip().rsplit(" ", 1)[-1]


def candidate_from_work(
    work: dict[str, Any], url: str, rung: str, location: Any = None
) -> Candidate:
    """Build a candidate carrying the work's own bibliographic metadata.

    :param work: The OpenAlex work the URL came from.
    :param url: The candidate PDF URL.
    :param rung: The rung that produced it.
    :param location: The ``locations[]`` record the URL was read from, when there
        was one. OpenAlex reports the license **per location**, and it is the
        copy we download that governs — see :func:`_observed_license`.
    :returns: The candidate.
    """
    year = work.get("publication_year")
    title = work.get("display_name") or work.get("title")
    return Candidate(
        url=url,
        rung=rung,
        title=title if isinstance(title, str) else None,
        year=year if isinstance(year, int) else None,
        first_author_family=_first_family_from_work(work),
        openalex=_short_id(work.get("id")),
        license=_observed_license(work, location),
    )


def _location_urls(
    work: dict[str, Any], key: str, keep: Callable[[str], bool]
) -> list[tuple[str, dict[str, Any]]]:
    """Return each usable `key` URL across ``locations``, with its own record.

    The location record travels with the URL because the license is reported
    per location, not per work: a work whose ``best_oa_location`` is ``cc-by``
    may hold a second, unlicensed copy, and the bytes we actually download are
    governed by *their* location.

    :param work: The OpenAlex work.
    :param key: The location field to read (``pdf_url`` / ``landing_page_url``).
    :param keep: Predicate deciding whether a URL is worth offering.
    :returns: ``(url, location)`` pairs in record order.
    """
    locations = work.get("locations")
    if not isinstance(locations, list):
        return []
    out: list[tuple[str, dict[str, Any]]] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        url = location.get(key)
        if isinstance(url, str) and keep(url):
            out.append((url, location))
    return out


def _location_pdf_urls(work: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return every ``pdf_url`` across the work's ``locations`` array.

    :param work: The OpenAlex work.
    :returns: ``(url, location)`` pairs for the direct PDF URLs, in record order.
    """
    return _location_urls(work, "pdf_url", lambda url: bool(url.strip()))


def _landing_locations(work: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return PDF-shaped landing URLs with the location records they came from.

    :param work: The OpenAlex work.
    :returns: ``(url, location)`` pairs, in record order.
    """
    return _location_urls(
        work, "landing_page_url", lambda url: url.strip().lower().endswith(".pdf")
    )


def landing_urls(work: dict[str, Any]) -> list[str]:
    """Return landing-page URLs that are shaped like a direct PDF link.

    OpenAlex marks a work ``closed`` when it has no ``pdf_url``, yet the landing
    page can *be* the PDF — Sill 1997's NeurIPS proceedings link is exactly this.
    Only ``.pdf``-suffixed links are offered, so the ladder does not download
    every HTML abstract page in the record.

    :param work: The OpenAlex work.
    :returns: Candidate landing URLs, in record order.
    """
    return [url for url, _location in _landing_locations(work)]


def identity_candidates(work: dict[str, Any]) -> list[Candidate]:
    """Build rungs 1-3 for a work: best OA location, all locations, landing pages.

    These are *identity-derived* — the URLs come from the work the citekey already
    resolves to, so they carry the work's own metadata and bypass the gate.
    Deduplicated by URL, preserving first-seen rung order.

    :param work: The OpenAlex work.
    :returns: Candidates in ladder order.
    """
    best_location = work.get("best_oa_location")
    best = (best_location or {}).get("pdf_url")
    ordered: list[tuple[str, str, Any]] = []
    if isinstance(best, str) and best.strip():
        ordered.append((best, RUNG_OA_BEST, best_location))
    ordered += [(url, RUNG_OA_LOCATIONS, loc) for url, loc in _location_pdf_urls(work)]
    ordered += [(url, RUNG_OA_LANDING, loc) for url, loc in _landing_locations(work)]
    seen: set[str] = set()
    out: list[Candidate] = []
    for url, rung, location in ordered:
        if url in seen:
            continue
        seen.add(url)
        out.append(candidate_from_work(work, url, rung, location))
    return out


# --- search-derived rungs (4-6) ---------------------------------------------

ARXIV_API = "https://export.arxiv.org/api/query"

#: How many search hits each gated rung will consider.
SEARCH_LIMIT = 10


def sibling_candidates(
    entry: Entry, work: dict[str, Any], *, client: SearchClient
) -> list[Candidate]:
    """Rung 4 — find other OpenAlex works with a related title and mine their PDFs.

    OpenAlex often holds a paper twice: once as the published version (which may
    be ``closed`` with no PDF) and once as the preprint (``green``, with one). The
    registry entry resolves to whichever the DOI names, so the PDF can be on the
    sibling. This finds it generically, and the gate decides whether the sibling
    really is the same paper.

    The pre-filter here deliberately uses the **same title relation as the gate**
    (:func:`_title_axis`'s exact-or-word-prefix-containment) rather than strict
    equality. A stricter pre-filter would discard a genuine sibling whose journal
    version added a subtitle before the gate ever saw it — even though the gate's
    ``containment`` → ``quarantine`` rule exists precisely to route that case to a
    human. A pre-filter must never preempt the adjudicator: rung 4 proposes,
    :func:`evaluate_match` disposes.

    :param entry: The registry entry (its title drives the search).
    :param work: The anchor work, excluded from the results.
    :param client: The HTTP client.
    :returns: Candidates from every title-related sibling, gated downstream.
    """
    if entry.title is None:
        return []
    anchor = _short_id(work.get("id"))
    page = client.get_json(
        f"{OPENALEX}/works",
        {"filter": f"title.search:{entry.title}", "per-page": str(SEARCH_LIMIT)},
    )
    if not isinstance(page, dict):
        return []
    out: list[Candidate] = []
    for sibling in page.get("results", []):
        if not isinstance(sibling, dict):
            continue
        if _short_id(sibling.get("id")) == anchor:
            continue
        title = sibling.get("display_name")
        if not isinstance(title, str) or _title_axis(entry.title, title) == "mismatch":
            continue
        for candidate in identity_candidates(sibling):
            candidate.rung = RUNG_SIBLING
            out.append(candidate)
    return out


def parse_arxiv_feed(xml: str) -> list[Candidate]:
    """Parse an arXiv Atom feed into candidates.

    An entry missing an id, a title, an author, or a date is skipped: the gate
    needs all three axes, so an unverifiable hit is worse than no hit. Malformed
    XML yields no candidates — arXiv served something unusable, and the caller
    reports an exhausted rung rather than crashing.

    :param xml: The Atom feed body.
    :returns: One candidate per usable entry.
    """
    from xml.etree import ElementTree  # nosec B405 - parsing a trusted API feed

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ElementTree.fromstring(xml)  # nosec B314 - see above
    except ElementTree.ParseError:
        return []
    out: list[Candidate] = []
    for node in root.findall("atom:entry", ns):
        raw_id = node.findtext("atom:id", default="", namespaces=ns)
        title = node.findtext("atom:title", default="", namespaces=ns).strip()
        published = node.findtext("atom:published", default="", namespaces=ns)
        author = node.find("atom:author/atom:name", ns)
        name = (author.text or "").strip() if author is not None else ""
        arxiv_id = re.sub(r"v\d+$", "", raw_id.rstrip("/").rsplit("/", 1)[-1])
        if not (arxiv_id and title and name and published[:4].isdigit()):
            continue
        out.append(
            Candidate(
                url=f"https://arxiv.org/pdf/{arxiv_id}",
                rung=RUNG_ARXIV_SEARCH,
                title=title,
                year=int(published[:4]),
                first_author_family=name.rsplit(" ", 1)[-1],
            )
        )
    return out


def arxiv_candidates(entry: Entry, *, client: SearchClient) -> list[Candidate]:
    """Rung 5 — search arXiv by title and first author.

    :param entry: The registry entry.
    :param client: The HTTP client (used for its transport and politeness only;
        arXiv returns Atom XML, not JSON).
    :returns: Candidates, gated downstream.
    """
    if entry.title is None:
        return []
    query = f'ti:"{entry.title}"'
    if entry.first_author_family is not None:
        query += f' AND au:"{entry.first_author_family}"'
    body = client.get_text(
        ARXIV_API, {"search_query": query, "max_results": str(SEARCH_LIMIT)}
    )
    return parse_arxiv_feed(body)


def venue_candidates(
    entry: Entry, work: dict[str, Any], resolvers: list[Any]
) -> list[Candidate]:
    """Rung 6 — expand consumer-configured venue URL templates.

    **Ships empty.** The generic rungs recover the cases that motivated this
    feature, so no venue-specific logic is shipped in the plugin; a consumer repo
    that needs an exotic venue adds a ``{match, url_template}`` pair to its own
    ``.defendable-science/config.yml``. Templates may reference ``{openalex}``,
    ``{doi}`` and ``{year}``.

    .. warning::
       **The gate provides no protection on this rung.** These candidates are
       built from the *anchor work* — the one the citekey already resolves to —
       so :func:`evaluate_match` compares the registry entry against itself and
       cannot do anything but accept. What the URL actually serves is
       unconstrained by anything OpenAlex said, and the only real check standing
       between a consumer's template and a citekey is the ``%PDF-`` magic-byte
       test. A consumer configuring a resolver is vouching for the template.

    :param entry: The registry entry (supplies ``{doi}``).
    :param work: The anchor work (supplies the venue name, ``{openalex}``, ``{year}``).
    :param resolvers: The configured resolver list; malformed entries are skipped.
    :returns: Candidates, gated downstream.
    """
    venue = ((work.get("primary_location") or {}).get("source") or {}).get(
        "display_name"
    )
    if not isinstance(venue, str):
        venue = ""
    fields = {
        "openalex": _short_id(work.get("id")) or "",
        "doi": entry.doi or "",
        "year": str(entry.year or ""),
    }
    out: list[Candidate] = []
    for resolver in resolvers:
        if not isinstance(resolver, dict):
            continue
        pattern = resolver.get("match")
        template = resolver.get("url_template")
        if not isinstance(pattern, str) or not isinstance(template, str):
            continue
        try:
            matched = re.search(pattern, venue) is not None
        except re.error:
            continue
        if not matched:
            continue
        try:
            url = template.format(**fields)
        except (KeyError, IndexError, ValueError):
            # A malformed template (unknown field, bad format spec, positional
            # placeholder, ...) is hand-edited consumer config gone wrong, not
            # a crash: skip it like any other malformed resolver.
            continue
        out.append(candidate_from_work(work, url, RUNG_VENUE))
    return out


# --- outcome buckets ---------------------------------------------------------

#: Bytes already recorded and resolvable from the cache or the mirror.
BUCKET_CACHED = "cached"
#: Bytes newly acquired, hashed, stored and recorded on the entry.
BUCKET_FETCHED = "fetched"
#: Plausible bytes held for a human ``confirm``; nothing written to the registry.
BUCKET_QUARANTINED = "quarantined"
#: The ladder was exhausted — this is the human worklist, never a failure report.
BUCKET_MANUAL = "manual"
#: A tooling failure: something went wrong, not "this paper has no PDF".
#: Plural, unlike the others, because it names the report key the sweep
#: dispatches into (``report[outcome.bucket]``, spec §7).
BUCKET_ERROR = "errors"


@dataclass
class Outcome:
    """What happened to one entry, in the shape the sweep's report buckets take.

    One flat record for every bucket rather than a variant per bucket: the sweep
    dispatches with ``report[outcome.bucket]`` and serializes with
    :meth:`as_json`, so a uniform shape is what keeps that dispatch total.

    :param citekey: The entry this is about.
    :param bucket: One of the ``BUCKET_*`` constants.
    :param sha256: The bare checksum of the bound or quarantined bytes;
        ``None`` when nothing landed (including under ``--dry-run``).
    :param rung: The ladder rung that produced the bytes, when one did.
    :param url: Where the bytes came from, when they did.
    :param candidate: The candidate record, for the audit trail.
    :param match: The gate's per-axis record. On a ``manual`` outcome this is the
        *refusal* that came closest, so a human can see which axis failed.
    :param reason: Why, on any outcome that is not a plain success. Also carries
        a partial-success note (a mirror write that failed after the bytes were
        safely cached and recorded). Serialized as ``error`` rather than
        ``reason`` for a :data:`BUCKET_ERROR` outcome (spec §7's report shape),
        so a consumer reading ``errors[]`` never has to check two key spellings.
    :param tried: Rungs attempted, in order, each once.
    :param failures: Per-URL byte-layer failures, as
        ``{rung, url, status, error, blocking}`` — see :class:`_Ladder`. Empty on
        every outcome that never downloaded anything, and on any outcome that
        landed bytes. Populated on a ``manual`` row (the links that were dead)
        and on the ``errors`` row a blocked ladder produces (the reason the run
        cannot claim the paper has no PDF).
    :param landing_urls: Somewhere for a human to click, on a ``manual`` outcome.
    :param committable: Whether the observed license permits an in-repo copy.
        ``fetch`` never makes that copy (spec §6) — it only reports.
    :param path: Where the bytes are on disk: the blob for an acquisition, the
        quarantine PDF for a quarantine.
    :param license: The observed license identifier, when one was reported.
    """

    citekey: str
    bucket: str
    sha256: str | None = None
    rung: str | None = None
    url: str | None = None
    candidate: dict[str, Any] | None = None
    match: dict[str, Any] | None = None
    reason: str | None = None
    tried: list[str] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    landing_urls: list[str] = field(default_factory=list)
    committable: bool = False
    path: str | None = None
    license: str | None = None

    def as_json(self) -> dict[str, Any]:
        """Return the outcome as a JSON-ready report row.

        The ``reason`` field is renamed to ``error`` for a :data:`BUCKET_ERROR`
        outcome, matching the sweep's own synthesized error rows (unknown
        citekey, aborted-by-rate-limit) and spec §7's example report — a
        consumer reading ``errors[]`` should never have to check two key
        spellings for the same information.

        :returns: The JSON-ready object.
        """
        payload: dict[str, Any] = {
            "citekey": self.citekey,
            "bucket": self.bucket,
            "sha256": self.sha256,
            "rung": self.rung,
            "url": self.url,
            "candidate": self.candidate,
            "match": self.match,
            "reason": self.reason,
            "tried": list(self.tried),
            "failures": [dict(failure) for failure in self.failures],
            "landing_urls": list(self.landing_urls),
            "committable": self.committable,
            "path": self.path,
            "license": self.license,
        }
        if self.bucket == BUCKET_ERROR:
            payload["error"] = payload.pop("reason")
        return payload


@dataclass
class Context:
    """Everything one acquisition needs, injected rather than constructed.

    :param registry_path: The ``references.json`` to patch.
    :param triage_path: The ``triage.yml`` sidecar (read by the sweep).
    :param cache_dir: The content-addressed cache root.
    :param mirror: The configured mirror, or ``None``.
    :param client: The JSON HTTP client for metadata rungs.
    :param fetcher: The byte fetcher, injected so the ladder runs offline.
    :param max_bytes: Hard size ceiling per download.
    :param resolvers: Consumer-configured venue resolvers (rung 6; ships empty).
    :param today: ISO date recorded as the acquisition date.
    """

    registry_path: Path
    triage_path: Path
    cache_dir: Path
    mirror: Mirror | None
    client: HttpClient
    fetcher: BytesFetcher
    max_bytes: int
    resolvers: list[Any]
    today: str


@dataclass
class _Ladder:
    """Mutable state carried across one entry's ladder walk.

    :param tried: Rungs attempted, in order, each recorded once.
    :param refusal: The first gated candidate the gate refused, kept so an
        exhausted ladder can explain *which axis* failed rather than only that
        nothing was found. The first is kept rather than the last because rungs
        are walked best-first, so it is the closest thing to a match seen.
    :param failures: Every byte-layer failure, in the order it happened, as
        ``{rung, url, status, error, blocking}``. Nothing is discarded: a
        download that failed is the one thing an exhausted ladder must not
        forget, because "the fetch was blocked" and "the paper has no PDF" are
        the two readings this module exists to keep apart. ``blocking`` is true
        for a failure that leaves the question open (a ``403``, a ``5xx``, a
        dropped connection, an oversized body) and false for a hard miss
        (``404`` / ``410``), where the server did answer and its answer was
        "there is nothing here".
    """

    tried: list[str] = field(default_factory=list)
    refusal: tuple[Candidate, MatchRecord] | None = None
    failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def blocking(self) -> list[dict[str, Any]]:
        """Return the failures that forbid a ``manual`` verdict.

        :returns: The recorded failures whose cause was a block rather than an
            established absence.
        """
        return [failure for failure in self.failures if failure["blocking"]]


_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def _safe_name(citekey: str) -> str:
    """Reduce a citekey to a filename-safe token.

    Citekeys come from a human-authored ``references.json``; a realistic one is
    already safe and passes through unchanged. One containing a path separator
    would otherwise write outside the cache, which is not a risk worth carrying
    for a field nobody validates.

    :param citekey: The CSL ``id``.
    :returns: The same string with anything outside ``[A-Za-z0-9._-]`` replaced.
    """
    return _UNSAFE_NAME.sub("_", citekey)


def _quarantine_dir(cache_dir: Path, citekey: str) -> Path:
    """Return the quarantine directory for one entry.

    :param cache_dir: The content-addressed cache root.
    :param citekey: The entry the candidate was proposed for.
    :returns: ``<cache_dir>/quarantine/<citekey>``.
    """
    return cache_dir / "quarantine" / _safe_name(citekey)


def _write_quarantine(
    ctx: Context,
    entry: Entry,
    src: Path,
    sha: str,
    candidate: Candidate,
    match: MatchRecord,
) -> Path:
    """Park plausible-but-unproven bytes with the evidence a human needs.

    **Nothing is written to the registry** (spec §5.3): promotion is an explicit
    ``literature confirm --sha256``, and there is deliberately no "promote
    whatever is in quarantine" convenience.

    :param ctx: The acquisition context.
    :param entry: The entry the candidate was proposed for.
    :param src: The landed bytes, moved into quarantine.
    :param sha: Their bare checksum.
    :param candidate: The candidate record.
    :param match: The gate's per-axis record.
    :returns: Where the PDF was parked.
    """
    directory = _quarantine_dir(ctx.cache_dir, entry.citekey)
    directory.mkdir(parents=True, exist_ok=True)
    pdf = directory / f"{sha}.pdf"
    src.replace(pdf)
    (directory / f"{sha}.json").write_text(
        json.dumps(
            {
                "candidate": candidate.as_json(),
                "match": match.as_json(),
                "url": candidate.url,
                "rung": candidate.rung,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return pdf


def _store_blob(ctx: Context, src: Path, sha: str) -> Path:
    """Move landed bytes into the content-addressed store.

    Overwriting is safe and unconditional: the destination is derived from the
    bytes, so anything already there is the same bytes.

    :param ctx: The acquisition context.
    :param src: The landed bytes.
    :param sha: Their bare checksum.
    :returns: The blob path.
    """
    dest = blob_path(ctx.cache_dir, sha)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dest)
    return dest


def _mirror_key(mirror: Mirror, sha: str) -> str:
    """Return the mirror key for a checksum (mirrors ``Mirror``'s own layout).

    :param mirror: The configured mirror.
    :param sha: The bare checksum.
    :returns: ``<base_path>/sha256/<hash>``, without a leading slash.
    """
    return f"{mirror.base_path.rstrip('/')}/sha256/{sha}".lstrip("/")


def _populate_mirror(
    ctx: Context, blob: Path, sha: str
) -> tuple[MirrorRef | None, str | None]:
    """Push newly acquired bytes to the mirror, if one is configured.

    A mirror failure does **not** discard the acquisition: the bytes are already
    hashed and in the local store, so calling this an error would misreport an
    acquired paper. Nor is it swallowed — no ``mirror`` reference is recorded (the
    spine must not claim a copy that is not there) and the failure is returned as
    a note that travels with the outcome.

    :param ctx: The acquisition context.
    :param blob: The stored blob.
    :param sha: Its bare checksum.
    :returns: ``(mirror reference or None, failure note or None)``.
    """
    if ctx.mirror is None:
        return None, None
    try:
        ctx.mirror.put(blob, sha)
    except RetrievalError as exc:
        return None, (
            f"the bytes are cached and recorded, but the mirror write failed: {exc}"
        )
    return MirrorRef(remote=ctx.mirror.remote, key=_mirror_key(ctx.mirror, sha)), None


def _recorded(entry: Entry) -> tuple[Asset, str] | None:
    """Return the entry's already-recorded asset and checksum, if it has one.

    :param entry: The registry entry.
    :returns: ``(asset, bare checksum)``, or ``None`` when no bytes are recorded.
    """
    asset = entry.asset
    if asset is None or not asset.files:
        return None
    return asset, bare_sha256(asset.files[0].sha256)


def _cached_outcome(
    entry: Entry,
    asset: Asset,
    sha: str,
    *,
    rung: str | None = None,
    url: str | None = None,
    path: Path | None = None,
) -> Outcome:
    """Build the outcome for bytes that were already ours.

    :param entry: The registry entry.
    :param asset: Its recorded spine.
    :param sha: The bare checksum.
    :param rung: The rung that re-served the bytes, under ``--refetch``.
    :param url: Where they were re-served from, under ``--refetch``.
    :param path: The blob path, when known.
    :returns: A :data:`BUCKET_CACHED` outcome.
    """
    return Outcome(
        citekey=entry.citekey,
        bucket=BUCKET_CACHED,
        sha256=sha,
        rung=rung,
        url=url,
        committable=asset.redistributable,
        license=asset.license.id,
        path=None if path is None else str(path),
    )


def _resolve_recorded(entry: Entry, ctx: Context, asset: Asset, sha: str) -> Outcome:
    """Resolve an already-recorded checksum from the cache, then the mirror.

    **No network.** This is the substrate half of the fixity model (spec §4). An
    entry whose bytes are already identified by a checksum has nothing to
    acquire, so no acquisition rung runs and no metadata call is made —
    re-walking the ladder would risk rebinding a citekey to whatever the source
    happens to serve today.

    :param entry: The registry entry.
    :param ctx: The acquisition context.
    :param asset: Its recorded spine.
    :param sha: The recorded bare checksum.
    Bytes that fail verification are treated as absent (spec §9) *and deleted*:
    leaving a known-bad blob at the content-addressed path would have every
    later run re-read the same bad bytes. The refusal says which of the two
    situations occurred, because "the mirror is serving corrupt bytes" and "the
    mirror does not have it" are different problems with different fixes, and
    reporting the same sentence for both is the failure-honesty rule's exact
    complaint in miniature.

    A mirror that could not be *reached* is a third case and the one this
    function must be most careful with: it is a tooling failure, so it becomes
    an :data:`BUCKET_ERROR` row. Filing it as ``manual`` would put a paper that
    is very probably sitting in the mirror, behind an expired credential, on a
    human's hand-download worklist — and, because ``manual`` is a worklist and
    not a failure, would do so with ``complete: true`` and exit 0.

    :returns: :data:`BUCKET_CACHED` when the bytes are resolvable,
        :data:`BUCKET_ERROR` when a configured mirror could not be reached, and
        otherwise :data:`BUCKET_MANUAL` — the recorded bytes are gone, which is
        a fact about this paper and belongs on the human worklist.
    """
    blob = blob_path(ctx.cache_dir, sha)
    faults: list[str] = []
    if blob.is_file():
        if verified(blob, sha):
            return _cached_outcome(entry, asset, sha, path=blob)
        blob.unlink(missing_ok=True)
        faults.append(
            "the cached blob did not match the recorded checksum and was discarded"
        )
    try:
        from_mirror = ctx.mirror is not None and ctx.mirror.get(sha, blob)
    except MirrorUnreachableError as exc:
        return Outcome(
            citekey=entry.citekey,
            bucket=BUCKET_ERROR,
            sha256=sha,
            reason=(
                f"recorded checksum sha256:{sha} could not be resolved: "
                + ("; ".join(faults) + "; " if faults else "")
                + f"the mirror could not be reached to look for it: {exc}. This "
                "is a tooling failure, not a missing paper — the mirror may "
                "well hold these bytes."
            ),
        )
    if from_mirror:
        if verified(blob, sha):
            return _cached_outcome(entry, asset, sha, path=blob)
        blob.unlink(missing_ok=True)
        faults.append(
            "the mirror served bytes that do not match the recorded checksum, so "
            "the mirror copy is corrupt too"
        )
    detail = (
        "; ".join(faults)
        if faults
        else "it is not in the local cache, and not in the mirror either"
    )
    return Outcome(
        citekey=entry.citekey,
        bucket=BUCKET_MANUAL,
        sha256=sha,
        reason=(
            f"recorded checksum sha256:{sha} resolves to nothing — {detail}. "
            "Supply the bytes with 'literature confirm --file', or re-run with "
            "--refetch to acquire them again."
        ),
    )


def _identifier(entry: Entry) -> str | None:
    """Return the identifier to resolve this entry by.

    The recorded ``pid`` wins over the DOI: it is what a previous resolution
    settled on, so re-resolving through it cannot drift to a different work.

    :param entry: The registry entry.
    :returns: A DOI / OpenAlex id, or ``None`` when the entry carries neither.
    """
    pid = entry.asset.pid if entry.asset is not None else None
    if pid is None:
        return entry.doi
    return pid[len("openalex:") :] if pid.lower().startswith("openalex:") else pid


def _resolve_work(
    entry: Entry, ctx: Context
) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve an entry to the full OpenAlex work the ladder is built from.

    Two calls rather than one: :func:`~defendable_science.literature.graph.resolve`
    owns identifier classification and the honest miss/throttle distinction but
    returns a summary, and the ladder needs ``locations[]``. The client caches
    JSON responses, so the second call is free whenever the first was an OpenAlex
    id lookup.

    A miss is an **error**, not a ``manual`` row: we never looked for a PDF, so
    saying "download this by hand" would be a claim we did not earn.
    ``RateLimitError`` and ``HttpError`` are deliberately *not* caught — the sweep
    decides between aborting and an error row (spec §9).

    :param entry: The registry entry.
    :param ctx: The acquisition context.
    :returns: ``(work, None)`` on success, ``(None, reason)`` on a miss.
    :raises RateLimitError: If a provider throttles — never a "no PDF".
    :raises HttpError: On a transport failure the sweep must see.
    """
    identifier = _identifier(entry)
    if identifier is None:
        return None, (
            "no DOI and no recorded identifier on the entry — nothing to resolve; "
            "add a 'DOI' field to the registry entry first"
        )
    info = resolve(identifier, client=ctx.client)
    if not info.get("resolved"):
        return None, f"could not resolve {identifier!r}: {info.get('reason')}"
    work = ctx.client.get_json(f"{OPENALEX}/works/{info['openalex']}")
    if not isinstance(work, dict) or not work.get("id"):
        return None, (
            f"resolved {identifier!r} to {info['openalex']} but OpenAlex returned "
            "no usable work record for it"
        )
    return work, None


def _all_landing_urls(work: dict[str, Any]) -> list[str]:
    """Return every landing page on the work — the human's click targets.

    Wider than :func:`landing_urls`, deliberately: that one keeps only links
    shaped like a direct PDF, because rung 3 downloads them. This one feeds the
    ``manual`` worklist, where an ordinary HTML abstract page is exactly what a
    human wants.

    :param work: The OpenAlex work.
    :returns: Landing URLs in record order, deduplicated.
    """
    locations = work.get("locations")
    if not isinstance(locations, list):
        return []
    out: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        url = location.get("landing_page_url")
        if isinstance(url, str) and url.strip() and url not in out:
            out.append(url)
    return out


def _access_from_work(work: dict[str, Any]) -> str | None:
    """Return ``open`` / ``gated`` from the work's OA flag, or ``None`` if unstated.

    :param work: The OpenAlex work.
    :returns: The access class, or ``None`` when the record does not say.
    """
    is_oa = (work.get("open_access") or {}).get("is_oa")
    if is_oa is True:
        return "open"
    if is_oa is False:
        return "gated"
    return None


def _ladder(entry: Entry, work: dict[str, Any], ctx: Context) -> Iterator[Candidate]:
    """Yield every candidate in ladder order, lazily.

    A generator, not a list: rungs 4-6 each cost a network round trip, and the
    first accepted candidate wins, so an entry whose ``best_oa_location`` serves
    a PDF must not pay for a sibling search it will never look at.

    :param entry: The registry entry.
    :param work: The resolved anchor work.
    :param ctx: The acquisition context.
    :returns: Candidates, rungs 1-3 (identity-derived) before 4-6 (gated).
    """
    yield from identity_candidates(work)
    yield from sibling_candidates(entry, work, client=ctx.client)
    yield from arxiv_candidates(entry, client=ctx.client)
    yield from venue_candidates(entry, work, ctx.resolvers)


def _note(tried: list[str], rung: str) -> None:
    """Record that a rung was attempted, once.

    :param tried: The accumulator.
    :param rung: The rung attempted.
    """
    if rung not in tried:
        tried.append(rung)


def _gate(entry: Entry, candidate: Candidate, state: _Ladder) -> MatchRecord | None:
    """Adjudicate a candidate, or ``None`` to skip it.

    Rungs 1-3 are identity-derived and carry no match to make. Every other rung
    goes through :func:`evaluate_match` with no exceptions — that gate stands
    where ``dataset`` has a pre-known hash, so a rung that bypassed it would be
    binding unverified bytes to a citekey.

    :param entry: The registry entry.
    :param candidate: The candidate under consideration.
    :param state: The ladder state, which remembers the first refusal.
    :returns: The match record, or ``None`` when the candidate is refused.
    """
    if candidate.rung not in GATED_RUNGS:
        return MatchRecord(verdict=IDENTITY)
    record = evaluate_match(entry, candidate)
    if record.verdict == REFUSE:
        if state.refusal is None:
            state.refusal = (candidate, record)
        return None
    return record


def _land_bytes(
    ctx: Context, entry: Entry, candidate: Candidate, state: _Ladder
) -> FetchedBytes | None:
    """Download one candidate and check it really is a PDF.

    A :class:`~defendable_science.core.download.DownloadError` here is about
    *this URL* — a dead proceedings link, a 403, an oversized body — so it ends
    the candidate and nothing more. Ending the ladder on it would report "no PDF
    exists" on the strength of one broken link.

    But it is **recorded** on the ladder state before the walk goes on, with its
    status and its message, because the opposite mistake is worse: an exhausted
    ladder whose every rung was *blocked* knows nothing about whether the paper
    has a PDF, and :func:`_exhausted` needs the evidence to say so instead of
    filing a silent ``manual`` row. A ``403`` from a CDN that dislikes
    non-browser agents is a routine event on a real sweep.

    A **throttle** (``429``, or ``503`` with ``Retry-After``) is not per-URL at
    all — the host is telling us to stop — so it is raised as
    :class:`~defendable_science.core.http.RateLimitError`, the same signal the
    metadata layer already uses to abort the sweep (spec §9). Walking on would
    collect one 429 per remaining URL and then bucket the entry as if we had
    looked.

    :param ctx: The acquisition context.
    :param entry: The registry entry (names the scratch file).
    :param candidate: The candidate to download.
    :param state: The ladder state, which accumulates the failures.
    :returns: The landed PDF bytes, or ``None`` to move to the next candidate.
    :raises RateLimitError: If the byte host throttles us.
    """
    from defendable_science.core.http import RateLimitError

    dest = ctx.cache_dir / "incoming" / f"{_safe_name(entry.citekey)}.part"
    try:
        fetched = ctx.fetcher(candidate.url, dest, ctx.max_bytes)
    except DownloadError as exc:
        if exc.rate_limited:
            raise RateLimitError(
                f"{candidate.rung} throttled while downloading bytes: {exc}"
            ) from exc
        state.failures.append(
            {
                "rung": candidate.rung,
                "url": candidate.url,
                "status": exc.status,
                "error": str(exc),
                "blocking": not exc.hard_miss,
            }
        )
        return None
    if looks_like_pdf(fetched):
        return fetched
    fetched.path.unlink(missing_ok=True)
    return None


def _dry_run_outcome(
    entry: Entry, candidate: Candidate, match: MatchRecord, state: _Ladder
) -> Outcome:
    """Report the rung that would yield bytes, without fetching or writing.

    :param entry: The registry entry.
    :param candidate: The first candidate that passed the gate.
    :param match: Its match record.
    :param state: The ladder state.
    :returns: The would-be outcome, with ``sha256`` unset — no bytes were hashed,
        so claiming a checksum would be inventing one.
    """
    return Outcome(
        citekey=entry.citekey,
        bucket=(BUCKET_QUARANTINED if match.verdict == QUARANTINE else BUCKET_FETCHED),
        sha256=None,
        rung=candidate.rung,
        url=candidate.url,
        candidate=candidate.as_json(),
        match=match.as_json(),
        tried=state.tried,
        committable=is_permissive(candidate.license),
        license=_license_from_observed(candidate.license).id,
    )


def _refetch_outcome(
    entry: Entry,
    ctx: Context,
    asset: Asset,
    candidate: Candidate,
    fetched: FetchedBytes,
    sha: str,
    recorded: str,
) -> Outcome:
    """Compare re-acquired bytes against the recorded checksum.

    Drift **refuses**. A citekey's identity is what the recorded bytes say it is,
    so a source now serving different bytes — a new arXiv version, a corrected
    proof, a replaced file — is a decision for a human, not a side effect of
    re-running a command. The registry is left untouched.

    :param entry: The registry entry.
    :param ctx: The acquisition context.
    :param asset: The recorded spine.
    :param candidate: The candidate that served the bytes.
    :param fetched: The landed bytes.
    :param sha: Their bare checksum.
    :param recorded: The checksum already on the entry.
    :returns: :data:`BUCKET_CACHED` when the bytes are the recorded ones,
        :data:`BUCKET_ERROR` describing the drift when they are not.
    """
    if sha != recorded:
        fetched.path.unlink(missing_ok=True)
        return Outcome(
            citekey=entry.citekey,
            bucket=BUCKET_ERROR,
            sha256=sha,
            rung=candidate.rung,
            url=candidate.url,
            candidate=candidate.as_json(),
            reason=(
                f"refetch drift: recorded {recorded} but source now serves {sha} "
                "— a citekey is not rebound silently; confirm --file if the new "
                "version is intended"
            ),
        )
    blob = _store_blob(ctx, fetched.path, sha)
    return _cached_outcome(
        entry, asset, sha, rung=candidate.rung, url=candidate.url, path=blob
    )


def _bind(
    entry: Entry,
    ctx: Context,
    fetched: FetchedBytes,
    sha: str,
    *,
    rung: str,
    url: str | None,
    candidate: dict[str, Any] | None,
    match: dict[str, Any],
    license: License,
    pid: str | None = None,
    access: str | None = None,
) -> Outcome:
    """Write one asset spine: store the blob, mirror it, patch the registry.

    The one place in the module that writes a spine. :func:`_accept` (an
    accepted ladder candidate), :func:`confirm_quarantined` (a human-reviewed
    quarantine blob) and :func:`adopt_file` (a human-supplied file) each land
    bytes by a different route, but all three converge here rather than
    repeating the "hash, store, mirror, patch" tail three times — a second
    writer is how the recorded provenance and the actual bytes on disk drift
    apart.

    :param entry: The registry entry to bind the bytes to.
    :param ctx: The acquisition context.
    :param fetched: The bytes to bind. Moved into the content-addressed store
        by this call — a caller wanting copy semantics (:func:`adopt_file`)
        must already have copied the human's file before this runs.
    :param sha: The bytes' bare checksum.
    :param rung: The ladder rung recorded on the acquisition (``manual`` for
        an adoption, the original rung for a promoted quarantine candidate).
    :param url: Where the bytes came from, when they came from anywhere.
    :param candidate: The candidate record for the audit trail, or ``None``
        when there was no candidate (an adopted file).
    :param match: The gate's per-axis record, JSON-ready.
    :param license: The observed license.
    :param pid: The persistent identifier to record, when one is known.
    :param access: ``open`` | ``gated``, when known.
    :returns: :data:`BUCKET_FETCHED`, or :data:`BUCKET_ERROR` if the registry
        could not be patched — the bytes are cached either way, and saying so is
        the difference between a recoverable state and a lost one.
    """
    blob = _store_blob(ctx, fetched.path, sha)
    mirror_ref, mirror_note = _populate_mirror(ctx, blob, sha)
    asset = Asset(
        pid=pid,
        files=[
            AssetFile(
                path=f"sha256/{sha}",
                sha256=f"sha256:{sha}",
                size=fetched.size,
                media_type=fetched.media_type,
            )
        ],
        license=license,
        redistributable=is_permissive(license.id),
        access=access,
        mirror=mirror_ref,
        acquisition=Acquisition(
            rung=rung,
            url=url,
            candidate=candidate or {},
            match=match,
            fetched=ctx.today,
        ),
    )
    try:
        patch_asset(ctx.registry_path, entry.citekey, asset)
    except RegistryError as exc:
        return Outcome(
            citekey=entry.citekey,
            bucket=BUCKET_ERROR,
            sha256=sha,
            rung=rung,
            url=url,
            path=str(blob),
            reason=(
                f"acquired {sha} but could not record it: {exc} — the bytes are "
                "in the cache, so re-run once the registry is readable"
            ),
        )
    return Outcome(
        citekey=entry.citekey,
        bucket=BUCKET_FETCHED,
        sha256=sha,
        rung=rung,
        url=url,
        candidate=candidate,
        match=match,
        reason=mirror_note,
        committable=asset.redistributable,
        path=str(blob),
        license=license.id,
    )


def _accept(
    entry: Entry,
    ctx: Context,
    work: dict[str, Any],
    candidate: Candidate,
    match: MatchRecord,
    fetched: FetchedBytes,
    sha: str,
) -> Outcome:
    """Bind accepted bytes: store, mirror, record — trust established on first use.

    The checksum is *computed here and written back*, which is the one place this
    front-end differs from ``dataset``'s known-hash contract (spec §4). ``files``
    records a content-addressed blob path and never a repository path: ``fetch``
    does not add bytes to someone's git history on the strength of a scraped
    license field (spec §6).

    :param entry: The registry entry.
    :param ctx: The acquisition context.
    :param work: The resolved anchor work.
    :param candidate: The candidate that served the bytes.
    :param match: The gate's record (``identity`` for rungs 1-3).
    :param fetched: The landed bytes.
    :param sha: Their bare checksum.
    :returns: :data:`BUCKET_FETCHED`, or :data:`BUCKET_ERROR` if the registry
        could not be patched — the bytes are cached either way, and saying so is
        the difference between a recoverable state and a lost one.
    """
    return _bind(
        entry,
        ctx,
        fetched,
        sha,
        rung=candidate.rung,
        url=candidate.url,
        candidate=candidate.as_json(),
        match=match.as_json(),
        license=_license_from_observed(candidate.license),
        pid=f"openalex:{_short_id(work.get('id'))}",
        access=_access_from_work(work),
    )


def _try_candidate(
    entry: Entry,
    ctx: Context,
    work: dict[str, Any],
    candidate: Candidate,
    state: _Ladder,
    *,
    recorded: tuple[Asset, str] | None,
    dry_run: bool,
) -> Outcome | None:
    """Walk one candidate to a verdict, or ``None`` to continue the ladder.

    :param entry: The registry entry.
    :param ctx: The acquisition context.
    :param work: The resolved anchor work.
    :param candidate: The candidate under consideration.
    :param state: The ladder state.
    :param recorded: The already-recorded ``(asset, checksum)`` under
        ``--refetch``, or ``None`` on a first acquisition.
    :param dry_run: Report rather than download.
    :returns: A terminal outcome, or ``None`` when the ladder should go on.
    """
    _note(state.tried, candidate.rung)
    match = _gate(entry, candidate, state)
    if match is None:
        return None
    if dry_run:
        return _dry_run_outcome(entry, candidate, match, state)
    fetched = _land_bytes(ctx, entry, candidate, state)
    if fetched is None:
        return None
    sha = sha256_file(fetched.path)
    if recorded is not None:
        asset, previous = recorded
        return _refetch_outcome(entry, ctx, asset, candidate, fetched, sha, previous)
    if match.verdict == QUARANTINE:
        path = _write_quarantine(ctx, entry, fetched.path, sha, candidate, match)
        return Outcome(
            citekey=entry.citekey,
            bucket=BUCKET_QUARANTINED,
            sha256=sha,
            rung=candidate.rung,
            url=candidate.url,
            candidate=candidate.as_json(),
            match=match.as_json(),
            reason=match.reason,
            tried=state.tried,
            path=str(path),
        )
    return _accept(entry, ctx, work, candidate, match, fetched, sha)


def _failure_digest(failures: list[dict[str, Any]]) -> str:
    """Render per-URL byte-layer failures as one human-readable clause.

    :param failures: The recorded failures.
    :returns: ``"<rung> <url>: <error>"``, semicolon-separated, in the order the
        failures happened.
    """
    return "; ".join(
        f"{failure['rung']} {failure['url']}: {failure['error']}"
        for failure in failures
    )


def _exhausted(entry: Entry, work: dict[str, Any], state: _Ladder) -> Outcome:
    """Bucket a ladder that produced no bytes — ``manual`` only if it earned it.

    Two different endings, and keeping them apart is the whole point:

    - **Nothing was blocked.** Every rung was consulted and either offered
        nothing, served something that was not a PDF, or served a link the host
        answered as gone (``404`` / ``410``). That is a fact about the paper, so
        it is a :data:`BUCKET_MANUAL` row — the human worklist.
    - **Something was blocked.** At least one download failed for a reason that
        says nothing about the paper: a ``403``, a ``5xx``, a dropped connection,
        a body over the size cap. Then we did *not* look everywhere, so
        ``manual`` would be a claim we did not earn and the row is a
        :data:`BUCKET_ERROR` — which also makes ``fetch`` exit non-zero, so no CI
        loop reads the sweep as finished (spec §9).

    A throttle never reaches here at all: :func:`_land_bytes` raises
    :class:`~defendable_science.core.http.RateLimitError` and the sweep aborts.

    :param entry: The registry entry.
    :param work: The resolved anchor work.
    :param state: The ladder state.
    :returns: A :data:`BUCKET_MANUAL` outcome carrying the rungs tried, the
        landing URLs to click, the per-URL failures and the closest refusal if
        there was one — or a :data:`BUCKET_ERROR` outcome naming what blocked us.
    """
    candidate: dict[str, Any] | None = None
    match: dict[str, Any] | None = None
    refused_note = ""
    if state.refusal is not None:
        refused, record = state.refusal
        candidate, match = refused.as_json(), record.as_json()
        refused_note = f"; the closest candidate was refused: {record.reason}"
    blocking = state.blocking
    if blocking:
        reason = (
            f"the ladder produced no PDF, but {len(blocking)} of the URLs it "
            "tried failed in transport rather than reporting no PDF, so whether "
            "this paper has an obtainable PDF is unknown — this is not a "
            f"'no PDF exists' verdict: {_failure_digest(blocking)}. Retry once "
            "the source is reachable" + refused_note
        )
        bucket = BUCKET_ERROR
    else:
        reason = (
            "the acquisition ladder is exhausted — every rung was consulted and "
            "none served PDF bytes" + refused_note
        )
        bucket = BUCKET_MANUAL
    return Outcome(
        citekey=entry.citekey,
        bucket=bucket,
        reason=reason,
        tried=state.tried,
        failures=state.failures,
        landing_urls=_all_landing_urls(work),
        candidate=candidate,
        match=match,
    )


def acquire_one(
    entry: Entry, ctx: Context, *, refetch: bool = False, dry_run: bool = False
) -> Outcome:
    """Acquire the PDF for one registry entry.

    **Resolution before acquisition.** An entry that already records a checksum
    is a pure substrate resolution — cache, then mirror — and touches the network
    not at all. **Trust on first use, gated.** With no checksum recorded, the
    ladder runs and the checksum is established from the accepted bytes, with the
    match gate standing where ``dataset`` has a pre-known hash. **Drift refuses**
    (spec §4).

    Rate limits propagate to the caller rather than being bucketed here —
    whether they came from a metadata call or from a PDF host — and only a
    ladder that ran to the end **unblocked** means "no PDF was obtainable". A
    ladder every rung of which was blocked in transport is an
    :data:`BUCKET_ERROR`, not a ``manual`` row (:func:`_exhausted`).

    :param entry: The registry entry to acquire for.
    :param ctx: The acquisition context.
    :param refetch: Re-run the ladder even though a checksum is recorded, and
        refuse if the bytes have changed.
    :param dry_run: Report the rung that would yield bytes; fetch and write
        nothing.
    :returns: The outcome, in one of the ``BUCKET_*`` buckets.
    :raises RateLimitError: If a provider throttles a metadata call, or a PDF
        host throttles a byte download.
    :raises HttpError: On a metadata transport failure.
    :raises RetrievalError: If ``rclone`` is missing altogether, which is a
        configuration fault affecting every entry, not a fact about this paper.
        A mirror that is present but *unreachable* (credentials, quota,
        network) is per-entry and becomes an :data:`BUCKET_ERROR` outcome
        instead, so a sweep reports it and continues.
    """
    recorded = _recorded(entry)
    if recorded is not None and not refetch:
        return _resolve_recorded(entry, ctx, *recorded)
    work, reason = _resolve_work(entry, ctx)
    if work is None:
        return Outcome(citekey=entry.citekey, bucket=BUCKET_ERROR, reason=reason)
    state = _Ladder()
    for candidate in _ladder(entry, work, ctx):
        outcome = _try_candidate(
            entry, ctx, work, candidate, state, recorded=recorded, dry_run=dry_run
        )
        if outcome is not None:
            return outcome
    return _exhausted(entry, work, state)


# --- confirm: promote quarantine, or adopt a manual file ---------------------
#
# The two ways an entry that never got bound by `acquire_one` becomes bound
# anyway, both requiring an explicit human act (spec §7). Neither re-resolves
# the OpenAlex work: a quarantine promotion and a manual adoption record
# nothing beyond what the human is vouching for right now, so `pid` and
# `access` are left unset rather than reconstructed from a stale or absent
# anchor work.


def _quarantine_manifest(directory: Path) -> list[str]:
    """Return the bare checksums currently parked in a quarantine directory.

    :param directory: A citekey's quarantine directory (may not exist).
    :returns: Sorted bare checksums, one per parked ``.pdf``.
    """
    if not directory.is_dir():
        return []
    return sorted(pdf.stem for pdf in directory.glob("*.pdf"))


def confirm_quarantined(entry: Entry, ctx: Context, sha256: str) -> Outcome:
    """Promote a quarantined candidate after a human has reviewed it.

    The blob is verified against its own filename-hash before promotion — the
    quarantine file is named by the hash of its contents, so re-hashing it is
    a free integrity check, and it means a truncated or tampered quarantine
    file cannot be blessed into the registry. Nothing else about the
    candidate is re-examined: the gate already ran when the bytes were
    quarantined, and the human's ``confirm`` *is* the re-examination spec
    §5.3 asks for.

    :param entry: The registry entry the quarantined candidate was proposed for.
    :param ctx: The acquisition context.
    :param sha256: The checksum naming the quarantined candidate, prefixed or
        bare.
    :returns: :data:`BUCKET_FETCHED` on success. :data:`BUCKET_ERROR`, with
        quarantine left untouched, if the parked bytes no longer match their
        own filename-hash.
    :raises RetrievalError: If no quarantined candidate matches `sha256` for
        this citekey, naming what is actually in quarantine so the human can
        correct the checksum rather than read a lookup traceback.
    """
    bare = bare_sha256(sha256)
    directory = _quarantine_dir(ctx.cache_dir, entry.citekey)
    pdf = directory / f"{bare}.pdf"
    sidecar = directory / f"{bare}.json"
    if not pdf.is_file() or not sidecar.is_file():
        present = _quarantine_manifest(directory)
        available = (
            f"quarantine holds {present} for {entry.citekey!r}"
            if present
            else f"quarantine is empty for {entry.citekey!r}"
        )
        raise RetrievalError(
            f"no quarantined candidate {bare} for {entry.citekey!r} — {available}"
        )
    actual = sha256_file(pdf)
    if actual != bare:
        return Outcome(
            citekey=entry.citekey,
            bucket=BUCKET_ERROR,
            sha256=actual,
            path=str(pdf),
            reason=(
                f"quarantined file {pdf.name} now hashes to {actual}, not {bare} "
                "— truncated or tampered; refusing to promote it, quarantine "
                "left untouched"
            ),
        )
    data: dict[str, Any] = json.loads(sidecar.read_text(encoding="utf-8"))
    candidate = cast("dict[str, Any]", data["candidate"])
    match = cast("dict[str, Any]", data["match"])
    rung = cast("str", data["rung"])
    url = cast("str | None", data["url"])
    license = _license_from_observed(cast("str | None", candidate.get("license")))
    fetched = FetchedBytes(
        path=pdf, media_type="application/pdf", size=pdf.stat().st_size
    )
    outcome = _bind(
        entry,
        ctx,
        fetched,
        bare,
        rung=rung,
        url=url,
        candidate=candidate,
        match=match,
        license=license,
    )
    sidecar.unlink(missing_ok=True)
    return outcome


def adopt_file(entry: Entry, ctx: Context, path: Path) -> Outcome:
    """Record a PDF the human downloaded and verified themselves.

    This is what makes an exhausted ladder a workflow rather than a dead
    end (spec §5, §7): a human works the ``manual`` worklist by hand — a
    paywalled portal, an inter-library loan, a colleague's copy — and hands
    the result back with ``confirm --file``.

    **Copies, never moves.** `path` is the researcher's own file, most likely
    sitting in a Downloads folder; it must still be there after this
    returns, so the bytes are copied into a scratch location before anything
    is hashed or stored.

    The recorded license is all-``None`` and therefore non-redistributable:
    the tool observed nothing about the rights on a file it did not fetch
    from anywhere it could see, and an absent observation is never a grant
    (spec §6) — the same default every other unlicensed acquisition in this
    module gets.

    :param entry: The registry entry to bind the file to.
    :param ctx: The acquisition context.
    :param path: The human-supplied PDF.
    :returns: :data:`BUCKET_FETCHED` on success. A :data:`BUCKET_ERROR`
        outcome, with the registry left unchanged, when the file is not a PDF.
    :raises RetrievalError: If `path` does not exist — a plain, actionable
        message rather than a raw ``FileNotFoundError`` traceback.
    """
    if not path.is_file():
        raise RetrievalError(f"no file at {path} to adopt")
    dest = ctx.cache_dir / "incoming" / f"{_safe_name(entry.citekey)}.manual.part"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    fetched = FetchedBytes(path=dest, media_type=None, size=dest.stat().st_size)
    if not looks_like_pdf(fetched):
        dest.unlink(missing_ok=True)
        return Outcome(
            citekey=entry.citekey,
            bucket=BUCKET_ERROR,
            reason=(
                f"{path} does not look like a PDF (no %PDF- magic bytes and no "
                "application/pdf content type) — refusing to adopt it, the "
                "registry is unchanged"
            ),
        )
    fetched.media_type = "application/pdf"
    sha = sha256_file(dest)
    return _bind(
        entry,
        ctx,
        fetched,
        sha,
        rung=RUNG_MANUAL,
        url=None,
        candidate=None,
        match=MatchRecord(verdict=IDENTITY).as_json(),
        license=License(),
    )


# --- the sweep ----------------------------------------------------------------


def _select(
    registry: Registry,
    triage: dict[str, TriageRow],
    citekeys: list[str] | None,
    disposition: str | None,
) -> list[tuple[str, Entry | None, str | None]]:
    """Choose which citekeys to sweep, and in what order.

    ``disposition`` behaves differently depending on where the citekey list
    came from. For an **implicit** whole-registry sweep (``citekeys`` is
    ``None``), a citekey whose triage row does not match is silently
    excluded — that is the filter's entire purpose there. For an
    **explicitly**-named citekey, the same mismatch instead becomes an error
    row: the caller asked for that citekey by name, so silently dropping it
    would be indistinguishable from "it was processed and landed nowhere",
    which is exactly the ambiguity this module exists to refuse (spec §9).

    :param registry: The loaded registry.
    :param triage: The loaded triage sidecar, by citekey.
    :param citekeys: Explicit entries to attempt, in this order; the whole
        registry, in file order, when ``None``.
    :param disposition: Restrict to citekeys whose triage row carries this
        disposition.
    :returns: ``(citekey, entry, error)`` triples, in sweep order. ``error``
        is set when the row is an outright failure rather than something to
        attempt — an unknown citekey, or an explicitly-named citekey
        excluded by ``disposition`` — in which case ``entry`` carries no
        meaning and may be ``None``.
    """
    explicit = citekeys is not None
    keys = citekeys if citekeys is not None else [e.citekey for e in registry.entries]
    selected: list[tuple[str, Entry | None, str | None]] = []
    for key in keys:
        if disposition is not None:
            row = triage.get(key)
            if row is None or row.disposition != disposition:
                if explicit:
                    selected.append(
                        (
                            key,
                            None,
                            f"excluded by disposition={disposition!r} "
                            "(no matching triage row)",
                        )
                    )
                continue
        selected.append((key, registry.get(key), None))
    return selected


def fetch_all(
    ctx: Context,
    *,
    citekeys: list[str] | None = None,
    disposition: str | None = None,
    refetch: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Sweep the registry, bucketing every entry's outcome.

    A rate limit **aborts** the sweep with ``complete: false`` and a
    ``not_attempted`` count, because a throttle is not information about the
    remaining papers: reporting them as ``manual`` would tell a human to
    download by hand what the tool simply never asked for. That holds for a
    throttle from a *PDF host* exactly as it does for one from a metadata
    provider — arXiv and publisher CDNs throttle unattended sweeps, and the
    remaining entries are no more "manual" for it. Any other transport failure
    is per-entry — it lands in ``errors`` and the sweep continues.

    :param ctx: The acquisition context.
    :param citekeys: Explicit entries to attempt, in this order; the whole
        registry when ``None``. An entry named here that is not in the
        registry becomes an ``errors[]`` row rather than a crash.
    :param disposition: Restrict to entries whose ``triage.yml`` row carries
        this disposition. For the implicit whole-registry sweep, an entry
        with no matching row is excluded when this is given and included
        when it is not. An **explicitly**-named citekey excluded this way
        becomes an ``errors[]`` row instead of a silent drop — the caller
        asked for it by name, so a reader must be able to tell "processed"
        from "vanished".
    :param refetch: Re-run the ladder for entries that already have a
        checksum.
    :param dry_run: Report the rung that would yield bytes without
        downloading.
    :returns: The report — ``complete``, ``not_attempted``, and the
        ``fetched`` / ``cached`` / ``quarantined`` / ``manual`` /
        ``committable`` / ``errors`` buckets.
    :raises RegistryError: If the registry or the triage sidecar cannot be
        read.
    """
    from defendable_science.core.http import HttpError, RateLimitError

    registry = load_registry(ctx.registry_path)
    triage = load_triage(ctx.triage_path)
    targets = _select(registry, triage, citekeys, disposition)
    report: dict[str, Any] = {
        "complete": True,
        "not_attempted": 0,
        "fetched": [],
        "cached": [],
        "quarantined": [],
        "manual": [],
        "committable": [],
        "errors": [],
    }
    for index, (citekey, entry, error) in enumerate(targets):
        if error is not None or entry is None:
            report["errors"].append(
                {
                    "citekey": citekey,
                    "error": error or f"no entry {citekey!r} in the registry",
                }
            )
            continue
        try:
            outcome = acquire_one(entry, ctx, refetch=refetch, dry_run=dry_run)
        except RateLimitError as exc:
            report["errors"].append(
                {"citekey": citekey, "error": f"rate-limited, sweep aborted: {exc}"}
            )
            report["complete"] = False
            report["not_attempted"] = len(targets) - index - 1
            break
        except HttpError as exc:
            report["errors"].append({"citekey": citekey, "error": str(exc)})
            continue
        report[outcome.bucket].append(outcome.as_json())
        if outcome.committable:
            report["committable"].append(outcome.as_json())
    return report


# --- verify: offline fixity ---------------------------------------------------


@dataclass
class VerifyReport:
    """The outcome of :func:`verify_entry` for one registry entry.

    Mirrors ``dataset.retrieval.VerifyReport``'s shape exactly (spec §4: once
    a checksum is recorded, this front-end's fixity story is identical to
    ``dataset``'s — offline, re-hash, report). It adds one thing ``dataset``
    has no need for: a dataset manifest always declares the files an entry
    has, so "nothing is declared" cannot arise there. Literature instead
    *establishes* a checksum from the first acquisition (spec §4), so a
    bibliography entry nothing has been fetched for is a first-class,
    common report — not an empty one. That case is reported as `missing`
    with `note` naming it explicitly, and is never `ok`: an unfetched paper
    must not read as verified.

    :param citekey: The registry entry this report is about.
    :param verified: Files whose on-disk bytes matched the recorded checksum.
    :param missing: Files recorded but absent from the cache — including one
        sentinel string when the entry records no asset at all.
    :param corrupt: Files present but with a mismatched checksum, or present
        and unreadable (an ``OSError`` while hashing is folded in here rather
        than raised).
    :param note: ``None`` when the entry has a recorded asset; otherwise an
        explicit statement that no bytes have been recorded for this entry,
        so a reader cannot mistake "no asset at all" for "one oddly-named
        missing file" from `missing` alone.
    """

    citekey: str
    verified: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    corrupt: list[str] = field(default_factory=list)
    note: str | None = None

    @property
    def ok(self) -> bool:
        """Return whether every recorded file verified.

        An entry with nothing recorded is never ``ok``: ``verified`` empty
        with `missing` and `corrupt` also empty would otherwise read as
        vacuously clean — exactly the false assurance this report exists to
        refuse (``verify --all`` on a fresh registry must say "nothing is
        verified", not "everything checks out").

        :returns: Whether at least one file verified and none is missing or
            corrupt.
        """
        return bool(self.verified) and not self.missing and not self.corrupt

    def as_json(self) -> dict[str, Any]:
        """Return the report as a JSON-ready object for the audit trail.

        :returns: The JSON-ready object. ``note`` is present only when set.
        """
        payload: dict[str, Any] = {
            "citekey": self.citekey,
            "ok": self.ok,
            "verified": self.verified,
            "missing": self.missing,
            "corrupt": self.corrupt,
        }
        if self.note is not None:
            payload["note"] = self.note
        return payload


def verify_entry(entry: Entry, *, cache_dir: Path) -> VerifyReport:
    """Re-hash an entry's on-disk file(s) against the recorded checksum.

    **Offline. Never downloads.** This only re-hashes bytes already on disk
    and reports; it takes no client and no fetcher, matching
    ``dataset.retrieval.verify``'s contract exactly (spec §4).

    :param entry: The registry entry to verify.
    :param cache_dir: The content-addressed cache root.
    :returns: The per-file verification report. An entry with no recorded
        asset is reported as :attr:`VerifyReport.missing` with an explicit
        :attr:`VerifyReport.note` — never as :attr:`VerifyReport.ok` — because
        an unfetched paper must not read as verified. A present-but-unreadable
        file (``OSError`` while hashing) is folded into `corrupt` rather than
        raising, matching `dataset`'s own offline report.
    """
    report = VerifyReport(citekey=entry.citekey)
    asset = entry.asset
    if asset is None or not asset.files:
        report.note = "no asset recorded for this entry — nothing has been fetched yet"
        report.missing.append(report.note)
        return report
    for ref in asset.files:
        path = blob_path(cache_dir, ref.sha256)
        if not path.is_file():
            report.missing.append(ref.path)
            continue
        try:
            digest = sha256_file(path)
        except OSError:
            report.corrupt.append(ref.path)
            continue
        if digest == bare_sha256(ref.sha256):
            report.verified.append(ref.path)
        else:
            report.corrupt.append(ref.path)
    return report


# --- mirror: push to, or probe, the private mirror -----------------------------


def mirror_entry(
    entry: Entry, *, cache_dir: Path, mirror: MirrorClient, check_only: bool = False
) -> dict[str, Any]:
    """Push an entry's recorded file(s) to the mirror, or probe presence only.

    Probes the mirror before deciding what to do with each file: a copy
    already there is reported as such rather than re-pushed, and
    `check_only` never calls :meth:`Mirror.put` regardless of what the probe
    finds. A transport failure that `Mirror` *raises* — a missing ``rclone``
    binary, or a probe that failed for any reason other than the key being
    absent (an expired credential, a quota, an outage) — is not caught here:
    it propagates as the actionable ``RetrievalError`` /
    :class:`~defendable_science.core.mirror.MirrorUnreachableError`, because a
    transport failure and "no copy in the mirror" are different problems with
    different fixes. A `missing` entry therefore means the mirror was asked
    and answered.

    **A local blob is re-hashed before it is pushed.** Every other path that
    calls :meth:`Mirror.put` in this codebase does so immediately after
    hashing freshly-landed bytes (`_populate_mirror` here;
    ``dataset.retrieval``'s Tier-B hop is the same shape) — the bytes and the
    checksum are contemporaneous. A maintenance sweep has no such guarantee:
    the blob may have bit-rotted since acquisition, and spec §9 already
    names a corrupt cache blob as something to treat as absent, not as
    something to propagate. Pushing it anyway would turn the mirror — kept
    precisely as insurance against link rot and paywalls — into a second
    copy of the damage. A checksum mismatch is therefore routed to
    `corrupt`, not `missing`: the human's next action differs (investigate
    the local copy, most likely via `re-fetch`, rather than simply retry the
    push).

    :param entry: The registry entry to mirror. An entry with no recorded
        asset has nothing to push; it is reported entirely under `missing`.
    :param cache_dir: The content-addressed cache root, to find the local
        blob to push.
    :param mirror: The configured mirror (or any stand-in shaped like
        :class:`MirrorClient`).
    :param check_only: Probe presence without pushing anything.
    :returns: A JSON-ready per-file report: ``citekey``, ``pushed`` (newly
        pushed this call), ``already_present`` (the mirror already had it),
        ``missing`` (still not confirmed in the mirror after this call —
        because `check_only` skipped the push, because there is no local
        blob to push, or because the entry records no asset at all), and
        ``corrupt`` (a local blob whose bytes no longer match the recorded
        checksum — never pushed).
    :raises RetrievalError: If the mirror transport raises — a missing
        ``rclone`` binary, a push that fails, or a probe that could not reach
        the mirror — surfaced intact rather than folded into `missing`.
    """
    report: dict[str, Any] = {
        "citekey": entry.citekey,
        "pushed": [],
        "already_present": [],
        "missing": [],
        "corrupt": [],
    }
    asset = entry.asset
    if asset is None or not asset.files:
        report["missing"].append("no asset recorded for this entry — nothing to mirror")
        return report
    for ref in asset.files:
        sha = bare_sha256(ref.sha256)
        if mirror.check(sha):
            report["already_present"].append(sha)
            continue
        if check_only:
            report["missing"].append(sha)
            continue
        blob = blob_path(cache_dir, ref.sha256)
        if not blob.is_file():
            report["missing"].append(sha)
            continue
        try:
            digest = sha256_file(blob)
        except OSError:
            report["corrupt"].append(sha)
            continue
        if digest != sha:
            report["corrupt"].append(sha)
            continue
        mirror.put(blob, sha)
        report["pushed"].append(sha)
    return report
