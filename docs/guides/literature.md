# Literature: from a citation graph to PDFs you can defend

A task-oriented guide to the whole `literature` capability — mining the citation
graph, keeping the registry, and actually getting the PDFs onto disk with
byte-level provenance. The running example is a real one: a survey of monotonic
neural networks, in which 73 works were resolved into the registry and 40 were
proposed for inclusion.

If you have not met `defendable-science` yet, read the
[User Guide](../USER-GUIDE.md) first — this page assumes you know what a skill is
and what the agency principle asks of you.

## 1. Two kinds of instruction, and how to tell them apart

The `literature` capability is half assistant and half command-line tool, and
mixing the two up is the single most common way to get stuck.

- **`scout` and `position` are skill *modes*.** They are things you *ask the
  assistant for*, in prose. `scout` looks outward (mine who-cited-whom for
  leads); `position` looks inward (defend a committed claim against prior work).
  There is no `defendable-science literature scout` command and there never will
  be — these modes are judgement-heavy graph work plus writing, which is what the
  agent is for.
- **`defendable-science literature …` is a CLI.** Nine commands, each printing
  JSON: the graph primitives `resolve | cites | refs | enrich | neighbors`, and
  the asset verbs `fetch | confirm | verify | mirror`. These are what run in a
  terminal, and what the skill itself shells out to.

So that this page can never be misread, it uses exactly two conventions and
nothing in between:

> **Ask the assistant.** Anything you say to the agent appears in a quote block
> like this one, in plain language. You are not meant to type it into a shell.

```bash
# Anything in a shell block is a real command, verbatim.
defendable-science literature verify --all
```

The CLI is installed by the [`ensure-tooling`](../../resources/ensure-tooling.md)
bootstrap (`uv tool install defendable-science`), isolated from your project's own
environment. The skill runs it for you; you can also run it yourself, and the
guide shows the real invocation each time so you can.

## 2. The registry: two files, one join key

Everything the capability knows lives in two git-tracked files, joined by citekey
(or DOI). By default:

```text
docs/research/literature/references.json   # bibliographic facts — the source of truth
docs/research/literature/triage.yml        # your decisions about each paper
```

Both paths are configurable in `.defendable-science/config.yml`:

```yaml
literature:
  registry: docs/research/literature/references.json
  triage:   docs/research/literature/triage.yml
  mirror:   {remote: papers, base_path: literature}
  acquisition:
    max_bytes: 52428800      # 50 MiB
    venue_resolvers: []
```

Every key is optional. A missing `literature:` block means "all of the above
defaults".

**`references.json` is CSL-JSON, and it is the source of truth.** JSON, because
the skills append rows, join by key, and build comparison matrices
programmatically, and a `.bib` file is a miserable thing to do that to. **BibTeX
is a generated view** — export it on demand (pandoc, Zotero) when you build a
manuscript. Never hand-author the `.bib` and treat it as the truth; it will be
overwritten.

**`triage.yml` is your decision layer**, keyed by citekey, one mapping per paper:
`role` (anchor / rival / prior-art / support / contrast / neighbor),
`disposition` (`inbox → screened → interesting → acting → acted-on → dismissed`),
`rationale`, `priority`, `notes`, reviewer, date.

```yaml
sill1997monotonic:
  role: prior-art
  disposition: screened
  rationale: the original hint-based construction; the ancestor of the whole branch
```

The `rationale` field is doing double duty and it matters: across a screened set,
include/exclude reasons **are** the PRISMA log. That is the anti-cherry-picking
record — the thing that lets you show you did not quietly drop the three papers
that disagreed with you. Write the rationale even when the answer is obvious.

Two consequences of the registry being human-authored:

- The tools patch it **surgically**. `fetch` and `confirm` replace exactly one
  object on one entry and leave unknown keys and key order alone.
- `triage.yml` is stricter still: YAML comments cannot survive a round-trip
  through the YAML library, so a triage write **refuses with an explicit reason**
  rather than rewriting a commented file. Your PRISMA rationales are not worth
  losing to a convenience.

### The `custom.defendable-science` spine

