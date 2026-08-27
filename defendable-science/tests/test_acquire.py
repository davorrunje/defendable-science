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
from defendable_science.core.mirror import MirrorUnreachableError
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
    assert frozenset({a.RUNG_SIBLING, a.RUNG_ARXIV_SEARCH}) == a.GATED_RUNGS


def test_the_venue_rung_is_trusted_not_gated() -> None:
    # Its candidate is built from the anchor work, so evaluate_match would be
    # comparing the entry against itself: an "accept" there is a verification
    # that never happened (ADR-0038).
    assert a.RUNG_VENUE not in a.GATED_RUNGS


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


def test_a_closed_work_still_offers_its_landing_pages_to_the_sniff_tail() -> None:
    # No pdf_url anywhere, so rungs 1-2 are empty; the landing pages are offered
    # because a suffix is a hint, not a requirement. looks_like_pdf disposes.
    candidates = a.identity_candidates(_work("monokan_journal"))
    assert {c.rung for c in candidates} == {a.RUNG_OA_LANDING}


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


def test_landing_urls_puts_pdf_shaped_links_first() -> None:
    work = {
        "locations": [
            {"landing_page_url": "http://x/abs/1"},
            {"landing_page_url": "http://x/paper.pdf"},
            {"landing_page_url": None},
            {},
            "junk",
        ]
    }
    assert a.landing_urls(work) == ["http://x/paper.pdf", "http://x/abs/1"]


def test_the_sniff_tail_is_bounded_but_pdf_shaped_links_are_not() -> None:
    # A work with a long locations[] array must not become one round-trip per
    # entry; the cap applies only to the suffix-less tail.
    extra = a.LANDING_SNIFF_LIMIT + 2
    work = {
        "locations": [
            *({"landing_page_url": f"http://x/p{i}.pdf"} for i in range(extra)),
            *({"landing_page_url": f"http://x/abs/{i}"} for i in range(extra)),
        ]
    }
    urls = a.landing_urls(work)
    assert urls[:extra] == [f"http://x/p{i}.pdf" for i in range(extra)]
    assert urls[extra:] == [f"http://x/abs/{i}" for i in range(a.LANDING_SNIFF_LIMIT)]


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


HTML = b"<html>an abstract page, not a PDF</html>"

#: Fixture URLs that stand for an HTML abstract page. The landing rung sniffs
#: suffix-less URLs up to ``LANDING_SNIFF_LIMIT`` rather than dropping them on
#: their suffix, so a decoy must actually serve non-PDF bytes to be rejected —
#: which is precisely what ``looks_like_pdf`` is there to decide.
DECOY_BODIES: dict[str, bytes | Exception] = {"http://x/abstract": HTML}


class FakeFetcher:
    """A ``BytesFetcher`` that serves canned bodies (or raises) per URL."""

    def __init__(
        self,
        bodies: dict[str, bytes | Exception] | None = None,
        default: bytes | Exception | None = PDF,
    ) -> None:
        self.bodies = {**DECOY_BODIES, **(bodies or {})}
        self.default = default
        self.calls: list[str] = []

    def __call__(self, url: str, dest: Path, max_bytes: int) -> FetchedBytes:
        self.calls.append(url)
        payload = self.bodies.get(url, self.default)
        if isinstance(payload, Exception):
            raise payload
        if payload is None:
            raise DownloadError(f"{url}: nothing here", status=404)
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
        self,
        body: bytes | None = None,
        put_error: Exception | None = None,
        check_error: Exception | None = None,
        get_error: Exception | None = None,
        present: bool | None = None,
    ) -> None:
        self.body = body
        self.put_error = put_error
        self.check_error = check_error
        self.get_error = get_error
        self.present = present
        self.puts: list[tuple[str, str]] = []
        self.checks: list[str] = []
        self.remote = "papers"
        self.base_path = "literature"

    def put(self, local: str | Path, sha256: str) -> None:
        if self.put_error is not None:
            raise self.put_error
        self.puts.append((str(local), sha256))

    def get(self, sha256: str, dst: str | Path) -> bool:
        if self.get_error is not None:
            raise self.get_error
        if self.body is None:
            return False
        target = Path(dst)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.body)
        return True

    def check(self, sha256: str) -> bool:
        self.checks.append(sha256)
        if self.check_error is not None:
            raise self.check_error
        return self.present if self.present is not None else self.body is not None


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
def test_observed_license_scans_work_level_fallback_locations(
    work: dict[str, Any], expected: str | None
) -> None:
    """``_observed_license`` with no location falls back to the work-level scan.

    Exercised directly rather than through a shipped public wrapper: nothing
    ships calls a work-level-only license lookup (rung 6's own use goes
    through :func:`~defendable_science.literature.acquire.candidate_from_work`,
    which is covered by the rung-6 tests below), so there is no
    ``license_from_work`` to call here — only the private helpers this test
    exists to pin down.
    """
    assert a._license_from_observed(a._observed_license(work)).id == expected


