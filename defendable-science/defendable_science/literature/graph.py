"""Citation-graph client over OpenAlex (+ Semantic Scholar) — defendable-science#1.

The read/enrich half of the ``literature`` substrate: resolve any id to a
canonical work, page forward citations and backward references, enrich with the
fields ranking turns on, and compute co-citation / bibliographic-coupling
neighbour sets. OpenAlex is the keyless backbone (identity anchor); Semantic
Scholar adds citation contexts / SciCite intents / ``isInfluential`` when a key is
configured, degrading to OpenAlex-only otherwise.

Every function takes an injected :class:`~defendable_science.core.http.HttpClient`, so
the module is exercised offline in tests. Design:
``docs/design/proposals/literature-citation-graph-client.md``.

.. note::
   Endpoint shapes follow the public OpenAlex / S2 documentation; the code is
   covered by mocked-transport tests. Validation against the live services is
   tracked in defendable-science#30.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING, Any

from pydantic import Field

from defendable_science.core.models import ExternalModel, parse_each, parse_obj

if TYPE_CHECKING:
    from defendable_science.core.http import HttpClient

OPENALEX = "https://api.openalex.org"
S2 = "https://api.semanticscholar.org/graph/v1"

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_OPENALEX_RE = re.compile(r"^[Ww]\d+$")
_ARXIV_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")


class _Source(ExternalModel):
    display_name: str | None = None


class _PrimaryLocation(ExternalModel):
    source: _Source | None = None


class _Author(ExternalModel):
    display_name: str | None = None


class _Authorship(ExternalModel):
    author: _Author | None = None


class _WorkIds(ExternalModel):
    arxiv: str | None = None


class OpenAlexWork(ExternalModel):
    """An OpenAlex work object, as far as this package reads it."""

    id: str | None = None
    doi: str | None = None
    ids: _WorkIds = Field(default_factory=_WorkIds)
    display_name: str | None = None
    title: str | None = None
    publication_year: int | None = None
    cited_by_count: int | None = None
    primary_location: _PrimaryLocation | None = None
    authorships: list[_Authorship] = Field(default_factory=list)
    abstract_inverted_index: dict[str, list[int]] | None = None
    referenced_works: list[str] = Field(default_factory=list)


class _PageMeta(ExternalModel):
    next_cursor: str | None = None


class WorksPage(ExternalModel):
    """One cursor-paginated page of the OpenAlex ``/works`` endpoint."""

    results: list[OpenAlexWork] = Field(default_factory=list)
    meta: _PageMeta = Field(default_factory=_PageMeta)


class _ExternalIdBundle(ExternalModel):
    doi: str | None = Field(default=None, alias="DOI")
    arxiv: str | None = Field(default=None, alias="ArXiv")
    corpus_id: int | str | None = Field(default=None, alias="CorpusId")


class S2ExternalIds(ExternalModel):
    """A Semantic Scholar paper's ``externalIds`` response."""

    external_ids: _ExternalIdBundle = Field(
        default_factory=_ExternalIdBundle, alias="externalIds"
    )


class S2CitationEdge(ExternalModel):
    """One incoming citation edge from S2's ``/citations`` endpoint."""

    contexts: list[str] = Field(default_factory=list)
    intents: list[str] = Field(default_factory=list)
    is_influential: bool = Field(default=False, alias="isInfluential")


class S2CitationsPage(ExternalModel):
    """One page of S2's ``/paper/{id}/citations`` response.

    ``data`` has **no default** on purpose: unlike ``WorksPage.results``
    (which defaults to ``[]`` because a missing/empty page is not a hard
    error there either), a missing, ``null``, or non-list ``data`` here is a
    malformed page, not a page with zero edges — the two must not collapse,
    or a truncated response would read as "this work simply has no citation
    edges."
    """

    data: list[Any]


