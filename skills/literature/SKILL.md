---
name: literature
description: >-
  Mines and situates a research literature over one citation-graph substrate
  (OpenAlex + Semantic Scholar). Use when scouting the forward-citation graph for
  research leads (scout mode) or defending a committed claim/paper against prior
  work (position mode); maintains a CSL-JSON bib + triage sidecar. Proposes and
  surfaces — it does not adjudicate novelty; the human decides.
---

One skill, two modes over one citation-graph substrate. `scout` looks **outward**
(generative — mine the graph for leads); `position` looks **inward** (defensive —
situate a committed claim against prior work). Both walk the same graph engine —
**OpenAlex** backbone (free, keyless via `mailto=` polite pool) plus **Semantic
Scholar** for citation contexts, SciCite intents, and recommendations — and both
write to the same registry (a CSL-JSON bib + a YAML triage sidecar). A `level`
parameter (`hypothesis` | `paper` | `thesis`) — the three mirror levels — tunes
ranking, depth, and stopping; it is a *parameter*, not a mode boundary.

This skill **proposes and surfaces**; it never adjudicates. `scout` proposes
leads, `position` surfaces precedent — the human decides what to pursue and what
counts as novel.

## When to use

- **`scout`** — you want research leads mined from who-cited-whom: "what have
  people built on our work / the rivals', and where are the open sub-fronts?"
  Emits ranked idea-backlog rows, each with mandatory provenance.
- **`position`** — you have a committed claim or paper and need to defend it:
  "would a reviewer say this is already known?" (hypothesis) or "write the related
  work + pick baselines" (paper). Emits a precedent verdict or `positioning.md`
  with a PRISMA-style audit trail.
- **Registry upkeep** — record/triage a paper (role, disposition, rationale),
  export `.bib` for a manuscript, or resolve a mirrored PDF.

