"""Dataset retrieval, private-mirror & fixity tooling (defendable-science#3).

Runs the substrate resolution chain — local cache → private mirror → public
source → gated instructions — with SHA-256 enforced at every hop, and populates
the private mirror on first acquisition. The manifest SHA-256 is authoritative;
a file that fails verification is treated as **absent** and the chain continues.

Dependency contract: ``pooch`` (Tier-B fetch) + ``pyyaml`` (Python) plus
``rclone`` (a Go binary invoked as a subprocess, never a Python dependency). Both
``pooch`` and the rclone ``run`` callable are injectable, so the chain is tested
without the network or the binary. Design:
``docs/design/proposals/dataset-retrieval-mirror-tooling.md``.

.. note::
   The pooch/rclone command shapes follow their public docs and are covered by
   mocked tests; the opt-in live suite (``tests/test_live_retrieval.py``,
   ``-m live``) exercises them against real ``pooch`` + ``rclone`` (defendable-science#30).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from defendable_science.core.fixity import RetrievalError as RetrievalError
from defendable_science.core.fixity import bare_sha256 as bare_sha256
from defendable_science.core.fixity import blob_path as blob_path
from defendable_science.core.fixity import sha256_file as sha256_file
from defendable_science.core.fixity import verified as verified
from defendable_science.core.mirror import (
    Mirror as Mirror,  # noqa: TC001 - runtime re-export, callers reach `r.Mirror`
)
from defendable_science.dataset import manifest as manifest_mod

if TYPE_CHECKING:
    from defendable_science.dataset.manifest import DatasetEntry, FileRef, Manifest

#: A fetcher: ``(url, sha256, dest) -> path``; the default uses ``pooch``.
TierBFetcher = Callable[[str, str, Path], Path]


# --- fetch chain & fixity ---------------------------------------------------


def _pooch_fetch(url: str, sha256: str, dest: Path) -> Path:  # pragma: no cover
    """Default Tier-B fetcher: ``pooch.retrieve`` into `dest`.

    Exercised only against the live network; the resolution-chain tests inject a
    fake fetcher, so this real path is excluded from coverage.
    """
    import pooch  # imported lazily so the module loads without pooch

    dest.parent.mkdir(parents=True, exist_ok=True)
    got = pooch.retrieve(
        url=url,
        known_hash=f"sha256:{bare_sha256(sha256)}",
        fname=dest.name,
        path=dest.parent,
    )
    return Path(got)


def _resolve_file(
    entry: DatasetEntry,
    ref: FileRef,
    *,
    cache_dir: Path,
    mirror: Mirror | None,
    tier_b_fetch: TierBFetcher,
) -> Path:
    """Resolve one file through the chain, verifying at every hop.

    :raises RetrievalError: If the chain is exhausted without verified bytes.
    """
    # Tier A: the file is committed in-repo at its path; verify in place.
    if entry.tier == "A":
        repo_path = Path(ref.path)
        if verified(repo_path, ref.sha256):
            return repo_path
        raise RetrievalError(f"{entry.id}: Tier-A file {ref.path} missing or corrupt")

    blob = blob_path(cache_dir, ref.sha256)

    # 1. local cache
    if verified(blob, ref.sha256):
        return blob

    # 2. private mirror
    if (
        mirror is not None
        and mirror.get(ref.sha256, blob)
        and verified(blob, ref.sha256)
    ):
        return blob

    # 3. public source (Tier B)
    if entry.tier == "B":
        url = (entry.retrieval.url if entry.retrieval else None) or entry.source
        if not url:
            raise RetrievalError(f"{entry.id}: Tier-B entry has no source URL")
        landed = tier_b_fetch(url, ref.sha256, blob)
        if verified(landed, ref.sha256):
            if mirror is not None:
                mirror.put(landed, ref.sha256)
            return landed
        raise RetrievalError(f"{entry.id}: fetched {ref.path} failed SHA-256")

    # 4. gated / manual (Tier C): never fetches
    raise RetrievalError(
        f"{entry.id}: gated (Tier C) — acquire manually then re-verify:\n"
        f"{entry.instructions or '(no instructions recorded)'}"
    )


def fetch(
    entry: DatasetEntry,
    *,
    cache_dir: str | Path,
    mirror: Mirror | None = None,
    tier_b_fetch: TierBFetcher = _pooch_fetch,
) -> list[Path]:
    """Materialize every file of `entry` through the resolution chain.

    :param entry: The dataset entry to fetch.
    :param cache_dir: The content-addressed cache directory.
    :param mirror: Optional private mirror (populated on first acquisition).
    :param tier_b_fetch: The Tier-B fetcher (injectable; defaults to pooch).
    :returns: The verified on-disk paths, one per file.
    :raises RetrievalError: If any file cannot be resolved and verified.
    """
    cache = Path(cache_dir)
    return [
        _resolve_file(
            entry, ref, cache_dir=cache, mirror=mirror, tier_b_fetch=tier_b_fetch
        )
        for ref in entry.files
    ]


@dataclass
class VerifyReport:
    """The outcome of :func:`verify` for one entry.

    :param entry_id: The dataset id.
    :param verified: Files whose on-disk bytes matched the manifest.
    :param missing: Files absent from the cache/repo.
    :param corrupt: Files present but with a mismatched checksum.
    """

    entry_id: str
    verified: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    corrupt: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return whether every file verified."""
        return not self.missing and not self.corrupt


