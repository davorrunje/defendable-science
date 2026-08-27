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
