"""Tests for the literature registry read model + surgical writers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from defendable_science.literature import registry as reg


def _write(path: Path, items: list[dict[str, Any]]) -> Path:
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")
    return path


def _item(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "sill1997monotonic",
        "type": "paper-conference",
        "title": "Monotonic Networks",
        "author": [{"family": "Sill", "given": "Joseph"}],
        "issued": {"date-parts": [[1997]]},
    }
    base.update(kw)
    return base


def test_loads_bibliographic_fields(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item(DOI="10.5555/x")])
    entry = reg.load_registry(path).get("sill1997monotonic")
    assert entry is not None
    assert entry.title == "Monotonic Networks"
    assert entry.year == 1997
    assert entry.first_author_family == "Sill"
    assert entry.doi == "10.5555/x"
    assert entry.asset is None


def test_get_returns_none_for_unknown_citekey(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item()])
    assert reg.load_registry(path).get("nope") is None


def test_decodes_the_spine_from_custom(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "r.json",
        [
            _item(
                custom={
                    reg.NAMESPACE: {
                        "schema": 1,
                        "pid": "openalex:W2293093810",
                        "files": [
                            {
                                "path": "sha256/ab",
                                "sha256": "sha256:ab",
                                "size": 12,
                                "media_type": "application/pdf",
                            }
                        ],
                        "license": {
                            "id": "cc-by-4.0",
                            "observed": "CC BY 4.0",
                            "source": "openalex",
                        },
                        "redistributable": True,
                        "access": "open",
                        "mirror": {"remote": "papers", "key": "sha256/ab"},
                        "acquisition": {
                            "rung": "openalex-landing",
                            "url": "http://x/p.pdf",
                            "candidate": {"openalex": "W2293093810"},
                            "match": {"verdict": "identity"},
                            "fetched": "2026-08-27",
                        },
                    }
                }
            )
        ],
    )
    asset = reg.load_registry(path).get("sill1997monotonic").asset  # type: ignore[union-attr]
    assert asset is not None
    assert asset.files[0].sha256 == "sha256:ab"
    assert asset.license.id == "cc-by-4.0"
    assert asset.redistributable is True
    assert asset.mirror == reg.MirrorRef(remote="papers", key="sha256/ab")
    assert asset.acquisition is not None
    assert asset.acquisition.rung == "openalex-landing"


def test_ignores_a_foreign_custom_namespace(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item(custom={"zotero": {"x": 1}})])
    assert reg.load_registry(path).get("sill1997monotonic").asset is None  # type: ignore[union-attr]


def test_missing_year_and_author_decode_to_none(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [{"id": "k", "title": "T"}])
    entry = reg.load_registry(path).get("k")
    assert entry is not None
    assert entry.year is None
    assert entry.first_author_family is None


def test_literal_author_without_family_decodes_to_none(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item(author=[{"literal": "The Consortium"}])])
    assert reg.load_registry(path).get("sill1997monotonic").first_author_family is None  # type: ignore[union-attr]


def test_raw_date_parts_year_as_string_is_parsed(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item(issued={"date-parts": [["1997"]]})])
    assert reg.load_registry(path).get("sill1997monotonic").year == 1997  # type: ignore[union-attr]


def test_unparsable_year_is_none_not_an_error(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item(issued={"date-parts": [["n.d."]]})])
    assert reg.load_registry(path).get("sill1997monotonic").year is None  # type: ignore[union-attr]


def test_missing_file_is_an_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(reg.RegistryError, match="not found"):
        reg.load_registry(tmp_path / "absent.json")


def test_invalid_json_is_an_actionable_error(tmp_path: Path) -> None:
    path = tmp_path / "r.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(reg.RegistryError, match="invalid JSON"):
        reg.load_registry(path)


def test_non_array_top_level_is_an_actionable_error(tmp_path: Path) -> None:
    path = tmp_path / "r.json"
    path.write_text('{"items": []}', encoding="utf-8")
    pattern = rf"{re.escape(str(path))}: <root>: Input should be a valid array"
    with pytest.raises(reg.RegistryError, match=pattern):
        reg.load_registry(path)


def test_entry_without_an_id_is_an_actionable_error(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [{"title": "T"}])
    with pytest.raises(reg.RegistryError, match="entry 0 has no 'id'"):
        reg.load_registry(path)


def test_non_object_entry_is_an_actionable_error(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", ["nope"])  # type: ignore[list-item]
    with pytest.raises(reg.RegistryError, match="entry 0 is not an object"):
        reg.load_registry(path)


def test_asset_to_json_round_trips(tmp_path: Path) -> None:
    asset = reg.Asset(
        pid="openalex:W1",
        files=[
            reg.AssetFile(
                path="sha256/ab",
                sha256="sha256:ab",
                size=1,
                media_type="application/pdf",
            )
        ],
        license=reg.License(id="cc0-1.0", observed="CC0", source="openalex"),
        redistributable=True,
        access="open",
        mirror=reg.MirrorRef(remote="m", key="sha256/ab"),
        acquisition=reg.Acquisition(
            rung="manual",
            url=None,
            candidate={},
            match={"verdict": "identity"},
            fetched="2026-08-27",
        ),
    )
    path = _write(
        tmp_path / "r.json", [_item(custom={reg.NAMESPACE: reg.asset_to_json(asset)})]
    )
    assert reg.load_registry(path).get("sill1997monotonic").asset == asset  # type: ignore[union-attr]


def test_asset_to_json_omits_absent_optionals() -> None:
    blob = reg.asset_to_json(reg.Asset())
    assert "mirror" not in blob
    assert "acquisition" not in blob
    assert blob["schema"] == reg.SCHEMA
    assert blob["redistributable"] is False


# --- Supplementary coverage: malformed sub-fields degrade to "unknown" ------
#
# Not in the plan brief's 15-test list; added to close statement/branch
# coverage to the repo's 100% gate. Each case below is a hand-editable
# `references.json` field that is present but malformed in a way that means
# "unknown", not "structurally unusable" -- so it must decode to an absent
# value rather than raise.


def test_year_with_empty_date_parts_is_none(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item(issued={"date-parts": []})])
    assert reg.load_registry(path).get("sill1997monotonic").year is None  # type: ignore[union-attr]


def test_year_with_empty_first_date_part_is_none(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item(issued={"date-parts": [[]]})])
    assert reg.load_registry(path).get("sill1997monotonic").year is None  # type: ignore[union-attr]


def test_first_author_non_dict_entry_decodes_to_none(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item(author=["not-a-dict"])])
    assert reg.load_registry(path).get("sill1997monotonic").first_author_family is None  # type: ignore[union-attr]


def test_decode_asset_with_malformed_subfields_degrades(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "r.json",
        [
            _item(
                custom={
                    reg.NAMESPACE: {
                        "files": "not-a-list",
                        "license": "not-a-dict",
                        "mirror": "not-a-dict",
                        "acquisition": "not-a-dict",
                    }
                }
            )
        ],
    )
    asset = reg.load_registry(path).get("sill1997monotonic").asset  # type: ignore[union-attr]
    assert asset is not None
    assert asset.files == []
    assert asset.license == reg.License()
    assert asset.mirror is None
    assert asset.acquisition is None


def test_decode_files_skips_unusable_rows(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "r.json",
        [
            _item(
                custom={
                    reg.NAMESPACE: {
                        "files": [
                            "not-a-dict",
                            {"path": None, "sha256": "sha256:ab"},
                            {"path": "sha256/ab"},
                        ]
                    }
                }
            )
        ],
    )
    asset = reg.load_registry(path).get("sill1997monotonic").asset  # type: ignore[union-attr]
    assert asset is not None
    assert asset.files == []


def test_decode_mirror_missing_key_is_none(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "r.json",
        [_item(custom={reg.NAMESPACE: {"mirror": {"remote": "papers"}}})],
    )
    asset = reg.load_registry(path).get("sill1997monotonic").asset  # type: ignore[union-attr]
    assert asset is not None
    assert asset.mirror is None


def test_decode_acquisition_missing_rung_is_none(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "r.json",
        [_item(custom={reg.NAMESPACE: {"acquisition": {"url": "http://x"}}})],
    )
    asset = reg.load_registry(path).get("sill1997monotonic").asset  # type: ignore[union-attr]
    assert asset is not None
    assert asset.acquisition is None


def test_patch_asset_preserves_unknown_top_level_keys(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "r.json",
        [
            _item(
                **{
                    "note": "hand-written",
                    "keyword": "monotone",
                    "custom": {"zotero": {"k": 1}},
                }
            )
        ],
    )
    reg.patch_asset(path, "sill1997monotonic", reg.Asset(pid="openalex:W1"))
    item = json.loads(path.read_text(encoding="utf-8"))[0]
    assert item["note"] == "hand-written"
    assert item["keyword"] == "monotone"
    assert item["custom"]["zotero"] == {"k": 1}
    assert item["custom"][reg.NAMESPACE]["pid"] == "openalex:W1"


def test_patch_asset_preserves_key_order(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item()])
    before = list(json.loads(path.read_text(encoding="utf-8"))[0])
    reg.patch_asset(path, "sill1997monotonic", reg.Asset())
    after = list(json.loads(path.read_text(encoding="utf-8"))[0])
    assert after[: len(before)] == before
    assert after[-1] == "custom"


def test_patch_asset_leaves_other_entries_untouched(tmp_path: Path) -> None:
    other = {"id": "other", "title": "Other", "note": "keep me"}
    path = _write(tmp_path / "r.json", [_item(), other])
    reg.patch_asset(path, "sill1997monotonic", reg.Asset())
    assert json.loads(path.read_text(encoding="utf-8"))[1] == other


def test_patch_asset_replaces_an_existing_spine(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "r.json",
        [_item(custom={reg.NAMESPACE: {"schema": 1, "pid": "old", "stale": True}})],
    )
    reg.patch_asset(path, "sill1997monotonic", reg.Asset(pid="new"))
    blob = json.loads(path.read_text(encoding="utf-8"))[0]["custom"][reg.NAMESPACE]
    assert blob["pid"] == "new"
    assert "stale" not in blob


def test_patch_asset_falls_back_to_doi_lookup(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item(id="weird-key", DOI="10.5555/x")])
    reg.patch_asset(path, "10.5555/x", reg.Asset(pid="by-doi"))
    item = json.loads(path.read_text(encoding="utf-8"))[0]
    assert item["custom"][reg.NAMESPACE]["pid"] == "by-doi"


def test_patch_asset_unknown_citekey_is_an_actionable_error(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item()])
    with pytest.raises(reg.RegistryError, match="no entry 'nope'"):
        reg.patch_asset(path, "nope", reg.Asset())


def test_patch_asset_is_atomic_and_leaves_no_temp_file(tmp_path: Path) -> None:
    # NOTE: adjusted from the brief. The suite's autouse `_isolated_xdg_config_home`
    # fixture (tests/conftest.py) also creates a `home/` dir under `tmp_path`, so
    # asserting the full directory listing is brittle; assert on the specific
    # temp artifact instead, matching the precedent in test_literature.py.
    path = _write(tmp_path / "r.json", [_item()])
    reg.patch_asset(path, "sill1997monotonic", reg.Asset())
    assert not (tmp_path / "r.json.tmp").exists()
    assert path.exists()


def test_patch_asset_keeps_non_ascii_unescaped(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item(author=[{"family": "Bélair"}])])
    reg.patch_asset(path, "sill1997monotonic", reg.Asset())
    assert "Bélair" in path.read_text(encoding="utf-8")


def test_patch_asset_ends_with_a_newline(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item()])
    reg.patch_asset(path, "sill1997monotonic", reg.Asset())
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_patch_asset_rejects_a_non_object_custom(tmp_path: Path) -> None:
    # NOTE: match text adjusted from the brief to the implementation's actual
    # wording ("has a 'custom' field that is not an object") — the brief's
    # regex ("'custom' is not an object") does not occur as a substring of the
    # brief's own implementation message.
    path = _write(tmp_path / "r.json", [_item(custom="oops")])
    with pytest.raises(reg.RegistryError, match="'custom' field that is not an object"):
        reg.patch_asset(path, "sill1997monotonic", reg.Asset())


# --- Not from the brief: added to close a coverage gap the brief's 10 tests
# leave open (the DOI-fallback loop's non-dict guard in `_locate`). ---


def test_patch_asset_doi_fallback_skips_a_non_dict_item(tmp_path: Path) -> None:
    # A malformed/foreign CSL item (not an object) must not crash the DOI
    # fallback scan — it is skipped, and the scan continues to the real match.
    path = tmp_path / "r.json"
    path.write_text(
        json.dumps(["not-a-csl-item", _item(id="other-id", DOI="10.5555/y")]),
        encoding="utf-8",
    )
    reg.patch_asset(path, "10.5555/y", reg.Asset(pid="ok"))
    items = json.loads(path.read_text(encoding="utf-8"))
    assert items[0] == "not-a-csl-item"
    assert items[1]["custom"][reg.NAMESPACE]["pid"] == "ok"


def test_load_triage_reads_rows(tmp_path: Path) -> None:
    path = tmp_path / "t.yml"
    path.write_text(
        "sill1997monotonic:\n  disposition: screened\n  rationale: seminal\n",
        encoding="utf-8",
    )
    rows = reg.load_triage(path)
    assert rows["sill1997monotonic"].disposition == "screened"
    assert rows["sill1997monotonic"].raw["rationale"] == "seminal"


def test_load_triage_missing_file_is_empty_not_an_error(tmp_path: Path) -> None:
    assert reg.load_triage(tmp_path / "absent.yml") == {}


def test_load_triage_blank_file_is_empty(tmp_path: Path) -> None:
    path = tmp_path / "t.yml"
    path.write_text("", encoding="utf-8")
    assert reg.load_triage(path) == {}


def test_load_triage_skips_non_mapping_rows(tmp_path: Path) -> None:
    path = tmp_path / "t.yml"
    path.write_text("a: 3\nb:\n  disposition: screened\n", encoding="utf-8")
    rows = reg.load_triage(path)
    assert set(rows) == {"b"}


def test_load_triage_non_mapping_top_level_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "t.yml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(reg.RegistryError, match="expected a YAML mapping"):
        reg.load_triage(path)


def test_load_triage_invalid_yaml_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "t.yml"
    path.write_text("a: [unclosed\n", encoding="utf-8")
    with pytest.raises(reg.RegistryError, match="invalid YAML"):
        reg.load_triage(path)


def test_patch_triage_adds_and_replaces_scalars(tmp_path: Path) -> None:
    path = tmp_path / "t.yml"
    path.write_text("k:\n  disposition: inbox\n", encoding="utf-8")
    reg.patch_triage(path, "k", {"disposition": "screened", "priority": 2})
    rows = reg.load_triage(path)
    assert rows["k"].disposition == "screened"
    assert rows["k"].raw["priority"] == 2


def test_patch_triage_none_deletes_a_key(tmp_path: Path) -> None:
    path = tmp_path / "t.yml"
    path.write_text("k:\n  disposition: inbox\n  stale: yes\n", encoding="utf-8")
    reg.patch_triage(path, "k", {"stale": None})
    assert "stale" not in reg.load_triage(path)["k"].raw


def test_patch_triage_refuses_a_commented_file(tmp_path: Path) -> None:
    path = tmp_path / "t.yml"
    original = "# PRISMA log — do not lose this\nk:\n  disposition: inbox\n"
    path.write_text(original, encoding="utf-8")
    with pytest.raises(reg.RegistryError, match="carries comments"):
        reg.patch_triage(path, "k", {"disposition": "screened"})
    assert path.read_text(encoding="utf-8") == original


def test_patch_triage_refuses_a_nested_value(tmp_path: Path) -> None:
    path = tmp_path / "t.yml"
    path.write_text("k:\n  disposition: inbox\n", encoding="utf-8")
    with pytest.raises(reg.RegistryError, match="scalar"):
        reg.patch_triage(path, "k", {"seeded": ["a", "b"]})  # type: ignore[dict-item]


def test_patch_triage_creates_a_missing_row(tmp_path: Path) -> None:
    path = tmp_path / "t.yml"
    path.write_text("other:\n  disposition: inbox\n", encoding="utf-8")
    reg.patch_triage(path, "k", {"disposition": "screened"})
    assert reg.load_triage(path)["k"].disposition == "screened"
    assert reg.load_triage(path)["other"].disposition == "inbox"


def test_patch_triage_creates_a_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "t.yml"
    reg.patch_triage(path, "k", {"disposition": "screened"})
    assert reg.load_triage(path)["k"].disposition == "screened"


# --- #144: a failed atomic replace must not leave an orphan .tmp ---------------


def test_patch_triage_removes_the_tmp_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`tmp.replace(target)` raising leaves no `.tmp` beside the untouched file."""
    path = tmp_path / "t.yml"
    original = "k:\n  disposition: inbox\n"
    path.write_text(original, encoding="utf-8")

    def _boom(self: Path, _target: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", _boom)
    with pytest.raises(OSError, match="disk full"):
        reg.patch_triage(path, "k", {"disposition": "screened"})

    assert path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "t.yml.tmp").exists()


