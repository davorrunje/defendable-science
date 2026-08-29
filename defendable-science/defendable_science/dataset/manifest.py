"""``datasets.yml`` manifest tooling — loader, validator and Croissant interop.

Implements the metadata half of the ``dataset`` skill (defendable-science#2): parse
``datasets.yml`` into typed records, validate the base asset record plus
tier-conditional required fields, and round-trip
[Croissant](https://mlcommons.org/croissant/) / schema.org ``Dataset`` JSON-LD.

This module is **metadata only** — it never opens data files, computes SHA-256,
touches the network, or runs ``rclone``. Byte handling lives in
:mod:`defendable_science.dataset.retrieval` (defendable-science#3). Design:
``docs/design/proposals/dataset-manifest-tooling.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import Field

from defendable_science.core.models import ExternalModel, parse_obj

#: A file checksum value: 64 lowercase hex chars, optionally ``sha256:``-prefixed.
SHA256_RE = re.compile(r"^(sha256:)?[0-9a-f]{64}$")

TIERS = frozenset({"A", "B", "C"})
ACCESS = frozenset({"open", "gated"})
RETRIEVAL_KINDS = frozenset({"http", "doi", "openml", "git-lfs", "manual"})
SENSITIVITY_VALUES = frozenset({"none", "pii", "confidential"})


class ManifestError(ValueError):
    """Raised when a ``datasets.yml`` file cannot be structurally decoded."""


@dataclass
class FileRef:
    """One file belonging to a dataset entry.

    :param path: Repo- or cache-relative path to the file.
    :param sha256: Authoritative checksum (bare 64-hex or ``sha256:``-prefixed).
    :param size: Optional byte size.
    """

    path: str
    sha256: str
    size: int | None = None


@dataclass
class Retrieval:
    """A Tier-B retrieval recipe.

    :param kind: One of :data:`RETRIEVAL_KINDS`.
    :param url: The source locator (``http(s)``/``ftp``/``sftp``/``doi:`` …).
    """

    kind: str
    url: str | None = None


@dataclass
class Citation:
    """The DataCite six-mandatory tuple for a citable dataset.

    All fields are optional at the record level; :func:`validate` warns (never
    errors) when the tuple is incomplete, since a citable record may not yet exist.

    :param identifier: DOI / persistent identifier.
    :param creator: Dataset creator(s).
    :param title: Dataset title.
    :param publisher: Publishing entity.
    :param publication_year: Year of publication.
    :param resource_type: DataCite resource type (``Dataset``).
    """

    identifier: str | None = None
    creator: str | None = None
    title: str | None = None
    publisher: str | None = None
    publication_year: int | None = None
    resource_type: str | None = None

    def is_complete(self) -> bool:
        """Return whether all six DataCite-mandatory fields are populated."""
        return all(
            value is not None
            for value in (
                self.identifier,
                self.creator,
                self.title,
                self.publisher,
                self.publication_year,
                self.resource_type,
            )
        )


@dataclass
class DatasetEntry:
    """A single dataset registry entry (the superset source of truth).

    :param id: Stable slug, unique within the registry.
    :param version: Dataset version string.
    :param tier: Storage tier (``A`` / ``B`` / ``C``).
    :param license: SPDX id or explicit terms + URL.
    :param redistributable: Whether the license permits redistribution.
    :param access: ``open`` or ``gated``.
    :param files: The dataset's files.
    :param datasheet: Path/URL to the Gebru datasheet, or ``"N/A + <reason>"``.
    :param source: Tier-B canonical source URL.
    :param retrieval: Tier-B retrieval recipe.
    :param instructions: Tier-C acquisition instructions.
    :param sensitivity: ``none`` / ``pii`` / ``confidential``.
    :param pid: Persistent identifier (e.g. ``doi:10.xxxx/…``).
    :param title: Human-readable title (defaults to `id` on emit).
    :param description: Free-text description.
    :param citation: DataCite citation tuple.
    """

    id: str
    version: str | None = None
    tier: str | None = None
    license: str | None = None
    redistributable: bool | None = None
    access: str | None = None
    files: list[FileRef] = field(default_factory=list)
    datasheet: str | None = None
    source: str | None = None
    retrieval: Retrieval | None = None
    instructions: str | None = None
    sensitivity: str | None = None
    pid: str | None = None
    title: str | None = None
    description: str | None = None
    citation: Citation | None = None


@dataclass
class Mirror:
    """The private-mirror binding block.

    :param rclone_remote: Logical rclone remote name (credentials live elsewhere).
    :param base_path: Base path under the remote.
    :param hash: rclone transport hash (never authoritative).
    """

    rclone_remote: str | None = None
    base_path: str | None = None
    hash: str | None = None


@dataclass
class Manifest:
    """A parsed ``datasets.yml`` registry.

    :param mirror: Optional mirror binding.
    :param datasets: The dataset entries.
    """

    mirror: Mirror | None = None
    datasets: list[DatasetEntry] = field(default_factory=list)


@dataclass
class ValidationReport:
    """The outcome of :func:`validate`.

    :param errors: Hard violations, formatted ``entry '<id>': <field>: <reason>``.
    :param warnings: Soft issues (incomplete citation, ``N/A`` datasheet).
    """

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return whether the manifest has no hard errors."""
        return not self.errors


