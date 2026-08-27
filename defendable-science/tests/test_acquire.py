"""Tests for the literature acquisition ladder and its match gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from defendable_science.core.download import DownloadError, FetchedBytes
from defendable_science.core.fixity import RetrievalError
from defendable_science.core.http import HttpError, RateLimitError
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
        # Not from the brief: task 10 added `license` to Candidate so a rung-4
        # sibling's bytes record the *sibling's* license, not the anchor's.
        "license": None,
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
    work = _work("sill1997")
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


# Not from the brief: fix round 1 restored the real `source.display_name` to
# the sill1997 fixture (see report), so no remaining test exercised a work
# with *no* venue at all. monokan_arxiv's primary_location has no `source`.
def test_rung_6_treats_a_missing_venue_as_no_match() -> None:
    work = _work("monokan_arxiv")
    resolvers = [{"match": "arxiv", "url_template": "http://v/x.pdf"}]
    assert a.venue_candidates(_entry(), work, resolvers) == []


def test_rung_6_skips_a_malformed_resolver() -> None:
    resolvers: list[Any] = [
        "junk",
        {"match": "Neural"},
        {"url_template": "http://v/x.pdf"},
        {"match": "(", "url_template": "http://v/x.pdf"},
        # Not from the brief: a resolver that matches the venue but whose
        # template can't be formatted must degrade, not crash (failure
        # honesty -- venue_resolvers is hand-edited consumer config).
        {"match": "Neural", "url_template": "http://v/{unknown}.pdf"},  # KeyError
        {"match": "Neural", "url_template": "http://v/{.pdf"},  # ValueError
        {"match": "Neural", "url_template": "http://v/{0}.pdf"},  # IndexError
        {"match": "Neural", "url_template": "http://v/{openalex!z}.pdf"},  # ValueError
    ]
    assert a.venue_candidates(_entry(), _work("sill1997"), resolvers) == []


# --- task 10: single-entry acquisition --------------------------------------
#
# Fixtures below build OpenAlex works and registry files inline rather than
# reaching for the three captured payloads, because the ladder's branches need
# shapes the real captures do not have (two PDF URLs, a permissive license, a
# same-title sibling by a different author). The captured payloads still drive
# the two named regression cases.


def _ctx(tmp_path: Path, client: Any, fetcher: Any, **kw: Any) -> a.Context:
    base: dict[str, Any] = {
        "registry_path": tmp_path / "references.json",
        "triage_path": tmp_path / "triage.yml",
        "cache_dir": tmp_path / "cache",
        "mirror": None,
        "client": client,
        "fetcher": fetcher,
        "max_bytes": 1 << 20,
        "resolvers": [],
        "today": "2026-08-27",
    }
    base.update(kw)
    return a.Context(**base)


PDF = b"%PDF-1.4 body"
PDF_SHA = hashlib.sha256(PDF).hexdigest()
OTHER_PDF = b"%PDF-1.4 a different body"
OTHER_SHA = hashlib.sha256(OTHER_PDF).hexdigest()


class FakeFetcher:
    """A ``BytesFetcher`` that serves canned bodies (or raises) per URL."""

    def __init__(
        self,
        bodies: dict[str, bytes | Exception] | None = None,
        default: bytes | Exception | None = PDF,
    ) -> None:
        self.bodies = bodies or {}
        self.default = default
        self.calls: list[str] = []

    def __call__(self, url: str, dest: Path, max_bytes: int) -> FetchedBytes:
        self.calls.append(url)
        payload = self.bodies.get(url, self.default)
        if isinstance(payload, Exception):
            raise payload
        if payload is None:
            raise DownloadError(f"{url}: nothing here")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
        media = "application/pdf" if payload.startswith(b"%PDF-") else "text/html"
        return FetchedBytes(path=dest, media_type=media, size=len(payload))


class NeverFetcher:
    """A fetcher that fails the test if the ladder ever downloads anything."""

    def __call__(self, url: str, dest: Path, max_bytes: int) -> FetchedBytes:
        raise AssertionError(f"the fetcher must not be called, but got {url}")


class FakeMirror:
    """A stand-in for ``Mirror`` that never shells out to rclone."""

    def __init__(
        self, body: bytes | None = None, put_error: Exception | None = None
    ) -> None:
        self.body = body
        self.put_error = put_error
        self.puts: list[tuple[str, str]] = []
        self.remote = "papers"
        self.base_path = "literature"

    def put(self, local: str | Path, sha256: str) -> None:
        if self.put_error is not None:
            raise self.put_error
        self.puts.append((str(local), sha256))

    def get(self, sha256: str, dst: str | Path) -> bool:
        if self.body is None:
            return False
        target = Path(dst)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.body)
        return True

    def check(self, sha256: str) -> bool:
        return self.body is not None


def _oa(
    wid: str = "W1",
    title: str = "Monotonic Networks",
    year: int = 1997,
    family: str = "Sill",
    pdf: str | None = None,
    pdfs: list[str] | None = None,
    landing: str | None = None,
    lic: Any = None,
    is_oa: Any = None,
    venue: str | None = "Neural Information Processing Systems",
) -> dict[str, Any]:
    """Build a minimal OpenAlex work with exactly the shape a test needs."""
    urls = pdfs if pdfs is not None else [pdf]
    locations: list[dict[str, Any]] = [
        {"landing_page_url": landing, "pdf_url": url, "license": lic} for url in urls
    ]
    source = {"display_name": venue} if venue is not None else None
    return {
        "id": f"https://openalex.org/{wid}",
        "display_name": title,
        "publication_year": year,
        "authorships": [{"author": {"display_name": f"Joseph {family}"}}],
        "open_access": {"is_oa": is_oa},
        "best_oa_location": (
            {"pdf_url": urls[0], "license": lic} if urls[0] is not None else None
        ),
        "locations": locations,
        "primary_location": {"source": source},
        "ids": {},
        "doi": None,
    }


def _registry(
    tmp_path: Path,
    citekey: str = "sill1997monotonic",
    title: str | None = "Monotonic Networks",
    year: int | None = 1997,
    family: str | None = "Sill",
    doi: str | None = "10.1234/abc",
    spine: dict[str, Any] | None = None,
) -> tuple[Path, reg.Entry]:
    """Write a one-entry ``references.json`` and return it with its decoded entry."""
    item: dict[str, Any] = {"id": citekey, "type": "paper-conference"}
    if title is not None:
        item["title"] = title
    if year is not None:
        item["issued"] = {"date-parts": [[year]]}
    if family is not None:
        item["author"] = [{"family": family, "given": "Joseph"}]
    if doi is not None:
        item["DOI"] = doi
    if spine is not None:
        item["custom"] = {reg.NAMESPACE: spine}
    path = tmp_path / "references.json"
    path.write_text(json.dumps([item], indent=2) + "\n", encoding="utf-8")
    return path, reg.load_registry(path).entries[0]


def _spine(sha: str = PDF_SHA, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema": reg.SCHEMA,
        "pid": None,
        "files": [{"path": f"sha256/{sha}", "sha256": f"sha256:{sha}"}],
        "license": {"id": None, "observed": None, "source": None},
        "redistributable": False,
    }
    base.update(kw)
    return base


def _seed_blob(tmp_path: Path, body: bytes = PDF) -> Path:
    blob = tmp_path / "cache" / "sha256" / hashlib.sha256(body).hexdigest()
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(body)
    return blob


def _asset(path: Path) -> reg.Asset:
    asset = reg.load_registry(path).entries[0].asset
    assert asset is not None
    return asset


# --- the license allowlist --------------------------------------------------


@pytest.mark.parametrize(
    ("spdx", "expected"),
    [
        ("cc-by", True),
        ("cc-by-4.0", True),
        ("cc0-1.0", True),
        ("cc-by-sa", True),
        ("mit", True),
        ("apache-2.0", True),
        ("CC-BY-4.0", True),
        (None, False),
        ("", False),
        ("all-rights-reserved", False),
        # Non-commercial is not a redistribution grant for an in-repo copy of a
        # paper. Getting this backwards is a licence-compliance error.
        ("cc-by-nc", False),
        ("cc-by-nc-nd", False),
        ("cc-by-nd", False),
    ],
)
def test_is_permissive(spdx: str | None, expected: bool) -> None:
    assert a.is_permissive(spdx) is expected


@pytest.mark.parametrize(
    ("work", "expected"),
    [
        ({"best_oa_location": {"license": "cc-by"}}, "cc-by"),
        ({"primary_location": {"license": "CC-BY-4.0 "}}, "cc-by-4.0"),
        ({"locations": [{"license": "mit"}]}, "mit"),
        # everything unusable -> no observation at all
        ({}, None),
        ({"best_oa_location": None, "locations": "not-a-list"}, None),
        ({"locations": ["junk", {"license": None}, {"license": "  "}]}, None),
    ],
)
def test_license_from_work(work: dict[str, Any], expected: str | None) -> None:
    assert a.license_from_work(work).id == expected


def test_license_from_work_records_the_raw_string_and_its_source() -> None:
    observed = a.license_from_work(
        {"best_oa_location": {"license": "All-Rights-Reserved"}}
    )
    assert observed.observed == "All-Rights-Reserved"
    assert observed.id == "all-rights-reserved"
    assert observed.source == a.LICENSE_SOURCE


def test_a_blank_observed_license_is_no_license() -> None:
    """Private helper: a whitespace-only string is not a license observation."""
    assert a._license_from_observed("   ") == reg.License()


# --- resolution before acquisition (spec §4) --------------------------------


def test_already_recorded_sha_resolves_from_cache_without_network(
    tmp_path: Path,
) -> None:
    """The load-bearing no-network property of a recorded checksum."""
    path, entry = _registry(tmp_path, spine=_spine())
    before = path.read_bytes()
    _seed_blob(tmp_path)
    client = FakeClient({})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, NeverFetcher()))
    assert outcome.bucket == a.BUCKET_CACHED
    assert outcome.sha256 == PDF_SHA
    assert client.calls == []
    assert path.read_bytes() == before


def test_already_recorded_sha_falls_through_to_mirror(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path, spine=_spine())
    mirror = FakeMirror(body=PDF)
    outcome = a.acquire_one(
        entry, _ctx(tmp_path, FakeClient({}), NeverFetcher(), mirror=mirror)
    )
    assert outcome.bucket == a.BUCKET_CACHED
    assert outcome.sha256 == PDF_SHA


def test_a_mirror_that_does_not_hold_the_key_is_manual(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path, spine=_spine())
    outcome = a.acquire_one(
        entry, _ctx(tmp_path, FakeClient({}), NeverFetcher(), mirror=FakeMirror())
    )
    assert outcome.bucket == a.BUCKET_MANUAL


def test_mirror_bytes_that_do_not_verify_are_treated_as_absent(
    tmp_path: Path,
) -> None:
    """A corrupt copy is 'absent', per the substrate rule — never bound anyway."""
    _path, entry = _registry(tmp_path, spine=_spine())
    outcome = a.acquire_one(
        entry,
        _ctx(
            tmp_path, FakeClient({}), NeverFetcher(), mirror=FakeMirror(body=b"corrupt")
        ),
    )
    assert outcome.bucket == a.BUCKET_MANUAL
    assert outcome.reason is not None
    assert "the mirror copy is corrupt too" in outcome.reason
    # The bad bytes must not be left at the content-addressed path for a later
    # run to re-read.
    assert not (tmp_path / "cache" / "sha256" / PDF_SHA).exists()


def test_recorded_sha_with_no_bytes_anywhere_is_manual(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path, spine=_spine())
    outcome = a.acquire_one(entry, _ctx(tmp_path, FakeClient({}), NeverFetcher()))
    assert outcome.bucket == a.BUCKET_MANUAL
    assert outcome.reason is not None
    assert PDF_SHA in outcome.reason
    assert "not in the local cache, and not in the mirror either" in outcome.reason


def test_a_corrupt_cache_blob_falls_through_to_the_mirror(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path, spine=_spine())
    blob = tmp_path / "cache" / "sha256" / PDF_SHA
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(b"corrupt")
    outcome = a.acquire_one(
        entry,
        _ctx(tmp_path, FakeClient({}), NeverFetcher(), mirror=FakeMirror(body=PDF)),
    )
    assert outcome.bucket == a.BUCKET_CACHED


def test_a_recorded_spine_with_no_files_still_runs_the_ladder(tmp_path: Path) -> None:
    """``pid`` recorded, bytes never acquired — resolution has nothing to resolve."""
    path, entry = _registry(
        tmp_path, spine=_spine(files=[], pid="openalex:W1"), doi=None
    )
    client = FakeClient({"/works/": _oa(pdf="http://x/p.pdf")})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher()))
    assert outcome.bucket == a.BUCKET_FETCHED
    assert _asset(path).files[0].sha256 == f"sha256:{PDF_SHA}"
    assert client.calls[0][0].endswith("/works/W1")


def test_a_non_openalex_pid_is_resolved_as_written(tmp_path: Path) -> None:
    _path, entry = _registry(
        tmp_path, spine=_spine(files=[], pid="doi:10.1234/abc"), doi=None
    )
    client = FakeClient({"/works/": _oa(pdf="http://x/p.pdf")})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher()))
    assert outcome.bucket == a.BUCKET_FETCHED
    assert client.calls[0][0].endswith("/works/doi:10.1234/abc")


# --- the ladder -------------------------------------------------------------


def test_identity_rung_fetches_and_records(tmp_path: Path) -> None:
    """Sill 1997 — closed in OpenAlex, but its landing page *is* the PDF."""
    path, entry = _registry(tmp_path)
    client = FakeClient({"/works/": _work("sill1997")})
    fetcher = FakeFetcher()
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, fetcher))
    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.rung == a.RUNG_OA_LANDING
    assert outcome.sha256 == PDF_SHA
    assert outcome.match is not None
    assert outcome.match["verdict"] == a.IDENTITY
    asset = _asset(path)
    assert asset.files[0].path == f"sha256/{PDF_SHA}"
    assert asset.files[0].sha256 == f"sha256:{PDF_SHA}"
    assert asset.pid == "openalex:W2293093810"
    assert asset.acquisition is not None
    assert asset.acquisition.rung == a.RUNG_OA_LANDING
    assert asset.acquisition.fetched == "2026-08-27"
    assert (tmp_path / "cache" / "sha256" / PDF_SHA).read_bytes() == PDF


def test_files_path_is_always_a_blob_path_never_a_repo_path(tmp_path: Path) -> None:
    """Spec §6 — ``fetch`` never writes bytes into the consumer's repository."""
    path, entry = _registry(tmp_path)
    client = FakeClient({"/works/": _oa(pdf="http://x/p.pdf", lic="cc-by")})
    a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher()))
    assert _asset(path).files[0].path.startswith("sha256/")
    assert not (tmp_path / "sill1997monotonic.pdf").exists()


