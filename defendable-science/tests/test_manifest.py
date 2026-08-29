"""Tests for the ``datasets.yml`` manifest tooling (defendable-science#2)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from defendable_science.cli import app
from defendable_science.dataset import manifest as m

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

_HEX = "a" * 64

_VALID_YAML = f"""
mirror:
  rclone_remote: mystore
  base_path: proj/datasets
  hash: md5
datasets:
  - id: example-tabular
    version: "1.0.0"
    tier: B
    license: CC-BY-4.0
    redistributable: true
    access: open
    pid: doi:10.1234/abcd
    files:
      - path: data/example.parquet
        sha256: {_HEX}
        size: 12345
    source: https://example.org/example.parquet
    retrieval:
      kind: http
      url: https://example.org/example.parquet
    datasheet: datasheets/example.md
    citation:
      creator: A. Author
      title: Example
      publisher: Example Org
      publicationYear: 2024
      resourceType: Dataset
      identifier: doi:10.1234/abcd
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "datasets.yml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_valid_manifest(tmp_path: Path) -> None:
    manifest = m.load(_write(tmp_path, _VALID_YAML))
    assert manifest.mirror is not None
    assert manifest.mirror.rclone_remote == "mystore"
    assert len(manifest.datasets) == 1
    entry = manifest.datasets[0]
    assert entry.id == "example-tabular"
    assert entry.redistributable is True
    assert entry.files[0].sha256 == _HEX
    assert entry.retrieval is not None
    assert entry.retrieval.kind == "http"


def test_load_missing_file_raises() -> None:
    with pytest.raises(m.ManifestError, match="no such file"):
        m.load("does-not-exist.yml")


def test_load_malformed_names_the_entry(tmp_path: Path) -> None:
    bad = "datasets:\n  - version: '1'\n"  # entry has no id
    with pytest.raises(m.ManifestError, match=r"datasets\[0\].*'id'"):
        m.load(_write(tmp_path, bad))


def test_validate_clean_manifest_ok(tmp_path: Path) -> None:
    report = m.validate(m.load(_write(tmp_path, _VALID_YAML)))
    assert report.ok
    assert report.errors == []


def test_validate_accumulates_all_errors() -> None:
    entry = m.DatasetEntry(id="bad", files=[m.FileRef(path="x", sha256="nothex")])
    report = m.validate(m.Manifest(datasets=[entry]))
    assert not report.ok
    joined = "\n".join(report.errors)
    for fieldname in ("version", "tier", "license", "redistributable", "access"):
        assert f"entry 'bad': {fieldname}" in joined
    assert "files[0].sha256" in joined


def test_validate_tier_b_requires_retrieval() -> None:
    entry = m.DatasetEntry(
        id="b",
        version="1",
        tier="B",
        license="MIT",
        redistributable=True,
        access="open",
        files=[m.FileRef(path="f", sha256=_HEX)],
        datasheet="ds.md",
    )
    report = m.validate(m.Manifest(datasets=[entry]))
    assert any("source/retrieval" in e for e in report.errors)


def test_validate_tier_a_consistency() -> None:
    common = {
        "version": "1",
        "tier": "A",
        "license": "MIT",
        "files": [m.FileRef(path="f", sha256=_HEX)],
        "datasheet": "ds.md",
    }
    gated = m.DatasetEntry(id="g", access="gated", redistributable=True, **common)  # type: ignore[arg-type]
    nonredist = m.DatasetEntry(id="n", access="open", redistributable=False, **common)  # type: ignore[arg-type]
    report = m.validate(m.Manifest(datasets=[gated, nonredist]))
    assert any("tier A cannot be access: gated" in e for e in report.errors)
    assert any("tier A requires redistributable: true" in e for e in report.errors)


def test_validate_duplicate_id_is_error() -> None:
    entry = m.DatasetEntry(
        id="dup",
        version="1",
        tier="B",
        license="MIT",
        redistributable=True,
        access="open",
        files=[m.FileRef(path="f", sha256=_HEX)],
        datasheet="ds.md",
        retrieval=m.Retrieval(kind="http", url="u"),
    )
    report = m.validate(m.Manifest(datasets=[entry, entry]))
    assert any("duplicated" in e for e in report.errors)


