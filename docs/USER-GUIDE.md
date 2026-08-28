<p align="center">
  <img src="../assets/wordmark-banner.svg" alt="Defendable Science" width="640">
</p>

<!-- defendable-science user guide -->

# User Guide

A hands-on guide for a researcher meeting `defendable-science` for the first time.
It walks you from install to a signed finding to a submitted paper, using one
running example throughout, and hands off to a **per-capability guide** whenever
you need the depth.

Read this page front to back once. After that, the guides are where the work
happens:

| Guide | When you need it |
|---|---|
| [Literature](guides/literature.md) | mining the citation graph, the registry, getting PDFs with byte-level provenance |
| [Datasets](guides/dataset.md) | registering data, tiers and licenses, the resolution chain, the mirror |
| [Experiment backend](guides/experiment-backend.md) | the one part you implement; how a run becomes citable evidence |
| [`defend`](guides/defend.md) | the examination before every sign-off; targets, personas, what gets recorded |
| [`progress`](guides/progress.md) | coverage and blockers, the dashboard, and why there is no score |
| [API keys](guides/keys.md) | what each key buys and where credentials are kept |

**Two kinds of instruction appear throughout, and mixing them up is the fastest
way to get stuck.** A shell block is a real command you type:

```bash
defendable-science dataset fetch imagenet-c
```

A quote block is something you *ask the assistant*, in prose — a skill mode, not a
command:

> **Ask the assistant.** Scout the citation graph for research leads at hypothesis
> level (`literature` in `scout` mode).

Most of `defendable-science` is the second kind. For the *why* behind the design,
read [`README.md`](../README.md) and the specs under [`docs/design/`](design/);
this guide is the *how*.

## 1. What Defendable Science is (and the two rules it runs on)

`defendable-science` helps you keep research honest — **especially now that AI is in the
loop**. It is a Claude Code plugin for the **scientific** side of research — idea →
literature → hypothesis → test → publish-decision → paper → (optional) thesis. It
delegates the *engineering* (design, plans, code) to the bound **engineering
backend** via the engineering-delegation contract; `defendable-science` calls out to that
backend for all of that rather than reimplementing it.

To be clear up front: Defendable Science does **not** certify that your work is honest —
there is no seal of honesty. It gives you the *mechanics* to do honest work and to
disclose truthfully what you and the AI each did; readers judge the result.

Honesty here is mechanical, not a slogan. Everything you do sits under two rules.
They are not decoration — they change how the skills behave at every step:

1. **Agency — you decide and sign off.** The skills draft, keep the accounts, and
   advise like a colleague. They never make a *material* scientific decision for
   you: whether a hypothesis is confirmed or refuted, whether a result is real,
   whether a paper is worth publishing, whether a thesis is defensible. Each of
   those is recorded in the artifact with a **named human sign-off + date**. You
   cannot "run" Defendable Science to produce a paper — you drive it. In practice: expect the
   skill to stop at every judgement point and ask you. *So the science is honestly
   yours.*

2. **Understanding — the `defend` skill verifies and teaches.** Before any material decision,
   the [`defend`](../skills/defend/SKILL.md) skill probes whether you can actually
   defend the claim, the cited work, and the method — Socratically, one question
   at a time. When it finds a gap it *teaches* (source-grounded), then re-asks. It
   never grades the substance of your novel claim; it makes sure you understand
   what you are signing. In practice: expect to be asked "why this method?" and
   "what would falsify this?" before you sign anything. *So "I understand my own
   paper" is true, not assumed.*

Around these two rules sits the rest of the honesty kit, all covered below: the
**rigor kit** against cargo-cult method (§4b), **provenance** so evidence is honest
— every number traces to a run-ref (§4d), **anti-Goodhart** metrics with no
productivity score to game (§7), and **file-drawer + disclosure** discipline —
dropped ideas are retired not deleted (§4a), and AI use is disclosed truthfully
(§5a).

Between them sits the **firewall**: exploration *proposes* candidates, resolution
*disposes* (tests to a verdict), synthesis *reports*. No single skill both
proposes a claim and adjudicates it.

## 2. Install

`defendable-science` is distributed as a Claude Code plugin; its repo is its own marketplace.