def test_non_pdf_bytes_are_rejected_and_the_ladder_continues(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path)
    work = _oa(pdfs=["http://x/one.pdf", "http://x/two.pdf"])
    client = FakeClient({"/works/": work})
    fetcher = FakeFetcher({"http://x/one.pdf": b"<html>not a pdf</html>"})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, fetcher))
    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.rung == a.RUNG_OA_LOCATIONS
    assert outcome.url == "http://x/two.pdf"
    assert fetcher.calls == ["http://x/one.pdf", "http://x/two.pdf"]


def test_download_error_on_one_rung_does_not_end_the_ladder(tmp_path: Path) -> None:
    """A dead link is about *this URL*, never a verdict about the paper."""
    _path, entry = _registry(tmp_path)
    work = _oa(pdfs=["http://x/one.pdf", "http://x/two.pdf", "http://x/three.pdf"])
    client = FakeClient({"/works/": work})
    fetcher = FakeFetcher(
        {
            "http://x/one.pdf": DownloadError("http://x/one.pdf: 404"),
            "http://x/two.pdf": DownloadError("http://x/two.pdf: 403"),
        }
    )
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, fetcher))
    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.url == "http://x/three.pdf"
    assert fetcher.calls == [
        "http://x/one.pdf",
        "http://x/two.pdf",
        "http://x/three.pdf",
    ]


