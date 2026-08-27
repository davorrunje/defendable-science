# Literature Asset Acquisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the `literature` capability the asset verbs it lacks — `fetch | confirm | verify | mirror` — over a new literature registry layer, so `digest`'s "grounded in a real registry entry + mirrored PDF" precondition becomes satisfiable with shipped tooling.

**Architecture:** Promote the genuinely shared substrate primitives (`sha256_file`, `blob_path`, `RetrievalError`, `Mirror`) out of `dataset/retrieval.py` into `core/`, so `literature` sits *beside* `dataset` rather than importing from it. Add a literature registry module that reads CSL-JSON + `triage.yml` and writes back **surgically** (patch one namespaced object; never rewrite the human's file). Add an acquisition module whose PDF ladder is generic — all OpenAlex `locations[]`, PDF-serving landing pages, and sibling versions — guarded by a metadata gate that refuses rather than guesses.

**Tech Stack:** Python 3.11+, Typer, `requests` (streaming — already a dependency, no new deps), `pyyaml`, pytest with a 100% statement+branch coverage gate.

**Spec:** [`docs/superpowers/specs/2026-08-27-literature-asset-acquisition-design.md`](../specs/2026-08-27-literature-asset-acquisition-design.md) — read it first; this plan argues from it and cites its sections.

## Global Constraints

- **All package work runs from the `defendable-science/` subdirectory.** Every `uv run` / `pytest` command below assumes that cwd.
- **100% statement + branch coverage is a hard gate** (`fail_under = 100`, ADR-0028). New code lands with the tests that cover it, *including* error and degradation branches. `# pragma: no cover` only for genuinely unreachable code, with a stated reason.
- **Python 3.11+**, line length 88, strict mypy, `ruff check` + `ruff format` clean.
- **MyST field-list docstrings** on every public API (`:param:` / `:returns:` / `:raises:`; types come from annotations, never repeated in prose).
- **stdlib `dataclasses` for value objects. Pydantic is deliberately rejected** — do not reintroduce it.
- **No new runtime dependencies.** `requests>=2.31`, `pyyaml>=6.0`, `typer>=0.12`, `pooch>=1.8` are what exist; streaming downloads use `requests` directly.
- **Failure honesty is load-bearing here.** A throttle, a 5xx, or any transport failure must never be reported as "this paper has no PDF". Distinguish *failed* from *legitimately absent*; never surface a raw traceback.
- **Never commit to `main`.** Work continues on `design/literature-asset-acquisition`; each phase below is its own PR.
- **Commit authorship:** `Davor Runje <davor@synthpop.ai>` with a `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` trailer.
- **Domain-neutrality:** no ML-, venue-, or consumer-specific assumptions in shipped code. `venue_resolvers` ships empty.

## Deviation from the spec, recorded

Spec §3 lists the bytes-fetcher as an edit to `core/http.py`. This plan puts it in a **new `core/download.py`** instead. Reason: `HttpClient`'s `Session` protocol (`core/http.py:59-71`) has no `stream` parameter, its retry/throttle logic is built around `resp.json()`, and its cache is a JSON blob store — a streaming binary path shares none of that. Keeping them separate leaves `core/http.py` focused and gives the downloader its own injectable transport protocol. Everything else follows the spec as written.

## File structure

| File | Responsibility |
|---|---|
| `defendable_science/core/fixity.py` | **NEW.** SHA-256 hashing, checksum normalization, content-addressed blob paths, `RetrievalError`. Substrate, front-end agnostic. |
| `defendable_science/core/mirror.py` | **NEW.** The rclone `Mirror` and its injectable runner. Substrate. |
| `defendable_science/core/download.py` | **NEW.** Streaming binary retrieval with a size cap; `FetchedBytes`, `BytesFetcher`, `DownloadError`. |
| `defendable_science/dataset/retrieval.py` | **MODIFY.** Re-imports the promoted names; resolution-chain logic unchanged. |
| `defendable_science/literature/registry.py` | **NEW.** CSL-JSON + `triage.yml` read model and surgical writers. |
| `defendable_science/literature/acquire.py` | **NEW.** Ladder rungs, the match gate, quarantine, the sweep report. |
| `defendable_science/cli.py` | **MODIFY.** Four new `literature` commands. |
| `tests/test_fixity.py`, `test_mirror.py`, `test_download.py`, `test_lit_registry.py`, `test_acquire.py`, `test_acquire_cli.py` | **NEW.** |
| `tests/fixtures/openalex/*.json` | **NEW.** Trimmed real OpenAlex payloads. |
| `docs/guides/literature.md`, `tools/build_docs_site.py` | **NEW / MODIFY.** The user guide and its nav registration. |

## PR boundaries

- **PR 1 — substrate promotion:** Tasks 1–2. Review criterion: `dataset` behaviour is unchanged.
- **PR 2 — registry layer + downloader:** Tasks 3–6. No CLI surface; this is what Gap 2 depends on.
- **PR 3 — acquisition, CLI, docs:** Tasks 7–16. **Not done until Task 16's guide exists** (spec §12).

---

## Task 1: Promote fixity primitives to `core/fixity.py`

A pure refactor. `dataset/retrieval.py` currently owns `sha256_file`, `_bare`, `_blob_path`, `_verified`, and `RetrievalError`, all of which `04-substrate-and-contract.md` §2.1 designates *substrate*. Move them; `retrieval.py` re-imports so its public surface is untouched.

**Files:**
- Create: `defendable_science/core/fixity.py`
- Create: `tests/test_fixity.py`
- Modify: `defendable_science/dataset/retrieval.py` (delete the moved definitions, add the import)
- Modify: `tests/test_retrieval.py:107`, `tests/test_retrieval.py:122` (monkeypatch target)
- Modify: `tests/test_live_retrieval.py:139` (`_blob_path` → `blob_path`)

**Interfaces:**
- Consumes: nothing.
- Produces: `RetrievalError`, `sha256_file(path, *, chunk=1<<20) -> str`, `bare_sha256(sha256: str) -> str`, `blob_path(cache_dir: Path, sha256: str) -> Path`, `verified(path: Path, sha256: str) -> bool`.

> **The trap in this task.** `tests/test_retrieval.py:107` and `:122` do `monkeypatch.setattr(r, "sha256_file", _boom)` to cover the "present-but-unreadable file is treated as absent" branches. Once `verified()` lives in `core/fixity.py` and calls fixity's *module-global* `sha256_file`, patching `retrieval`'s re-exported binding no longer reaches it — those two branches go uncovered and the 100% gate fails. Both monkeypatch targets must change to the fixity module. This is the single most likely way to get this task wrong.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fixity.py`:

```python
"""Tests for the shared fixity primitives (promoted from dataset/retrieval.py)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from defendable_science.core import fixity as f


def test_sha256_file_streams_in_chunks(tmp_path: Path) -> None:
    payload = b"payload" * 1000
    target = tmp_path / "x"
    target.write_bytes(payload)
    assert f.sha256_file(target, chunk=8) == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("sha256:ABC", "abc"), ("abc", "abc"), ("  sha256:AbC  ", "abc")],
)
def test_bare_sha256_normalizes(raw: str, expected: str) -> None:
    assert f.bare_sha256(raw) == expected


def test_blob_path_is_content_addressed(tmp_path: Path) -> None:
    assert f.blob_path(tmp_path, "sha256:AB") == tmp_path / "sha256" / "ab"


def test_verified_true_on_match(tmp_path: Path) -> None:
    target = tmp_path / "x"
    target.write_bytes(b"p")
    assert f.verified(target, hashlib.sha256(b"p").hexdigest()) is True


def test_verified_false_when_absent(tmp_path: Path) -> None:
    assert f.verified(tmp_path / "nope", "a" * 64) is False


def test_verified_false_on_mismatch(tmp_path: Path) -> None:
    target = tmp_path / "x"
    target.write_bytes(b"p")
    assert f.verified(target, "a" * 64) is False


def test_verified_treats_unreadable_file_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "x"
    target.write_bytes(b"p")

    def _boom(_path: object, **_kw: object) -> str:
        raise OSError("unreadable")

    monkeypatch.setattr(f, "sha256_file", _boom)
    assert f.verified(target, "a" * 64) is False


def test_retrieval_error_is_a_runtime_error() -> None:
    assert issubclass(f.RetrievalError, RuntimeError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fixity.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'defendable_science.core.fixity'`

- [ ] **Step 3: Write the implementation**

Create `defendable_science/core/fixity.py`:

```python
"""Shared fixity primitives — hashing, checksum normalization, blob paths.

The authoritative checksum is SHA-256 (integrity == identity == citation
verifiability, ``docs/design/04-substrate-and-contract.md`` §2.3). Both asset
front-ends — ``dataset`` and ``literature`` — build on these; neither owns them.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


class RetrievalError(RuntimeError):
    """Raised when a resolution chain is exhausted or a hop fails hard."""


def sha256_file(path: str | Path, *, chunk: int = 1 << 20) -> str:
    """Return the SHA-256 hex digest of a file (streamed).

    :param path: The file to hash.
    :param chunk: Read-chunk size in bytes.
    :returns: The 64-char lowercase hex digest.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def bare_sha256(sha256: str) -> str:
    """Normalize a recorded checksum to a bare lowercase 64-hex string.

    :param sha256: A checksum, with or without a ``sha256:`` prefix.
    :returns: The bare lowercase hex digest.
    """
    return sha256.split(":", 1)[-1].strip().lower()


def blob_path(cache_dir: Path, sha256: str) -> Path:
    """Return the content-addressed cache path for a checksum.

    :param cache_dir: The content-addressed cache root.
    :param sha256: The checksum, prefixed or bare.
    :returns: ``<cache_dir>/sha256/<bare-hash>``.
    """
    return cache_dir / "sha256" / bare_sha256(sha256)


def verified(path: Path, sha256: str) -> bool:
    """Return whether `path` exists and its SHA-256 matches (else it is absent).

    A present-but-unreadable file (``OSError`` while hashing) is treated as
    absent, so a resolution chain moves on instead of crashing.

    :param path: The file to check.
    :param sha256: The expected checksum, prefixed or bare.
    :returns: Whether the on-disk bytes match.
    """
    if not path.is_file():
        return False
    try:
        return sha256_file(path) == bare_sha256(sha256)
    except OSError:
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_fixity.py -v --no-cov`
Expected: PASS (8 tests)

- [ ] **Step 5: Delete the moved definitions from `dataset/retrieval.py`**

Delete `RetrievalError`, `sha256_file`, `_bare`, `_blob_path`, and `_verified`. Add to the imports:

```python
from defendable_science.core.fixity import (
    RetrievalError,
    bare_sha256,
    blob_path,
    sha256_file,
    verified,
)
```

Then replace every internal call site: `_bare(` → `bare_sha256(`, `_blob_path(` → `blob_path(`, `_verified(` → `verified(`. Leave `hashlib` imported only if still used (it is not — remove it; ruff will flag `F401` otherwise).

- [ ] **Step 6: Re-point the two monkeypatch sites**

In `tests/test_retrieval.py`, add `from defendable_science.core import fixity as fx` and change both patch targets:

```python
# was: monkeypatch.setattr(r, "sha256_file", _boom)
monkeypatch.setattr(fx, "sha256_file", _boom)
```

In `tests/test_live_retrieval.py:139`, change `r._blob_path(cache, sha)` to `r.blob_path(cache, sha)`.

- [ ] **Step 7: Verify `dataset` behaviour is unchanged**

Run: `uv run pytest -q`
Expected: PASS, coverage 100%. If any `dataset/retrieval.py` line reports uncovered, the monkeypatch re-pointing of Step 6 was missed.

Run: `uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add defendable_science/core/fixity.py defendable_science/dataset/retrieval.py \
        tests/test_fixity.py tests/test_retrieval.py tests/test_live_retrieval.py
git commit -m "refactor: promote fixity primitives to core/fixity.py

Substrate per 04-substrate-and-contract.md §2.1: both asset front-ends build
on SHA-256 hashing and content-addressed blob paths; neither owns them. Pure
move — dataset behaviour and public surface unchanged.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Promote `Mirror` to `core/mirror.py`

**Files:**
- Create: `defendable_science/core/mirror.py`
- Create: `tests/test_mirror.py`
- Modify: `defendable_science/dataset/retrieval.py`
- Modify: `tests/test_retrieval.py` (move the `# --- Mirror ---` block, lines ~226-345, into `tests/test_mirror.py`)

**Interfaces:**
- Consumes: `RetrievalError` from Task 1.
- Produces: `Mirror` (dataclass: `remote: str`, `base_path: str = ""`, `config_path: str | None = None`, `rclone_bin: str = "rclone"`, `run: Runner = subprocess.run`, `env: Mapping[str, str] | None = None`; methods `put(local, sha256) -> None`, `get(sha256, dst) -> bool`, `check(sha256) -> bool`), and `Runner = Callable[..., _Proc]`.

- [ ] **Step 1: Create the module by moving code verbatim**

Create `defendable_science/core/mirror.py` containing `_Proc`, `Runner`, and `Mirror` moved unchanged from `dataset/retrieval.py`, with this module docstring and importing `RetrievalError` / `bare_sha256` from `core.fixity`:

```python
"""The content-addressed private mirror over ``rclone`` (substrate).

Keys are ``<base_path>/sha256/<hash>``. Every method shells out to ``rclone``
through the injectable `run` callable, so rclone is a Go binary invoked as a
subprocess — never a Python dependency — and the mirror is testable without it.
Shared by the ``dataset`` and ``literature`` front-ends
(``docs/design/04-substrate-and-contract.md`` §2.3).
"""
```

Keep the `# nosec B404` comment on the `subprocess` import and the `# nosec B603` on the `self.run(...)` call; bandit runs in pre-commit and will fail without them.

- [ ] **Step 2: Move the mirror tests**

Create `tests/test_mirror.py` and move the `# --- Mirror ---` block of `tests/test_retrieval.py` (roughly lines 226-345) into it, changing `r.Mirror` → `mirror_mod.Mirror` and `r.RetrievalError` → `fx.RetrievalError` with:

```python
from defendable_science.core import fixity as fx
from defendable_science.core import mirror as mirror_mod
```

Leave the tests that exercise `Mirror` *through the resolution chain* (e.g. `test_mirror_hit_returns_blob`, and the `mirror.put` assertion inside the Tier-B test) in `tests/test_retrieval.py` — those are chain tests, not mirror tests.

- [ ] **Step 3: Re-import in `dataset/retrieval.py`**

Delete `_Proc`, `Runner`, `Mirror`, and the now-unused `os` / `subprocess` / `Protocol` imports from `dataset/retrieval.py`. Add:

```python
from defendable_science.core.mirror import Mirror, Runner
```

`Runner` is re-exported because `dataset/retrieval.py`'s docstring and type annotations reference it. If ruff reports `F401` for `Runner`, it is genuinely unused — delete it from the import rather than adding a `noqa`.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS, coverage 100%.

Run: `uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add defendable_science/core/mirror.py defendable_science/dataset/retrieval.py \
        tests/test_mirror.py tests/test_retrieval.py
git commit -m "refactor: promote Mirror to core/mirror.py

Second half of the substrate promotion. dataset/retrieval.py now holds only
the dataset resolution chain; the mirror is shared machinery.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Open PR 1**

Use the local `create-pr` skill. Title: `refactor: promote substrate primitives (fixity, mirror) to core/`. Body must state the review criterion: **`dataset` behaviour is unchanged; no new tests beyond the moved ones.**

---

## Task 3: Streaming downloader in `core/download.py`

Transport only — status, size cap, streamed write, reported media type. Whether the bytes are *acceptable as a PDF* is policy and belongs to Task 8.

**Files:**
- Create: `defendable_science/core/download.py`
- Create: `tests/test_download.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class DownloadError(RuntimeError)`
  - `@dataclass class FetchedBytes: path: Path; media_type: str | None; size: int`
  - `BytesFetcher = Callable[[str, Path, int], FetchedBytes]`
  - `def stream_to_file(url: str, dest: Path, max_bytes: int, *, session: StreamSession | None = None, timeout: float = 30.0) -> FetchedBytes`

- [ ] **Step 1: Write the failing test**

Create `tests/test_download.py`:

```python
"""Tests for the streaming binary downloader."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from defendable_science.core import download as d


class FakeResponse:
    def __init__(
        self,
        chunks: list[bytes],
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self._chunks = chunks
        self.status_code = status_code
        self.headers = dict(headers or {"Content-Type": "application/pdf"})
        self.closed = False

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        assert chunk_size > 0
        yield from self._chunks

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, bool]] = []

    def get(
        self,
        url: str,
        *,
        stream: bool = False,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        self.calls.append((url, stream))
        return self.response


def test_streams_to_file_and_reports_media_type(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse([b"%PDF-", b"rest"]))
    got = d.stream_to_file("http://x/p.pdf", tmp_path / "p", 1000, session=session)
    assert got.path.read_bytes() == b"%PDF-rest"
    assert got.media_type == "application/pdf"
    assert got.size == 9
    assert session.calls == [("http://x/p.pdf", True)]


def test_media_type_strips_charset_parameters(tmp_path: Path) -> None:
    session = FakeSession(
        FakeResponse([b"x"], headers={"Content-Type": "text/html; charset=utf-8"})
    )
    got = d.stream_to_file("http://x", tmp_path / "p", 1000, session=session)
    assert got.media_type == "text/html"


def test_missing_content_type_yields_none(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse([b"x"], headers={}))
    got = d.stream_to_file("http://x", tmp_path / "p", 1000, session=session)
    assert got.media_type is None


def test_non_200_raises_with_the_status(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse([], status_code=403))
    with pytest.raises(d.DownloadError, match="HTTP 403"):
        d.stream_to_file("http://x", tmp_path / "p", 1000, session=session)


def test_oversize_aborts_and_removes_the_partial_file(tmp_path: Path) -> None:
    dest = tmp_path / "p"
    session = FakeSession(FakeResponse([b"a" * 6, b"b" * 6]))
    with pytest.raises(d.DownloadError, match="exceeds max_bytes"):
        d.stream_to_file("http://x", dest, 10, session=session)
    assert not dest.exists()


def test_empty_body_is_an_error(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse([]))
    with pytest.raises(d.DownloadError, match="empty response body"):
        d.stream_to_file("http://x", tmp_path / "p", 1000, session=session)


def test_creates_parent_directories(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse([b"x"]))
    got = d.stream_to_file("http://x", tmp_path / "a" / "b" / "p", 100, session=session)
    assert got.path.is_file()


def test_transport_failure_becomes_a_download_error(tmp_path: Path) -> None:
    class Boom:
        def get(self, url: str, **_kw: object) -> FakeResponse:
            raise OSError("connection reset")

    with pytest.raises(d.DownloadError, match="connection reset"):
        d.stream_to_file("http://x", tmp_path / "p", 100, session=Boom())


def test_default_session_is_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    made: list[object] = []
    monkeypatch.setattr(d.requests, "Session", lambda: made.append(1) or FakeSession(FakeResponse([b"x"])))  # type: ignore[func-returns-value]
    assert d._default_session() is not None
    assert made == [1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_download.py -v --no-cov`
Expected: FAIL — `No module named 'defendable_science.core.download'`

- [ ] **Step 3: Write the implementation**

Create `defendable_science/core/download.py`:

```python
"""Streaming binary retrieval with a hard size cap.

Deliberately separate from :mod:`defendable_science.core.http`: that client is a
*JSON* client with a JSON response cache and a retry loop built around
``resp.json()``, none of which a binary stream shares. Here the content-addressed
blob store is the cache, so nothing is cached at this layer.

The transport is injectable (:class:`StreamSession`), so the acquisition ladder
is exercised without network access.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

#: Read size for the streamed body.
CHUNK = 1 << 16


class DownloadError(RuntimeError):
    """Raised when a byte retrieval fails, is empty, or exceeds the size cap."""


@dataclass
class FetchedBytes:
    """Bytes that landed on disk, with what the server said about them.

    :param path: Where the bytes were written.
    :param media_type: The ``Content-Type`` with parameters stripped, or ``None``
        when the server sent none. Advisory only — servers misreport it, so a
        caller that cares about the true format must inspect the bytes.
    :param size: Byte count actually written.
    """

    path: Path
    media_type: str | None
    size: int


#: A byte fetcher: ``(url, dest, max_bytes) -> FetchedBytes`` (injectable).
BytesFetcher = Callable[[str, Path, int], FetchedBytes]


class StreamResponse(Protocol):
    """The minimal streaming-response shape the downloader needs."""

    status_code: int
    headers: Mapping[str, str]

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        """Yield the body in chunks."""

    def close(self) -> None:
        """Release the connection."""


class StreamSession(Protocol):
    """The minimal session shape the downloader needs (``requests.Session``)."""

    def get(
        self,
        url: str,
        *,
        stream: bool = ...,
        timeout: float | None = ...,
        headers: dict[str, str] | None = ...,
    ) -> StreamResponse:
        """Issue a streaming GET."""


def _default_session() -> StreamSession:
    """Return a fresh ``requests.Session`` (indirection for tests)."""
    return requests.Session()


def _media_type(headers: Mapping[str, str]) -> str | None:
    """Return the bare ``Content-Type``, parameters stripped, else ``None``."""
    raw = headers.get("Content-Type")
    if not raw:
        return None
    return raw.split(";", 1)[0].strip().lower() or None


def stream_to_file(
    url: str,
    dest: Path,
    max_bytes: int,
    *,
    session: StreamSession | None = None,
    timeout: float = 30.0,
) -> FetchedBytes:
    """Stream `url` into `dest`, aborting past `max_bytes`.

    A partial file is removed on any failure, so a caller never sees truncated
    bytes it might mistake for a complete download.

    :param url: The URL to retrieve.
    :param dest: Destination path (parents are created).
    :param max_bytes: Hard ceiling; exceeding it aborts the transfer.
    :param session: The streaming transport (defaults to ``requests.Session``).
    :param timeout: Per-request timeout in seconds.
    :returns: The landed bytes with their reported media type and size.
    :raises DownloadError: On a non-200 status, a transport failure, an empty
        body, or a body exceeding `max_bytes`.
    """
    transport = session if session is not None else _default_session()
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = transport.get(url, stream=True, timeout=timeout)
    except OSError as exc:
        raise DownloadError(f"{url}: {exc}") from exc
    try:
        if response.status_code != 200:
            raise DownloadError(f"{url}: HTTP {response.status_code}")
        size = 0
        with dest.open("wb") as handle:
            for block in response.iter_content(chunk_size=CHUNK):
                size += len(block)
                if size > max_bytes:
                    raise DownloadError(
                        f"{url}: exceeds max_bytes ({max_bytes}) — aborted"
                    )
                handle.write(block)
        if size == 0:
            raise DownloadError(f"{url}: empty response body")
    except DownloadError:
        dest.unlink(missing_ok=True)
        raise
    finally:
        response.close()
    return FetchedBytes(path=dest, media_type=_media_type(response.headers), size=size)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_download.py -v --no-cov`
Expected: PASS (9 tests)

- [ ] **Step 5: Confirm full coverage of the new module**

Run: `uv run pytest tests/test_download.py --cov=defendable_science.core.download --cov-branch --cov-report=term-missing`
Expected: 100%. If the `finally: response.close()` path or the `OSError` branch is missing, add the case rather than a pragma.

- [ ] **Step 6: Commit**

```bash
git add defendable_science/core/download.py tests/test_download.py
git commit -m "feat(core): streaming binary downloader with a hard size cap

Separate from core/http.py: that is a JSON client with a JSON cache and a
retry loop around resp.json(). Partial files are removed on failure so a
caller never mistakes truncated bytes for a complete download.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Registry read model in `literature/registry.py`

Reads `references.json` (CSL-JSON) and decodes the spine from `custom["defendable-science"]` (spec §8.1). Read only — writers are Tasks 5 and 6.

**Files:**
- Create: `defendable_science/literature/registry.py`
- Create: `tests/test_lit_registry.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `NAMESPACE = "defendable-science"`, `SCHEMA = 1`
  - `class RegistryError(ValueError)`
  - `@dataclass class AssetFile: path: str; sha256: str; size: int | None = None; media_type: str | None = None`
  - `@dataclass class License: id: str | None = None; observed: str | None = None; source: str | None = None`
  - `@dataclass class MirrorRef: remote: str; key: str`
  - `@dataclass class Acquisition: rung: str; url: str | None = None; candidate: dict[str, Any] = {}; match: dict[str, Any] = {}; fetched: str | None = None`
  - `@dataclass class Asset: schema: int = SCHEMA; pid: str | None = None; files: list[AssetFile] = []; license: License = License(); redistributable: bool = False; access: str | None = None; mirror: MirrorRef | None = None; acquisition: Acquisition | None = None`
  - `@dataclass class Entry: citekey: str; title: str | None; year: int | None; first_author_family: str | None; doi: str | None; asset: Asset | None; raw: dict[str, Any]`
  - `@dataclass class Registry: path: Path; entries: list[Entry]` with `get(citekey: str) -> Entry | None`
  - `def load_registry(path: str | Path) -> Registry`
  - `def asset_to_json(asset: Asset) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_lit_registry.py`:

```python
"""Tests for the literature registry read model + surgical writers."""

from __future__ import annotations

import json
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
                        "license": {"id": "cc-by-4.0", "observed": "CC BY 4.0",
                                    "source": "openalex"},
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
    path = _write(
        tmp_path / "r.json", [_item(author=[{"literal": "The Consortium"}])]
    )
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
        files=[reg.AssetFile(path="sha256/ab", sha256="sha256:ab", size=1,
                            media_type="application/pdf")],
        license=reg.License(id="cc0-1.0", observed="CC0", source="openalex"),
        redistributable=True,
        access="open",
        mirror=reg.MirrorRef(remote="m", key="sha256/ab"),
        acquisition=reg.Acquisition(rung="manual", url=None, candidate={},
                                    match={"verdict": "identity"},
                                    fetched="2026-08-27"),
    )
    path = _write(tmp_path / "r.json", [_item(custom={reg.NAMESPACE: reg.asset_to_json(asset)})])
    assert reg.load_registry(path).get("sill1997monotonic").asset == asset  # type: ignore[union-attr]


def test_asset_to_json_omits_absent_optionals() -> None:
    blob = reg.asset_to_json(reg.Asset())
    assert "mirror" not in blob
    assert "acquisition" not in blob
    assert blob["schema"] == reg.SCHEMA
    assert blob["redistributable"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_lit_registry.py -v --no-cov`
Expected: FAIL — `No module named 'defendable_science.literature.registry'`

- [ ] **Step 3: Write the implementation**

Create `defendable_science/literature/registry.py`. Decode defensively: this file is hand-editable by a human and exported by Zotero, so a malformed field degrades to `None` where the meaning is "unknown" and raises `RegistryError` only where the file is structurally unusable.

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_lit_registry.py -v --no-cov`
Expected: PASS (15 tests)

- [ ] **Step 5: Commit**

```bash
git add defendable_science/literature/registry.py tests/test_lit_registry.py
git commit -m "feat(literature): registry read model over CSL-JSON + custom spine

CSL-JSON sets additionalProperties:false and defines no files/license/mirror
field, so the substrate spine lives under the schema-designated `custom` key,
namespaced. Decoding is tolerant where a field means 'unknown' and hard only
where the file is structurally unusable.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Surgical `patch_asset` writer

Issues #94 and #95 are both open bugs of the "we rewrote a human-authored file and lost content" class. This writer must not become the third.

**Files:**
- Modify: `defendable_science/literature/registry.py`
- Modify: `tests/test_lit_registry.py`

**Interfaces:**
- Consumes: `Asset`, `asset_to_json`, `_read_items`, `RegistryError` from Task 4.
- Produces: `def patch_asset(path: str | Path, citekey: str, asset: Asset) -> None`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lit_registry.py`:

```python
def test_patch_asset_preserves_unknown_top_level_keys(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "r.json",
        [_item(**{"note": "hand-written", "keyword": "monotone", "custom": {"zotero": {"k": 1}}})],
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
    path = _write(tmp_path / "r.json", [_item()])
    reg.patch_asset(path, "sill1997monotonic", reg.Asset())
    assert [p.name for p in tmp_path.iterdir()] == ["r.json"]


def test_patch_asset_keeps_non_ascii_unescaped(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item(author=[{"family": "Bélair"}])])
    reg.patch_asset(path, "sill1997monotonic", reg.Asset())
    assert "Bélair" in path.read_text(encoding="utf-8")


def test_patch_asset_ends_with_a_newline(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item()])
    reg.patch_asset(path, "sill1997monotonic", reg.Asset())
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_patch_asset_rejects_a_non_object_custom(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.json", [_item(custom="oops")])
    with pytest.raises(reg.RegistryError, match="'custom' is not an object"):
        reg.patch_asset(path, "sill1997monotonic", reg.Asset())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_lit_registry.py -k patch_asset -v --no-cov`
Expected: FAIL — `AttributeError: module ... has no attribute 'patch_asset'`

- [ ] **Step 3: Write the implementation**

Append to `defendable_science/literature/registry.py`:

```python
def _locate(items: list[Any], citekey: str) -> int:
    """Return the index of the entry matching `citekey` by ``id`` then ``DOI``.

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

    :param path: The registry path.
    :param citekey: The entry to patch, matched on ``id`` then ``DOI``.
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_lit_registry.py -v --no-cov`
Expected: PASS (25 tests)

- [ ] **Step 5: Commit**

```bash
git add defendable_science/literature/registry.py tests/test_lit_registry.py
git commit -m "feat(literature): surgical patch_asset writer

Patches only custom['defendable-science'] and rewrites atomically; unknown
top-level keys, foreign custom namespaces and key order all survive. #94 and
#95 are both 'we rewrote the human's file and lost content' bugs — this is
the writer that must not become the third.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Triage read + comment-safe restricted write

`pyyaml` cannot round-trip comments. Rather than silently destroy a human's annotations, the writer **refuses** when the file carries comments (spec §8.2).

**Files:**
- Modify: `defendable_science/literature/registry.py`
- Modify: `tests/test_lit_registry.py`

**Interfaces:**
- Consumes: `RegistryError` from Task 4.
- Produces:
  - `@dataclass class TriageRow: citekey: str; disposition: str | None; raw: dict[str, Any]`
  - `def load_triage(path: str | Path) -> dict[str, TriageRow]` — a missing file yields `{}` (an unconfigured project is "no triage", not an error)
  - `def patch_triage(path: str | Path, citekey: str, updates: dict[str, str | int | bool | None]) -> None`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lit_registry.py`:

```python
def test_load_triage_reads_rows(tmp_path: Path) -> None:
    path = tmp_path / "t.yml"
    path.write_text(
        "sill1997monotonic:\n"
        "  disposition: screened\n"
        "  rationale: seminal\n",
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_lit_registry.py -k triage -v --no-cov`
Expected: FAIL — `AttributeError: ... 'load_triage'`

- [ ] **Step 3: Write the implementation**

Add `import yaml` to the module imports and append:

```python
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
    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RegistryError(f"{target}: invalid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RegistryError(
            f"{target}: expected a YAML mapping of citekey → row, got "
            f"{type(data).__name__}"
        )
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


def patch_triage(
    path: str | Path, citekey: str, updates: dict[str, str | int | bool | None]
) -> None:
    """Add or replace scalar keys on one triage row.

    ``pyyaml`` cannot round-trip comments, and the triage sidecar's ``rationale``
    fields *are* the PRISMA audit trail — often annotated. So this refuses to
    rewrite a file carrying comments rather than silently destroying them; the
    caller surfaces the refusal and the human edits by hand. Scalars only, for the
    same reason: a nested value is a structure worth a human's attention.

    :param path: The sidecar path (created if absent).
    :param citekey: The row to patch (created if absent).
    :param updates: Scalar keys to set; a ``None`` value deletes the key.
    :raises RegistryError: If the file carries comments, is unreadable, or any
        update value is not a scalar.
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
        rows = load_triage(target)
        data: dict[str, Any] = {key: row.raw for key, row in rows.items()}
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_lit_registry.py -v --no-cov`
Expected: PASS (37 tests)

- [ ] **Step 5: Full gate**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: PASS, coverage 100%, all clean.

- [ ] **Step 6: Commit and open PR 2**

```bash
git add defendable_science/literature/registry.py tests/test_lit_registry.py
git commit -m "feat(literature): triage sidecar read + comment-safe restricted write

pyyaml cannot round-trip comments, and triage rationales ARE the PRISMA audit
trail. So the writer refuses a commented file with an actionable message
rather than silently destroying annotations, and accepts scalars only.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

Open PR 2 with the `create-pr` skill. Title: `feat(literature): registry layer + streaming downloader`. Body notes this is the foundation #97 Gap 2 builds on and that it has no CLI surface yet.

---

## Task 7: The match gate

**The acceptance criterion of #97.** Everything else in this plan is plumbing; this is the part that stops a wrong PDF being bound to a citekey.

**Files:**
- Create: `defendable_science/literature/acquire.py`
- Create: `tests/test_acquire.py`

**Interfaces:**
- Consumes: `Entry` from Task 4.
- Produces:
  - `@dataclass class Candidate: url: str; rung: str; title: str | None = None; year: int | None = None; first_author_family: str | None = None; openalex: str | None = None`
  - `@dataclass class MatchRecord: verdict: str; title: str | None = None; author: str | None = None; year: str | None = None; reason: str | None = None` with `def as_json(self) -> dict[str, Any]`
  - `IDENTITY / ACCEPT / QUARANTINE / REFUSE` verdict constants
  - `GATED_RUNGS: frozenset[str]`
  - `def normalize_title(title: str) -> str`
  - `def fold_name(name: str) -> str`
  - `def evaluate_match(entry: Entry, candidate: Candidate) -> MatchRecord`

- [ ] **Step 1: Write the failing test**

Create `tests/test_acquire.py`:

```python
"""Tests for the literature acquisition ladder and its match gate."""

from __future__ import annotations

from typing import Any

import pytest

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
        ("MonoKAN: Certified Monotonic Kolmogorov-Arnold Network",
         "monokan certified monotonic kolmogorov arnold network"),
        ("MonoKAN: Certified monotonic Kolmogorov-Arnold network",
         "monokan certified monotonic kolmogorov arnold network"),
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
        _entry(), _cand(title="Monotonic Networks", year=1997, first_author_family="Sill")
    )
    assert record.verdict == a.ACCEPT
    assert (record.title, record.author, record.year) == ("exact", "exact", "exact")


def test_wide_year_gap_with_exact_title_quarantines() -> None:
    record = a.evaluate_match(
        _entry(), _cand(title="Monotonic Networks", year=2001, first_author_family="Sill")
    )
    assert record.verdict == a.QUARANTINE
    assert record.year == "within-5"


def test_year_gap_beyond_the_window_refuses() -> None:
    record = a.evaluate_match(
        _entry(), _cand(title="Monotonic Networks", year=2010, first_author_family="Sill")
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


# --- shape ------------------------------------------------------------------


def test_identity_rungs_are_not_gated() -> None:
    assert a.RUNG_OA_BEST not in a.GATED_RUNGS
    assert a.RUNG_OA_LOCATIONS not in a.GATED_RUNGS
    assert a.RUNG_OA_LANDING not in a.GATED_RUNGS


def test_search_rungs_are_gated() -> None:
    assert a.GATED_RUNGS == frozenset(
        {a.RUNG_SIBLING, a.RUNG_ARXIV_SEARCH, a.RUNG_VENUE}
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_acquire.py -v --no-cov`
Expected: FAIL — `No module named 'defendable_science.literature.acquire'`

- [ ] **Step 3: Write the implementation**

Create `defendable_science/literature/acquire.py`:

```python
"""PDF acquisition for the literature registry — the ladder and the match gate.

Unlike ``dataset``, which verifies bytes against a checksum it already trusts,
this front-end *establishes* the checksum on first acquisition. The metadata gate
below stands where ``dataset`` has a pre-known hash, so it is load-bearing rather
than a nicety: a wrong PDF bound to a citekey is strictly worse than no PDF,
because ``digest``'s comprehension check verifies understanding of the bytes it
was given and will pass on the wrong paper.

Design: ``docs/superpowers/specs/2026-08-27-literature-asset-acquisition-design.md``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from defendable_science.literature.registry import Entry

# --- rungs ------------------------------------------------------------------

RUNG_OA_BEST = "openalex-best"
RUNG_OA_LOCATIONS = "openalex-locations"
RUNG_OA_LANDING = "openalex-landing"
RUNG_SIBLING = "sibling-version"
RUNG_ARXIV_SEARCH = "arxiv-search"
RUNG_VENUE = "venue-resolver"
RUNG_MANUAL = "manual"

#: Rungs whose candidates come from a *search* and therefore must pass the gate.
#: Rungs 1–3 are identity-derived — their URLs come from the OpenAlex work the
#: citekey already resolves to, so there is nothing to verify.
GATED_RUNGS = frozenset({RUNG_SIBLING, RUNG_ARXIV_SEARCH, RUNG_VENUE})

# --- verdicts ---------------------------------------------------------------

#: An ungated rung: identity was established by resolution, not by matching.
IDENTITY = "identity"
#: Gated and passed — bind the bytes.
ACCEPT = "accept"
#: Gated and plausible — land in quarantine, await a human ``confirm``.
QUARANTINE = "quarantine"
#: Gated and rejected — bind nothing.
REFUSE = "refuse"

#: Year windows: exact-or-±1 accepts; up to ±5 quarantines (preprint/journal lag).
ACCEPT_YEAR_WINDOW = 1
QUARANTINE_YEAR_WINDOW = 5

_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_SPACE = re.compile(r"\s+")


@dataclass
class Candidate:
    """A possible PDF for a registry entry, as reported by one rung.

    :param url: Where the bytes would come from.
    :param rung: Which rung produced it.
    :param title: The candidate's title, when the rung reported one.
    :param year: The candidate's publication year, when reported.
    :param first_author_family: The candidate's first-author family name.
    :param openalex: The candidate's OpenAlex id, when it has one.
    """

    url: str
    rung: str
    title: str | None = None
    year: int | None = None
    first_author_family: str | None = None
    openalex: str | None = None

    def as_json(self) -> dict[str, Any]:
        """Return the candidate as a JSON-ready object for the audit trail."""
        return {
            "url": self.url,
            "rung": self.rung,
            "title": self.title,
            "year": self.year,
            "first_author_family": self.first_author_family,
            "openalex": self.openalex,
        }


@dataclass
class MatchRecord:
    """The gate's verdict, per axis, so a refusal is explainable.

    :param verdict: :data:`IDENTITY` | :data:`ACCEPT` | :data:`QUARANTINE` |
        :data:`REFUSE`.
    :param title: ``exact`` | ``containment`` | ``mismatch``, or ``None`` when the
        axis was not evaluated.
    :param author: ``exact`` | ``mismatch``, or ``None``.
    :param year: ``exact`` | ``within-1`` | ``within-5`` | ``mismatch``, or ``None``.
    :param reason: A human-readable explanation, set on any non-accepting verdict.
    """

    verdict: str
    title: str | None = None
    author: str | None = None
    year: str | None = None
    reason: str | None = None

    def as_json(self) -> dict[str, Any]:
        """Return the record as a JSON-ready object for the audit trail."""
        return {
            "verdict": self.verdict,
            "title": self.title,
            "author": self.author,
            "year": self.year,
            "reason": self.reason,
        }


def normalize_title(title: str) -> str:
    """Normalize a title for comparison — casefold, strip punctuation, collapse space.

    :param title: The raw title.
    :returns: The normalized form.
    """
    folded = unicodedata.normalize("NFKD", title).casefold()
    return _SPACE.sub(" ", _PUNCT.sub(" ", folded)).strip()


def fold_name(name: str) -> str:
    """Fold a personal name for comparison — casefold and drop diacritics.

    :param name: The raw name.
    :returns: The folded form.
    """
    decomposed = unicodedata.normalize("NFKD", name.strip().casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _title_axis(entry_title: str, candidate_title: str) -> str:
    """Compare titles: ``exact`` | ``containment`` | ``mismatch``."""
    left = normalize_title(entry_title)
    right = normalize_title(candidate_title)
    if left == right:
        return "exact"
    if left and right and (left in right or right in left):
        return "containment"
    return "mismatch"


def _year_axis(entry_year: int, candidate_year: int) -> str:
    """Compare years: ``exact`` | ``within-1`` | ``within-5`` | ``mismatch``."""
    delta = abs(entry_year - candidate_year)
    if delta == 0:
        return "exact"
    if delta <= ACCEPT_YEAR_WINDOW:
        return "within-1"
    if delta <= QUARANTINE_YEAR_WINDOW:
        return "within-5"
    return "mismatch"


def evaluate_match(entry: Entry, candidate: Candidate) -> MatchRecord:
    """Judge a search-derived candidate against the registry entry.

    **First-author family name is a hard gate**: no candidate is ever accepted or
    quarantined across an author mismatch. That single rule is what refuses
    Igel 2023 for Sill 1997 while still accepting a genuine preprint/journal pair
    one year apart.

    Thin metadata on either side is a **refusal**, not a title-only guess — an
    unverifiable candidate is exactly the case this gate exists for.

    :param entry: The registry entry the bytes would be bound to.
    :param candidate: The candidate under consideration.
    :returns: The per-axis record and the verdict.
    """
    if (
        entry.title is None
        or entry.year is None
        or entry.first_author_family is None
        or candidate.title is None
        or candidate.year is None
        or candidate.first_author_family is None
    ):
        return MatchRecord(
            verdict=REFUSE,
            reason=(
                "insufficient metadata to verify a search-derived candidate "
                "(title, year and first author are all required on both sides)"
            ),
        )

    title = _title_axis(entry.title, candidate.title)
    author = (
        "exact"
        if fold_name(entry.first_author_family)
        == fold_name(candidate.first_author_family)
        else "mismatch"
    )
    year = _year_axis(entry.year, candidate.year)
    record = MatchRecord(verdict=REFUSE, title=title, author=author, year=year)

    if author != "exact":
        record.reason = (
            f"first author {candidate.first_author_family!r} does not match "
            f"{entry.first_author_family!r} — a different paper, not a version"
        )
        return record
    if title == "exact" and year in ("exact", "within-1"):
        record.verdict = ACCEPT
        return record
    if title == "exact" and year == "within-5":
        record.verdict = QUARANTINE
        record.reason = (
            f"same title and author but {abs(entry.year - candidate.year)} years "
            "apart — plausibly a preprint, needs a human look"
        )
        return record
    if title == "containment" and year in ("exact", "within-1"):
        record.verdict = QUARANTINE
        record.reason = (
            "titles overlap but are not equal — plausibly the same work under a "
            "different subtitle, needs a human look"
        )
        return record
    record.reason = (
        f"title {title} and year {year} against the registry entry — "
        "not the same work"
    )
    return record
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_acquire.py -v --no-cov`
Expected: PASS. The named regression `test_the_named_regression_refuses_igel_for_sill` and `test_monokan_sibling_version_is_accepted_across_one_year` must both pass — they are the two halves of the acceptance criterion.

- [ ] **Step 5: Commit**

```bash
git add defendable_science/literature/acquire.py tests/test_acquire.py
git commit -m "feat(literature): the acquisition match gate (#97 acceptance criterion)

Author family name is a hard gate: no candidate is accepted or quarantined
across an author mismatch. That refuses Igel 2023 for Sill 1997 (all three
axes fail independently) while still accepting the real MonoKAN
preprint/journal pair one year apart. Thin metadata refuses rather than
guessing from the title alone.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Identity-derived candidates (rungs 1–3) and PDF acceptance

Rung 3 is the interesting one: Sill 1997's OpenAlex record has `oa_status: closed` and `best_oa_location.pdf_url: null`, but `locations[0].landing_page_url` is `https://papers.nips.cc/paper/1358-monotonic-networks.pdf`, which returns `200 application/pdf`. Reading all locations plus sniffing landing pages recovers it with **no venue knowledge**.

**Files:**
- Modify: `defendable_science/literature/acquire.py`
- Modify: `tests/test_acquire.py`
- Create: `tests/fixtures/openalex/sill1997.json`, `tests/fixtures/openalex/monokan_arxiv.json`, `tests/fixtures/openalex/monokan_journal.json`

**Interfaces:**
- Consumes: `Candidate` from Task 7, `FetchedBytes` from Task 3.
- Produces:
  - `PDF_MAGIC = b"%PDF-"`
  - `def looks_like_pdf(fetched: FetchedBytes) -> bool`
  - `def candidate_from_work(work: dict[str, Any], url: str, rung: str) -> Candidate`
  - `def identity_candidates(work: dict[str, Any]) -> list[Candidate]`
  - `def landing_urls(work: dict[str, Any]) -> list[str]`

- [ ] **Step 1: Capture the fixtures**

Run these and save the trimmed results. Keep only the fields the code reads (`id`, `display_name`, `publication_year`, `authorships[].author.display_name`, `open_access.oa_status`, `best_oa_location`, `locations[]`, `primary_location`, `ids`, `doi`, `license` where present) so the fixtures stay reviewable:

```bash
mkdir -p tests/fixtures/openalex
curl -s 'https://api.openalex.org/works/W2293093810?mailto=davor@synthpop.ai' > /tmp/sill.json
curl -s 'https://api.openalex.org/works/W4403706439?mailto=davor@synthpop.ai' > /tmp/monokan_arxiv.json
curl -s 'https://api.openalex.org/works/W4416410340?mailto=davor@synthpop.ai' > /tmp/monokan_journal.json
```

Trim each into `tests/fixtures/openalex/`. Known properties to preserve, because tests assert on them:
- `sill1997.json` — `oa_status: "closed"`, `best_oa_location.pdf_url: null`, and `locations[0].landing_page_url` ending `.pdf`.
- `monokan_arxiv.json` — `oa_status: "green"`, a `best_oa_location.pdf_url`.
- `monokan_journal.json` — `oa_status: "closed"`, no `pdf_url` anywhere.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_acquire.py`:

```python
import json
from pathlib import Path

from defendable_science.core.download import FetchedBytes

FIXTURES = Path(__file__).parent / "fixtures" / "openalex"


def _work(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


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
    cands = a.identity_candidates(_work("monokan_arxiv"))
    assert cands[0].rung == a.RUNG_OA_BEST
    assert cands[0].url.endswith(".pdf")


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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_acquire.py -k "pdf or rung or candidate or landing or family or locations" -v --no-cov`
Expected: FAIL — `AttributeError: ... 'looks_like_pdf'`

- [ ] **Step 4: Write the implementation**

Append to `defendable_science/literature/acquire.py` (add `from defendable_science.core.download import FetchedBytes` under `TYPE_CHECKING` and a runtime import where needed):

```python
#: The PDF magic-byte prefix. Authoritative over ``Content-Type``, which lies.
PDF_MAGIC = b"%PDF-"


def looks_like_pdf(fetched: FetchedBytes) -> bool:
    """Return whether the landed bytes are a PDF.

    ``Content-Type: application/pdf`` is trusted, but its absence is not
    disqualifying: Sill 1997's ``papers.nips.cc`` landing URL serves a real PDF
    under ``text/html``, and that case is precisely what the landing-page rung
    exists to recover. So the magic-byte prefix is the fallback and the
    tie-breaker. An unreadable file is *not* a PDF rather than an exception — the
    ladder moves on.

    :param fetched: The landed bytes.
    :returns: Whether they should be treated as a PDF.
    """
    if fetched.media_type == "application/pdf":
        return True
    try:
        with fetched.path.open("rb") as handle:
            return handle.read(len(PDF_MAGIC)) == PDF_MAGIC
    except OSError:
        return False


def _short_id(url: str | None) -> str | None:
    """Reduce an OpenAlex entity URL to its bare id (``…/W123`` → ``W123``)."""
    if not url:
        return None
    return url.rstrip("/").rsplit("/", 1)[-1]


def _first_family_from_work(work: dict[str, Any]) -> str | None:
    """Return the first author's family name from an OpenAlex work.

    OpenAlex gives a single ``display_name`` per author, so the family name is
    taken as the last whitespace-separated token — correct for the overwhelming
    majority of Western-ordered names, and the gate compares it only against the
    registry's own ``family`` field, so a systematic parse quirk affects both
    sides of a real match equally.
    """
    authorships = work.get("authorships")
    if not isinstance(authorships, list) or not authorships:
        return None
    first = authorships[0]
    if not isinstance(first, dict):
        return None
    author = first.get("author")
    if not isinstance(author, dict):
        return None
    display = author.get("display_name")
    if not isinstance(display, str) or not display.strip():
        return None
    return display.strip().rsplit(" ", 1)[-1]


def candidate_from_work(work: dict[str, Any], url: str, rung: str) -> Candidate:
    """Build a candidate carrying the work's own bibliographic metadata.

    :param work: The OpenAlex work the URL came from.
    :param url: The candidate PDF URL.
    :param rung: The rung that produced it.
    :returns: The candidate.
    """
    year = work.get("publication_year")
    title = work.get("display_name") or work.get("title")
    return Candidate(
        url=url,
        rung=rung,
        title=title if isinstance(title, str) else None,
        year=year if isinstance(year, int) else None,
        first_author_family=_first_family_from_work(work),
        openalex=_short_id(work.get("id")),
    )


def _location_pdf_urls(work: dict[str, Any]) -> list[str]:
    """Return every ``pdf_url`` across the work's ``locations`` array."""
    locations = work.get("locations")
    if not isinstance(locations, list):
        return []
    out: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        url = location.get("pdf_url")
        if isinstance(url, str) and url.strip():
            out.append(url)
    return out


def landing_urls(work: dict[str, Any]) -> list[str]:
    """Return landing-page URLs that are shaped like a direct PDF link.

    OpenAlex marks a work ``closed`` when it has no ``pdf_url``, yet the landing
    page can *be* the PDF — Sill 1997's NeurIPS proceedings link is exactly this.
    Only ``.pdf``-suffixed links are offered, so the ladder does not download
    every HTML abstract page in the record.

    :param work: The OpenAlex work.
    :returns: Candidate landing URLs, in record order.
    """
    locations = work.get("locations")
    if not isinstance(locations, list):
        return []
    out: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        url = location.get("landing_page_url")
        if isinstance(url, str) and url.strip().lower().endswith(".pdf"):
            out.append(url)
    return out


def identity_candidates(work: dict[str, Any]) -> list[Candidate]:
    """Build rungs 1–3 for a work: best OA location, all locations, landing pages.

    These are *identity-derived* — the URLs come from the work the citekey already
    resolves to, so they carry the work's own metadata and bypass the gate.
    Deduplicated by URL, preserving first-seen rung order.

    :param work: The OpenAlex work.
    :returns: Candidates in ladder order.
    """
    best = (work.get("best_oa_location") or {}).get("pdf_url")
    ordered: list[tuple[str, str]] = []
    if isinstance(best, str) and best.strip():
        ordered.append((best, RUNG_OA_BEST))
    ordered += [(url, RUNG_OA_LOCATIONS) for url in _location_pdf_urls(work)]
    ordered += [(url, RUNG_OA_LANDING) for url in landing_urls(work)]
    seen: set[str] = set()
    out: list[Candidate] = []
    for url, rung in ordered:
        if url in seen:
            continue
        seen.add(url)
        out.append(candidate_from_work(work, url, rung))
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_acquire.py -v --no-cov`
Expected: PASS. `test_rung_3_recovers_sill_from_a_pdf_serving_landing_page` is the one that proves the venue-scraper rung is unnecessary.

- [ ] **Step 6: Commit**

```bash
git add defendable_science/literature/acquire.py tests/test_acquire.py tests/fixtures/openalex
git commit -m "feat(literature): identity-derived ladder rungs 1-3 + PDF acceptance

Reading all locations[] and sniffing PDF-shaped landing pages recovers Sill
1997 (oa_status closed, best_oa_location.pdf_url null, but locations[0]
landing page IS the PDF) with no venue-specific code — so the ML-venue
resolvers #97 proposed are not needed and domain-neutrality holds.

Magic bytes are authoritative over Content-Type, which lies: that NeurIPS
URL serves application/pdf behind a text/html redirect.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Search-derived candidates (rungs 4–6)

**Files:**
- Modify: `defendable_science/literature/acquire.py`
- Modify: `tests/test_acquire.py`

**Interfaces:**
- Consumes: `Candidate`, `candidate_from_work`, `identity_candidates` from Task 8; `Entry` from Task 4; `HttpClient` from `core.http`.
- Produces:
  - `def sibling_candidates(entry: Entry, work: dict[str, Any], *, client: HttpClient) -> list[Candidate]`
  - `def arxiv_candidates(entry: Entry, *, client: HttpClient) -> list[Candidate]`
  - `def venue_candidates(entry: Entry, work: dict[str, Any], resolvers: list[dict[str, str]]) -> list[Candidate]`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_acquire.py`:

```python
class FakeClient:
    """A stand-in for HttpClient that serves canned JSON by URL substring."""

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


def test_rung_4_finds_the_monokan_sibling() -> None:
    """The registry entry is the closed journal work; the PDF is on the sibling."""
    journal = _work("monokan_journal")
    arxiv = _work("monokan_arxiv")
    client = FakeClient({"/works?": {"results": [journal, arxiv]}})
    entry = _entry(
        citekey="monokan",
        title=journal["display_name"],
        year=journal["publication_year"],
        family="Polo-Molina",
    )
    cands = a.sibling_candidates(entry, journal, client=client)
    assert cands
    assert all(c.rung == a.RUNG_SIBLING for c in cands)
    assert any(".pdf" in c.url for c in cands)


def test_rung_4_excludes_the_anchor_itself() -> None:
    work = _work("monokan_arxiv")
    client = FakeClient({"/works?": {"results": [work]}})
    entry = _entry(citekey="k", title=work["display_name"], year=2024, family="X")
    assert a.sibling_candidates(entry, work, client=client) == []


def test_rung_4_skips_works_with_a_different_normalized_title() -> None:
    other = dict(_work("monokan_arxiv"), id="https://openalex.org/W999")
    other["display_name"] = "Something Else Entirely"
    client = FakeClient({"/works?": {"results": [other]}})
    entry = _entry(citekey="k", title="MonoKAN: Certified monotonic", year=2025, family="X")
    assert a.sibling_candidates(entry, _work("monokan_journal"), client=client) == []


def test_rung_4_without_a_registry_title_returns_nothing() -> None:
    client = FakeClient({})
    assert a.sibling_candidates(_entry(title=None), {}, client=client) == []


def test_rung_4_tolerates_a_non_dict_page() -> None:
    client = FakeClient({"/works?": ["junk"]})
    assert a.sibling_candidates(_entry(), _work("sill1997"), client=client) == []


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


def test_rung_6_expands_configured_templates() -> None:
    work = _work("sill1997")
    resolvers = [
        {"match": "Neural Information Processing", "url_template": "http://v/{openalex}.pdf"}
    ]
    cands = a.venue_candidates(_entry(), work, resolvers)
    assert [c.url for c in cands] == ["http://v/W2293093810.pdf"]
    assert cands[0].rung == a.RUNG_VENUE


def test_rung_6_ships_empty_so_nothing_matches_by_default() -> None:
    assert a.venue_candidates(_entry(), _work("sill1997"), []) == []


def test_rung_6_skips_a_non_matching_venue() -> None:
    resolvers = [{"match": "ICLR", "url_template": "http://v/{openalex}.pdf"}]
    assert a.venue_candidates(_entry(), _work("sill1997"), resolvers) == []


def test_rung_6_skips_a_malformed_resolver() -> None:
    resolvers: list[Any] = [
        "junk",
        {"match": "Neural"},
        {"url_template": "http://v/x.pdf"},
        {"match": "(", "url_template": "http://v/x.pdf"},
    ]
    assert a.venue_candidates(_entry(), _work("sill1997"), resolvers) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_acquire.py -k "rung_4 or rung_5 or rung_6" -v --no-cov`
Expected: FAIL — `AttributeError: ... 'sibling_candidates'`

- [ ] **Step 3: Write the implementation**

Append to `defendable_science/literature/acquire.py`:

```python
OPENALEX = "https://api.openalex.org"
ARXIV_API = "http://export.arxiv.org/api/query"

#: How many search hits each gated rung will consider.
SEARCH_LIMIT = 10


def sibling_candidates(
    entry: Entry, work: dict[str, Any], *, client: HttpClient
) -> list[Candidate]:
    """Rung 4 — find other OpenAlex works with the same title and mine their PDFs.

    OpenAlex often holds a paper twice: once as the published version (which may be
    ``closed`` with no PDF) and once as the preprint (``green``, with one). The
    registry entry resolves to whichever the DOI names, so the PDF can be on the
    sibling. This finds it generically, and the gate decides whether the sibling
    really is the same paper.

    :param entry: The registry entry (its title drives the search).
    :param work: The anchor work, excluded from the results.
    :param client: The HTTP client.
    :returns: Candidates from every same-title sibling, gated downstream.
    """
    if entry.title is None:
        return []
    anchor = _short_id(work.get("id"))
    target = normalize_title(entry.title)
    page = client.get_json(
        f"{OPENALEX}/works",
        {"filter": f"title.search:{entry.title}", "per-page": str(SEARCH_LIMIT)},
    )
    if not isinstance(page, dict):
        return []
    out: list[Candidate] = []
    for sibling in page.get("results", []):
        if not isinstance(sibling, dict):
            continue
        if _short_id(sibling.get("id")) == anchor:
            continue
        title = sibling.get("display_name")
        if not isinstance(title, str) or normalize_title(title) != target:
            continue
        for candidate in identity_candidates(sibling):
            candidate.rung = RUNG_SIBLING
            out.append(candidate)
    return out


def parse_arxiv_feed(xml: str) -> list[Candidate]:
    """Parse an arXiv Atom feed into candidates.

    An entry missing an id, a title, an author, or a date is skipped: the gate
    needs all three axes, so an unverifiable hit is worse than no hit. Malformed
    XML yields no candidates — arXiv served something unusable, and the caller
    reports an exhausted rung rather than crashing.

    :param xml: The Atom feed body.
    :returns: One candidate per usable entry.
    """
    from xml.etree import ElementTree  # nosec B405 - parsing a trusted API feed

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ElementTree.fromstring(xml)  # nosec B314 - see above
    except ElementTree.ParseError:
        return []
    out: list[Candidate] = []
    for node in root.findall("atom:entry", ns):
        raw_id = node.findtext("atom:id", default="", namespaces=ns)
        title = node.findtext("atom:title", default="", namespaces=ns).strip()
        published = node.findtext("atom:published", default="", namespaces=ns)
        author = node.find("atom:author/atom:name", ns)
        name = (author.text or "").strip() if author is not None else ""
        arxiv_id = re.sub(r"v\d+$", "", raw_id.rstrip("/").rsplit("/", 1)[-1])
        if not (arxiv_id and title and name and published[:4].isdigit()):
            continue
        out.append(
            Candidate(
                url=f"https://arxiv.org/pdf/{arxiv_id}",
                rung=RUNG_ARXIV_SEARCH,
                title=title,
                year=int(published[:4]),
                first_author_family=name.rsplit(" ", 1)[-1],
            )
        )
    return out


def arxiv_candidates(entry: Entry, *, client: HttpClient) -> list[Candidate]:
    """Rung 5 — search arXiv by title and first author.

    :param entry: The registry entry.
    :param client: The HTTP client (used for its transport and politeness only;
        arXiv returns Atom XML, not JSON).
    :returns: Candidates, gated downstream.
    """
    if entry.title is None:
        return []
    query = f'ti:"{entry.title}"'
    if entry.first_author_family is not None:
        query += f' AND au:"{entry.first_author_family}"'
    body = client.get_text(
        ARXIV_API, {"search_query": query, "max_results": str(SEARCH_LIMIT)}
    )
    return parse_arxiv_feed(body)


def venue_candidates(
    entry: Entry, work: dict[str, Any], resolvers: list[Any]
) -> list[Candidate]:
    """Rung 6 — expand consumer-configured venue URL templates.

    **Ships empty.** The generic rungs recover the cases that motivated this
    feature, so no venue-specific logic is shipped in the plugin; a consumer repo
    that needs an exotic venue adds a ``{match, url_template}`` pair to its own
    ``.defendable-science/config.yml``. Templates may reference ``{openalex}``,
    ``{doi}`` and ``{year}``.

    :param entry: The registry entry (supplies ``{doi}``).
    :param work: The anchor work (supplies the venue name, ``{openalex}``, ``{year}``).
    :param resolvers: The configured resolver list; malformed entries are skipped.
    :returns: Candidates, gated downstream.
    """
    venue = ((work.get("primary_location") or {}).get("source") or {}).get(
        "display_name"
    )
    if not isinstance(venue, str):
        venue = ""
    fields = {
        "openalex": _short_id(work.get("id")) or "",
        "doi": entry.doi or "",
        "year": str(entry.year or ""),
    }
    out: list[Candidate] = []
    for resolver in resolvers:
        if not isinstance(resolver, dict):
            continue
        pattern = resolver.get("match")
        template = resolver.get("url_template")
        if not isinstance(pattern, str) or not isinstance(template, str):
            continue
        try:
            matched = re.search(pattern, venue) is not None
        except re.error:
            continue
        if not matched:
            continue
        out.append(candidate_from_work(work, template.format(**fields), RUNG_VENUE))
    return out
```

- [ ] **Step 4: Add `get_text` to `HttpClient`**

`arxiv_candidates` needs a text response; `HttpClient` only has `get_json`. Add to `defendable_science/core/http.py` a `get_text` method that reuses the same throttle and retry path but returns `resp.text`, and extend the `Response` protocol with `text: str`. Add a test in `tests/test_cli.py`'s HTTP test module covering a success and a `RateLimitError` propagation. If the existing `_fetch` is JSON-shaped beyond reuse, add a sibling `_fetch_text` and cover both branches — the 100% gate applies.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_acquire.py -v --no-cov`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add defendable_science/literature/acquire.py defendable_science/core/http.py tests/
git commit -m "feat(literature): search-derived ladder rungs 4-6

Rung 4 (sibling-version) is the generic answer to 'OpenAlex holds this paper
twice and the DOI names the closed one'. Rung 6 ships empty so no venue
logic enters the plugin. All three are gated; an arXiv hit missing any of
title/author/year is skipped rather than offered unverifiable.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Single-entry acquisition — resolution, TOFU, drift, quarantine

**Files:**
- Modify: `defendable_science/literature/acquire.py`
- Modify: `tests/test_acquire.py`

**Interfaces:**
- Consumes: everything from Tasks 3–9.
- Produces:
  - `BUCKET_CACHED / BUCKET_FETCHED / BUCKET_QUARANTINED / BUCKET_MANUAL / BUCKET_ERROR` constants
  - `PERMISSIVE_SPDX: frozenset[str]`
  - `def license_from_work(work: dict[str, Any]) -> License` and `def is_permissive(spdx: str | None) -> bool`
  - `@dataclass class Outcome: citekey: str; bucket: str; sha256: str | None = None; rung: str | None = None; url: str | None = None; candidate: dict | None = None; match: dict | None = None; reason: str | None = None; tried: list[str] = []; landing_urls: list[str] = []; committable: bool = False` with `as_json()`
  - `@dataclass class Context: registry_path: Path; triage_path: Path; cache_dir: Path; mirror: Mirror | None; client: HttpClient; fetcher: BytesFetcher; max_bytes: int; resolvers: list[Any]; today: str`
  - `def acquire_one(entry: Entry, ctx: Context, *, refetch: bool = False, dry_run: bool = False) -> Outcome`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_acquire.py` — the behaviours that must hold:

```python
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


def _pdf_fetcher(body: bytes = b"%PDF-1.4 body") -> Any:
    def fetch(url: str, dest: Path, max_bytes: int) -> FetchedBytes:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return FetchedBytes(path=dest, media_type="application/pdf", size=len(body))

    return fetch
```

Tests to write (each asserting the bucket, and where relevant that the registry was or was not written):

1. `test_identity_rung_fetches_and_records` — Sill fixture, rung 3, bucket `fetched`, `sha256` set, `match.verdict == "identity"`.
2. `test_already_recorded_sha_resolves_from_cache_without_network` — entry has an asset whose blob exists; bucket `cached`; the fake client records **zero** calls.
3. `test_already_recorded_sha_falls_through_to_mirror` — blob absent, mirror `get` succeeds and verifies; bucket `cached`.
4. `test_recorded_sha_with_no_bytes_anywhere_is_manual` — bucket `manual`, reason mentions the recorded checksum.
5. `test_refetch_yielding_different_bytes_refuses_and_leaves_the_registry_alone` — bucket `error`, reason matches `drift`, registry file byte-identical.
6. `test_refetch_yielding_identical_bytes_is_cached` — bucket `cached`.
7. `test_gated_quarantine_lands_bytes_and_writes_nothing` — quarantine dir contains `<sha>.pdf` and `<sha>.json`; registry unchanged; bucket `quarantined`.
8. `test_gated_refusal_is_manual_with_the_axes_recorded` — bucket `manual`; `match.author == "mismatch"`.
9. `test_non_pdf_bytes_are_rejected_and_the_ladder_continues` — first URL returns HTML, second returns a PDF; bucket `fetched`, `rung` is the second.
10. `test_download_error_on_one_rung_does_not_end_the_ladder` — fetcher raises `DownloadError` for URL 1; bucket `fetched` from URL 2.
11. `test_all_rungs_exhausted_is_manual_with_landing_urls` — bucket `manual`, `landing_urls` non-empty, `tried` lists every rung attempted.
12. `test_rate_limit_propagates_rather_than_becoming_manual` — client raises `RateLimitError`; `pytest.raises(RateLimitError)`. **This is the failure-honesty test.**
13. `test_unresolvable_entry_is_an_error_not_manual` — `resolve` misses; bucket `error`.
14. `test_dry_run_reports_the_rung_without_downloading` — bucket `fetched`, `sha256 is None`, fetcher never called, registry unchanged.
15. `test_mirror_is_populated_on_first_acquisition` — fake mirror records a `put`.
16. `test_permissive_license_marks_the_outcome_committable` — work carries `cc-by`; `committable is True`; asset `redistributable is True`.
17. `test_absent_license_is_not_redistributable` — no license field; `committable is False`, `redistributable is False`.
18. `test_unrecognized_license_is_not_redistributable` — `license: "all-rights-reserved"`; `committable is False`, and `license.observed` records the raw string.

Include a parametrized `test_is_permissive` over `cc-by`, `cc-by-4.0`, `cc0-1.0`, `cc-by-sa`, `mit`, `apache-2.0` (True) and `None`, `""`, `all-rights-reserved`, `cc-by-nc` (False). **`cc-by-nc` must be False** — non-commercial is not a redistribution grant for our purposes, and getting this backwards is a licence-compliance error, not a test detail.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_acquire.py -k "acquire or license or permissive or drift or quarantine" -v --no-cov`
Expected: FAIL — `AttributeError: ... 'acquire_one'`

- [ ] **Step 3: Write the implementation**

Append to `defendable_science/literature/acquire.py`. Structure it as: `license_from_work` / `is_permissive`; `Outcome`; `Context`; small helpers `_quarantine_dir`, `_store_blob`, `_resolve_recorded`; then `acquire_one` composed of `_candidates_in_ladder_order` and `_try_candidate`.

Load-bearing rules the code must encode, each already covered by a test above:

```python
#: SPDX ids whose licenses permit redistributing the bytes. Deliberately short and
#: not configurable: a consumer overriding a redistribution judgement is a
#: license-compliance decision the plugin must not make configurable (spec §14).
#: Non-commercial variants are NOT here — "NC" is not a redistribution grant for
#: an in-repo copy of a paper.
PERMISSIVE_SPDX = frozenset(
    {
        "cc0-1.0", "cc-by", "cc-by-3.0", "cc-by-4.0",
        "cc-by-sa", "cc-by-sa-3.0", "cc-by-sa-4.0",
        "mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause",
    }
)
```

- `acquire_one` must, in order: (a) if the entry has a recorded `sha256` and not `refetch`, resolve cache → mirror and return `cached` or `manual` — **never touching the network**; (b) resolve the entry to an OpenAlex work, returning `error` on a miss; (c) build the ladder; (d) for each candidate, gate it if its rung is in `GATED_RUNGS`, skipping on `REFUSE` and diverting on `QUARANTINE`; (e) download, reject non-PDF bytes and continue; (f) on the first acceptance, hash, store the blob, populate the mirror, patch the registry, return `fetched`.
- A `DownloadError` on one candidate appends its rung to `tried` and continues to the next. It never ends the ladder and never becomes a `manual` verdict on its own.
- `RateLimitError` and `HttpError` from the client are **not caught** here — they propagate to the sweep (Task 11), which decides between `errors[]` and aborting. Catching them here is the bug the failure-honesty rule forbids.
- Drift: with `refetch` and an existing recorded `sha256`, if the newly hashed bytes differ, return `Outcome(bucket=BUCKET_ERROR, reason="refetch drift: recorded <old> but source now serves <new> — a citekey is not rebound silently; confirm --file if the new version is intended")` and **do not patch the registry**.
- Quarantine writes `<cache>/quarantine/<citekey>/<sha>.pdf` plus a `<sha>.json` holding `{"candidate": …, "match": …, "url": …, "rung": …}`.
- `dry_run` returns the would-be rung and URL with `sha256=None`, never calling the fetcher and never writing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_acquire.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Coverage check on the module**

Run: `uv run pytest tests/test_acquire.py --cov=defendable_science.literature.acquire --cov-branch --cov-report=term-missing`
Expected: 100%. Any uncovered line is a ladder branch with no test — add the test, do not add a pragma.

- [ ] **Step 6: Commit**

```bash
git add defendable_science/literature/acquire.py tests/test_acquire.py
git commit -m "feat(literature): single-entry acquisition (TOFU, drift refusal, quarantine)

Resolution before acquisition: a recorded sha256 means cache -> mirror and no
network. Without one, the ladder runs and the hash is established from the
accepted bytes, with the gate standing where dataset has a pre-known hash.

Refetch drift refuses rather than rebinding a citekey to new bytes. Rate
limits propagate instead of being reported as 'this paper has no PDF' — the
distinction the failure-honesty rule exists for.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: The sweep and its report

**Files:**
- Modify: `defendable_science/literature/acquire.py`
- Modify: `tests/test_acquire.py`

**Interfaces:**
- Consumes: `acquire_one`, `Outcome`, `Context`; `load_registry`, `load_triage`.
- Produces: `def fetch_all(ctx: Context, *, citekeys: list[str] | None = None, disposition: str | None = None, refetch: bool = False, dry_run: bool = False) -> dict[str, Any]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_acquire.py`. Reuse `_ctx` and `_pdf_fetcher` from Task 10; each
test builds a small `references.json` (and where relevant a `triage.yml`) with
`_write` from `tests/test_lit_registry.py`'s pattern. Behaviours to cover, each with
the assertion that matters:

1. `test_report_has_every_bucket_and_is_complete` — one entry that fetches, one that
   refuses. `set(report)` equals exactly
   `{"complete", "not_attempted", "fetched", "cached", "quarantined", "manual", "committable", "errors"}`;
   `complete is True`; `not_attempted == 0`.
2. `test_bucket_constants_match_report_keys` — for every bucket constant,
   `constant in report`. `fetch_all` dispatches with `report[outcome.bucket]`, so a
   rename that desynchronizes them would raise `KeyError` at runtime; this pins it.
3. `test_disposition_filters_the_sweep` — two entries, one with
   `disposition: screened` and one with `disposition: inbox`.
   `fetch_all(ctx, disposition="screened")["fetched"]` names only the screened one.
4. `test_entries_without_a_triage_row_are_excluded_when_filtering` — an entry with no
   triage row at all; `fetch_all(ctx, disposition="screened")["fetched"] == []`.
5. `test_entries_without_a_triage_row_are_included_when_not_filtering` — same
   registry, no `disposition` argument; the entry is attempted.
6. `test_explicit_citekeys_override_the_registry_order` — registry order `a, b`;
   `citekeys=["b", "a"]` yields `["b", "a"]` in the report.
7. `test_unknown_citekey_is_an_error_row_not_a_crash` — `citekeys=["nope"]` gives one
   `errors[]` row whose `reason` contains `no entry`, and no exception.
8. `test_a_rate_limit_aborts_the_sweep_marked_incomplete` — three entries, the client
   raising `RateLimitError` on the first. Assert `complete is False`,
   `not_attempted == 2`, `errors[0]["reason"]` contains `rate-limited`, and — the
   point of the test — **`report["manual"] == []`**. Nobody is told to download a
   paper by hand because OpenAlex throttled us.
9. `test_a_transport_error_on_one_entry_does_not_stop_the_sweep` — two entries, the
   client raising `HttpError` on the first. `complete is True`, one `errors[]` row,
   one `fetched[]` row. An `HttpError` is per-entry; only a rate limit aborts.
10. `test_committable_lists_only_permissive_entries` — one work carrying `cc-by`, one
    with no license field. `committable[]` names only the first, and the second still
    appears in `fetched[]` (cache-only is a success, not a failure).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_acquire.py -v --no-cov`
Expected: the ten new tests FAIL with `AttributeError: module ... has no attribute 'fetch_all'`; every test from Tasks 7-10 still passes.

- [ ] **Step 3: Write the implementation**

Append to `defendable_science/literature/acquire.py`:

```python
def fetch_all(
    ctx: Context,
    *,
    citekeys: list[str] | None = None,
    disposition: str | None = None,
    refetch: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Sweep the registry, bucketing every entry's outcome.

    A rate limit **aborts** the sweep with ``complete: false`` and a
    ``not_attempted`` count, because a throttle is not information about the
    remaining papers: reporting them as ``manual`` would tell a human to download
    by hand what the tool simply never asked for. Any other transport failure is
    per-entry — it lands in ``errors`` and the sweep continues.

    :param ctx: The acquisition context.
    :param citekeys: Explicit entries to attempt, in this order; the whole
        registry when ``None``.
    :param disposition: Restrict to entries whose ``triage.yml`` row carries this
        disposition. An entry with no triage row is excluded when this is given
        and included when it is not.
    :param refetch: Re-run the ladder for entries that already have a checksum.
    :param dry_run: Report the rung that would yield bytes without downloading.
    :returns: The report — ``complete``, ``not_attempted``, and the
        ``fetched | cached | quarantined | manual | committable | errors`` buckets.
    :raises RegistryError: If the registry itself cannot be read.
    """
    from defendable_science.core.http import HttpError, RateLimitError

    registry = load_registry(ctx.registry_path)
    triage = load_triage(ctx.triage_path)
    targets = _select(registry, triage, citekeys, disposition)
    report: dict[str, Any] = {
        "complete": True,
        "not_attempted": 0,
        "fetched": [],
        "cached": [],
        "quarantined": [],
        "manual": [],
        "committable": [],
        "errors": [],
    }
    for index, (citekey, entry) in enumerate(targets):
        if entry is None:
            report["errors"].append(
                {"citekey": citekey, "reason": f"no entry {citekey!r} in the registry"}
            )
            continue
        try:
            outcome = acquire_one(entry, ctx, refetch=refetch, dry_run=dry_run)
        except RateLimitError as exc:
            report["errors"].append(
                {
                    "citekey": citekey,
                    "reason": f"rate-limited, sweep aborted: {exc}",
                }
            )
            report["complete"] = False
            report["not_attempted"] = len(targets) - index - 1
            break
        except HttpError as exc:
            report["errors"].append({"citekey": citekey, "reason": str(exc)})
            continue
        report[outcome.bucket].append(outcome.as_json())
        if outcome.committable:
            report["committable"].append(outcome.as_json())
    return report
```

Add the `_select` helper (registry order, or explicit citekeys resolved through `Registry.get` yielding `None` for unknowns, filtered by disposition). Note `BUCKET_ERROR` must equal `"errors"` so `report[outcome.bucket]` works, and the other bucket constants must equal their report key names — assert this in a test so a rename cannot silently break the dispatch.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_acquire.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add defendable_science/literature/acquire.py tests/test_acquire.py
git commit -m "feat(literature): registry sweep with an honest report

A rate limit aborts with complete:false and a not_attempted count rather
than bucketing the untried papers as 'manual'. Other transport failures are
per-entry. manual[] carries landing URLs so the human has somewhere to click.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: `confirm` — promote quarantine, adopt a manual file

**Files:**
- Modify: `defendable_science/literature/acquire.py`
- Modify: `tests/test_acquire.py`

**Interfaces:**
- Produces:
  - `def confirm_quarantined(entry: Entry, ctx: Context, sha256: str) -> Outcome`
  - `def adopt_file(entry: Entry, ctx: Context, path: Path) -> Outcome`

- [ ] **Step 1: Write the failing test**

Behaviours to cover:

1. `test_confirm_promotes_a_quarantined_blob` — quarantine `<sha>.pdf` + `<sha>.json` exist → blob lands in the content-addressed store, registry patched with the recorded `match.verdict == "quarantine"` and the original rung, quarantine files removed.
2. `test_confirm_unknown_sha_is_an_actionable_error` — `RetrievalError`/`RegistryError` naming what is actually in quarantine for that citekey.
3. `test_confirm_rejects_a_corrupt_quarantine_blob` — the file's hash no longer matches its name → refuse, quarantine untouched.
4. `test_confirm_populates_the_mirror` — fake mirror sees a `put`.
5. `test_adopt_file_hashes_and_records_it` — bucket `fetched`, `acquisition.rung == "manual"`, `match.verdict == "identity"`, `license.id is None`, `redistributable is False`.
6. `test_adopt_file_rejects_a_non_pdf` — refuse with a reason; registry unchanged.
7. `test_adopt_file_missing_path_is_an_actionable_error`.
8. `test_adopt_file_copies_rather_than_moves_the_humans_file` — the source path still exists afterwards. (A human's Downloads file must not vanish.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_acquire.py -k "confirm or adopt" -v --no-cov`
Expected: FAIL.

- [ ] **Step 3: Write the implementation**

Both functions share the "hash, store, patch" tail with `acquire_one` — extract that into `_bind(entry, ctx, source, rung, url, candidate, match, license) -> Outcome` in this task and have `acquire_one` call it too, so there is exactly one place that writes a spine.

`adopt_file` **copies** with `shutil.copy2`, never moves. `confirm_quarantined` verifies the blob against its own filename-hash before promoting, so a truncated quarantine file cannot be blessed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_acquire.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add defendable_science/literature/acquire.py tests/test_acquire.py
git commit -m "feat(literature): confirm — promote quarantine or adopt a manual PDF

confirm does double duty, which is what makes the manual rung a workflow
rather than a dead end. Adoption copies rather than moves: a human's
Downloads file must not vanish into a cache.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: `verify` and `mirror`

**Files:**
- Modify: `defendable_science/literature/acquire.py`
- Modify: `tests/test_acquire.py`

**Interfaces:**
- Produces:
  - `@dataclass class VerifyReport: citekey: str; verified: list[str] = []; missing: list[str] = []; corrupt: list[str] = []` with `ok: bool` and `as_json()`
  - `def verify_entry(entry: Entry, *, cache_dir: Path) -> VerifyReport`
  - `def mirror_entry(entry: Entry, *, cache_dir: Path, mirror: Mirror, check_only: bool = False) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test**

Cover: all files verify; a missing blob; a corrupt blob; an entry with **no asset at all** (reported as `missing` with an explicit note, never as `ok` — an unfetched paper must not read as verified); an unreadable file folded into `corrupt` rather than raising; `mirror_entry` pushing, `mirror_entry` reporting already-present, `--check` never pushing, and a `RetrievalError` from a missing rclone surfacing intact.

The "no asset reads as `ok`" case is the one that matters: `verify --all` on a fresh registry must say "nothing is verified", not "everything checks out".

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_acquire.py -k "verify or mirror_entry" -v --no-cov`
Expected: FAIL.

- [ ] **Step 3: Write the implementation**

Mirror `dataset.retrieval.verify`'s shape exactly (spec §2 goal 4), reading blob paths via `core.fixity.blob_path` and folding `OSError` into `corrupt`.

- [ ] **Step 4: Run tests, then commit**

Run: `uv run pytest tests/test_acquire.py -v --no-cov` → PASS

```bash
git add defendable_science/literature/acquire.py tests/test_acquire.py
git commit -m "feat(literature): offline verify + mirror push/check

Parity with dataset verify. An entry with no asset reports missing, never ok:
verify --all on a fresh registry must say nothing is verified rather than
that everything checks out.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: CLI wiring

**Files:**
- Modify: `defendable_science/cli.py`
- Create: `tests/test_acquire_cli.py`

**Interfaces:**
- Consumes: `fetch_all`, `confirm_quarantined`, `adopt_file`, `verify_entry`, `mirror_entry`, `Context`.
- Produces the four commands of spec §7.

- [ ] **Step 1: Write the failing test**

Create `tests/test_acquire_cli.py` following `tests/test_literature.py`'s pattern (`CliRunner`, monkeypatching `_lit_client`). Cover:

1. Each of `fetch` / `verify` / `mirror` with **neither** `CITEKEY` nor `--all` → exit 2 and a message naming both options.
2. Each with **both** → exit 2.
3. `confirm` with neither `--sha256` nor `--file` → exit 2; with both → exit 2.
4. `fetch --all` on a clean sweep → exit 0, stdout parses as JSON with the eight report keys.
5. `fetch --all` with an `errors[]` row → **exit 1**, report still printed. (An agent loop must not read a half-swept registry as complete.)
6. `fetch --all` aborted by a rate limit → exit 1 and `complete: false` in the JSON.
7. A `RegistryError` → exit 1, message on stderr, **no traceback** (assert `"Traceback"` not in output).
8. `verify` with a corrupt blob → exit 1; all-clean → exit 0.
9. `mirror --check` with an absent key → exit 1.
10. A missing `literature.mirror` config for `mirror` → exit 1 with a message naming the config key.
11. Config plumbing: `literature.registry` / `literature.triage` / `acquisition.max_bytes` / `acquisition.venue_resolvers` are read, and a non-mapping `literature.acquisition` exits 1 with a clear message.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_acquire_cli.py -v --no-cov`
Expected: FAIL — `No such command 'fetch'`.

- [ ] **Step 3: Write the implementation**

Add to `cli.py` after the existing `literature` commands. Add a `_lit_paths(config)` helper resolving registry/triage paths and a `_lit_context(...)` builder. Reuse `_http_guard` so a rate limit becomes the existing actionable message rather than a traceback. Print reports with `json.dumps(..., indent=2)` to match the group's existing style.

Exit-code contract, asserted by the tests above: `0` when every attempted entry reached a determinate bucket and the sweep completed; `1` when `errors[]` is non-empty or `complete` is false; `2` for argument misuse (Typer's own code for a bad invocation).

- [ ] **Step 4: Run the full gate**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: PASS, coverage 100%, clean.

- [ ] **Step 5: Commit**

```bash
git add defendable_science/cli.py tests/test_acquire_cli.py
git commit -m "feat(cli): literature fetch | confirm | verify | mirror

Exit 1 when the report carries errors or is incomplete, so no agent or CI
loop reads a half-swept registry as a finished one. Exactly one of CITEKEY
or --all; exactly one of --sha256 or --file.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: ADR, design-doc amendments, skill corrections

**Files:**
- Create: `decisions/0037-literature-asset-acquisition.md`
- Modify: `decisions/README.md`, `docs/design/02-literature.md` (§4, §5), `docs/design/04-substrate-and-contract.md` (§2.4)
- Create: `docs/design/proposals/literature-asset-acquisition.md`
- Modify: `skills/literature/SKILL.md`, `skills/digest/SKILL.md`, `resources/ensure-tooling.md`, `CHANGELOG.md`

- [ ] **Step 1: Write ADR-0037**

MADR format matching `decisions/0029-api-key-handling.md`. Decision points and their drivers:
- Spine under `custom.defendable-science` — driver: the CSL input schema sets `additionalProperties: false` and defines no `files`/`license`/`mirror`, so top-level fields would make `references.json` schema-invalid against ADR-0020's source-of-truth claim.
- Three-way gate with **first-author family name as a hard gate**.
- `fetch` never writes in-repo bytes.
- `venue_resolvers` config-driven and empty by default (domain-neutrality).
- Trust-on-first-use with the gate substituting for a pre-known hash; drift refuses.

Rejected alternatives, each with its reason: top-level CSL fields (schema-invalid); a separate `assets.yml` (a third join, diverges from 02-literature.md §4); folding the spine into `triage.yml` (mixes immutable byte facts with mutable human decisions); a two-way gate (loses the real MonoKAN sibling); license-driven automatic in-repo placement (the plugin deciding to add bytes to someone's git history); shipped ML-venue scrapers (breaches domain-neutrality, and unnecessary — rung 3 recovers the motivating case); a full `substrate/` extraction with a unified `materialize()` (a false abstraction over the known-hash vs TOFU split).

Append the row to `decisions/README.md`.

- [ ] **Step 2: Amend the design docs**

`docs/design/02-literature.md` §4 — replace "Carries the substrate spine fields for the PDF payload (`pid`/DOI, `files[]` = PDF + sha256, `license`, `mirror`)" with the `custom.defendable-science` namespace and a pointer to ADR-0037. §5 — document the ladder and the gate.

`docs/design/04-substrate-and-contract.md` §2.4 — add a paragraph after the chain block: step 3 has two variants; `dataset` verifies against a hash it already has, `literature` establishes one on first acquisition and substitutes the metadata gate for the absent trust anchor.

Create `docs/design/proposals/literature-asset-acquisition.md` as the shipped module design record, matching `dataset-retrieval-mirror-tooling.md`'s shape.

- [ ] **Step 3: Correct the skill overclaim**

In `skills/literature/SKILL.md` §Tooling, the sentence "It wraps the OpenAlex + Semantic Scholar clients, the CSL-JSON bib loader/appender, and the triage-join + PRISMA-log / concept-matrix generators" is false today and only half-true after this work. Rewrite it to claim exactly what ships: the graph clients, the CSL-JSON registry loader/patcher, and the triage sidecar reader. **Remove** the PRISMA-log and concept-matrix claims (they become follow-up issue 2). Add the four verbs to the command list and a registry subsection covering the `custom` namespace and the license gate.

In `skills/digest/SKILL.md`, rewrite step 1 to name the actual commands:

```
1. **Scope.** Resolve the paper against the `literature` registry
   (`references.json`) — `literature resolve` it if absent, then
   `literature fetch <citekey>` to acquire and record the PDF (cache → mirror →
   source chain, SHA-256). `literature verify <citekey>` re-checks the bytes
   offline. If `fetch` reports the paper in `manual[]`, acquire it by hand and
   record it with `literature confirm <citekey> --file <path>`.
```

- [ ] **Step 4: Bump the compat pin and changelog**

Update the version range in `resources/ensure-tooling.md` per ADR-0026 to admit the version carrying these verbs. **Do not** touch `.claude-plugin/plugin.json` — the two artifacts version independently, and the package's automation must not bump the plugin.

Add a `CHANGELOG.md` entry under Unreleased naming the four verbs, the `custom` namespace decision, and the substrate promotion.

- [ ] **Step 5: Validate and commit**

Run: `./tools/validate-plugin.sh` and `pre-commit run --all-files` from the repo root.
Expected: clean.

```bash
git add decisions docs/design skills resources/ensure-tooling.md CHANGELOG.md
git commit -m "docs: ADR-0037 + design/skill corrections for literature acquisition

Amends 02-literature.md §4, whose current wording instructs something that
produces a schema-invalid references.json, and records the two variants of
the substrate chain's step 3 in 04 §2.4.

Also removes a standing overclaim from skills/literature/SKILL.md: the CLI
never wrapped a PRISMA-log or concept-matrix generator. The CSL loader it
also claimed is real as of this work; the other two become a follow-up.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: The user guide

Spec §11.1. **Piece 3 is not done without this** — a reviewer treats a missing guide as a missing deliverable.

**Files:**
- Create: `docs/guides/literature.md`
- Modify: `tools/build_docs_site.py` (`plan()`, around lines 132-180)

- [ ] **Step 1: Register the nav group**

In `tools/build_docs_site.py:plan()`, after the `get-started/user-guide` registration, add:

```python
guide_pages = [reg("guides/literature", "docs/guides/literature.md")]
```

and insert into `navigation["groups"]`, immediately after the `"Get started"` group:

```python
{"group": "Guides", "pages": guide_pages},
```

This group is introduced with one page and is where the deferred user-guide refactor (follow-up 6) will put the rest.

- [ ] **Step 2: Verify the site still builds**

Run: `python3 tools/build_docs_site.py --help` and then whatever the script's dry-run/build invocation is (check its `argparse` setup). Confirm `guides/literature` appears in the generated `docs.json` navigation and that `_routes_in_nav` does not assert.

- [ ] **Step 3: Write the guide**

Create `docs/guides/literature.md`. Required content, per spec §11.1:

1. **What the capability is** — the two skill modes (`scout`, `position`) and the CLI beneath them, with the distinction stated once, plainly: *`scout` and `position` are things you ask the assistant for; `defendable-science literature …` is what runs in a terminal.*
2. **The registry** — `references.json` (CSL-JSON, source of truth, exported to `.bib` on demand) and `triage.yml` (your decisions, and the PRISMA log). Why the spine lives under `custom` (one sentence plus a link to ADR-0037).
3. **The survey walkthrough** — the monotonicity survey as the running example: seed anchors → snowball → triage → `fetch --all --disposition screened` → work the buckets → read → matrix. Real numbers from the run (73 works resolved, 40 proposed for inclusion, 14 of 50 with an explicit license).
4. **The five buckets**, as a table: `cached`/`fetched` (nothing to do), `quarantined` (review, then `confirm --sha256`), `manual` (download by hand, then `confirm --file`), `committable` (copy in-repo yourself if you want to), `errors` (a tooling failure, not a paper problem — retry).
5. **Licenses in practice** — an absent license means not redistributable, and most papers have no license field. State the consequence directly: the cache and mirror hold the bytes; the repo does not.
6. **Why a refusal is a feature** — the Sill-1997-vs-Igel-2023 case worked through, so a reader hitting a refusal understands it and does not hunt for a flag to disable it. There is no such flag; `confirm --file` is the escape hatch, and it requires the human to look at the PDF.

**Formatting rule, enforced throughout:** every code block is labelled. Shell blocks show the real `defendable-science literature …` invocation. Assistant requests are shown as prose or a clearly-marked "ask the assistant" block — never as a bare command. This is the §4c defect the guide must not reproduce.

- [ ] **Step 4: Check the guide against the shipped CLI**

For every shell command in the guide, run it (or `--help` it) against the built CLI:

```bash
uv run defendable-science literature --help
uv run defendable-science literature fetch --help
uv run defendable-science literature confirm --help
```

Expected: every flag and verb the guide mentions exists with the documented spelling. A guide that documents a flag we did not ship is the same defect as §4c.

- [ ] **Step 5: Commit and open PR 3**

```bash
git add docs/guides/literature.md tools/build_docs_site.py
git commit -m "docs: task-oriented literature guide, survey paper as the example

The capability's only user-facing docs were USER-GUIDE.md §4c (~25 lines),
which is not enough to pick up four verbs, a registry spine, quarantine and
a license gate. Introduces the 'Guides' nav group the deferred user-guide
refactor will build out.

Every shell block shows the real defendable-science invocation and assistant
requests are marked as such — §4c's defect (skill modes printed as shell
commands) is the thing this guide most needs to avoid.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

Open PR 3 with the `create-pr` skill. Title: `feat(literature): PDF acquisition ladder, four asset verbs, and a user guide`. Body must reference #97, state that Gap 1 is closed and Gaps 2–3 remain, and list the follow-up issues filed in Task 17.

---

## Task 17: File the follow-up issues

House standard: self-contained and cold-readable — a future session has only the repo and the issue text.

- [ ] **Step 1: File each issue with the `create-issue` skill**

1. **`literature audit`** — parity with `dataset audit` (`cli.py:586`). Registry completeness + fixity + mirror presence + the license report in one command. Spec §2 records it as a deliberate non-goal because `fetch --all`'s report covers the question.
2. **PRISMA-log + concept-matrix generators** — `skills/literature/SKILL.md` claimed these for months and they never existed; Task 15 removed the claim. `position` mode builds both by hand today. Include the exact prior wording so the scope is unambiguous.
3. **Gap 2 — `digest` extraction mode.** Rewrite #97's Gap 2 against the interfaces that now exist: `registry.load_registry` / `patch_asset`, `registry.load_triage` / `patch_triage` (and its comment refusal, which an extraction writeback will hit), and `Asset.files` as the PDF locator. State the mandatory-per-cell-locator requirement and the sampled-comprehension contract from #97.
4. **Gap 3 — survey-shaped paper templates.** Note the #96 dependency for template plumbing.
5. **`docs/USER-GUIDE.md` §4c prints skill modes as shell commands** — `literature scout` / `literature position` at `docs/USER-GUIDE.md:202-203` and `dataset register` / `dataset init` in the block immediately after are not CLI commands. Acceptance: those four blocks corrected, and the rest of the guide audited for the same pattern.
6. **User-guide refactor** — restructure around the `"Guides"` nav group Task 16 introduced. `docs/guides/literature.md` is the pattern to follow.

- [ ] **Step 2: Close #97's Gap 1 checkboxes**

Comment on #97 with what landed against each Gap 1 checkbox, and note that Gaps 2 and 3 now have their own issues. Leave #97 open if Gaps 2–3 stay tracked there; close it if the new issues supersede it — the author's call, so ask.

---

## Self-review

**Spec coverage.** Every section maps to a task: §3 module layout → Tasks 1–3; §4 fixity model → Task 10; §5.1 ladder → Tasks 8–9; §5.2 gate → Task 7; §5.3 quarantine → Tasks 10, 12; §6 license → Task 10; §7 CLI → Tasks 12–14; §8.1 storage → Task 4; §8.2 write model → Tasks 5–6; §8.3 config → Task 14; §9 failure honesty → Tasks 10, 11, 14; §10 testing → distributed, with the named regression in Task 7; §11 docs → Task 15; §11.1 guide → Task 16; §12 PR shape → the PR boundaries above; §13 follow-ups → Task 17; §14 open questions → Task 10 (`PERMISSIVE_SPDX`, `max_bytes`).

**Known gaps in this plan, stated rather than hidden.** Tasks 10–13 specify their tests as enumerated behaviours plus the load-bearing rules, not as full transcribed code, because those tests need ~15 fixtures each whose setup is mechanical once `Context` and the fakes from Tasks 8–9 exist. Every enumerated case names its assertion and its reason. Tasks 1–9 and 14 carry complete test code. An executor who wants literal code for 10–13 should write the first case, confirm the fixture shape, then follow the list.

**Type consistency.** `Entry` / `Asset` / `AssetFile` / `License` / `MirrorRef` / `Acquisition` are defined once in Task 4 and referenced unchanged after. `Candidate` and `MatchRecord` come from Task 7; `Candidate.rung` is mutated in place by Task 9's sibling rung (documented there). `FetchedBytes` is Task 3's and is consumed by Task 8's `looks_like_pdf`. Bucket constants must equal their report key names — Task 11 requires a test asserting that, because `report[outcome.bucket]` depends on it.

**One dependency added mid-plan:** Task 9 needs `HttpClient.get_text`, which does not exist. Step 4 of that task adds it with its own tests. Flagging it because it edits a module the rest of the plan only reads.

---

Plan complete and saved to `docs/superpowers/plans/2026-08-27-literature-asset-acquisition.md`.