def parse_work(payload: object, *, source: str) -> OpenAlexWork:
    """Validate an OpenAlex work payload, or fail the call.

    A malformed work is a hard error rather than a skipped row: returning a
    partial frontier as if it were complete is the failure this package exists
    to prevent (ADR-0043 decision point 4).

    :param payload: The raw work object.
    :param source: The URL it came from, for the message.
    :returns: The validated work.
    :raises HttpError: If `payload` is not a well-formed OpenAlex work.
    """
    from defendable_science.core.http import HttpError

    return parse_obj(OpenAlexWork, payload, source=source, error=HttpError)


def _classify(identifier: str) -> tuple[str, str]:
    """Classify a raw identifier into ``(kind, normalized)``.

    :param identifier: A DOI / arXiv id / OpenAlex ``W…`` / S2 id (any prefixing).
    :returns: ``(kind, normalized)`` where kind is ``openalex`` / ``doi`` /
        ``arxiv`` / ``s2`` / ``unknown``.
    """
    ident = identifier.strip()
    low = ident.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if low.startswith(prefix):
            ident = ident[len(prefix) :]
            low = ident.lower()
    if low.startswith("arxiv:"):
        return "arxiv", ident[len("arxiv:") :]
    if low.startswith("corpusid:"):
        return "s2", ident
    if _OPENALEX_RE.match(ident):
        return "openalex", ident.upper()
    if _DOI_RE.match(ident):
        return "doi", ident
    if _ARXIV_RE.match(ident):
        return "arxiv", ident
    if re.fullmatch(r"[0-9a-f]{40}", low):
        return "s2", ident
    return "unknown", ident


def _short_id(url: str | None) -> str | None:
    """Reduce an OpenAlex/S2 entity URL to its bare id (``…/W123`` → ``W123``)."""
    if not url:
        return None
    return url.rstrip("/").rsplit("/", 1)[-1]


def _strip_doi(doi: str | None) -> str | None:
    """Strip the ``https://doi.org/`` prefix from an OpenAlex ``doi`` field."""
    if not doi:
        return None
    return re.sub(r"^https?://doi\.org/", "", doi, flags=re.IGNORECASE)


def _abstract(index: dict[str, list[int]] | None) -> str | None:
    """Reconstruct an abstract from OpenAlex's inverted index, if present."""
    if not index:
        return None
    positions: list[tuple[int, str]] = []
    for word, where in index.items():
        positions.extend((pos, word) for pos in where)
    return " ".join(word for _, word in sorted(positions))


def enrich_work(work: OpenAlexWork) -> dict[str, Any]:
    """Project a validated OpenAlex work into the stable enrichment record shape.

    :param work: A validated OpenAlex work object.
    :returns: ``{id{…}, title, year, venue, cited_by_count, authors, abstract}``.
    """
    source = work.primary_location.source if work.primary_location else None
    authors = [
        a.author.display_name
        for a in work.authorships
        if a.author and a.author.display_name
    ]
    return {
        "id": {
            "openalex": _short_id(work.id),
            "doi": _strip_doi(work.doi),
            "s2": None,
            "arxiv": _short_id(work.ids.arxiv) if work.ids.arxiv else None,
        },
        "title": work.display_name or work.title,
        "year": work.publication_year,
        "venue": source.display_name if source else None,
        "cited_by_count": work.cited_by_count,
        "authors": authors,
        "abstract": _abstract(work.abstract_inverted_index),
    }


def _fetch_work(client: HttpClient, openalex_id: str) -> OpenAlexWork:
    """Fetch one OpenAlex work by its ``W…`` id.

    :raises HttpError: If the 200 body is not a well-formed work object (wrong
        shape, or no ``id``); a hollow ``{}`` is never returned in its place.
    """
    from defendable_science.core.http import HttpError

    url = f"{OPENALEX}/works/{openalex_id}"
    work = parse_work(client.get_json(url), source=url)
    if not work.id:
        raise HttpError(f"{url}: response is not an OpenAlex work object")
    return work


def _arxiv_doi(arxiv_id: str) -> str:
    """Build the arXiv DataCite DOI for an arXiv id, dropping any ``vN`` suffix.

    arXiv registers one DOI per paper (``10.48550/arXiv.<id>``) with no version
    component, so a versioned id like ``2205.11775v4`` must have the suffix
    stripped before the lookup — otherwise it resolves to a non-existent DOI.
    """
    unversioned = re.sub(r"v\d+$", "", arxiv_id)
    return f"10.48550/arXiv.{unversioned}"