def test_all_rungs_exhausted_is_manual_with_landing_urls(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path)
    anchor = _oa(pdf="http://x/dead.pdf", landing="http://x/abstract")
    sibling = _oa(wid="W2", family="Igel", pdf="http://x/sib.pdf")
    client = FakeClient(
        {
            "/works/": anchor,
            "/works": {"results": [sibling]},
            "export.arxiv.org": "<feed/>",
        }
    )
    fetcher = FakeFetcher(default=DownloadError("http://x/dead.pdf: 404"))
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, fetcher))
    assert outcome.bucket == a.BUCKET_MANUAL
    assert outcome.landing_urls == ["http://x/abstract"]
    assert outcome.tried == [a.RUNG_OA_BEST, a.RUNG_SIBLING]


def test_a_ladder_with_no_candidates_at_all_is_manual(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path)
    anchor = _oa(pdf=None, landing="http://x/abstract")
    client = FakeClient(
        {
            "/works/": anchor,
            "/works": {"results": []},
            "export.arxiv.org": "<feed/>",
        }
    )
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, NeverFetcher()))
    assert outcome.bucket == a.BUCKET_MANUAL
    assert outcome.tried == []
    assert outcome.match is None
    assert outcome.landing_urls == ["http://x/abstract"]


# --- the gate, in the ladder ------------------------------------------------


