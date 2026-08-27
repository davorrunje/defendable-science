"""The ``defendable-science`` command-line interface.

A Typer command tree mirroring the plugin's skill verbs: ``doctor``,
``literature`` (citation graph), ``dataset`` (manifest / retrieval / mirror),
``defend record``, and ``backlog`` are all implemented and emit JSON. See
ADR-0024 and ``docs/design/proposals/tooling-package.md``.
"""

from __future__ import annotations

import dataclasses
import getpass
import json
import platform
import shutil
import subprocess  # nosec B404 - used only to read `--version` of trusted tools
import sys
from contextlib import contextmanager
from datetime import date as date_cls
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer

from defendable_science import __version__
from defendable_science.core import keys as keys_mod
from defendable_science.core.download import stream_to_file
from defendable_science.core.fixity import RetrievalError
from defendable_science.core.mirror import Mirror
from defendable_science.dataset import manifest as manifest_mod
from defendable_science.dataset import retrieval as retrieval_mod
from defendable_science.defend import record as record_mod
from defendable_science.exploration import backlog as backlog_mod
from defendable_science.literature import acquire as acquire_mod
from defendable_science.literature import graph as graph_mod
from defendable_science.literature import registry as registry_mod

if TYPE_CHECKING:
    from collections.abc import Iterator

    from defendable_science.core.http import HttpClient

