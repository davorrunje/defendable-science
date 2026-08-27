"""Tests for the literature acquisition ladder and its match gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from defendable_science.core.download import FetchedBytes
from defendable_science.literature import acquire as a
from defendable_science.literature import registry as reg


def _entry(
    citekey: str = "sill1997monotonic",
    title: str | None = "Monotonic Networks",
    year: int | None = 1997,
    family: str | None = "Sill",
) -> reg.Entry:
    return reg.Entry(
        citekey=citekey,
        title=title,
        year=year,
        first_author_family=family,
        doi=None,
        asset=None,
        raw={"id": citekey},
    )


def _cand(**kw: Any) -> a.Candidate:
    base: dict[str, Any] = {"url": "http://x/p.pdf", "rung": a.RUNG_ARXIV_SEARCH}
    base.update(kw)
    return a.Candidate(**base)


# --- normalization ----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Monotonic Networks", "monotonic networks"),
        (
            "MonoKAN: Certified Monotonic Kolmogorov-Arnold Network",
            "monokan certified monotonic kolmogorov arnold network",
        ),
        (
            "MonoKAN: Certified monotonic Kolmogorov-Arnold network",
            "monokan certified monotonic kolmogorov arnold network",
        ),
        ("  Spaced   Out  ", "spaced out"),
        ("Hyphen-Ated, Punctuated!", "hyphen ated punctuated"),
    ],
)
def test_normalize_title(raw: str, expected: str) -> None:
    assert a.normalize_title(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Sill", "sill"), ("Bélair", "belair"), ("  van Dijk ", "van dijk")],
)
def test_fold_name(raw: str, expected: str) -> None:
    assert a.fold_name(raw) == expected


# --- the gate ---------------------------------------------------------------


def test_the_named_regression_refuses_igel_for_sill() -> None:
    """#97's acceptance criterion.

    An arXiv title search for "Monotonic Networks" (Sill, NIPS 1997) returned
    arXiv:2306.01147 — Igel's *Smooth Min-Max Monotonic Networks* (2023). A wrong
    PDF bound to a citekey is strictly worse than no PDF: the reader digests the
    wrong paper, cites it as the other, and digest's comprehension check passes,
    because it verifies understanding of the bytes it was given.
    """
    record = a.evaluate_match(
        _entry(),
        _cand(
            title="Smooth Min-Max Monotonic Networks",
            year=2023,
            first_author_family="Igel",
        ),
    )
    assert record.verdict == a.REFUSE
    assert record.author == "mismatch"
    assert record.title == "mismatch"
    assert record.year == "mismatch"
    assert record.reason is not None


def test_author_mismatch_alone_refuses_even_on_a_perfect_title_and_year() -> None:
    """The load-bearing invariant: author family name is a hard gate."""
    record = a.evaluate_match(
        _entry(),
        _cand(title="Monotonic Networks", year=1997, first_author_family="Igel"),
    )
    assert record.verdict == a.REFUSE
    assert record.author == "mismatch"
    assert record.title == "exact"
    assert record.year == "exact"


def test_monokan_sibling_version_is_accepted_across_one_year() -> None:
    """The positive counterpart — a real preprint/journal pair.

    The registry entry is the 2025 *Neural Networks* version; the candidate is the
    2024 arXiv work. Tightening the year window to exact would break every pair
    like this, which is why this test exists next to the refusal above.
    """
    record = a.evaluate_match(
        _entry(
            citekey="monokan",
            title="MonoKAN: Certified monotonic Kolmogorov-Arnold network",
            year=2025,
            family="Polo-Molina",
        ),
        _cand(
            rung=a.RUNG_SIBLING,
            title="MonoKAN: Certified Monotonic Kolmogorov-Arnold Network",
            year=2024,
            first_author_family="Polo-Molina",
        ),
    )
    assert record.verdict == a.ACCEPT
    assert record.year == "within-1"


def test_exact_match_accepts() -> None:
    record = a.evaluate_match(
        _entry(),
        _cand(title="Monotonic Networks", year=1997, first_author_family="Sill"),
    )
    assert record.verdict == a.ACCEPT
    assert (record.title, record.author, record.year) == ("exact", "exact", "exact")


def test_wide_year_gap_with_exact_title_quarantines() -> None:
    record = a.evaluate_match(
        _entry(),
        _cand(title="Monotonic Networks", year=2001, first_author_family="Sill"),
    )
    assert record.verdict == a.QUARANTINE
    assert record.year == "within-5"


def test_year_gap_beyond_the_window_refuses() -> None:
    record = a.evaluate_match(
        _entry(),
        _cand(title="Monotonic Networks", year=2010, first_author_family="Sill"),
    )
    assert record.verdict == a.REFUSE
    assert record.year == "mismatch"


def test_containment_title_within_one_year_quarantines() -> None:
    record = a.evaluate_match(
        _entry(),
        _cand(
            title="Monotonic Networks for Tabular Data",
            year=1998,
            first_author_family="Sill",
        ),
    )
    assert record.verdict == a.QUARANTINE
    assert record.title == "containment"


def test_containment_is_symmetric() -> None:
    record = a.evaluate_match(
        _entry(title="Monotonic Networks for Tabular Data"),
        _cand(title="Monotonic Networks", year=1997, first_author_family="Sill"),
    )
    assert record.title == "containment"
    assert record.verdict == a.QUARANTINE


def test_containment_with_a_wide_year_gap_refuses() -> None:
    record = a.evaluate_match(
        _entry(),
        _cand(
            title="Monotonic Networks for Tabular Data",
            year=2003,
            first_author_family="Sill",
        ),
    )
    assert record.verdict == a.REFUSE


def test_unrelated_title_refuses() -> None:
    record = a.evaluate_match(
        _entry(),
        _cand(title="Attention Is All You Need", year=1997, first_author_family="Sill"),
    )
    assert record.verdict == a.REFUSE
    assert record.title == "mismatch"


# --- honest degradation on thin metadata ------------------------------------


@pytest.mark.parametrize("field", ["title", "year", "family"])
def test_thin_registry_metadata_refuses_rather_than_guessing(field: str) -> None:
    record = a.evaluate_match(
        _entry(**{field: None}),  # type: ignore[arg-type]
        _cand(title="Monotonic Networks", year=1997, first_author_family="Sill"),
    )
    assert record.verdict == a.REFUSE
    assert record.reason is not None
    assert "insufficient" in record.reason


@pytest.mark.parametrize(
    "kw",
    [
        {"title": None, "year": 1997, "first_author_family": "Sill"},
        {"title": "Monotonic Networks", "year": None, "first_author_family": "Sill"},
        {"title": "Monotonic Networks", "year": 1997, "first_author_family": None},
    ],
)
def test_thin_candidate_metadata_refuses(kw: dict[str, Any]) -> None:
    record = a.evaluate_match(_entry(), _cand(**kw))
    assert record.verdict == a.REFUSE
    assert record.reason is not None
    assert "insufficient" in record.reason


# Not in the brief: fix-round-1 findings. A title or author that is *present*
# but blank (present as a string, normalizes/folds to "") is metadata, not
# absence, so the ``is None`` checks above let it through — and two blanks
# compared to each other score "exact", which can reach ACCEPT. The registry
# side cannot produce this today (``registry.py``'s ``_opt_str`` coerces blank
# strings to ``None``), but the gate must not depend on that other module's
# discipline: Task 9 feeds it arXiv/OpenAlex-parsed candidate metadata with no
# such guarantee.


def test_both_titles_blank_after_normalization_refuses() -> None:
    record = a.evaluate_match(
        _entry(title="!!!"),
        _cand(title="???", year=1997, first_author_family="Sill"),
    )
    assert record.verdict == a.REFUSE
    assert record.reason is not None
    assert "insufficient" in record.reason


def test_both_first_authors_blank_after_folding_refuses() -> None:
    record = a.evaluate_match(
        _entry(family=""),
        _cand(title="Monotonic Networks", year=1997, first_author_family=""),
    )
    assert record.verdict == a.REFUSE
    assert record.reason is not None
    assert "insufficient" in record.reason


def test_title_axis_treats_a_blank_side_as_mismatch_not_containment() -> None:
    """Direct unit test of the private axis, per its own docstring contract.

    ``evaluate_match`` never reaches ``_title_axis`` with a blank title —
    that is refused upstream as insufficient metadata (see the two tests
    above) — but ``_title_axis`` guards its own ``left_words and
    right_words`` invariant independently, so that guard needs its own
    oracle rather than relying on an upstream caller to make it unreachable.
    A blank side must never vacuously "contain" a real title.
    """
    assert a._title_axis("", "Monotonic Networks") == "mismatch"
    assert a._title_axis("Monotonic Networks", "") == "mismatch"


# --- shape ------------------------------------------------------------------


def test_identity_rungs_are_not_gated() -> None:
    assert a.RUNG_OA_BEST not in a.GATED_RUNGS
    assert a.RUNG_OA_LOCATIONS not in a.GATED_RUNGS
    assert a.RUNG_OA_LANDING not in a.GATED_RUNGS


def test_search_rungs_are_gated() -> None:
    assert (
        frozenset({a.RUNG_SIBLING, a.RUNG_ARXIV_SEARCH, a.RUNG_VENUE}) == a.GATED_RUNGS
    )


def test_match_record_as_json_is_serializable() -> None:
    record = a.MatchRecord(verdict=a.IDENTITY)
    assert record.as_json() == {
        "verdict": "identity",
        "title": None,
        "author": None,
        "year": None,
        "reason": None,
    }


# --- not in the brief: added to close gaps in the 100% coverage gate --------
#
# Both tests below assert against the module's *design* (its own docstrings/
# field contracts), not against whatever the implementation happened to
# return — per the task instructions on closing coverage gaps honestly.


def test_candidate_as_json_is_serializable() -> None:
    """``Candidate.as_json`` is public API but was never exercised by the brief.

    Its contract, from its own docstring, is "every field, verbatim, as a
    plain JSON-ready dict" — used for the audit trail.
    """
    candidate = a.Candidate(
        url="http://x/p.pdf",
        rung=a.RUNG_ARXIV_SEARCH,
        title="Monotonic Networks",
        year=1997,
        first_author_family="Sill",
        openalex="W123",
    )
    assert candidate.as_json() == {
        "url": "http://x/p.pdf",
        "rung": a.RUNG_ARXIV_SEARCH,
        "title": "Monotonic Networks",
        "year": 1997,
        "first_author_family": "Sill",
        "openalex": "W123",
    }


def test_title_that_normalizes_to_empty_refuses_as_insufficient() -> None:
    """A title of only punctuation normalizes to the empty string.

    ``normalize_title`` strips all punctuation, so a title like ``"!!!"``
    normalizes to ``""``. A blank title carries no information to match on —
    it is thin metadata, exactly like a missing one — so the gate must refuse
    it as insufficient before ever reaching the title axis, rather than
    scoring a (vacuous) "mismatch" or, worse, a vacuous "exact"/"containment"
    against another blank. (Fix-round-1: this test previously asserted
    ``title == "mismatch"``, which was itself the gap the reviewer found —
    two blanks used to compare as "exact".)
    """
    record = a.evaluate_match(
        _entry(title="!!!"),
        _cand(title="Monotonic Networks", year=1997, first_author_family="Sill"),
    )
    assert record.verdict == a.REFUSE
    assert record.title is None
    assert record.reason is not None
    assert "insufficient" in record.reason


FIXTURES = Path(__file__).parent / "fixtures" / "openalex"


def _work(name: str) -> dict[str, Any]:
    return cast(
        "dict[str, Any]",
        json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")),
    )


def _fetched(tmp_path: Path, body: bytes, media_type: str | None) -> FetchedBytes:
    target = tmp_path / "b"
    target.write_bytes(body)
    return FetchedBytes(path=target, media_type=media_type, size=len(body))


# --- PDF acceptance ---------------------------------------------------------


def test_pdf_content_type_is_accepted(tmp_path: Path) -> None:
    assert a.looks_like_pdf(_fetched(tmp_path, b"anything", "application/pdf"))


def test_lying_content_type_is_accepted_on_magic_bytes(tmp_path: Path) -> None:
    """Sill 1997's papers.nips.cc landing URL — served as text/html, actually a PDF.

    Rung 3's entire reason to exist: content-type lies, magic bytes do not.
    """
    assert a.looks_like_pdf(_fetched(tmp_path, b"%PDF-1.4\nstuff", "text/html"))


def test_html_body_with_html_content_type_is_rejected(tmp_path: Path) -> None:
    assert not a.looks_like_pdf(_fetched(tmp_path, b"<!doctype html>", "text/html"))


def test_missing_content_type_falls_back_to_magic_bytes(tmp_path: Path) -> None:
    assert a.looks_like_pdf(_fetched(tmp_path, b"%PDF-1.7", None))
    assert not a.looks_like_pdf(_fetched(tmp_path, b"nope", None))


def test_unreadable_body_is_rejected_not_an_error(tmp_path: Path) -> None:
    missing = FetchedBytes(path=tmp_path / "gone", media_type=None, size=0)
    assert a.looks_like_pdf(missing) is False


# --- rungs 1-3 --------------------------------------------------------------


def test_rung_1_takes_best_oa_location() -> None:
    work = _work("monokan_arxiv")
    cands = a.identity_candidates(work)
    assert cands[0].rung == a.RUNG_OA_BEST
    assert cands[0].url == work["best_oa_location"]["pdf_url"]


def test_rung_3_recovers_sill_from_a_pdf_serving_landing_page() -> None:
    """The case #97 wanted venue scrapers for. No venue knowledge needed."""
    work = _work("sill1997")
    assert (work.get("best_oa_location") or {}).get("pdf_url") is None
    assert work["open_access"]["oa_status"] == "closed"
    cands = a.identity_candidates(work)
    assert [c.rung for c in cands] == [a.RUNG_OA_LANDING]
    assert "papers.nips.cc" in cands[0].url


