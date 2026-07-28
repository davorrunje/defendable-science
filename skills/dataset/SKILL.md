---
name: dataset
description: >-
  Manage research datasets with a thin, git-tracked registry, tiered storage, a
  private rclone mirror, and SHA-256 fixity. Use when a run declares the data it
  needs, when adding/registering a dataset, or when fetching, verifying,
  mirroring, or auditing datasets so results resolve to exact bytes. Verbs:
  init, register, export, fetch, verify, mirror, audit.
---

# dataset

One skill for the whole dataset lifecycle. It keeps a thin, git-tracked registry
(`datasets.yml`), classifies each dataset into a storage tier, fetches and
verifies bytes through a resolution chain, and mirrors durable copies to a
private rclone remote. It is **upstream of the experiment backend**: runs declare
the datasets they need, this skill materializes and verifies them, and the
`id + version + sha256` fingerprint flows into the backend's provenance stamp so
every reported result resolves to exact bytes.

Grounding: `../../docs/design/03-dataset.md`,
`../../docs/design/04-substrate-and-contract.md` (§2 substrate),
`../../resources/references/dataset-management-standards.md`,
`../../resources/references/dataset-tooling-mirror.md`, and ADRs
`../../decisions/0009-dataset-thin-manifest.md`,
`../../decisions/0010-storage-tiers.md`,
`../../decisions/0011-rclone-mirror-sha256.md`,
`../../decisions/0012-shared-substrate.md`.

**Agency:** this skill fetches, verifies, and reports. It never decides which
dataset is *appropriate* for a claim — that is a scientific judgement the
researcher owns (and a `defend` methodology probe may ask them to defend). Tier is
*proposed* here but *confirmed by the human* on register.

**Dependencies:** `pyyaml` + `pooch` (Python) and `rclone` (a Go binary invoked
as a subprocess, not a Python dep). Heavy loaders (`datasets`, pandas) stay in the
consumer project, never in this skill.

## When to use

- A run/experiment declares a dataset dependency and needs it materialized + verified before it counts.
- Adding a dataset to the project (`register`), or bootstrapping the registry the first time (`init`).
- Pulling bytes for local work (`fetch`), or confirming on-disk bytes still match the manifest (`verify`).
- Refreshing the private durability copy (`mirror`), or a whole-manifest health check before release/submission (`audit`).
- Emitting a Croissant file for a venue (e.g. NeurIPS D&B) or ingesting one to bootstrap an entry.

Do **not** use it to choose a dataset for a hypothesis, judge whether data support a
conclusion, or promote a tier because a mirror exists — those are out of scope.

## Verbs

| Verb | Action |
|---|---|
| `init` | Scaffold `datasets.yml`, `.defendable-science/rclone.conf.example` (remote name + type only), and a gitignored cache dir. |
| `register` | Add an entry (ingest a published Croissant if present); *propose* a tier; write/link a datasheet; **the human confirms tier + license**. |
| `fetch` | Materialize via the resolution chain (cache → mirror → source → gated). Hard-fail on any SHA-256 mismatch. |
| `verify` | Recompute SHA-256 of on-disk files vs. the manifest; report `verified-against-registry`. Never downloads. |
| `mirror` | Populate/refresh the private rclone mirror under content-addressed keys (`sha256/<hash>`); re-hash after transfer. |
| `audit` | Fixity + presence + license/datasheet completeness **+ tier↔(access, redistributable) consistency** across the entire manifest; report gaps. |
| `export` | Emit a Croissant JSON-LD file for a venue (e.g. NeurIPS D&B) from a registry entry; the registry stays the source of truth (CLI: `dataset emit`). |

Composed: `fetch` = resolve + verify + mirror-populate; `audit` = `verify` across
every entry plus schema/license/datasheet/tier completeness. **Croissant ingest**
rides inside `register` (bootstrap an entry from a published Croissant); **emit** is
the standalone `export` verb.

## Manifest

Registry is a single thin, repo-owned, **public** YAML file: `datasets.yml`. Field
names map onto **schema.org / Croissant** + **DataCite** so an entry can *ingest*
and *emit* a Croissant file. It is *not* DVC machinery (dependency mass fails the
light posture). Each entry extends the shared substrate base asset record.