# --- loading ----------------------------------------------------------------


def _opt_str(value: Any) -> str | None:
    """Coerce a scalar to ``str``, preserving ``None``."""
    return None if value is None else str(value)


def _opt_bool(value: Any) -> bool | None:
    """Return `value` if it is a real ``bool``, else ``None``.

    A non-bool (e.g. the string ``"true"``) is left as ``None`` so
    :func:`validate` can flag the type error rather than silently coercing.
    """
    return value if isinstance(value, bool) else None


def _int_or_error(value: Any, where: str, fieldname: str) -> int | None:
    """Coerce an optional integer field, raising :class:`ManifestError`.

    Accepts real ints and numeric strings (``int(value)``); ``None`` passes
    through. A non-numeric value is a clean error rather than a silent drop.

    :param value: The raw value to coerce.
    :param where: Location prefix for the error message.
    :param fieldname: The field name to name in the error message.
    :returns: The coerced integer, or ``None`` when `value` is ``None``.
    :raises ManifestError: If `value` is non-``None`` and not integer-coercible.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError) as exc:
        raise ManifestError(
            f"{where}: '{fieldname}' must be an integer, got {value!r}"
        ) from exc


def _decode_file_ref(raw: Any, where: str) -> FileRef:
    """Decode one ``files[]`` element, raising :class:`ManifestError` on shape."""
    if not isinstance(raw, dict):
        raise ManifestError(f"{where}: each file must be a mapping")
    try:
        path = str(raw["path"])
        sha256 = str(raw["sha256"])
    except KeyError as exc:
        raise ManifestError(f"{where}: file missing required key {exc}") from exc
    return FileRef(
        path=path, sha256=sha256, size=_int_or_error(raw.get("size"), where, "size")
    )


def _decode_retrieval(raw: Any, where: str) -> Retrieval:
    """Decode a ``retrieval`` block."""
    if not isinstance(raw, dict):
        raise ManifestError(f"{where}: 'retrieval' must be a mapping")
    return Retrieval(
        kind=str(raw.get("kind", "")),
        url=_opt_str(raw.get("url")),
    )


def _decode_citation(raw: Any, where: str) -> Citation:
    """Decode a ``citation`` block (DataCite tuple)."""
    if not isinstance(raw, dict):
        raise ManifestError(f"{where}: 'citation' must be a mapping")
    year = raw.get("publicationYear", raw.get("publication_year"))
    year_int = _int_or_error(year, where, "publicationYear")
    return Citation(
        identifier=_opt_str(raw.get("identifier")),
        creator=_opt_str(raw.get("creator")),
        title=_opt_str(raw.get("title")),
        publisher=_opt_str(raw.get("publisher")),
        publication_year=year_int,
        resource_type=_opt_str(raw.get("resourceType", raw.get("resource_type"))),
    )


def _decode_entry(raw: Any, index: int) -> DatasetEntry:
    """Decode one ``datasets[]`` element into a :class:`DatasetEntry`."""
    where = f"datasets[{index}]"
    if not isinstance(raw, dict):
        raise ManifestError(f"{where}: entry must be a mapping")
    if "id" not in raw:
        raise ManifestError(f"{where}: entry missing required key 'id'")
    entry_id = str(raw["id"])
    where = f"entry '{entry_id}'"

    retrieval = None
    if raw.get("retrieval") is not None:
        retrieval = _decode_retrieval(raw["retrieval"], where)
    citation = None
    if raw.get("citation") is not None:
        citation = _decode_citation(raw["citation"], where)

    return DatasetEntry(
        id=entry_id,
        version=_opt_str(raw.get("version")),
        tier=_opt_str(raw.get("tier")),
        license=_opt_str(raw.get("license")),
        redistributable=_opt_bool(raw.get("redistributable")),
        access=_opt_str(raw.get("access")),
        files=[
            _decode_file_ref(f, f"{where}: files[{i}]")
            for i, f in enumerate(raw.get("files") or [])
        ],
        datasheet=_opt_str(raw.get("datasheet")),
        source=_opt_str(raw.get("source")),
        retrieval=retrieval,
        instructions=_opt_str(raw.get("instructions")),
        sensitivity=_opt_str(raw.get("sensitivity")),
        pid=_opt_str(raw.get("pid")),
        title=_opt_str(raw.get("title")),
        description=_opt_str(raw.get("description")),
        citation=citation,
    )


def load_text(text: str, path: str | Path = "datasets.yml") -> Manifest:
    """Parse ``datasets.yml`` from text into a :class:`Manifest`.

    :param text: The YAML text to parse.
    :param path: Path to the manifest file (for error messages).
    :returns: The decoded manifest.
    :raises ManifestError: If the text is not a YAML mapping, or an entry is
        structurally malformed. The message names the offending entry.
    """
    manifest_path = Path(path)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestError(f"{manifest_path}: invalid YAML: {exc}") from exc
    if data is None:
        return Manifest()
    if not isinstance(data, dict):
        raise ManifestError(f"{manifest_path}: expected a mapping at the top level")

    mirror = None
    if (mraw := data.get("mirror")) is not None:
        if not isinstance(mraw, dict):
            raise ManifestError(f"{manifest_path}: 'mirror' must be a mapping")
        mirror = Mirror(
            rclone_remote=_opt_str(mraw.get("rclone_remote")),
            base_path=_opt_str(mraw.get("base_path")),
            hash=_opt_str(mraw.get("hash")),
        )

    datasets_raw = data.get("datasets") or []
    if not isinstance(datasets_raw, list):
        raise ManifestError(f"{manifest_path}: 'datasets' must be a list")
    return Manifest(
        mirror=mirror,
        datasets=[_decode_entry(entry, i) for i, entry in enumerate(datasets_raw)],
    )


def load(path: str | Path = "datasets.yml") -> Manifest:
    """Parse ``datasets.yml`` into a :class:`Manifest`.

    :param path: Path to the manifest file.
    :returns: The decoded manifest.
    :raises ManifestError: If the file is missing, is not a YAML mapping, or an
        entry is structurally malformed. The message names the offending entry.
    """
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise ManifestError(f"{manifest_path}: no such file")
    return load_text(manifest_path.read_text(encoding="utf-8"), manifest_path)


# --- validation -------------------------------------------------------------


def _err(report: ValidationReport, entry_id: str, fieldname: str, reason: str) -> None:
    """Append a hard error, formatted ``entry '<id>': <field>: <reason>``."""
    report.errors.append(f"entry '{entry_id}': {fieldname}: {reason}")


def _warn(report: ValidationReport, entry_id: str, fieldname: str, reason: str) -> None:
    """Append a soft warning, formatted ``entry '<id>': <field>: <reason>``."""
    report.warnings.append(f"entry '{entry_id}': {fieldname}: {reason}")


def _validate_required(entry: DatasetEntry, report: ValidationReport) -> None:
    """Validate the always-required core fields."""
    eid = entry.id
    if not entry.version:
        _err(report, eid, "version", "required")
    if entry.tier not in TIERS:
        _err(report, eid, "tier", f"must be one of {sorted(TIERS)}, got {entry.tier!r}")
    if not entry.license:
        _err(report, eid, "license", "required (SPDX id or explicit terms + URL)")
    if entry.redistributable is None:
        _err(report, eid, "redistributable", "required boolean")
    if entry.access not in ACCESS:
        _err(
            report,
            eid,
            "access",
            f"must be one of {sorted(ACCESS)}, got {entry.access!r}",
        )


def _validate_files(entry: DatasetEntry, report: ValidationReport) -> None:
    """Validate ``files[]`` presence, paths, and checksum shape."""
    if not entry.files:
        _err(report, entry.id, "files", "at least one file is required")
    for i, ref in enumerate(entry.files):
        if not ref.path:
            _err(report, entry.id, f"files[{i}].path", "required")
        if not SHA256_RE.match(ref.sha256):
            _err(
                report,
                entry.id,
                f"files[{i}].sha256",
                "must be 64 hex (optional 'sha256:')",
            )


def _validate_datasheet(entry: DatasetEntry, report: ValidationReport) -> None:
    """Require a datasheet; flag an ``N/A`` placeholder as a completeness gap."""
    if not entry.datasheet:
        _err(report, entry.id, "datasheet", "required (path/URL, or 'N/A + <reason>')")
    elif entry.datasheet.strip().upper().startswith("N/A"):
        _warn(report, entry.id, "datasheet", "placeholder 'N/A' — a completeness gap")


def _validate_conditional(entry: DatasetEntry, report: ValidationReport) -> None:
    """Validate tier-conditional required fields and enum values."""
    eid = entry.id
    if entry.tier == "B" and not (entry.source or entry.retrieval):
        _err(report, eid, "source/retrieval", "required for Tier B")
    if entry.retrieval is not None and entry.retrieval.kind not in RETRIEVAL_KINDS:
        _err(report, eid, "retrieval.kind", f"must be one of {sorted(RETRIEVAL_KINDS)}")
    if entry.tier == "C" and not entry.instructions:
        _err(report, eid, "instructions", "required for Tier C (gated/manual)")
    if entry.sensitivity is not None and entry.sensitivity not in SENSITIVITY_VALUES:
        _err(report, eid, "sensitivity", f"must be one of {sorted(SENSITIVITY_VALUES)}")


def _validate_consistency(entry: DatasetEntry, report: ValidationReport) -> None:
    """Enforce tier↔(access, redistributable) consistency; warn on thin citations."""
    eid = entry.id
    if entry.tier == "A" and entry.redistributable is False:
        _err(report, eid, "tier", "tier A requires redistributable: true")
    if entry.tier == "A" and entry.access == "gated":
        _err(report, eid, "tier", "tier A cannot be access: gated")
    if entry.citation is not None and not entry.citation.is_complete():
        _warn(report, eid, "citation", "incomplete DataCite tuple — not DOI-mintable")


def _validate_entry(entry: DatasetEntry, report: ValidationReport) -> None:
    """Append every rule violation for one entry to `report`."""
    _validate_required(entry, report)
    _validate_files(entry, report)
    _validate_datasheet(entry, report)
    _validate_conditional(entry, report)
    _validate_consistency(entry, report)


def validate(manifest: Manifest) -> ValidationReport:
    """Validate a manifest against the schema and tier rules.

    Accumulates *all* violations (never first-fail). Cross-entry checks (duplicate
    ids) run once. Datasheet ``N/A`` placeholders and incomplete DataCite tuples
    are warnings, not errors.

    :param manifest: The manifest to validate.
    :returns: A report; :attr:`ValidationReport.ok` is false if any hard error.
    """
    report = ValidationReport()
    seen: dict[str, int] = {}
    for entry in manifest.datasets:
        seen[entry.id] = seen.get(entry.id, 0) + 1
        _validate_entry(entry, report)
    for entry_id, count in seen.items():
        if count > 1:
            report.errors.append(f"entry '{entry_id}': id: duplicated {count} times")
    return report


# --- Croissant interop ------------------------------------------------------

_CROISSANT_CONTEXT = {
    "@vocab": "https://schema.org/",
    "sha256": "https://schema.org/sha256",
    "cr": "http://mlcommons.org/croissant/",
    "citeAs": "cr:citeAs",
}


def _citation_text(citation: Citation) -> str:
    """Render a DataCite tuple as a one-line ``citeAs`` string."""
    parts = [
        part
        for part in (
            citation.creator,
            f"({citation.publication_year})" if citation.publication_year else None,
            citation.title,
            citation.publisher,
            citation.identifier,
        )
        if part
    ]
    return ". ".join(str(part) for part in parts)


def croissant_for(entry: DatasetEntry) -> dict[str, Any]:
    """Emit a schema.org ``Dataset`` Croissant JSON-LD document for one entry.

    Fields with no registry value are omitted rather than emitted empty. The
    registry stays the superset source of truth; this is an export view.

    :param entry: The dataset entry to render.
    :returns: A JSON-serializable Croissant document.
    """
    doc: dict[str, Any] = {
        "@context": _CROISSANT_CONTEXT,
        "@type": "Dataset",
        "name": entry.title or entry.id,
    }
    # Preserve the stable registry slug so an emit→ingest round-trip recovers the
    # same `id` (and `title`) instead of collapsing both onto the human name.
    if entry.title and entry.title != entry.id:
        doc["alternateName"] = entry.id
    if entry.description:
        doc["description"] = entry.description
    if entry.version:
        doc["version"] = entry.version
    if entry.license:
        doc["license"] = entry.license
    if entry.pid:
        doc["identifier"] = entry.pid
    if entry.citation is not None:
        doc["citeAs"] = _citation_text(entry.citation)

    distribution: list[dict[str, Any]] = []
    for ref in entry.files:
        obj: dict[str, Any] = {
            "@type": "cr:FileObject",
            "contentUrl": ref.path,
            "sha256": ref.sha256,
        }
        if ref.size is not None:
            obj["contentSize"] = ref.size
        distribution.append(obj)
    if distribution:
        doc["distribution"] = distribution
    return doc


class CroissantDocument(ExternalModel):
    """The parts of a published Croissant / schema.org ``Dataset`` we read.

    ``extra="ignore"``: a real Croissant file carries a great deal of JSON-LD
    this package has no use for, and an unmodelled field is not an error. What
    *is* an error is a document that is not an object at all, or whose
    ``distribution`` is not a list — both of which used to reach
    :func:`entry_from_croissant` and raise an ``AttributeError`` that escaped
    the CLI's ``except`` tuple as a traceback.
    """

    name: str | None = None
    alternate_name: str | None = Field(default=None, alias="alternateName")
    distribution: list[Any] = Field(default_factory=list)


def entry_from_croissant(json_ld: object) -> DatasetEntry:
    """Ingest a published Croissant document into a *draft* registry entry.

    Fills what the Croissant carries and leaves human-owned fields (``tier``,
    ``retrieval``, ``datasheet``, ``sensitivity``) unset — the caller flags them
    as TODO on register. Never guesses a tier or a license grant.

    :param json_ld: A parsed Croissant / schema.org ``Dataset`` document, of any
        shape — it is validated here rather than assumed.
    :returns: A partial :class:`DatasetEntry` draft.
    :raises ManifestError: If the document is not a JSON object, has no usable
        ``name``, or a ``distribution`` entry is a malformed ``FileObject`` (not
        a mapping, or missing ``contentUrl`` / ``sha256``). A malformed file is
        surfaced, never silently dropped — "no distribution" is distinct from
        "a bad file".
    """
    doc = parse_obj(CroissantDocument, json_ld, source="croissant", error=ManifestError)
    if not doc.name:
        raise ManifestError("croissant: document has no 'name' to derive an id from")
    # A round-tripped export carries the stable slug in `alternateName`; external
    # Croissant files won't, so fall back to `name` for the id.
    entry_id = str(doc.alternate_name or doc.name)
    title = str(doc.name) if str(doc.name) != entry_id else None
    # `doc` only models the fields entry_from_croissant needs firm validation
    # on (name, alternateName, distribution); parse_obj already established
    # json_ld is object-shaped, so the remaining optional fields are read
    # straight off it, as before.
    raw = cast("dict[str, Any]", json_ld)

    files: list[FileRef] = []
    for i, obj in enumerate(doc.distribution):
        loc = f"croissant: distribution[{i}]"
        if not isinstance(obj, dict):
            raise ManifestError(f"{loc}: FileObject must be a mapping")
        url = obj.get("contentUrl")
        sha = obj.get("sha256")
        if not url or not sha:
            raise ManifestError(
                f"{loc}: FileObject missing 'contentUrl' and/or 'sha256'"
            )
        files.append(
            FileRef(
                path=str(url),
                sha256=str(sha),
                size=_int_or_error(obj.get("contentSize"), loc, "contentSize"),
            )
        )

    return DatasetEntry(
        id=entry_id,
        version=_opt_str(raw.get("version")),
        license=_opt_str(raw.get("license")),
        title=title,
        description=_opt_str(raw.get("description")),
        pid=_opt_str(raw.get("identifier")),
        files=files,
        citation=(
            Citation(
                title=title or str(doc.name),
                identifier=_opt_str(raw.get("identifier")),
            )
            if raw.get("citeAs")
            else None
        ),
    )