def test_gated_quarantine_lands_bytes_and_writes_nothing(tmp_path: Path) -> None:
    path, entry = _registry(tmp_path)
    before = path.read_bytes()
    anchor = _oa(pdf=None, landing="http://x/abstract")
    sibling = _oa(wid="W2", year=2002, pdf="http://x/sib.pdf")
    client = FakeClient({"/works/": anchor, "/works": {"results": [sibling]}})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher()))
    assert outcome.bucket == a.BUCKET_QUARANTINED
    assert outcome.sha256 == PDF_SHA
    assert outcome.match is not None
    assert outcome.match["verdict"] == a.QUARANTINE
    directory = tmp_path / "cache" / "quarantine" / "sill1997monotonic"
    assert (directory / f"{PDF_SHA}.pdf").read_bytes() == PDF
    parked = json.loads((directory / f"{PDF_SHA}.json").read_text(encoding="utf-8"))
    assert parked["url"] == "http://x/sib.pdf"
    assert parked["rung"] == a.RUNG_SIBLING
    assert parked["match"]["verdict"] == a.QUARANTINE
    assert parked["candidate"]["openalex"] == "W2"
    assert path.read_bytes() == before


def test_gated_refusal_is_manual_with_the_axes_recorded(tmp_path: Path) -> None:
    """The Sill-1997-vs-Igel-2023 shape, walked through the whole ladder."""
    path, entry = _registry(tmp_path)
    before = path.read_bytes()
    anchor = _oa(pdf=None, landing="http://x/abstract")
    sibling = _oa(wid="W2", family="Igel", pdf="http://x/sib.pdf")
    client = FakeClient(
        {
            "/works/": anchor,
            "/works": {"results": [sibling]},
            "export.arxiv.org": _ARXIV_FEED,
        }
    )
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, NeverFetcher()))
    assert outcome.bucket == a.BUCKET_MANUAL
    assert outcome.match is not None
    assert outcome.match["author"] == "mismatch"
    assert outcome.candidate is not None
    assert outcome.candidate["openalex"] == "W2"
    assert outcome.tried == [a.RUNG_SIBLING, a.RUNG_ARXIV_SEARCH]
    assert path.read_bytes() == before