Required **core** fields (every tier): `id`, `version`, `tier`, `license` (SPDX
id or explicit terms + URL), `redistributable` (bool), `access` (`open`|`gated`),
`files[]` (each `path` + `sha256`), `datasheet` (path/URL; **required** — a
`"N/A + reason"` placeholder is permitted only as an explicit, `audit`-flagged
deficiency, never a clean state).
Additionally: `source`/`retrieval` required for **Tier B**; acquisition
`instructions` required for **Tier C**; `sensitivity` required if PII/confidential.

```yaml
# datasets.yml (committed, public — no secrets, no blobs above Tier A)
mirror:
  rclone_remote: <logical-name>       # name only; credentials live outside the repo
  base_path: "<project>/datasets"
  hash: md5                           # rclone transport check only; NOT authoritative

datasets:
  - id: example-tabular               # stable slug, unique in registry
    version: "1.0.0"
    tier: B                           # A | B | C  — human-confirmed
    license: CC-BY-4.0                # SPDX id or explicit terms + URL
    redistributable: true
    access: open                      # open | gated
    pid: doi:10.xxxx/xxxxx            # optional but preferred
    files:
      - path: data/example.parquet
        sha256: <64-hex>              # AUTHORITATIVE fixity, single source of truth
        size: 12345678
    source: https://example.org/example.parquet
    retrieval:                        # required for Tier B
      kind: http                      # http | doi | openml | git-lfs | manual
      url: https://example.org/example.parquet
    datasheet: datasheets/example.md  # Gebru datasheet; required
    citation: { creator: ..., title: ..., publisher: ..., publicationYear: ..., resourceType: Dataset }
    sensitivity: none                 # required if PII/confidential
```

