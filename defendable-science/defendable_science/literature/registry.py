"""The literature registry — CSL-JSON bib + ``triage.yml`` sidecar.

``references.json`` is CSL-JSON and is the source of truth (ADR-0020). The CSL
input schema sets ``additionalProperties: false`` and defines no ``files`` /
``license`` / ``mirror`` field, so the substrate spine
(``docs/design/04-substrate-and-contract.md`` §2.1) lives under the
schema-designated ``custom`` field, namespaced — keeping the file valid CSL-JSON
and round-trippable through Zotero and pandoc.

Writers here are **surgical**: they patch one namespaced object and leave every
other byte of the human's file alone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: The ``custom`` sub-key that holds our spine.
NAMESPACE = "defendable-science"

#: Spine schema version, so a future migration need not guess.
SCHEMA = 1


class RegistryError(ValueError):
    """Raised when the registry file is missing, unparsable, or unusable."""


@dataclass
class AssetFile:
    """One payload file of a registry entry.

    :param path: Content-addressed blob path, relative to the cache root. Never
        a repository path — ``fetch`` does not place bytes in-repo (spec §6).
    :param sha256: The authoritative checksum, ``sha256:``-prefixed.
    :param size: Byte count, when known.
    :param media_type: The media type observed at acquisition, when known.
    """

    path: str
    sha256: str
    size: int | None = None
    media_type: str | None = None


@dataclass
class License:
    """An *observed* license, not an assertion of rights.

    :param id: SPDX id, when a source reported one we recognize.
    :param observed: The raw license string as reported.
    :param source: Which acquisition rung reported it.
    """

    id: str | None = None
    observed: str | None = None
    source: str | None = None


@dataclass
class MirrorRef:
    """Where a mirrored copy lives.

    :param remote: The logical rclone remote name.
    :param key: The content-addressed key under the remote's base path.
    """

    remote: str
    key: str


@dataclass
class Acquisition:
    """How the bytes were obtained — the audit trail for a bound PDF.

    :param rung: The ladder rung that yielded the bytes.
    :param url: The URL the bytes came from, if any.
    :param candidate: The candidate record as reported by the rung.
    :param match: The gate's per-axis verdict record.
    :param fetched: ISO date of acquisition.
    """

    rung: str
    url: str | None = None
    candidate: dict[str, Any] = field(default_factory=dict)
    match: dict[str, Any] = field(default_factory=dict)
    fetched: str | None = None


@dataclass
class Asset:
    """The substrate spine for one registry entry.

    :param schema: Spine schema version.
    :param pid: Persistent identifier (``openalex:W…`` / ``doi:…``).
    :param files: Payload files.
    :param license: The observed license.
    :param redistributable: Whether the license permits republishing the bytes.
        Defaults to ``False``; an absent or unrecognized license stays ``False``.
    :param access: ``open`` | ``gated``, when known.
    :param mirror: The mirror reference, present iff a mirrored copy exists.
    :param acquisition: How the bytes were obtained.
    """

    schema: int = SCHEMA
    pid: str | None = None
    files: list[AssetFile] = field(default_factory=list)
    license: License = field(default_factory=License)
    redistributable: bool = False
    access: str | None = None
    mirror: MirrorRef | None = None
    acquisition: Acquisition | None = None


@dataclass
class Entry:
    """A registry entry — the bibliographic facts the gate needs, plus the spine.

    :param citekey: The CSL ``id``.
    :param title: The entry title.
    :param year: Publication year, when parseable.
    :param first_author_family: First author's family name, when present.
    :param doi: The DOI, when present.
    :param asset: The decoded spine, or ``None`` if the entry has none yet.
    :param raw: The undecoded CSL item, so writers can round-trip it.
    """

    citekey: str
    title: str | None
    year: int | None
    first_author_family: str | None
    doi: str | None
    asset: Asset | None
    raw: dict[str, Any]


@dataclass
class Registry:
    """A loaded ``references.json``.

    :param path: Where it was loaded from.
    :param entries: The decoded entries, in file order.
    """

    path: Path
    entries: list[Entry]

    def get(self, citekey: str) -> Entry | None:
        """Return the entry with this citekey, or ``None``.

        :param citekey: The CSL ``id`` to look up.
        :returns: The entry, or ``None`` when absent.
        """
        for entry in self.entries:
            if entry.citekey == citekey:
                return entry
        return None


def _opt_str(value: Any) -> str | None:
    """Return `value` as a string, or ``None`` if it is not a non-empty string."""
    return value if isinstance(value, str) and value.strip() else None


def _year(raw: Any) -> int | None:
    """Extract a year from a CSL ``issued`` object, tolerantly.

    A missing, malformed, or non-numeric date (``"n.d."``, an empty
    ``date-parts``) yields ``None``: the year is *unknown*, which the match gate
    treats as insufficient metadata rather than as a mismatch.
    """
    if not isinstance(raw, dict):
        return None
    parts = raw.get("date-parts")
    if not isinstance(parts, list) or not parts:
        return None
    first = parts[0]
    if not isinstance(first, list) or not first:
        return None
    try:
        return int(first[0])
    except (TypeError, ValueError):
        return None


def _first_family(raw: Any) -> str | None:
    """Return the first author's ``family`` name, or ``None``.

    A CSL ``literal`` author (a consortium) has no family name; that is ``None``,
    not an error — the gate degrades on it (spec §5.2).
    """
    if not isinstance(raw, list) or not raw:
        return None
    first = raw[0]
    if not isinstance(first, dict):
        return None
    return _opt_str(first.get("family"))


def _decode_files(raw: Any) -> list[AssetFile]:
    """Decode the spine's ``files`` array, skipping unusable rows."""
    if not isinstance(raw, list):
        return []
    out: list[AssetFile] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = _opt_str(item.get("path"))
        sha = _opt_str(item.get("sha256"))
        if path is None or sha is None:
            continue
        size = item.get("size")
        out.append(
            AssetFile(
                path=path,
                sha256=sha,
                size=size if isinstance(size, int) else None,
                media_type=_opt_str(item.get("media_type")),
            )
        )
    return out