def test_observed_license_records_the_raw_string_and_its_source() -> None:
    observed = a._license_from_observed(
        a._observed_license({"best_oa_location": {"license": "All-Rights-Reserved"}})
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


def _unreachable_mirror() -> FakeMirror:
    return FakeMirror(
        get_error=MirrorUnreachableError(
            "rclone copyto on 'papers' failed with exit 7: SignatureDoesNotMatch — "
            "the mirror could not be reached",
            returncode=7,
            stderr="SignatureDoesNotMatch",
        )
    )


def test_a_mirror_that_could_not_be_reached_is_an_error_never_manual(
    tmp_path: Path,
) -> None:
    """The negative that matters: no `manual` row for a mirror we never asked.

    A ``manual`` row is a worklist item — it leaves the sweep ``complete`` and
    exit 0 — so filing an expired credential there tells a researcher to
    hand-download a paper that is very likely sitting in their own mirror.
    """
    _path, entry = _registry(tmp_path, spine=_spine())

    outcome = a.acquire_one(
        entry,
        _ctx(tmp_path, FakeClient({}), NeverFetcher(), mirror=_unreachable_mirror()),
    )

    assert outcome.bucket != a.BUCKET_MANUAL
    assert outcome.bucket == a.BUCKET_ERROR
    assert outcome.reason is not None
    assert "could not be reached" in outcome.reason
    assert "not in the mirror either" not in outcome.reason
    # Serialized under ``error``, the key an ``errors[]`` reader looks at.
    assert "could not be reached" in outcome.as_json()["error"]


def test_an_unreachable_mirror_still_reports_a_corrupt_cache_blob(
    tmp_path: Path,
) -> None:
    """Both faults are true at once, and the row says so."""
    _path, entry = _registry(tmp_path, spine=_spine())
    blob = tmp_path / "cache" / "sha256" / PDF_SHA
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(b"corrupt")

    outcome = a.acquire_one(
        entry,
        _ctx(tmp_path, FakeClient({}), NeverFetcher(), mirror=_unreachable_mirror()),
    )

    assert outcome.bucket == a.BUCKET_ERROR
    assert outcome.reason is not None
    assert "did not match the recorded checksum" in outcome.reason
    assert "could not be reached" in outcome.reason


def test_a_sweep_reports_an_unreachable_mirror_and_keeps_going(
    tmp_path: Path,
) -> None:
    """Per-entry, not fatal: the row lands in ``errors`` and the sweep completes."""
    _path, _entry_obj = _registry(tmp_path, spine=_spine())
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher(), mirror=_unreachable_mirror())

    report = a.fetch_all(ctx)

    assert report["manual"] == []
    assert len(report["errors"]) == 1
    assert "could not be reached" in report["errors"][0]["error"]


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
            "http://x/one.pdf": DownloadError("http://x/one.pdf: 404", status=404),
            "http://x/two.pdf": DownloadError("http://x/two.pdf: 403", status=403),
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
    fetcher = FakeFetcher(default=DownloadError("http://x/dead.pdf: 404", status=404))
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, fetcher))
    assert outcome.bucket == a.BUCKET_MANUAL
    assert outcome.landing_urls == ["http://x/abstract"]
    # The landing page is fetched and sniffed now, not dropped on its suffix, so
    # it is a rung the ladder really did try.
    assert outcome.tried == [a.RUNG_OA_BEST, a.RUNG_OA_LANDING, a.RUNG_SIBLING]


def test_a_ladder_with_no_candidates_at_all_is_manual(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path)
    # No landing page either: this ladder really has nothing to offer.
    anchor = _oa(pdf=None, landing=None)
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
    assert outcome.landing_urls == []


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
    # No landing page, so the ladder reaches the gated rung untouched.
    anchor = _oa(pdf=None, landing=None)
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


def test_a_venue_resolver_candidate_is_trusted_not_gate_verified(
    tmp_path: Path,
) -> None:
    """Rung 6 binds the bytes, but says it was trusted, not verified (ADR-0038)."""
    _path, entry = _registry(tmp_path)
    anchor = _oa(pdf=None, landing=None)
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
    assert outcome.match["verdict"] == a.TRUSTED
    # No axis is claimed, because none was compared.
    assert outcome.match["title"] is None
    assert outcome.match["author"] is None
    assert outcome.match["year"] is None
    assert "not verified" in outcome.match["reason"]


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
    # No landing page, so the sibling is the first candidate a dry run reports.
    anchor = _oa(pdf=None, landing=None)
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
        "failures": [],
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
        entry,
        _ctx(tmp_path, client, FakeFetcher(default=DownloadError("gone", status=404))),
    )
    assert outcome.bucket == a.BUCKET_MANUAL
    assert outcome.tried == [a.RUNG_OA_BEST, a.RUNG_OA_LOCATIONS, a.RUNG_OA_LANDING]


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
        {
            "http://x/licensed.pdf": DownloadError(
                "http://x/licensed.pdf: 403", status=403
            )
        }
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


# --- task 11: the sweep and its report ---------------------------------------
#
# `_registry` (above) writes exactly one entry, so the multi-entry sweep tests
# below use their own small helpers rather than stretching that one to fit.


def _bib(
    citekey: str, doi: str, *, title: str = "T", year: int = 2020, family: str = "A"
) -> dict[str, Any]:
    return {
        "id": citekey,
        "type": "article",
        "title": title,
        "author": [{"family": family, "given": "X"}],
        "issued": {"date-parts": [[year]]},
        "DOI": doi,
    }


def _write_bib(tmp_path: Path, items: list[dict[str, Any]]) -> Path:
    path = tmp_path / "references.json"
    path.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")
    return path


def _write_triage(tmp_path: Path, rows: dict[str, str]) -> Path:
    path = tmp_path / "triage.yml"
    body = "".join(f"{key}:\n  disposition: {value}\n" for key, value in rows.items())
    path.write_text(body, encoding="utf-8")
    return path


def test_report_has_every_bucket_and_is_complete(tmp_path: Path) -> None:
    _write_bib(
        tmp_path,
        [
            _bib("fetches", "10.1000/fetches", family="Fa"),
            _bib("refuses", "10.1000/refuses", family="Fb"),
        ],
    )
    client = FakeClient(
        {
            "/works/doi:10.1000/fetches": _oa(
                wid="Wf", family="Fa", pdf="http://x/f.pdf"
            ),
            "/works/Wf": _oa(wid="Wf", family="Fa", pdf="http://x/f.pdf"),
            "/works/doi:10.1000/refuses": _oa(wid="Wr", family="Fb", pdf=None),
            "/works/Wr": _oa(wid="Wr", family="Fb", pdf=None),
            "/works": {"results": []},
            "export.arxiv.org": "<feed/>",
        }
    )
    report = a.fetch_all(_ctx(tmp_path, client, FakeFetcher()))
    assert set(report) == {
        "complete",
        "not_attempted",
        "fetched",
        "cached",
        "quarantined",
        "manual",
        "committable",
        "errors",
    }
    assert report["complete"] is True
    assert report["not_attempted"] == 0