```
/plugin marketplace add davorrunje/defendable-science
/plugin install defendable-science@defendable-science
```

To enable it for a whole project (so collaborators get it on trust), add to the
consuming repo's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "defendable-science": { "source": { "source": "github", "repo": "davorrunje/defendable-science" } }
  },
  "enabledPlugins": { "defendable-science@defendable-science": true }
}
```

Commit that file and every collaborator gets the same skills auto-enabled. To pin
a fixed release, add `"ref": "v0.2.0"` inside the marketplace `source`; omit it to
track the plugin's `main`. Skills are
invoked by name (`research-init`, `hypothesis-testing`, …) in your Claude Code
session.

## 3. First-time setup: `research-init`

Onboard your repo once with [`research-init`](../skills/research-init/SKILL.md).
It has **two modes**, both landing the repo in the same layout:

- **`init`** — a greenfield repo with no research artifacts yet.
- **`adopt`** — an existing repo that already has reference PDFs, a bibliography,
  dataset files or download scripts, and prior results scattered around. `adopt`
  runs `init`, then inventories those assets and proposes how to map them in —
  you confirm every material call (licenses, dataset tiers, which old result maps
  to which hypothesis). This is the payoff for a sprawling, unsystematic folder.

```
research-init init          # new repo
research-init adopt         # backfill an existing one
```

Both scaffold the **consumer layout** (git-native plain text — markdown, YAML,
CSL-JSON; the repo is the source of truth):

```
docs/research/
  papers.md                 # registry: paper-id → root + experiment-backend binding
  <paper>/
    hypotheses/<YYYY-MM-DD-slug>/{hypothesis,strategy,design,plan,findings}.md
    backlog.md              # this paper's hypothesis backlog
    paper/{pitch,positioning,outline,ledger,decision}.md + sections/
  portfolio-backlog.md      # paper-level backlog
  thesis/                   # OPTIONAL — only for a thesis repo
  dashboard.md              # GENERATED from status frontmatter — never hand-edit
  literature/
    references.json         # CSL-JSON bibliography (source of truth)
    triage.yml              # decision sidecar: role, disposition, rationale
datasets.yml                # dataset registry (entries + checksums + tiers + license)
.defendable-science/
  config.yml                # rclone remote, literature anchors, experiment-backend binding
  rclone.conf.example       # committed template; real rclone.conf is gitignored
```

Registries are created **empty but valid**. `research-init` does not commit — it
leaves the scaffolding staged for you to review. It is idempotent: re-running
fills gaps, never overwrites. After onboarding, you register individual items
with the capability skills' own verbs, not with `research-init`.

## 4. The core loop — a worked walkthrough

Running example: a project studying **whether a learned data-augmentation policy
improves out-of-distribution accuracy** for an image classifier. We will take one
hypothesis from raw idea to a signed verdict, then roll it into a paper.

### 4a. Explore hypotheses (propose)

[`hypothesis-exploration`](../skills/hypothesis-exploration/SKILL.md) runs an
idea pipeline into the paper's `backlog.md`. Its verbs form a small state machine:
`park → generate → rank → promote | drop`.

> **Ask the assistant.** Park this idea in the backlog: "learned aug policy may
> help OOD but hurt in-distribution". Then generate candidates from the literature
> scout and the EDA, rank them by EIG and feasibility × interest, and flag any
> framing problems. I will pick what to promote.

The row-level mechanics are a real CLI the skill shells out to, so you can also
drive the table yourself:

```bash
defendable-science backlog park "learned aug policy may help OOD but hurt in-distribution" \
    --provenance "own" --backlog docs/research/<paper>/backlog.md
defendable-science backlog rank <id> --EIG high --feas med --interest high \
    --backlog docs/research/<paper>/backlog.md
defendable-science backlog promote <id> --scaffold --paper-root docs/research/<paper> \
    --backlog docs/research/<paper>/backlog.md