def test_identity_candidates_carry_the_works_own_metadata() -> None:
    cand = a.identity_candidates(_work("sill1997"))[0]
    assert cand.title == "Monotonic Networks"
    assert cand.year == 1997
    assert cand.first_author_family == "Sill"
    assert cand.openalex == "W2293093810"


def test_no_candidates_when_nothing_is_available() -> None:
    assert a.identity_candidates(_work("monokan_journal")) == []


def test_candidates_are_deduplicated_by_url() -> None:
    work = {
        "id": "https://openalex.org/W1",
        "display_name": "T",
        "publication_year": 2020,
        "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
        "best_oa_location": {"pdf_url": "http://x/p.pdf"},
        "locations": [
            {"pdf_url": "http://x/p.pdf"},
            {"pdf_url": "http://x/p.pdf"},
        ],
    }
    assert [c.url for c in a.identity_candidates(work)] == ["http://x/p.pdf"]


def test_landing_urls_only_returns_pdf_shaped_links() -> None:
    work = {
        "locations": [
            {"landing_page_url": "http://x/abs/1"},
            {"landing_page_url": "http://x/paper.pdf"},
            {"landing_page_url": None},
            {},
            "junk",
        ]
    }
    assert a.landing_urls(work) == ["http://x/paper.pdf"]