A paper's PDF provenance — `pid`, `files[]`, `license`, `mirror`, `acquisition` —
lives in one namespaced object under the CSL item's `custom` field, never as
top-level item properties:

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
      "files": [{"path": "sha256/6b071e82…", "sha256": "sha256:6b071e82…",
                 "size": 1518143, "media_type": "application/pdf"}],
      "license": {"id": null, "observed": null, "source": null},
      "redistributable": false,
      "access": "gated",
      "acquisition": {"rung": "openalex-landing", "url": "https://papers.nips.cc/paper/1358-monotonic-networks.pdf",
                      "match": {"verdict": "identity"}, "fetched": "2026-08-27"}
    }
  }
}
```

Why `custom` and not top-level fields? Because the CSL-JSON input schema sets
`additionalProperties: false` on items, so a top-level `files` or `license` would
make your `references.json` schema-invalid, while `custom` is the schema's own
designated escape hatch and round-trips through Zotero and pandoc unchanged — see
[ADR-0037](../../decisions/0037-literature-asset-acquisition.md). You do not
hand-edit this object; `fetch` and `confirm` write it.

## 3. A survey, end to end

Seven steps. Steps 1–3 and 6–7 are conversations with the assistant; steps 4–5
are where the CLI earns its keep.

### Step 1 — seed anchors

A survey lives or dies on the diversity of its seed set: 3–6 anchors spanning
different communities and terminologies, so you do not inherit one subfield's
blind spot.

> **Ask the assistant.** Use `literature` in `position` mode at paper level.
> Here are five anchors spanning the lattice, hint-based, and certified-monotonic
> lines of work — resolve them and record them in the registry as `role: anchor`.

Under the hood that is `defendable-science literature resolve` per anchor. You can
check one yourself:

```bash
defendable-science literature resolve 10.1016/j.neunet.2025.108278
```

### Step 2 — snowball to saturation

Backward (references → foundations and precedent) and forward (citations → newer
competitors and SOTA), iterating until a pass turns up no new *method*.

> **Ask the assistant.** Snowball both directions from the anchors until
> saturation. Log every candidate you look at in `triage.yml` with an
> include/exclude rationale, even the ones you drop immediately.

The graph primitives beneath it, if you want to walk a step by hand:

```bash
defendable-science literature cites W2293093810
defendable-science literature refs  W2293093810
defendable-science literature enrich W2293093810 W4403706439
```

In the monotonicity run this produced **73 works resolved into
`references.json`**.

### Step 3 — triage, which is the PRISMA log

Screen each candidate to `screened` or `dismissed`, with a rationale. The run
ended with **40 works proposed for inclusion** out of the 73 — and, crucially, 33
recorded exclusions with reasons rather than 33 papers that silently never
existed.

> **Ask the assistant.** Walk the inbox with me. For each paper, propose a
> disposition and a one-line rationale; I will confirm or override.

The skill proposes; you dispose. Novelty and inclusion are material decisions, so
they carry your name.

### Step 4 — get the PDFs

Now the shell. Sweep exactly the set you screened in:

```bash
defendable-science literature fetch --all --disposition screened
```

`--disposition` takes any value from the triage state machine, so you can sweep
`screened` for the survey and `acting` for the papers you are actively reading.
Entries with no triage row are excluded when `--disposition` is given, and
included when it is not.

Dry-run first if you want to see which rung would land the bytes without
downloading anything:

```bash
defendable-science literature fetch sill1997monotonic --dry-run
```

Real output from that command, for the survey's oldest anchor — verbatim, all
thirteen keys of a report row:

```json
{
  "complete": true,
  "not_attempted": 0,
  "fetched": [
    {
      "citekey": "sill1997monotonic",
      "bucket": "fetched",
      "sha256": null,
      "rung": "openalex-landing",
      "url": "https://papers.nips.cc/paper/1358-monotonic-networks.pdf",
      "candidate": {
        "url": "https://papers.nips.cc/paper/1358-monotonic-networks.pdf",
        "rung": "openalex-landing",
        "title": "Monotonic Networks",
        "year": 1997,
        "first_author_family": "Sill",
        "openalex": "W2293093810",
        "license": null
      },
      "match": {
        "verdict": "identity",
        "title": null,
        "author": null,
        "year": null,
        "reason": null
      },
      "reason": null,
      "tried": [
        "openalex-landing"
      ],
      "landing_urls": [],
      "committable": false,
      "path": null,
      "license": null
    }
  ],
  "cached": [],
  "quarantined": [],
  "manual": [],
  "committable": [],
  "errors": []
}
```

Two things to read out of that. `rung: openalex-landing` means the PDF was not
where a metadata field said it would be — OpenAlex reported this 1997 paper as
closed access with no PDF URL, and the bytes were found by noticing that one of
its *landing page* URLs actually serves `%PDF-`. And `verdict: "identity"` means
no matching was needed, because the URL came out of the very OpenAlex record the
citekey already resolves to.

Run it for real and the checksum is computed from the accepted bytes and written
back:

```bash
defendable-science literature fetch sill1997monotonic
```

```json
"fetched": [{"citekey": "sill1997monotonic",
             "sha256": "6b071e825203d8abf9a3f2a0102650b53c2346bbf538c7896230f98ae15ed793",
             "rung": "openalex-landing",
             "path": ".defendable-science/cache/literature/sha256/6b071e825203d8abf9a3f2a0102650b53c2346bbf538c7896230f98ae15ed793"}]