def test_a_venue_resolver_candidate_still_passes_the_gate(tmp_path: Path) -> None:
    """Rung 6 is gated like any other search rung; a match binds the bytes."""
    _path, entry = _registry(tmp_path)
    anchor = _oa(pdf=None, landing="http://x/abstract")
    client = FakeClient(
        {
            "/works/": anchor,
            "/works": {"results": []},
            "export.arxiv.org": "<feed/>",
        }
    )
    ctx = _ctx(
        tmp_path,
        client,
        FakeFetcher(),
        resolvers=[
            {"match": "Neural", "url_template": "http://v/{openalex}.pdf"},
        ],
    )
    outcome = a.acquire_one(entry, ctx)
    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.rung == a.RUNG_VENUE
    assert outcome.match is not None
    assert outcome.match["verdict"] == a.ACCEPT


# --- refetch and drift ------------------------------------------------------


def test_refetch_yielding_different_bytes_refuses_and_leaves_the_registry_alone(
    tmp_path: Path,
) -> None:
    path, entry = _registry(tmp_path, spine=_spine(sha=OTHER_SHA))
    before = path.read_bytes()
    client = FakeClient({"/works/": _oa(pdf="http://x/p.pdf")})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher()), refetch=True)
    assert outcome.bucket == a.BUCKET_ERROR
    assert outcome.reason is not None
    assert "drift" in outcome.reason
    assert OTHER_SHA in outcome.reason
    assert PDF_SHA in outcome.reason
    assert path.read_bytes() == before


def test_refetch_yielding_identical_bytes_is_cached(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path, spine=_spine())
    client = FakeClient({"/works/": _oa(pdf="http://x/p.pdf")})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher()), refetch=True)
    assert outcome.bucket == a.BUCKET_CACHED
    assert outcome.sha256 == PDF_SHA
    assert outcome.rung == a.RUNG_OA_BEST
    assert (tmp_path / "cache" / "sha256" / PDF_SHA).read_bytes() == PDF


# --- the mirror -------------------------------------------------------------


def test_mirror_is_populated_on_first_acquisition(tmp_path: Path) -> None:
    path, entry = _registry(tmp_path)
    mirror = FakeMirror()
    client = FakeClient({"/works/": _oa(pdf="http://x/p.pdf")})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher(), mirror=mirror))
    assert outcome.bucket == a.BUCKET_FETCHED
    assert mirror.puts == [(str(tmp_path / "cache" / "sha256" / PDF_SHA), PDF_SHA)]
    recorded = _asset(path).mirror
    assert recorded is not None
    assert (recorded.remote, recorded.key) == ("papers", f"literature/sha256/{PDF_SHA}")


def test_a_failed_mirror_write_does_not_discard_the_acquisition(
    tmp_path: Path,
) -> None:
    """The bytes are hashed and cached; calling that an error would be a lie."""
    path, entry = _registry(tmp_path)
    mirror = FakeMirror(put_error=RetrievalError("rclone copyto to mirror failed"))
    client = FakeClient({"/works/": _oa(pdf="http://x/p.pdf")})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher(), mirror=mirror))
    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.reason is not None
    assert "mirror write failed" in outcome.reason
    assert _asset(path).mirror is None


# --- failure honesty --------------------------------------------------------