def test_bucket_constants_match_report_keys(tmp_path: Path) -> None:
    """Pins ``report[outcome.bucket]``: a rename desynchronizing them would KeyError."""
    _write_bib(tmp_path, [])
    report = a.fetch_all(_ctx(tmp_path, FakeClient({}), NeverFetcher()))
    for constant in (
        a.BUCKET_CACHED,
        a.BUCKET_FETCHED,
        a.BUCKET_QUARANTINED,
        a.BUCKET_MANUAL,
        a.BUCKET_ERROR,
    ):
        assert constant in report


def test_disposition_filters_the_sweep(tmp_path: Path) -> None:
    _write_bib(
        tmp_path,
        [
            _bib("screened_entry", "10.1000/s", family="Sa"),
            _bib("inbox_entry", "10.1000/i", family="Ib"),
        ],
    )
    _write_triage(tmp_path, {"screened_entry": "screened", "inbox_entry": "inbox"})
    client = FakeClient(
        {
            "/works/doi:10.1000/s": _oa(wid="Ws", family="Sa", pdf="http://x/s.pdf"),
            "/works/Ws": _oa(wid="Ws", family="Sa", pdf="http://x/s.pdf"),
        }
    )
    report = a.fetch_all(_ctx(tmp_path, client, FakeFetcher()), disposition="screened")
    assert [row["citekey"] for row in report["fetched"]] == ["screened_entry"]


def test_entries_without_a_triage_row_are_excluded_when_filtering(
    tmp_path: Path,
) -> None:
    _write_bib(tmp_path, [_bib("solo", "10.1000/solo")])
    report = a.fetch_all(
        _ctx(tmp_path, FakeClient({}), NeverFetcher()), disposition="screened"
    )
    assert report["fetched"] == []


def test_entries_without_a_triage_row_are_included_when_not_filtering(
    tmp_path: Path,
) -> None:
    _write_bib(tmp_path, [_bib("solo", "10.1000/solo", family="So")])
    client = FakeClient(
        {
            "/works/doi:10.1000/solo": _oa(
                wid="Wsolo", family="So", pdf="http://x/solo.pdf"
            ),
            "/works/Wsolo": _oa(wid="Wsolo", family="So", pdf="http://x/solo.pdf"),
        }
    )
    report = a.fetch_all(_ctx(tmp_path, client, FakeFetcher()))
    assert [row["citekey"] for row in report["fetched"]] == ["solo"]


def test_an_explicit_citekey_with_no_triage_row_is_an_error_under_a_filter(
    tmp_path: Path,
) -> None:
    """A citekey named by hand must never just vanish.

    Silently dropping it would be indistinguishable from "it was processed
    and landed nowhere" — the same ambiguity spec §9 forbids for a throttle.
    Unlike the implicit whole-registry sweep, where a non-matching entry is
    correctly just excluded, the caller asked for this one by name.
    """
    _write_bib(tmp_path, [_bib("solo", "10.1000/solo")])
    report = a.fetch_all(
        _ctx(tmp_path, FakeClient({}), NeverFetcher()),
        citekeys=["solo"],
        disposition="screened",
    )
    assert report["complete"] is True
    assert len(report["errors"]) == 1
    assert report["errors"][0]["citekey"] == "solo"
    assert "disposition" in report["errors"][0]["error"]
    for bucket in ("fetched", "cached", "quarantined", "manual"):
        assert report[bucket] == []


def test_an_explicit_citekey_with_a_non_matching_row_is_an_error_under_a_filter(
    tmp_path: Path,
) -> None:
    _write_bib(tmp_path, [_bib("solo", "10.1000/solo")])
    _write_triage(tmp_path, {"solo": "inbox"})
    report = a.fetch_all(
        _ctx(tmp_path, FakeClient({}), NeverFetcher()),
        citekeys=["solo"],
        disposition="screened",
    )
    assert report["complete"] is True
    assert len(report["errors"]) == 1
    assert report["errors"][0]["citekey"] == "solo"
    assert "disposition" in report["errors"][0]["error"]


def test_explicit_citekeys_override_the_registry_order(tmp_path: Path) -> None:
    _write_bib(
        tmp_path,
        [_bib("a", "10.1000/a", family="Aa"), _bib("b", "10.1000/b", family="Bb")],
    )
    client = FakeClient(
        {
            "/works/doi:10.1000/a": _oa(wid="Wa", family="Aa", pdf=None),
            "/works/Wa": _oa(wid="Wa", family="Aa", pdf=None),
            "/works/doi:10.1000/b": _oa(wid="Wb", family="Bb", pdf=None),
            "/works/Wb": _oa(wid="Wb", family="Bb", pdf=None),
            "/works": {"results": []},
            "export.arxiv.org": "<feed/>",
        }
    )
    report = a.fetch_all(_ctx(tmp_path, client, NeverFetcher()), citekeys=["b", "a"])
    assert [row["citekey"] for row in report["manual"]] == ["b", "a"]


def test_unknown_citekey_is_an_error_row_not_a_crash(tmp_path: Path) -> None:
    _write_bib(tmp_path, [_bib("known", "10.1000/known")])
    report = a.fetch_all(
        _ctx(tmp_path, FakeClient({}), NeverFetcher()), citekeys=["nope"]
    )
    assert report["complete"] is True
    assert len(report["errors"]) == 1
    assert "no entry" in report["errors"][0]["error"]


def test_a_rate_limit_aborts_the_sweep_marked_incomplete(tmp_path: Path) -> None:
    """The point of the test.

    Nobody is told to download a paper by hand because OpenAlex throttled
    us — the untried entries are not bucketed at all, least of all as
    ``manual``.
    """
    _write_bib(
        tmp_path,
        [_bib("a1", "10.1000/a1"), _bib("a2", "10.1000/a2"), _bib("a3", "10.1000/a3")],
    )
    client = FakeClient({"/works/": RateLimitError("429 from OpenAlex")})
    report = a.fetch_all(_ctx(tmp_path, client, NeverFetcher()))
    assert report["complete"] is False
    assert report["not_attempted"] == 2
    assert "rate-limited" in report["errors"][0]["error"]
    assert report["manual"] == []


