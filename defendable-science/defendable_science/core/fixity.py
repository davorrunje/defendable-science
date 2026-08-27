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