def test_rate_limit_propagates_rather_than_becoming_manual(tmp_path: Path) -> None:
    """The failure-honesty test.

    A throttle is not information about this paper. Bucketing it as ``manual``
    would tell a human to go download by hand what the tool never asked for.
    """
    _path, entry = _registry(tmp_path)
    client = FakeClient({"/works/": RateLimitError("429 from OpenAlex")})
    with pytest.raises(RateLimitError):
        a.acquire_one(entry, _ctx(tmp_path, client, NeverFetcher()))


def test_a_transport_error_on_the_work_lookup_propagates(tmp_path: Path) -> None:
    """Nothing here converts a 5xx into a statement about the paper."""
    _path, entry = _registry(tmp_path)
    client = FakeClient(
        {"/works/doi:": _oa(pdf="http://x/p.pdf"), "/works/W1": HttpError("502")}
    )
    with pytest.raises(HttpError):
        a.acquire_one(entry, _ctx(tmp_path, client, NeverFetcher()))


def test_a_transport_error_during_resolution_is_an_error_row_not_manual(
    tmp_path: Path,
) -> None:
    """``graph.resolve`` folds a non-throttle ``HttpError`` into a miss.

    Not from the brief, which says every ``HttpError`` propagates. That is not
    true of the *first* call, because ``graph.resolve`` has caught ``HttpError``
    since defendable-science#1 and returns ``{resolved: False, reason}``. The
    property the failure-honesty rule actually needs still holds — it lands in
    ``errors[]``, never in ``manual[]`` — so this pins the real behaviour rather
    than bending ``resolve``'s long-standing contract to the brief's wording.
    """
    _path, entry = _registry(tmp_path)
    client = FakeClient({"/works/": HttpError("502 from OpenAlex")})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, NeverFetcher()))
    assert outcome.bucket == a.BUCKET_ERROR
    assert outcome.reason is not None
    assert "502 from OpenAlex" in outcome.reason


def test_unresolvable_entry_is_an_error_not_manual(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path)
    client = FakeClient({"/works/": {}})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, NeverFetcher()))
    assert outcome.bucket == a.BUCKET_ERROR
    assert outcome.reason is not None
    assert "could not resolve" in outcome.reason


def test_an_entry_with_no_identifier_is_an_error_without_a_request(
    tmp_path: Path,
) -> None:
    _path, entry = _registry(tmp_path, doi=None)
    client = FakeClient({})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, NeverFetcher()))
    assert outcome.bucket == a.BUCKET_ERROR
    assert outcome.reason is not None
    assert "nothing to resolve" in outcome.reason
    assert client.calls == []


def test_a_work_record_that_comes_back_unusable_is_an_error(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path)
    client = FakeClient(
        {"/works/doi:": _oa(pdf="http://x/p.pdf"), "/works/W1": ["not-a-work"]}
    )
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, NeverFetcher()))
    assert outcome.bucket == a.BUCKET_ERROR
    assert outcome.reason is not None
    assert "no usable work record" in outcome.reason


def test_bytes_that_cannot_be_recorded_are_an_error_that_says_where_they_are(
    tmp_path: Path,
) -> None:
    _path, entry = _registry(tmp_path)
    client = FakeClient({"/works/": _oa(pdf="http://x/p.pdf")})
    ctx = _ctx(
        tmp_path, client, FakeFetcher(), registry_path=tmp_path / "moved-away.json"
    )
    outcome = a.acquire_one(entry, ctx)
    assert outcome.bucket == a.BUCKET_ERROR
    assert outcome.reason is not None
    assert "could not record it" in outcome.reason
    assert outcome.sha256 == PDF_SHA
    assert (tmp_path / "cache" / "sha256" / PDF_SHA).exists()


# --- dry run ----------------------------------------------------------------


def test_dry_run_reports_the_rung_without_downloading(tmp_path: Path) -> None:
    path, entry = _registry(tmp_path)
    before = path.read_bytes()
    client = FakeClient({"/works/": _oa(pdf="http://x/p.pdf")})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, NeverFetcher()), dry_run=True)
    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.sha256 is None
    assert outcome.rung == a.RUNG_OA_BEST
    assert outcome.url == "http://x/p.pdf"
    assert outcome.committable is False
    assert path.read_bytes() == before


def test_dry_run_reports_a_permissive_license_as_committable(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path)
    client = FakeClient({"/works/": _oa(pdf="http://x/p.pdf", lic="cc-by")})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, NeverFetcher()), dry_run=True)
    assert outcome.committable is True
    assert outcome.license == "cc-by"