```

(Abridged — every bucket row carries the full outcome shape. See §4.)

Run it again and the same entry comes back in `cached[]` instead: once a checksum
is recorded, `fetch` is a pure cache → mirror resolution and the acquisition
ladder does not run at all. Which also means `--refetch` is the only way to make
it try again — and if `--refetch` yields *different* bytes for an entry that
already has a checksum, it **refuses and reports the drift** rather than silently
rebinding your citekey to a new arXiv version. A paper's identity is what the
recorded bytes say it is.

### Step 5 — work the report buckets

`fetch --all` prints one report with six buckets, each row carrying its full
provenance. That is a lot of JSON to read at once, so the fastest way to see where
a sweep landed is to collapse each bucket to its citekeys:

```bash
defendable-science literature fetch --all --disposition screened \
  | jq 'with_entries(if (.value|type)=="array" then .value |= map(.citekey) else . end)'
```

Real output, over a five-entry slice of the survey's screened set, on a first run
(run it again and those three come back under `cached[]` instead):

```json
{
  "complete": true,
  "not_attempted": 0,
  "fetched": [
    "sill1997monotonic",
    "polo2025monokan",
    "kitouni2023expressive"
  ],
  "cached": [],
  "quarantined": [],
  "manual": [
    "daniels2010monotone"
  ],
  "committable": [
    "kitouni2023expressive"
  ],
  "errors": [
    "igel2023smooth"
  ]
}
```

Read left to right, that is: three PDFs acquired, one of them permissively
licensed and so also offered in `committable[]` (the same row, listed twice — the
buckets are not disjoint), one paywalled paper for your hands, and one entry the
tool could not even try because its registry row has no identifier. That command
**exits 1**, because `errors[]` is non-empty — a sweep with an error is not a
finished sweep, and no CI loop should read it as one.

§4 is the table of what each bucket means and what you do about it. The short
version: `cached` and `fetched` need nothing, `quarantined` and `manual` are your
worklists, `committable` is an offer, and `errors` is about the tooling or the
registry row, never a verdict on the paper.

### Step 6 — read, with the comprehension check

A PDF on disk is not a paper you have read.

> **Ask the assistant.** Digest `polo2025monokan` — I want the comprehension
> check, and write the outcome back to its `triage.yml` row.

[`digest`](../../skills/digest/SKILL.md) requires a real registry entry plus a
mirrored PDF, never a bare URL, which is exactly what step 4 produced. It then
examines *you* on the paper and records the result. Note what it can and cannot
do: it verifies you understood the bytes you were handed. It has no way to know
whether those bytes are the right paper — which is why §6 matters.

### Step 7 — the concept matrix

> **Ask the assistant.** Build the concept-centric matrix over the included set:
> rows are methods, columns are the attributes our delta turns on. Then derive the
> section spine from the column clusters.

Concept-centric, never author-by-author — "Smith et al. did X, then Jones et al.
did Y" is a reading list, not a synthesis. Be aware that the matrix and the PRISMA
log are produced by the assistant following the procedure over your triage fields;
there is **no** CLI command that generates either artifact, and you should not go
looking for one.

## 4. The six buckets of a fetch report

| bucket | what it means | what you do |
|---|---|---|
| `fetched` | bytes acquired this run, hashed, cached, mirrored if a mirror is configured, and recorded on the entry | nothing |
| `cached` | the entry already had a checksum and the bytes resolved from the cache or the mirror | nothing |
| `quarantined` | a search-derived candidate was *plausible but not certain*. Bytes are on disk; `references.json` is untouched | look at the PDF, then `confirm --sha256 <hash>` to accept it — or ignore it and treat the entry as `manual` |
| `manual` | the ladder ran to the end **unblocked** and nothing served PDF bytes — every rung was consulted, and any link that failed did so with a `404`/`410`, i.e. the host said "there is nothing here". The row carries `landing_urls[]` so there is somewhere to click, and `failures[]` naming the dead links | download it by hand, then `confirm --file <path>` |
| `committable` | the observed license is on the shipped permissive allowlist, so you *may* keep an in-repo copy | copy the blob into the repo yourself, if you want to. Nothing is copied for you |
| `errors` | a tooling failure — a rate limit, a transport error (on metadata *or* on a PDF download), an unresolvable identifier, a conflicting request. **Not** a statement about the paper. A ladder that produced no bytes but was *blocked* on the way — a `403` from a CDN, a `5xx`, a dropped connection, a body over `max_bytes` — lands here rather than in `manual`, with `failures[]` naming each URL and its cause | fix or retry. Never treat this as "no PDF exists" |

Four properties of the report worth knowing before you script against it:

- **The buckets are not disjoint.** A permissively-licensed paper appears in
  `fetched[]` *and* in `committable[]` — two equal copies of the same row, one in
  each list, rather than one row cross-referenced from two places.
- **A row that came from an attempt carries the full outcome shape** — fourteen
  keys — not a per-bucket projection. A `fetched` row can legitimately carry a
  `reason`: the bytes landed and verified in the cache but the *mirror* write then
  failed. Projecting that row down to `{citekey, sha256, rung, url}` would hide a
  partial failure, which is the one thing this tool must not do.
- **`errors[]` has two row shapes, and this is the one place the uniformity above
  does not hold.** An entry the tool actually tried carries the full shape with
  its message under `error`:

  ```json
  {"citekey": "igel2023smooth", "bucket": "errors", "sha256": null, "rung": null,
   "url": null, "candidate": null, "match": null, "tried": [], "failures": [],
   "landing_urls": [], "committable": false, "path": null, "license": null,
   "error": "no DOI and no recorded identifier on the entry — nothing to resolve; add a 'DOI' field to the registry entry first"}
  ```

  But three failures happen *before* any attempt exists to describe — an unknown
  citekey, a citekey you named explicitly that `--disposition` would have excluded,
  and the rate-limit abort — and those are synthesized as a bare pair:

  ```json
  {"citekey": "nosuchkey2020", "error": "no entry 'nosuchkey2020' in the registry"}
  ```

  Both spell the message `error` rather than `reason`, so you never have to check
  two keys for the same information. But if you read `.bucket` or `.tried` off an
  `errors[]` row, guard for their absence.
- **`complete` and `not_attempted` are the honesty fields.** A throttle aborts
  the sweep with `complete: false` and a count of entries never attempted, rather
  than reporting the remaining papers as `manual`. That holds wherever the
  throttle came from: a `429` from OpenAlex, and equally a `429` — or a `503`
  carrying `Retry-After` — from the *PDF host*, which is what an unattended
  50-paper sweep against arXiv actually hits. Being rate-limited is
  not information about a paper, and telling you to go download 30 PDFs by hand
  because a server said "slow down" would be a lie. A non-empty `errors[]` or
  `complete: false` also makes the command exit non-zero, so no CI loop reads a
  half-swept registry as a finished one.

### Working the `manual` bucket

A real `manual` row, for a paywalled 2010 journal paper in the survey's set:

```json
{
  "citekey": "daniels2010monotone",
  "bucket": "manual",
  "reason": "the acquisition ladder is exhausted — every rung was consulted and none served PDF bytes",
  "tried": [],
  "failures": [],
  "landing_urls": [
    "https://doi.org/10.1109/tnn.2010.2044803",
    "https://pubmed.ncbi.nlm.nih.gov/20371402",
    "https://pure.eur.nl/en/publications/3aceccfc-62ce-438f-82fb-72fb024ea81c",
    "http://hdl.handle.net/1765/76536",
    "http://hdl.handle.net/2066/83870"
  ]
}
```

Click a landing URL, get the PDF through your institutional access, then adopt it:

```bash
defendable-science literature confirm daniels2010monotone --file ~/Downloads/daniels-2010-monotone.pdf
```

What it prints. Every value below is the real shape of an adoption outcome, with
one deliberate exception: the checksum is written as a placeholder, because this
paper's PDF is paywalled and we cannot hand you bytes to reproduce it from. Every
other hash on this page is the true hash of bytes you can re-fetch yourself, and
printing some other paper's checksum here would quietly break that.

```json
{
  "citekey": "daniels2010monotone",
  "bucket": "fetched",
  "sha256": "<sha256 of the file you supplied>",
  "rung": "manual",
  "url": null,
  "candidate": null,
  "match": {"verdict": "identity", "title": null, "author": null, "year": null, "reason": null},
  "reason": null,
  "tried": [],
  "failures": [],
  "landing_urls": [],
  "committable": false,
  "path": ".defendable-science/cache/literature/sha256/<that same sha256>",
  "license": null
}
```

Three details of adoption, each deliberate. It **copies** — your file stays where
it was; a tool you pointed at your downloads folder must not make things vanish
from it. It records `rung: manual` so the audit trail says a human supplied these
bytes. And it records an **empty license**, hence `committable: false`: the tool
observed nothing about rights on bytes it did not fetch, and silence is not a
grant.

### Working the `quarantined` bucket

Quarantined bytes land at
`.defendable-science/cache/literature/quarantine/<citekey>/<sha256>.pdf`, beside a
`<sha256>.json` holding the candidate record, the per-axis match verdict, the URL
and the rung. **Nothing is written to `references.json`.** Open the PDF, satisfy
yourself it is the paper the citekey names, then:

```bash
defendable-science literature confirm sill1997monotonic --sha256 <hash-from-the-report>
```

There is no "promote everything in quarantine" convenience and nothing is ever
auto-promoted. That is the whole point of the bucket: it is the set of cases where
the machine's confidence ran out and a human's has to take over.

## 5. Licenses in practice

The rule is short and it will surprise you the first time: **an absent license
means not redistributable, and most papers have no license field at all.** In the
run behind this feature, 14 of 50 works carried an explicit license; the other 36
carried none.

What follows from that:

- **`fetch` never writes PDF bytes into your repository.** Not automatically, not
  behind a flag. It writes the content-addressed cache, pushes to your mirror if
  one is configured, records what it observed, and *reports* what would be
  committable. The cache and the mirror hold the bytes; the repository does not.
  `files[].path` is therefore always a content-addressed blob path, never a repo
  path.
- **`license` records an observation, not a right**: `{id, observed, source}` —
  the identifier as reported, verbatim, plus which rung reported it. An
  unrecognized string such as `all-rights-reserved` is preserved as observed and
  stays non-redistributable.
- **`redistributable` is `true` only for an SPDX id on a shipped permissive
  allowlist** — `cc0-1.0`, `cc-by` and its 3.0/4.0 forms, `cc-by-sa` and its
  variants, `mit`, `apache-2.0`, `bsd-2-clause`, `bsd-3-clause`. There is no
  config override, deliberately: whether you may republish someone's paper is a
  license-compliance decision, and making it configurable would be inviting you to
  configure your way into an infringement.

An explicit license is not the same as a permissive one. The survey's MonoKAN
entry acquired cleanly with `license: "cc-by-nc-nd"` — and `committable: false`,
because a no-derivatives clause is not a grant for an in-repo copy:

```json
{
  "citekey": "polo2025monokan",
  "bucket": "fetched",
  "rung": "sibling-version",
  "url": "https://arxiv.org/pdf/2409.11078",
  "match": {"verdict": "accept", "title": "exact", "author": "exact", "year": "within-1", "reason": null},
  "committable": false,
  "license": "cc-by-nc-nd"
}
```

Compare a genuinely permissive one, which shows up in `committable[]` as an offer
you may take or leave:

```json
{
  "citekey": "kitouni2023expressive",
  "bucket": "fetched",
  "rung": "openalex-best",
  "url": "https://arxiv.org/pdf/2307.07512",
  "committable": true,
  "license": "cc-by"
}
```

If you want that PDF in the repo, copy it out of the cache yourself and commit it.
The plugin does not add bytes to your git history on the strength of a license
field it scraped off an API.

## 6. Why a refusal is a feature

Sooner or later `fetch` will tell you it found something and refused it, and your
instinct will be to look for the flag that turns that off. There isn't one. Here
is the case that put the gate there.

The survey needed Sill's *Monotonic Networks* (NIPS 1997). An arXiv title search
for "Monotonic Networks" returned **arXiv:2306.01147** — Christian Igel's *Smooth
Min-Max Monotonic Networks*, 2023. A title matched. Different author, twenty-six
years later, different paper entirely.

Consider what binding that PDF to `sill1997monotonic` would have cost. You would
read Igel's 2023 paper believing it was Sill's 1997 one. You would cite it as
Sill 1997 in your related-work section. And `digest`'s comprehension check would
*pass*, because it verifies that you understood the bytes you were handed — it has
no independent notion of which paper those bytes should have been. A wrong PDF
bound to a citekey is strictly worse than no PDF: no PDF is a gap you can see, and
a wrong PDF is a gap that looks like completed work all the way through your
bibliography.

So the tool refuses. Every search-derived candidate is compared against the
registry entry on three axes — normalized title, first-author family name, and
year — and the verdict is one of `accept`, `quarantine`, or `refuse`. For the Igel
candidate:

```json
{
  "verdict": "refuse",
  "title": "mismatch",
  "author": "mismatch",
  "year": "mismatch",
  "reason": "first author 'Igel' does not match 'Sill' — a different paper, not a version"
}
```

Three independent refusals, and the author axis is a **hard gate**: no candidate is
ever accepted or quarantined across a first-author mismatch, however well the
title and year line up. That single rule is what lets the same gate be generous
elsewhere — the MonoKAN case in §5 was accepted automatically across a one-year
preprint/journal gap and a capitalization difference, because the author matched
exactly.

The gate is load-bearing rather than decorative, and it is worth knowing why.
`dataset fetch` verifies bytes against a checksum it already has. A paper on first
acquisition has no such anchor — the checksum is *established* from whatever bytes
are accepted. The gate is standing exactly where `dataset` has a pre-known hash.
Disabling it would not be a convenience flag; it would remove the only thing
between a loose title search and your bibliography.

Two more things the gate does that are easy to misread as bugs:

- **It refuses on thin metadata.** If either side is missing a title, an author or
  a year, a search-derived candidate is refused with `insufficient metadata to
  verify a search-derived candidate (title, year and first author are all
  required on both sides)` — never accepted on a title match alone. Fill in the
  registry entry and try again.
- **It refuses front-extensions.** A candidate that *prepends* words — `"GPT-3:
  Language Models are Few-Shot Learners"` against a registry title of `"Language
  Models are Few-Shot Learners"` — refuses, where a subtitle *appended* to the
  registry title is admitted. That is real friction, and the deliberate trade:
  the entry lands in `manual[]` with its landing URLs and you adopt the PDF with
  `confirm --file`, having looked at it.

