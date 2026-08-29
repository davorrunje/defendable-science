"""Tests for the citation-graph client + HTTP layer (defendable-science#1)."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from defendable_science import cli
from defendable_science.cli import app
from defendable_science.core import http
from defendable_science.literature import graph

runner = CliRunner()


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any,
        headers: dict[str, str] | None = None,
        text: str | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers: dict[str, str] = headers or {}
        self._text = text

    def json(self) -> Any:
        return self._payload

    @property
    def text(self) -> str:
        return self._text if self._text is not None else json.dumps(self._payload)


class FakeSession:
    """A routing fake: maps a URL to a queue of responses (or one response)."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> FakeResponse:
        self.calls.append((url, params))
        payload = self.routes.get(url)
        if isinstance(payload, list):  # a queue of successive responses
            payload = payload.pop(0)
        if isinstance(payload, FakeResponse):
            return payload
        if payload is None:
            return FakeResponse(404, {})
        return FakeResponse(200, payload)


def _client(routes: dict[str, Any], **kw: Any) -> http.HttpClient:
    return http.HttpClient(
        session=FakeSession(routes), sleep=lambda _s: None, cache_dir=None, **kw
    )


# --- HttpClient -------------------------------------------------------------


def test_http_get_json_ok() -> None:
    client = _client({"https://x/y": {"ok": True}})
    assert client.get_json("https://x/y") == {"ok": True}


def test_http_adds_mailto_for_openalex() -> None:
    session = FakeSession({"https://x": {"ok": 1}})
    client = http.HttpClient(session=session, mailto="me@x.org", cache_dir=None)
    client.get_json("https://x")
    assert session.calls[0][1] is not None
    assert session.calls[0][1]["mailto"] == "me@x.org"


def test_http_retries_then_succeeds() -> None:
    session = FakeSession(
        {"https://x": [FakeResponse(429, {}), FakeResponse(200, {"ok": 1})]}
    )
    client = http.HttpClient(session=session, sleep=lambda _s: None, cache_dir=None)
    assert client.get_json("https://x") == {"ok": 1}
    assert len(session.calls) == 2


def test_http_gives_up_and_raises() -> None:
    session = FakeSession({"https://x": FakeResponse(503, {})})
    client = http.HttpClient(
        session=session, sleep=lambda _s: None, cache_dir=None, max_retries=2
    )
    with pytest.raises(http.HttpError, match="giving up") as exc:
        client.get_json("https://x")
    # A retry-budget exhaustion has no single status to point to — it must
    # not masquerade as a genuine 404 by carrying that status_code.
    assert exc.value.status_code is None


def test_http_4xx_is_fatal() -> None:
    client = _client({"https://x": FakeResponse(404, {})})
    with pytest.raises(http.HttpError, match="HTTP 404") as exc:
        client.get_json("https://x")
    assert exc.value.status_code == 404


def test_http_cache_avoids_second_call(tmp_path: Any) -> None:
    session = FakeSession({"https://x": {"n": 1}})
    client = http.HttpClient(session=session, cache_dir=tmp_path)
    assert client.get_json("https://x") == {"n": 1}
    assert client.get_json("https://x") == {"n": 1}
    assert len(session.calls) == 1  # second served from cache


def test_http_corrupt_cache_is_refetched_not_traceback(tmp_path: Any) -> None:
    session = FakeSession({"https://x": {"n": 1}})
    client = http.HttpClient(session=session, cache_dir=tmp_path, sleep=lambda _s: None)
    key = http._cache_key("https://x", {})
    (tmp_path / f"{key}.json").write_text("{ not valid json", encoding="utf-8")
    # A corrupt entry (e.g. an interrupted store) is a cache miss, not a crash.
    assert client.get_json("https://x") == {"n": 1}
    assert len(session.calls) == 1
    # The re-fetch atomically overwrote it: a second call hits the repaired cache
    # and no temp file is left behind.
    assert client.get_json("https://x") == {"n": 1}
    assert len(session.calls) == 1
    assert not (tmp_path / f"{key}.json.tmp").exists()


# --- get_text (task 9, feeds arxiv_candidates' non-JSON Atom response) ------


def test_http_get_text_ok() -> None:
    session = FakeSession({"https://x": FakeResponse(200, None, text="<feed/>")})
    client = http.HttpClient(session=session, sleep=lambda _s: None, cache_dir=None)
    assert client.get_text("https://x") == "<feed/>"


def test_http_get_text_never_sends_mailto() -> None:
    """Fix round 1: `mailto` was configured for OpenAlex's polite pool.

    ``get_text`` exists for other hosts (arXiv); sending a user's contact
    email to a host they never configured it for is a privacy leak, not a
    politeness nicety, so it must never be added here regardless of `mailto`.
    """
    session = FakeSession({"https://x": FakeResponse(200, None, text="ok")})
    client = http.HttpClient(
        session=session, mailto="me@x.org", sleep=lambda _s: None, cache_dir=None
    )
    client.get_text("https://x")
    params = session.calls[0][1]
    assert params is None or "mailto" not in params


def test_http_get_text_rate_limit_propagates() -> None:
    """A throttle is never a 'no results' — ``get_text`` must raise, same as JSON."""
    session = FakeSession({"https://x": FakeResponse(429, {})})
    client = http.HttpClient(
        session=session, sleep=lambda _s: None, cache_dir=None, max_retries=2
    )
    with pytest.raises(http.RateLimitError, match="giving up"):
        client.get_text("https://x")


def test_http_get_text_is_not_cached(tmp_path: Any) -> None:
    """No on-disk cache for text.

    Unlike ``get_json``, ``get_text`` has no on-disk cache (``JsonValue`` is
    dict/list only, so a raw string cannot be stored through the same path).
    A real `cache_dir` is passed so the assertion is load-bearing: with
    caching enabled but inert for ``get_text``, both calls must still reach
    the transport.
    """
    session = FakeSession({"https://x": [FakeResponse(200, None, text="a")] * 2})
    client = http.HttpClient(session=session, sleep=lambda _s: None, cache_dir=tmp_path)
    assert client.get_text("https://x") == "a"
    assert client.get_text("https://x") == "a"
    assert len(session.calls) == 2


# --- graph ------------------------------------------------------------------


def test_classify() -> None:
    assert graph._classify("W123")[0] == "openalex"
    assert graph._classify("10.1234/abc")[0] == "doi"
    assert graph._classify("doi:10.1234/abc") == ("doi", "10.1234/abc")
    assert graph._classify("arXiv:2205.11775")[0] == "arxiv"
    assert graph._classify("nonsense")[0] == "unknown"


_WORK = {
    "id": "https://openalex.org/W1",
    "doi": "https://doi.org/10.1234/abc",
    "display_name": "A Title",
    "publication_year": 2023,
    "cited_by_count": 42,
    "primary_location": {"source": {"display_name": "ICML"}},
    "authorships": [{"author": {"display_name": "D. Runje"}}],
    "abstract_inverted_index": {"Hello": [0], "world": [1]},
    "referenced_works": ["https://openalex.org/W9", "https://openalex.org/W8"],
}


def test_resolve_openalex() -> None:
    client = _client({"https://api.openalex.org/works/W1": _WORK})
    rec = graph.resolve("W1", client=client)
    assert rec["resolved"] is True
    assert rec["openalex"] == "W1"
    assert rec["doi"] == "10.1234/abc"
    assert rec["year"] == 2023


