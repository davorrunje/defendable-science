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

import yaml

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


def _parse_items(text: str, target: Path) -> list[Any]:
    """Parse CSL-JSON items from text.

    :param text: The JSON text to parse.
    :param target: The path (for error messages).
    :returns: The parsed array of items.
    :raises RegistryError: If the text is not valid JSON or is not a JSON array.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RegistryError(f"{target}: invalid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise RegistryError(
            f"{target}: expected a JSON array of CSL-JSON items, got "
            f"{type(data).__name__}"
        )
    return data


def _read_items(path: Path) -> list[Any]:
    """Read and structurally validate the CSL-JSON array at `path`.

    :raises RegistryError: If the file is missing, is not valid JSON, or is not a
        JSON array.
    """
    if not path.is_file():
        raise RegistryError(f"{path}: registry not found")
    return _parse_items(path.read_text(encoding="utf-8"), path)


def load_registry_text(text: str, path: str | Path) -> Registry:
    """Decode ``references.json`` from text.

    :param text: The JSON text to decode.
    :param path: The registry path (for error messages and the returned Registry).
    :returns: The decoded registry.
    :raises RegistryError: If the text is not a JSON array, or contains an entry
        that is not an object or has no ``id``.
    """
    target = Path(path)
    entries: list[Entry] = []
    for index, item in enumerate(_parse_items(text, target)):
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


def load_registry(path: str | Path) -> Registry:
    """Load and decode ``references.json``.

    :param path: The registry path.
    :returns: The decoded registry.
    :raises RegistryError: If the file is missing, unparsable, not a JSON array,
        or contains an entry that is not an object or has no ``id``.
    """
    target = Path(path)
    if not target.is_file():
        raise RegistryError(f"{target}: registry not found")
    return load_registry_text(target.read_text(encoding="utf-8"), target)


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


def _locate(items: list[Any], citekey: str) -> int:
    """Return the index of the entry matching `citekey` by ``id`` then ``DOI``.

    The DOI fallback is **API-only**: no shipped caller reaches it, because
    everything in ``literature/`` patches by the ``id`` it read out of this same
    file. It is kept because a library caller holding a DOI and no citekey has
    nowhere else to go — but see :func:`patch_asset`'s warning: passing a DOI
    writes to whichever entry carries it, which need not be the entry the caller
    thinks it resolved.

    :raises RegistryError: If no entry matches.
    """
    for index, item in enumerate(items):
        if isinstance(item, dict) and _opt_str(item.get("id")) == citekey:
            return index
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        doi = _opt_str(item.get("DOI")) or _opt_str(item.get("doi"))
        if doi is not None and doi.lower() == citekey.lower():
            return index
    raise RegistryError(f"no entry {citekey!r} in the registry")


def patch_asset(path: str | Path, citekey: str, asset: Asset) -> None:
    """Replace one entry's spine, leaving every other byte of the file alone.

    Surgical by design: reads the raw JSON, mutates only
    ``entry["custom"]["defendable-science"]``, and rewrites atomically. Unknown
    top-level keys, unknown ``custom`` sub-keys (a Zotero namespace, say), and key
    order all survive. The registry is a human-editable file; a writer that
    round-trips it through a model would silently drop what the model does not
    know about.

    .. warning::
       The ``DOI`` fallback in the lookup is for **API callers only**, and it is
       reached by nothing this package ships: every internal caller passes the
       ``id`` it read out of this same file. A caller that passes a DOI instead
       of a citekey will write the spine onto whichever entry carries that DOI —
       which may not be the entry it believes it resolved. Pass a citekey.

    :param path: The registry path.
    :param citekey: The entry to patch, matched on ``id``, then — for API
        callers only — on ``DOI``.
    :param asset: The spine to store.
    :raises RegistryError: If the file is unusable, no entry matches `citekey`, or
        the entry's existing ``custom`` field is not an object.
    """
    target = Path(path)
    items = _read_items(target)
    index = _locate(items, citekey)
    item = items[index]
    custom = item.get("custom", {})
    if not isinstance(custom, dict):
        raise RegistryError(
            f"{target}: entry {citekey!r} has a 'custom' field that is not an "
            "object — fix it by hand rather than have it overwritten"
        )
    custom[NAMESPACE] = asset_to_json(asset)
    item["custom"] = custom
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(
        json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    tmp.replace(target)


@dataclass
class TriageRow:
    """One ``triage.yml`` row — our decisions about a paper.

    :param citekey: The row key, joining to the bib entry.
    :param disposition: The state-machine value, when set.
    :param raw: The full row, so callers can read fields this model does not name.
    """

    citekey: str
    disposition: str | None
    raw: dict[str, Any]


def triage_mapping(target: Path, text: str) -> dict[Any, Any]:
    """Parse the triage sidecar into its raw top-level mapping.

    Raw on purpose: the row values are handed back exactly as ``pyyaml`` gave
    them, including rows that are not mappings, so a *writer* can see what a
    reader would skip. This public function must exist because ``load_triage``
    skips rows that are not mappings — correct for a reader, but that means a
    malformed row is invisible to every consumer, and ``check`` is the one
    caller that must see what a reader would skip.

    :param target: The path, for error messages.
    :param text: The file contents.
    :returns: The top-level mapping, or ``{}`` for an empty file.
    :raises RegistryError: If the text is not valid YAML, or is not a mapping at
        the top level.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RegistryError(f"{target}: invalid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RegistryError(
            f"{target}: expected a YAML mapping of citekey → row, got "
            f"{type(data).__name__}"
        )
    return data