def _lookup_url(kind: str, norm: str) -> str | None:
    """Map a ``(kind, normalized-id)`` pair to its OpenAlex work-lookup URL."""
    return {
        "openalex": f"{OPENALEX}/works/{norm}",
        "doi": f"{OPENALEX}/works/doi:{norm}",
        "arxiv": f"{OPENALEX}/works/doi:{_arxiv_doi(norm)}",
    }.get(kind)


def _s2_crossref(client: HttpClient, s2_id: str) -> tuple[str, str] | None:
    """Cross-reference a Semantic Scholar id to a ``(kind, id)`` OpenAlex anchor.

    OpenAlex has no S2 lookup, so an S2 id (``CorpusId:…`` / SHA) is resolved
    through S2's ``externalIds`` to a DOI or arXiv id that OpenAlex *does* index.

    :returns: ``("doi", …)`` / ``("arxiv", …)``, or ``None`` if S2 misses or the
        paper carries no DOI/arXiv cross-reference.
    :raises RateLimitError: If S2 rate-limits — a throttle is not a "no such paper".
    """
    from defendable_science.core.http import HttpError, RateLimitError

    try:
        paper = client.get_json(
            f"{S2}/paper/{s2_id}", {"fields": "externalIds"}, s2=True
        )
    except RateLimitError:
        raise
    except HttpError:
        return None
    ids = parse_obj(
        S2ExternalIds, paper, source=f"{S2}/paper/{s2_id}", error=HttpError
    ).external_ids
    if ids.doi:
        return "doi", ids.doi
    if ids.arxiv:
        return "arxiv", ids.arxiv
    return None


def _resolve_s2_xref(client: HttpClient, norm: str) -> tuple[str, str] | dict[str, Any]:
    """Cross-reference an S2 id for `resolve`.

    Returns ``(kind, norm)`` on success, or a failure dict for `resolve` to
    return as-is. Split out of `resolve` to keep its branch count down; the
    returned failure dict already matches `resolve`'s own
    ``{resolved: False, ...}`` shape.

    :raises RateLimitError: If S2 rate-limits — a throttle must propagate.
    """
    from defendable_science.core.http import HttpError, RateLimitError

    try:
        xref = _s2_crossref(client, norm)
    except RateLimitError:
        raise
    except HttpError as exc:
        # A malformed S2 200 body during cross-reference is a transport
        # anomaly, not "no such paper" — mirrors the OpenAlex work-fetch
        # path in `resolve` for the same defect (ADR-0043 decision point 4).
        return {"resolved": False, "reason": str(exc), "transport_error": True}
    if xref is None:
        return {
            "resolved": False,
            "reason": f"could not cross-reference S2 id {norm!r} to a DOI/arXiv",
        }
    return xref


def resolve(identifier: str, *, client: HttpClient) -> dict[str, Any]:
    """Resolve any identifier to a canonical work record.

    :param identifier: DOI / arXiv id / OpenAlex ``W…`` / S2 id.
    :param client: The HTTP client.
    :returns: ``{resolved, openalex, doi, s2, arxiv, title, year}``; on a genuine
        miss (``404`` / empty body / no cross-reference / unsupported identifier
        kind), ``{resolved: False, reason: …}``. On a transport failure (any
        other ``HttpError`` — a ``502``, an exhausted retry budget, a non-JSON
        body), the same shape additionally carries ``transport_error: True`` —
        a consumer must not treat that as "no such paper".
    :raises RateLimitError: If a provider rate-limits — a throttle must propagate,
        never be recorded as a "not found".
    """
    from defendable_science.core.http import HttpError, RateLimitError

    kind, norm = _classify(identifier)
    if kind == "s2":
        outcome = _resolve_s2_xref(client, norm)
        if isinstance(outcome, dict):
            return outcome
        kind, norm = outcome
    lookup = _lookup_url(kind, norm)
    if lookup is None:
        return {"resolved": False, "reason": f"unsupported identifier kind: {kind}"}
    try:
        payload = client.get_json(lookup)
    except RateLimitError:
        raise
    except HttpError as exc:
        if exc.status_code == 404:
            return {"resolved": False, "reason": str(exc)}
        return {"resolved": False, "reason": str(exc), "transport_error": True}
    try:
        work = parse_work(payload, source=lookup)
    except HttpError as exc:
        # A 200 body of the wrong shape is not a miss — a consumer must not
        # record it as "no such paper" (ADR-0043 decision point 4).
        return {"resolved": False, "reason": str(exc), "transport_error": True}
    if not work.id:
        return {"resolved": False, "reason": "no work found"}
    return {
        "resolved": True,
        "openalex": _short_id(work.id),
        "doi": _strip_doi(work.doi),
        "s2": None,
        "arxiv": _short_id(work.ids.arxiv) if work.ids.arxiv else None,
        "title": work.display_name or work.title,
        "year": work.publication_year,
    }