def _decode_license(raw: Any) -> License:
    """Decode the spine's ``license`` object."""
    if not isinstance(raw, dict):
        return License()
    return License(
        id=_opt_str(raw.get("id")),
        observed=_opt_str(raw.get("observed")),
        source=_opt_str(raw.get("source")),
    )


def _decode_mirror(raw: Any) -> MirrorRef | None:
    """Decode the spine's ``mirror`` object, or ``None`` when absent/unusable."""
    if not isinstance(raw, dict):
        return None
    remote = _opt_str(raw.get("remote"))
    key = _opt_str(raw.get("key"))
    if remote is None or key is None:
        return None
    return MirrorRef(remote=remote, key=key)


def _decode_acquisition(raw: Any) -> Acquisition | None:
    """Decode the spine's ``acquisition`` object, or ``None`` when absent."""
    if not isinstance(raw, dict):
        return None
    rung = _opt_str(raw.get("rung"))
    if rung is None:
        return None
    candidate = raw.get("candidate")
    match = raw.get("match")
    return Acquisition(
        rung=rung,
        url=_opt_str(raw.get("url")),
        candidate=candidate if isinstance(candidate, dict) else {},
        match=match if isinstance(match, dict) else {},
        fetched=_opt_str(raw.get("fetched")),
    )


def _decode_asset(item: dict[str, Any]) -> Asset | None:
    """Decode the spine from a CSL item's ``custom`` field, or ``None``."""
    custom = item.get("custom")
    if not isinstance(custom, dict):
        return None
    blob = custom.get(NAMESPACE)
    if not isinstance(blob, dict):
        return None
    schema = blob.get("schema")
    return Asset(
        schema=schema if isinstance(schema, int) else SCHEMA,
        pid=_opt_str(blob.get("pid")),
        files=_decode_files(blob.get("files")),
        license=_decode_license(blob.get("license")),
        redistributable=blob.get("redistributable") is True,
        access=_opt_str(blob.get("access")),
        mirror=_decode_mirror(blob.get("mirror")),
        acquisition=_decode_acquisition(blob.get("acquisition")),
    )


def _read_items(path: Path) -> list[Any]:
    """Read and structurally validate the CSL-JSON array at `path`.

    :raises RegistryError: If the file is missing, is not valid JSON, or is not a
        JSON array.
    """
    if not path.is_file():
        raise RegistryError(f"{path}: registry not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RegistryError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise RegistryError(
            f"{path}: expected a JSON array of CSL-JSON items, got "
            f"{type(data).__name__}"
        )
    return data


def load_registry(path: str | Path) -> Registry:
    """Load and decode ``references.json``.

    :param path: The registry path.
    :returns: The decoded registry.
    :raises RegistryError: If the file is missing, unparsable, not a JSON array,
        or contains an entry that is not an object or has no ``id``.
    """
    target = Path(path)
    entries: list[Entry] = []
    for index, item in enumerate(_read_items(target)):
        if not isinstance(item, dict):
            raise RegistryError(f"{target}: entry {index} is not an object")
        citekey = _opt_str(item.get("id"))
        if citekey is None:
            raise RegistryError(f"{target}: entry {index} has no 'id'")
        entries.append(
            Entry(
                citekey=citekey,
                title=_opt_str(item.get("title")),
                year=_year(item.get("issued")),
                first_author_family=_first_family(item.get("author")),
                doi=_opt_str(item.get("DOI")) or _opt_str(item.get("doi")),
                asset=_decode_asset(item),
                raw=item,
            )
        )
    return Registry(path=target, entries=entries)


def asset_to_json(asset: Asset) -> dict[str, Any]:
    """Render an :class:`Asset` as the JSON object stored under ``custom``.

    Absent optionals are omitted rather than written as ``null``, so the file
    stays readable and a hand-editing human is not shown fields that mean nothing.

    :param asset: The spine to render.
    :returns: The JSON-ready object.
    """
    blob: dict[str, Any] = {
        "schema": asset.schema,
        "pid": asset.pid,
        "files": [
            {
                "path": ref.path,
                "sha256": ref.sha256,
                "size": ref.size,
                "media_type": ref.media_type,
            }
            for ref in asset.files
        ],
        "license": {
            "id": asset.license.id,
            "observed": asset.license.observed,
            "source": asset.license.source,
        },
        "redistributable": asset.redistributable,
        "access": asset.access,
    }
    if asset.mirror is not None:
        blob["mirror"] = {"remote": asset.mirror.remote, "key": asset.mirror.key}
    if asset.acquisition is not None:
        blob["acquisition"] = {
            "rung": asset.acquisition.rung,
            "url": asset.acquisition.url,
            "candidate": asset.acquisition.candidate,
            "match": asset.acquisition.match,
            "fetched": asset.acquisition.fetched,
        }
    return blob