def test_resolve_miss_is_not_fatal() -> None:
    client = _client({})  # 404 for everything
    rec = graph.resolve("W404", client=client)
    assert rec["resolved"] is False
    assert "reason" in rec
    # The negative that matters (defendable-science#106): a genuine miss must
    # never carry the transport-failure discriminator.
    assert "transport_error" not in rec


def test_enrich_work_reconstructs_abstract() -> None:
    rec = graph.enrich_work(graph.parse_work(_WORK, source="test"))
    assert rec["abstract"] == "Hello world"
    assert rec["venue"] == "ICML"
    assert rec["authors"] == ["D. Runje"]


def test_cites_paginates() -> None:
    page1 = {
        "results": [{"id": "https://openalex.org/W2"}],
        "meta": {"next_cursor": "c2"},
    }
    page2 = {
        "results": [{"id": "https://openalex.org/W3"}],
        "meta": {"next_cursor": None},
    }
    client = _client({"https://api.openalex.org/works": [page1, page2]})
    rows = graph.cites("W1", client=client)
    assert [r["id"]["openalex"] for r in rows] == ["W2", "W3"]
    assert rows[0]["provenance"]["via"] == "openalex"


def test_cites_respects_max() -> None:
    page = {
        "results": [{"id": f"https://openalex.org/W{i}"} for i in range(5)],
        "meta": {"next_cursor": None},
    }
    client = _client({"https://api.openalex.org/works": page})
    assert len(graph.cites("W1", client=client, max_results=3)) == 3


def test_refs_reads_referenced_works() -> None:
    client = _client({"https://api.openalex.org/works/W1": _WORK})
    assert graph.refs("W1", client=client) == ["W9", "W8"]


def test_fetch_work_non_dict_raises() -> None:
    # A non-dict 200 body must not be coerced to a hollow {} work. The message
    # must name both halves (ADR-0043 decision point 4): the failing source
    # and the reason — either alone would leave a dropped-URL regression
    # undetected.
    client = _client({"https://api.openalex.org/works/W1": ["not-a-dict"]})
    with pytest.raises(
        http.HttpError, match=r"https://api\.openalex\.org/works/W1.*valid dictionary"
    ):
        graph.refs("W1", client=client)


def test_fetch_work_idless_body_raises() -> None:
    client = _client({"https://api.openalex.org/works/W1": {}})  # dict but no 'id'
    with pytest.raises(http.HttpError, match="not an OpenAlex work"):
        graph.refs("W1", client=client)


def test_enrich_with_context_degrades_without_key() -> None:
    client = _client({"https://api.openalex.org/works/W1": _WORK})
    rec = graph.enrich(["W1"], client=client, with_context=True)[0]
    assert rec["degraded"] == ["context", "intent", "is_influential"]


# --- CLI (fake client injected via _lit_client) -----------------------------


