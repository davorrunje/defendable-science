---
name: research-init
description: Use when onboarding a repository onto the defendable-science research workflow — either scaffolding a fresh repo (init) or backfilling an existing one that already has papers, datasets, benchmarks, and prior results (adopt). Drives any repo to the standard consumer layout so hypotheses, papers, literature, and datasets are tracked the same way everywhere.
---

# Research Init

Onboards a repository onto the `defendable-science` workflow. One skill, **two modes** —
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
  or `.defendable-science/` yet.
- A repo already has research artifacts (reference PDFs, a bibliography, dataset
  files or download scripts, prior results, an existing benchmark/experiment
  harness) that are **not yet systematically recorded** — use `adopt`.
- Re-running is safe and additive: existing scaffolding is preserved, gaps are
  filled, nothing is overwritten.

Do **not** use this to register individual items after onboarding — that is the
job of the capability skills' own verbs (see Composition). This skill only
scaffolds and, in `adopt`, proposes the initial mapping.

## Modes

| Mode | Repo state | What it does |
|---|---|---|
| `init` | greenfield | Scaffold the layout: empty-but-valid registries, backlogs, and config. |
| `adopt` | brownfield | Everything `init` does, **plus** inventory existing assets, propose where they live (`layout:`) and how they map, and materialize with per-item human confirmation. |

Pick `adopt` whenever prior research material exists; pick `init` for an empty
repo. Both leave the repo readable by the same commands — but not necessarily
with the same tree. `init` writes the default layout. `adopt` may instead
**record where the repo's material already lives** in a `layout:` block, so the
existing tree stays put and the tooling follows it (see Adopt, step 2).

## What it scaffolds

Both modes scaffold by **calling the CLI**, not by writing files by hand. First
bootstrap the tooling ([`ensure-tooling`](../../resources/ensure-tooling.md)),
then:

```bash
defendable-science init              # add --thesis for a thesis-by-publication repo
defendable-science init --dry-run    # report what a real run would do, write nothing
```

`init` is **idempotent and non-destructive**: a file already present is reported
`exists` and left exactly as the author wrote it. There is deliberately no
`--force` — re-running fills gaps only. `.gitignore` is the single exception and
is merged **append-only**, so it is reported `merged` (never `created`), and
rules the repo already depends on survive. The report is JSON on stdout: one
entry per path considered, each `created` | `exists` | `merged`, plus a `counts`
object. A run that fails prints no report — a partial scaffold must never read as
a finished one.

Every **machine-read** file is rendered by the package that owns its shape —
`papers.md`, the portfolio backlog, `references.json`, `triage.yml`,
`datasets.yml`, `config.yml`, `rclone.conf.example`, `dashboard.md`, and with
`--thesis` the thesis `aims.md` stub, `milestones.yml` and `kappa/`. That is why
two `init` runs agree and why the files parse for every command that reads them.
Registries land **empty but valid**, never as prose to be fixed up later.

What `init` does *not* write: the per-paper tree. A paper's root, its empty
`backlog.md` and a tracked `paper/pitch.md` stub arrive when a portfolio-backlog
row is promoted (`defendable-science backlog promote <row-id> --level paper
--scaffold --backend <binding>`; `--level` defaults to `hypothesis`, and the
paper level requires the backend binding). The remaining staged documents —
`positioning.md`, `ledger.md`, `decision.md` — are written by `paper-synthesis`
at their own stages, from the prose skeletons in
[`resources/templates/`](../../resources/templates/). Every hypothesis / paper /
thesis artifact carries the status frontmatter block that feeds `progress`.

The default layout, for orientation (a repo may record a different one — see
Adopt, step 2):

```
docs/research/
  papers.md
  <paper>/
    hypotheses/<YYYY-MM-DD-slug>/{hypothesis,strategy,design,plan,findings}.md
    backlog.md
    paper/{pitch,positioning,outline,plan,ledger,decision}.md
    paper/sections/
  portfolio-backlog.md
  thesis/                        # OPTIONAL — only with --thesis
    kappa/
    aims.md
    milestones.yml
  dashboard.md
  literature/
    references.json
    triage.yml
datasets.yml
.defendable-science/
  config.yml
  cache/                         # gitignored (path from config.yml `cache_dir:`)
  rclone.conf.example            # committed template
  rclone.conf                    # gitignored (credentials)
  # keys.json is NOT scaffolded here — `defendable-science keys` stores API keys
  # outside the repo by default (ADR-0032); see the note below.
```

`.defendable-science/config.yml` records the consumer bindings, **every one of
them `null` until the author sets it** — never a `<placeholder>` string, which
would parse as a real binding: the **rclone remote name** for the private mirror,
the **literature anchors** (seed works/authors the `literature` capability ranks
around), the **experiment-backend binding** (`experiment_backend:` — which
repo-local harness implements the run/evidence/tables/is-current contract), the
**engineering-backend binding** (`engineering_backend:` — the
`design`/`plan`/`implement` delegate the pipeline skills hand engineering off to;
ADR-0023), and the **cache directory** (`cache_dir:`, default `.defendable-science/cache/`
— the CLI's dataset + HTTP caches always live under exactly this path;
[ADR-0031](../../decisions/0031-config-driven-cache-dir.md)). `init` also
gitignores the configured `cache_dir:` path, `.defendable-science/rclone.conf`,
and (defense-in-depth) `.defendable-science/keys.json`.

`dashboard.md` is scaffolded as a stub that says no generator has run yet, rather
than a plausible-looking projection of a repo with nothing in it. It is
regenerated by `progress`, never hand-edited.

