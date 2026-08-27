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

if TYPE_CHECKING:
    from defendable_science.core.http import HttpClient

OPENALEX = "https://api.openalex.org"
S2 = "https://api.semanticscholar.org/graph/v1"

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_OPENALEX_RE = re.compile(r"^[Ww]\d+$")
_ARXIV_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")


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


def _abstract(work: dict[str, Any]) -> str | None:
    """Reconstruct an abstract from OpenAlex's inverted index, if present."""
    index = work.get("abstract_inverted_index")
    if not index:
        return None
    positions: list[tuple[int, str]] = []
    for word, where in index.items():
        positions.extend((pos, word) for pos in where)
    return " ".join(word for _, word in sorted(positions))


def enrich_work(work: dict[str, Any]) -> dict[str, Any]:
    """Project a raw OpenAlex work into the stable enrichment record shape.

    :param work: A raw OpenAlex work object.
    :returns: ``{id{…}, title, year, venue, cited_by_count, authors, abstract}``.
    """
    ids = work.get("ids", {})
    source = (work.get("primary_location") or {}).get("source") or {}
    authors = [
        (a.get("author") or {}).get("display_name")
        for a in work.get("authorships", [])
        if (a.get("author") or {}).get("display_name")
    ]
    return {
        "id": {
            "openalex": _short_id(work.get("id")),
            "doi": _strip_doi(work.get("doi")),
            "s2": None,
            "arxiv": _short_id(ids.get("arxiv")) if ids.get("arxiv") else None,
        },
        "title": work.get("display_name") or work.get("title"),
        "year": work.get("publication_year"),
        "venue": source.get("display_name"),
        "cited_by_count": work.get("cited_by_count"),
        "authors": authors,
        "abstract": _abstract(work),
    }


def _fetch_work(client: HttpClient, openalex_id: str) -> dict[str, Any]:
    """Fetch one OpenAlex work by its ``W…`` id.

    :raises HttpError: If the 200 body is not a work object (non-dict or no
        ``id``); a hollow ``{}`` is never returned in its place.
    """
    from defendable_science.core.http import HttpError

    url = f"{OPENALEX}/works/{openalex_id}"
    data = client.get_json(url)
    if not isinstance(data, dict) or not data.get("id"):
        raise HttpError(f"{url}: response is not an OpenAlex work object")
    return data


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
    ext = (paper.get("externalIds") or {}) if isinstance(paper, dict) else {}
    if ext.get("DOI"):
        return "doi", str(ext["DOI"])
    if ext.get("ArXiv"):
        return "arxiv", str(ext["ArXiv"])
    return None


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
        xref = _s2_crossref(client, norm)
        if xref is None:
            return {
                "resolved": False,
                "reason": f"could not cross-reference S2 id {norm!r} to a DOI/arXiv",
            }
        kind, norm = xref
    lookup = _lookup_url(kind, norm)
    if lookup is None:
        return {"resolved": False, "reason": f"unsupported identifier kind: {kind}"}
    try:
        work = client.get_json(lookup)
    except RateLimitError:
        raise
    except HttpError as exc:
        if exc.status_code == 404:
            return {"resolved": False, "reason": str(exc)}
        return {"resolved": False, "reason": str(exc), "transport_error": True}
    if not isinstance(work, dict) or not work.get("id"):
        return {"resolved": False, "reason": "no work found"}
    ids = work.get("ids", {})
    return {
        "resolved": True,
        "openalex": _short_id(work.get("id")),
        "doi": _strip_doi(work.get("doi")),
        "s2": None,
        "arxiv": _short_id(ids.get("arxiv")) if ids.get("arxiv") else None,
        "title": work.get("display_name") or work.get("title"),
        "year": work.get("publication_year"),
    }


def cites(
    openalex_id: str, *, client: HttpClient, max_results: int | None = None
) -> list[dict[str, Any]]:
    """Return forward citations (works citing `openalex_id`), cursor-paginated.

    :param openalex_id: The anchor's OpenAlex ``W…`` id.
    :param client: The HTTP client.
    :param max_results: Cap on rows returned (all citations if ``None``).
    :returns: One record per citing work with provenance ``{via: "openalex"}``.
    :raises HttpError: If a page mid-pagination is not a JSON object. Stopping
        silently here would return a truncated frontier as if complete, so it is
        a hard error (mirroring :meth:`HttpClient.get_json`'s non-JSON path).
    """
    from defendable_science.core.http import HttpError

    results: list[dict[str, Any]] = []
    cursor: str | None = "*"
    while cursor:
        page = client.get_json(
            f"{OPENALEX}/works",
            {"filter": f"cites:{openalex_id}", "per-page": "200", "cursor": cursor},
        )
        if not isinstance(page, dict):
            raise HttpError(f"{OPENALEX}/works: citation page is not a JSON object")
        for work in page.get("results", []):
            record = enrich_work(work)
            record["provenance"] = {"source_id": openalex_id, "via": "openalex"}
            results.append(record)
            if max_results is not None and len(results) >= max_results:
                return results
        cursor = (page.get("meta") or {}).get("next_cursor")
    return results


def refs(openalex_id: str, *, client: HttpClient) -> list[str]:
    """Return the backward references (OpenAlex ids) of a work.

    :param openalex_id: The work's OpenAlex ``W…`` id.
    :param client: The HTTP client.
    :returns: The ``referenced_works`` ids (bare ``W…`` form).
    """
    work = _fetch_work(client, openalex_id)
    return [rid for ref in work.get("referenced_works", []) if (rid := _short_id(ref))]


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
    corpus = (
        (meta.get("externalIds") or {}).get("CorpusId")
        if isinstance(meta, dict)
        else None
    )
    if corpus is not None:
        out["s2"] = f"CorpusId:{corpus}"
    try:
        page = client.get_json(
            f"{S2}/paper/{s2_paper_id}/citations",
            {"fields": "contexts,intents,isInfluential", "limit": "100"},
            s2=True,
        )
    except RateLimitError:
        raise
    except HttpError:
        return out
    edges = page.get("data", []) if isinstance(page, dict) else []
    _aggregate_s2_edges(edges, out)
    return out


def _aggregate_s2_edges(edges: list[Any], out: dict[str, Any]) -> None:
    """Fold S2 citation edges into `out` (representative snippet / intent / flag).

    :param edges: The raw ``/citations`` edge list (non-dict entries are ignored).
    :param out: The context bundle mutated in place.
    """
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        if out["context_snippet"] is None and edge.get("contexts"):
            out["context_snippet"] = edge["contexts"][0]
        if out["intent"] is None and edge.get("intents"):
            out["intent"] = edge["intents"][0]
        if edge.get("isInfluential"):
            out["is_influential"] = True
    if out["is_influential"] is None and edges:
        out["is_influential"] = False


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
