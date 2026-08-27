# defendable-science sub-spec 2 — Literature capability (`literature`)

**Date:** 2026-07-17
**Author:** Davor Runje
**Status:** Implemented. Sub-spec of the `defendable-science` meta-spec; realized in this repo (skills + CLI).

> Sub-spec of [00-meta-spec.md](00-meta-spec.md).
> Builds on the asset substrate of
> [sub-spec 4](04-substrate-and-contract.md) §2.
> Governed by the ⚑ agency (§2.1) and Understanding (§2.2) principles.
> Grounding: [citation-scouting](../../resources/references/citation-scouting.md),
> [related-works-synthesis](../../resources/references/related-works-synthesis.md).

## 1. The `literature` skill

One skill, two modes over one citation-graph substrate. Each mode takes a
`level ∈ {hypothesis, paper, thesis}` parameter (the three mirror levels) that
tunes ranking / depth / stopping — the level split is a *parameter*, not a skill
boundary.

| Mode | Intent | Feeds | Output |
|---|---|---|---|
| `scout` | generative, *outward* — mine the citation graph for leads | `*-exploration` backlogs | ranked idea rows with provenance |
| `position` | defensive, *inward* — situate a committed claim/paper | `hypothesis-testing` strategy; `paper-synthesis` positioning | precedent verdict (hyp) / `positioning.md` (paper) |

**Agency & Understanding interlock:** `scout` *proposes* leads and `position`
*surfaces* precedent; neither adjudicates. The human decides what to pursue and
what counts as novel. The `defend` skill's `cited-work` target draws on this
capability ("does ref [12] actually support this sentence?").

## 2. `scout` mode

Engine (from the citation-scouting digest): **OpenAlex** backbone (free, keyless
`mailto=` polite pool) + **Semantic Scholar** for citation **contexts + intents
(SciCite)** and recommendations.

Pipeline: fix anchor set (own papers + rival anchors) → pull forward citations →
enrich (year, venue, count, authors, **context snippet + intent**) → filter/rank
→ cluster (co-citation + bibliographic coupling) into sub-fronts → classify each
into an idea type (untested extension / contradiction / new domain / transferable
technique / methodological gap) → emit ranked backlog rows.

**Mandatory provenance on every emitted idea:** `idea | type | source-paper (id) |
citing-context snippet | why-it-matters | est. feasibility`. The snippet is the
auditable link from idea back to who-cited-what. Rows land in the relevant
`backlog.md` / `portfolio-backlog.md` (a `scout`-emitted row is a *proposal* the
human triages via the exploration skills).

**Level tuning:** `hypothesis` → precision; small set, read full text,
context/intent dominates (find Contrasting / Result-comparison citations).
`paper` → recall; large set, skim metadata, co-citation clustering + research-front
/ burst detection dominates. `thesis` → program-wide recall across *all* aims,
unioned/deduplicated across the papers' sets.

Idea-shaping lenses (applied by the exploration skills, not scout): gap-spotting
vs. problematization (Sandberg & Alvesson 2011); feasibility × interest (Alon
2009).

## 3. `position` mode

Pipeline (from the related-works-synthesis digest): frame the claim(s) as
falsifiable deltas → build a diverse seed set → **snowball to saturation**
(backward + forward, S2/OpenAlex) with a **PRISMA-style log** (include/exclude +
reasons — the anti-cherry-picking audit trail) → extract a **concept-centric
matrix** (Webster & Watson: rows = methods, cols = the attributes the delta turns
on) → derive the **taxonomy** → write a per-branch **delta** → derive
**baselines** (one strong tuned representative per branch + current SOTA + the
most-likely-cited-against + a simplest floor).

Anti-patterns guarded (safeguards in parentheses): cherry-picking (PRISMA log),
author-by-author prose (concept matrix), overclaiming novelty (adversarial
precedent search + explicit "closest prior work" paragraph + isolating ablation),
weak baselines (matched tuning/splits).

**Level tuning:** `hypothesis` → a fast **adversarial precedent rapid-review**:
"would a reviewer say this is already known?" → verdict + the 1–3 papers that
would reject it + the surviving delta; feeds `strategy.md`. `paper` → full
taxonomy + comparison table + related-work prose + baseline list → `positioning.md`.
`thesis` → the widest synthesis: independent related work at thesis scope,
unioned/deduplicated across every aim/paper (a PhD's literature footprint exceeds
the union of its published papers) → the kappa's independent related-work chapter.
Ship a PRISMA-style log at every level.

## 4. Registry — bib + triage sidecar

Two layers joined by citekey/DOI (from the meta-spec §3.4 decision — share the
substrate mechanism, *not* the dataset manifest format):