def test_cli_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client({"https://api.openalex.org/works/W1": _WORK})
    monkeypatch.setattr(cli, "_lit_client", lambda: client)
    result = runner.invoke(app, ["literature", "resolve", "W1"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["openalex"] == "W1"


def test_cli_resolve_miss_exits_1_with_resolved_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "_lit_client", lambda: _client({}))
    result = runner.invoke(app, ["literature", "resolve", "W404"])
    assert result.exit_code == 1  # a genuine miss reports, but is not "success"
    body = json.loads(result.stdout)
    assert body["resolved"] is False
    assert "transport_error" not in body


def test_cli_resolve_transport_error_exits_3(monkeypatch: pytest.MonkeyPatch) -> None:
    # A 502 exhausts the retry budget as a plain HttpError (not a rate limit,
    # not a 404) — this must surface as a distinguishable failure, exit 3, not
    # a clean "no such paper" (exit 1), a false success (exit 0), or a usage
    # error (exit 2 — Click/Typer's code, reserved for bad flags/arguments).
    client = _client(
        {"https://api.openalex.org/works/W1": FakeResponse(502, {})}, max_retries=2
    )
    monkeypatch.setattr(cli, "_lit_client", lambda: client)
    result = runner.invoke(app, ["literature", "resolve", "W1"])
    assert result.exit_code == 3
    body = json.loads(result.stdout)
    assert body["resolved"] is False
    assert body["transport_error"] is True


def test_cli_resolve_usage_error_still_exits_2_not_3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The negative that matters here: a usage error (missing argument) must
    # keep Click/Typer's exit code 2 and must never be, or emit, a
    # transport_error — that collision is exactly what would let someone
    # later "simplify" the two codes back together without noticing.
    monkeypatch.setattr(cli, "_lit_client", lambda: _client({}))
    result = runner.invoke(app, ["literature", "resolve"])  # missing IDENTIFIER
    assert result.exit_code == 2
    assert "transport_error" not in result.stdout


def test_cli_refs_unresolved_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_lit_client", lambda: _client({}))
    result = runner.invoke(app, ["literature", "refs", "W404"])
    assert result.exit_code == 1  # a consuming command needs a resolved id


def test_cli_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client({"https://api.openalex.org/works/W1": _WORK})
    monkeypatch.setattr(cli, "_lit_client", lambda: client)
    result = runner.invoke(app, ["literature", "refs", "W1"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == ["W9", "W8"]


# --- graph internals & CLI (coverage sweep, defendable-science#16) ---------------


def test_classify_all_kinds() -> None:
    assert graph._classify("2205.11775")[0] == "arxiv"
    assert graph._classify("CorpusId:12345") == ("s2", "CorpusId:12345")
    assert graph._classify("0" * 40)[0] == "s2"
    assert graph._classify("https://doi.org/10.1234/x") == ("doi", "10.1234/x")


def test_helper_edges() -> None:
    assert graph._short_id(None) is None
    assert graph._strip_doi(None) is None
    assert graph._strip_doi("HTTPS://doi.org/10.1/x") == "10.1/x"
    assert graph._abstract(None) is None  # no inverted index


def test_resolve_arxiv_builds_doi_lookup() -> None:
    work = {
        "id": "https://openalex.org/W7",
        "display_name": "T",
        "publication_year": 2022,
    }
    client = _client(
        {"https://api.openalex.org/works/doi:10.48550/arXiv.2205.11775": work}
    )
    rec = graph.resolve("arXiv:2205.11775", client=client)
    assert rec["resolved"] is True
    assert rec["openalex"] == "W7"


def test_resolve_unknown_kind() -> None:
    rec = graph.resolve("not-an-id!!", client=_client({}))
    assert rec["resolved"] is False
    assert "unsupported" in rec["reason"]


def test_resolve_empty_body_is_miss() -> None:
    client = _client({"https://api.openalex.org/works/W1": {}})  # no 'id'
    assert graph.resolve("W1", client=client)["resolved"] is False


def test_cites_non_dict_first_page_raises() -> None:
    # The message must name both the failing source and the reason
    # (ADR-0043 decision point 4) — either alone would leave a dropped-URL
    # regression undetected.
    client = _client({"https://api.openalex.org/works": ["not-a-dict"]})
    with pytest.raises(
        http.HttpError, match=r"https://api\.openalex\.org/works.*valid dictionary"
    ):
        graph.cites("W1", client=client)


def test_cites_non_dict_page_mid_pagination_raises() -> None:
    # A truncated frontier must never be returned as if complete.
    page1 = {
        "results": [{"id": "https://openalex.org/W2"}],
        "meta": {"next_cursor": "c2"},
    }
    client = _client({"https://api.openalex.org/works": [page1, "not-a-dict"]})
    with pytest.raises(
        http.HttpError, match=r"https://api\.openalex\.org/works.*valid dictionary"
    ):
        graph.cites("W1", client=client)


def test_enrich_without_context() -> None:
    client = _client({"https://api.openalex.org/works/W1": _WORK})
    rec = graph.enrich(["W1"], client=client)[0]
    assert "degraded" not in rec
    assert rec["title"] == "A Title"


def test_enrich_with_context_and_key_no_degraded() -> None:
    client = _client({"https://api.openalex.org/works/W1": _WORK}, s2_key="k")
    rec = graph.enrich(["W1"], client=client, with_context=True)[0]
    assert "degraded" not in rec
    assert rec["context_snippet"] is None


def test_neighbors_both() -> None:
    oa = "https://api.openalex.org"
    w1 = {
        "id": f"{oa[:-1]}",
        "referenced_works": ["https://openalex.org/W9", "https://openalex.org/W8"],
    }
    w1["id"] = "https://openalex.org/W1"
    w2 = {
        "id": "https://openalex.org/W2",
        "referenced_works": ["https://openalex.org/W9", "https://openalex.org/W99"],
    }
    page_w1 = {
        "results": [{"id": "https://openalex.org/W2"}],
        "meta": {"next_cursor": None},
    }
    page_w9 = {
        "results": [{"id": "https://openalex.org/W2"}],
        "meta": {"next_cursor": None},
    }
    page_w8 = {
        "results": [{"id": "https://openalex.org/W3"}],
        "meta": {"next_cursor": None},
    }
    routes = {
        f"{oa}/works": [page_w1, page_w9, page_w8],
        f"{oa}/works/W1": w1,
        f"{oa}/works/W2": w2,
    }
    out = graph.neighbors("W1", client=_client(routes), kind="both", top=5, frontier=10)
    cocite = {n["openalex"] for n in out["cocitation"]}
    coupling = {n["openalex"] for n in out["coupling"]}
    assert cocite == {"W9", "W99"}
    assert coupling == {"W2", "W3"}
    assert out["capped"] is False


def test_cli_cites_and_neighbors(monkeypatch: pytest.MonkeyPatch) -> None:
    oa = "https://api.openalex.org"
    page = {
        "results": [{"id": "https://openalex.org/W2"}],
        "meta": {"next_cursor": None},
    }
    routes = {f"{oa}/works/W1": _WORK, f"{oa}/works": page, f"{oa}/works/W2": _WORK}
    monkeypatch.setattr(cli, "_lit_client", lambda: _client(routes))
    cites = runner.invoke(app, ["literature", "cites", "W1", "--max", "5"])
    assert cites.exit_code == 0
    assert json.loads(cites.stdout)[0]["id"]["openalex"] == "W2"
    nb = runner.invoke(
        app, ["literature", "neighbors", "W1", "--kind", "cocite", "--top", "3"]
    )
    assert nb.exit_code == 0
    assert "cocitation" in json.loads(nb.stdout)


def test_cli_enrich(monkeypatch: pytest.MonkeyPatch) -> None:
    routes = {"https://api.openalex.org/works/W1": _WORK}
    monkeypatch.setattr(cli, "_lit_client", lambda: _client(routes))
    result = runner.invoke(app, ["literature", "enrich", "W1", "--context"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)[0]["title"] == "A Title"


def test_cli_cites_unresolved_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_lit_client", lambda: _client({}))
    assert runner.invoke(app, ["literature", "cites", "W404"]).exit_code == 1


def test_lit_client_builds_from_config(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    monkeypatch.setenv("OPENALEX_MAILTO", "me@x.org")
    client = cli._lit_client()
    assert client.mailto == "me@x.org"


def test_lit_client_http_cache_defaults_under_cache_root(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    client = cli._lit_client()
    # Same root the dataset cache and research-init's .gitignore scaffold use
    # (defendable-science#65) — no more hardcoded, independently-drifting paths.
    assert client.cache_dir == tmp_path / cli._DEFAULT_CACHE_ROOT / "http"


def test_lit_client_http_cache_follows_configured_cache_dir(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / ".defendable-science"
    cfg.mkdir()
    (cfg / "config.yml").write_text("cache_dir: .custom-cache\n", encoding="utf-8")
    client = cli._lit_client()

    assert client.cache_dir == tmp_path / ".custom-cache/http"


class _BadJSON(FakeResponse):
    def json(self) -> object:
        raise ValueError("not json")


def test_http_s2_key_branch() -> None:
    client = http.HttpClient(
        session=FakeSession({"https://s2": {"ok": 1}}), s2_key="secret", cache_dir=None
    )
    assert client.get_json("https://s2", s2=True) == {"ok": 1}


def test_http_non_json_raises() -> None:
    client = http.HttpClient(
        session=FakeSession({"https://x": _BadJSON(200, None)}), cache_dir=None
    )
    with pytest.raises(http.HttpError, match="non-JSON"):
        client.get_json("https://x")


def test_neighbors_cocite_skips_idless_citer_and_self_ref() -> None:
    oa = "https://api.openalex.org"
    # citer 1 has no openalex id (skipped); citer 2 cites only the anchor (skipped).
    page = {
        "results": [{"id": None}, {"id": "https://openalex.org/W2"}],
        "meta": {"next_cursor": None},
    }
    w2 = {
        "id": "https://openalex.org/W2",
        "referenced_works": ["https://openalex.org/W1"],
    }
    out = graph.neighbors(
        "W1",
        client=_client({f"{oa}/works": [page], f"{oa}/works/W2": w2}),
        kind="cocite",
        frontier=10,
    )
    assert out["cocitation"] == []


def test_neighbors_couple_only_skips_self_citer() -> None:
    oa = "https://api.openalex.org"
    w1 = {"id": f"{oa[:-1]}/W1", "referenced_works": ["https://openalex.org/W9"]}
    anchor_cites = {"results": [], "meta": {"next_cursor": None}}
    w9_cites = {
        "results": [
            {"id": "https://openalex.org/W1"},
            {"id": "https://openalex.org/W2"},
        ],
        "meta": {"next_cursor": None},
    }
    routes = {f"{oa}/works": [anchor_cites, w9_cites], f"{oa}/works/W1": w1}
    out = graph.neighbors("W1", client=_client(routes), kind="couple", frontier=10)
    assert out["coupling"] == [{"openalex": "W2", "score": 1}]  # self W1 skipped
    assert "cocitation" not in out


# --- S2 enrichment + resolve cross-reference (defendable-science#31) --------------

_S2 = "https://api.semanticscholar.org/graph/v1"


def test_resolve_versioned_arxiv_strips_suffix() -> None:
    work = {"id": "https://openalex.org/W7", "display_name": "T"}
    # the DOI has no version component; a v4 suffix must be dropped
    client = _client(
        {"https://api.openalex.org/works/doi:10.48550/arXiv.2205.11775": work}
    )
    assert graph.resolve("arXiv:2205.11775v4", client=client)["resolved"] is True


def test_resolve_s2_id_crossrefs_via_doi() -> None:
    client = _client(
        {
            f"{_S2}/paper/CorpusId:12345": {"externalIds": {"DOI": "10.1234/abc"}},
            "https://api.openalex.org/works/doi:10.1234/abc": _WORK,
        }
    )
    rec = graph.resolve("CorpusId:12345", client=client)
    assert rec["resolved"] is True
    assert rec["openalex"] == "W1"


def test_resolve_s2_id_crossrefs_via_arxiv() -> None:
    work = {"id": "https://openalex.org/W7", "display_name": "T"}
    client = _client(
        {
            f"{_S2}/paper/CorpusId:7": {"externalIds": {"ArXiv": "2205.11775"}},
            "https://api.openalex.org/works/doi:10.48550/arXiv.2205.11775": work,
        }
    )
    assert graph.resolve("CorpusId:7", client=client)["openalex"] == "W7"


def test_resolve_s2_crossref_miss_is_not_fatal() -> None:
    rec = graph.resolve("CorpusId:404", client=_client({}))  # S2 404
    assert rec["resolved"] is False
    assert "cross-reference" in rec["reason"]


def test_resolve_s2_no_external_ids_is_miss() -> None:
    client = _client({f"{_S2}/paper/CorpusId:8": {"externalIds": {}}})
    assert graph.resolve("CorpusId:8", client=client)["resolved"] is False


def test_enrich_with_key_populates_s2_context() -> None:
    client = _client(
        {
            "https://api.openalex.org/works/W1": _WORK,
            f"{_S2}/paper/DOI:10.1234/abc": {"externalIds": {"CorpusId": 999}},
            f"{_S2}/paper/DOI:10.1234/abc/citations": {
                "data": [
                    {
                        "contexts": ["as shown in"],
                        "intents": ["methodology"],
                        "isInfluential": True,
                    },
                    # a second edge: snippet/intent already set, so it is skipped
                    {
                        "contexts": ["also"],
                        "intents": ["background"],
                        "isInfluential": False,
                    },
                ]
            },
        },
        s2_key="k",
    )
    rec = graph.enrich(["W1"], client=client, with_context=True)[0]
    assert "degraded" not in rec
    assert rec["context_snippet"] == "as shown in"
    assert rec["intent"] == "methodology"
    assert rec["is_influential"] is True
    assert rec["id"]["s2"] == "CorpusId:999"


def test_enrich_with_key_via_arxiv_id() -> None:
    work = {
        "id": "https://openalex.org/W2",
        "ids": {"arxiv": "https://arxiv.org/abs/2205.11775v2"},
    }
    client = _client(
        {
            "https://api.openalex.org/works/W2": work,
            f"{_S2}/paper/ARXIV:2205.11775": {"externalIds": {}},  # no CorpusId
            f"{_S2}/paper/ARXIV:2205.11775/citations": {
                "data": ["not-a-dict", {"contexts": ["x"], "intents": []}]
            },
        },
        s2_key="k",
    )
    rec = graph.enrich(["W2"], client=client, with_context=True)[0]
    assert rec["context_snippet"] == "x"
    assert rec["intent"] is None
    assert rec["is_influential"] is False  # edges present, none influential
    assert rec["id"]["s2"] is None


def test_enrich_with_key_no_addressable_id() -> None:
    """A work with no DOI/arXiv id was never *queried* — not "S2 had nothing".

    Both used to read as `context_snippet: null` with no `degraded` marker,
    making a work S2 was never asked about indistinguishable from one S2 was
    asked about and genuinely had nothing to say.
    """
    work = {"id": "https://openalex.org/W3", "display_name": "T"}  # no doi/arxiv
    client = _client({"https://api.openalex.org/works/W3": work}, s2_key="k")
    rec = graph.enrich(["W3"], client=client, with_context=True)[0]
    assert rec["context_snippet"] is None
    assert rec["degraded"] == ["context", "intent", "is_influential"]


def test_enrich_with_key_empty_citations_leaves_influential_none() -> None:
    client = _client(
        {
            "https://api.openalex.org/works/W1": _WORK,
            f"{_S2}/paper/DOI:10.1234/abc": {"externalIds": {"CorpusId": 1}},
            f"{_S2}/paper/DOI:10.1234/abc/citations": {"data": []},
        },
        s2_key="k",
    )
    rec = graph.enrich(["W1"], client=client, with_context=True)[0]
    assert rec["is_influential"] is None


def test_enrich_with_key_citations_error_returns_partial() -> None:
    # meta resolves (s2 id set) but the citations sub-resource 404s
    client = _client(
        {
            "https://api.openalex.org/works/W1": _WORK,
            f"{_S2}/paper/DOI:10.1234/abc": {"externalIds": {"CorpusId": 2}},
        },
        s2_key="k",
    )
    rec = graph.enrich(["W1"], client=client, with_context=True)[0]
    assert rec["id"]["s2"] == "CorpusId:2"
    assert rec["context_snippet"] is None


def test_enrich_with_key_meta_error_still_reads_citations() -> None:
    # meta 404s (no CorpusId) but citations resolve
    client = _client(
        {
            "https://api.openalex.org/works/W1": _WORK,
            f"{_S2}/paper/DOI:10.1234/abc/citations": {
                "data": [
                    {"contexts": ["c"], "intents": ["result"], "isInfluential": False}
                ]
            },
        },
        s2_key="k",
    )
    rec = graph.enrich(["W1"], client=client, with_context=True)[0]
    assert rec["id"]["s2"] is None
    assert rec["context_snippet"] == "c"
    assert rec["is_influential"] is False


def test_neighbors_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown kind"):
        graph.neighbors("W1", client=_client({}), kind="bogus")


def test_cli_neighbors_bad_kind_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    routes = {"https://api.openalex.org/works/W1": _WORK}
    monkeypatch.setattr(cli, "_lit_client", lambda: _client(routes))
    result = runner.invoke(app, ["literature", "neighbors", "W1", "--kind", "bogus"])
    assert result.exit_code == 1


def test_lit_client_rejects_non_mapping_config(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / ".defendable-science"
    cfg.mkdir()
    (cfg / "config.yml").write_text("- not\n- a mapping\n", encoding="utf-8")
    with pytest.raises(typer.Exit) as exc:
        cli._lit_client()
    assert exc.value.exit_code == 1


# --- rate-limit / transient-error honesty (defendable-science#41) ----------------


def test_http_honors_retry_after_header() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        {
            "https://x": [
                FakeResponse(429, {}, {"Retry-After": "7"}),
                FakeResponse(200, {"ok": 1}),
            ]
        }
    )
    client = http.HttpClient(session=session, sleep=sleeps.append, cache_dir=None)
    assert client.get_json("https://x") == {"ok": 1}
    assert sleeps == [7.0]  # honored the header, not the blind 2**0 backoff


def test_http_retry_after_http_date_falls_back_to_backoff() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        {
            "https://x": [
                FakeResponse(429, {}, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),
                FakeResponse(200, {"ok": 1}),
            ]
        }
    )
    client = http.HttpClient(session=session, sleep=sleeps.append, cache_dir=None)
    assert client.get_json("https://x") == {"ok": 1}
    # An HTTP-date is unparsable → ignored → exponential backoff (2**0) + jitter.
    assert len(sleeps) == 1
    assert 1.0 <= sleeps[0] < 2.0


def test_http_429_exhaustion_raises_rate_limit_error() -> None:
    session = FakeSession({"https://x": FakeResponse(429, {})})
    client = http.HttpClient(
        session=session, sleep=lambda _s: None, cache_dir=None, max_retries=2
    )
    with pytest.raises(http.RateLimitError, match="giving up"):
        client.get_json("https://x")


def test_http_503_with_retry_after_raises_rate_limit_error() -> None:
    session = FakeSession({"https://x": FakeResponse(503, {}, {"Retry-After": "1"})})
    client = http.HttpClient(
        session=session, sleep=lambda _s: None, cache_dir=None, max_retries=2
    )
    with pytest.raises(http.RateLimitError):
        client.get_json("https://x")


def test_http_503_without_retry_after_is_plain_http_error() -> None:
    session = FakeSession({"https://x": FakeResponse(503, {})})
    client = http.HttpClient(
        session=session, sleep=lambda _s: None, cache_dir=None, max_retries=2
    )
    with pytest.raises(http.HttpError) as exc:
        client.get_json("https://x")
    assert not isinstance(exc.value, http.RateLimitError)  # 503 sans header is not RL


# --- proactive rate limiting (defendable-science#67) ------------------------------


class FakeClock:
    """A deterministic clock/sleep pair: ``sleep`` advances ``now`` in lockstep.

    Keeps the throttle tests fully offline and exact — no real wall-clock time
    ever elapses, but the elapsed-time arithmetic in
    :meth:`http.HttpClient._throttle` behaves as if it had.
    """

    def __init__(self, start: float = 0.0) -> None:
        self.t = start
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


def test_http_throttle_spaces_back_to_back_s2_calls() -> None:
    clock = FakeClock()
    session = FakeSession({"https://s2/a": {"n": 1}, "https://s2/b": {"n": 2}})
    client = http.HttpClient(
        session=session,
        cache_dir=None,
        s2_rps=1.0,
        clock=clock.now,
        sleep=clock.sleep,
    )
    client.get_json("https://s2/a", s2=True)
    client.get_json("https://s2/b", s2=True)
    # No 429 round-trip involved: the second call alone triggers exactly one
    # sleep, for the full 1s/req interval (elapsed time since the first was 0).
    assert clock.sleeps == [1.0]
    assert clock.t == 1.0


def test_http_throttle_no_wait_when_interval_already_elapsed() -> None:
    clock = FakeClock()
    session = FakeSession({"https://s2/a": {"n": 1}, "https://s2/b": {"n": 2}})
    client = http.HttpClient(
        session=session,
        cache_dir=None,
        s2_rps=1.0,
        clock=clock.now,
        sleep=clock.sleep,
    )
    client.get_json("https://s2/a", s2=True)
    clock.t += 5.0  # plenty of real time passed between calls
    client.get_json("https://s2/b", s2=True)
    assert clock.sleeps == []  # already spaced further apart than min_interval


def test_http_throttle_tracks_s2_and_openalex_independently() -> None:
    clock = FakeClock()
    session = FakeSession({"https://s2/a": {"n": 1}, "https://oa/a": {"n": 2}})
    client = http.HttpClient(
        session=session,
        cache_dir=None,
        s2_rps=1.0,
        openalex_rps=1.0,
        clock=clock.now,
        sleep=clock.sleep,
    )
    client.get_json("https://s2/a", s2=True)
    client.get_json("https://oa/a", s2=False)
    # Different hosts, same instant: neither has a prior send on *its* key.
    assert clock.sleeps == []


def test_http_throttle_tracks_arxiv_independently_of_openalex() -> None:
    """Fix round 1: arXiv used to be throttled under the "openalex" key.

    ``get_text`` (arXiv's only current caller) must pace against its own
    "arxiv" key, never against — or in competition with — OpenAlex traffic
    through ``get_json``.
    """
    clock = FakeClock()
    session = FakeSession(
        {"https://oa/a": {"n": 1}, "https://arxiv/a": FakeResponse(200, None, text="x")}
    )
    client = http.HttpClient(
        session=session,
        cache_dir=None,
        openalex_rps=1.0,
        arxiv_rps=1.0,
        clock=clock.now,
        sleep=clock.sleep,
    )
    client.get_json("https://oa/a", s2=False)
    client.get_text("https://arxiv/a")
    # Same instant, different hosts: neither has a prior send on its own key.
    assert clock.sleeps == []


def test_http_throttle_spaces_back_to_back_arxiv_calls() -> None:
    clock = FakeClock()
    session = FakeSession(
        {
            "https://arxiv/a": FakeResponse(200, None, text="a"),
            "https://arxiv/b": FakeResponse(200, None, text="b"),
        }
    )
    client = http.HttpClient(
        session=session,
        cache_dir=None,
        arxiv_rps=1.0,
        clock=clock.now,
        sleep=clock.sleep,
    )
    client.get_text("https://arxiv/a")
    client.get_text("https://arxiv/b")
    assert clock.sleeps == [1.0]


def test_http_throttle_disabled_when_rps_is_zero() -> None:
    clock = FakeClock()
    session = FakeSession({"https://s2/a": {"n": 1}, "https://s2/b": {"n": 2}})
    client = http.HttpClient(
        session=session, cache_dir=None, s2_rps=0.0, clock=clock.now, sleep=clock.sleep
    )
    client.get_json("https://s2/a", s2=True)
    client.get_json("https://s2/b", s2=True)
    assert clock.sleeps == []


def test_http_throttle_defaults_are_conservative_for_s2_and_polite_for_openalex() -> (
    None
):
    client = http.HttpClient(cache_dir=None)
    assert client.s2_rps < 1.0  # strictly below S2's 1 req/s cumulative ceiling
    assert client.openalex_rps == 10.0  # OpenAlex's documented ceiling


def test_http_throttle_runs_once_per_call_not_per_retry() -> None:
    # Retries within one get_json() call must keep relying on the existing
    # reactive Retry-After/backoff handling, unchanged — not get re-throttled.
    sleeps: list[float] = []
    session = FakeSession(
        {"https://x": [FakeResponse(429, {}, {"Retry-After": "7"}), {"ok": 1}]}
    )
    client = http.HttpClient(session=session, sleep=sleeps.append, cache_dir=None)
    assert client.get_json("https://x") == {"ok": 1}
    assert sleeps == [7.0]  # only the Retry-After sleep — no extra throttle sleep


def test_lit_client_reads_rps_from_config(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / ".defendable-science"
    cfg.mkdir()
    (cfg / "config.yml").write_text(
        "literature:\n  s2_rps: 0.5\n  openalex_rps: 3\n", encoding="utf-8"
    )
    client = cli._lit_client()
    assert client.s2_rps == 0.5
    assert client.openalex_rps == 3.0


def test_lit_client_rejects_non_numeric_rps(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / ".defendable-science"
    cfg.mkdir()
    (cfg / "config.yml").write_text(
        "literature:\n  s2_rps: not-a-number\n", encoding="utf-8"
    )
    with pytest.raises(typer.Exit) as exc:
        cli._lit_client()
    assert exc.value.exit_code == 1


def test_resolve_rate_limit_propagates_not_miss() -> None:
    # A throttle must never be recorded as {resolved: False} ("no such work").
    client = _client(
        {"https://api.openalex.org/works/W1": FakeResponse(429, {})}, max_retries=2
    )
    with pytest.raises(http.RateLimitError):
        graph.resolve("W1", client=client)


def test_resolve_404_still_returns_genuine_miss() -> None:
    # The genuine not-found path is preserved: 404 → resolved False, not a raise.
    rec = graph.resolve("W404", client=_client({}))
    assert rec["resolved"] is False
    # The negative: a genuine 404 must never carry the transport discriminator.
    assert "transport_error" not in rec


def test_resolve_transport_error_is_distinguishable_from_a_miss() -> None:
    # A 502 that exhausts retries is a transport failure, not "no such paper" —
    # defendable-science#106. It must not be reportable as the same shape a
    # genuine miss gets.
    client = _client(
        {"https://api.openalex.org/works/W1": FakeResponse(502, {})}, max_retries=2
    )
    rec = graph.resolve("W1", client=client)
    assert rec["resolved"] is False
    assert rec["transport_error"] is True


def test_resolve_non_json_body_is_transport_error_not_a_miss() -> None:
    # A 200 with an undecodable body is also a transport-layer fault, not a
    # legitimate "this paper does not exist" — same discriminator applies.
    bad = FakeResponse(200, {})

    def _raise() -> Any:
        raise ValueError("boom")

    bad.json = _raise  # type: ignore[method-assign]
    client = _client({"https://api.openalex.org/works/W1": bad})
    rec = graph.resolve("W1", client=client)
    assert rec["resolved"] is False
    assert rec["transport_error"] is True


def test_resolve_s2_crossref_rate_limit_propagates() -> None:
    client = _client({f"{_S2}/paper/CorpusId:9": FakeResponse(429, {})}, max_retries=2)
    with pytest.raises(http.RateLimitError):
        graph.resolve("CorpusId:9", client=client)


def test_enrich_s2_context_meta_rate_limit_propagates() -> None:
    client = _client(
        {
            "https://api.openalex.org/works/W1": _WORK,
            f"{_S2}/paper/DOI:10.1234/abc": FakeResponse(429, {}),
        },
        s2_key="k",
        max_retries=2,
    )
    with pytest.raises(http.RateLimitError):
        graph.enrich(["W1"], client=client, with_context=True)


def test_enrich_s2_context_citations_rate_limit_propagates() -> None:
    client = _client(
        {
            "https://api.openalex.org/works/W1": _WORK,
            f"{_S2}/paper/DOI:10.1234/abc": {"externalIds": {"CorpusId": 5}},
            f"{_S2}/paper/DOI:10.1234/abc/citations": FakeResponse(429, {}),
        },
        s2_key="k",
        max_retries=2,
    )
    with pytest.raises(http.RateLimitError):
        graph.enrich(["W1"], client=client, with_context=True)


@pytest.mark.parametrize(
    "argv",
    [
        ["literature", "resolve", "W1"],
        ["literature", "cites", "W1"],
        ["literature", "refs", "W1"],
        ["literature", "enrich", "W1"],
        ["literature", "neighbors", "W1"],
    ],
)
def test_cli_rate_limit_exits_1_with_actionable_message(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(
        {"https://api.openalex.org/works/W1": FakeResponse(429, {})}, max_retries=2
    )
    monkeypatch.setattr(cli, "_lit_client", lambda: client)
    result = runner.invoke(app, argv)
    assert result.exit_code == 1
    assert not isinstance(result.exception, http.RateLimitError)  # no traceback
    assert "rate-limited" in result.stderr
    assert "S2_API_KEY" in result.stderr


def test_cli_generic_http_error_exits_1_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A non-rate-limit transport failure exits cleanly with a generic message.
    routes = {
        "https://api.openalex.org/works/W1": _WORK,
        "https://api.openalex.org/works": FakeResponse(403, {}),
    }
    monkeypatch.setattr(cli, "_lit_client", lambda: _client(routes))
    result = runner.invoke(app, ["literature", "cites", "W1"])
    assert result.exit_code == 1
    assert not isinstance(result.exception, http.HttpError)  # no traceback
    assert "literature request failed" in result.stderr
    assert "403" in result.stderr


def test_lit_client_rejects_non_dict_literature_block(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / ".defendable-science"
    cfg.mkdir()
    # A present-but-non-dict `literature:` block is a config error, not silently
    # discarded (which would drop `mailto` without a word).
    (cfg / "config.yml").write_text("literature: just-a-string\n", encoding="utf-8")
    with pytest.raises(typer.Exit) as exc:
        cli._lit_client()
    assert exc.value.exit_code == 1


# --- boundary-validation regressions (defendable-science#169) --------------------


def test_cites_rejects_a_non_dict_result_row() -> None:
    """Defect 1: a junk row raised AttributeError mid-pagination."""
    from defendable_science.core.http import HttpError

    client = _client(
        {
            "https://api.openalex.org/works": {
                "results": [_WORK, "not-a-work"],
                "meta": {"next_cursor": None},
            }
        }
    )
    with pytest.raises(HttpError, match=r"results\.1"):
        graph.cites("W1", client=client)


def test_enrich_work_rejects_a_non_mapping_inverted_index() -> None:
    """Defect 2: `index.items()` raised AttributeError on a string."""
    from defendable_science.core.http import HttpError

    bad = {**_WORK, "abstract_inverted_index": "Hello world"}
    with pytest.raises(HttpError, match=r"abstract_inverted_index"):
        graph.parse_work(bad, source="test")


def test_s2_edge_with_a_string_contexts_never_yields_one_character() -> None:
    """Defect 3: `edge["contexts"][0]` on a bare string yielded its first char."""
    out: dict[str, object] = {
        "s2": None,
        "context_snippet": None,
        "intent": None,
        "is_influential": None,
    }
    skipped = graph._aggregate_s2_edges([{"contexts": "Hello", "intents": []}], out)
    assert out["context_snippet"] != "H"
    assert out["context_snippet"] is None
    assert skipped == 1


def test_enrich_marks_degraded_when_an_s2_edge_is_skipped() -> None:
    """Defect 3, at the seam a consumer actually reads."""
    oa = "https://api.openalex.org"
    s2 = "https://api.semanticscholar.org/graph/v1"
    client = _client(
        {
            f"{oa}/works/W1": _WORK,
            f"{s2}/paper/DOI:10.1234/abc": {"externalIds": {"CorpusId": 7}},
            f"{s2}/paper/DOI:10.1234/abc/citations": {
                "data": [{"contexts": "Hello", "intents": [], "isInfluential": False}]
            },
        },
        s2_key="k",
    )
    (record,) = graph.enrich(["W1"], client=client, with_context=True)
    assert record["context_snippet"] is None
    assert record["degraded"] == ["context", "intent", "is_influential"]


def test_enrich_work_rejects_a_string_publication_year() -> None:
    """Defect 4: a string year propagated into the record and out through the CLI."""
    from defendable_science.core.http import HttpError

    bad = {**_WORK, "publication_year": "2023"}
    with pytest.raises(HttpError, match=r"publication_year"):
        graph.parse_work(bad, source="test")


def test_resolve_malformed_200_body_is_transport_error_not_a_miss() -> None:
    # A 200 body of the wrong shape is neither a genuine miss nor a clean
    # fetch — it must carry transport_error, same as any other transport fault
    # (ADR-0043 decision point 4).
    client = _client({"https://api.openalex.org/works/W1": "not-a-work"})
    rec = graph.resolve("W1", client=client)
    assert rec["resolved"] is False
    assert rec["transport_error"] is True
    pattern = rf"{re.escape('https://api.openalex.org/works/W1')}: <root>: Input should be a valid dictionary"
    assert re.search(pattern, rec["reason"])


# --- S2 leg fix wave: converted halfway, whole-branch review (#169) ---------


def test_enrich_with_key_malformed_meta_body_degrades_with_marker() -> None:
    """Item 1: a malformed S2 metadata body used to hard-fail the whole call.

    S2 is an optional, best-effort enrichment (spec §3.4) — a malformed
    ``/paper`` body must degrade like the transport-error path already does,
    not raise; and the lost ``s2`` id must show up in ``degraded``, not
    vanish silently.
    """
    client = _client(
        {
            "https://api.openalex.org/works/W1": _WORK,
            f"{_S2}/paper/DOI:10.1234/abc": "not-a-dict",
            f"{_S2}/paper/DOI:10.1234/abc/citations": {
                "data": [{"contexts": ["c"], "intents": [], "isInfluential": False}]
            },
        },
        s2_key="k",
    )
    rec = graph.enrich(["W1"], client=client, with_context=True)[0]
    assert rec["id"]["s2"] is None
    assert rec["context_snippet"] == "c"
    assert rec["degraded"] == ["s2"]


def test_enrich_with_key_null_citations_data_degrades_not_crashes() -> None:
    """Item 2a: ``{"data": null}`` used to raise a raw ``TypeError``.

    ``'NoneType' object is not iterable`` used to escape `_http_guard` as a
    traceback from ``literature enrich --context``; it must degrade instead.
    """
    client = _client(
        {
            "https://api.openalex.org/works/W1": _WORK,
            f"{_S2}/paper/DOI:10.1234/abc": {"externalIds": {"CorpusId": 3}},
            f"{_S2}/paper/DOI:10.1234/abc/citations": {"data": None},
        },
        s2_key="k",
    )
    rec = graph.enrich(["W1"], client=client, with_context=True)[0]
    assert rec["id"]["s2"] == "CorpusId:3"
    assert rec["context_snippet"] is None
    assert rec["degraded"] == ["context", "intent", "is_influential"]


def test_enrich_with_key_non_dict_citations_page_degrades_with_marker() -> None:
    """Item 2b: a non-dict ``/citations`` body used to be reported as clean.

    It used to yield all-``None`` with no ``degraded`` marker — a failure
    disguised as "S2 had nothing".
    """
    client = _client(
        {
            "https://api.openalex.org/works/W1": _WORK,
            f"{_S2}/paper/DOI:10.1234/abc": {"externalIds": {"CorpusId": 4}},
            f"{_S2}/paper/DOI:10.1234/abc/citations": "not-a-dict",
        },
        s2_key="k",
    )
    rec = graph.enrich(["W1"], client=client, with_context=True)[0]
    assert rec["id"]["s2"] == "CorpusId:4"
    assert rec["context_snippet"] is None
    assert rec["degraded"] == ["context", "intent", "is_influential"]


def test_resolve_s2_crossref_malformed_body_is_transport_error_not_a_miss() -> None:
    """Item 3: `resolve()`'s S2 leg used to report this defect differently.

    It reported exit 1 (a genuine miss) while the OpenAlex leg of the same
    function reports exit 3 (transport_error) for the identical defect.
    """
    client = _client({f"{_S2}/paper/CorpusId:7": "not-a-dict"})
    rec = graph.resolve("CorpusId:7", client=client)
    assert rec["resolved"] is False
    assert rec["transport_error"] is True
    pattern = rf"{re.escape(f'{_S2}/paper/CorpusId:7')}: <root>: Input should be a valid dictionary"
    assert re.search(pattern, rec["reason"])


# --- final-review fix wave: dropped null guards (default_factory covers a
# missing key, never an explicit JSON `null`, under `strict=True`) ----------


def test_resolve_s2_crossref_null_external_ids_is_a_clean_miss() -> None:
    """A well-formed S2 record with no DOI/arXiv is not a transport fault.

    `default_factory=_ExternalIdBundle` only covered a *missing*
    ``externalIds`` key; S2 sends an explicit `null` for a paper with none,
    and `strict=True` used to reject that as if the body were malformed —
    reporting exit 3 (transport_error) for a legitimate exit-1 miss.
    """
    client = _client(
        {f"{_S2}/paper/CorpusId:7": {"paperId": "abc", "externalIds": None}}
    )
    rec = graph.resolve("CorpusId:7", client=client)
    assert rec["resolved"] is False
    assert "transport_error" not in rec
    assert "could not cross-reference" in rec["reason"]


def test_s2_context_null_external_ids_is_not_meta_skipped() -> None:
    """Item 1's mirror: an explicit `externalIds: null` is not a lost signal.

    Before the fix this raised inside the best-effort guard and set
    `meta_skipped`, over-reporting `degraded` on a paper that genuinely has
    no cross-reference ids.
    """
    client = _client(
        {
            "https://api.openalex.org/works/W1": _WORK,
            f"{_S2}/paper/DOI:10.1234/abc": {"paperId": "abc", "externalIds": None},
            f"{_S2}/paper/DOI:10.1234/abc/citations": {
                "data": [{"contexts": ["c"], "intents": ["bg"], "isInfluential": True}]
            },
        },
        s2_key="k",
    )
    rec = graph.enrich(["W1"], client=client, with_context=True)[0]
    assert rec["id"]["s2"] is None
    assert "degraded" not in rec


def test_s2_context_falsy_but_present_meta_body_is_marked_skipped() -> None:
    """A malformed-but-falsy `/paper` body must not be mistaken for a miss.

    `if meta:` could not distinguish "S2 could not be reached" from "S2 sent
    `None`/`[]`/`0`/`""` on a 200" — every falsy body silently passed as a
    legitimate no-id result with no marker. Checking by identity against a
    transport-miss sentinel closes the gap for all four cases at once.

    ``None`` and ``[]`` are wrapped in an explicit :class:`FakeResponse`
    because :class:`FakeSession`'s own routing protocol repurposes a bare
    ``None`` route value as "no route configured" (a real 404) and a bare
    ``list`` as a queue of successive responses — both would collide with
    the very falsy *bodies* this test needs to send on a 200.
    """
    for meta in (FakeResponse(200, None), FakeResponse(200, []), 0, ""):
        client = _client(
            {
                "https://api.openalex.org/works/W1": _WORK,
                f"{_S2}/paper/DOI:10.1234/abc": meta,
                f"{_S2}/paper/DOI:10.1234/abc/citations": {"data": []},
            },
            s2_key="k",
        )
        rec = graph.enrich(["W1"], client=client, with_context=True)[0]
        assert rec["degraded"] == ["s2"], f"meta={meta!r}"


def test_cites_null_meta_ends_pagination_without_discarding_the_page() -> None:
    """`"meta": null` must not abort the whole citation frontier.

    `meta: _PageMeta = Field(default_factory=_PageMeta)` covered a *missing*
    key but not a `null` one; `strict=True` rejected the `null`, raising
    `HttpError` and discarding every page already collected — for a body
    OpenAlex sends to mean exactly "no further cursor".
    """
    client = _client(
        {
            "https://api.openalex.org/works": {
                "results": [{"id": "https://openalex.org/W2"}],
                "meta": None,
            }
        }
    )
    rows = graph.cites("W1", client=client)
    assert [r["id"]["openalex"] for r in rows] == ["W2"]


def test_s2_context_all_valid_edges_omit_edges_skipped_entirely() -> None:
    """`edges_skipped` must be absent, not merely falsy, when nothing was lost.

    The docstring promises the bookkeeping keys are "absent entirely when
    nothing was lost"; the count used to be assigned unconditionally,
    including a `0`, contradicting it for any reader using `"key" in bundle`.
    """
    client = _client(
        {
            "https://api.openalex.org/works/W1": _WORK,
            f"{_S2}/paper/DOI:10.1234/abc": {"externalIds": {"CorpusId": 9}},
            f"{_S2}/paper/DOI:10.1234/abc/citations": {
                "data": [{"contexts": ["c"], "intents": ["bg"], "isInfluential": True}]
            },
        },
        s2_key="k",
    )
    bundle = graph._s2_context(client, "DOI:10.1234/abc")
    assert "edges_skipped" not in bundle


def test_enrich_partial_edge_loss_does_not_degrade_recovered_samples() -> None:
    """One skipped edge among many survivors must not distrust real *samples*.

    `context_snippet`/`intent` used to be marked degraded whenever
    `edges_skipped` was truthy, even when a surviving edge supplied a real
    value — telling a consumer two correct, populated fields were
    unreliable. `is_influential` is different: it is an aggregate over every
    edge, so it is still marked degraded even though its value (`True`, here)
    happens to be correct — see the next test for the case where it is not.
    """
    client = _client(
        {
            "https://api.openalex.org/works/W1": _WORK,
            f"{_S2}/paper/DOI:10.1234/abc": {"externalIds": {"CorpusId": 10}},
            f"{_S2}/paper/DOI:10.1234/abc/citations": {
                "data": [
                    {"contexts": "Hello", "intents": []},
                    {"contexts": ["c"], "intents": ["bg"], "isInfluential": True},
                ]
            },
        },
        s2_key="k",
    )
    rec = graph.enrich(["W1"], client=client, with_context=True)[0]
    assert rec["context_snippet"] == "c"
    assert rec["intent"] == "bg"
    assert rec["is_influential"] is True
    assert rec["degraded"] == ["is_influential"]


def test_enrich_total_edge_loss_still_degrades_all_three_fields() -> None:
    """The mirror of the previous test: nothing recovered means genuinely degraded."""
    client = _client(
        {
            "https://api.openalex.org/works/W1": _WORK,
            f"{_S2}/paper/DOI:10.1234/abc": {"externalIds": {"CorpusId": 11}},
            f"{_S2}/paper/DOI:10.1234/abc/citations": {
                "data": [{"contexts": "Hello", "intents": "bad"}]
            },
        },
        s2_key="k",
    )
    rec = graph.enrich(["W1"], client=client, with_context=True)[0]
    assert rec["degraded"] == ["context", "intent", "is_influential"]


def test_s2_edge_with_null_is_influential_keeps_its_context_and_intent() -> None:
    """An explicit `"isInfluential": null` must not drop the whole edge.

    `is_influential: bool = Field(default=False, ...)` under `strict=True`
    rejected the null, so `parse_each` dropped the entire edge — not just the
    flag — losing a real `contexts`/`intents` value in the process.
    """
    out: dict[str, object] = {
        "s2": None,
        "context_snippet": None,
        "intent": None,
        "is_influential": None,
    }
    skipped = graph._aggregate_s2_edges(
        [{"contexts": ["c"], "intents": ["bg"], "isInfluential": None}], out
    )
    assert skipped == 0
    assert out["context_snippet"] == "c"
    assert out["intent"] == "bg"
    assert out["is_influential"] is False


@pytest.mark.parametrize(
    ("edge", "wanted"),
    [
        pytest.param(
            {"contexts": None, "intents": ["bg"], "isInfluential": True},
            (None, "bg", True),
            id="null-contexts-keeps-intent-and-flag",
        ),
        pytest.param(
            {"contexts": ["c"], "intents": None, "isInfluential": True},
            ("c", None, True),
            id="null-intents-keeps-context-and-flag",
        ),
    ],
)
def test_s2_edge_with_a_null_list_field_keeps_the_rest_of_the_edge(
    edge: dict[str, object], wanted: tuple[str | None, str | None, bool]
) -> None:
    """A null `contexts`/`intents` must not take the rest of the edge with it.

    `Field(default_factory=list)` covered a missing key but not a present
    `null`, so `strict=True` rejected the edge outright and `parse_each`
    dropped every *other* field on it too. For an edge, null and absent mean
    the same thing, so nothing is gained by distinguishing them.
    """
    out: dict[str, object] = {
        "s2": None,
        "context_snippet": None,
        "intent": None,
        "is_influential": None,
    }
    skipped = graph._aggregate_s2_edges([edge], out)
    assert skipped == 0
    assert (out["context_snippet"], out["intent"], out["is_influential"]) == wanted


def test_s2_edge_with_a_non_list_contexts_is_still_skipped() -> None:
    """Tolerating `null` must not also start tolerating a genuinely wrong type.

    This is the defect-3 guarantee: a bare string `contexts` used to yield
    its *first character* as the citation context. It must still be rejected.
    """
    out: dict[str, object] = {
        "s2": None,
        "context_snippet": None,
        "intent": None,
        "is_influential": None,
    }
    skipped = graph._aggregate_s2_edges([{"contexts": "Hello", "intents": []}], out)
    assert skipped == 1
    assert out["context_snippet"] is None


def test_enrich_marks_is_influential_degraded_even_when_samples_survive() -> None:
    """A dropped influential edge can silently flip `is_influential` to `False`.

    `context_snippet`/`intent` are representative samples — a surviving edge
    legitimately supplies them, so they must not be marked degraded. But
    `is_influential` is an aggregate over *every* edge (`any(...)`): dropping
    the one influential edge and keeping a non-influential survivor computes
    a confident `False` when the true answer is `True`. It must be marked
    degraded even though it is not `None`.
    """
    client = _client(
        {
            "https://api.openalex.org/works/W1": _WORK,
            f"{_S2}/paper/DOI:10.1234/abc": {"externalIds": {"CorpusId": 12}},
            f"{_S2}/paper/DOI:10.1234/abc/citations": {
                "data": [
                    {
                        "contexts": "an influential mention",  # malformed: not a list
                        "intents": ["bg"],
                        "isInfluential": True,
                    },
                    {"contexts": ["c"], "intents": ["bg"], "isInfluential": False},
                ]
            },
        },
        s2_key="k",
    )
    rec = graph.enrich(["W1"], client=client, with_context=True)[0]
    assert rec["context_snippet"] == "c"
    assert rec["intent"] == "bg"
    assert rec["is_influential"] is False  # the value is unreliable, not corrected
    assert rec["degraded"] == ["is_influential"]