def test_family_name_is_the_last_token_of_a_display_name() -> None:
    work = {
        "id": "https://openalex.org/W1",
        "display_name": "T",
        "publication_year": 2020,
        "authorships": [{"author": {"display_name": "Alberto Polo-Molina"}}],
        "best_oa_location": {"pdf_url": "http://x/p.pdf"},
    }
    assert a.identity_candidates(work)[0].first_author_family == "Polo-Molina"


def test_missing_authorships_yields_no_family_name() -> None:
    work = {
        "id": "https://openalex.org/W1",
        "display_name": "T",
        "publication_year": 2020,
        "best_oa_location": {"pdf_url": "http://x/p.pdf"},
    }
    assert a.identity_candidates(work)[0].first_author_family is None


def test_malformed_locations_are_skipped_not_fatal() -> None:
    work = {
        "id": "https://openalex.org/W1",
        "display_name": "T",
        "publication_year": 2020,
        "locations": ["junk", {"pdf_url": 5}, {"pdf_url": "http://x/ok.pdf"}],
    }
    assert [c.url for c in a.identity_candidates(work)] == ["http://x/ok.pdf"]


# --- coverage: not in the brief ----------------------------------------------
#
# Task 8 brief's test list left four branches of _short_id / _first_family_
# from_work unexercised (a work with no "id", and three malformed-authorship
# shapes). These close that gap with real oracles tied to the design ("degrade
# to None rather than raise"), not to the current implementation's behavior.


