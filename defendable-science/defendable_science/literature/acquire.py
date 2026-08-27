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
from typing import TYPE_CHECKING, Any, Protocol

from defendable_science.literature.graph import OPENALEX

if TYPE_CHECKING:
    from defendable_science.core.download import FetchedBytes
    from defendable_science.literature.registry import Entry

    class HttpClient(Protocol):
        """The subset of :class:`~defendable_science.core.http.HttpClient` rungs 4-6 need.

        A narrow structural type — like :class:`~defendable_science.core.http.Response`
        and :class:`~defendable_science.core.http.Session` in ``core.http`` — rather
        than a hard dependency on the concrete client, so a rung is exercised with any
        stand-in that shapes up, without touching the network.
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


def candidate_from_work(work: dict[str, Any], url: str, rung: str) -> Candidate:
    """Build a candidate carrying the work's own bibliographic metadata.

    :param work: The OpenAlex work the URL came from.
    :param url: The candidate PDF URL.
    :param rung: The rung that produced it.
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
    )


def _location_pdf_urls(work: dict[str, Any]) -> list[str]:
    """Return every ``pdf_url`` across the work's ``locations`` array.

    :param work: The OpenAlex work.
    :returns: The direct PDF URLs found across all locations, in record order.
    """
    locations = work.get("locations")
    if not isinstance(locations, list):
        return []
    out: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        url = location.get("pdf_url")
        if isinstance(url, str) and url.strip():
            out.append(url)
    return out


def landing_urls(work: dict[str, Any]) -> list[str]:
    """Return landing-page URLs that are shaped like a direct PDF link.

    OpenAlex marks a work ``closed`` when it has no ``pdf_url``, yet the landing
    page can *be* the PDF — Sill 1997's NeurIPS proceedings link is exactly this.
    Only ``.pdf``-suffixed links are offered, so the ladder does not download
    every HTML abstract page in the record.

    :param work: The OpenAlex work.
    :returns: Candidate landing URLs, in record order.
    """
    locations = work.get("locations")
    if not isinstance(locations, list):
        return []
    out: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        url = location.get("landing_page_url")
        if isinstance(url, str) and url.strip().lower().endswith(".pdf"):
            out.append(url)
    return out


def identity_candidates(work: dict[str, Any]) -> list[Candidate]:
    """Build rungs 1-3 for a work: best OA location, all locations, landing pages.

    These are *identity-derived* — the URLs come from the work the citekey already
    resolves to, so they carry the work's own metadata and bypass the gate.
    Deduplicated by URL, preserving first-seen rung order.

    :param work: The OpenAlex work.
    :returns: Candidates in ladder order.
    """
    best = (work.get("best_oa_location") or {}).get("pdf_url")
    ordered: list[tuple[str, str]] = []
    if isinstance(best, str) and best.strip():
        ordered.append((best, RUNG_OA_BEST))
    ordered += [(url, RUNG_OA_LOCATIONS) for url in _location_pdf_urls(work)]
    ordered += [(url, RUNG_OA_LANDING) for url in landing_urls(work)]
    seen: set[str] = set()
    out: list[Candidate] = []
    for url, rung in ordered:
        if url in seen:
            continue
        seen.add(url)
        out.append(candidate_from_work(work, url, rung))
    return out


# --- search-derived rungs (4-6) ---------------------------------------------

ARXIV_API = "http://export.arxiv.org/api/query"

#: How many search hits each gated rung will consider.
SEARCH_LIMIT = 10


def sibling_candidates(
    entry: Entry, work: dict[str, Any], *, client: HttpClient
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


def arxiv_candidates(entry: Entry, *, client: HttpClient) -> list[Candidate]:
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
        out.append(candidate_from_work(work, template.format(**fields), RUNG_VENUE))
    return out