**Tooling.** This is `defendable_science/dataset/manifest.py`, exposed via
`defendable-science dataset validate` (loader/validator) and `defendable-science dataset
ingest|emit` (Croissant) — ensure via [`ensure-tooling`](../../resources/ensure-tooling.md);
design in `../../docs/design/proposals/dataset-manifest-tooling.md`. By hand (if
the CLI isn't available):
- **loader/validator** — load with `python -c` + `yaml.safe_load` and eyeball the
  base record + tier-conditional required fields (self-describing `sha256:` values)
  against the table above.
- **Croissant ingest/emit** — hand-map registry fields ⇄ Croissant JSON-LD
  (`name`, `license`, `citeAs`, `version`, `distribution[].contentUrl/.sha256`) on
  register/export; keep the registry as the superset source of truth, Croissant as
  an export format.

## Tiers

Tier = f(**redistribution license × access automation**). Redistribution dominates
"can it be committed (Tier A)?". Proposed by the skill, **confirmed by the human**.

| Tier | Condition | Behavior |
|---|---|---|
| **A — committed** | small **and** license permits redistribution | committed via git/LFS; zero-setup reproducibility. Mirror redundant. |
| **B — auto-retrievable** | public + fetchable via stable URL/API, but large or non-redistributable | registry holds a `retrieval` recipe + sha256; materialized into the gitignored cache; **mirror = link-rot insurance** (populated on first fetch). |
| **C — manual/gated** | login / EULA / registration, or no stable source | metadata + datasheet + acquisition instructions + sha256; skill **verifies presence/integrity only, never fetches**; mirror only if the DUA permits a private copy. |

Every entry carries a **Gebru datasheet** (composition, collection, distribution,
maintenance). It is also a `defend` methodology target ("what are this dataset's
known biases / collection limits?").

## Retrieval & mirror

`fetch` runs the substrate **resolution chain**, verifying SHA-256 at every hop; a
file failing verification is treated as absent and the chain continues:

```
1  LOCAL CACHE     exists and sha256 == manifest → return; else discard-if-corrupt
2  PRIVATE MIRROR  (if configured) rclone copy mirror:base/sha256/<hash> → re-hash → return; else fall through
3  PUBLIC SOURCE   front-end fetcher — Tier A: git/LFS · Tier B: pooch (http/ftp/sftp/doi:)
                   → assert sha256 == manifest (HARD FAIL) → populate mirror → return
4  GATED / MANUAL  print acquisition instructions → wait for operator drop → verify → populate mirror → return
```

- **SHA-256 in the manifest is authoritative** (integrity == identity ==
  citation-verifiability). rclone's native per-backend hash (often MD5 on Drive/S3)
  is only a *transport* check; local bytes are always **re-hashed against the
  manifest** after any transfer, so verification is backend-independent.
- Cache is **gitignored** and **content-addressed on the wire** (`sha256/<hash>`
  keys → dedup, integrity == identity), name-addressed for use (symlink/copy).
- The mirror is populated on first successful acquisition → link-rot insurance
  (Tier B) and a re-acquirable home for gated assets (Tier C).
- Credentials never enter the repo: gitignore `rclone.conf`, point via
  `RCLONE_CONFIG=$PWD/.defendable-science/rclone.conf`, commit only `rclone.conf.example`
  (remote name + type). CI uses env-var remotes from secrets. `rclone obscure` is
  **not** encryption — never commit it.

**Tooling.** The resolution chain is `defendable_science/dataset/retrieval.py`, exposed
via `defendable-science dataset fetch|verify|mirror|audit` — ensure via
[`ensure-tooling`](../../resources/ensure-tooling.md); design in
`../../docs/design/proposals/dataset-retrieval-mirror-tooling.md`. rclone
is an optional external binary the wrappers shell out to, not a Python dep.
By hand (if the CLI isn't available):
- **Tier-B fetch** — `curl`/`wget` then `sha256sum` and manually compare to the
  manifest before use (the module will use `pooch.retrieve(url, known_hash="sha256:…")`
  into the content-addressed cache).
- **rclone mirror** — run the commands by hand with `--config .defendable-science/rclone.conf`:
  `mirror` = `rclone copyto <local> mirror:base/sha256/<hash>`; resolution step 2 =
  `rclone copyto mirror:base/sha256/<hash> <cache>` then re-hash; `audit` may use
  `rclone check --download` when backend hash sets are disjoint.

## Composition

- **Feeds the experiment backend.** On each run, the backend's provenance stamp
  copies `id + version + sha256` for every declared dataset; `verify` must pass
  before a run's evidence counts. See `../../docs/design/04-substrate-and-contract.md` §3.
- **Shares the substrate mechanism** (base record, rclone mirror, fixity,
  persistent-ID/citation) with `literature`; they share the *mechanism*, not the
  *file* (ADR-0012). This skill owns the dataset extension (`tier`, `retrieval`,
  `datasheet`, `sensitivity`) and `datasets.yml`.
- **Interop seams.** Croissant emit/ingest (venue-mandated at NeurIPS D&B);
  DataCite `citation` + DOI make a dataset citable and DOI-archivable at
  Zenodo/Dryad/figshare — *iff* redistributable.
- **Datasheets** close the loop with the rigor kit's per-dataset datasheets and are
  a `defend` methodology target.

## Guardrails

- **A private mirror is storage, NOT a redistribution grant.** Tier and
  `redistributable` are set by the **license**, never by mirror presence. Refuse to
  promote to Tier A because a mirror exists; never surface mirror contents publicly.
  (ADR-0010; FAIR A1.2/A2: metadata stays open even when bytes are gated.)
- **Human confirms tier + license on register.** The skill proposes; the researcher
  decides. Tier/license is a judgement, not an automation.
- **Tier must stay consistent with its inputs.** `tier` is
  `f(redistributable × access)`; a human confirms it but is not free to contradict
  the license. `audit` flags any entry whose `tier` disagrees with its
  `(access, redistributable)` fields (e.g. `tier: A` + `access: gated`, or `tier: A`
  + `redistributable: false`).
- **SHA-256 mismatch is a hard fail** at every hop — never return or count
  unverified bytes. Never trust a backend-reported hash alone.
- **Tier C is verify-only** — print acquisition instructions and wait for an
  operator drop; never attempt to fetch gated/credentialed data automatically.
- **Secret hygiene** — never commit `rclone.conf`, tokens, or `rclone obscure`
  output; only `rclone.conf.example` (name + type) is tracked.
- **No blobs above Tier A in the repo** — Tier B/C bytes live in the gitignored
  cache and/or the private mirror, never committed.
- **Never decide dataset appropriateness for a claim** — out of scope (agency
  principle).

## Commit attribution

When you commit artifacts produced by this skill, add these git trailers —
discovery + provenance (see [`../../resources/commit-attribution.md`](../../resources/commit-attribution.md)):

```
Generated-with: defendable-science (https://github.com/davorrunje/defendable-science)
DefendableScience-Skill: dataset
```