def test_a_transport_error_on_one_entry_does_not_stop_the_sweep(
    tmp_path: Path,
) -> None:
    """An ``HttpError`` is per-entry; only a rate limit aborts the sweep."""
    _write_bib(
        tmp_path,
        [
            _bib("broken", "10.1000/broken", family="Br"),
            _bib("ok", "10.1000/ok", family="Ok"),
        ],
    )
    client = FakeClient(
        {
            "/works/doi:10.1000/broken": _oa(
                wid="Wbroken", family="Br", pdf="http://x/b.pdf"
            ),
            "/works/Wbroken": HttpError("502 from OpenAlex"),
            "/works/doi:10.1000/ok": _oa(wid="Wok", family="Ok", pdf="http://x/ok.pdf"),
            "/works/Wok": _oa(wid="Wok", family="Ok", pdf="http://x/ok.pdf"),
        }
    )
    report = a.fetch_all(_ctx(tmp_path, client, FakeFetcher()))
    assert report["complete"] is True
    assert len(report["errors"]) == 1
    assert "502" in report["errors"][0]["error"]
    assert [row["citekey"] for row in report["fetched"]] == ["ok"]


def test_committable_lists_only_permissive_entries(tmp_path: Path) -> None:
    """A cache-only success (no permissive license) is still a success."""
    _write_bib(
        tmp_path,
        [
            _bib("licensed", "10.1000/lic", family="La"),
            _bib("unlicensed", "10.1000/unlic", family="Ua"),
        ],
    )
    client = FakeClient(
        {
            "/works/doi:10.1000/lic": _oa(
                wid="Wlic", family="La", pdf="http://x/l.pdf", lic="cc-by"
            ),
            "/works/Wlic": _oa(
                wid="Wlic", family="La", pdf="http://x/l.pdf", lic="cc-by"
            ),
            "/works/doi:10.1000/unlic": _oa(
                wid="Wunlic", family="Ua", pdf="http://x/u.pdf"
            ),
            "/works/Wunlic": _oa(wid="Wunlic", family="Ua", pdf="http://x/u.pdf"),
        }
    )
    report = a.fetch_all(_ctx(tmp_path, client, FakeFetcher()))
    assert [row["citekey"] for row in report["committable"]] == ["licensed"]
    assert {row["citekey"] for row in report["fetched"]} == {"licensed", "unlicensed"}


# --- not in the brief: obligations the task handed forward from Task 10 -----


def test_fetched_row_preserves_a_partial_mirror_failure_reason(tmp_path: Path) -> None:
    """A fetched row must not go silent about a partial mirror failure.

    Projecting it down to ``{citekey, sha256, rung, url}`` would make a
    partial mirror-write failure invisible — exactly the silent degradation
    spec §9 forbids. The report must carry the full outcome.
    """
    _write_bib(tmp_path, [_bib("mirrorfail", "10.1000/mf", family="Mf")])
    client = FakeClient(
        {
            "/works/doi:10.1000/mf": _oa(wid="Wmf", family="Mf", pdf="http://x/mf.pdf"),
            "/works/Wmf": _oa(wid="Wmf", family="Mf", pdf="http://x/mf.pdf"),
        }
    )
    mirror = FakeMirror(put_error=RetrievalError("rclone copyto to mirror failed"))
    ctx = _ctx(tmp_path, client, FakeFetcher(), mirror=mirror)
    report = a.fetch_all(ctx)
    assert len(report["fetched"]) == 1
    assert report["fetched"][0]["reason"] is not None
    assert "mirror write failed" in report["fetched"][0]["reason"]


def test_error_bucket_as_json_uses_error_not_reason() -> None:
    """Pins the key-spelling decision directly on ``Outcome.as_json()``."""
    outcome = a.Outcome(citekey="k", bucket=a.BUCKET_ERROR, reason="boom")
    payload = outcome.as_json()
    assert payload["error"] == "boom"
    assert "reason" not in payload


def test_non_error_bucket_as_json_still_uses_reason() -> None:
    outcome = a.Outcome(citekey="k", bucket=a.BUCKET_MANUAL, reason="boom")
    payload = outcome.as_json()
    assert payload["reason"] == "boom"
    assert "error" not in payload


def test_error_rows_from_acquire_one_also_use_the_error_key(tmp_path: Path) -> None:
    """The rename applies to ``acquire_one``'s own error rows too.

    Not just the sweep's synthesized ones (unknown citekey,
    aborted-by-rate-limit) — a consumer reading ``errors[]`` should never
    have to check two spellings.
    """
    _write_bib(tmp_path, [{"id": "noid", "type": "article", "title": "T"}])
    report = a.fetch_all(_ctx(tmp_path, FakeClient({}), NeverFetcher()))
    assert len(report["errors"]) == 1
    row = report["errors"][0]
    assert "reason" not in row
    assert row["error"] is not None
    assert "no DOI" in row["error"]


# --- task 12: confirm — promote quarantine, or adopt a manual file -----------


def _quarantine(
    tmp_path: Path,
    entry: reg.Entry,
    ctx: a.Context,
    *,
    sha: str = PDF_SHA,
    body: bytes = PDF,
    **cand_kw: Any,
) -> Path:
    """Park a candidate in quarantine via the module's own writer.

    Reuses :func:`a._write_quarantine` rather than hand-building the on-disk
    shape, so these tests do not silently drift from whatever the ladder
    actually writes.
    """
    candidate = _cand(rung=a.RUNG_SIBLING, url="http://x/sib.pdf", **cand_kw)
    match = a.MatchRecord(
        verdict=a.QUARANTINE,
        title="exact",
        author="exact",
        year="within-5",
        reason="plausibly a preprint, needs a human look",
    )
    src = tmp_path / "landed.part"
    src.write_bytes(body)
    return a._write_quarantine(ctx, entry, src, sha, candidate, match)