def load_triage(path: str | Path) -> dict[str, TriageRow]:
    """Load the triage sidecar, keyed by citekey.

    A missing file yields ``{}`` — a project with no triage yet is not an error.
    A row that is not a mapping is skipped rather than fatal, so one malformed
    row does not make the whole sidecar unreadable.

    :param path: The sidecar path.
    :returns: Rows by citekey.
    :raises RegistryError: If the file exists but is not valid YAML, or is not a
        YAML mapping at the top level.
    """
    target = Path(path)
    if not target.is_file():
        return {}
    data = triage_mapping(target, target.read_text(encoding="utf-8"))
    rows: dict[str, TriageRow] = {}
    for citekey, row in data.items():
        if not isinstance(row, dict):
            continue
        rows[str(citekey)] = TriageRow(
            citekey=str(citekey),
            disposition=_opt_str(row.get("disposition")),
            raw=row,
        )
    return rows


def _has_comments(text: str) -> bool:
    """Return whether the YAML text carries a comment line.

    Deliberately conservative: any line whose first non-space character is ``#``
    counts. An inline ``#`` inside a quoted scalar would be a false positive, and
    a false positive here costs a refusal the human can work around, while a false
    negative costs them their PRISMA rationales.
    """
    return any(line.lstrip().startswith("#") for line in text.splitlines())


def _walk_node(node: yaml.Node, owner: str, visits: dict[int, list[str]]) -> None:
    """Record that ``node`` (and everything reachable from it) belongs to ``owner``.

    :param node: The composed node to visit.
    :param owner: The top-level citekey whose subtree this node was reached from.
    :param visits: Accumulator, mutated in place: node id → the owners that
        reached it, one entry per visit (so a node reached twice from the same
        owner still shows a duplicate, meaning "aliased").
    """
    visits.setdefault(id(node), []).append(owner)
    if isinstance(node, yaml.MappingNode):
        for _, value_node in node.value:
            _walk_node(value_node, owner, visits)
    elif isinstance(node, yaml.SequenceNode):
        for item_node in node.value:
            _walk_node(item_node, owner, visits)


def _compose_row_visits(
    root: yaml.MappingNode,
) -> tuple[dict[str, yaml.Node], dict[int, list[str]]]:
    """Walk every row's subtree, tracking which citekey(s) reach each node.

    :param root: The composed top-level mapping node.
    :returns: ``(row_nodes, visits)`` — each top-level citekey's own value
        node, and, for every node anywhere in the document, the list of
        citekeys whose subtree reached it (with duplicates, so length alone
        says whether it was reached more than once).
    """
    row_nodes: dict[str, yaml.Node] = {}
    visits: dict[int, list[str]] = {}
    for key_node, value_node in root.value:
        citekey = str(key_node.value)
        row_nodes[citekey] = value_node
        _walk_node(value_node, citekey, visits)
    return row_nodes, visits