Which is the shape of the escape hatch generally. `confirm --file` is how you
overrule the tool, and it requires a human to open the PDF and see what it is.
That is not an obstacle to route around; it is the only sound way to bind bytes
the machine could not verify.

## 7. Checking what you have: `verify` and `mirror`

`verify` is offline. It never downloads — it re-hashes the bytes on disk against
the checksums the registry records:

```bash
defendable-science literature verify --all
```

```json
[
  {"citekey": "sill1997monotonic", "ok": true,
   "verified": ["sha256/6b071e825203d8abf9a3f2a0102650b53c2346bbf538c7896230f98ae15ed793"],
   "missing": [], "corrupt": []},
  {"citekey": "igel2023smooth", "ok": false, "verified": [], "corrupt": [],
   "missing": ["no asset recorded for this entry — nothing has been fetched yet"],
   "note": "no asset recorded for this entry — nothing has been fetched yet"}
]
```

An entry nothing has been fetched for is reported `missing` with an explicit
`note`, and is **never** `ok`. An unfetched paper must not read as verified.
`verify` exits non-zero if any report is not `ok`, so the second entry above makes
the whole command exit 1.

**One output to be careful with.** On a registry with no entries, `verify --all`
prints a bare empty array and exits 0:

```bash
defendable-science literature verify --all
```