def test_confirm_promotes_a_quarantined_blob(tmp_path: Path) -> None:
    path, entry = _registry(tmp_path)
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher())
    parked = _quarantine(tmp_path, entry, ctx)
    directory = parked.parent

    outcome = a.confirm_quarantined(entry, ctx, PDF_SHA)

    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.sha256 == PDF_SHA
    assert outcome.rung == a.RUNG_SIBLING
    assert outcome.url == "http://x/sib.pdf"
    assert outcome.match is not None
    assert outcome.match["verdict"] == a.QUARANTINE
    assert (tmp_path / "cache" / "sha256" / PDF_SHA).read_bytes() == PDF
    assert not (directory / f"{PDF_SHA}.pdf").exists()
    assert not (directory / f"{PDF_SHA}.json").exists()
    asset = _asset(path)
    assert asset.acquisition is not None
    assert asset.acquisition.rung == a.RUNG_SIBLING
    assert asset.acquisition.match["verdict"] == a.QUARANTINE


def test_confirm_accepts_a_prefixed_checksum(tmp_path: Path) -> None:
    """``--sha256`` is a human-typed value; a ``sha256:`` prefix must work too."""
    _path, entry = _registry(tmp_path)
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher())
    _quarantine(tmp_path, entry, ctx)

    outcome = a.confirm_quarantined(entry, ctx, f"sha256:{PDF_SHA}")

    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.sha256 == PDF_SHA


def test_confirm_unknown_sha_is_an_actionable_error(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path)
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher())
    _quarantine(tmp_path, entry, ctx)

    with pytest.raises(RetrievalError, match=PDF_SHA):
        a.confirm_quarantined(entry, ctx, OTHER_SHA)


def test_confirm_with_nothing_in_quarantine_says_so(tmp_path: Path) -> None:
    """No quarantine directory at all for this citekey is also an actionable error."""
    _path, entry = _registry(tmp_path)
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher())

    with pytest.raises(RetrievalError, match="quarantine is empty"):
        a.confirm_quarantined(entry, ctx, PDF_SHA)


def test_confirm_rejects_a_corrupt_quarantine_blob(tmp_path: Path) -> None:
    path, entry = _registry(tmp_path)
    before = path.read_bytes()
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher())
    parked = _quarantine(tmp_path, entry, ctx)
    parked.write_bytes(b"truncated")

    outcome = a.confirm_quarantined(entry, ctx, PDF_SHA)

    assert outcome.bucket == a.BUCKET_ERROR
    assert outcome.reason is not None
    assert "truncated or tampered" in outcome.reason
    assert parked.read_bytes() == b"truncated"
    assert (parked.parent / f"{PDF_SHA}.json").exists()
    assert path.read_bytes() == before


def test_confirm_populates_the_mirror(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path)
    mirror = FakeMirror()
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher(), mirror=mirror)
    _quarantine(tmp_path, entry, ctx)

    outcome = a.confirm_quarantined(entry, ctx, PDF_SHA)

    assert outcome.bucket == a.BUCKET_FETCHED
    assert mirror.puts == [(str(tmp_path / "cache" / "sha256" / PDF_SHA), PDF_SHA)]


def test_adopt_file_hashes_and_records_it(tmp_path: Path) -> None:
    path, entry = _registry(tmp_path)
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher())
    src = tmp_path / "downloads" / "paper.pdf"
    src.parent.mkdir()
    src.write_bytes(PDF)

    outcome = a.adopt_file(entry, ctx, src)

    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.sha256 == PDF_SHA
    assert outcome.rung == a.RUNG_MANUAL
    asset = _asset(path)
    assert asset.acquisition is not None
    assert asset.acquisition.rung == a.RUNG_MANUAL
    assert asset.acquisition.match["verdict"] == a.IDENTITY
    assert asset.license.id is None
    assert asset.redistributable is False


def test_adopt_file_rejects_a_non_pdf(tmp_path: Path) -> None:
    path, entry = _registry(tmp_path)
    before = path.read_bytes()
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher())
    src = tmp_path / "notes.txt"
    src.write_bytes(b"not a pdf")

    outcome = a.adopt_file(entry, ctx, src)

    assert outcome.bucket == a.BUCKET_ERROR
    assert outcome.reason is not None
    assert "does not look like a PDF" in outcome.reason
    assert path.read_bytes() == before
    assert src.exists()


def test_adopt_file_missing_path_is_an_actionable_error(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path)
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher())
    missing = tmp_path / "nope.pdf"

    with pytest.raises(RetrievalError, match=r"nope\.pdf"):
        a.adopt_file(entry, ctx, missing)


def test_adopt_file_copies_rather_than_moves_the_humans_file(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path)
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher())
    src = tmp_path / "downloads" / "paper.pdf"
    src.parent.mkdir()
    src.write_bytes(PDF)

    outcome = a.adopt_file(entry, ctx, src)

    assert outcome.bucket == a.BUCKET_FETCHED
    assert src.is_file()
    assert src.read_bytes() == PDF


# --- task 13: verify (offline fixity) + mirror (push/probe) -----------------


def test_verify_entry_all_files_verify(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path, spine=_spine())
    cache = tmp_path / "cache"
    _seed_blob(tmp_path)

    report = a.verify_entry(entry, cache_dir=cache)

    assert report.ok
    assert report.verified == [f"sha256/{PDF_SHA}"]
    assert report.missing == []
    assert report.corrupt == []
    assert report.note is None
    assert report.as_json() == {
        "citekey": entry.citekey,
        "ok": True,
        "verified": [f"sha256/{PDF_SHA}"],
        "missing": [],
        "corrupt": [],
    }


def test_verify_entry_flags_a_missing_blob(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path, spine=_spine())
    cache = tmp_path / "cache"  # nothing seeded here

    report = a.verify_entry(entry, cache_dir=cache)

    assert not report.ok
    assert report.missing == [f"sha256/{PDF_SHA}"]
    assert report.verified == []
    assert report.corrupt == []


def test_verify_entry_flags_a_corrupt_blob(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path, spine=_spine())
    cache = tmp_path / "cache"
    blob = cache / "sha256" / PDF_SHA
    blob.parent.mkdir(parents=True)
    blob.write_bytes(OTHER_PDF)  # bit-rot: wrong bytes under the recorded hash

    report = a.verify_entry(entry, cache_dir=cache)

    assert not report.ok
    assert report.corrupt == [f"sha256/{PDF_SHA}"]
    assert report.verified == []
    assert report.missing == []