def _classify_alias_groups(
    row_nodes: dict[str, yaml.Node], visits: dict[int, list[str]]
) -> tuple[list[list[str]], list[list[str]]]:
    """Split nodes reached more than once into whole-row and nested-alias groups.

    A node reached only once is not aliased at all — ordinary content. A node
    reached more than once is a genuine ``&anchor``/``*alias`` (see
    :func:`_alias_groups` for why that identity test cannot false-positive).
    It is a **whole-row** group when every citekey that reached it did so via
    its *own* top-level row value — the original "two citekeys, one anchored
    mapping" case. Otherwise it is a **nested-alias** group: at least one
    citekey reached the shared node only through something nested inside its
    row (a nested row, a merge key, or a scalar), or the same citekey reached
    it more than once from within its own row.

    :param row_nodes: Each top-level citekey's own value node.
    :param visits: Node id → the citekeys whose subtree reached it, as built
        by :func:`_compose_row_visits`.
    :returns: ``(whole_row_groups, nested_alias_groups)``, each a sorted list
        of sorted citekey lists; empty when nothing is aliased.
    """
    whole: dict[int, tuple[str, ...]] = {}
    nested: dict[int, tuple[str, ...]] = {}
    for node_id, owners in visits.items():
        if len(owners) <= 1:
            continue
        distinct = tuple(sorted(set(owners)))
        if all(id(row_nodes.get(c)) == node_id for c in distinct):
            whole[node_id] = distinct
        else:
            nested[node_id] = distinct
    return (
        [list(group) for group in sorted(set(whole.values()))],
        [list(group) for group in sorted(set(nested.values()))],
    )


def _alias_groups(text: str) -> tuple[list[list[str]], list[list[str]]]:
    """Return the citekey groups implicated by a YAML anchor/alias in ``text``.

    This walks the **composed node graph** (``yaml.compose``), not the
    ``yaml.safe_load``-constructed objects. That distinction is what makes the
    check safe for scalars: CPython interns small integers and singletons like
    ``True``/``False``, so two independently-written rows that both happen to
    hold ``extracted: true`` would share ``id(True)`` with no YAML anchor
    involved at all — a false positive if identity were tested on the
    constructed values. A composed :class:`yaml.nodes.Node` carries no such
    caching: every node is a fresh wrapper object regardless of the scalar it
    holds, so two nodes are ever the same object only when the source text
    actually used ``&anchor``/``*alias`` to make them so.

    Two kinds of sharing are distinguished, because one of them is exactly the
    pre-existing "two citekeys, one anchored mapping" case and keeps its
    established message; see :func:`_classify_alias_groups` for exactly how:

    - **whole-row** groups: every implicated citekey's *entire* top-level row
      is the shared node (``a2020: &shared`` / ``b2021: *shared``) — the
      original ``_aliased_rows`` case from ``bd60859``, now folded in here.
    - **nested-alias** groups: the shared node is reachable from more than one
      place but is not every implicated row's whole value — a row anchored at
      the top level and aliased *inside* another row's nested value, a merge
      key (``<<: *base``), or a scalar anchor (``rationale: *reason``) reused
      anywhere, including within a single row.

    :param text: The sidecar's YAML text. Assumed already validated by
        :func:`triage_mapping` as either blank or a top-level mapping — the
        only two shapes ``patch_triage`` calls this with.
    :returns: ``(whole_row_groups, nested_alias_groups)``, each a sorted list
        of sorted citekey lists; empty when nothing is aliased.
    """
    root = yaml.compose(text, Loader=yaml.SafeLoader)
    if root is None:
        return [], []
    if not isinstance(root, yaml.MappingNode):  # pragma: no cover
        # Unreachable in practice: triage_mapping already required text to be
        # either blank or a top-level mapping before this is ever called.
        return [], []
    row_nodes, visits = _compose_row_visits(root)
    return _classify_alias_groups(row_nodes, visits)