def cites(
    openalex_id: str, *, client: HttpClient, max_results: int | None = None
) -> list[dict[str, Any]]:
    """Return forward citations (works citing `openalex_id`), cursor-paginated.

    :param openalex_id: The anchor's OpenAlex ``W…`` id.
    :param client: The HTTP client.
    :param max_results: Cap on rows returned (all citations if ``None``).
    :returns: One record per citing work with provenance ``{via: "openalex"}``.
    :raises HttpError: If a page mid-pagination is not a well-formed citation
        page. Stopping silently here would return a truncated frontier as if
        complete, so it is a hard error (mirroring :meth:`HttpClient.get_json`'s
        non-JSON path).
    """
    from defendable_science.core.http import HttpError

    results: list[dict[str, Any]] = []
    cursor: str | None = "*"
    while cursor:
        raw = client.get_json(
            f"{OPENALEX}/works",
            {"filter": f"cites:{openalex_id}", "per-page": "200", "cursor": cursor},
        )
        page = parse_obj(WorksPage, raw, source=f"{OPENALEX}/works", error=HttpError)
        for work in page.results:
            record = enrich_work(work)
            record["provenance"] = {"source_id": openalex_id, "via": "openalex"}
            results.append(record)
            if max_results is not None and len(results) >= max_results:
                return results
        cursor = page.meta.next_cursor
    return results


def refs(openalex_id: str, *, client: HttpClient) -> list[str]:
    """Return the backward references (OpenAlex ids) of a work.

    :param openalex_id: The work's OpenAlex ``W…`` id.
    :param client: The HTTP client.
    :returns: The ``referenced_works`` ids (bare ``W…`` form).
    """
    work = _fetch_work(client, openalex_id)
    return [rid for ref in work.referenced_works if (rid := _short_id(ref))]


def _s2_paper_id(record: dict[str, Any]) -> str | None:
    """Pick an S2-addressable id (``DOI:…`` / ``ARXIV:…``) for an enriched work."""
    ids = record.get("id", {})
    if ids.get("doi"):
        return f"DOI:{ids['doi']}"
    if ids.get("arxiv"):
        unversioned = re.sub(r"v\d+$", "", str(ids["arxiv"]))
        return f"ARXIV:{unversioned}"
    return None