Not for: running experiments (that's the experiment-backend contract), or
deciding novelty/what to publish (a human sign-off, per the agency principle).

## Modes

| Mode | Direction | For |
|---|---|---|
| `scout` | outward / generative | mine the citation graph for leads → ranked idea-backlog rows |
| `position` | inward / defensive | situate a committed claim/paper → precedent verdict / `positioning.md` |

A `level` parameter (`hypothesis` \| `paper` \| `thesis`) tunes ranking/depth/stopping
— see the per-mode "Level tuning" notes below. Both modes run through the
`defendable-science literature` CLI (see [Tooling](#tooling)).

## How it works — `scout` mode

Grounding: [../../resources/references/citation-scouting.md](../../resources/references/citation-scouting.md).

Steps 1–5 are `defendable-science literature` commands (`resolve` / `cites` / `refs` /
`enrich` / `neighbors`) — install via `ensure-tooling`; see [Tooling](#tooling).

1. **Fix the anchor set** — own papers + rival anchors from `.defendable-science/config.yml`
   (or args). Resolve each to a stable id (DOI / arXiv / OpenAlex / S2).
2. **Pull forward citations** per anchor — OpenAlex `filter=cites:<WORKID>` and
   S2 `/paper/{id}/citations`. Store the raw JSON as the provenance root.
3. **Enrich** each citing paper — year, venue, citation count, authors, and the
   **citation-context snippet + SciCite intent** (Background / Method /
   Result-comparison) plus `isInfluential` from S2.
4. **Filter / rank** — intent (Method / Result-comparison > Background), recency
   (24–36 mo up for fronts), coupling proximity; impact is a tie-breaker only.
5. **Cluster** by co-citation + bibliographic coupling to expose sub-fronts.
6. **Classify** each cluster/paper into an idea type: untested extension,
   contradiction/rival, new domain, transferable technique, or methodological gap.
7. **Emit ranked backlog rows** — one per idea, with **mandatory provenance**:
   `idea | type | source-paper (id) | citing-context snippet | why-it-matters |
   est. feasibility`. The snippet is the auditable link from idea back to
   who-cited-what. Rows land in the relevant `*-exploration` backlog as
   *proposals* the human triages.

**Level tuning.** `hypothesis` → precision: small set, read full text,
context/intent dominates (surface Contrasting / Result-comparison citations).
`paper` → recall: large set, skim metadata, co-citation clustering + research-front
/ burst detection dominates. `thesis` → program-wide recall: mine the whole
program's citation neighborhood across *all* aims (future-work fronts that span
papers), unioned and deduplicated across the papers' sets.

> *e.g.* anchor = the group's ICML'23 paper → a citing paper with a
> **Result-comparison** intent whose snippet reads *"unlike [anchor], our method
> needs no lattice"* → idea row: `type: contradiction/rival | source: <id> |
> snippet: "…no lattice" | why: a competing mechanism to test against |
> feasibility: med`.

## How it works — `position` mode

Grounding: [../../resources/references/related-works-synthesis.md](../../resources/references/related-works-synthesis.md).

Snowball steps use the same `defendable-science literature` commands (`resolve` /
`cites` / `refs` / `enrich`); see [Tooling](#tooling).

1. **Frame the claim(s)** as 1–3 falsifiable delta statements *before* searching.
2. **Build a diverse seed set** — 3–6 anchors spanning communities/terminologies
   (reduce single-community myopia).
3. **Snowball to saturation** — backward (references → foundations/precedent) +
   forward (citations → newer competitors/SOTA), iterate until no new relevant
   method appears. Log **every** candidate with an include/exclude reason — this
   is the PRISMA-style audit trail (the anti-cherry-picking defense), materialized
   from the triage sidecar (screened + rationale).
4. **Extract a concept-centric matrix** (Webster & Watson): rows = included
   methods, cols = the attributes the delta turns on. Never organize
   author-by-author.
5. **Derive the taxonomy** from the matrix column clusters (the section spine).
6. **Write the per-branch delta** — one sentence per branch, grounded in a matrix
   cell: "Unlike ⟨family⟩ we ⟨difference⟩, which yields ⟨consequence⟩."
7. **Derive baselines from the taxonomy** — one strong tuned representative per
   branch + current SOTA + the most-likely-cited-against + a simplest floor.
   Match splits / tuning budget / compute.

**Level tuning.** `hypothesis` → a fast **adversarial precedent rapid-review**:
"would a reviewer say this is already known?" → verdict + the 1–3 papers that
would reject it + the surviving delta; feeds `strategy.md`. `paper` → full
taxonomy + comparison table + related-work prose + baseline list →
`positioning.md`. `thesis` → the **widest** synthesis: independent related work at
thesis scope, unioned and deduplicated across *every* aim/paper — deliberately
broader than any single paper's `positioning.md` (a PhD's literature footprint
exceeds the union of its published papers) → the kappa's independent related-work
chapter. Ship a PRISMA-style log at **every** level.

## Registry — bib + triage sidecar

Two git-tracked layers joined by citekey/DOI (per ADR-0008, ADR-0020):

**1. Bibliographic facts — CSL-JSON (`references.json`), source of truth.**
Robust to parse/validate/manipulate (the skills append rows, join by key, build
matrices programmatically). **BibTeX is exported on demand** (pandoc / Zotero)
for LaTeX manuscripts — treat any `.bib` as a generated view, not the source.
Do **not** hand-author `.bib` as the truth.

**2. Triage sidecar — `triage.yml`, keyed by citekey/DOI.** Our decisions about
each paper:

- `role` — anchor / rival / prior-art / support / contrast / neighbor
- `disposition` — state machine: `inbox → screened → interesting → acting →
  acted-on → dismissed`
- `rationale` — why interesting / why dismissed (**doubles as the PRISMA
  include/exclude reason**)
- `priority`, `intent` (SciCite), `seeded` (forward links to backlog items /
  hypotheses / papers this paper inspired), `notes`, reviewer, date

**The triage layer is the literature↔lifecycle connector.** An `acted-on`
disposition spawns a backlog entry (the reference→idea provenance link `scout`
produced); `screened` in/out + rationale across a paper's set *is* the PRISMA log
for `position`.

### The `custom.defendable-science` namespace — PDF provenance

The substrate spine for a paper's PDF payload (`pid`, `files[]`, `license`,
`mirror`, `acquisition`) lives under one namespaced object,
`custom.defendable-science`, on the CSL-JSON item — **never** as top-level
item properties. The CSL input schema forbids additional top-level properties
on an item, so a top-level spine would make `references.json` schema-invalid;
`custom` is the schema's own designated escape hatch and round-trips through
Zotero and pandoc unchanged (ADR-0037). `literature fetch` / `confirm`
populate this field; you should not hand-edit it.

`files[].path` is always a **content-addressed blob path** — `fetch` never
writes PDF bytes into this repository, automatically or behind a flag. A
license is recorded as what was *observed* (`{id, observed, source}`), not an
assertion of rights: absent or unrecognized means `redistributable: false`.
If you want an in-repo copy of a permissively-licensed PDF, copy it yourself;
`fetch --all`'s `committable[]` bucket is the worklist for exactly that.

**PDFs use the shared substrate.** Resolve via the cache → mirror → source
chain; the authoritative checksum is SHA-256 in the registry (see
[../../docs/design/04-substrate-and-contract.md](../../docs/design/04-substrate-and-contract.md) §2). A literature
entry usually has no pre-known hash on first acquisition, unlike a dataset
manifest entry — `fetch` establishes one via the acquisition ladder and match
gate below, rather than verifying against one already recorded.

### Acquisition — the ladder and the match gate

`literature fetch <citekey>` walks a ladder: identity-derived rungs read the
anchor's own OpenAlex record (`best_oa_location`, every `locations[].pdf_url`,
then any `locations[].landing_page_url` that actually serves PDF bytes); if
none yield bytes, search-derived rungs try (a sibling-version title search, an
arXiv query, and an empty-by-default, config-driven `venue_resolvers` list).
Every search-derived candidate passes a **match gate** — title, first-author
family name, and year, compared against the registry entry — that returns
`accept`, `quarantine`, or `refuse`. **First-author family name is a hard
gate: no candidate is ever accepted or quarantined across an author
mismatch.** This is what lets the gate accept a genuine preprint/journal
sibling pair one year apart while refusing a same-topic, different-author
paper a loose title search would otherwise bind to the wrong citekey. See
ADR-0037 for the full rationale.

A `quarantine` verdict lands bytes + the candidate record on disk without
touching `references.json`; nothing is ever auto-promoted. Review it, then
`literature confirm <citekey> --sha256 <hash>` to accept it, or leave it and
work the `manual[]` bucket instead. `literature confirm <citekey> --file
<path>` adopts a hand-downloaded PDF — it **copies** the file (your original
stays put) and records an empty, non-redistributable license, since the tool
observed nothing about a file it didn't fetch itself.

## Composition

- **`hypothesis-exploration` / `paper-exploration`** consume `scout` rows as
  proposals; they apply the idea-shaping lenses (gap-spotting vs. problematization;
  feasibility × interest) — `scout` does not.
- **`hypothesis-testing`** reads `position --level hypothesis` verdicts into
  `strategy.md`. **`paper-synthesis`** reads `position --level paper` into
  `positioning.md` and the baseline list. **`thesis`** reads
  `position --level thesis` into the kappa's independent related-work chapter.
- **`defend`** (target `cited-work`) draws on this registry to check "does ref [12]
  actually support this sentence?" — the same surface-don't-adjudicate posture.
- **`digest`** grounds each paper it digests in this registry (a
  `references.json` entry + mirrored PDF) and writes back to the `triage.yml`
  row on completion — the reading step that precedes triage/positioning
  (`../digest/SKILL.md`).
- **Substrate**: shares the persistent-ID / mirror / fixity mechanism with
  `dataset`; both are front-ends over one substrate, not one shared file.

## Guardrails

- **Propose / surface, never adjudicate.** `scout` emits proposals; `position`
  emits precedent + a verdict recommendation. Novelty and what-to-pursue are human
  decisions recorded with sign-off.
- **Provenance is mandatory.** Every `scout` idea row carries the source-paper id
  + exact citing-context snippet. No orphan ideas.
- **PRISMA at every position level.** Every candidate gets an include/exclude
  reason logged (via triage `rationale`); this is the anti-cherry-picking record.
- **Anti-patterns → safeguards:** cherry-picking → PRISMA log + diverse seed set;
  author-by-author prose → concept matrix; overclaiming novelty → adversarial
  precedent search + explicit "closest prior work" + isolating ablation; weak
  baselines → matched tuning/splits, one strong per branch.
- **Keyless-first, degrade gracefully.** OpenAlex needs no key (send `mailto=`).
  Semantic Scholar's key is optional — fall back to OpenAlex-only if absent, at
  the cost of citation contexts/intents. scite.ai is out of scope for v1.
- **License gate is non-negotiable.** `fetch` never writes PDF bytes into this
  repository, automatically or behind a flag, on the strength of a mirror or a
  scraped license field — only a human, informed by `redistributable` + a
  permissive `license`, commits an in-repo copy.
- **Reproducibility.** Record the search date, API versions, and query filters in
  the run's provenance; the same anchors + filters should reproduce the set.

## Tooling

The CLI group **`defendable-science literature`** exposes nine commands, each
emitting JSON. **Ensure it before use** via
[`ensure-tooling`](../../resources/ensure-tooling.md) (`uv tool install
defendable-science`, git/TestPyPI fallbacks).

- **`resolve | cites | refs | enrich | neighbors`** — the citation-graph
  primitives (`defendable_science/literature/graph.py`), wrapping the
  OpenAlex + Semantic Scholar clients. Design:
  `../../docs/design/proposals/literature-citation-graph-client.md`.
- **`fetch | confirm | verify | mirror`** — the registry + acquisition layer
  (`defendable_science/literature/{registry,acquire}.py`): the CSL-JSON
  registry loader/patcher, the `triage.yml` sidecar reader, the acquisition
  ladder and match gate, and the mirror/verify wrappers described in
  [Registry](#registry--bib--triage-sidecar) above. Design:
  `../../docs/design/proposals/literature-asset-acquisition.md`, ADR-0037.

`fetch`/`verify`/`mirror` each take exactly one of a `citekey` or `--all`
(never both, never neither); `confirm` takes exactly one of `--sha256` or
`--file`. `fetch --disposition <value>` restricts `--all` to entries whose
`triage.yml` row carries that disposition.

**A generator this skill does not (yet) provide:** the PRISMA-style log and
concept-centric matrix described in §3/§Guardrails above are produced by
following the described procedure over the triage sidecar's `rationale` /
`role` fields by hand — there is no `literature` command that generates
either artifact. Filed as a follow-up; do not assume a CLI command exists for
them.

Package deps: `requests` + `pyyaml` (+ the substrate's rclone mirror, invoked
as a subprocess).

> **The endpoints the graph commands wrap** (for reference, or a keyless manual check):
> - Forward citations: `curl 'https://api.openalex.org/works?filter=cites:<WORKID>&mailto=<email>&per-page=200'`
>   (paginate via `cursor=*`). Backward: read `referenced_works` on the anchor's work record.
> - Contexts + SciCite intents + `isInfluential`:
>   `curl 'https://api.semanticscholar.org/graph/v1/paper/<id>/citations?fields=contexts,intents,isInfluential,title,year,venue,authors'`
>   (add the `x-api-key` header if a key is configured; omit and degrade to
>   OpenAlex-only otherwise — `cites` marks the result `degraded` when it does).
> - Recommendations (idea expansion):
>   `https://api.semanticscholar.org/recommendations/v1/papers/forpaper/<id>`.

## Commit attribution

When you commit artifacts produced by this skill, add these git trailers —
discovery + provenance (see [`../../resources/commit-attribution.md`](../../resources/commit-attribution.md)):

```
Generated-with: defendable-science (https://github.com/davorrunje/defendable-science)
DefendableScience-Skill: literature
```