def patch_triage(
    path: str | Path, citekey: str, updates: dict[str, str | int | bool | None]
) -> None:
    """Add or replace scalar keys on one triage row.

    ``pyyaml`` cannot round-trip comments, and the triage sidecar's ``rationale``
    fields *are* the PRISMA audit trail — often annotated. So this refuses to
    rewrite a file carrying comments rather than silently destroying them; the
    caller surfaces the refusal and the human edits by hand. Scalars only, for the
    same reason: a nested value is a structure worth a human's attention.

    The same posture covers a **row that is not a mapping**. ``sill1997: include``
    (a shorthand disposition) and a bare ``igel2023:`` (a citekey queued with
    nothing under it yet) are ordinary hand-authoring, and both are invisible to
    :func:`load_triage`, which skips them. Rebuilding the file from what a reader
    could see would therefore delete them — the exact "we round-tripped a human's
    file and dropped what we did not know" failure this module was written to
    avoid. So the write is refused, naming the rows, and the human is told to
    edit by hand.

    It covers, too, **two citekeys whose rows are one anchored mapping**
    (``a2020: &shared`` / ``b2021: *shared``). ``yaml.safe_load`` hands both
    names the same object, so setting a field on either sets it on both, and
    ``safe_dump`` re-emits the alias — leaving a file that still looks
    hand-authored while carrying, say, an extraction record for a paper nothing
    ever extracted. Inventing an audit-trail entry is worse than losing one, so
    this is refused as well, naming the rows that share an object.

    It also covers every other shape a YAML anchor can take
    (defendable-science#143), via :func:`_alias_groups`, which walks the
    *composed node graph* rather than the constructed objects — the only way
    to test true identity without false-positiving on interned scalars like
    small ints or ``True``/``False``:

    - A row anchored at the top level and aliased **inside another row's
      nested value** (``a2020: &shared`` / ``b2021: {parent: *shared}``) is
      refused the same as the whole-row case — patching ``a2020`` must not
      silently write into ``b2021.parent`` too.
    - A **merge key** (``<<: *base``) or a **scalar anchor**
      (``rationale: *reason``), reused anywhere in the file — across rows or
      within one row — is refused rather than silently expanded. Anchor names
      cannot survive ``safe_dump`` either way; the previous behaviour lost
      only the anchor label, but "loses a label silently" is still a silent
      change this writer should not make on the human's behalf.

    :param path: The sidecar path (created if absent).
    :param citekey: The row to patch (created if absent).
    :param updates: Scalar keys to set; a ``None`` value deletes the key.
    :raises RegistryError: If the file carries comments, holds a row that is not
        a mapping, holds a YAML anchor aliased more than once anywhere in the
        document (whole rows, nested values, merge keys, or scalars), is
        unreadable, or any update value is not a scalar.
    """
    for key, value in updates.items():
        if value is not None and not isinstance(value, (str, int, bool)):
            raise RegistryError(
                f"triage update {key!r} must be a scalar or None, got "
                f"{type(value).__name__} — edit nested structure by hand"
            )
    target = Path(path)
    if target.is_file():
        text = target.read_text(encoding="utf-8")
        if _has_comments(text):
            raise RegistryError(
                f"{target}: carries comments, which cannot be preserved on write "
                f"— set {sorted(updates)} on {citekey!r} by hand"
            )
        raw = triage_mapping(target, text)
        opaque = sorted(
            str(key) for key, row in raw.items() if not isinstance(row, dict)
        )
        if opaque:
            raise RegistryError(
                f"{target}: rows {opaque} are not mappings — a shorthand "
                "'citekey: value' or a citekey with nothing under it yet. This "
                "writer cannot rewrite the file without dropping them, so it is "
                f"refusing — set {sorted(updates)} on {citekey!r} by hand"
            )
        whole, nested = _alias_groups(text)
        if whole:
            raise RegistryError(
                f"{target}: rows {whole} are the same mapping — citekeys joined "
                "by a YAML anchor. Setting a field on any one of them would set "
                "it on all of them, recording work that was never done on the "
                "others. So it is refusing — give each row its own keys, or set "
                f"{sorted(updates)} on {citekey!r} by hand"
            )
        if nested:
            raise RegistryError(
                f"{target}: rows {nested} share a YAML anchor somewhere inside "
                "them — a row anchored at the top level and aliased inside "
                "another row's nested value, a merge key ('<<: *base'), or a "
                "scalar anchor ('rationale: *reason'). Writing this back would "
                "either silently propagate a change across rows that share the "
                "anchor, or silently drop the anchor/alias structure entirely. "
                "So it is refusing — remove the anchor, or set "
                f"{sorted(updates)} on {citekey!r} by hand"
            )
        data: dict[str, Any] = {str(key): row for key, row in raw.items()}
    else:
        data = {}
    row = data.setdefault(citekey, {})
    for key, value in updates.items():
        if value is None:
            row.pop(key, None)
        else:
            row[key] = value
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    tmp.replace(target)
