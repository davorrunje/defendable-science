---
name: research-init
description: Use when onboarding a repository onto the honest-scholar research workflow — either scaffolding a fresh repo (init) or backfilling an existing one that already has papers, datasets, benchmarks, and prior results (adopt). Drives any repo to the standard consumer layout so hypotheses, papers, literature, and datasets are tracked the same way everywhere.
---

# Research Init

Onboards a repository onto the `honest-scholar` workflow. One skill, **two modes** —
both drive the repo to the same consumer layout (see the meta-spec
[§5](../../docs/design/00-meta-spec.md) and the content layout in
[lifecycle §7](../../docs/design/01-lifecycle.md)). `adopt` is `init` **plus** an
inventory-and-map phase; it is the payoff for a sprawling, unsystematic research
folder — the reason this workflow exists.

The layout is **git-native plain text** (markdown, YAML, CSL-JSON): the repo is
the source of truth, external trackers are optional front-ends only
([ADR-0018](../../decisions/0018-git-native-source-of-truth.md)). The plugin
ships generic scaffolding; the consumer owns all content, config, and the
experiment-backend implementation.

## When to use

- **First time** a repository adopts the workflow — there is no `docs/research/`
  or `.honest-scholar/` yet.
- A repo already has research artifacts (reference PDFs, a bibliography, dataset
  files or download scripts, prior results, an existing benchmark/experiment
  harness) that are **not yet systematically recorded** — use `adopt`.
- Re-running is safe and additive: existing scaffolding is preserved, gaps are
  filled, nothing is overwritten without confirmation.

Do **not** use this to register individual items after onboarding — that is the
job of the capability skills' own verbs (see Composition). This skill only
scaffolds and, in `adopt`, proposes the initial mapping.

## Modes

| Mode | Repo state | What it does |
|---|---|---|
| `init` | greenfield | Scaffold the layout, empty registries, config, and templates. |
| `adopt` | brownfield | Everything `init` does, **then** inventory existing assets, propose mappings, and materialize them with per-item human confirmation. |

Pick `adopt` whenever prior research material exists; pick `init` for an empty
repo. Both leave the repo in the identical target layout — `adopt` simply arrives
with the registries already populated.

## What it scaffolds

Both modes create (idempotently) the consumer layout:

```
docs/research/
  papers.md                      # registry: paper-id → root + `backend:` binding
  <paper>/
    hypotheses/<YYYY-MM-DD-slug>/{hypothesis,strategy,design,plan,findings}.md
    backlog.md                   # hypothesis backlog for this paper
    paper/{pitch,positioning,outline,plan,ledger,decision}.md
    paper/sections/              # assembled manuscript sections
  portfolio-backlog.md           # paper-level backlog
  thesis/                        # OPTIONAL — only if this is a thesis repo
    kappa/                       # framing chapter (aims, narrative, contributions)
    aims.md                      # through-line + chapter↔paper map
    milestones.yml               # configurable program gates (candidacy, submission, defense)
  dashboard.md                   # GENERATED projection of status frontmatter — never hand-edited
  literature/
    references.json              # CSL-JSON — bibliographic facts (source of truth; ADR-0020)
    triage.yml                    # decision sidecar (role, disposition, rationale), keyed by id/DOI
datasets.yml                     # dataset registry (entries + checksums + tiers + license)
.honest-scholar/
  config.yml                     # rclone remote name, literature anchors, cache_dir, experiment-backend + engineering_backend bindings
  cache/                         # gitignored materialized data + HTTP cache (path from config.yml `cache_dir:`)
  rclone.conf.example            # committed template (remote name/type only)
  rclone.conf                    # gitignored (credentials)
  # keys.json is NOT scaffolded here — `honest-scholar keys` stores API keys
  # outside the repo by default (ADR-0032); see the note below.
```

Registries are created **empty but valid** (a parseable `papers.md`,
`references.json`, `datasets.yml`, `triage.yml`). Staged-doc scaffolding for each
paper comes from the shared templates in
[`resources/templates/`](../../resources/templates/); every hypothesis/paper/thesis
artifact carries the status frontmatter block that feeds `progress`.

`.honest-scholar/config.yml` records the five consumer bindings: the **rclone remote
name** for the private mirror, the **literature anchors** (seed works/authors the
`literature` capability ranks around), the **experiment-backend binding**
(which repo-local harness implements the run/evidence/tables/is-current
contract), the **engineering-backend binding** (`engineering_backend:` — the
`design`/`plan`/`implement` delegate the pipeline skills hand engineering off to;
ADR-0023), and the **cache directory** (`cache_dir:`, default `.honest-scholar/cache/`
— the CLI's dataset + HTTP caches always live under exactly this path;
[ADR-0031](../../decisions/0031-config-driven-cache-dir.md)). `.gitignore` is
updated to exclude the configured `cache_dir:` path, `.honest-scholar/rclone.conf`,
and (defense-in-depth) `.honest-scholar/keys.json`.