```json
[]
```

That is *not* a clean bill of health. It means the tool found nothing to check —
most often because `literature.registry` points somewhere other than where your
bibliography actually is, or because the bibliography exists but nothing has been
fetched into it yet. Exit 0 here says "no failures", not "all verified". If you
expected 40 papers and got `[]`, check the path before you believe it.

`mirror` pushes recorded blobs to the configured remote, or probes with `--check`:

```bash
defendable-science literature mirror --all --check
```

It re-hashes a local blob before pushing, and reports a mismatch as `corrupt`
rather than `missing`, because your next move differs: investigate the local copy
(probably `fetch --refetch`) rather than simply retrying the push. With no
`literature.mirror` configured it says so and exits 1:

```text
no 'literature.mirror' configured in .defendable-science/config.yml
```

## 8. Quick reference

Every one of `fetch`, `verify`, `mirror` takes **exactly one** of a citekey or
`--all` — neither is an error, both is an error. `confirm` takes **exactly one**
of `--sha256` or `--file`.

| command | what it does |
|---|---|
| `defendable-science literature resolve ID` | resolve a DOI / arXiv id / OpenAlex or S2 id to a canonical work |
| `defendable-science literature cites ID` | forward citations |
| `defendable-science literature refs ID` | backward references |
| `defendable-science literature enrich ID…` | metadata bundle, with S2 citation contexts and intents |
| `defendable-science literature neighbors ID` | co-citation / bibliographic-coupling neighbours |
| `defendable-science literature fetch CITEKEY` | walk the ladder for one entry |
| `defendable-science literature fetch --all --disposition screened` | sweep a triaged set |
| `defendable-science literature fetch CITEKEY --dry-run` | which rung would land, writing nothing |
| `defendable-science literature fetch CITEKEY --refetch` | re-run the ladder for an acquired entry; drift refuses |
| `defendable-science literature confirm CITEKEY --sha256 HASH` | promote a reviewed quarantined candidate |
| `defendable-science literature confirm CITEKEY --file PATH` | adopt a hand-downloaded PDF (copied, not moved) |
| `defendable-science literature verify --all` | offline re-hash of everything recorded |
| `defendable-science literature mirror --all [--check]` | push recorded blobs to the mirror, or probe |

And the two things you ask for rather than type:

> **Ask the assistant.** Scout the citation graph outward from our anchors for
> research leads (`scout` mode) — or, when the claim is already committed,
> position it against prior work and tell me what a reviewer would say is already
> known (`position` mode).

## Where to go next

- [`skills/literature/SKILL.md`](../../skills/literature/SKILL.md) — the
  capability in the plugin's own words, including the `scout` / `position`
  procedures step by step.
- [`skills/digest/SKILL.md`](../../skills/digest/SKILL.md) — the verified-reading
  step that consumes what `fetch` acquired.
- [ADR-0037](../../decisions/0037-literature-asset-acquisition.md) — the spine
  under `custom`, the three-way match gate, and the alternatives that were
  rejected.
- [`docs/design/04-substrate-and-contract.md`](../design/04-substrate-and-contract.md)
  — the shared cache → mirror → source substrate that `literature` and `dataset`
  are both front-ends over.
