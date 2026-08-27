# Design — literature asset acquisition (`fetch` / `confirm` / `verify` / `mirror`)

**Date:** 2026-08-27
**Author:** Davor Runje
**Status:** Approved design; not yet implemented.
**Scope:** Gap 1 of [#97](https://github.com/davorrunje/defendable-science/issues/97), plus the
literature registry layer that Gap 2 will build on.

> Realizes the `literature` half of the asset-provenance substrate specified in
> [`04-substrate-and-contract.md`](../../design/04-substrate-and-contract.md) §2, and makes
> [`skills/digest/SKILL.md`](../../../skills/digest/SKILL.md) step 1 satisfiable with shipped
> tooling. Governed by the meta-spec's agency principle and the repo's failure-honesty rule.

## 1. Problem

`skills/digest/SKILL.md` step 1 requires that a paper be "grounded in a real registry entry +
mirrored PDF (cache → mirror → source chain, SHA-256), never a bare URL or an unmirrored link."
The `literature` CLI group exposes only `resolve | cites | refs | enrich | neighbors`. There is
no `fetch`, no `verify`, no `mirror`. **The only documented path into `digest` cannot be walked
with shipped tooling.**

Two further findings from reading the code and probing the live APIs reframe the work:

**1.1 The literature registry layer does not exist in code.** `skills/literature/SKILL.md`
§Tooling claims the CLI wraps "the OpenAlex + Semantic Scholar clients, the CSL-JSON bib
loader/appender, and the triage-join + PRISMA-log / concept-matrix generators." Only the first
exists. Nothing in `defendable_science/` reads or writes `references.json` or `triage.yml`. So
Gap 1 is not "add three verbs alongside `dataset`'s"; it is "build the literature registry layer
that every part of #97 writes back to." That layer is the shared prerequisite for Gap 2, and the
skill's claim is an overclaim to correct.

**1.2 The acquisition problem is not what #97 diagnoses, and the correct fix is cheaper.** #97
proposes venue-specific resolvers for `papers.nips.cc`, `proceedings.mlr.press`, and
`openreview.net`. That would put ML-venue logic into the plugin, breaching the
domain-neutrality rule. Probing the three concrete cases from the consumer run shows OpenAlex
already holds all three PDFs; `best_oa_location` simply does not surface them:

| case | why `best_oa_location` missed it | where the PDF actually is |
|---|---|---|
| **Sill 1997** `W2293093810` | `oa_status: closed`, `best_oa_location.pdf_url: null` | `locations[0].landing_page_url` = `https://papers.nips.cc/paper/1358-monotonic-networks.pdf` — verified `200 application/pdf`, 1 518 143 bytes |
| **MonoKAN** | the registry entry resolved to the *journal* work `W4416410340` (2025, `closed`, no PDF) | a **separate OpenAlex work**, `W4403706439` (2024, `green`), carries `pdf_url` — the arXiv version of the same paper |
| **Size and Depth of Monotone Neural Networks** | same sibling-version pattern | the arXiv work is `green` with a `pdf_url` |

The rungs that recover all three are therefore generic: read *all* `locations[]`, not just
`best_oa_location`; accept a `landing_page_url` that actually serves PDF bytes; and search for
sibling versions of the same work. No venue knowledge is required.

**1.3 The MonoKAN case and the wrong-PDF case pull in opposite directions.** The
sibling-version rung needs a **year window** (2024 preprint vs 2025 journal). That same slack is
what let an arXiv title search bind `arXiv:2306.01147` (Igel, *Smooth Min-Max Monotonic
Networks*, 2023) to Sill's *Monotonic Networks* (1997). A gate tight enough to reject Igel must
not reject the real MonoKAN preprint. §5 resolves this on the author axis.

## 2. Goals and non-goals

**Goals.**

1. `literature fetch` acquires a PDF through a generic ladder and records byte-level provenance.
2. Search-derived candidates are verified against the registry entry and **refused rather than
   guessed at** on mismatch.
3. `files[]` + `sha256` + `license` are recorded on the registry entry, in a form that keeps
   `references.json` valid CSL-JSON.
4. `literature verify` (offline) and `literature mirror` reach `dataset` parity.
5. The license rule (04 §2.5) drives a three-way *report*: committable / cache-only / manual.
6. A regression test built on the Sill-1997-vs-Igel-2023 case.
7. `digest` step 1 becomes satisfiable with shipped tooling.

**Non-goals.**

- `literature audit`. `dataset` has one and parity is tempting, but nothing in #97 needs it and
  `fetch --all`'s report answers the question it would answer. Filed as a follow-up.
- PDF text extraction. Verifying page-1 text against the registry title would need a PDF parser
  (`pypdf`), against the light-dependency posture. The gate operates on rung metadata; §5
  argues that is sufficient because rungs 1–3 are identity-derived and 4–6 are author-gated.
- The PRISMA-log and concept-matrix generators. Part of the §1.1 overclaim, but not needed here;
  filed as a follow-up and removed from the skill's claims until real.
- Gap 2 (`digest` extraction mode) and Gap 3 (survey templates). Separate spec → plan cycles.
- Writing PDF bytes into the consumer's repository. See §6.

## 3. Module layout

Approach chosen: **promote only what is genuinely shared.** `dataset/retrieval.py` currently owns
`Mirror`, `sha256_file`, and the content-addressed blob path, all of which 04 §2.1 designates
*substrate*. Move exactly those; leave the two resolution chains separate, because they are not
the same algorithm (§4).

```
core/fixity.py          NEW    sha256_file, blob_path(cache, sha256),  ← from dataset/retrieval.py
                               RetrievalError
core/mirror.py          NEW    Mirror (rclone)                         ← from dataset/retrieval.py
core/http.py            EDIT   + an injectable streaming bytes-fetcher
dataset/retrieval.py    EDIT   re-imports the promoted names; chain logic unchanged
literature/registry.py  NEW    CSL-JSON + triage.yml load / surgical patch / validate
literature/acquire.py   NEW    ladder, candidate model, match gate, quarantine
cli.py                  EDIT   literature: fetch | confirm | verify | mirror
```

Rejected: importing `Mirror` from `dataset` into `literature` (inverts the layering the substrate
spec draws, and Gap 2 would build on the inversion); extracting a full `substrate/` package with
a unified `materialize()` (would have to paper over the known-hash vs trust-on-first-use split of
§4, a false abstraction, and a large diff for Gap 1 to carry).

`core/http.py`'s `HttpClient` is JSON-only (`get_json`, backed by a JSON response cache), so
binary retrieval is new code: a streaming fetcher with a content-type check and a size cap,
bypassing the JSON cache because the content-addressed blob store *is* the cache for bytes. It
is injectable, following `TierBFetcher`'s precedent, so the ladder is tested without network.

```python
#: A bytes fetcher: (url, dest, max_bytes) -> FetchedBytes; default streams via requests.
BytesFetcher = Callable[[str, Path, int], FetchedBytes]

@dataclass
class FetchedBytes:
    path: Path
    media_type: str | None   # as reported by Content-Type
    size: int
```

## 4. Fixity model — the one place literature differs from dataset

`dataset.retrieval.fetch` treats the manifest SHA-256 as **authoritative**: bytes that do not
match are "absent," and the chain continues. A paper on first acquisition has no hash to match
against, so literature cannot reuse that contract. Instead:

- **Resolution before acquisition.** If the entry already records a `sha256`, `fetch` is a pure
  substrate resolution — cache → mirror — and stops. Acquisition rungs do not run.
- **Trust on first use, gated.** With no `sha256` recorded, the acquisition rungs run; the hash
  is *computed from the accepted bytes and written back*. The metadata gate of §5 substitutes
  for the absent trust anchor. This is why the gate is load-bearing rather than a nicety: it is
  the only thing standing where `dataset` has a pre-known hash.
- **Drift refuses.** `--refetch` on an entry that already has a `sha256`, yielding different
  bytes, **refuses and reports the drift**. It never silently rebinds a citekey to a new arXiv
  version; a paper's identity is what the recorded bytes say it is.
- Once a hash is recorded, `verify` is exactly `dataset verify`'s contract: offline, re-hash,
  report `verified / missing / corrupt`.

`04-substrate-and-contract.md` §2.4 is amended to record that step 3 of the resolution chain has
two variants — dataset verifies against a hash it already has, literature establishes one.

## 5. The acquisition ladder and the match gate

### 5.1 Ladder

Rungs 1–3 are **identity-derived**: the URLs come from the OpenAlex work the citekey already
resolves to, so no matching is needed. Rungs 4–6 are **search-derived** and every one passes
through the gate.

| # | rung | derived from | gated |
|---|---|---|---|
| 1 | `openalex-best` | `best_oa_location.pdf_url` | no |
| 2 | `openalex-locations` | every `locations[].pdf_url` | no |
| 3 | `openalex-landing` | every `locations[].landing_page_url` that serves PDF bytes | no |
| 4 | `sibling-version` | title search → same-normalized-title works ≠ anchor → their rungs 1–3 | **yes** |
| 5 | `arxiv-search` | arXiv API query by title + author | **yes** |
| 6 | `venue-resolver` | config `literature.acquisition.venue_resolvers` templates | **yes** |
| 7 | *manual* | nothing fetched; reported with the landing URLs to click | — |

Rungs are attempted in order; the first accepted candidate wins. `--dry-run` walks the ladder
and reports which rung *would* yield bytes without downloading them.

Rung 4's own same-title pre-filter narrows the search; it does **not** stand in for the gate.
Every candidate from rungs 4–6 is evaluated by §5.2 regardless of how it was found, so a rung
whose pre-filter is loose (rung 5's arXiv title query, which is how the Igel case arose) is
caught by the same check as one whose pre-filter is tight.

**Byte acceptance, applied at every rung:** HTTP 200, size ≤ `max_bytes`, and
`Content-Type: application/pdf` **or** a body beginning `%PDF-`. The magic-byte check is
authoritative, because content-type lies — and it is the entire mechanism of rung 3, which
distinguishes Sill 1997's PDF-serving `papers.nips.cc` landing URL from an ordinary HTML landing
page with no venue knowledge whatsoever.

**Rung 6 ships empty.** `venue_resolvers: []` by default. The generic rungs cover all three of
#97's concrete cases, so no ML-venue logic enters the plugin; a consumer repo needing an exotic
venue adds a `{match, url_template}` pair in its own config. This is how the issue's venue rung
gets a home without breaching domain-neutrality.

**Politeness.** Metadata calls (rungs 1–5) go through the existing `HttpClient`, inheriting the
`mailto=` polite pool and the proactive rate limiting. Byte downloads go through the new fetcher
with a per-host minimum interval.

### 5.2 The gate

Three axes, candidate-vs-registry-entry:

- **title** — normalized: casefolded, punctuation and runs of whitespace collapsed, a trailing
  subtitle after `:` optionally dropped.
- **first-author family name** — casefolded, diacritics folded.
- **year** — integer.

"Title containment match" means that, after normalization and tokenization into words, the
shorter title is a **word-prefix** of the longer one — the symmetric relation, since a candidate
may be either broader or narrower than the registry title.

*Amended 2026-08-27, during implementation.* This clause originally read "either string contains
the other as a substring", which was wrong twice over. It contradicted this section's own Sill/Igel
example below — `"monotonic networks"` **is** a trailing substring of
`"smooth min max monotonic networks"`, so that example could not simultaneously be "a containment
match" and "refuse on all three axes". And substring matching is not word-aware at all: `"GAN"`
would score a containment match against `"Improved Training of Wasserstein GANs"`, and `"Net"`
against `"Monotonic Networks"`. With author and year agreeing, those become **quarantine** — a
wrong PDF one human keystroke from a citekey, which is precisely the failure §1.3 exists to
prevent. Word-prefix is the minimal word-aware relation that still admits the subtitle case
(`"MonoKAN"` ↔ `"MonoKAN: Certified Monotonic Kolmogorov-Arnold Network"`, in both directions)
while rejecting Igel.

**The cost, stated:** a *front-extension* — where the candidate prepends words rather than
appending them, e.g. `"Language Models are Few-Shot Learners"` vs
`"GPT-3: Language Models are Few-Shot Learners"`, or an acronym added on journal publication —
now refuses where it would arguably have been quarantined. That is friction, not loss: the entry
lands in `fetch --all`'s `manual[]` worklist with its landing URLs, and `literature confirm
--file` adopts a hand-downloaded PDF. Refusing over guessing is this gate's stated posture.

| verdict | condition |
|---|---|
| `accept` | author exact **and** title normalized-equal **and** \|Δyear\| ≤ 1 |
| `quarantine` | author exact **and** title normalized-equal **and** \|Δyear\| ≤ 5 |
| `quarantine` | author exact **and** title containment match **and** \|Δyear\| ≤ 1 |
| `refuse` | anything else |

**The load-bearing invariant: first-author family name is a hard gate. No candidate is ever
accepted or quarantined across an author mismatch.** Checked against both real cases:

- **MonoKAN** — registry entry is the 2025 *Neural Networks* version; candidate is
  `W4403706439`, 2024. Same first author; "Certified Monotonic Kolmogorov-Arnold Network" and
  "Certified monotonic Kolmogorov-Arnold network" normalize to the same string; Δyear = 1 →
  **accept**. Recovered automatically.
- **Sill 1997 vs Igel 2023** — Igel ≠ Sill (hard gate); `"monotonic networks"` is not a
  word-prefix of `"smooth min max monotonic networks"` (it is a trailing substring, which the
  amended rule above deliberately excludes), so the title axis reads `mismatch`; Δyear = 26 →
  **refuse** on all three axes independently.

**Honest degradation on thin metadata.** If either side lacks a title, an author, or a year — or
carries one that normalizes to the empty string, such as a title of pure punctuation — the gate
cannot be evaluated, so search-derived rungs are **refused** with
`reason: insufficient registry metadata to verify a search-derived candidate` — never accepted
on a title match alone. Identity-derived rungs 1–3 still work, needing no gate.

### 5.3 Quarantine

A `quarantine` verdict lands bytes at `<cache>/quarantine/<citekey>/<sha256>.pdf` alongside a
`<sha256>.json` holding the candidate record, the per-axis match record, the URL, and the rung.
**Nothing is written to `references.json`.** Promotion requires an explicit human `confirm`
(§7); there is no "promote whatever is in quarantine" convenience, and quarantine is never
auto-promoted.

## 6. License-gated destination

`fetch` **never writes PDF bytes into the consumer's repository** — not automatically, and not
behind a flag. It writes the content-addressed cache, populates the mirror when one is
configured, records what it observed, and *reports* which entries would be committable. A human
who wants an in-repo copy makes it themselves. Rationale: the plugin does not add bytes to
someone's git history on the strength of a license field it scraped, and the agency principle
puts that decision with the human.

Consequently `files[].path` is **always** a content-addressed blob path, never a repo path, which
removes `dataset`'s Tier-A/Tier-B path dichotomy from the literature side entirely.

`license` records what was *observed*, not an assertion of rights: `{id, observed, source}` — an
SPDX id when a rung reported one, the raw string, and which rung said so. `redistributable`
defaults to `false` and is `true` only for an SPDX id on a shipped permissive allowlist
(`cc-by`, `cc-by-sa`, `cc0`, and the other clearly-permissive SPDX ids). **Absent or unparseable
license → `false`**, per #97's observation that 36 of 50 works in the real run carried no
license field at all.

The three-way appears in `fetch --all`'s report as `committable[]` (permissive, human may copy),
the ordinary `fetched[]`/`cached[]` (cache and mirror only), and `manual[]` (nothing obtainable).

## 7. CLI surface

```
literature fetch   [CITEKEY] [--all] [--disposition VALUE] [--refetch] [--dry-run]
literature confirm CITEKEY (--sha256 SHA | --file PATH)
literature verify  [CITEKEY] [--all]
literature mirror  [CITEKEY] [--all] [--check]
```

For `fetch`, `verify`, and `mirror`: **exactly one of `CITEKEY` or `--all` is required** — neither
is an error (nothing to do, stated as such), and both together is an error. For `confirm`:
**exactly one of `--sha256` or `--file` is required**; `--sha256` is not optional-when-unambiguous,
because promoting quarantined bytes is an explicit human act (§5.3).

`--disposition` filters `--all` by the `triage.yml` `disposition` field, taking any value from the
shipped state machine (`inbox` | `screened` | `interesting` | `acting` | `acted-on` |
`dismissed`), so a survey can sweep exactly the set it has screened in. An entry with no triage
row is excluded when `--disposition` is given and included when it is not.

**`confirm` does double duty**, which is what makes rung 7 a workflow rather than a dead end:

- `--sha256` promotes a quarantined candidate after human review — moves the blob out of
  quarantine into the content-addressed store and patches the registry.
- `--file` **adopts a manually downloaded PDF** — hashes it, moves it into the blob store,
  patches the registry, recording `rung: manual`. This closes #97's "a manual-acquisition list
  the human works through."

Every command emits JSON on stdout, per the package's convention. `fetch --all`'s report:

```json
{
  "complete": true,
  "fetched":     [{"citekey": "…", "sha256": "…", "rung": "…", "url": "…"}],
  "cached":      [{"citekey": "…", "sha256": "…"}],
  "quarantined": [{"citekey": "…", "sha256": "…", "candidate": {…}, "match": {…}, "path": "…"}],
  "manual":      [{"citekey": "…", "reason": "…", "tried": ["…"], "landing_urls": ["…"]}],
  "committable": [{"citekey": "…", "license": "cc-by-4.0"}],
  "errors":      [{"citekey": "…", "error": "…"}]
}
```

`manual[]` *is* the human worklist and carries landing URLs so there is somewhere to click.

## 8. Registry layer

### 8.1 Storage — the CSL `custom` namespace

The CSL-JSON input schema (`csl-data.json`) sets **`additionalProperties: false`** on items and
defines no `files`, `license`, `mirror`, or `sha256` field. So #97's acceptance criterion as
literally written, and `02-literature.md` §4's "the bib carries the substrate spine fields for
the PDF payload," would produce a **schema-invalid** `references.json` — against ADR-0020's
"CSL-JSON is the source of truth." The schema does define `custom`, described as "used to store
additional information that does not have a designated CSL JSON field," and it round-trips
through Zotero and pandoc.

The spine therefore lives in one namespaced object per entry:

```json
{
  "id": "sill1997monotonic",
  "type": "paper-conference",
  "title": "Monotonic Networks",
  "author": [{"family": "Sill", "given": "Joseph"}],
  "issued": {"date-parts": [[1997]]},
  "custom": {
    "defendable-science": {
      "schema": 1,
      "pid": "openalex:W2293093810",
      "files": [{"path": "sha256/ab12…", "sha256": "sha256:ab12…",
                 "size": 1518143, "media_type": "application/pdf"}],
      "license": {"id": null, "observed": null, "source": null},
      "redistributable": false,
      "access": "open",
      "mirror": {"remote": "papers", "key": "sha256/ab12…"},
      "acquisition": {
        "rung": "openalex-landing",
        "url": "https://papers.nips.cc/paper/1358-monotonic-networks.pdf",
        "candidate": {"openalex": "W2293093810", "year": 1997,
                      "first_author_family": "Sill"},
        "match": {"verdict": "identity", "title": null, "author": null, "year": null},
        "fetched": "2026-08-27"
      }
    }
  }
}
```

`schema: 1` makes a future migration possible without guessing. `match.verdict: "identity"` marks
an ungated rung, distinct from `"accept"` (gated and passed).

### 8.2 Write model — surgical, not load-and-rewrite

Issues #94 and #95 are both open bugs of the "we rewrote a human-authored file and lost content"
class. This module does not add a third.

`registry.patch_asset(citekey, asset)` reads the JSON, locates the entry by `id` (falling back to
DOI), replaces **only** `custom["defendable-science"]`, and rewrites via temp-file-and-rename
with `indent=2` and `ensure_ascii=False`. Unknown top-level keys, unknown `custom` sub-keys, and
key order are preserved.

`triage.yml` gets the same posture with a stricter limit: round-tripping YAML comments is not
possible with `pyyaml`, so triage writes are restricted to **adding or replacing scalar keys on
an existing row**, and the module **refuses with an explicit reason** rather than rewriting a
file whose comments it would destroy. A consumer with a commented `triage.yml` gets an
actionable message, not silent data loss.

### 8.3 Config

```yaml
literature:
  registry: docs/research/literature/references.json
  triage:   docs/research/literature/triage.yml
  mirror:   {remote: papers, base_path: literature}
  acquisition:
    max_bytes: 52428800
    venue_resolvers: []   # [{match: "<venue regex>", url_template: "…"}]
```

All keys optional with these defaults; a missing `literature` block means "all defaults", per
`core/config.py`'s existing posture.

## 9. Error handling and failure honesty

This feature is unusually exposed to the repo's non-negotiable rule, because "no PDF exists" and
"we failed to look for the PDF" are trivially confusable and their consequences differ
completely.

- **A throttle or a 5xx never becomes a `manual[]` row.** Telling a human to download a paper by
  hand because OpenAlex rate-limited us is exactly the class of bug #41/#43 fixed elsewhere.
  `RateLimitError` propagates (graph.py's existing contract); transport failures land in
  `errors[]`. Only an **exhausted ladder** — every rung consulted, none yielding accepted bytes
  — produces a `manual[]` row, and the row records which rungs were tried.
- **`fetch --all` exits non-zero if anything landed in `errors[]`**, so no agent or CI loop can
  read a half-swept registry as a complete one.
- **A partial sweep is marked.** `complete: false` plus the not-attempted count if the run aborts
  (interrupt, rate-limit budget). A truncated list is never presented as the whole registry.
- **A corrupt cache blob is treated as absent** per the substrate rule — but logged, not silently
  re-downloaded.
- CLI errors route through the existing `_http_guard` / `typer.Exit(1)` pattern; no raw
  tracebacks. A missing `rclone` keeps `Mirror`'s existing actionable message.
- **Quarantine is never auto-promoted** (§5.3).

## 10. Testing

Hermetic, 100% statement + branch coverage (ADR-0028), injecting the bytes-fetcher, the
`HttpClient` transport, and the rclone `run`. Fixtures are trimmed real API payloads rather than
invented shapes: the OpenAlex records for Sill 1997 (`W2293093810`), MonoKAN journal
(`W4416410340`) and MonoKAN arXiv (`W4403706439`) were captured during this design's probes; the
Igel 2023 arXiv record and the `papers.nips.cc` response headers are to be captured the same way
during implementation.

- **The named regression — #97's acceptance criterion.** Sill 1997 `W2293093810` as the registry
  entry, Igel 2023 `arXiv:2306.01147` as the search-derived candidate. Asserts four things, not a
  boolean: verdict is `refuse`; the per-axis record shows the **author** axis failing;
  `references.json` is byte-identical afterwards; the entry lands in `manual[]`, not
  `quarantined[]`.
- **The positive counterpart.** The MonoKAN pair (`W4416410340` journal entry, `W4403706439`
  arXiv candidate): sibling-version rung → `accept` at Δyear = 1. This is the test that stops
  someone "fixing" the gate by tightening the year to exact and quietly breaking every
  preprint/journal pair.
- **The lying-content-type case.** Sill's `papers.nips.cc` landing URL served as
  `Content-Type: text/html` with a `%PDF-` body → accepted on magic bytes. Rung 3's reason to
  exist.
- **Thin-metadata degradation.** An entry with no author: rungs 1–3 succeed; rungs 4–6 refuse
  with the insufficient-metadata reason.
- **Drift.** `--refetch` yielding different bytes for an entry with a recorded `sha256` → refuse,
  registry unchanged.
- **Write safety.** Unknown top-level CSL keys and unknown `custom` sub-keys survive a patch
  unchanged; a commented `triage.yml` is refused rather than stripped.
- **Failure honesty.** A `RateLimitError` mid-sweep does not produce a `manual[]` row, sets
  `complete: false`, and exits non-zero.
- **Promotion of the `dataset` internals** is covered by the existing suite continuing to pass
  unchanged — the refactor of §3 must not alter `dataset` behaviour.
- **Live suite** (`@pytest.mark.live`, skipped by default): real OpenAlex resolution plus one
  real small PDF download.

## 11. Documentation and decision record

More doc change than code change, and two items are corrections rather than additions.

- **New ADR `0037`** — *Literature asset acquisition: spine under CSL `custom`, three-way match
  gate.* Records the `custom.defendable-science` namespace (driver: the schema's
  `additionalProperties: false`); the accept/quarantine/refuse gate with author-family as a hard
  gate; `fetch` never writing in-repo bytes; venue resolvers config-driven and empty by default.
  Rejected alternatives: top-level CSL fields (schema-invalid), a separate `assets.yml` sidecar,
  folding the spine into `triage.yml`, a two-way gate, license-driven automatic placement,
  shipped ML-venue scrapers, a full `substrate/` extraction with a unified `materialize()`.
  Appended to `decisions/README.md`.
- **`docs/design/02-literature.md`** §4/§5 — amend "the bib carries the substrate spine fields"
  to the `custom` namespace; document the ladder and the gate.
- **`docs/design/04-substrate-and-contract.md`** §2.4 — record the two variants of chain step 3
  (§4).
- **`docs/design/proposals/literature-asset-acquisition.md`** — the shipped CLI-module design
  record, matching `dataset-retrieval-mirror-tooling.md`. A deliverable of the implementation.
- **`skills/literature/SKILL.md`** — add the four verbs to §Tooling and a registry subsection;
  **remove the §1.1 overclaim** (the CSL loader/appender becomes real here; the PRISMA-log and
  concept-matrix generators do not, and the claim comes out until they do).
- **`skills/digest/SKILL.md`** step 1 — point at `literature fetch` / `verify`. This is the line
  that closes #97's headline complaint.
- **`resources/ensure-tooling.md`** — bump the compatible package range (ADR-0026) once the
  package version lands. **Do not** touch `.claude-plugin/plugin.json`'s version from the
  package's automation.
- **`CHANGELOG.md`**.
- **`docs/guides/literature.md`** — a new, task-oriented user guide for the whole `literature`
  capability, required as part of this work rather than after it. See §11.1.

### 11.1 The `literature` user guide (a required deliverable)

Today the capability's only user-facing documentation is `docs/USER-GUIDE.md` §4c, about
twenty-five lines. With this spec's four verbs, the registry spine, the ladder, quarantine, and
the license three-way added, that is far too little for someone to pick the capability up — so
the guide ships **with** the code, not later.

**Route and nav.** `docs/guides/literature.md`, registered in `tools/build_docs_site.py`'s
`plan()` under a new `"Guides"` navigation group placed immediately after `"Get started"`. The
group is introduced now with one page and is where the deferred user-guide refactor will put the
rest.

**Running example: a survey paper.** A survey is the right vehicle because it exercises every
part of the capability at once and at scale — a large screened set, a concept matrix, per-paper
acquisition, and a license mix — where a methods paper touches only a few references. The example
is the monotonicity survey from the consumer run that produced #97 (73 works resolved, 40
proposed for inclusion), because its numbers, its license split (14 of 50 with an explicit
license), and its failure cases are real and checkable rather than invented.

**Content requirements.**

1. The registry layout — `references.json` and `triage.yml`, what belongs in each, and why the
   spine lives under `custom` (§8.1).
2. The survey walkthrough end to end: seed anchors → snowball → triage/PRISMA log → `fetch --all
   --disposition screened` → work the four report buckets → read → matrix.
3. What to do with each `fetch --all` bucket: `cached`/`fetched` (nothing), `quarantined`
   (review, then `confirm --sha256`), `manual` (download by hand, then `confirm --file`),
   `committable` (copy in-repo yourself if you want to), `errors` (a tooling failure, not a
   paper problem — retry).
4. The license three-way in practice, stated plainly: an absent license means
   **not redistributable**, and most papers have no license field.
5. Why a refusal is a feature — the Sill-1997-vs-Igel-2023 case as a worked example of the gate
   doing its job, so a reader who hits a refusal does not go looking for a flag to disable it.

**Must not repeat the §4c defect.** `docs/USER-GUIDE.md` §4c currently prints
`literature scout --level hypothesis` and `literature position --level hypothesis` in bare code
blocks that read as shell, but neither is a CLI command — both are *skill modes*. (The following
block has the same problem with `dataset register` / `dataset init`; the real verbs are
`validate|ingest|emit|fetch|verify|mirror|audit`.) A reader who copies those into a terminal gets
"no such command". The new guide must keep **what you say to the agent** and **what runs in a
shell** visually distinct on every example, and label every shell block with the real
`defendable-science …` invocation. Correcting §4c itself is a separate follow-up (§13).

## 12. Implementation shape

Scope check: this is one spec but it should not be one pull request. It splits into three
independently reviewable, independently landable pieces, in this order:

1. **Substrate promotion** (§3) — move `sha256_file` / `blob_path` / `RetrievalError` to
   `core/fixity.py` and `Mirror` to `core/mirror.py`; `dataset/retrieval.py` re-imports. A pure
   refactor: the existing `dataset` suite must pass unchanged, with no new tests needed beyond
   what already covers those functions.
2. **Registry layer** (§8) — `literature/registry.py` plus the streaming bytes-fetcher in
   `core/http.py`. Shippable and testable with no CLI surface; this is the piece Gap 2 depends on.
3. **Acquisition + CLI** (§4–§7, §9) — `literature/acquire.py`, the four verbs, and the doc/ADR
   changes of §11 **including the user guide of §11.1**.

Piece 1 must not change `dataset` behaviour; that is the review criterion for it. Pieces 2 and 3
carry the new tests of §10. Piece 3 is not done until §11.1's guide is written — a reviewer should
treat a missing guide as a missing deliverable, not a follow-up, because the capability is already
past the point where a reader can infer its use from `--help`.

## 13. Follow-up issues to file

Self-contained and cold-readable, per the house standard (`create-issue` skill):

1. **`literature audit`** — parity with `dataset audit` (§2 non-goal).
2. **PRISMA-log + concept-matrix generators** — the remainder of the §1.1 overclaim.
3. **Gap 2 — `digest` extraction mode**, rewritten against the registry interfaces this spec
   establishes (`registry.patch_asset`, the triage write restriction of §8.2).
4. **Gap 3 — survey-shaped paper templates**, noting its dependency on #96 for template
   plumbing.
5. **`docs/USER-GUIDE.md` §4c prints skill modes as shell commands** — a pre-existing defect,
   independent of #97: `literature scout` / `literature position` and `dataset register` /
   `dataset init` are not CLI commands, so a reader who copies them gets "no such command". Fix
   the four blocks and audit the guide for the same pattern elsewhere. Exact locations are
   `docs/USER-GUIDE.md:202-203` and the `dataset` block immediately following.
6. **User-guide refactor** — restructure `docs/USER-GUIDE.md` around the `"Guides"` nav group
   §11.1 introduces, moving per-capability material out of the single monolithic page. Explicitly
   deferred by the author; §11.1's guide is the first page of the target structure and should be
   treated as the pattern to follow.

## 14. Open questions

None blocking. Two judgement calls recorded for the implementer:

- The permissive SPDX allowlist of §6 is a fixed shipped set; if a consumer needs a license we
  do not classify, `redistributable` stays `false` and they copy the file themselves. No config
  override, deliberately — a consumer overriding a redistribution judgement is a
  license-compliance decision the plugin should not make configurable.
- `max_bytes` defaults to 50 MiB. Large enough for any paper, small enough that a
  misidentified-URL download of a dataset or video fails fast rather than filling a disk.
