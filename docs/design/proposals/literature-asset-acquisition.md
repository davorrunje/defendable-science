# Proposal: Literature asset acquisition (`fetch` / `confirm` / `verify` / `mirror`)

`Status: implemented (designed 2026-08-27) · Skill: literature`

## Context

`skills/digest/SKILL.md` step 1 requires that a paper be grounded in "a real
registry entry + mirrored PDF (cache → mirror → source chain, SHA-256), never a
bare URL or an unmirrored link." Before this work, the `literature` CLI group
exposed only the citation-graph primitives (`resolve | cites | refs | enrich |
neighbors`) — no `fetch`, no `verify`, no `mirror`, no `confirm`, and nothing in
`defendable_science/` read or wrote `references.json` or `triage.yml` at all.
`digest`'s only documented path could not be walked with shipped tooling, and
`skills/literature/SKILL.md` §Tooling overclaimed a CSL-JSON loader/appender and
a triage-join that did not exist.

This is also #97 (Gap 1)'s ask — acquire a PDF for a registry entry the way
`dataset fetch` acquires a data blob — reframed by two findings from probing the
concrete cases the issue raised: the acquisition gap OpenAlex leaves is
recoverable generically (no venue-specific scraping needed), and the naive fix
(a loose title search) reintroduces a worse bug (a wrong PDF bound to the wrong
citekey) than the one it fixes. See ADR-0037 and the full design spec
(`docs/superpowers/specs/2026-08-27-literature-asset-acquisition-design.md`) for
the complete reasoning and the two motivating cases (Sill 1997 vs. Igel 2023;
the MonoKAN preprint/journal pair) that shaped the gate.

## Goal

Provide the literature registry layer (CSL-JSON `custom` spine + `triage.yml`
reader) and the acquisition mechanism the four verbs call, so `fetch` can
acquire a PDF end-to-end — through a generic, non-venue-specific ladder, gated
against the registry entry to refuse rather than guess at a mismatch — record
byte-level provenance in a schema-valid `references.json`, and never place PDF
bytes in the consumer's repository. Bring `verify`/`mirror` to parity with
`dataset`'s equivalents, and close `digest` step 1 with real, callable
commands.

## Design sketch

### Registry layer

`literature/registry.py` reads `references.json` (CSL-JSON) and `triage.yml`
(YAML sidecar), and writes back **surgically**:

- `registry.patch_asset(citekey, asset)` locates the entry by `id` (falling
  back to DOI), replaces only `custom["defendable-science"]`, and rewrites via
  temp-file-and-rename with `indent=2`, `ensure_ascii=False`. Unknown top-level
  keys, unknown `custom` sub-keys, and key order all survive unchanged.
- Triage writes are restricted to adding/replacing scalar keys on an existing
  row; a commented `triage.yml` is refused with an explicit reason rather than
  silently stripped, because `pyyaml` cannot round-trip comments.

The spine lives under `custom.defendable-science` (ADR-0037), not as top-level
CSL properties, because the CSL input schema forbids additional top-level
properties on an item.

### Fixity model — where `literature` differs from `dataset`

`dataset.retrieval.fetch` treats the manifest SHA-256 as authoritative and
already known. A literature entry usually has none on first acquisition:

- **Resolution before acquisition.** An entry that already records a `sha256`
  is a pure substrate resolution (cache → mirror); the acquisition ladder does
  not run.
- **Trust on first use, gated.** With no recorded hash, the ladder runs and the
  match gate substitutes for the absent trust anchor; the hash is computed
  from the accepted bytes and written back.
- **Drift refuses**, never silently rebinds a citekey to different bytes.
- Once a hash exists, `verify` is exactly `dataset verify`'s contract: offline,
  re-hash, report `verified / missing / corrupt`.