```

Every backlog row carries **mandatory provenance** (where the idea came from —
a scouted citing-context snippet, an EDA observation, or `own`). A hypothesis
must be a *falsifiable sentence*, not a topic: "a learned augmentation policy
raises OOD top-1 accuracy by ≥2 points at equal in-distribution accuracy." `rank`
advises; it never auto-selects. `drop` records a reason and retires the row — it
never deletes it (file-drawer discipline). This skill **only proposes**; you
promote.

### 4b. Test one hypothesis (dispose)

`promote` hands the claim to
[`hypothesis-testing`](../skills/hypothesis-testing/SKILL.md), the resolve skill.
Its governing rule is **science before engineering**: you settle *how* you would
confirm or refute the claim before any code is designed. It drives four staged
documents, in order, under `docs/research/<paper>/hypotheses/<slug>/`:

1. **`hypothesis.md`** — the claim, why it matters, what confirming vs. refuting
   looks like. No method yet.
2. **`strategy.md`** — *the science.* The decisive comparison and decision rule;
   at least one **rival explanation** plus a test that separates it; the
   **rigor-kit** choices (confirmatory-vs-exploratory tag, power/MDE, severity,
   TOST bounds if the claim is a null). It calls `literature position` for an
   adversarial "would a reviewer say this is already known?" check, and declares
   the datasets it needs. **`defend` fires here** on the strategy — expect to
   defend your assumptions and falsifiers before moving on.
3. **`design.md` / `plan.md`** — *the engineering, delegated to the bound
   engineering backend* (its `design` → `plan` capabilities). Defendable Science stores the
   results here but does not design experiments or write code itself. Executing
   the plan produces the runs.
4. **`findings.md`** — *the verdict:* `confirmed | refuted | inconclusive`, tied
   to the strategy's decision rule. Results are cited as backend **run-refs**,
   never hand-typed numbers. Before you sign, the **`defend` guardrail fires**: it
   surfaces any gap; you may override, but the override is logged.

The verdict is a material decision — it is real only once `signed-off-by` +
`signed-off-date` are set. And **refuted is done, not failed**: learning the
claim is false is successful science.

### 4c. Where literature and datasets plug in

- [`literature`](../skills/literature/SKILL.md) has two modes over one
  citation-graph engine (OpenAlex + Semantic Scholar). `scout` looks outward
  (mines who-cited-whom for leads → ranked backlog rows with provenance);
  `position` looks inward (defends a committed claim → an adversarial precedent
  verdict at hypothesis level, a full related-works synthesis with a PRISMA-style
  audit log and baseline list at paper level). A `--level` parameter tunes depth.
  It keeps the `references.json` + `triage.yml` registry; it **proposes and
  surfaces, never adjudicates novelty**.

  > **Ask the assistant.** Scout the citation graph for research leads at
  > hypothesis level (`literature` in `scout` mode) — feeds
  > `hypothesis-exploration`. Or, once a claim is committed, position it
  > against prior work at hypothesis level (`position` mode) — feeds
  > `strategy.md`. There is no `defendable-science literature scout` or
  > `literature position` command; these are skill modes you ask the
  > assistant for.

  **Full guide: [Literature](guides/literature.md)** — a survey end to end, the
  six buckets of a fetch report, licenses in practice, and why a refusal is a
  feature.

- [`dataset`](../skills/dataset/SKILL.md) manages the data your strategy declares,
  over `datasets.yml`. Each dataset gets a storage **tier** (A committed / B
  auto-retrievable / C gated), a **SHA-256 fingerprint** (authoritative; a
  mismatch is a hard fail), and a Gebru **datasheet**. You confirm tier and
  license — the skill proposes.

  > **Ask the assistant.** Register `imagenet-c` in the dataset manifest —
  > propose a tier and license for me to confirm. `register` is a `dataset`
  > skill mode, not a CLI verb.

  ```bash
  defendable-science dataset fetch imagenet-c    # materialize + verify against the registry
  ```

  **Full guide: [Datasets](guides/dataset.md)** — tiers as a license question, the
  four-step resolution chain, the mirror as link-rot insurance, and what `audit`
  checks beyond fixity.

### 4d. How runs become evidence — the experiment-backend contract

Defendable Science defines a **contract**; your repo supplies the implementation (bound in
`.defendable-science/config.yml`, named per paper in `papers.md`). The contract has four
capabilities:

| Capability | What it gives you |
|---|---|
| `run` | execute/resume an experiment for a config → a **run-ref** (the citable unit of evidence) |
| `evidence` | results for a run-ref + a provenance stamp (config hash, code, dataset `id+version+sha256`, hardware) |
| `tables` | render result blocks into your docs — the **only** writer of numbers |
| `is-current` | is a run-ref's evidence still valid, or stale (with reasons)? |

Because every number resolves to an exact `id+version+sha256`, results are
reproducible and staleness is honest. You never hand-copy a number: `findings.md`
cites run-refs, and `tables` writes the figures. `is-current` reports staleness;
**you** decide whether to re-run.

**Full guide: [Experiment backend](guides/experiment-backend.md)** — what a
minimal implementation looks like, how to bind one, and why the plugin ships
none.

## 5. Papers: from candidate to publish decision

The paper level mirrors the hypothesis level one step up.

- [`paper-exploration`](../skills/paper-exploration/SKILL.md) proposes *candidate
  papers* into `portfolio-backlog.md` — via generation lenses (mechanism-transfer,
  limitation-driven, result-driven) and optionally `literature scout --level
  paper`. Same verbs (`park/generate/rank/promote/drop`), same firewall.
  `promote` registers the paper in `papers.md` (assigning its `paper-id` and
  experiment-backend binding) and hands it to synthesis.

  > **Ask the assistant.** Generate candidate papers from the resolved
  > hypotheses (`paper-exploration` in `generate` mode) across all three lenses,
  > and rank them. I will pick.

  ```bash
  # The registry/scaffold half is a real CLI:
  defendable-science backlog promote aug-policy-robustness \
      --backlog docs/research/portfolio-backlog.md --level paper --scaffold \
      --research-root docs/research --backend bench
  ```

- [`paper-synthesis`](../skills/paper-synthesis/SKILL.md) develops the committed
  paper through staged docs: **pitch → positioning → outline/plan → decision →
  sections**. `positioning.md` (via `literature position --level paper`) gives the
  taxonomy, concept matrix, PRISMA log, and baseline list. Section prose is
  assembled from a **claim→evidence ledger** (`ledger.md`) where each row is a
  Toulmin sextet (claim / grounds / warrant / backing / qualifier / rebuttal) and
  **grounds cite run-refs**. The **`decision.md`** publish/no-go verdict is a
  material, human-signed decision, gated by an examination over positioning + cited-work +
  claims. A **no-go reads as done, not failed.**

### 5a. Honest AI use — disclose & cite

When the paper is finalized you can add a truthful **AI-use disclosure** — a short
statement of what you and the AI each did — plus a citation to `defendable-science`. The
template, how-to-cite, and an optional badge live in
[`../DISCLOSURE.md`](../DISCLOSURE.md).

You should not have to remember this: after the publish `decision` is signed off,
[`paper-synthesis`](../skills/paper-synthesis/SKILL.md) **proactively proposes** the
disclosure and citation, **drafted from your provenance record** (who signed off
which decisions, which run-refs back which results) — so it is evidence-based, not
boilerplate. It is opt-in and author-owned: you review, edit, adopt, or decline.

Plainly: every published paper that carries the disclosure points other researchers
to the tool. But Defendable Science only *supports* honest disclosure — it does **not**
certify that your research is honest, and there is no seal of honesty. The statement
says what was done and links the record; readers judge.

## 6. Thesis (optional)

Only for a doctoral thesis-by-publication — a plain portfolio repo omits this
level entirely. [`thesis`](../skills/thesis/SKILL.md) is one skill with two modes:

- **`framing` (occasional)** — set the **aims** and the narrative through-line,
  and map which portfolio papers compose the thesis (`docs/research/thesis/aims.md`).
- **`synthesis`** — assemble the **kappa** (the Nordic framing chapter that binds
  the papers; introduces *no new findings*) and clear the **defensibility gate**.

Defensibility is the highest-stakes decision, so its gate is escalated: before you
sign, `defend` runs a full **mock viva** across all three targets, and you must
acknowledge *each* surfaced gap in writing (per-gap sign-off, not one blanket
override). Done = every aim covered by ≥1 paper **and** the kappa states a
coherent through-line. Never a paper count.

## 7. Cross-cutting: progress and defend

Both are skill modes — there is no `defendable-science progress` command group,
and the examination half of `defend` is a conversation, not a command.

- [`progress`](../skills/progress/SKILL.md) is **read-only reporting**. Roll-up is
  **semantic, not arithmetic**: it surfaces coverage and blockers, never a
  percentage. A single refuted *load-bearing* hypothesis blocks its paper — an
  average would hide that. **A refuted hypothesis reads as done/green.** There are
  no scores, ever — a hard design invariant, not a missing feature.

  > **Ask the assistant.** Where do all our hypotheses stand (`progress` in
  > `status hypothesis` mode)? Then regenerate the dashboard.

  **Full guide: [`progress`](guides/progress.md)** — the four roll-ups, the two
  readings that catch people out, and the Goodhart argument in full.

- [`defend`](../skills/defend/SKILL.md) is the Socratic tutor-examiner. It is
  **self-invoked** on demand and fires **automatically as a guardrail** before
  every material sign-off. It probes, teaches on a gap, and re-probes; it targets
  `claim | cited-work | methodology`. It offers author-selectable **mentor
  personas** — *sounding board*, *critical examiner* (default), *directive
  editor*, opt-in *devil's advocate* — chosen by you or suggested by the stage,
  **never inferred from your personality**. It teaches established knowledge
  freely but never supplies the answer key to your novel claim.

  > **Ask the assistant.** Examine me on the claim in `findings.md` before I sign
  > it — critical examiner, and push on the rival explanations.

  **Full guide: [`defend`](guides/defend.md)** — the three targets and what is
  off-limits in each, the persona levers, and the evidentiary record
  `defend record` writes.

## 8. API keys & credentials

Some services the tooling reaches key-gate their *useful* rate limits. Providing a
key is **optional** — everything degrades gracefully without one — but it removes
the throttling that otherwise stalls citation-graph work.

| Key | Service | What it buys |
|---|---|---|
| `S2_API_KEY` | Semantic Scholar | raises the rate limit far above the shared keyless pool |
| `OPENALEX_MAILTO` | OpenAlex | joins the "polite pool" — just a contact email |
| `RCLONE_CONFIG_<REMOTE>_*` | private mirror | rclone credentials as scoped env vars |

Keys live in a **CLI-managed JSON store — never a `.env`** — at an XDG config path
**outside any repo's work tree**, so a stored key cannot be committed by accident
(ADR-0032). The value is never taken from the command line, only from a hidden
prompt or stdin.

```bash
defendable-science keys set S2_API_KEY     # hidden prompt, or reads piped stdin
defendable-science keys check              # presence + source, never values
```

**Full guide: [API keys](guides/keys.md)** — what each key buys, the
`os.environ > store > unset` precedence, opting into a different location, and the
plaintext-at-rest caveat.

## 9. Everyday tips

- **What Defendable Science will NOT do.** It will not make a material decision for you
  (confirm/refute, publish/no-go, defensible), will not write your paper
  unattended, will not hand-copy result numbers, and will not produce a
  productivity score. Every judgement point stops and asks.
- **Trust the firewall.** If a skill refuses to test a claim it also generated, or
  refuses to adjudicate its own decision, that is by design — use the paired
  skill.
- **Commits are attributed.** Commits made via Defendable Science skills carry a discovery
  trailer, so provenance of an automated change is visible in `git log`. Defendable Science
  never auto-commits `research-init` scaffolding — you review and commit.
- **Evidence is run-refs, not numbers.** If a number can't be traced to a run-ref,
  it doesn't go in a findings doc or a paper section.
- **Follow-ups become issues.** Deferred checks and known gaps become
  self-contained GitHub issues, not `TODO`s buried in a doc.
- **Where the reasoning lives.** Specs (the *what*) in [`docs/design/`](design/);
  decision log with rejected alternatives (the *why*) in
  [`decisions/`](../decisions/); verified source digests (the *evidence*) in
  [`resources/references/`](../resources/references/); fillable staged-doc
  skeletons in [`resources/templates/`](../resources/templates/).

---

**The shortest possible path:** `research-init` → `hypothesis-exploration
promote` → `hypothesis-testing` (strategy, examined → delegate design/plan →
sign findings) → `paper-exploration promote` → `paper-synthesis` (positioning →
sign decision → sections) → `progress` skill (read status, regenerate dashboard). You drive every arrow; Defendable Science
keeps the accounts and makes sure you can defend each signature.
