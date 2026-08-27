"""Tests for the literature registry read model + surgical writers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from defendable_science.literature import registry as reg

if TYPE_CHECKING:
    from pathlib import Path


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
    with pytest.raises(reg.RegistryError, match="expected a JSON array"):
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