**API keys never enter the repo by default.** `honest-scholar keys set` (ADR-0029)
stores credentials at an XDG config path outside the repo's work tree —
`$XDG_CONFIG_HOME/honest-scholar/keys.json`, falling back to
`~/.config/honest-scholar/keys.json` — never at a path this skill scaffolds
(ADR-0032, honest-scholar#66). An author can opt into the legacy in-repo path
(`HONEST_SCHOLAR_KEYS_PATH=.honest-scholar/keys.json`), which is why the
`.gitignore` entry above still exists; `keys set` also warns if the resolved
store ever sits in a git work tree without being gitignored.

The `thesis/` tree is optional — scaffold it only when the repo is a
thesis-by-publication; a plain portfolio repo omits the top level.

## Adopt: backfill workflow

`adopt` runs the `init` scaffolding, then an **inventory → propose → confirm →
materialize** loop. The skill *proposes* mappings; the human *confirms every
material classification* — never silently guessed. The generic mapping rules
(domain-neutral; a monotonic-network repo is only one example consumer):

1. **Inventory.** Walk the repo for research-bearing assets: reference PDFs and
   any digests/notes, bibliography files, dataset files and download/prep
   scripts, prior results and experiment specs/notes, and any existing
   benchmark/experiment harness.

2. **Literature.** Reference PDFs + digests + any existing bibliography →
   `literature/references.json` (CSL-JSON) + `triage.yml`, with **roles tagged**
   (e.g. anchor / rival / prior-art / supporting). *Confirm each role* — the
   skill proposes from context, the human decides.
   *(Example: in a monotonic-network repo, the foundational paper is the anchor
   and later competing constructions are rivals.)*

3. **Datasets.** Dataset files and download/prep scripts → `datasets.yml`
   entries, computing **checksums**, inferring **source/license**, and assigning
   a **tier**. *License and tier are material classifications and must be
   human-confirmed* — never assume redistribution is permitted.

4. **Retroactive hypotheses.** Prior results, experiment specs, and informal
   notes → retroactive hypothesis docs (`hypotheses/<YYYY-MM-DD-slug>/`) with
   `findings.md` filled from the recorded evidence — "a detailed record per
   hypothesis" applied historically. *The human confirms which result maps to
   which hypothesis* and signs off each retroactive verdict (it is still a
   material decision).

5. **Experiment backend.** An existing benchmark/experiment harness → bound as
   the repo's experiment-backend **implementation** in `.honest-scholar/config.yml`
   (the plugin ships only the contract; the harness stays in the consumer).

Present proposals as a reviewable diff/table before writing. Anything the skill
cannot classify with confidence is surfaced as an open question, not decided.

## Composition

- **Delegates per-item registration to the capability skills' verbs** — it does
  not reimplement them. After scaffolding, populate via
  [`literature`](../literature/SKILL.md) (`scout` / `position`),
  [`dataset`](../dataset/SKILL.md) (`init/register/fetch/verify/mirror/audit/export`),
  and the pipeline skills
  ([`hypothesis-exploration`](../hypothesis-exploration/SKILL.md),
  [`hypothesis-testing`](../hypothesis-testing/SKILL.md),
  [`paper-exploration`](../paper-exploration/SKILL.md),
  [`paper-synthesis`](../paper-synthesis/SKILL.md)). In `adopt`, the mapping
  steps above call those same verbs so backfilled items enter through the normal
  front door.
- **Delegates all engineering to the bound engineering backend** (via the
  engineering-delegation contract) — design, planning, implementation, and test
  authoring for the experiment-backend harness are not this skill's job; it only
  *binds* the harness in config.
- **Regenerates** `dashboard.md` via `progress dashboard` once the registries
  hold content — never hand-edit it.

## Guardrails

- **Human confirms every material classification.** In `adopt`, licenses/tiers
  and result→hypothesis mappings are material and require explicit sign-off;
  propose, never presume ([ADR-0017](../../decisions/0017-research-init-one-skill.md),
  meta-spec agency principle §2.1).
- **Retroactive verdicts are still verdicts** — each backfilled `findings.md`
  needs a named human sign-off + date.
- **Git-native only.** Do not introduce an external tracker as the source of
  truth; the committed files are authoritative
  ([ADR-0018](../../decisions/0018-git-native-source-of-truth.md)).
- **Domain-neutral.** Scaffold and map from what the repo actually contains;
  bake in no field-specific assumptions.
- **Idempotent and non-destructive.** Never overwrite existing content without
  confirmation; re-running fills gaps only.
- **Do not commit** as part of this skill — leave the scaffolding staged for the
  author to review and commit ([ADR-0001](../../decisions/0001-separate-plugin-repo.md)
  frames the plugin↔consumer boundary this respects).

## Commit attribution

When you commit artifacts produced by this skill, add these git trailers —
discovery + provenance (see [`../../resources/commit-attribution.md`](../../resources/commit-attribution.md)):

```
Generated-with: honest-scholar (https://github.com/davorrunje/honest-scholar)
HonestScholar-Skill: research-init
```