1. **Bibliographic facts** — a standard format (**BibTeX / CSL-JSON**,
   Zotero-exportable). Immutable, ecosystem-native (pandoc/LaTeX). Carries the
   substrate spine for the PDF payload (`pid`/DOI, `files[]` = PDF + sha256,
   `license`, `mirror`, `acquisition`) namespaced under CSL-JSON's own
   `custom.defendable-science` field, **not** as top-level item properties —
   the CSL input schema sets `additionalProperties: false` on items and
   defines no such fields, so a top-level spine would make `references.json`
   schema-invalid against ADR-0020's source-of-truth claim. See ADR-0037 and
   §5 below for the acquisition mechanism that populates it.
2. **Triage sidecar** — git-tracked YAML, keyed by citekey/DOI. *Our decisions:*
   - `role` — anchor / rival / prior-art / support / contrast / neighbor
   - `disposition` — state machine: inbox → screened → interesting → acting → acted-on → dismissed
   - `rationale` — why interesting / why dismissed (**doubles as the PRISMA include/exclude reason**)
   - `priority`, `intent` (SciCite), `seeded` (forward links to backlog items / hypotheses / papers this inspired), `notes`, reviewer, date

The triage layer is the literature↔lifecycle connector: an **`acted-on`**
disposition spawns a backlog entry (the reference→idea provenance link `scout`
produced); **`screened` in/out + rationale** across a paper's set *is* the PRISMA
log for `position`.

**Source of truth is git-tracked plain text** (bib + triage sidecar); Zotero is
an optional authoring front-end that exports the bib — no shared DB dependency.

## 5. Mirror & fixity

PDFs use the substrate mirror (sub-spec 4 §2.3): key papers are mirrored via
rclone with SHA-256 fixity, resolving via the same cache → mirror → source chain.
Copyright is respected exactly as dataset licensing is — a mirror is storage, not
a redistribution grant; the `license`/`redistributable` fields gate whether a PDF
may be committed vs. mirror-only.

Unlike `dataset`, a literature entry usually has no pre-known hash to verify
against on first acquisition (04 §2.4 records this as the second variant of
the chain's step 3): `fetch` runs an **acquisition ladder**, and a
**match gate** substitutes for the absent trust anchor on every rung whose
candidate came from a search rather than the anchor's own metadata.

**The ladder.** Rungs 1–3 are *identity-derived* — the URL comes from the
OpenAlex work the citekey already resolves to (`best_oa_location`, every
`locations[].pdf_url`, then every `locations[].landing_page_url` that
actually serves PDF bytes, checked by magic bytes because `Content-Type`
lies) — so no matching is needed. Rungs 4–6 are *search-derived* — a
sibling-version title search, an arXiv query, and a config-driven, empty-by-
default `venue_resolvers` list — and every candidate they produce passes
through the gate before its bytes are ever accepted. A rung's own pre-filter
narrows what it searches for; it must never be stricter than the gate itself,
or a genuine match gets discarded before the gate sees it. Rung 7 is
*manual*: nothing fetched, reported with landing URLs for a human to click,
adopted afterwards via `confirm --file`.

**The gate.** Three axes — title (normalized, trailing subtitle optionally
dropped), first-author family name, and year — combine into `accept` /
`quarantine` / `refuse`. **First-author family name is a hard gate: no
candidate is ever accepted or quarantined across an author mismatch.** Title
agreement admits either a normalized-equal match or a **word-prefix**
containment match (not a bare substring — substring matching isn't
word-aware, so `"Net"` would wrongly score a containment match against
`"Monotonic Networks"`). This is what accepts a genuine preprint/journal
sibling pair one year apart while refusing a same-topic paper by a different
author found by the same search. Quarantine lands bytes and the candidate
record on disk without ever touching `references.json`; promotion is an
explicit human `confirm`, never automatic. See ADR-0037 for the full
rationale and the two motivating cases (a real sibling pair vs. a genuine
false positive) that shaped the gate.

`fetch` never writes PDF bytes into the consumer's repository, automatically
or behind a flag — `files[].path` is always a content-addressed blob path.
A human who wants an in-repo copy of a permissively-licensed PDF makes that
copy themselves, using the report's `committable[]` bucket as the worklist.

## 6. Plugin vs. consumer

- **Plugin:** the `literature` skill; the citation-graph engine (OpenAlex + S2
  clients, snowballing, intent classification, clustering); the bib-loader +
  triage-schema; the PRISMA-log + concept-matrix generators; reference digests.
  Deps: HTTP client + `pyyaml` (+ the substrate's rclone mirror). No heavy deps.
- **Consumer:** the `references.json` + `triage.yml`; mirrored PDFs; API config
  (anchors, keys) in `.defendable-science/config.yml`.

## 7. Open items

- **Bib format** — *resolved (ADR-0020):* **CSL-JSON is the source of truth**
  (robust to parse/validate/manipulate — the skills append/join programmatically);
  **BibTeX is exported on demand** (pandoc/Zotero) for LaTeX manuscripts. Authors
  who prefer hand-editing `.bib` treat it as a generated view.
- **Semantic Scholar key** — optional; degrade gracefully to OpenAlex-only if
  absent.
- **scite.ai** (Supporting/Contrasting) — out of scope for v1 (paid); SciCite
  intents from S2 cover the need.