def test_work_with_no_id_yields_no_openalex_id() -> None:
    work = {
        "display_name": "T",
        "publication_year": 2020,
        "best_oa_location": {"pdf_url": "http://x/p.pdf"},
    }
    assert a.identity_candidates(work)[0].openalex is None


def test_non_dict_first_authorship_yields_no_family_name() -> None:
    work = {
        "id": "https://openalex.org/W1",
        "display_name": "T",
        "publication_year": 2020,
        "authorships": ["not-a-dict"],
        "best_oa_location": {"pdf_url": "http://x/p.pdf"},
    }
    assert a.identity_candidates(work)[0].first_author_family is None


def test_non_dict_author_yields_no_family_name() -> None:
    work = {
        "id": "https://openalex.org/W1",
        "display_name": "T",
        "publication_year": 2020,
        "authorships": [{"author": "not-a-dict"}],
        "best_oa_location": {"pdf_url": "http://x/p.pdf"},
    }
    assert a.identity_candidates(work)[0].first_author_family is None


def test_blank_display_name_yields_no_family_name() -> None:
    work = {
        "id": "https://openalex.org/W1",
        "display_name": "T",
        "publication_year": 2020,
        "authorships": [{"author": {"display_name": "   "}}],
        "best_oa_location": {"pdf_url": "http://x/p.pdf"},
    }
    assert a.identity_candidates(work)[0].first_author_family is None


