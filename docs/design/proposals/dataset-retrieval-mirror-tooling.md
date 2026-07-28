# Proposal: Dataset retrieval, private-mirror & fixity tooling

`Status: implemented (designed 2026-07-18) · Skill: dataset`

## Context

The `dataset` skill defines a resolution chain (local cache → private mirror →
public source → gated instructions) with SHA-256 fixity at every hop, but the
`fetch`/`verify`/`mirror`/`audit` verbs currently have no executable backing —
`../../../skills/dataset/SKILL.md` (§Retrieval & mirror, § *Tooling*) documents the
pooch fetcher and rclone wrappers as not-yet-implemented. **Interim (until the module is
implemented):** the skill orchestrates the resolution chain manually / via direct
tool calls — fetch, `sha256sum` fixity checks, and hand-run `rclone` — which is
error-prone; once `defendable-science` is installed (via
[`ensure-tooling`](../../../resources/ensure-tooling.md)) the skill calls
`defendable-science dataset …` instead. This proposal specifies that tooling.

The substrate that this tooling implements is already fixed by
`../../../resources/substrate/asset-registry.md`: a git-committed, license-bearing,
persistently-identified registry; a backend-agnostic rclone mirror; and a
**two-layer fixity** model where SHA-256 in the manifest is authoritative and the
rclone-native per-backend hash is only a transport check. The tooling review in
`../../../resources/references/dataset-tooling-mirror.md` settles the stack: reject
DVC/DataLad/lakeFS/Quilt on dependency weight; adopt **pooch** (Tier-B fetch) +
**rclone** (mirror engine, binary subprocess) over a thin resolution-chain core.

## Goal

Provide the ~200-line core the `dataset` verbs call, so the resolution chain runs
end-to-end with fixity enforced at every hop and the private mirror populated on
first acquisition — while keeping the plugin's dependency contract to **pooch +
pyyaml** (Python) plus **rclone** (a Go binary invoked as a subprocess, never a
Python dependency), and keeping all credentials out of the repo.

## Design sketch

Three front-end fetchers (one per tier) behind a shared substrate core that owns
cache, mirror, and fixity. The manifest SHA-256 is threaded through every layer.

**Tier-A checkout (git / LFS).** For small, redistributable, in-repo assets:
resolve the committed path, `git lfs pull` if pointer-backed, re-hash against the
manifest. No network fetcher; the mirror is redundant for Tier A.

**Tier-B fetcher (pooch).** `pooch.retrieve(url, known_hash="sha256:<hex>", …)`
into the content-addressed cache, covering `http`/`https`/`ftp`/`sftp` and `doi:`
(Zenodo/Figshare) locators from the entry's `retrieval` recipe. pooch verifies
its own `known_hash`, but the core **re-hashes the landed bytes against the
manifest** regardless (single source of truth). `huggingface_hub` is an
opportunistic add for HF-hosted/gated entries, not a base dependency.

**Tier-C instruct-drop-verify.** No fetch. Print the entry's acquisition
`instructions`, wait for an operator to drop bytes into the expected location,
verify SHA-256, then populate the mirror (only if the DUA permits a private copy).

**rclone subprocess wrappers.** Thin functions over `rclone --config <conf>` (or
env-var remotes), all keyed by content address `mirror:<base_path>/sha256/<hash>`:
- `mirror_put(local, sha256)` → `rclone copyto <local> mirror:base/sha256/<hash>`
- `mirror_get(sha256, dst)` → `rclone copyto mirror:base/sha256/<hash> <dst>`, then re-hash
- `mirror_check(sha256)` → `rclone check` / `rclone hashsum` as a transport-level
  presence/integrity probe; `--download` when backend hash sets are disjoint
Config resolution: prefer `RCLONE_CONFIG=$PWD/.defendable-science/rclone.conf` (untracked),
fall back to env-var remotes (`RCLONE_CONFIG_<NAME>_TYPE=…`) for CI from secrets.

**Fixity — two layers, SHA-256 authoritative.** rclone's native hash (often MD5)
is used only to short-circuit obviously-corrupt transfers; the local bytes are
**always re-hashed against the manifest SHA-256** after any transfer, so
verification is backend-independent. A file failing verification is treated as
**absent** and the chain continues; exhausting the chain is a hard fail.

**Populate-on-first-acquisition.** Whenever step 3 (public source) or step 4
(gated drop) yields verified bytes, the core calls `mirror_put` before returning,
turning the mirror into link-rot insurance (Tier B) and the re-acquirable home for
gated assets (Tier C). Mirror presence never changes tier or `redistributable`.

**Content-addressed cache.** Blobs land under `sha256/<hash>` (dedup, integrity ==
identity); a name-addressed symlink/copy is exposed for use. The cache directory
is gitignored.

