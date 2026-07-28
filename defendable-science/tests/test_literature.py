"""Tests for the citation-graph client + HTTP layer (defendable-science#1)."""

from __future__ import annotations

import json
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
        self, status_code: int, payload: Any, headers: dict[str, str] | None = None
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers: dict[str, str] = headers or {}

    def json(self) -> Any:
        return self._payload


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
    with pytest.raises(http.HttpError, match="giving up"):
        client.get_json("https://x")


def test_http_4xx_is_fatal() -> None:
    client = _client({"https://x": FakeResponse(404, {})})
    with pytest.raises(http.HttpError, match="HTTP 404"):
        client.get_json("https://x")


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


def test_enrich_work_reconstructs_abstract() -> None:
    rec = graph.enrich_work(_WORK)
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
    # A non-dict 200 body must not be coerced to a hollow {} work.
    client = _client({"https://api.openalex.org/works/W1": ["not-a-dict"]})
    with pytest.raises(http.HttpError, match="not an OpenAlex work"):
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


def test_cli_resolve_miss_exits_0_with_resolved_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "_lit_client", lambda: _client({}))
    result = runner.invoke(app, ["literature", "resolve", "W404"])
    assert result.exit_code == 0  # resolve reports, never crashes
    assert json.loads(result.stdout)["resolved"] is False


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
    assert graph._abstract({}) is None  # no inverted index


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
    client = _client({"https://api.openalex.org/works": ["not-a-dict"]})
    with pytest.raises(http.HttpError, match="not a JSON object"):
        graph.cites("W1", client=client)


def test_cites_non_dict_page_mid_pagination_raises() -> None:
    # A truncated frontier must never be returned as if complete.
    page1 = {
        "results": [{"id": "https://openalex.org/W2"}],
        "meta": {"next_cursor": "c2"},
    }
    client = _client({"https://api.openalex.org/works": [page1, "not-a-dict"]})
    with pytest.raises(http.HttpError, match="not a JSON object"):
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
    assert client.cache_dir == cli._DEFAULT_CACHE_ROOT / "http"


def test_lit_client_http_cache_follows_configured_cache_dir(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / ".defendable-science"
    cfg.mkdir()
    (cfg / "config.yml").write_text("cache_dir: .custom-cache\n", encoding="utf-8")
    client = cli._lit_client()
    from pathlib import Path

    assert client.cache_dir == Path(".custom-cache/http")


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
    work = {"id": "https://openalex.org/W3", "display_name": "T"}  # no doi/arxiv
    client = _client({"https://api.openalex.org/works/W3": work}, s2_key="k")
    rec = graph.enrich(["W3"], client=client, with_context=True)[0]
    assert rec["context_snippet"] is None
    assert "degraded" not in rec


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
