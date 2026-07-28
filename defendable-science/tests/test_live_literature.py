"""Opt-in live integration tests: real OpenAlex + Semantic Scholar (defendable-science#30).

Skipped unless ``DEFENDABLE_SCIENCE_LIVE=1``. These exercise the real endpoint shapes,
cursor pagination, and the S2 enrichment/cross-reference paths that the hermetic
suite can only mock — the integration risk a *final* release must retire.

    DEFENDABLE_SCIENCE_LIVE=1 OPENALEX_MAILTO=you@example.org \
        uv run pytest -m live --no-cov

S2-keyed assertions are additionally gated on ``S2_API_KEY`` because keyless S2 is
aggressively rate-limited; a keyless call is only asserted to degrade *gracefully*.
"""

from __future__ import annotations

import os

import pytest

from defendable_science.core.http import HttpClient
from defendable_science.literature import graph

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("DEFENDABLE_SCIENCE_LIVE") != "1",
        reason="live test — set DEFENDABLE_SCIENCE_LIVE=1 (needs network)",
    ),
]

_MAILTO = os.environ.get("OPENALEX_MAILTO", "davor@synthpop.ai")
_S2_KEY = os.environ.get("S2_API_KEY")
# A stable, well-connected anchor: Piwowar et al. 2018, "The state of OA".
_ANCHOR = "W2741809807"
# The group's ICML'23 paper (arXiv), for the arXiv + S2 cross-reference paths.
_CMNN_ARXIV = "arXiv:2205.11775"
_CMNN_CORPUSID = "CorpusId:249017894"

_requires_s2 = pytest.mark.skipif(
    not _S2_KEY, reason="needs S2_API_KEY (keyless S2 rate-limits too hard to assert)"
)


@pytest.fixture
def client() -> HttpClient:
    return HttpClient(cache_dir=None, mailto=_MAILTO, s2_key=_S2_KEY)


def test_resolve_openalex_anchor(client: HttpClient) -> None:
    rec = graph.resolve(_ANCHOR, client=client)
    assert rec["resolved"] is True
    assert rec["openalex"] == _ANCHOR
    assert rec["year"]


def test_resolve_arxiv_and_versioned(client: HttpClient) -> None:
    rec = graph.resolve(_CMNN_ARXIV, client=client)
    assert rec["resolved"] is True
    assert "monotonic" in (rec["title"] or "").lower()
    # A versioned id must strip the vN suffix and still resolve (defendable-science#31 B3).
    assert graph.resolve(_CMNN_ARXIV + "v4", client=client)["resolved"] is True


def test_refs_nonempty_for_published_work(client: HttpClient) -> None:
    refs = graph.refs(_ANCHOR, client=client)
    assert refs
    assert all(rid.startswith("W") for rid in refs)


def test_cites_paginates_with_cap(client: HttpClient) -> None:
    rows = graph.cites(_ANCHOR, client=client, max_results=5)
    assert 1 <= len(rows) <= 5
    assert all(row["provenance"]["via"] == "openalex" for row in rows)
    assert all(row["id"]["openalex"] for row in rows)


def test_neighbors_cocite(client: HttpClient) -> None:
    out = graph.neighbors(_ANCHOR, client=client, kind="cocite", top=5, frontier=10)
    assert "cocitation" in out
    assert "capped" in out


def test_enrich_degrades_without_key() -> None:
    # Deterministic even keyless: no S2 key → the degraded marker is present.
    keyless = HttpClient(cache_dir=None, mailto=_MAILTO, s2_key=None)
    rec = graph.enrich([_ANCHOR], client=keyless, with_context=True)[0]
    assert rec["degraded"] == ["context", "intent", "is_influential"]
    assert rec["title"]


def test_resolve_corpusid_keyless_is_graceful() -> None:
    # Keyless S2 may rate-limit; resolve must either succeed or degrade cleanly
    # (return resolved=False + reason), never raise.
    keyless = HttpClient(cache_dir=None, mailto=_MAILTO, s2_key=None)
    rec = graph.resolve(_CMNN_CORPUSID, client=keyless)
    assert "resolved" in rec
    if not rec["resolved"]:
        assert "reason" in rec


@_requires_s2
def test_enrich_with_key_attaches_s2(client: HttpClient) -> None:
    rec = graph.enrich([_ANCHOR], client=client, with_context=True)[0]
    assert "degraded" not in rec  # a key was used, so no not-queried marker
    s2_id = rec["id"]["s2"]
    assert s2_id
    assert s2_id.startswith("CorpusId:")


@_requires_s2
def test_resolve_via_corpusid_with_key(client: HttpClient) -> None:
    # CorpusId → S2 externalIds → OpenAlex (defendable-science#31 B3).
    rec = graph.resolve(_CMNN_CORPUSID, client=client)
    assert rec["resolved"] is True
    assert "monotonic" in (rec["title"] or "").lower()