def test_dry_run_reports_a_quarantine_as_a_quarantine(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path)
    anchor = _oa(pdf=None, landing="http://x/abstract")
    sibling = _oa(wid="W2", year=2002, pdf="http://x/sib.pdf")
    client = FakeClient({"/works/": anchor, "/works": {"results": [sibling]}})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, NeverFetcher()), dry_run=True)
    assert outcome.bucket == a.BUCKET_QUARANTINED
    assert outcome.sha256 is None
    assert not (tmp_path / "cache" / "quarantine").exists()


# --- the license three-way --------------------------------------------------


def test_permissive_license_marks_the_outcome_committable(tmp_path: Path) -> None:
    path, entry = _registry(tmp_path)
    client = FakeClient({"/works/": _oa(pdf="http://x/p.pdf", lic="cc-by")})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher()))
    assert outcome.committable is True
    assert outcome.license == "cc-by"
    asset = _asset(path)
    assert asset.redistributable is True
    assert asset.license.id == "cc-by"
    assert asset.license.source == a.LICENSE_SOURCE


def test_absent_license_is_not_redistributable(tmp_path: Path) -> None:
    """36 of 50 works in the run that motivated this feature had no license."""
    path, entry = _registry(tmp_path)
    client = FakeClient({"/works/": _oa(pdf="http://x/p.pdf")})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher()))
    assert outcome.committable is False
    assert outcome.license is None
    asset = _asset(path)
    assert asset.redistributable is False
    assert asset.license.observed is None


def test_unrecognized_license_is_not_redistributable(tmp_path: Path) -> None:
    path, entry = _registry(tmp_path)
    client = FakeClient(
        {"/works/": _oa(pdf="http://x/p.pdf", lic="all-rights-reserved")}
    )
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher()))
    assert outcome.committable is False
    asset = _asset(path)
    assert asset.redistributable is False
    assert asset.license.observed == "all-rights-reserved"


def test_a_siblings_license_is_recorded_not_the_anchors(tmp_path: Path) -> None:
    """Rung 4 serves a *sibling's* bytes; the anchor's license does not describe them."""
    path, entry = _registry(tmp_path)
    anchor = _oa(pdf=None, landing="http://x/abstract", lic="cc-by")
    sibling = _oa(wid="W2", year=1998, pdf="http://x/sib.pdf", lic="cc-by-nc")
    client = FakeClient({"/works/": anchor, "/works": {"results": [sibling]}})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher()))
    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.rung == a.RUNG_SIBLING
    assert _asset(path).license.observed == "cc-by-nc"
    assert outcome.committable is False


def test_an_arxiv_candidate_carries_no_license_observation(tmp_path: Path) -> None:
    path, entry = _registry(
        tmp_path, title="Smooth Min-Max Monotonic Networks", year=2023, family="Igel"
    )
    anchor = _oa(
        title="Smooth Min-Max Monotonic Networks",
        year=2023,
        family="Igel",
        pdf=None,
        landing="http://x/abstract",
        lic="cc-by",
    )
    client = FakeClient(
        {
            "/works/": anchor,
            "/works": {"results": []},
            "export.arxiv.org": _ARXIV_FEED,
        }
    )
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher()))
    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.rung == a.RUNG_ARXIV_SEARCH
    assert _asset(path).license.observed is None


# --- access, landing pages, names -------------------------------------------


@pytest.mark.parametrize(
    ("open_access", "expected"),
    [({"is_oa": True}, "open"), ({"is_oa": False}, "gated"), ({}, None), (None, None)],
)
def test_access_from_work(open_access: Any, expected: str | None) -> None:
    assert a._access_from_work({"open_access": open_access}) == expected


@pytest.mark.parametrize(
    ("work", "expected"),
    [
        ({}, []),
        ({"locations": "nope"}, []),
        ({"locations": ["junk", {"landing_page_url": None}]}, []),
        ({"locations": [{"landing_page_url": "  "}]}, []),
        (
            {"locations": [{"landing_page_url": "http://x/a"}] * 2},
            ["http://x/a"],
        ),
    ],
)
def test_all_landing_urls(work: dict[str, Any], expected: list[str]) -> None:
    """Wider than :func:`landing_urls` — the manual worklist wants click targets."""
    assert a._all_landing_urls(work) == expected


def test_a_citekey_with_path_characters_stays_inside_the_cache(
    tmp_path: Path,
) -> None:
    assert a._quarantine_dir(tmp_path, "../../etc/passwd") == (
        tmp_path / "quarantine" / ".._.._etc_passwd"
    )


def test_outcome_as_json_carries_every_field() -> None:
    outcome = a.Outcome(citekey="k", bucket=a.BUCKET_MANUAL, tried=["r"])
    assert a.Outcome(citekey="k", bucket=a.BUCKET_MANUAL).as_json() == {
        "citekey": "k",
        "bucket": a.BUCKET_MANUAL,
        "sha256": None,
        "rung": None,
        "url": None,
        "candidate": None,
        "match": None,
        "reason": None,
        "tried": [],
        "landing_urls": [],
        "committable": False,
        "path": None,
        "license": None,
    }
    assert outcome.as_json()["tried"] == ["r"]