(`docs/design/04-substrate-and-contract.md` §2.4 records this as the second
variant of the shared resolution chain's step 3.)

### The acquisition ladder

Rungs 1–3 are identity-derived from the OpenAlex work the citekey already
resolves to (`best_oa_location`, every `locations[].pdf_url`, then every
`locations[].landing_page_url` that serves PDF bytes — checked by magic bytes,
because `Content-Type` lies). No gate needed; the URL already belongs to the
anchor's own record. A `.pdf` suffix orders the landing rung but does not gate
it: suffix-less landing pages follow, capped at `LANDING_SNIFF_LIMIT`, because a
publisher serving a PDF from an extension-less path is a real shape and dropping
it unseen cost recall (#104).

Rungs 4–5 are search-derived and every candidate passes the gate: a
sibling-version title search (word-prefix or equal, same relation the gate
itself uses — a rung's pre-filter must never be stricter than the gate) and an
arXiv title+author query. Rung 6 is the config-driven `venue_resolvers` list,
which ships **empty** — the generic rungs already recover the concrete cases
that motivated the feature, so no ML-venue logic enters the plugin. It is
*trusted*, not gated: its candidate URL comes from a consumer's template and
there is nothing in OpenAlex to match it against, so the record says `trusted`
rather than claiming an `accept` it did not earn (ADR-0038). Rung 7 is manual:
report the landing URLs, adopt by hand via `confirm --file`.

### The match gate

Three axes — title (normalized), first-author family name, year — combine
into `accept` / `quarantine` / `refuse`. Two verdicts sit outside the gate
because no comparison was made: `identity` (rungs 1–3, the URL is the anchor's
own) and `trusted` (rung 6, the operator vouched — ADR-0038). First-author family name is a hard
gate: no candidate is ever accepted or quarantined across a mismatch. Title
agreement is normalized-equality or **word-prefix containment** (not
substring — substring isn't word-aware). Quarantine lands bytes plus the
candidate record under `<cache>/quarantine/<citekey>/<sha256>.{pdf,json}`
without touching `references.json`; promotion requires an explicit human
`confirm --sha256`.

### License-gated destination

`fetch` never writes PDF bytes into the consumer's repository — not
automatically, not behind a flag. `files[].path` is always a content-addressed
blob path; there is no Tier-A/Tier-B path dichotomy on the literature side.
`license` records what a rung *observed* — `{id, observed, source}` — and
`redistributable` defaults to `false`, true only for an SPDX id on a shipped
permissive allowlist. Absent or unparsable → non-redistributable. The
three-way (`committable[]` / ordinary fetched-or-cached / `manual[]`) appears
in `fetch --all`'s report; a human decides whether to copy a committable PDF
in-repo themselves.

## API / CLI the verbs call

```
literature fetch   [CITEKEY] [--all] [--disposition VALUE] [--refetch] [--dry-run]
literature confirm CITEKEY (--sha256 SHA | --file PATH)
literature verify  [CITEKEY] [--all]
literature mirror  [CITEKEY] [--all] [--check]
```

For `fetch`/`verify`/`mirror`: exactly one of `CITEKEY` or `--all` — neither is
"nothing to do," both together is an error. For `confirm`: exactly one of
`--sha256` (promote a quarantined candidate, moving the blob out of
quarantine) or `--file` (adopt a manually downloaded PDF, **copying** it —
the human's file must not disappear because they pointed a tool at it — and
recording `rung: manual` with an empty, non-redistributable license, since the
tool observed nothing about a file it didn't fetch).

`--disposition` filters `--all` by the `triage.yml` `disposition` field.
Naming a citekey explicitly *and* passing `--disposition` is a conflict,
reported as an `errors[]` row, never a silent omission.

Every command emits JSON on stdout. `fetch --all`'s report carries
`complete`, `not_attempted`, and `fetched` / `cached` / `quarantined` /
`manual` / `committable` / `errors` buckets, each row carrying the full
outcome shape uniformly (a `fetched` row can still carry a `reason` if the
mirror write failed after the bytes landed) rather than a narrower
per-bucket projection — a partial failure must never become invisible.

Verb → mechanism:
- `fetch`   → resolution-before-acquisition, then the ladder + gate; `mirror_put`
              on first acquisition.
- `verify`  → offline re-hash against the registry's recorded checksum(s).
- `mirror`  → push recorded file(s) to the configured mirror, or `--check`
              probe presence without pushing.
- `confirm` → promote a quarantined candidate, or adopt a manual download.

## Dependencies & posture

- No new base dependency: the ladder's metadata calls reuse the existing
  `HttpClient` (polite pool, rate limiting); byte downloads use a new
  injectable streaming fetcher in `core/http.py` with a content-type check and
  a hard size cap (`literature.acquisition.max_bytes`, default 50 MiB),
  bypassing the JSON cache because the content-addressed blob store *is* the
  cache for bytes.
- `sha256_file` / `blob_path` / `RetrievalError` live in `core/fixity.py` and
  `Mirror` in `core/mirror.py`, promoted out of `dataset/retrieval.py` because
  ADR-0037 rejected a full `substrate/` extraction with a unified
  `materialize()` as a false abstraction over the known-hash-vs-TOFU split —
  only the genuinely shared primitives moved; the two resolution chains stay
  separate. `dataset/retrieval.py` re-imports them; its own behaviour is
  unchanged.
- `pyyaml` for the triage sidecar (already a dependency).

## Testing

Hermetic, 100% statement + branch coverage (ADR-0028), injecting the
bytes-fetcher, the `HttpClient` transport, and the rclone `run`. Fixtures are
trimmed real API payloads (OpenAlex records for Sill 1997, the MonoKAN
journal and arXiv works, the Igel 2023 arXiv record, `papers.nips.cc`
response headers). Named regressions include: the Sill/Igel refusal (verdict
`refuse`, author axis fails, `references.json` byte-identical, entry lands in
`manual[]` not `quarantined[]`); the MonoKAN acceptance (sibling rung →
`accept` at Δyear = 1 — the test that stops someone "fixing" the gate by
tightening the year to exact); the lying-`Content-Type` case (accepted on
magic bytes); thin-metadata degradation (rungs 1–3 still work, 4–6 refuse with
an explicit insufficient-metadata reason); drift refusal; and write safety
(unknown CSL/`custom` keys survive a patch; a commented `triage.yml` is
refused, not stripped).

## Acceptance criteria

- `literature fetch` acquires a PDF via the ladder for at least one
  identity-derived and one search-derived rung, recording `files[]` + `sha256`
  + `license` under `custom.defendable-science` in valid CSL-JSON.
- The Sill-1997-vs-Igel-2023 case refuses; the MonoKAN sibling case accepts.
  Both are named regression tests (#97's acceptance criterion).
- `fetch` never writes PDF bytes into the consumer's repository, under any
  flag combination.
- `literature verify` is offline and never touches the network.
- `literature mirror` pushes recorded files to the configured mirror and
  `--check` probes presence without pushing.
- `literature confirm` promotes quarantine (`--sha256`, move) and adopts a
  manual download (`--file`, copy), in both cases patching the registry
  surgically.
- `digest`'s step 1 precondition is satisfiable end-to-end with these four
  verbs and no other tooling.
- `dataset`'s existing suite passes unchanged after the `core/fixity.py` /
  `core/mirror.py` promotion.

## Links

- `../../../skills/literature/SKILL.md` — the skill (§Tooling, §Registry) this implements
- `../../../skills/digest/SKILL.md` — step 1, the precondition this closes
- `../02-literature.md` §4–§5, `../04-substrate-and-contract.md` §2.4
- `docs/superpowers/specs/2026-08-27-literature-asset-acquisition-design.md` — the full design
- ADR-0008, ADR-0011, ADR-0012, ADR-0020, ADR-0037
- `dataset-retrieval-mirror-tooling.md` — the sibling proposal this mirrors and
  partially shares substrate with