def _s2_context(client: HttpClient, s2_paper_id: str) -> dict[str, Any]:
    """Aggregate a work's incoming S2 citation edges into a per-work context bundle.

    S2 exposes citation context / SciCite intent / ``isInfluential`` per *edge*
    (``/paper/{id}/citations``); for a work in isolation we surface a representative
    citing sentence and intent plus whether *any* citation is influential. Returns
    ``{s2, context_snippet, intent, is_influential}`` (each ``None`` when absent);
    an S2 miss/error yields all-``None`` (best effort — the key was still used). A
    rate-limit is *not* best-effort: it propagates rather than masquerading as "S2
    had no data".

    The bundle also carries internal bookkeeping keys read by :func:`enrich` to
    build its ``degraded`` marker — never emitted to a consumer directly, and
    absent entirely when nothing was lost:

    - ``meta_skipped`` — the ``/paper`` metadata body was malformed, so the
      ``s2`` id (if any) could not be read (spec §3.4: best effort, never a
      hard failure over an optional field).
    - ``edges_skipped`` — how many individual ``/citations`` edges were
      malformed (see :func:`_aggregate_s2_edges`).
    - ``citations_skipped`` — the whole ``/citations`` page was malformed, so
      no edges could be read at all; distinct from a transport miss (a 404,
      say), which yields all-``None`` with no marker because that is a
      legitimate "S2 has nothing" rather than a lost signal.

    :raises RateLimitError: If S2 rate-limits during either sub-request.
    """
    from defendable_science.core.http import HttpError, RateLimitError

    out: dict[str, Any] = {
        "s2": None,
        "context_snippet": None,
        "intent": None,
        "is_influential": None,
    }
    try:
        meta = client.get_json(
            f"{S2}/paper/{s2_paper_id}", {"fields": "externalIds"}, s2=True
        )
    except RateLimitError:
        raise
    except HttpError:
        meta = {}
    corpus = None
    if meta:
        try:
            corpus = parse_obj(
                S2ExternalIds,
                meta,
                source=f"{S2}/paper/{s2_paper_id}",
                error=HttpError,
            ).external_ids.corpus_id
        except HttpError:
            # A malformed metadata body must not hard-fail the whole call —
            # S2 is an optional, best-effort enrichment (spec §3.4) — but the
            # lost `s2` id must still be visible to the caller, not silently
            # absent (ADR-0043 decision point 4).
            out["meta_skipped"] = True
    if corpus is not None:
        out["s2"] = f"CorpusId:{corpus}"
    try:
        raw_page = client.get_json(
            f"{S2}/paper/{s2_paper_id}/citations",
            {"fields": "contexts,intents,isInfluential", "limit": "100"},
            s2=True,
        )
    except RateLimitError:
        raise
    except HttpError:
        return out
    try:
        page = parse_obj(
            S2CitationsPage,
            raw_page,
            source=f"{S2}/paper/{s2_paper_id}/citations",
            error=HttpError,
        )
    except HttpError:
        # A malformed citations page (missing/null/non-list `data`) is the
        # same "must not hard-fail, must not vanish" situation as a malformed
        # edge or a malformed metadata body — it must not raise (a `None`
        # `data` used to blow up as a raw TypeError) and must not report as a
        # legitimate empty result with no marker.
        out["citations_skipped"] = True
        return out
    out["edges_skipped"] = _aggregate_s2_edges(page.data, out)
    return out


def _aggregate_s2_edges(edges: list[Any], out: dict[str, Any]) -> int:
    """Fold S2 citation edges into `out` (representative snippet / intent / flag).

    Best effort by design: a malformed edge is skipped rather than failing an
    optional enrichment, but the count is returned so the caller can mark the
    loss instead of hiding it (ADR-0043 decision point 4).

    :param edges: The raw ``/citations`` edge list.
    :param out: The context bundle mutated in place.
    :returns: How many edges were skipped as malformed.
    """
    parsed, skipped = parse_each(S2CitationEdge, edges)
    for edge in parsed:
        if out["context_snippet"] is None and edge.contexts:
            out["context_snippet"] = edge.contexts[0]
        if out["intent"] is None and edge.intents:
            out["intent"] = edge.intents[0]
        if edge.is_influential:
            out["is_influential"] = True
    if out["is_influential"] is None and parsed:
        out["is_influential"] = False
    return skipped