def test_verify_entry_unreadable_file_is_corrupt_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _path, entry = _registry(tmp_path, spine=_spine())
    cache = tmp_path / "cache"
    _seed_blob(tmp_path)

    def _boom(_p: object, **_kw: object) -> str:
        raise PermissionError("unreadable")

    monkeypatch.setattr(a, "sha256_file", _boom)
    report = a.verify_entry(entry, cache_dir=cache)

    assert report.corrupt == [f"sha256/{PDF_SHA}"]
    assert not report.ok


def test_verify_entry_with_no_asset_reports_missing_never_ok(tmp_path: Path) -> None:
    """The case that matters: an unfetched paper must never read as verified."""
    entry = _entry()
    assert entry.asset is None

    report = a.verify_entry(entry, cache_dir=tmp_path / "cache")

    assert report.ok is False
    assert report.verified == []
    assert report.note is not None
    assert report.missing == [report.note]
    assert "no asset recorded" in report.note
    payload = report.as_json()
    assert payload["ok"] is False
    assert payload["note"] == report.note


def test_verify_entry_with_asset_but_no_files_also_reports_missing(
    tmp_path: Path,
) -> None:
    """A recorded-but-empty spine is the same "nothing to verify" case."""
    _path, entry = _registry(tmp_path, spine=_spine(files=[]))

    report = a.verify_entry(entry, cache_dir=tmp_path / "cache")

    assert report.ok is False
    assert report.note is not None
    assert report.missing == [report.note]


def test_mirror_entry_pushes_a_locally_cached_file(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path, spine=_spine())
    _seed_blob(tmp_path)
    mirror = FakeMirror()  # not yet present in the mirror

    report = a.mirror_entry(entry, cache_dir=tmp_path / "cache", mirror=mirror)

    assert report == {
        "citekey": entry.citekey,
        "pushed": [PDF_SHA],
        "already_present": [],
        "missing": [],
        "corrupt": [],
    }
    assert mirror.puts == [(str(tmp_path / "cache" / "sha256" / PDF_SHA), PDF_SHA)]


def test_mirror_entry_reports_an_already_present_file_without_pushing(
    tmp_path: Path,
) -> None:
    _path, entry = _registry(tmp_path, spine=_spine())
    _seed_blob(tmp_path)
    mirror = FakeMirror(present=True)

    report = a.mirror_entry(entry, cache_dir=tmp_path / "cache", mirror=mirror)

    assert report["already_present"] == [PDF_SHA]
    assert report["pushed"] == []
    assert mirror.puts == []


def test_mirror_entry_check_only_never_pushes(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path, spine=_spine())
    _seed_blob(tmp_path)  # bytes are available locally, but --check must not push
    mirror = FakeMirror(present=False)

    report = a.mirror_entry(
        entry,
        cache_dir=tmp_path / "cache",
        mirror=mirror,
        check_only=True,
    )

    assert report["missing"] == [PDF_SHA]
    assert report["pushed"] == []
    assert mirror.puts == []


def test_mirror_entry_with_no_local_blob_reports_missing_without_pushing(
    tmp_path: Path,
) -> None:
    _path, entry = _registry(tmp_path, spine=_spine())
    # No blob seeded: nothing local to push, even though the mirror lacks it too.
    mirror = FakeMirror(present=False)

    report = a.mirror_entry(entry, cache_dir=tmp_path / "cache", mirror=mirror)

    assert report["missing"] == [PDF_SHA]
    assert report["pushed"] == []
    assert mirror.puts == []


def test_mirror_entry_with_no_asset_reports_missing_without_probing(
    tmp_path: Path,
) -> None:
    entry = _entry()
    assert entry.asset is None
    mirror = FakeMirror()

    report = a.mirror_entry(entry, cache_dir=tmp_path / "cache", mirror=mirror)

    assert report["pushed"] == []
    assert report["already_present"] == []
    assert len(report["missing"]) == 1
    assert "no asset recorded" in report["missing"][0]
    assert mirror.checks == []  # nothing to probe for


def test_mirror_entry_with_asset_but_no_files_reports_missing(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path, spine=_spine(files=[]))
    mirror = FakeMirror()

    report = a.mirror_entry(entry, cache_dir=tmp_path / "cache", mirror=mirror)

    assert len(report["missing"]) == 1
    assert mirror.checks == []


def test_mirror_entry_propagates_a_missing_rclone_binary_intact(
    tmp_path: Path,
) -> None:
    """A transport failure is not "not present" — it must not be swallowed."""
    _path, entry = _registry(tmp_path, spine=_spine())
    _seed_blob(tmp_path)
    mirror = FakeMirror(
        check_error=RetrievalError("rclone not found on PATH — install it")
    )

    with pytest.raises(RetrievalError, match="rclone not found"):
        a.mirror_entry(entry, cache_dir=tmp_path / "cache", mirror=mirror)

    assert mirror.puts == []


def test_mirror_entry_refuses_to_push_a_bit_rotted_local_blob(tmp_path: Path) -> None:
    """A local blob whose bytes no longer match the recorded checksum.

    The mirror exists as insurance against link rot and paywalls; pushing
    corrupt bytes into it would turn the backup into a second copy of the
    damage (spec §9 already treats a corrupt cache blob as absent — the
    same rule literature's own `verify_entry` applies).
    """
    _path, entry = _registry(tmp_path, spine=_spine())
    blob = tmp_path / "cache" / "sha256" / PDF_SHA
    blob.parent.mkdir(parents=True)
    blob.write_bytes(OTHER_PDF)  # bit-rot: wrong bytes under the recorded hash
    mirror = FakeMirror(present=False)

    report = a.mirror_entry(entry, cache_dir=tmp_path / "cache", mirror=mirror)

    assert report["corrupt"] == [PDF_SHA]
    assert report["pushed"] == []
    assert report["missing"] == []
    assert mirror.puts == []


def test_mirror_entry_unreadable_local_blob_is_corrupt_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _path, entry = _registry(tmp_path, spine=_spine())
    _seed_blob(tmp_path)
    mirror = FakeMirror(present=False)

    def _boom(_p: object, **_kw: object) -> str:
        raise PermissionError("unreadable")

    monkeypatch.setattr(a, "sha256_file", _boom)
    report = a.mirror_entry(entry, cache_dir=tmp_path / "cache", mirror=mirror)

    assert report["corrupt"] == [PDF_SHA]
    assert report["pushed"] == []
    assert mirror.puts == []