def test_patch_triage_removes_the_tmp_file_when_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`tmp.write_text` raising is also cleaned up, even though nothing landed."""
    path = tmp_path / "t.yml"
    original = "k:\n  disposition: inbox\n"
    path.write_text(original, encoding="utf-8")

    def _boom(self: Path, *_args: object, **_kwargs: object) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "write_text", _boom)
    with pytest.raises(OSError, match="permission denied"):
        reg.patch_triage(path, "k", {"disposition": "screened"})

    assert path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "t.yml.tmp").exists()


# --- the write must not lose a row a reader cannot see -------------------------
#
# `load_triage` skips a row that is not a mapping, which is right for a reader:
# one malformed row should not make the sidecar unreadable. `patch_triage` used
# to rebuild the file from what that reader returned, so every skipped row was
# deleted on write — the "we round-tripped a human's file and dropped what we did
# not know" failure (#94, #95) reappearing in the writer built to avoid it.


def test_patch_triage_refuses_rather_than_dropping_a_non_mapping_row(
    tmp_path: Path,
) -> None:
    """The required test 2 — the two shorthands a human really writes.

    ``sill1997: include`` is a shorthand disposition and ``igel2023:`` is a
    citekey queued with nothing under it yet. Both are ordinary hand-authoring
    and both are invisible to `load_triage`. The refusal names them, and the file
    is byte-identical afterwards.
    """
    path = tmp_path / "t.yml"
    original = (
        "sill1997: include\n"
        "igel2023:\n"
        "other2020:\n"
        "  disposition: exclude\n"
        "  rationale: out of scope\n"
    )
    path.write_text(original, encoding="utf-8")

    with pytest.raises(reg.RegistryError) as caught:
        reg.patch_triage(path, "other2020", {"disposition": "include"})

    message = str(caught.value)
    assert "not mappings" in message
    assert "sill1997" in message
    assert "igel2023" in message
    assert "'disposition'" in message
    assert path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "t.yml.tmp").exists()


def test_patch_triage_refuses_when_the_row_it_was_asked_to_patch_is_shorthand(
    tmp_path: Path,
) -> None:
    """The same rule applies to the target row: rewriting it is still a rewrite."""
    path = tmp_path / "t.yml"
    original = "k: include\n"
    path.write_text(original, encoding="utf-8")
    with pytest.raises(reg.RegistryError, match="not mappings"):
        reg.patch_triage(path, "k", {"disposition": "screened"})
    assert path.read_text(encoding="utf-8") == original


def test_patch_triage_still_writes_when_every_row_is_a_mapping(
    tmp_path: Path,
) -> None:
    """The refusal is targeted: an all-mapping file patches as before."""
    path = tmp_path / "t.yml"
    path.write_text(
        "a:\n  disposition: inbox\nb:\n  disposition: exclude\n", encoding="utf-8"
    )
    reg.patch_triage(path, "a", {"disposition": "screened"})
    rows = reg.load_triage(path)
    assert rows["a"].disposition == "screened"
    assert rows["b"].disposition == "exclude"


# --- the write must not fabricate an audit trail -------------------------------
#
# Two rows joined by a YAML anchor (`b2021: *shared`) are ONE dict after
# `yaml.safe_load`, so patching either one writes the fields onto both — and
# `safe_dump` re-emits the alias, so the file still looks hand-authored. Through
# `digest extract record` that invents an extraction record for a paper the run
# never touched, at exit 0, in the PRISMA audit trail. Identity is the exact test:
# two rows written out separately are distinct objects even when equal (#143).


ALIASED_TRIAGE = (
    "a2020: &shared\n"
    "  disposition: screened\n"
    "  rationale: same protocol arm\n"
    "b2021: *shared\n"
    "c2022: *shared\n"
    "d2023:\n"
    "  disposition: inbox\n"
)


def test_patch_triage_refuses_rows_that_share_one_mapping(tmp_path: Path) -> None:
    """The refusal names every row in the shared group, and writes nothing."""
    path = tmp_path / "t.yml"
    path.write_text(ALIASED_TRIAGE, encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(reg.RegistryError) as caught:
        reg.patch_triage(path, "a2020", {"extracted": "2026-08-28"})

    message = str(caught.value)
    assert "same mapping" in message
    for citekey in ("a2020", "b2021", "c2022"):
        assert citekey in message
    assert "d2023" not in message
    assert "'extracted'" in message
    assert path.read_bytes() == before
    assert not (tmp_path / "t.yml.tmp").exists()


def test_patch_triage_refuses_a_shared_mapping_it_was_not_asked_to_patch(
    tmp_path: Path,
) -> None:
    """The sharing is the hazard, not the target: patching `d2023` refuses too.

    Rewriting the file at all re-emits the aliased group, and a later patch of
    that group would fabricate. The whole file is refused, as with comments.
    """
    path = tmp_path / "t.yml"
    path.write_text(ALIASED_TRIAGE, encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(reg.RegistryError, match="same mapping"):
        reg.patch_triage(path, "d2023", {"extracted": "2026-08-28"})
    assert path.read_bytes() == before


def test_patch_triage_does_not_refuse_rows_that_merely_look_alike(
    tmp_path: Path,
) -> None:
    """The over-correction guard: equal content is not shared content.

    The check is object identity, which cannot false-positive — two rows written
    out separately are distinct objects however identical they read.
    """
    path = tmp_path / "t.yml"
    path.write_text(
        "a2020:\n  disposition: screened\n  rationale: same protocol arm\n"
        "b2021:\n  disposition: screened\n  rationale: same protocol arm\n",
        encoding="utf-8",
    )
    reg.patch_triage(path, "a2020", {"extracted": "2026-08-28"})
    rows = reg.load_triage(path)
    assert rows["a2020"].raw["extracted"] == "2026-08-28"
    # The negative this guard exists for, from the other side: the lookalike row
    # must not acquire the field.
    assert "extracted" not in rows["b2021"].raw


def test_patch_triage_refuses_blank_file_without_choking_on_composing_it(
    tmp_path: Path,
) -> None:
    """A blank *existing* file composes to ``None`` — not a mapping to walk."""
    path = tmp_path / "t.yml"
    path.write_text("", encoding="utf-8")
    reg.patch_triage(path, "k", {"disposition": "screened"})
    assert reg.load_triage(path)["k"].disposition == "screened"


# --- #143: a row anchored at the top level, aliased *inside* another row's ----
# nested value. The bd60859 guard only buckets top-level rows by id() and does
# not walk into a row's nested values, so this shape slipped through: patching
# `a2020` silently wrote `extracted`/`extraction-cells` into `b2021.parent` too,
# and `patch_triage` returned exit 0 as a clean success.

NESTED_ALIAS_TRIAGE = (
    "a2020: &shared\n"
    "  disposition: screened\n"
    "  rationale: superseded by the 2023 revision\n"
    "b2021:\n"
    "  disposition: screened\n"
    "  parent: *shared\n"
)


def test_patch_triage_refuses_a_row_aliased_inside_another_rows_nested_value(
    tmp_path: Path,
) -> None:
    """The issue's exact repro: `a2020` reachable both at top level and nested."""
    path = tmp_path / "t.yml"
    path.write_text(NESTED_ALIAS_TRIAGE, encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(reg.RegistryError) as caught:
        reg.patch_triage(
            path, "a2020", {"extracted": "2026-08-28", "extraction-cells": 8}
        )

    message = str(caught.value)
    assert "a2020" in message
    assert "b2021" in message
    assert "'extracted'" in message
    assert "'extraction-cells'" in message
    # No write happened at all — b2021.parent must not have gained the fields.
    assert path.read_bytes() == before
    assert not (tmp_path / "t.yml.tmp").exists()


def test_patch_triage_refuses_a_row_aliased_inside_a_list(tmp_path: Path) -> None:
    """The same nested-alias hazard, one level deeper: inside a sequence."""
    path = tmp_path / "t.yml"
    path.write_text(
        "a2020: &shared\n"
        "  disposition: screened\n"
        "b2021:\n"
        "  disposition: screened\n"
        "  related:\n"
        "    - *shared\n",
        encoding="utf-8",
    )
    before = path.read_bytes()

    with pytest.raises(reg.RegistryError) as caught:
        reg.patch_triage(path, "a2020", {"extracted": "2026-08-28"})

    message = str(caught.value)
    assert "a2020" in message
    assert "b2021" in message
    assert path.read_bytes() == before


def test_patch_triage_refuses_a_self_referential_anchor_without_crashing(
    tmp_path: Path,
) -> None:
    """A row aliased into its own nested value makes the node graph cyclic.

    ``&anchor`` inside the row it names, aliased back into itself
    (``a2020: &shared {..., self: *shared}``), is a legitimate composed shape
    — a plausible typo, not malformed YAML — and must be refused like any
    other anchor reuse, not crash with a ``RecursionError``.
    """
    path = tmp_path / "t.yml"
    path.write_text(
        "a2020: &shared\n  disposition: screened\n  self: *shared\n",
        encoding="utf-8",
    )
    before = path.read_bytes()

    with pytest.raises(reg.RegistryError) as caught:
        reg.patch_triage(path, "a2020", {"extracted": "2026-08-28"})

    assert "a2020" in str(caught.value)
    assert path.read_bytes() == before


def test_patch_triage_refuses_a_merge_key_reuse(tmp_path: Path) -> None:
    """A merge key (`<<: *base`) is refused by name, not silently expanded."""
    path = tmp_path / "t.yml"
    path.write_text(
        "base: &base\n"
        "  disposition: screened\n"
        "a2020:\n"
        "  <<: *base\n"
        "  rationale: templated\n",
        encoding="utf-8",
    )
    before = path.read_bytes()

    with pytest.raises(reg.RegistryError) as caught:
        reg.patch_triage(path, "a2020", {"extracted": "2026-08-28"})

    message = str(caught.value)
    assert "a2020" in message
    assert "base" in message
    assert "anchor" in message
    assert path.read_bytes() == before


def test_patch_triage_refuses_a_scalar_anchor_reuse(tmp_path: Path) -> None:
    """A scalar anchor (`rationale: *reason`) reused across rows is refused."""
    path = tmp_path / "t.yml"
    path.write_text(
        "a2020:\n"
        "  disposition: screened\n"
        "  rationale: &reason superseded by the 2023 revision\n"
        "b2021:\n"
        "  disposition: screened\n"
        "  rationale: *reason\n",
        encoding="utf-8",
    )
    before = path.read_bytes()

    with pytest.raises(reg.RegistryError) as caught:
        reg.patch_triage(path, "a2020", {"extracted": "2026-08-28"})

    message = str(caught.value)
    assert "a2020" in message
    assert "b2021" in message
    assert "anchor" in message
    assert path.read_bytes() == before


def test_patch_triage_refuses_a_scalar_anchor_reused_within_one_row(
    tmp_path: Path,
) -> None:
    """The same posture applies with no cross-row leak at all: still refused.

    Per #143's acceptance criteria, a merge key or scalar anchor is "either
    survives or is refused — not silently expanded" unconditionally, even when
    every alias of the anchor sits inside the single row being patched.
    """
    path = tmp_path / "t.yml"
    path.write_text(
        "a2020:\n"
        "  disposition: screened\n"
        "  rationale: &reason same story\n"
        "  note: *reason\n",
        encoding="utf-8",
    )
    before = path.read_bytes()

    with pytest.raises(reg.RegistryError) as caught:
        reg.patch_triage(path, "a2020", {"extracted": "2026-08-28"})

    message = str(caught.value)
    assert "a2020" in message
    assert "anchor" in message
    assert path.read_bytes() == before


def test_patch_triage_on_an_accepted_sidecar_changes_only_the_named_row(
    tmp_path: Path,
) -> None:
    """A negative test on a plain, alias-free sidecar with several rows."""
    path = tmp_path / "t.yml"
    path.write_text(
        "a2020:\n  disposition: screened\n"
        "b2021:\n  disposition: exclude\n"
        "c2022:\n  disposition: inbox\n",
        encoding="utf-8",
    )
    reg.patch_triage(path, "b2021", {"extracted": "2026-08-28", "extraction-cells": 8})
    rows = reg.load_triage(path)
    assert rows["b2021"].raw["extracted"] == "2026-08-28"
    assert rows["b2021"].raw["extraction-cells"] == 8
    for citekey in ("a2020", "c2022"):
        assert "extracted" not in rows[citekey].raw
        assert "extraction-cells" not in rows[citekey].raw


def test_patch_triage_keeps_a_non_string_citekey_addressable(tmp_path: Path) -> None:
    """A YAML key that is not a string (``2020:``) is still a row, not a casualty."""
    path = tmp_path / "t.yml"
    path.write_text("2020:\n  disposition: inbox\n", encoding="utf-8")
    reg.patch_triage(path, "k", {"disposition": "screened"})
    rows = reg.load_triage(path)
    assert rows["2020"].disposition == "inbox"
    assert rows["k"].disposition == "screened"


def test_triage_mapping_is_public_and_returns_the_raw_rows() -> None:
    from pathlib import Path

    assert reg.triage_mapping(Path("triage.yml"), "a: include\nb: {x: 1}\n") == {
        "a": "include",
        "b": {"x": 1},
    }