# --- rungs 4-6 (search-derived, task 9) -------------------------------------


class FakeClient:
    """A stand-in for HttpClient that serves canned JSON/text by URL substring.

    Not from the brief: routes below are keyed ``"/works"`` rather than the
    brief's ``"/works?"`` -- ``sibling_candidates`` calls
    ``client.get_json(f"{OPENALEX}/works", {...})`` with params passed
    separately (never embedded into the URL string as a literal ``?``), so the
    brief's fragment would never match and every rung-4 test would raise
    "unrouted URL" rather than exercising the code.
    """

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict[str, str] | None]] = []
        self.s2_key: str | None = None
        self.max_retries = 4

    def get_json(
        self, url: str, params: dict[str, str] | None = None, *, s2: bool = False
    ) -> Any:
        self.calls.append((url, params))
        for fragment, payload in self.routes.items():
            if fragment in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError(f"unrouted URL: {url}")

    # Not from the brief (Correction 1): the brief's FakeClient defines only
    # get_json, so arxiv_candidates (which calls client.get_text) was never
    # actually exercised by the brief's rung-5 tests -- only parse_arxiv_feed
    # was. Routes by the same URL-substring convention as get_json.
    def get_text(
        self,
        url: str,
        params: dict[str, str] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> str:
        self.calls.append((url, params))
        for fragment, payload in self.routes.items():
            if fragment in url:
                if isinstance(payload, Exception):
                    raise payload
                return cast("str", payload)
        raise AssertionError(f"unrouted URL: {url}")


def test_rung_4_finds_the_monokan_sibling() -> None:
    """The registry entry is the closed journal work; the PDF is on the sibling."""
    journal = _work("monokan_journal")
    arxiv = _work("monokan_arxiv")
    client = FakeClient({"/works": {"results": [journal, arxiv]}})
    entry = _entry(
        citekey="monokan",
        title=journal["display_name"],
        year=journal["publication_year"],
        family="Polo-Molina",
    )
    cands = a.sibling_candidates(entry, journal, client=client)
    assert cands
    assert all(c.rung == a.RUNG_SIBLING for c in cands)
    # Not from the brief: the fixture's arXiv PDF URLs have no literal ".pdf"
    # suffix (e.g. "https://arxiv.org/pdf/2409.11078"), so the brief's own
    # ".pdf" in c.url assertion could never pass against this fixture.
    assert any("arxiv.org/pdf" in c.url for c in cands)


def test_rung_4_excludes_the_anchor_itself() -> None:
    work = _work("monokan_arxiv")
    client = FakeClient({"/works": {"results": [work]}})
    entry = _entry(citekey="k", title=work["display_name"], year=2024, family="X")
    assert a.sibling_candidates(entry, work, client=client) == []


def test_rung_4_skips_works_with_a_different_normalized_title() -> None:
    other = dict(_work("monokan_arxiv"), id="https://openalex.org/W999")
    other["display_name"] = "Something Else Entirely"
    client = FakeClient({"/works": {"results": [other]}})
    entry = _entry(
        citekey="k", title="MonoKAN: Certified monotonic", year=2025, family="X"
    )
    assert a.sibling_candidates(entry, _work("monokan_journal"), client=client) == []


def test_rung_4_without_a_registry_title_returns_nothing() -> None:
    client = FakeClient({})
    assert a.sibling_candidates(_entry(title=None), {}, client=client) == []


def test_rung_4_tolerates_a_non_dict_page() -> None:
    client = FakeClient({"/works": ["junk"]})
    assert a.sibling_candidates(_entry(), _work("sill1997"), client=client) == []


# Not from the brief: closes a coverage gap the brief's own test suite left --
# a "results" entry that is not itself a dict (a malformed hit, distinct from
# a malformed *page*, which test_rung_4_tolerates_a_non_dict_page covers).
def test_rung_4_skips_a_non_dict_result_entry() -> None:
    client = FakeClient({"/works": {"results": ["junk"]}})
    assert a.sibling_candidates(_entry(), _work("sill1997"), client=client) == []


# Not from the brief (Correction 2): the brief's rung-4 pre-filter required
# normalized-title *equality*, which is stricter than the gate it feeds -- a
# genuine sibling whose journal version added a subtitle would be discarded
# before evaluate_match ever saw it. Spec amended in d325055; see
# docs/superpowers/specs/2026-08-27-literature-asset-acquisition-design.md §5.1.
# This proves the widened pre-filter (same exact-or-word-prefix-containment
# relation _title_axis implements) now *proposes* such a sibling, and that it
# is the gate -- not the pre-filter -- that decides the verdict.
def test_rung_4_proposes_a_subtitle_extended_sibling_and_the_gate_decides() -> None:
    """A pre-filter must never preempt the adjudicator (spec §5.1, amended)."""
    journal = _work("monokan_journal")
    arxiv = _work("monokan_arxiv")
    client = FakeClient({"/works": {"results": [journal, arxiv]}})
    # The entry's title is the short form; the arXiv sibling's is the same paper
    # with a subtitle. Strict equality would have dropped this sibling entirely.
    entry = _entry(citekey="monokan", title="MonoKAN", year=2024, family="Polo-Molina")
    cands = a.sibling_candidates(entry, journal, client=client)
    assert cands  # proposed despite not being normalized-equal to the entry title
    assert any("arxiv.org/pdf" in c.url for c in cands)
    for candidate in cands:
        record = a.evaluate_match(entry, candidate)
        assert record.title == "containment"
        assert record.verdict == a.QUARANTINE  # author+year decide, not the filter


def test_rung_5_builds_candidates_from_the_arxiv_atom_feed() -> None:
    feed = (
        '<?xml version="1.0"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        "<entry>"
        "<id>http://arxiv.org/abs/2306.01147v1</id>"
        "<title>Smooth Min-Max Monotonic Networks</title>"
        "<published>2023-06-01T00:00:00Z</published>"
        "<author><name>Christian Igel</name></author>"
        "</entry>"
        "</feed>"
    )
    cands = a.parse_arxiv_feed(feed)
    assert len(cands) == 1
    assert cands[0].rung == a.RUNG_ARXIV_SEARCH
    assert cands[0].url == "https://arxiv.org/pdf/2306.01147"
    assert cands[0].title == "Smooth Min-Max Monotonic Networks"
    assert cands[0].year == 2023
    assert cands[0].first_author_family == "Igel"


def test_rung_5_feed_entries_missing_fields_are_skipped() -> None:
    feed = (
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        "<entry><title>No id</title></entry>"
        "<entry><id>http://arxiv.org/abs/1234.5678</id></entry>"
        "</feed>"
    )
    assert a.parse_arxiv_feed(feed) == []


def test_rung_5_malformed_xml_yields_no_candidates_not_an_error() -> None:
    assert a.parse_arxiv_feed("<not xml") == []


# Not from the brief (Correction 1): direct tests for arxiv_candidates itself,
# since the brief's FakeClient had no get_text and so never called it.
_ARXIV_FEED = (
    '<feed xmlns="http://www.w3.org/2005/Atom">'
    "<entry>"
    "<id>http://arxiv.org/abs/2306.01147v1</id>"
    "<title>Smooth Min-Max Monotonic Networks</title>"
    "<published>2023-06-01T00:00:00Z</published>"
    "<author><name>Christian Igel</name></author>"
    "</entry>"
    "</feed>"
)


def test_rung_5_arxiv_candidates_builds_query_from_title_and_author() -> None:
    client = FakeClient({"export.arxiv.org": _ARXIV_FEED})
    entry = _entry(title="Monotonic Networks", family="Sill")
    a.arxiv_candidates(entry, client=client)
    url, params = client.calls[0]
    assert url == a.ARXIV_API
    assert params is not None
    assert params["search_query"] == 'ti:"Monotonic Networks" AND au:"Sill"'


def test_rung_5_arxiv_candidates_returns_parsed_candidates() -> None:
    client = FakeClient({"export.arxiv.org": _ARXIV_FEED})
    entry = _entry(title="Monotonic Networks", family="Sill")
    cands = a.arxiv_candidates(entry, client=client)
    assert len(cands) == 1
    assert cands[0].rung == a.RUNG_ARXIV_SEARCH
    assert cands[0].first_author_family == "Igel"


def test_rung_5_arxiv_candidates_omits_author_clause_when_entry_has_none() -> None:
    client = FakeClient({"export.arxiv.org": _ARXIV_FEED})
    entry = _entry(title="Monotonic Networks", family=None)
    a.arxiv_candidates(entry, client=client)
    _url, params = client.calls[0]
    assert params is not None
    assert params["search_query"] == 'ti:"Monotonic Networks"'


def test_rung_5_arxiv_candidates_returns_nothing_when_entry_has_no_title() -> None:
    client = FakeClient({})
    assert a.arxiv_candidates(_entry(title=None), client=client) == []
    assert client.calls == []  # no wasted request when there is nothing to search


def test_rung_6_expands_configured_templates() -> None:
    # Not from the brief: the sill1997 fixture's primary_location carries no
    # `source` (venue) name, so the brief's version of this test could never
    # have matched. Add one inline rather than editing the shared fixture,
    # which other tests (rungs 1-3, identity metadata) also depend on as-is.
    work = dict(_work("sill1997"))
    work["primary_location"] = dict(
        work["primary_location"],
        source={"display_name": "Advances in Neural Information Processing Systems"},
    )
    resolvers = [
        {
            "match": "Neural Information Processing",
            "url_template": "http://v/{openalex}.pdf",
        }
    ]
    cands = a.venue_candidates(_entry(), work, resolvers)
    assert [c.url for c in cands] == ["http://v/W2293093810.pdf"]
    assert cands[0].rung == a.RUNG_VENUE


def test_rung_6_ships_empty_so_nothing_matches_by_default() -> None:
    assert a.venue_candidates(_entry(), _work("sill1997"), []) == []


def test_rung_6_skips_a_non_matching_venue() -> None:
    resolvers = [{"match": "ICLR", "url_template": "http://v/{openalex}.pdf"}]
    assert a.venue_candidates(_entry(), _work("sill1997"), resolvers) == []


def test_rung_6_skips_a_malformed_resolver() -> None:
    resolvers: list[Any] = [
        "junk",
        {"match": "Neural"},
        {"url_template": "http://v/x.pdf"},
        {"match": "(", "url_template": "http://v/x.pdf"},
    ]
    assert a.venue_candidates(_entry(), _work("sill1997"), resolvers) == []