# --- the byte layer's failure honesty ------------------------------------------
#
# The metadata layer got this right from the start: `_resolve_work` refuses to
# call a miss a `manual` row, and a `RateLimitError` aborts the sweep. The *byte*
# layer did not. Every `DownloadError` — 429, 403, 503, a dropped connection —
# was swallowed by `_land_bytes`, the ladder walked on, and an exhausted ladder
# was filed as "this paper has no PDF" with `complete: true` and exit 0. These
# tests assert the negative: which verdicts a transport failure must *not* be
# able to produce.


def test_a_byte_layer_throttle_cannot_produce_a_manual_verdict(
    tmp_path: Path,
) -> None:
    """The required test 1 — a 429 from a PDF host is never "no PDF exists".

    arXiv answers 429 to unthrottled PDF pulls and publisher CDNs 403
    non-browser agents, so this is what a 50-paper sweep hits in practice. It
    must abort the sweep, exactly as an OpenAlex throttle does: nothing
    bucketed as ``manual``, ``complete: false`` so the command exits non-zero,
    the untried entries counted rather than adjudicated, and the cause text
    still readable in the report.
    """
    _write_bib(
        tmp_path,
        [
            _bib("sill1997", "10.1000/sill", family="Sill"),
            _bib("later1", "10.1000/later1", family="Fb"),
            _bib("later2", "10.1000/later2", family="Fc"),
        ],
    )
    work = _oa(family="Sill", pdf="http://arxiv.org/pdf/1234")
    client = FakeClient(
        {
            "/works/doi:10.1000/sill": work,
            "/works/W1": work,
            "/works": {"results": []},
            "export.arxiv.org": "<feed/>",
        }
    )
    fetcher = FakeFetcher(
        default=DownloadError(
            "http://arxiv.org/pdf/1234: HTTP 429", status=429, retry_after=60
        )
    )
    report = a.fetch_all(_ctx(tmp_path, client, fetcher))

    assert report["manual"] == []
    assert report["fetched"] == []
    assert report["complete"] is False
    assert report["not_attempted"] == 2
    assert len(report["errors"]) == 1
    error = report["errors"][0]["error"]
    assert "rate-limited, sweep aborted" in error
    assert "HTTP 429" in error
    assert a.RUNG_OA_BEST in error


def test_a_503_asking_us_to_wait_aborts_the_sweep_too(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path)
    work = _oa(pdf="http://x/one.pdf")
    client = FakeClient({"/works/": work})
    fetcher = FakeFetcher(
        default=DownloadError("http://x/one.pdf: HTTP 503", status=503, retry_after=5)
    )
    with pytest.raises(RateLimitError, match="throttled while downloading bytes"):
        a.acquire_one(entry, _ctx(tmp_path, client, fetcher))


def test_a_blocked_ladder_is_an_error_row_not_a_manual_one(tmp_path: Path) -> None:
    """A 403 on every rung means we never looked, so ``manual`` is unearned.

    ``manual`` is a promise: we consulted every rung and this paper has no
    obtainable PDF. A CDN that refuses a non-browser agent has told us nothing
    about the paper, so the row goes to ``errors`` — which also makes the sweep
    exit non-zero — and it names each URL and its cause.
    """
    _path, entry = _registry(tmp_path)
    anchor = _oa(pdf="http://x/blocked.pdf", landing="http://x/abstract")
    client = FakeClient(
        {
            "/works/": anchor,
            "/works": {"results": []},
            "export.arxiv.org": "<feed/>",
        }
    )
    fetcher = FakeFetcher(
        default=DownloadError("http://x/blocked.pdf: HTTP 403", status=403)
    )
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, fetcher))

    assert outcome.bucket == a.BUCKET_ERROR
    assert outcome.reason is not None
    assert "not a 'no PDF exists' verdict" in outcome.reason
    assert "http://x/blocked.pdf: HTTP 403" in outcome.reason
    assert outcome.failures == [
        {
            "rung": a.RUNG_OA_BEST,
            "url": "http://x/blocked.pdf",
            "status": 403,
            "error": "http://x/blocked.pdf: HTTP 403",
            "blocking": True,
        }
    ]
    # The message keys as `error`, like every other errors[] row.
    payload = outcome.as_json()
    assert "reason" not in payload
    assert "http://x/blocked.pdf: HTTP 403" in payload["error"]
    assert payload["failures"] == outcome.failures
    # And the landing URLs still travel, so a human has somewhere to click.
    assert payload["landing_urls"] == ["http://x/abstract"]


def test_a_dead_link_still_earns_a_manual_verdict_and_records_the_cause(
    tmp_path: Path,
) -> None:
    """``404`` is the one transport answer that *is* evidence about the paper.

    The server answered, and its answer was "there is nothing here". So the row
    stays ``manual`` — but the cause is recorded rather than discarded, which is
    the difference between a worklist entry a human can act on and a bare
    "nothing served bytes".
    """
    _path, entry = _registry(tmp_path)
    anchor = _oa(pdf="http://x/dead.pdf", landing="http://x/abstract")
    client = FakeClient(
        {
            "/works/": anchor,
            "/works": {"results": []},
            "export.arxiv.org": "<feed/>",
        }
    )
    fetcher = FakeFetcher(
        default=DownloadError("http://x/dead.pdf: HTTP 404", status=404)
    )
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, fetcher))

    assert outcome.bucket == a.BUCKET_MANUAL
    assert outcome.failures[0]["blocking"] is False
    assert outcome.failures[0]["status"] == 404
    assert outcome.failures[0]["error"] == "http://x/dead.pdf: HTTP 404"