app = typer.Typer(
    name="defendable-science",
    help="Supporting tooling for the defendable-science research-workflow plugin.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    """Print the package version and exit when ``--version`` is given.

    :param value: Whether the ``--version`` flag was supplied.
    :raises typer.Exit: With code 0 after printing, when `value` is true.
    """
    if value:
        typer.echo(__version__)
        raise typer.Exit(code=0)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the defendable-science version and exit.",
        ),
    ] = False,
) -> None:
    """defendable-science — research-workflow tooling CLI."""


def _tool_report(name: str) -> str:
    """Report the presence and version of an external tool on ``PATH``.

    Absence is reported, not treated as an error.

    :param name: Executable name to look up via :func:`shutil.which`.
    :returns: A human-readable one-line status string.
    """
    path = shutil.which(name)
    if path is None:
        return f"{name}: not found"
    try:
        proc = subprocess.run(  # nosec B603 - `path` resolved from PATH; fixed args
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - defensive
        return f"{name}: found ({path}), version unknown"
    output = (proc.stdout or proc.stderr).strip().splitlines()
    detail = output[0] if output else "version unknown"
    return f"{name}: {detail} ({path})"


@app.command()
def doctor() -> None:
    """Report the local environment: Python, ``uv`` and ``rclone``.

    Prints a short diagnostic report. Missing optional tools (``uv``,
    ``rclone``) are reported, not treated as failures. Always exits 0.
    """
    typer.echo("defendable-science doctor")
    typer.echo(f"  defendable-science: {__version__}")
    typer.echo(f"  python: {platform.python_version()} ({platform.platform()})")
    typer.echo(f"  {_tool_report('uv')}")
    typer.echo(f"  {_tool_report('rclone')}")
    typer.echo("  keys:")
    for known in keys_mod.KNOWN_KEYS.values():
        source = keys_mod.source_of(known.name)
        if source is None:
            typer.echo(f"    {known.name}: not set")
        else:
            typer.echo(f"    {known.name}: set (source: {source})")
    raise typer.Exit(code=0)


# --- shared cache-root config (defendable-science#65) ---------------------------------
_DEFAULT_CACHE_ROOT = Path(".defendable-science/cache")


def _load_config_or_exit() -> dict[str, Any]:
    """Load ``.defendable-science/config.yml``, exiting 1 on invalid YAML/mapping.

    :returns: The parsed configuration mapping (empty if the file is absent).
    :raises typer.Exit: Code 1 if the file exists but is not a valid YAML
        mapping.
    """
    from defendable_science.core.config import load_config

    try:
        return load_config()
    except ValueError as exc:
        typer.echo(f"invalid .defendable-science/config.yml: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _cache_root(config: dict[str, Any] | None = None) -> Path:
    """Resolve the cache root from ``config.yml``'s ``cache_dir:`` key.

    Both the dataset content-addressed cache and the literature HTTP cache
    live under this single root, and ``research-init`` gitignores exactly
    this path (see the SKILL.md scaffold). Sourcing it from config instead of
    hardcoding it in two places is what keeps the scaffolded ``.gitignore``
    and the runtime cache location from drifting apart (defendable-science#65).

    :param config: A pre-loaded config mapping; loaded fresh when omitted.
    :returns: The configured cache root, or :data:`_DEFAULT_CACHE_ROOT` when
        ``cache_dir`` is unset.
    :raises typer.Exit: Code 1 if ``cache_dir`` is present but not a string.
    """
    if config is None:
        config = _load_config_or_exit()
    cache_dir = config.get("cache_dir")
    if cache_dir is None:
        return _DEFAULT_CACHE_ROOT
    if not isinstance(cache_dir, str):
        typer.echo(
            "invalid .defendable-science/config.yml: 'cache_dir' must be a string",
            err=True,
        )
        raise typer.Exit(code=1)
    return Path(cache_dir)


# --- literature (defendable-science#1) ------------------------------------------------
literature = typer.Typer(
    help="Citation-graph and metadata tools.", no_args_is_help=True
)
app.add_typer(literature, name="literature")


def _rps_from_config(lit: object, field_name: str, default: float) -> float:
    """Read a numeric ``literature.<field_name>`` override from `lit`, or `default`.

    :param lit: The parsed ``literature:`` config block (or ``None``/non-mapping).
    :param field_name: The config key (``s2_rps`` or ``openalex_rps``).
    :param default: The value to use when the key is absent.
    :returns: The configured rps, or `default` when unset.
    :raises typer.Exit: Code 1 if the key is present but not a number.
    """
    raw = lit.get(field_name) if isinstance(lit, dict) else None
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        typer.echo(
            f"invalid .defendable-science/config.yml: 'literature.{field_name}' "
            "must be a number",
            err=True,
        )
        raise typer.Exit(code=1) from exc


def _lit_client() -> HttpClient:
    """Build the literature HTTP client from config + the key store.

    Reads ``literature.mailto`` from ``.defendable-science/config.yml`` (polite pool),
    falling back to ``OPENALEX_MAILTO``, and sources ``S2_API_KEY`` through the
    key store — both with ``os.environ`` > store precedence (ADR-0029). Also
    reads ``literature.s2_rps`` / ``literature.openalex_rps`` — proactive
    per-host rate-limit caps (defendable-science#67) — falling back to
    :class:`HttpClient`'s own conservative defaults (S2 below its 1 req/s
    per-key ceiling) when absent. Caches responses under ``<cache_dir>/http``
    (``cache_dir:`` in config, default ``.defendable-science/cache/``; see
    :func:`_cache_root`). Tests monkeypatch this to inject a fake client.
    """
    from defendable_science.core.http import HttpClient

    config = _load_config_or_exit()
    lit = config.get("literature")
    if lit is not None and not isinstance(lit, dict):
        typer.echo(
            "invalid .defendable-science/config.yml: 'literature' must be a mapping",
            err=True,
        )
        raise typer.Exit(code=1)
    mailto = lit.get("mailto") if isinstance(lit, dict) else None
    defaults = HttpClient()
    return HttpClient(
        cache_dir=_cache_root(config) / "http",
        mailto=mailto or keys_mod.get("OPENALEX_MAILTO"),
        s2_key=keys_mod.get("S2_API_KEY"),
        s2_rps=_rps_from_config(lit, "s2_rps", defaults.s2_rps),
        openalex_rps=_rps_from_config(lit, "openalex_rps", defaults.openalex_rps),
    )


@contextmanager
def _http_guard(client: HttpClient) -> Iterator[None]:
    """Translate an HTTP failure into a clean, actionable non-zero exit.

    A rate-limit (``RateLimitError``) is distinguished from other transport
    failures so the researcher is told *why* the lookup stopped — never a
    traceback, and never silently folded into an empty result.

    :param client: The client whose retry budget informs the message.
    :raises typer.Exit: Code 1 on any :class:`HttpError` (message on stderr).
    """
    from defendable_science.core.http import HttpError, RateLimitError

    try:
        yield
    except RateLimitError as exc:
        typer.echo(
            f"rate-limited by Semantic Scholar after {client.max_retries} retries "
            "— set S2_API_KEY for higher limits, or retry later",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    except HttpError as exc:
        typer.echo(f"literature request failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _openalex_id(client: HttpClient, identifier: str) -> str:
    """Resolve `identifier` to an OpenAlex id, or exit 1 if it cannot resolve."""
    record = graph_mod.resolve(identifier, client=client)
    if not record.get("resolved") or not record.get("openalex"):
        typer.echo(
            f"could not resolve {identifier!r}: {record.get('reason')}", err=True
        )
        raise typer.Exit(code=1)
    return str(record["openalex"])


@literature.command()
def resolve(identifier: str) -> None:
    """Resolve an identifier (DOI, arXiv id, OpenAlex/S2 id) to a canonical work.

    The exit code follows the result so a caller need not parse JSON to tell
    the outcomes apart — and never mistake a network failure for a clean
    "no result":

    :raises typer.Exit: Code ``0`` on a resolution. Code ``1`` on a genuine
        miss (no such paper). Code ``2`` on a Click/Typer usage error (bad
        flags, missing argument) — untouched, not raised by this body. Code
        ``3`` on a transport failure (``transport_error: true`` in the JSON) —
        deliberately distinct from ``2`` so a caller can never confuse "you
        typed it wrong" with "the network failed".

    :param identifier: The identifier to resolve.
    """
    client = _lit_client()
    with _http_guard(client):
        record = graph_mod.resolve(identifier, client=client)
        typer.echo(json.dumps(record, indent=2))
        if record.get("resolved"):
            raise typer.Exit(code=0)
        if record.get("transport_error"):
            raise typer.Exit(code=3)
        raise typer.Exit(code=1)


@literature.command()
def cites(
    identifier: str,
    max_results: Annotated[int, typer.Option("--max", help="Cap on rows.")] = 0,
) -> None:
    """List works that cite the given work (JSON array).

    :param identifier: The work identifier.
    :param max_results: Optional cap on the number of rows (0 = all).
    """
    client = _lit_client()
    with _http_guard(client):
        rows = graph_mod.cites(
            _openalex_id(client, identifier),
            client=client,
            max_results=max_results or None,
        )
        typer.echo(json.dumps(rows, indent=2))
        raise typer.Exit(code=0)


@literature.command()
def refs(identifier: str) -> None:
    """List the backward references (OpenAlex ids) of the given work.

    :param identifier: The work identifier.
    """
    client = _lit_client()
    with _http_guard(client):
        typer.echo(
            json.dumps(graph_mod.refs(_openalex_id(client, identifier), client=client))
        )
        raise typer.Exit(code=0)


@literature.command()
def enrich(
    identifiers: list[str],
    with_context: Annotated[bool, typer.Option("--context")] = False,
) -> None:
    """Enrich one or more works with their metadata bundle (JSON array).

    :param identifiers: The work identifiers to enrich.
    :param with_context: Request S2 citation-context fields (degrades w/o a key).
    """
    client = _lit_client()
    with _http_guard(client):
        ids = [_openalex_id(client, ident) for ident in identifiers]
        rows = graph_mod.enrich(ids, client=client, with_context=with_context)
        typer.echo(json.dumps(rows, indent=2))
        raise typer.Exit(code=0)


@literature.command()
def neighbors(
    identifier: str,
    kind: Annotated[
        str, typer.Option("--kind", help="cocite | couple | both.")
    ] = "both",
    top: Annotated[int, typer.Option("--top")] = 20,
) -> None:
    """List co-citation / bibliographic-coupling neighbours of the given work.

    :param identifier: The work identifier.
    :param kind: ``cocite`` / ``couple`` / ``both``.
    :param top: Number of neighbours per set.
    """
    client = _lit_client()
    with _http_guard(client):
        resolved = _openalex_id(client, identifier)
        try:
            result = graph_mod.neighbors(resolved, client=client, kind=kind, top=top)
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(result, indent=2))
        raise typer.Exit(code=0)


# --- literature acquisition (defendable-science#97) -----------------------------------
#
# fetch | confirm | verify | mirror — spec §7:
# docs/superpowers/specs/2026-08-27-literature-asset-acquisition-design.md.
# All config is optional (spec §8.3): a missing 'literature' block, or a missing
# sub-key within it, means the shipped default.

_DEFAULT_REGISTRY_PATH = "docs/research/literature/references.json"
_DEFAULT_TRIAGE_PATH = "docs/research/literature/triage.yml"
_DEFAULT_MAX_BYTES = 52_428_800


def _lit_block(config: dict[str, Any]) -> dict[str, Any] | None:
    """Return the ``literature:`` config block, or exit 1 if it isn't a mapping.

    :param config: The loaded ``.defendable-science/config.yml``.
    :returns: The block, or ``None`` when unset.
    :raises typer.Exit: Code 1 if ``literature`` is present but not a mapping.
    """
    lit = config.get("literature")
    if lit is not None and not isinstance(lit, dict):
        typer.echo(
            "invalid .defendable-science/config.yml: 'literature' must be a mapping",
            err=True,
        )
        raise typer.Exit(code=1)
    return lit


def _lit_str(lit: dict[str, Any] | None, field_name: str, default: str) -> str:
    """Read a string ``literature.<field_name>`` override, or `default`.

    :param lit: The parsed ``literature:`` config block, or ``None``.
    :param field_name: The config key (``registry`` or ``triage``).
    :param default: The value to use when the key is absent.
    :returns: The configured value, or `default` when unset.
    :raises typer.Exit: Code 1 if the key is present but not a string.
    """
    raw = lit.get(field_name) if lit is not None else None
    if raw is None:
        return default
    if not isinstance(raw, str):
        typer.echo(
            f"invalid .defendable-science/config.yml: 'literature.{field_name}' "
            "must be a string",
            err=True,
        )
        raise typer.Exit(code=1)
    return raw


def _lit_registry_paths(lit: dict[str, Any] | None) -> tuple[Path, Path]:
    """Resolve ``literature.registry`` / ``literature.triage`` (spec §8.3).

    :param lit: The parsed ``literature:`` config block, or ``None``.
    :returns: ``(registry_path, triage_path)``.
    :raises typer.Exit: Code 1 if either key is present but not a string.
    """
    registry = _lit_str(lit, "registry", _DEFAULT_REGISTRY_PATH)
    triage = _lit_str(lit, "triage", _DEFAULT_TRIAGE_PATH)
    return Path(registry), Path(triage)


def _lit_cache_dir(config: dict[str, Any]) -> Path:
    """Return the literature content-addressed cache dir, under the cache root.

    :param config: The loaded configuration mapping.
    :returns: ``<cache_root>/literature`` (see :func:`_cache_root`).
    """
    return _cache_root(config) / "literature"


def _lit_acquisition(lit: dict[str, Any] | None) -> tuple[int, list[Any]]:
    """Read ``literature.acquisition.{max_bytes,venue_resolvers}`` (spec §8.3).

    :param lit: The parsed ``literature:`` config block, or ``None``.
    :returns: ``(max_bytes, venue_resolvers)``.
    :raises typer.Exit: Code 1 if ``literature.acquisition`` is present but not
        a mapping, or either sub-key has the wrong shape.
    """
    raw = lit.get("acquisition") if lit is not None else None
    if raw is None:
        return _DEFAULT_MAX_BYTES, []
    if not isinstance(raw, dict):
        typer.echo(
            "invalid .defendable-science/config.yml: 'literature.acquisition' "
            "must be a mapping",
            err=True,
        )
        raise typer.Exit(code=1)
    max_bytes = raw.get("max_bytes", _DEFAULT_MAX_BYTES)
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool):
        typer.echo(
            "invalid .defendable-science/config.yml: "
            "'literature.acquisition.max_bytes' must be an integer",
            err=True,
        )
        raise typer.Exit(code=1)
    resolvers = raw.get("venue_resolvers", [])
    if not isinstance(resolvers, list):
        typer.echo(
            "invalid .defendable-science/config.yml: "
            "'literature.acquisition.venue_resolvers' must be a list",
            err=True,
        )
        raise typer.Exit(code=1)
    return max_bytes, resolvers


def _lit_mirror(lit: dict[str, Any] | None) -> Mirror | None:
    """Build the literature :class:`Mirror` from ``literature.mirror`` config.

    Any ``RCLONE_CONFIG_<REMOTE>_*`` credentials in the key store (or
    environment) for this remote are handed to rclone as a scoped, in-memory
    ``env`` (ADR-0029), matching the ``dataset`` mirror's own construction.

    :param lit: The parsed ``literature:`` config block, or ``None``.
    :returns: The configured mirror, or ``None`` when ``literature.mirror`` is
        unset.
    :raises typer.Exit: Code 1 if ``literature.mirror`` is present but not a
        mapping with a ``remote`` string, or ``base_path`` is present but not
        a string.
    """
    raw = lit.get("mirror") if lit is not None else None
    if raw is None:
        return None
    remote = raw.get("remote") if isinstance(raw, dict) else None
    if not isinstance(remote, str) or not remote:
        typer.echo(
            "invalid .defendable-science/config.yml: 'literature.mirror' must "
            "be a mapping with a 'remote' string",
            err=True,
        )
        raise typer.Exit(code=1)
    base_path = raw.get("base_path")
    if base_path is not None and not isinstance(base_path, str):
        typer.echo(
            "invalid .defendable-science/config.yml: "
            "'literature.mirror.base_path' must be a string",
            err=True,
        )
        raise typer.Exit(code=1)
    scoped = keys_mod.rclone_scoped_env(remote)
    return Mirror(
        remote=remote,
        base_path=base_path or "",
        config_path=".defendable-science/rclone.conf",
        env=scoped or None,
    )


def _lit_context() -> acquire_mod.Context:
    """Build the acquisition :class:`~defendable_science.literature.acquire.Context`.

    Reads ``literature.registry``, ``literature.triage``, ``literature.mirror``
    and ``literature.acquisition.{max_bytes,venue_resolvers}`` from
    ``.defendable-science/config.yml`` (spec §8.3; all keys optional). The
    HTTP client comes from :func:`_lit_client`, matching every other
    ``literature`` command (tests monkeypatch it to inject a fake).

    :returns: The context, ready for :func:`~defendable_science.literature.acquire.fetch_all`
        or a single-entry acquisition call.
    :raises typer.Exit: Code 1 on any malformed ``literature.*`` config key.
    """
    config = _load_config_or_exit()
    lit = _lit_block(config)
    registry_path, triage_path = _lit_registry_paths(lit)
    max_bytes, resolvers = _lit_acquisition(lit)
    return acquire_mod.Context(
        registry_path=registry_path,
        triage_path=triage_path,
        cache_dir=_lit_cache_dir(config),
        mirror=_lit_mirror(lit),
        client=_lit_client(),
        fetcher=stream_to_file,
        max_bytes=max_bytes,
        resolvers=resolvers,
        today=date_cls.today().isoformat(),
    )


def _load_registry_or_exit(path: Path) -> registry_mod.Registry:
    """Load the registry, exiting 1 on a :class:`RegistryError`.

    :param path: The registry path (``literature.registry``).
    :returns: The loaded registry.
    :raises typer.Exit: Code 1 if the registry is missing or unparsable.
    """
    try:
        return registry_mod.load_registry(path)
    except registry_mod.RegistryError as exc:
        typer.echo(f"registry error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _lit_entry_or_exit(
    registry: registry_mod.Registry, citekey: str
) -> registry_mod.Entry:
    """Look up a citekey, exiting 1 if it's unknown.

    :param registry: The loaded registry.
    :param citekey: The CSL ``id`` to look up.
    :returns: The entry.
    :raises typer.Exit: Code 1 if `citekey` is not in the registry.
    """
    entry = registry.get(citekey)
    if entry is None:
        typer.echo(f"no entry {citekey!r} in the registry", err=True)
        raise typer.Exit(code=1)
    return entry


def _one_of_citekey_or_all(citekey: str, all_flag: bool) -> list[str] | None:
    """Enforce 'exactly one of CITEKEY or --all', resolving the sweep's targets.

    :param citekey: The positional citekey, or ``""`` when omitted.
    :param all_flag: Whether ``--all`` was given.
    :returns: ``[citekey]`` to attempt a single entry, or ``None`` for the
        whole registry (``--all``).
    :raises typer.Exit: Code 2 if neither, or both, were given.
    """
    if bool(citekey) == all_flag:
        typer.echo(
            "give exactly one of CITEKEY or --all, not neither or both", err=True
        )
        raise typer.Exit(code=2)
    return None if all_flag else [citekey]


def _fetch_report_exit_code(report: dict[str, Any]) -> int:
    """Return the sweep's exit code from its report.

    :param report: The report returned by
        :func:`~defendable_science.literature.acquire.fetch_all`.
    :returns: ``1`` when ``errors`` is non-empty or ``complete`` is false — so
        no agent or CI loop reads a half-swept registry as a finished one;
        ``0`` otherwise.
    """
    if report.get("errors") or not report.get("complete", True):
        return 1
    return 0


@literature.command(name="fetch")
def lit_fetch(
    citekey: Annotated[
        str, typer.Argument(help="The citekey to fetch (omit with --all).")
    ] = "",
    fetch_all: Annotated[
        bool, typer.Option("--all", help="Sweep every entry in the registry.")
    ] = False,
    disposition: Annotated[
        str | None,
        typer.Option(
            "--disposition",
            help="Restrict --all to entries with this triage.yml disposition.",
        ),
    ] = None,
    refetch: Annotated[
        bool,
        typer.Option(
            "--refetch", help="Re-run the ladder for an already-acquired entry."
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Report the rung that would land; write nothing."
        ),
    ] = False,
) -> None:
    """Acquire the PDF for one registry entry, or sweep the registry with ``--all``.

    Prints the sweep report (spec §7) as JSON: ``complete``, ``not_attempted``,
    and the ``fetched`` / ``cached`` / ``quarantined`` / ``manual`` /
    ``committable`` / ``errors`` buckets.

    :param citekey: The citekey to fetch; give exactly one of this or `fetch_all`.
    :param fetch_all: Sweep every registry entry (optionally narrowed by
        `disposition`).
    :param disposition: Restrict `fetch_all` to entries whose ``triage.yml``
        row carries this disposition. Naming `citekey` explicitly *and* giving
        this is a conflict, reported as an ``errors[]`` row, not a silent
        omission.
    :param refetch: Re-run the acquisition ladder even for an entry with a
        recorded checksum; drift refuses rather than rebinding.
    :param dry_run: Report which rung would yield bytes without downloading or
        writing anything.
    :raises typer.Exit: Code 2 if neither, or both, of `citekey`/`fetch_all`
        are given. Code 1 if the registry or triage sidecar can't be read, the
        mirror transport fails (e.g. a missing ``rclone``), a metadata lookup
        is rate-limited or fails, or the sweep's report carries any
        ``errors[]`` row or is incomplete. Code 0 on a clean, complete sweep.
    """
    citekeys = _one_of_citekey_or_all(citekey, fetch_all)
    ctx = _lit_context()
    with _http_guard(ctx.client):
        try:
            report = acquire_mod.fetch_all(
                ctx,
                citekeys=citekeys,
                disposition=disposition,
                refetch=refetch,
                dry_run=dry_run,
            )
        except registry_mod.RegistryError as exc:
            typer.echo(f"fetch failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        except RetrievalError as exc:
            typer.echo(f"fetch failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(report, indent=2))
    raise typer.Exit(code=_fetch_report_exit_code(report))


@literature.command(name="confirm")
def lit_confirm(
    citekey: str,
    sha256: Annotated[
        str,
        typer.Option("--sha256", help="Promote this quarantined checksum."),
    ] = "",
    file: Annotated[
        str,
        typer.Option("--file", help="Adopt this manually downloaded PDF (copied)."),
    ] = "",
) -> None:
    """Promote a quarantined candidate, or adopt a manually downloaded PDF.

    ``--sha256`` moves a quarantined blob into the content-addressed store
    after human review. ``--file`` copies (never moves) a human-supplied PDF,
    recording ``rung: manual`` and an empty, non-redistributable license —
    this closes the ``manual[]`` worklist a fetch sweep leaves behind
    (spec §7).

    :param citekey: The registry entry to bind the bytes to.
    :param sha256: The checksum naming a quarantined candidate to promote;
        give exactly one of this or `file`.
    :param file: Path to a human-downloaded PDF to adopt.
    :raises typer.Exit: Code 2 if neither, or both, of `sha256`/`file` are
        given. Code 1 if `citekey` is unknown, the quarantine lookup fails
        (an unknown checksum, an unreadable file), or the outcome itself is an
        error (a tampered quarantine blob, a non-PDF adoption). Code 0 on a
        successful promotion or adoption.
    """
    if bool(sha256) == bool(file):
        typer.echo(
            "give exactly one of --sha256 or --file, not neither or both", err=True
        )
        raise typer.Exit(code=2)
    ctx = _lit_context()
    registry = _load_registry_or_exit(ctx.registry_path)
    entry = _lit_entry_or_exit(registry, citekey)
    try:
        if sha256:
            outcome = acquire_mod.confirm_quarantined(entry, ctx, sha256)
        else:
            outcome = acquire_mod.adopt_file(entry, ctx, Path(file))
    except RetrievalError as exc:
        typer.echo(f"confirm failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(outcome.as_json(), indent=2))
    raise typer.Exit(code=1 if outcome.bucket == acquire_mod.BUCKET_ERROR else 0)


@literature.command(name="verify")
def lit_verify(
    citekey: Annotated[
        str, typer.Argument(help="The citekey to verify (omit with --all).")
    ] = "",
    verify_all: Annotated[
        bool, typer.Option("--all", help="Verify every entry in the registry.")
    ] = False,
) -> None:
    """Re-hash on-disk bytes against the registry's recorded checksum(s).

    Offline — this never downloads, matching ``dataset verify``'s contract.
    An entry with no recorded asset is reported as ``missing`` with an
    explicit note, never as ``ok``: an unfetched paper must not read as
    verified.

    :param citekey: The citekey to verify; give exactly one of this or
        `verify_all`.
    :param verify_all: Verify every entry in the registry.
    :raises typer.Exit: Code 2 if neither, or both, of `citekey`/`verify_all`
        are given. Code 1 if the registry can't be read, `citekey` is
        unknown, or any report is not ``ok``. Code 0 when every report is
        ``ok``.
    """
    citekeys = _one_of_citekey_or_all(citekey, verify_all)
    config = _load_config_or_exit()
    lit = _lit_block(config)
    registry_path, _triage_path = _lit_registry_paths(lit)
    cache_dir = _lit_cache_dir(config)
    registry = _load_registry_or_exit(registry_path)
    if citekeys is not None:
        entries = [_lit_entry_or_exit(registry, citekeys[0])]
    else:
        entries = list(registry.entries)
    reports = [acquire_mod.verify_entry(e, cache_dir=cache_dir) for e in entries]
    output: Any = (
        reports[0].as_json() if citekeys is not None else [r.as_json() for r in reports]
    )
    typer.echo(json.dumps(output, indent=2))
    raise typer.Exit(code=0 if all(r.ok for r in reports) else 1)


@literature.command(name="mirror")
def lit_mirror(
    citekey: Annotated[
        str, typer.Argument(help="The citekey to mirror (omit with --all).")
    ] = "",
    mirror_all: Annotated[
        bool, typer.Option("--all", help="Mirror every entry in the registry.")
    ] = False,
    check: Annotated[
        bool,
        typer.Option("--check", help="Probe mirror presence; never push."),
    ] = False,
) -> None:
    """Push a registry entry's recorded file(s) to the mirror, or probe with ``--check``.

    A local blob is re-hashed before it is pushed; a mismatch is reported as
    ``corrupt`` rather than ``missing``, since the human's next action differs
    (investigate the local copy, most likely via ``fetch --refetch``, rather
    than simply retrying the push).

    :param citekey: The citekey to mirror; give exactly one of this or
        `mirror_all`.
    :param mirror_all: Mirror every entry in the registry.
    :param check: Probe mirror presence without pushing anything.
    :raises typer.Exit: Code 2 if neither, or both, of `citekey`/`mirror_all`
        are given. Code 1 if ``literature.mirror`` is not configured, the
        registry can't be read, `citekey` is unknown, the mirror transport
        fails (e.g. a missing ``rclone``), or any file ends up ``missing`` or
        ``corrupt``. Code 0 when every file is ``pushed`` or
        ``already_present``.
    """
    citekeys = _one_of_citekey_or_all(citekey, mirror_all)
    config = _load_config_or_exit()
    lit = _lit_block(config)
    registry_path, _triage_path = _lit_registry_paths(lit)
    cache_dir = _lit_cache_dir(config)
    mir = _lit_mirror(lit)
    if mir is None:
        typer.echo(
            "no 'literature.mirror' configured in .defendable-science/config.yml",
            err=True,
        )
        raise typer.Exit(code=1)
    registry = _load_registry_or_exit(registry_path)
    try:
        if citekeys is not None:
            entries = [_lit_entry_or_exit(registry, citekeys[0])]
        else:
            entries = list(registry.entries)
        reports = [
            acquire_mod.mirror_entry(
                e, cache_dir=cache_dir, mirror=mir, check_only=check
            )
            for e in entries
        ]
    except RetrievalError as exc:
        typer.echo(f"mirror failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    output: Any = reports[0] if citekeys is not None else reports
    typer.echo(json.dumps(output, indent=2))
    ok = all(not r["missing"] and not r["corrupt"] for r in reports)
    raise typer.Exit(code=0 if ok else 1)


# --- dataset (defendable-science#2 manifest / #3 retrieval) ---------------------------
dataset = typer.Typer(
    help="Dataset manifest, retrieval and mirroring.", no_args_is_help=True
)
app.add_typer(dataset, name="dataset")


@dataset.command()
def validate(
    manifest: Annotated[
        str, typer.Argument(help="Path to the manifest to validate.")
    ] = "datasets.yml",
) -> None:
    """Validate a ``datasets.yml`` manifest (the register/audit gate).

    Prints a JSON report ``{ok, errors, warnings}`` and exits non-zero on any
    hard error.

    :param manifest: Path to the manifest to validate.
    :raises typer.Exit: Code 1 on a malformed manifest or any validation error.
    """
    try:
        parsed = manifest_mod.load(manifest)
    except manifest_mod.ManifestError as exc:
        typer.echo(json.dumps({"ok": False, "errors": [str(exc)], "warnings": []}))
        raise typer.Exit(code=1) from exc
    report = manifest_mod.validate(parsed)
    typer.echo(
        json.dumps(
            {"ok": report.ok, "errors": report.errors, "warnings": report.warnings},
            indent=2,
        )
    )
    raise typer.Exit(code=0 if report.ok else 1)


@dataset.command()
def ingest(croissant: str) -> None:
    """Ingest a published Croissant JSON-LD file to bootstrap a draft entry.

    Prints the draft registry entry as JSON, with the human-owned fields it could
    not fill listed under ``_needs_human`` (the caller confirms them on register).

    :param croissant: Path to the Croissant JSON-LD file.
    :raises typer.Exit: Code 1 if the file is unreadable or has no ``name``.
    """
    try:
        doc = json.loads(Path(croissant).read_text(encoding="utf-8"))
        entry = manifest_mod.entry_from_croissant(doc)
    except (OSError, json.JSONDecodeError, manifest_mod.ManifestError) as exc:
        typer.echo(f"ingest failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    draft = dataclasses.asdict(entry)
    draft["_needs_human"] = [
        name
        for name in ("license", "tier", "access", "datasheet", "sensitivity")
        if draft.get(name) is None
    ]
    typer.echo(json.dumps(draft, indent=2))
    raise typer.Exit(code=0)


@dataset.command()
def emit(
    identifier: Annotated[
        str, typer.Argument(help="The dataset id to emit (omit with --all).")
    ] = "",
    emit_all: Annotated[
        bool, typer.Option("--all", help="Emit every entry as a JSON array.")
    ] = False,
    manifest: Annotated[
        str, typer.Option(help="Path to the manifest to read.")
    ] = "datasets.yml",
) -> None:
    """Emit a Croissant JSON-LD document for a manifest entry (or all entries).

    :param identifier: The dataset id to emit; omit when using ``--all``.
    :param emit_all: Emit every registry entry as a JSON array.
    :param manifest: Path to the manifest to read.
    :raises typer.Exit: Code 1 if the manifest is malformed, no id/``--all`` is
        given, or the id is unknown.
    """
    try:
        parsed = manifest_mod.load(manifest)
    except manifest_mod.ManifestError as exc:
        typer.echo(f"emit failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if emit_all:
        docs = [manifest_mod.croissant_for(e) for e in parsed.datasets]
        typer.echo(json.dumps(docs, indent=2))
        raise typer.Exit(code=0)
    if not identifier:
        typer.echo("emit: give a dataset id or --all", err=True)
        raise typer.Exit(code=1)
    for entry in parsed.datasets:
        if entry.id == identifier:
            typer.echo(json.dumps(manifest_mod.croissant_for(entry), indent=2))
            raise typer.Exit(code=0)
    typer.echo(f"emit failed: no entry with id {identifier!r}", err=True)
    raise typer.Exit(code=1)


def _dataset_cache_dir() -> Path:
    """Return the dataset content-addressed cache dir, under the cache root.

    :returns: ``<cache_root>/datasets`` (see :func:`_cache_root`).
    """
    return _cache_root() / "datasets"


def _load_manifest_or_exit(path: str) -> manifest_mod.Manifest:
    """Load a manifest, exiting 1 on a malformed file."""
    try:
        return manifest_mod.load(path)
    except manifest_mod.ManifestError as exc:
        typer.echo(f"manifest error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _entry_or_exit(
    parsed: manifest_mod.Manifest, identifier: str
) -> manifest_mod.DatasetEntry:
    """Find an entry by id, exiting 1 if unknown."""
    for entry in parsed.datasets:
        if entry.id == identifier:
            return entry
    typer.echo(f"no dataset with id {identifier!r}", err=True)
    raise typer.Exit(code=1)


def _mirror_from(parsed: manifest_mod.Manifest) -> retrieval_mod.Mirror | None:
    """Build a :class:`Mirror` from the manifest's mirror block, if configured.

    Any ``RCLONE_CONFIG_<REMOTE>_*`` credentials in the key store (or environment)
    for this remote are handed to rclone as a scoped, in-memory ``env`` (ADR-0029);
    a hand-managed ``.defendable-science/rclone.conf`` still works as a fallback.
    """
    mir = parsed.mirror
    if mir is None or not mir.rclone_remote:
        return None
    scoped = keys_mod.rclone_scoped_env(mir.rclone_remote)
    return retrieval_mod.Mirror(
        remote=mir.rclone_remote,
        base_path=mir.base_path or "",
        config_path=".defendable-science/rclone.conf",
        env=scoped or None,
    )


@dataset.command()
def fetch(
    identifier: str,
    manifest: Annotated[
        str, typer.Option(help="Path to the manifest.")
    ] = "datasets.yml",
) -> None:
    """Fetch a registered dataset through the resolution chain (pooch/rclone).

    :param identifier: The dataset id to fetch.
    :param manifest: Path to the manifest.
    :raises typer.Exit: Code 1 if the id is unknown or the chain is exhausted.
    """
    parsed = _load_manifest_or_exit(manifest)
    entry = _entry_or_exit(parsed, identifier)
    try:
        paths = retrieval_mod.fetch(
            entry, cache_dir=_dataset_cache_dir(), mirror=_mirror_from(parsed)
        )
    except retrieval_mod.RetrievalError as exc:
        typer.echo(f"fetch failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps([str(p) for p in paths], indent=2))
    raise typer.Exit(code=0)


@dataset.command()
def verify(
    identifier: str,
    manifest: Annotated[
        str, typer.Option(help="Path to the manifest.")
    ] = "datasets.yml",
) -> None:
    """Verify on-disk bytes against the manifest SHA-256 (offline).

    :param identifier: The dataset id to verify.
    :param manifest: Path to the manifest.
    :raises typer.Exit: Code 1 if the id is unknown or a file fails to verify.
    """
    parsed = _load_manifest_or_exit(manifest)
    entry = _entry_or_exit(parsed, identifier)
    report = retrieval_mod.verify(entry, cache_dir=_dataset_cache_dir())
    typer.echo(json.dumps(dataclasses.asdict(report) | {"ok": report.ok}, indent=2))
    raise typer.Exit(code=0 if report.ok else 1)


@dataset.command()
def mirror(
    identifier: str,
    manifest: Annotated[
        str, typer.Option(help="Path to the manifest.")
    ] = "datasets.yml",
) -> None:
    """Populate/refresh the private rclone mirror for a dataset.

    :param identifier: The dataset id to mirror.
    :param manifest: Path to the manifest.
    :raises typer.Exit: Code 1 if no mirror is configured or a hop fails.
    """
    parsed = _load_manifest_or_exit(manifest)
    entry = _entry_or_exit(parsed, identifier)
    mir = _mirror_from(parsed)
    if mir is None:
        typer.echo("no mirror configured in the manifest", err=True)
        raise typer.Exit(code=1)
    try:
        paths = retrieval_mod.fetch(entry, cache_dir=_dataset_cache_dir(), mirror=mir)
        for path, ref in zip(paths, entry.files, strict=True):
            mir.put(path, ref.sha256)
    except retrieval_mod.RetrievalError as exc:
        typer.echo(f"mirror failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps({"mirrored": entry.id, "files": len(entry.files)}, indent=2))
    raise typer.Exit(code=0)


@dataset.command()
def audit(
    identifier: Annotated[
        str, typer.Argument(help="Optional dataset id; whole manifest if omitted.")
    ] = "",
    manifest: Annotated[
        str, typer.Option(help="Path to the manifest.")
    ] = "datasets.yml",
) -> None:
    """Audit fixity, mirror presence and manifest completeness.

    :param identifier: Optional dataset id; audits the whole manifest if omitted.
    :param manifest: Path to the manifest.
    :raises typer.Exit: Code 1 if validation or any fixity check fails.
    """
    parsed = _load_manifest_or_exit(manifest)
    if identifier:
        entry = _entry_or_exit(parsed, identifier)
        parsed = manifest_mod.Manifest(mirror=parsed.mirror, datasets=[entry])
    report = retrieval_mod.audit(
        parsed, cache_dir=_dataset_cache_dir(), mirror=_mirror_from(parsed)
    )
    typer.echo(
        json.dumps(
            {
                "ok": report.ok,
                "validation": {
                    "ok": report.validation.ok,
                    "errors": report.validation.errors,
                    "warnings": report.validation.warnings,
                },
                "fixity": [dataclasses.asdict(f) for f in report.fixity],
                "mirror_present": report.mirror_present,
            },
            indent=2,
        )
    )
    raise typer.Exit(code=0 if report.ok else 1)


# --- defend (defendable-science#4, defendable-science#68) ----------------------------------
defend = typer.Typer(help="Defensibility record helpers.", no_args_is_help=True)
app.add_typer(defend, name="defend")


def _parse_acks(acks: str) -> list[dict[str, str]]:
    """Parse ``"gap::by||gap2::by2"`` into per-gap acknowledgement dicts."""
    result: list[dict[str, str]] = []
    for item in filter(None, (a.strip() for a in acks.split("||"))):
        gap, _, by = item.partition("::")
        result.append({"gap": gap.strip(), "by": by.strip()})
    return result


def _parse_points(raw: str) -> list[record_mod.PointRecord]:
    """Parse a JSON array of point-record objects into ``PointRecord``s (ADR-0033).

    :param raw: JSON text: ``[{"point": ..., "source_quote": ..., "reader_answer":
        ..., "resolved": ..., "location": ..., "gap_note": ...}, ...]`` —
        ``location``/``gap_note`` are optional per item; empty input means no
        points.
    :raises record_mod.RecordError: If `raw` isn't a JSON array of point objects
        with the expected fields and field types.
    """
    if not raw.strip():
        return []
    try:
        data: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise record_mod.RecordError(f"--points is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise record_mod.RecordError("--points must be a JSON array")
    points: list[record_mod.PointRecord] = []
    for item in data:
        if not isinstance(item, dict):
            raise record_mod.RecordError("--points item must be a JSON object")
        points.append(record_mod.point_record_from_mapping(item))
    return points


@defend.command()
def record(
    artifact: Annotated[
        str, typer.Option("--artifact", help="Target markdown artifact.")
    ],
    target: Annotated[
        str,
        typer.Option(
            "--target", help="claim | cited-work | methodology | paper-comprehension."
        ),
    ],
    points: Annotated[
        str,
        typer.Option(
            "--points",
            help="Point records: a JSON-array file path, or '-' for stdin.",
        ),
    ] = "",
    signed_off_by: Annotated[str, typer.Option("--signed-off-by")] = "",
    override: Annotated[bool, typer.Option("--override")] = False,
    acks: Annotated[
        str, typer.Option("--acks", help="Per-gap sign-offs, 'gap::name||…'.")
    ] = "",
    transcript: Annotated[
        str, typer.Option("--transcript", help="Transcript file, or '-' for stdin.")
    ] = "",
    log_dir: Annotated[str, typer.Option("--log-dir")] = str(
        record_mod.DEFAULT_LOG_DIR
    ),
) -> None:
    """Record a ``defend``/``digest`` examination: patch understanding + log.

    Writes ``status.understanding`` into the artifact frontmatter and appends the
    full evidentiary point record (ADR-0033) to the accountability log. Records
    observed facts only — never a verdict, score, or answer key.

    :param artifact: The examined markdown artifact.
    :param target: ``claim`` / ``cited-work`` / ``methodology`` /
        ``paper-comprehension``.
    :param points: Point records — a JSON-array file path, or ``-`` for stdin;
        empty means none.
    :param signed_off_by: Named human; required when gaps are waved through.
    :param override: A blanket logged override of the surfaced gaps.
    :param acks: Per-gap acknowledgements, ``gap::name``, ``||``-separated.
    :param transcript: Transcript file path, or ``-`` for stdin.
    :param log_dir: Directory for the accountability log.
    :raises typer.Exit: Code 1 on a guard violation or malformed artifact/input.
    """
    try:
        transcript_text: str | None = None
        if transcript == "-":
            transcript_text = sys.stdin.read()
        elif transcript:
            # Inside the try so an unreadable transcript exits 1 cleanly rather
            # than tracebacking (it is an ``OSError`` like the other read paths).
            transcript_text = Path(transcript).read_text(encoding="utf-8")
        points_text = ""
        if points == "-":
            points_text = sys.stdin.read()
        elif points:
            points_text = Path(points).read_text(encoding="utf-8")
        point_list = _parse_points(points_text)
        result = record_mod.record(
            artifact,
            target,
            point_list,
            signed_off_by=signed_off_by or None,
            override=override,
            acknowledgements=_parse_acks(acks),
            transcript=transcript_text,
            log_dir=log_dir,
        )
    except (record_mod.RecordError, OSError) as exc:
        typer.echo(f"defend record failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        json.dumps(
            {
                "outcome": result.outcome,
                "artifact": str(result.artifact),
                "log_entry": str(result.log_entry),
                "transcript": str(result.transcript) if result.transcript else None,
            },
            indent=2,
        )
    )
    raise typer.Exit(code=0)


# --- backlog (defendable-science#5) ---------------------------------------------------
backlog = typer.Typer(help="Exploration backlog management.", no_args_is_help=True)
app.add_typer(backlog, name="backlog")

_BacklogPath = Annotated[str, typer.Option("--backlog", help="Path to the backlog.")]
_LevelOpt = Annotated[str, typer.Option("--level", help="hypothesis | paper.")]


def _open_backlog(path: str, level: str) -> backlog_mod.Backlog:
    """Validate `level` and load the backlog at `path`.

    :raises typer.Exit: Code 2 on an invalid level.
    """
    if level not in ("hypothesis", "paper"):
        typer.echo(f"--level must be 'hypothesis' or 'paper', got {level!r}", err=True)
        raise typer.Exit(code=2)
    return backlog_mod.Backlog.load(path, level)  # type: ignore[arg-type]


def _emit_row(row: dict[str, str]) -> None:
    """Print one backlog row as JSON and exit 0."""
    typer.echo(json.dumps(row, indent=2))
    raise typer.Exit(code=0)


@backlog.command()
def park(
    one_line: str,
    provenance: Annotated[str, typer.Option("--provenance", help="Origin, verbatim.")],
    backlog_path: _BacklogPath = "backlog.md",
    level: _LevelOpt = "hypothesis",
    row_id: Annotated[str, typer.Option("--id", help="Explicit row id.")] = "",
) -> None:
    """Park a raw one-line idea as a ``parked`` backlog row.

    :param one_line: The one-line idea.
    :param provenance: Its origin (verbatim); required.
    :param backlog_path: Path to the backlog table.
    :param level: Backlog level (``hypothesis`` or ``paper``).
    :param row_id: Optional explicit id.
    :raises typer.Exit: Code 1 on a guard violation.
    """
    board = _open_backlog(backlog_path, level)
    try:
        row = board.park(one_line, provenance, row_id=row_id or None)
    except backlog_mod.BacklogError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    board.save(backlog_path)
    _emit_row(row)


@backlog.command()
def add(
    one_line: str,
    provenance: Annotated[str, typer.Option("--provenance", help="Origin, verbatim.")],
    backlog_path: _BacklogPath = "backlog.md",
    level: _LevelOpt = "hypothesis",
    row_id: Annotated[str, typer.Option("--id", help="Explicit row id.")] = "",
) -> None:
    """Add a ``candidate`` row (realizes the ``generate`` verb).

    :param one_line: The one-line idea.
    :param provenance: Its origin (verbatim); required.
    :param backlog_path: Path to the backlog table.
    :param level: Backlog level (``hypothesis`` or ``paper``).
    :param row_id: Optional explicit id.
    :raises typer.Exit: Code 1 on a guard violation.
    """
    board = _open_backlog(backlog_path, level)
    try:
        row = board.add(one_line, provenance, row_id=row_id or None)
    except backlog_mod.BacklogError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    board.save(backlog_path)
    _emit_row(row)


@backlog.command(name="list")
def list_(
    backlog_path: _BacklogPath = "backlog.md",
    level: _LevelOpt = "hypothesis",
    status: Annotated[str, typer.Option("--status", help="Filter by status.")] = "",
) -> None:
    """List backlog rows as JSON (read-only), optionally filtered by status.

    :param backlog_path: Path to the backlog table.
    :param level: Backlog level.
    :param status: Optional status filter.
    """
    board = _open_backlog(backlog_path, level)
    rows = board.listing(status=status or None)
    typer.echo(json.dumps(rows, indent=2))
    raise typer.Exit(code=0)


@backlog.command()
def rank(
    row_id: str,
    backlog_path: _BacklogPath = "backlog.md",
    level: _LevelOpt = "hypothesis",
    eig: Annotated[str, typer.Option("--eig")] = "",
    feas: Annotated[str, typer.Option("--feas")] = "",
    interest: Annotated[str, typer.Option("--interest")] = "",
    frame: Annotated[str, typer.Option("--frame")] = "",
) -> None:
    """Score a row and set it ``ranked`` (advises; never selects).

    :param row_id: The row to rank.
    :param backlog_path: Path to the backlog table.
    :param level: Backlog level.
    :param eig: Expected-information-gain score (hypothesis level).
    :param feas: Feasibility score.
    :param interest: Interest score.
    :param frame: gap-spotting / problematization (hypothesis level).
    :raises typer.Exit: Code 1 on a guard violation.
    """
    board = _open_backlog(backlog_path, level)
    scores = {
        k: v
        for k, v in (
            ("EIG", eig),
            ("feas", feas),
            ("interest", interest),
            ("frame", frame),
        )
        if v
    }
    try:
        row = board.rank(row_id, **scores)
    except backlog_mod.BacklogError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    board.save(backlog_path)
    _emit_row(row)


def _check_scaffold_opts(
    level: str, paper_root: str, research: str, backend: str
) -> None:
    """Validate the ``--scaffold`` option combination for `level`.

    :param level: The validated backlog level.
    :param paper_root: ``--paper-root`` (hypothesis level).
    :param research: ``--research-root`` (paper level).
    :param backend: ``--backend`` (paper level).
    :raises typer.Exit: Code 2 if an option this level requires is missing.
    """
    if level == "hypothesis":
        needed = {"--paper-root": paper_root}
    else:
        # ``backend`` has no default: the plugin ships no experiment backend, so
        # a registry row with an empty binding is not a usable paper (ADR-0013).
        needed = {"--research-root": research, "--backend": backend}
    missing = sorted(name for name, value in needed.items() if not value)
    if missing:
        typer.echo(
            f"--scaffold at the {level} level requires {', '.join(missing)}", err=True
        )
        raise typer.Exit(code=2)


def _scaffold_promoted(
    level: str,
    row: dict[str, str],
    *,
    paper_root: str,
    research: str,
    backend: str,
    slug: str,
    date: str,
) -> dict[str, str]:
    """Scaffold the next-stage artifact for a just-promoted `row`.

    :param level: The validated backlog level.
    :param row: The promoted row, whose ``one-line``/``provenance`` are carried
        into the artifact verbatim.
    :param paper_root: The paper root (hypothesis level).
    :param research: The ``docs/research`` directory (paper level).
    :param backend: The experiment-backend binding to record (paper level).
    :param slug: Explicit hypothesis folder name; ``<date>-<row-id>`` otherwise.
    :param date: ISO date for the folder name and ``last-updated``.
    :returns: The created paths, keyed for the caller's JSON report.
    :raises backlog_mod.BacklogError: If a target artifact already exists.
    """
    today = date or backlog_mod.today_iso()
    if level == "hypothesis":
        target = backlog_mod.scaffold_hypothesis(
            paper_root,
            slug or f"{today}-{row['id']}",
            row["one-line"],
            row["provenance"],
            today=today,
        )
        return {"hypothesis": str(target)}
    root = backlog_mod.scaffold_paper(
        research,
        row["id"],
        row["one-line"],
        backend=backend,
        provenance=row["provenance"],
        today=today,
    )
    return {
        "paper_root": str(root),
        "pitch": str(root / "paper" / "pitch.md"),
        "backlog": str(root / "backlog.md"),
        "registry": str(Path(research) / "papers.md"),
    }


@backlog.command()
def promote(
    row_id: str,
    backlog_path: _BacklogPath = "backlog.md",
    level: _LevelOpt = "hypothesis",
    scaffold: Annotated[
        bool,
        typer.Option("--scaffold", help="Also scaffold the next-stage artifact."),
    ] = False,
    paper_root: Annotated[
        str,
        typer.Option("--paper-root", help="Paper root (hypothesis level scaffold)."),
    ] = "",
    research_root: Annotated[
        str,
        typer.Option("--research-root", help="docs/research dir (paper level)."),
    ] = "",
    backend: Annotated[
        str,
        typer.Option("--backend", help="Experiment-backend binding (paper level)."),
    ] = "",
    slug: Annotated[
        str,
        typer.Option("--slug", help="Hypothesis folder name; <date>-<id> otherwise."),
    ] = "",
    date: Annotated[
        str, typer.Option("--date", help="ISO date for the scaffold (default today).")
    ] = "",
) -> None:
    """Mark a ``ranked`` row ``promoted`` (an explicit human pick).

    Flips the row's status and saves the backlog. With ``--scaffold`` it also
    creates the next-stage artifact the row hands off to — the hypothesis folder
    at the hypothesis level, or the paper root plus its ``papers.md`` registry row
    at the paper level — and reports the created paths instead of the bare row.

    Scaffolding runs *before* the backlog is written, so a refused scaffold (the
    artifact already exists) leaves the row ``ranked`` and the operation
    retryable, never ``promoted`` with nothing on disk.

    :param row_id: The row to promote.
    :param backlog_path: Path to the backlog table.
    :param level: Backlog level.
    :param scaffold: Also scaffold the next-stage artifact.
    :param paper_root: The paper root; required with ``--scaffold`` at the
        hypothesis level.
    :param research_root: The ``docs/research`` directory; required with
        ``--scaffold`` at the paper level.
    :param backend: The experiment-backend binding; required with ``--scaffold``
        at the paper level (the plugin bundles no default).
    :param slug: Explicit ``<YYYY-MM-DD-slug>`` hypothesis folder name.
    :param date: ISO date for the folder name and ``last-updated``.
    :raises typer.Exit: Code 1 on a guard violation, code 2 on a missing option.
    """
    board = _open_backlog(backlog_path, level)
    if scaffold:
        _check_scaffold_opts(level, paper_root, research_root, backend)
    try:
        row = board.promote(row_id)
        artifacts = (
            _scaffold_promoted(
                level,
                row,
                paper_root=paper_root,
                research=research_root,
                backend=backend,
                slug=slug,
                date=date,
            )
            if scaffold
            else None
        )
    except backlog_mod.BacklogError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    board.save(backlog_path)
    if artifacts is None:
        _emit_row(row)
    typer.echo(json.dumps({"row": row, "artifacts": artifacts}, indent=2))
    raise typer.Exit(code=0)


@backlog.command()
def drop(
    row_id: str,
    reason: Annotated[str, typer.Option("--reason", help="Why it is dropped.")],
    backlog_path: _BacklogPath = "backlog.md",
    level: _LevelOpt = "hypothesis",
) -> None:
    """Retire a row as ``dropped`` with a recorded reason (never deletes it).

    :param row_id: The row to drop.
    :param reason: Why it is dropped; required (file-drawer discipline).
    :param backlog_path: Path to the backlog table.
    :param level: Backlog level.
    :raises typer.Exit: Code 1 on a guard violation.
    """
    board = _open_backlog(backlog_path, level)
    try:
        row = board.drop(row_id, reason)
    except backlog_mod.BacklogError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    board.save(backlog_path)
    _emit_row(row)


# --- keys (defendable-science#42) -----------------------------------------------------
keys = typer.Typer(
    help="Store, list and check API keys & credentials (ADR-0029).",
    no_args_is_help=True,
)
app.add_typer(keys, name="keys")


def _stdin_is_piped() -> bool:
    """Return whether stdin is a pipe/redirect rather than an interactive tty."""
    return not sys.stdin.isatty()


def _parse_json_object(raw: str) -> dict[str, object] | None:
    """Parse `raw` as a JSON object, or ``None`` if it is not one.

    :param raw: The raw stdin text.
    :returns: The decoded mapping, or ``None`` when `raw` is not valid JSON or is
        valid JSON but not an object (so it is treated as a single value).
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _warn_unknown(name: str) -> None:
    """Warn on stderr when `name` is not a recognised key (but still store it)."""
    if not keys_mod.is_known(name):
        typer.echo(f"warning: {name!r} is not a known key; storing it anyway", err=True)


def _warn_if_store_committable() -> None:
    """Warn on stderr when the resolved store sits in a non-gitignored repo.

    Defense-in-depth (defendable-science#66, ADR-0032): the default store lives
    outside any repo, but anyone who opts into :envvar:`STORE_PATH_ENV` — e.g.
    the legacy in-repo location — could otherwise commit a secret file without
    noticing. Warns and continues; the out-of-repo default is the real fix, so
    this never refuses.
    """
    resolved = keys_mod.store_path()
    if keys_mod.store_at_risk(resolved):
        typer.echo(
            f"warning: the key store at {resolved} is inside a git work tree and "
            "does not appear to be gitignored — a stored key here is committable; "
            "gitignore it, or unset "
            f"{keys_mod.STORE_PATH_ENV} to use the default out-of-repo store",
            err=True,
        )


def _set_many(blob: dict[str, object]) -> None:
    """Set every entry of a piped JSON object; never echoes a value.

    :param blob: The decoded ``{name: value}`` mapping.
    :raises typer.Exit: Code 2 if the object is empty or any value is not a string.
    """
    if not blob:
        typer.echo("keys set: the JSON object is empty", err=True)
        raise typer.Exit(code=2)
    _warn_if_store_committable()
    for name, value in blob.items():
        if not isinstance(value, str):
            typer.echo(f"keys set: value for {name!r} must be a string", err=True)
            raise typer.Exit(code=2)
        _warn_unknown(name)
        keys_mod.set_key(name, value)
    typer.echo(f"stored {len(blob)} key(s) (source: store)")


@keys.command(name="set")
def set_(
    name: Annotated[
        str, typer.Argument(help="Key name; omit only when piping a JSON object.")
    ] = "",
) -> None:
    """Store a key. The value comes from **stdin or a hidden prompt**, never argv.

    Piping a JSON object (``{"NAME": "value", ...}``) sets many at once. Unknown
    names warn but are still stored. No value is ever echoed.

    :param name: The key name (unused when a JSON object is piped).
    :raises typer.Exit: Code 2 on a missing name or an empty value; code 0 on
        success.
    """
    if _stdin_is_piped():
        raw = sys.stdin.read()
        blob = _parse_json_object(raw)
        if blob is not None:
            _set_many(blob)
            raise typer.Exit(code=0)
        value: str | None = raw.strip()
    else:
        value = None
    if not name:
        typer.echo(
            "keys set: provide NAME (or pipe a JSON object to set many)", err=True
        )
        raise typer.Exit(code=2)
    if value is None:
        value = getpass.getpass(f"Value for {name} (input hidden): ")
    if not value:
        typer.echo(f"keys set: empty value for {name}", err=True)
        raise typer.Exit(code=2)
    _warn_if_store_committable()
    _warn_unknown(name)
    keys_mod.set_key(name, value)
    typer.echo(f"stored {name} (source: store)")
    raise typer.Exit(code=0)


def _key_report() -> list[dict[str, object]]:
    """Build a presence report for every known + stored key — never a value.

    :returns: One record per key with ``name``, ``service``, ``benefit``,
        ``how_to_obtain``, ``present`` and ``source`` (``env``/``store``/``None``).
    """
    report: list[dict[str, object]] = []
    seen: set[str] = set()
    for known in keys_mod.KNOWN_KEYS.values():
        source = keys_mod.source_of(known.name)
        report.append(
            {
                "name": known.name,
                "service": known.service,
                "benefit": known.benefit,
                "how_to_obtain": known.how_to_obtain,
                "present": source is not None,
                "source": source,
            }
        )
        seen.add(known.name)
    report.extend(
        {
            "name": name,
            "service": None,
            "benefit": None,
            "how_to_obtain": None,
            "present": True,
            "source": keys_mod.source_of(name),
        }
        for name in sorted(keys_mod.load_store())
        if name not in seen
    )
    return report


@keys.command(name="list")
def list_keys() -> None:
    """List every known + stored key with its metadata and presence (no values)."""
    typer.echo(json.dumps(_key_report(), indent=2))
    raise typer.Exit(code=0)


@keys.command()
def check() -> None:
    """Report presence/absence and source of each key as JSON (never a value)."""
    compact = [
        {"name": row["name"], "present": row["present"], "source": row["source"]}
        for row in _key_report()
    ]
    typer.echo(json.dumps(compact, indent=2))
    raise typer.Exit(code=0)


@keys.command()
def unset(
    name: Annotated[str, typer.Argument(help="Key name to remove from the store.")],
) -> None:
    """Remove a key from the store (a no-op if it was not stored).

    :param name: The key name to remove.
    """
    if keys_mod.unset_key(name):
        typer.echo(f"unset {name}")
    else:
        typer.echo(f"{name} was not in the store", err=True)
    raise typer.Exit(code=0)


@keys.command()
def path() -> None:
    """Print the resolved key-store path."""
    typer.echo(str(keys_mod.store_path()))
    raise typer.Exit(code=0)


if __name__ == "__main__":  # pragma: no cover
    app()