def verify(entry: DatasetEntry, *, cache_dir: str | Path) -> VerifyReport:
    """Re-hash an entry's on-disk files against the manifest, offline.

    Never downloads. Tier-A files are checked at their repo path; Tier-B/C files
    at their content-addressed cache path.

    :param entry: The dataset entry to verify.
    :param cache_dir: The content-addressed cache directory.
    :returns: A per-file verification report. A present-but-unreadable file
        (``OSError`` while hashing) is folded into ``corrupt`` rather than
        crashing the offline report.
    """
    cache = Path(cache_dir)
    report = VerifyReport(entry_id=entry.id)
    for ref in entry.files:
        path = Path(ref.path) if entry.tier == "A" else blob_path(cache, ref.sha256)
        if not path.is_file():
            report.missing.append(ref.path)
            continue
        try:
            digest = sha256_file(path)
        except OSError:
            report.corrupt.append(ref.path)
            continue
        if digest == bare_sha256(ref.sha256):
            report.verified.append(ref.path)
        else:
            report.corrupt.append(ref.path)
    return report


@dataclass
class AuditReport:
    """A whole-manifest audit.

    :param validation: The manifest schema/tier validation report.
    :param fixity: Per-entry verification reports.
    :param mirror_present: Per-entry mirror-presence flags (if a mirror is given).
    """

    validation: manifest_mod.ValidationReport
    fixity: list[VerifyReport] = field(default_factory=list)
    mirror_present: dict[str, bool] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Return whether validation and every fixity check pass."""
        return self.validation.ok and all(report.ok for report in self.fixity)


def audit(
    manifest: Manifest, *, cache_dir: str | Path, mirror: Mirror | None = None
) -> AuditReport:
    """Audit fixity + mirror presence + manifest completeness across a manifest.

    Folds in the manifest loader/validator (schema, license, datasheet,
    tier-consistency) alongside the byte-level fixity and mirror-presence checks.

    :param manifest: The parsed manifest.
    :param cache_dir: The content-addressed cache directory.
    :param mirror: Optional mirror to probe for presence.
    :returns: The combined audit report.
    """
    report = AuditReport(validation=manifest_mod.validate(manifest))
    for entry in manifest.datasets:
        report.fixity.append(verify(entry, cache_dir=cache_dir))
        if mirror is not None:
            report.mirror_present[entry.id] = all(
                mirror.check(ref.sha256) for ref in entry.files
            )
    return report