## API / CLI the verbs call

A single module, `defendable_science/dataset/retrieval.py` (sharing the package's
`core` cache/http/provenance helpers), exposing the seams the verbs invoke:

```
resolve(entry, *, cache_dir, mirror_cfg) -> Path        # full chain, verified
verify(entry, *, cache_dir) -> VerifyReport             # re-hash on-disk vs manifest; never fetches
mirror_put(local, sha256, mirror_cfg) -> None           # populate content-addressed key
mirror_get(sha256, dst, mirror_cfg) -> bool             # step-2 pull + re-hash
mirror_check(sha256, mirror_cfg) -> PresenceReport      # transport-level probe (audit)
sha256_file(path) -> str                                # the one authoritative hash fn
```

Verb → core mapping:
- `fetch`  → `resolve` (= chain steps 1–4 + verify + `mirror_put` on acquisition)
- `verify` → `verify` (steps-1 fixity only, offline)
- `mirror` → `mirror_put` across an entry's files (populate/refresh)
- `audit`  → `verify` + `mirror_check` across every manifest entry, plus
  schema/license/datasheet/tier-consistency completeness (owned by the manifest
  loader/validator)

CLI shape mirrors the verbs: `defendable-science dataset fetch <id>`,
`defendable-science dataset verify [<id>|--all]`, `defendable-science dataset mirror <id>`,
`defendable-science dataset audit`. All read the mirror remote name + base
path from `datasets.yml`; none embed credentials.

## Dependencies & posture

- **pooch** — Tier-B fetcher; 3 pure-Python deps. Base plugin dependency.
- **pyyaml** — manifest load/validate (shared with the loader/validator TODO).
- **rclone** — mirror engine; a single static Go binary invoked as a
  **subprocess**, explicitly **not** a Python dependency (no PyPI coupling, no
  Rust/binary conflicts). Absence is a clear, actionable error, not an import
  failure.
- Heavy loaders (`datasets`, pandas, pyarrow) stay in the consumer project.
- Rejected: DVC/DataLad/lakeFS/Quilt (dependency weight / server posture) per the
  tooling-review digest.

**Secret hygiene (non-negotiable).** Never commit `rclone.conf`, tokens, or
`rclone obscure` output (`obscure` is not encryption). `init` ships only
`.defendable-science/rclone.conf.example` (remote name + type). The cache and real config are
gitignored; CI uses env-var remotes sourced from secrets.

## Open questions

- Do we vendor a minimal http/`doi:` fetcher as a fallback for environments that
  cannot install pooch, or hard-require pooch for Tier B?
- How is rclone discovered/version-pinned — `PATH` probe with a min-version check,
  or a documented install step in `init`?
- Should `mirror_check` default to `--download` (correctness) or hash-set compare
  (speed) when backend hashes are non-SHA-256, given the size of some mirrors?
- Cache eviction/GC policy for the content-addressed store — out of scope here or
  a `dataset` sub-verb later?
- Concurrency: is a lock needed around `mirror_put` / cache writes for parallel
  runs sharing one cache?

## Acceptance criteria

- `fetch` materializes a Tier-A, Tier-B (http + `doi:`), and Tier-C entry through
  the full chain, re-hashing against the manifest at every hop.
- A SHA-256 mismatch at any hop is treated as absent (chain continues) and an
  exhausted chain hard-fails; no unverified bytes are ever returned.
- On first successful step-3/step-4 acquisition the mirror is populated under the
  `sha256/<hash>` key and a subsequent `fetch` (cache cleared) resolves from the
  mirror at step 2.
- `verify` recomputes on-disk SHA-256 offline and never touches the network.
- `audit` reports fixity + mirror presence + license/datasheet/tier-consistency
  completeness across the whole manifest.
- rclone config resolves from either an untracked `rclone.conf` or env-var
  remotes; no test or fixture commits credentials; only `rclone.conf.example` is
  tracked.
- Plugin imports without pooch/rclone succeeding only degrades the affected verbs
  with a clear error — no hard import-time dependency on rclone.

## Links

- `../../../skills/dataset/SKILL.md` — the skill (§ *Retrieval & mirror*, § *Tooling*) this implements
- `../../../resources/substrate/asset-registry.md` — resolution chain + two-layer fixity
- `../../../resources/references/dataset-tooling-mirror.md` — tooling review / stack decision
- `../03-dataset.md`, `../04-substrate-and-contract.md`
- ADRs `../../../decisions/0010-storage-tiers.md`, `../../../decisions/0011-rclone-mirror-sha256.md`, `../../../decisions/0012-shared-substrate.md`