def test_validate_na_datasheet_is_warning_not_error() -> None:
    entry = m.DatasetEntry(
        id="c",
        version="1",
        tier="C",
        license="proprietary",
        redistributable=False,
        access="gated",
        files=[m.FileRef(path="f", sha256=_HEX)],
        datasheet="N/A + not yet written",
        instructions="email the authors",
    )
    report = m.validate(m.Manifest(datasets=[entry]))
    assert report.ok  # N/A is a warning, not a hard error
    assert any("datasheet" in w for w in report.warnings)


def test_croissant_round_trip_preserves_core(tmp_path: Path) -> None:
    entry = m.load(_write(tmp_path, _VALID_YAML)).datasets[0]
    doc = m.croissant_for(entry)
    assert doc["@type"] == "Dataset"
    assert doc["distribution"][0]["contentUrl"] == "data/example.parquet"
    assert doc["distribution"][0]["sha256"] == _HEX
    back = m.entry_from_croissant(doc)
    assert back.id == entry.id
    assert back.version == entry.version
    assert back.license == entry.license
    assert back.files[0].sha256 == entry.files[0].sha256


def test_entry_from_croissant_flags_human_todo() -> None:
    draft = m.entry_from_croissant(
        {"name": "x", "distribution": [{"contentUrl": "f", "sha256": _HEX}]}
    )
    assert draft.tier is None
    assert draft.datasheet is None
    assert draft.sensitivity is None


def test_entry_from_croissant_without_name_raises() -> None:
    with pytest.raises(m.ManifestError, match="no 'name'"):
        m.entry_from_croissant({"description": "no name here"})


def test_entry_from_croissant_non_string_name_raises() -> None:
    """Deliberate tightening (#169), not an accidental regression.

    Pre-fix, ``{"name": 2024}`` silently minted the id ``"2024"`` via
    ``str()`` coercion. ``name``/``alternateName`` are held to ``str`` (unlike
    the five ``Any``-typed scalars) because the entry id is derived from them,
    and coercing a non-string into a plausible-looking id is the
    silently-wrong-value failure this model exists to reject.
    """
    with pytest.raises(m.ManifestError, match=r"croissant: name: .*valid string"):
        m.entry_from_croissant({"name": 2024})


def test_ingest_a_top_level_array_exits_1_not_a_traceback(tmp_path: Path) -> None:
    """Defect 6: AttributeError escaped cli.py's except tuple as a traceback."""
    croissant = tmp_path / "x.json"
    croissant.write_text("[1, 2]", encoding="utf-8")

    result = runner.invoke(app, ["dataset", "ingest", str(croissant)])

    assert result.exit_code == 1
    assert "ingest failed" in result.output
    assert "croissant" in result.output
    assert not isinstance(result.exception, AttributeError)


def test_entry_from_croissant_rejects_a_non_mapping_document() -> None:
    with pytest.raises(m.ManifestError, match=r"croissant: <root>: .*valid dictionary"):
        m.entry_from_croissant([1, 2])


# --- CLI ---------------------------------------------------------------------


def test_cli_validate_ok(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID_YAML)
    result = runner.invoke(app, ["dataset", "validate", str(path)])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["ok"] is True