def test_a_rung_is_listed_once_however_many_candidates_it_offered(
    tmp_path: Path,
) -> None:
    _path, entry = _registry(tmp_path)
    anchor = _oa(
        pdfs=["http://x/one.pdf", "http://x/two.pdf"], landing="http://x/abstract"
    )
    client = FakeClient(
        {
            "/works/": anchor,
            "/works": {"results": []},
            "export.arxiv.org": "<feed/>",
        }
    )
    outcome = a.acquire_one(
        entry, _ctx(tmp_path, client, FakeFetcher(default=DownloadError("gone")))
    )
    assert outcome.bucket == a.BUCKET_MANUAL
    assert outcome.tried == [a.RUNG_OA_BEST, a.RUNG_OA_LOCATIONS]


def test_a_corrupt_cache_blob_with_no_mirror_says_so_and_discards_it(
    tmp_path: Path,
) -> None:
    """'The cache is corrupt' and 'nothing has it' are different problems."""
    _path, entry = _registry(tmp_path, spine=_spine())
    blob = tmp_path / "cache" / "sha256" / PDF_SHA
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(b"corrupt")
    outcome = a.acquire_one(entry, _ctx(tmp_path, FakeClient({}), NeverFetcher()))
    assert outcome.bucket == a.BUCKET_MANUAL
    assert outcome.reason is not None
    assert "the cached blob did not match" in outcome.reason
    assert not blob.exists()


def test_a_rungs_license_is_the_one_on_its_own_location(tmp_path: Path) -> None:
    """OpenAlex reports the license per *location*, and rungs 2-3 change location.

    Rung 1's ``best_oa_location`` is ``cc-by`` but does not download; rung 2
    succeeds on a second copy whose own ``license`` is null. Recording ``cc-by``
    there would put the entry in ``committable[]`` — a rights assertion a human
    may act on by copying the bytes into their repository — on the strength of a
    grant that covers a different copy.
    """
    path, entry = _registry(tmp_path)
    work = _oa(pdf="http://x/licensed.pdf", lic="cc-by")
    work["locations"].append(
        {
            "landing_page_url": None,
            "pdf_url": "http://x/unlicensed.pdf",
            "license": None,
        }
    )
    client = FakeClient({"/works/": work})
    fetcher = FakeFetcher(
        {"http://x/licensed.pdf": DownloadError("http://x/licensed.pdf: 403")}
    )
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, fetcher))
    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.url == "http://x/unlicensed.pdf"
    assert outcome.license is None
    assert outcome.committable is False
    asset = _asset(path)
    assert asset.license.observed is None
    assert asset.redistributable is False


def test_a_landing_page_rung_reads_its_own_locations_license(tmp_path: Path) -> None:
    """The same rule one rung further down: rung 3 is a location too."""
    path, entry = _registry(tmp_path)
    work = _oa(pdf=None, landing="http://x/paper.pdf", lic=None)
    work["best_oa_location"] = {"pdf_url": None, "license": "cc-by"}
    client = FakeClient({"/works/": work})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher()))
    assert outcome.rung == a.RUNG_OA_LANDING
    assert outcome.committable is False
    assert _asset(path).license.observed is None


def test_a_location_that_does_carry_a_license_records_it(tmp_path: Path) -> None:
    path, entry = _registry(tmp_path)
    work = _oa(pdf=None, landing="http://x/paper.pdf", lic="cc-by-4.0")
    client = FakeClient({"/works/": work})
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, FakeFetcher()))
    assert outcome.committable is True
    assert _asset(path).license.id == "cc-by-4.0"


def test_a_venue_template_falls_back_to_the_work_level_license(
    tmp_path: Path,
) -> None:
    """Rung 6 names the anchor work, not one of its copies — no location to read."""
    path, entry = _registry(tmp_path)
    anchor = _oa(pdf=None, landing="http://x/abstract", lic="cc-by")
    client = FakeClient(
        {
            "/works/": anchor,
            "/works": {"results": []},
            "export.arxiv.org": "<feed/>",
        }
    )
    ctx = _ctx(
        tmp_path,
        client,
        FakeFetcher(),
        resolvers=[{"match": "Neural", "url_template": "http://v/{openalex}.pdf"}],
    )
    outcome = a.acquire_one(entry, ctx)
    assert outcome.rung == a.RUNG_VENUE
    assert _asset(path).license.id == "cc-by"