def enrich(
    openalex_ids: list[str], *, client: HttpClient, with_context: bool = False
) -> list[dict[str, Any]]:
    """Enrich each work id with its metadata bundle.

    With `with_context`, each record also carries ``context_snippet`` / ``intent``
    / ``is_influential`` from Semantic Scholar (and its ``s2`` id). When **no S2
    key** is configured those fields degrade to ``null`` with a ``degraded``
    marker — distinct from "S2 was queried and returned nothing", where the fields
    are ``null`` *without* the marker.

    :param openalex_ids: The works to enrich.
    :param client: The HTTP client.
    :param with_context: Attach the S2 citation-context bundle (see above).
    :returns: One enrichment record per id.
    """
    records: list[dict[str, Any]] = []
    for wid in openalex_ids:
        record = enrich_work(_fetch_work(client, wid))
        if with_context:
            if not client.s2_key:
                record["context_snippet"] = None
                record["intent"] = None
                record["is_influential"] = None
                record["degraded"] = ["context", "intent", "is_influential"]
            else:
                s2_id = _s2_paper_id(record)
                bundle = (
                    _s2_context(client, s2_id)
                    if s2_id is not None
                    else {
                        "context_snippet": None,
                        "intent": None,
                        "is_influential": None,
                    }
                )
                if bundle.get("s2"):
                    record["id"]["s2"] = bundle["s2"]
                record["context_snippet"] = bundle["context_snippet"]
                record["intent"] = bundle["intent"]
                record["is_influential"] = bundle["is_influential"]
                degraded: list[str] = []
                if bundle.get("meta_skipped"):
                    degraded.append("s2")
                if bundle.get("edges_skipped") or bundle.get("citations_skipped"):
                    degraded.extend(["context", "intent", "is_influential"])
                if degraded:
                    record["degraded"] = degraded
        records.append(record)
    return records


def _cocitation(
    openalex_id: str, citers: list[dict[str, Any]], client: HttpClient, top: int
) -> list[dict[str, Any]]:
    """Rank works co-cited with the anchor (shared citing papers)."""
    counter: Counter[str] = Counter()
    for citer in citers:
        citer_id = citer["id"]["openalex"]
        if citer_id:
            for ref in refs(citer_id, client=client):
                if ref != openalex_id:
                    counter[ref] += 1
    return [{"openalex": wid, "score": n} for wid, n in counter.most_common(top)]


def _coupling(
    openalex_id: str, client: HttpClient, top: int, frontier: int
) -> list[dict[str, Any]]:
    """Rank works sharing references with the anchor (bibliographic coupling)."""
    counter: Counter[str] = Counter()
    for ref in refs(openalex_id, client=client)[:frontier]:
        for citer in cites(ref, client=client, max_results=frontier):
            citer_id = citer["id"]["openalex"]
            if citer_id and citer_id != openalex_id:
                counter[citer_id] += 1
    return [{"openalex": wid, "score": n} for wid, n in counter.most_common(top)]


def neighbors(
    openalex_id: str,
    *,
    client: HttpClient,
    kind: str = "both",
    top: int = 20,
    frontier: int = 50,
) -> dict[str, Any]:
    """Compute co-citation and/or bibliographic-coupling neighbour sets.

    Pure set arithmetic over OpenAlex data. The citer/reference frontier is capped
    at `frontier` to bound the API fan-out for highly-cited anchors; the cap is
    reported in the result so truncation is never silent.

    :param openalex_id: The anchor's OpenAlex ``W…`` id.
    :param client: The HTTP client.
    :param kind: ``cocite`` / ``couple`` / ``both``.
    :param top: Number of neighbours to return per set.
    :param frontier: Max citers/references sampled for the computation.
    :returns: ``{cocitation: [...], coupling: [...], capped: bool}``.
    :raises ValueError: If `kind` is not ``cocite`` / ``couple`` / ``both``.
    """
    if kind not in ("cocite", "couple", "both"):
        raise ValueError(f"unknown kind {kind!r} (want cocite | couple | both)")
    out: dict[str, Any] = {}
    citers = cites(openalex_id, client=client, max_results=frontier)
    # ``cites`` now either paginates to completion or raises on a bad page, so a
    # short list genuinely means the frontier was exhausted; hitting the cap is
    # the only way to be incomplete, and that is what ``capped`` reports.
    out["capped"] = len(citers) >= frontier
    if kind in ("cocite", "both"):
        out["cocitation"] = _cocitation(openalex_id, citers, client, top)
    if kind in ("couple", "both"):
        out["coupling"] = _coupling(openalex_id, client, top, frontier)
    return out