def test_cli_validate_reports_errors_and_exits_nonzero(tmp_path: Path) -> None:
    path = _write(tmp_path, "datasets:\n  - id: bad\n")
    result = runner.invoke(app, ["dataset", "validate", str(path)])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_cli_emit_by_id(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID_YAML)
    result = runner.invoke(
        app, ["dataset", "emit", "example-tabular", "--manifest", str(path)]
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["@type"] == "Dataset"


def test_cli_emit_unknown_id_exits_1(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID_YAML)
    result = runner.invoke(app, ["dataset", "emit", "nope", "--manifest", str(path)])
    assert result.exit_code == 1


def test_cli_ingest_emits_draft(tmp_path: Path) -> None:
    croissant = tmp_path / "c.json"
    croissant.write_text(
        json.dumps(
            {"name": "ingested", "distribution": [{"contentUrl": "f", "sha256": _HEX}]}
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["dataset", "ingest", str(croissant)])
    assert result.exit_code == 0
    draft = json.loads(result.stdout)
    assert draft["id"] == "ingested"
    assert "tier" in draft["_needs_human"]


# --- decode / validate / croissant branch coverage (#16 sweep) --------------


def test_load_empty_file(tmp_path: Path) -> None:
    assert m.load(_write(tmp_path, "")).datasets == []


def test_load_top_not_mapping(tmp_path: Path) -> None:
    with pytest.raises(m.ManifestError, match="mapping at the top level"):
        m.load(_write(tmp_path, "- a\n- b\n"))


def test_load_datasets_not_list(tmp_path: Path) -> None:
    with pytest.raises(m.ManifestError, match="'datasets' must be a list"):
        m.load(_write(tmp_path, "datasets:\n  key: value\n"))


def test_load_mirror_not_mapping(tmp_path: Path) -> None:
    with pytest.raises(m.ManifestError, match="'mirror' must be a mapping"):
        m.load(_write(tmp_path, "mirror: nope\ndatasets: []\n"))


def test_decode_entry_not_mapping(tmp_path: Path) -> None:
    with pytest.raises(m.ManifestError, match="entry must be a mapping"):
        m.load(_write(tmp_path, "datasets:\n  - just-a-string\n"))


def test_decode_file_not_mapping(tmp_path: Path) -> None:
    text = "datasets:\n  - id: x\n    files:\n      - astring\n"
    with pytest.raises(m.ManifestError, match="each file must be a mapping"):
        m.load(_write(tmp_path, text))


def test_decode_file_missing_key(tmp_path: Path) -> None:
    text = "datasets:\n  - id: x\n    files:\n      - path: p\n"
    with pytest.raises(m.ManifestError, match="missing required key"):
        m.load(_write(tmp_path, text))


def test_decode_retrieval_not_mapping(tmp_path: Path) -> None:
    text = "datasets:\n  - id: x\n    retrieval: nope\n"
    with pytest.raises(m.ManifestError, match="'retrieval' must be a mapping"):
        m.load(_write(tmp_path, text))


def test_decode_citation_not_mapping(tmp_path: Path) -> None:
    text = "datasets:\n  - id: x\n    citation: nope\n"
    with pytest.raises(m.ManifestError, match="'citation' must be a mapping"):
        m.load(_write(tmp_path, text))


def test_validate_conditional_and_shape_errors() -> None:
    entry = m.DatasetEntry(
        id="e",
        version="1",
        tier="C",
        license="X",
        redistributable=False,
        access="gated",
        files=[m.FileRef(path="", sha256=_HEX)],
        datasheet="d.md",
        retrieval=m.Retrieval(kind="bogus"),
        sensitivity="huge",
    )
    errs = "\n".join(m.validate(m.Manifest(datasets=[entry])).errors)
    assert "files[0].path" in errs
    assert "retrieval.kind" in errs
    assert "sensitivity" in errs
    assert "instructions" in errs  # Tier C requires instructions


def test_croissant_optional_fields_and_no_size() -> None:
    entry = m.DatasetEntry(
        id="e",
        version="2.0",
        license="MIT",
        description="a desc",
        pid="doi:10.1/x",
        files=[m.FileRef(path="f", sha256=_HEX)],  # no size
        citation=m.Citation(creator="A", title="T", publication_year=2020),
    )
    doc = m.croissant_for(entry)
    assert doc["description"] == "a desc"
    assert doc["identifier"] == "doi:10.1/x"
    assert "citeAs" in doc
    assert "contentSize" not in doc["distribution"][0]


def test_entry_from_croissant_no_distribution() -> None:
    draft = m.entry_from_croissant({"name": "x"})
    assert draft.files == []


def test_validate_incomplete_citation_warns() -> None:
    entry = m.DatasetEntry(
        id="e",
        version="1",
        tier="B",
        license="MIT",
        redistributable=True,
        access="open",
        files=[m.FileRef(path="f", sha256=_HEX)],
        datasheet="d.md",
        retrieval=m.Retrieval(kind="http", url="u"),
        citation=m.Citation(creator="A"),
    )
    report = m.validate(m.Manifest(datasets=[entry]))
    assert any("citation" in w for w in report.warnings)


def test_entry_from_croissant_valid_distribution() -> None:
    draft = m.entry_from_croissant(
        {
            "name": "x",
            "citeAs": "Author (2020). X.",
            "distribution": [
                {"contentUrl": "u2", "sha256": _HEX, "contentSize": 5},
            ],
        }
    )
    assert [f.path for f in draft.files] == ["u2"]
    assert draft.files[0].size == 5
    assert draft.citation is not None


def test_entry_from_croissant_non_dict_file_object_raises() -> None:
    with pytest.raises(m.ManifestError, match=r"distribution\[0\].*must be a mapping"):
        m.entry_from_croissant({"name": "x", "distribution": ["not-a-dict"]})


def test_entry_from_croissant_file_object_missing_sha_raises() -> None:
    # A malformed FileObject is surfaced, not silently dropped.
    with pytest.raises(m.ManifestError, match=r"distribution\[0\].*contentUrl"):
        m.entry_from_croissant({"name": "x", "distribution": [{"contentUrl": "u1"}]})


def test_entry_from_croissant_file_object_missing_url_raises() -> None:
    with pytest.raises(m.ManifestError, match=r"distribution\[0\]"):
        m.entry_from_croissant({"name": "x", "distribution": [{"sha256": _HEX}]})


def test_entry_from_croissant_numeric_string_content_size_accepted() -> None:
    draft = m.entry_from_croissant(
        {
            "name": "x",
            "distribution": [{"contentUrl": "u", "sha256": _HEX, "contentSize": "42"}],
        }
    )
    assert draft.files[0].size == 42


def test_entry_from_croissant_non_numeric_content_size_raises() -> None:
    with pytest.raises(m.ManifestError, match="'contentSize' must be an integer"):
        m.entry_from_croissant(
            {
                "name": "x",
                "distribution": [
                    {"contentUrl": "u", "sha256": _HEX, "contentSize": "big"}
                ],
            }
        )


def test_croissant_minimal_entry_omits_absent_fields() -> None:
    doc = m.croissant_for(m.DatasetEntry(id="bare"))
    assert doc["name"] == "bare"
    for absent in ("version", "license", "description", "identifier", "distribution"):
        assert absent not in doc


# --- input hardening + round-trip fidelity (defendable-science#31) ---------------


def test_decode_file_non_numeric_size_is_clean_error(tmp_path: Path) -> None:
    text = (
        "datasets:\n  - id: x\n    files:\n"
        f"      - path: f\n        sha256: {_HEX}\n        size: not-a-number\n"
    )
    with pytest.raises(m.ManifestError, match="'size' must be an integer"):
        m.load(_write(tmp_path, text))


def test_decode_citation_non_numeric_year_is_clean_error(tmp_path: Path) -> None:
    text = (
        "datasets:\n  - id: x\n    citation:\n"
        "      title: T\n      publicationYear: last-year\n"
    )
    with pytest.raises(m.ManifestError, match="'publicationYear' must be an integer"):
        m.load(_write(tmp_path, text))


def test_croissant_round_trip_preserves_id_and_title() -> None:
    entry = m.DatasetEntry(
        id="stable-slug",
        version="1.0",
        license="MIT",
        title="A Human Title",
        files=[m.FileRef(path="f", sha256=_HEX)],
        citation=m.Citation(title="A Human Title", identifier="doi:10.1/x"),
        pid="doi:10.1/x",
    )
    doc = m.croissant_for(entry)
    assert doc["name"] == "A Human Title"
    assert doc["alternateName"] == "stable-slug"  # slug preserved for round-trip
    back = m.entry_from_croissant(doc)
    assert back.id == "stable-slug"  # id is NOT collapsed onto the human name
    assert back.title == "A Human Title"
    assert back.citation is not None
    assert back.citation.identifier == "doi:10.1/x"


def test_croissant_no_alternate_name_when_title_equals_id() -> None:
    doc = m.croissant_for(m.DatasetEntry(id="same", title="same"))
    assert "alternateName" not in doc
    assert m.entry_from_croissant(doc).id == "same"