**API keys never enter the repo by default.** `defendable-science keys set` (ADR-0029)
stores credentials at an XDG config path outside the repo's work tree —
`$XDG_CONFIG_HOME/defendable-science/keys.json`, falling back to
`~/.config/defendable-science/keys.json` — never at a path this skill scaffolds
(ADR-0032, defendable-science#66). An author can opt into the legacy in-repo path
(`DEFENDABLE_SCIENCE_KEYS_PATH=.defendable-science/keys.json`), which is why the
`.gitignore` entry above still exists; `keys set` also warns if the resolved
store ever sits in a git work tree without being gitignored.

The `thesis/` tree is optional — scaffold it only when the repo is a
thesis-by-publication; a plain portfolio repo omits the top level.

Finally, **verify the repo** rather than declaring it working:

```bash
defendable-science check
```

Report what it finds. `invalid` and `unreadable` findings mean the repo is not
yet usable — fix them before handing back. Each finding carries a remedy.
`gap` findings are honest incomplete states (an unsigned verdict, no bound
experiment backend) and are reported, not fixed: they are the author's
decisions to make.

## Adopt: backfill workflow

`adopt` is an **inventory → propose → confirm → materialize** loop around the
`init` scaffolding. Inventory comes first, because the layout question in step 2
decides where everything after it lands. The skill *proposes*; the human
*confirms every material classification* — never silently guessed. The generic
mapping rules (domain-neutral; a monotonic-network repo is only one example
consumer):

1. **Inventory.** Walk the repo for research-bearing assets: reference PDFs and
   any digests/notes, bibliography files, dataset files and download/prep
   scripts, prior results and experiment specs/notes, and any existing
   benchmark/experiment harness.

2. **Layout.** If the inventory finds papers, references or datasets outside the
   default tree, **propose a `layout:` block** for
   `.defendable-science/config.yml` instead of moving the author's files. Four
   keys, each optional and each a repo-relative path inside the work tree:
   `research_root`, `literature_dir`, `datasets_manifest`, `thesis_dir`. An
   omitted key keeps the default; an unknown key is an error, not a silent
   ignore. *The author confirms the block* — recording where material already
   lives is the proposal, and **relocating files to the default tree stays
   available as the author's choice**, no longer the only option.
   Sequencing, given that `init` renders `config.yml` itself and never rewrites
   an existing one: run `defendable-science init --dry-run` first — it writes
   nothing and reports every path it *would* touch. With no `layout:` block
   recorded yet, those are the **default** paths, so read them back as the
   proposal the block is about to override, not as a preview of where files will
   end up. Then run `init`, add the confirmed block to the `config.yml` it
   rendered, and run `init` once more so anything still missing lands in the
   recorded locations. Finally delete the empty registries the first run left
   behind **for the keys the block moved** — a key the block leaves at its
   default has its live file exactly where the first run put it.

3. **Literature.** Reference PDFs + digests + any existing bibliography →
   `literature/references.json` (CSL-JSON) + `triage.yml`, with **roles tagged**
   (e.g. anchor / rival / prior-art / supporting). *Confirm each role* — the
   skill proposes from context, the human decides.
   *(Example: in a monotonic-network repo, the foundational paper is the anchor
   and later competing constructions are rivals.)*

4. **Datasets.** Dataset files and download/prep scripts → `datasets.yml`
   entries, computing **checksums**, inferring **source/license**, and assigning
   a **tier**. *License and tier are material classifications and must be
   human-confirmed* — never assume redistribution is permitted.

5. **Retroactive hypotheses.** Prior results, experiment specs, and informal
   notes → retroactive hypothesis docs (`hypotheses/<YYYY-MM-DD-slug>/`) with
   `findings.md` filled from the recorded evidence — "a detailed record per
   hypothesis" applied historically. *The human confirms which result maps to
   which hypothesis* and signs off each retroactive verdict (it is still a
   material decision).

6. **Experiment backend.** An existing benchmark/experiment harness → bound as
   the repo's experiment-backend **implementation** under `experiment_backend:`
   in `.defendable-science/config.yml` (the plugin ships only the contract; the
   harness stays in the consumer).

Present proposals as a reviewable diff/table before writing. Anything the skill
cannot classify with confidence is surfaced as an open question, not decided.

Then, **verify the repo**:

```bash
defendable-science check
```

Report what it finds. `invalid` and `unreadable` findings mean the repo is not
yet usable — fix them before handing back. Each finding carries a remedy.
`gap` findings are honest incomplete states (an unsigned verdict, no bound
experiment backend) and are reported, not fixed: they are the author's
decisions to make.

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
- **Regenerates** `dashboard.md` via [`progress`](../progress/SKILL.md) once the
  registries hold content — never hand-edit it.

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
- **Idempotent and non-destructive.** `init` never overwrites existing content —
  re-running fills gaps only, and `.gitignore` is merged append-only. Nothing
  this skill does by hand may overwrite either.
- **Do not commit** as part of this skill — leave the scaffolding staged for the
  author to review and commit ([ADR-0001](../../decisions/0001-separate-plugin-repo.md)
  frames the plugin↔consumer boundary this respects).

## Commit attribution

When you commit artifacts produced by this skill, add these git trailers —
discovery + provenance (see [`../../resources/commit-attribution.md`](../../resources/commit-attribution.md)):

```
Generated-with: defendable-science (https://github.com/davorrunje/defendable-science)
DefendableScience-Skill: research-init
```