def test_one_block_among_dead_links_is_enough_to_refuse_manual(
    tmp_path: Path,
) -> None:
    """The verdict is only as good as its weakest rung.

    Rung 1 is genuinely gone (404); rung 2 was blocked (403). The blocked one
    might have been the PDF, so the entry cannot be filed as having none.
    """
    _path, entry = _registry(tmp_path)
    anchor = _oa(pdfs=["http://x/dead.pdf", "http://x/blocked.pdf"])
    client = FakeClient(
        {
            "/works/": anchor,
            "/works": {"results": []},
            "export.arxiv.org": "<feed/>",
        }
    )
    fetcher = FakeFetcher(
        {
            "http://x/dead.pdf": DownloadError("dead: HTTP 404", status=404),
            "http://x/blocked.pdf": DownloadError("blocked: HTTP 403", status=403),
        }
    )
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, fetcher))

    assert outcome.bucket == a.BUCKET_ERROR
    assert [failure["blocking"] for failure in outcome.failures] == [False, True]
    assert outcome.reason is not None
    assert "blocked: HTTP 403" in outcome.reason
    assert "dead: HTTP 404" not in outcome.reason


def test_a_failure_with_no_status_at_all_blocks_a_manual_verdict(
    tmp_path: Path,
) -> None:
    """A dropped connection or a full disk carries no status, and settles nothing."""
    _path, entry = _registry(tmp_path)
    client = FakeClient(
        {
            "/works/": _oa(pdf="http://x/one.pdf"),
            "/works": {"results": []},
            "export.arxiv.org": "<feed/>",
        }
    )
    fetcher = FakeFetcher(
        default=DownloadError("http://x/one.pdf: connection reset by peer")
    )
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, fetcher))

    assert outcome.bucket == a.BUCKET_ERROR
    assert outcome.failures[0]["status"] is None
    assert outcome.failures[0]["blocking"] is True


def test_a_refusal_is_still_reported_alongside_a_block(tmp_path: Path) -> None:
    """The closest refusal is what a human reads first; a block must not hide it."""
    _path, entry = _registry(tmp_path)
    anchor = _oa(pdf="http://x/blocked.pdf")
    sibling = _oa(wid="W2", family="Igel", pdf="http://x/sib.pdf")
    client = FakeClient(
        {
            "/works/": anchor,
            "/works": {"results": [sibling]},
            "export.arxiv.org": "<feed/>",
        }
    )
    fetcher = FakeFetcher(default=DownloadError("blocked: HTTP 403", status=403))
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, fetcher))

    assert outcome.bucket == a.BUCKET_ERROR
    assert outcome.reason is not None
    assert "the closest candidate was refused" in outcome.reason
    assert outcome.match is not None
    assert outcome.match["author"] == "mismatch"


def test_bytes_that_land_after_a_block_are_a_plain_success(tmp_path: Path) -> None:
    """A recorded failure is not a permanent stain: rung 2 served the PDF."""
    _path, entry = _registry(tmp_path)
    anchor = _oa(pdfs=["http://x/blocked.pdf", "http://x/good.pdf"])
    client = FakeClient({"/works/": anchor})
    fetcher = FakeFetcher(
        {"http://x/blocked.pdf": DownloadError("blocked: HTTP 403", status=403)}
    )
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, fetcher))

    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.url == "http://x/good.pdf"
    assert outcome.failures == []


# --- the landing sniff tail, end to end (#104) --------------------------------


def test_a_suffixless_landing_page_that_serves_a_pdf_is_recovered(
    tmp_path: Path,
) -> None:
    """The rung's point: a publisher can serve a PDF from an extension-less path."""
    _path, entry = _registry(tmp_path)
    anchor = _oa(pdf=None, landing="http://x/content/1358")
    client = FakeClient({"/works/": anchor})
    fetcher = FakeFetcher({"http://x/content/1358": PDF}, default=None)
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, fetcher))
    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.rung == a.RUNG_OA_LANDING
    assert outcome.url == "http://x/content/1358"
    assert outcome.sha256 == PDF_SHA
    # Identity-derived: no gate ran, and none was claimed to have run.
    assert outcome.match is not None
    assert outcome.match["verdict"] == a.IDENTITY


def test_a_suffixless_landing_page_serving_html_is_rejected(tmp_path: Path) -> None:
    """Sniffing costs a round-trip; %PDF- is what keeps an abstract page out."""
    _path, entry = _registry(tmp_path)
    anchor = _oa(pdf=None, landing="http://x/content/1358")
    client = FakeClient(
        {"/works/": anchor, "/works": {"results": []}, "export.arxiv.org": "<feed/>"}
    )
    fetcher = FakeFetcher({"http://x/content/1358": HTML}, default=None)
    outcome = a.acquire_one(entry, _ctx(tmp_path, client, fetcher))
    assert outcome.bucket == a.BUCKET_MANUAL
    assert fetcher.calls == ["http://x/content/1358"]  # tried once, then moved on
    assert outcome.landing_urls == ["http://x/content/1358"]


# --- rung 6 is trusted, not gated (#105) --------------------------------------


def test_a_venue_resolver_is_admitted_for_a_thin_entry(tmp_path: Path) -> None:
    """The gate refused thin *entries*; that never said anything about the URL.

    ``evaluate_match`` refuses when the entry lacks title/year/author, which used
    to block rung 6 as a side effect. The refusal was about the registry entry's
    own metadata, not about the consumer's template, so it is gone with the gate.
    """
    _path, entry = _registry(tmp_path, title=None, year=None, family=None)
    anchor = _oa(pdf=None, landing=None)
    client = FakeClient({"/works/": anchor, "/works": {"results": []}})
    ctx = _ctx(
        tmp_path,
        client,
        FakeFetcher(),
        resolvers=[{"match": "Neural", "url_template": "http://v/{openalex}.pdf"}],
    )
    outcome = a.acquire_one(entry, ctx)
    assert outcome.bucket == a.BUCKET_FETCHED
    assert outcome.rung == a.RUNG_VENUE
    assert outcome.match is not None
    assert outcome.match["verdict"] == a.TRUSTED


def test_the_trusted_verdict_is_not_an_accept() -> None:
    # A reader of the audit trail must be able to tell "we checked and it
    # matched" from "we took the operator's word for it".
    assert a.TRUSTED != a.ACCEPT
    assert a.TRUSTED != a.IDENTITY
