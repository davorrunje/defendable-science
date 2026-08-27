# ADR-0037: Literature asset acquisition — spine under CSL `custom`, three-way match gate

- Status: accepted · Date: 2026-08-27 · Deciders: Davor Runje

## Context

#97 (Gap 1) asks `literature` to acquire a PDF for a registry entry the way
`dataset fetch` acquires a data blob, closing the only documented path into
`digest` (`skills/digest/SKILL.md` step 1 requires "a real registry entry +
mirrored PDF," but no `fetch`/`verify`/`mirror`/`confirm` existed to produce
one). Two things surfaced while designing the fix that this record exists to
capture, because neither is reconstructable from the code alone:

1. **02-literature.md §4, as written, is schema-breaking.** It instructs the
   bib to "carry the substrate spine fields for the PDF payload" — `pid`,
   `files[]`, `license`, `mirror` — as fields on the CSL-JSON item itself. The
   CSL input schema (`csl-data.json`) sets `additionalProperties: false` on
   items and defines no such fields, so following that instruction literally
   produces a `references.json` that fails CSL-JSON validation — directly
   against ADR-0020's "CSL-JSON is the source of truth."
2. **The acquisition problem #97 diagnoses is narrower than the fix it
   proposes.** #97 asks for venue-specific resolvers (`papers.nips.cc`,
   `proceedings.mlr.press`, `openreview.net`), which would put ML-venue logic
   in the plugin. Probing the three concrete cases from the consumer run that
   raised #97 showed OpenAlex already holds all three PDFs; `best_oa_location`
   simply doesn't surface them (see the design spec, `docs/superpowers/specs/
   2026-08-27-literature-asset-acquisition-design.md`, §1.2, for the per-case
   detail). Reading every `locations[]` entry, plus landing pages that serve
   PDF bytes regardless of their `Content-Type`, recovers all three with no
   venue knowledge at all.
3. **A real sibling-version case and a wrong-paper case pull on the same
   axis.** The genuine MonoKAN preprint/journal pair sits one year apart under
   the same title, family, and (loosely) content — exactly the shape a search
   error also takes. `arXiv:2306.01147` (Igel, *Smooth Min-Max Monotonic
   Networks*, 2023) is a false positive for `sill1997monotonic` (Sill,
   *Monotonic Networks*, 1997) under a title search loose enough to catch the
   real sibling. Something has to separate them without an exact-title
   requirement, which would throw out genuine subtitle/rewording drift between
   preprint and journal versions.

## Decision drivers

- **Schema validity.** `references.json` must stay valid CSL-JSON at every
  step (ADR-0020) — no field the schema doesn't define, at the top level.
- **Never guess at a citation binding.** A wrong PDF one keystroke from a
  citekey is worse than no PDF; the mechanism must refuse rather than accept
  on thin evidence, and record what it refused and why.
- **Domain-neutrality.** No ML-, venue-, or consumer-specific logic ships in
  the plugin (repo-wide rule); a real acquisition gap must be closed generically
  or left to consumer config.
- **Agency.** The plugin does not add bytes to a consumer's git history on the
  strength of a license field it scraped; a human makes that call.
- **Failure honesty.** "No PDF exists" and "we failed to look for one" are
  trivially confusable and must not be conflated (repo-wide rule).
- **Consistency with the existing substrate.** `dataset`'s cache → mirror →
  source chain and SHA-256-authoritative fixity (ADR-0011, ADR-0012) should be
  reused, not re-invented, everywhere the two front-ends are actually doing
  the same thing.

## Considered options — where the spine lives

1. **Top-level CSL fields** (`files`, `license`, `mirror`, `sha256` as item
   properties) — what §4 said before this ADR.
2. **A separate `assets.yml` sidecar**, joined by citekey/DOI alongside
   `triage.yml`.
3. **Fold the spine into `triage.yml`.**
4. **A single namespaced object under CSL-JSON's `custom` field.** *(chosen)*

## Decision

**Option 4.** The substrate spine lives under `custom.defendable-science` on
each CSL-JSON item:

```json
{
  "id": "sill1997monotonic",
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
      "acquisition": {"rung": "…", "url": "…", "candidate": {…},
                       "match": {…}, "fetched": "2026-08-27"}
    }
  }
}
```

`custom` is the CSL-JSON schema's own designated escape hatch ("used to store
additional information that does not have a designated CSL JSON field") and
round-trips through Zotero and pandoc unchanged, so a hand-authoring workflow
built on either tool does not see the spine as garbage. `schema: 1` versions
the namespace's own shape for a future migration.

Two further, related decisions the same design fixes:

- **A three-way match gate — accept / quarantine / refuse — with first-author
  family name as a hard gate.** No candidate is ever accepted or quarantined
  across an author mismatch, independent of how well title or year agree.
  This is what refuses Igel 2023 as a candidate for Sill 1997 while still
  accepting the genuine MonoKAN preprint/journal pair one year apart under the
  same author. Title agreement is graded two ways — normalized-equal, or
  containment — and containment is a **word-prefix** relation, not a substring
  one: substring matching is not word-aware, so `"GAN"` would score a
  containment match against `"Improved Training of Wasserstein GANs"`, and
  `"Net"` against `"Monotonic Networks"`, which would have scored the very
  Sill/Igel pair the gate exists to refuse as at least a quarantine (both
  contain "monotonic networks" as a trailing substring). Word-prefix is the
  minimal word-aware relation that still admits genuine subtitle drift
  (`"MonoKAN"` ↔ `"MonoKAN: Certified Monotonic Kolmogorov-Arnold Network"`)
  while rejecting Igel.
- **A rung's own pre-filter must never be stricter than the gate it feeds.**
  The sibling-version rung's title pre-filter originally required exact
  normalized-title equality — stricter than the gate's own containment
  allowance — which would have discarded a genuine sibling with a
  journal-added subtitle before the gate ever saw it. A pre-filter narrows a
  search; only the gate adjudicates.
- **`fetch` never writes PDF bytes into the consumer's repository** — not
  automatically, not behind a flag. `files[].path` is always a
  content-addressed blob path. The plugin does not decide, on the strength of
  a license field it scraped, to add bytes to someone's git history; a human
  who wants an in-repo copy makes that copy themselves, using the
  `committable[]` report bucket as the worklist.
- **Trust-on-first-use, with the match gate substituting for a pre-known
  hash.** `dataset` treats its manifest SHA-256 as authoritative and already
  known; a paper has no hash to check against on first acquisition, so the
  gate is what stands in its place — which is why the gate is load-bearing
  rather than a nicety. Once a hash is recorded, `--refetch` yielding
  different bytes **refuses and reports the drift** rather than silently
  rebinding a citekey to a different version of the paper.
- **`venue_resolvers` is config-driven and ships empty** (`[]`). The generic
  rungs (every OpenAlex `locations[]` entry, plus PDF-serving landing pages,
  plus a sibling-version search) recover all three of #97's motivating cases
  with no venue knowledge; a consumer needing an exotic venue adds a
  `{match, url_template}` pair to their own config, keeping the plugin
  domain-neutral.
- **An observed license belongs to the location the bytes came from,**
  including its absence. A license is recorded as `{id, observed, source}` —
  what a rung actually reported, not an assertion of rights — and an absent
  or unrecognized license means `redistributable: false`. This applies
  uniformly, including to a `confirm --file` adoption of a hand-downloaded
  PDF: the tool observed nothing about rights on bytes it did not fetch, so
  the license is recorded empty and non-redistributable rather than guessed.

## Consequences

- `references.json` stays valid CSL-JSON at every step, closing the gap
  02-literature.md §4 opened; a validator running against the raw CSL schema
  sees ordinary `custom` data, not an error.
- The spine travels with the bibliographic record it describes (one join, not
  two), while staying cleanly separable — a consumer who doesn't use `literature
  fetch` at all sees an item with no `custom.defendable-science` key, which is
  indistinguishable from an entry Zotero authored directly.
- The gate is strict enough to refuse real false positives (Igel/Sill) and
  loose enough to accept a real sibling pair (MonoKAN) — the two cases that
  motivated the design pull in opposite directions on the year and title axes,
  and the author hard gate is what lets both resolve correctly.
- A citekey's identity is exactly what its recorded bytes say it is; drift
  never silently rebinds it.
- `venue_resolvers` gives a consumer an escape hatch for an exotic venue
  without asking the plugin to carry it.

## Rejected alternatives

- **Top-level CSL fields** — schema-invalid against `csl-data.json`'s
  `additionalProperties: false`; the reason this ADR exists.
- **A separate `assets.yml` sidecar** — a third join (bib × triage × assets)
  where 02-literature.md §4 specifies two; diverges from the shipped design
  for no offsetting benefit, and doubles the ways the three files can drift
  out of sync with each other.
- **Folding the spine into `triage.yml`.** `triage.yml` holds mutable human
  decisions (role, disposition, rationale, priority); the spine holds
  immutable byte facts (a SHA-256 doesn't change because someone re-triages a
  paper). Mixing them would make `triage.yml`'s comment-preserving restricted
  write (§8.2 of the design spec) responsible for surgically patching two
  unrelated kinds of data, and would put a hash inside a file explicitly
  designed to be safe for a human to hand-edit.
- **A two-way accept/refuse gate** (no quarantine). Loses the real MonoKAN
  sibling: at Δyear = 1 with a normalized-equal title, a two-way gate must
  either accept blind (risky for a genuinely ambiguous candidate) or refuse
  correct matches outright. Quarantine is the middle state that lets a human
  adjudicate the genuinely close cases without the tool either guessing or
  discarding real hits.
- **License-driven automatic in-repo placement.** Letting a permissive
  observed license auto-copy bytes into the consumer's repository would be
  the plugin making a redistribution-and-commit decision on the strength of a
  scraped field, not a human sign-off — against the agency principle. The
  `committable[]` report bucket exists precisely so the human still makes the
  copy.
- **Shipped ML-venue scrapers**, as #97 proposed. Breaches domain-neutrality,
  and turned out to be unnecessary: reading all of OpenAlex's `locations[]`
  plus PDF-serving landing pages recovers the three motivating cases with no
  venue-specific code at all.
- **A full `substrate/` extraction with a unified `materialize()`.** Would
  have to paper over the known-hash-vs-trust-on-first-use split between
  `dataset` and `literature` documented in §2.4 of
  `docs/design/04-substrate-and-contract.md` — a false abstraction that
  hides the one place the two front-ends genuinely differ, for a large diff
  this feature does not need to carry. Only the genuinely shared primitives
  (`sha256_file`, the content-addressed blob path, the rclone `Mirror`) were
  promoted, to `core/fixity.py` and `core/mirror.py`; the two resolution
  chains stay separate.

## Links

`docs/superpowers/specs/2026-08-27-literature-asset-acquisition-design.md` (the
full design, §4–§8); `docs/design/02-literature.md` §4–§5;
`docs/design/04-substrate-and-contract.md` §2.4;
`docs/design/proposals/literature-asset-acquisition.md`;
`defendable-science/defendable_science/literature/{registry,acquire}.py`;
ADR-0008 (bib + triage sidecar), ADR-0011 (rclone mirror, SHA-256
authoritative), ADR-0012 (shared substrate), ADR-0020 (CSL-JSON source of
truth); #97 (Gap 1).
