# Project brief — the business domain

Derived by reading the code, the skills and the ADRs, not by paraphrasing the README.
Every claim carries a `file:line`.

---

## 1. What the product is

`defendable-science` is a **research-workflow methodology for a PhD-scale research
program**, shipped as a Claude Code plugin plus a supporting CLI. Its thesis is stated
in one line in `.claude-plugin/plugin.json:4`:

> "Assistants, not researchers: you drive, and you must be able to defend it."

The domain problem it addresses is not productivity. It is **defensibility**: at a
viva, a review, or a retraction inquiry, a researcher must be able to say what they
claimed, on what evidence, why they believed it, and who signed off — for work that an
AI assistant helped produce. Every mechanism in the repository is downstream of that.

Two artifacts ship independently (`CLAUDE.md:7`, ADR-0026): the **plugin** (markdown
skills, the primary deliverable) and the **`defendable-science` package** (a Typer CLI
the skills shell out to, published to PyPI and installed isolated from the consumer's
ML environment, `resources/ensure-tooling.md:56`).

---

## 2. The methodology: three nested levels, generate → resolve

One object×action shape repeats at three scales (ADR-0005, ADR-0006). At each level a
*generate* skill proposes and a *resolve* skill disposes.

```
  thesis            (optional top)              thesis
     │                                             │
     ├── paper       paper-exploration  ────→  paper-synthesis
     │                    (generate)              (resolve)
     │                                             │
     └── hypothesis  hypothesis-exploration ──→ hypothesis-testing
                          (generate)              (resolve)
```

Nesting is real containment, not analogy: a hypothesis lives inside a paper
(`Layout.hypothesis_dir`, `scaffold/layout.py:199`), a paper inside the portfolio
(`Layout.paper_dir`, `:179`), and a thesis is optional and skippable
(`skills/thesis/SKILL.md:3`, "skip it entirely for a repo that is not a thesis").

### The exploration→resolution firewall

**No skill both proposes a claim and adjudicates it.** This is the load-bearing
structural rule, and it is maintained in the prose rather than merely asserted.
`skills/paper-exploration/SKILL.md:41` renders it as a **Firewall column in the verb
table**, where `promote` is the only row marked "human disposes".
`skills/hypothesis-exploration/SKILL.md` does rank — the closest thing to adjudication
in a generate skill — and fences it three times: "advisory inputs to the human's
ordering, not an automatic gate" (`:118`), "recommends; it does not select the testing
slate" (`:141`), "Ranking advises, never selects… Do not auto-promote the top row"
(`:183`). The resolve skills refuse the other direction
(`skills/hypothesis-testing/SKILL.md:36`, `skills/paper-synthesis/SKILL.md:24`).

The firewall is why the CLI has no command that both scores and selects: `backlog rank`
writes scores and sets a row `ranked` (`cli.py:2124`, "advises; never selects"), and
`backlog promote` is a separate, explicitly human act (`cli.py:2289`, "an explicit human
pick").

### The eleven skills, from their own text

| Skill | Level / role | What it actually does |
|---|---|---|
| `hypothesis-exploration` | hypothesis · generate | Runs an origin-agnostic idea pipeline — a raw idea, a citation-seeded lead, a data pattern — into the paper's backlog, ranks advisorily, hands promoted items to `hypothesis-testing`. "Proposes only; never tests or adjudicates a claim." (`SKILL.md:3`) |
| `hypothesis-testing` | hypothesis · resolve | Drives one promoted hypothesis through `hypothesis → strategy → design/plan → findings` to a **signed** verdict. Does the science (strategy, rigor, verdict); **delegates the engineering** to a bound backend. (`SKILL.md:3`) |
| `paper-exploration` | paper · generate | Mines finished and in-flight work for candidate application and follow-up papers; grooms the portfolio backlog; wires a promoted paper into the registry. "Proposes candidate papers (never commits to writing one)." (`SKILL.md:3`) |
| `paper-synthesis` | paper · resolve | Drives one paper through `pitch → positioning → outline/plan → decision → sections` to a human-signed publish/no-go, assembling claims from a **Toulmin-sextet ledger** whose entries cite experiment-backend run-refs. "Drafts proposals; the author authors and decides." (`SKILL.md:3`) |
| `thesis` | thesis · both, optional | Frames the aims, chooses which portfolio papers compose the thesis, assembles the kappa framing chapter, and clears the **defensibility gate** (per-gap signed acknowledgement, ADR-0021). Refuses to "adjudicate paper quality" (`SKILL.md:33`). |
| `progress` | cross-cutting · read-only | Reads `status:` frontmatter from every artifact and projects a dashboard: state, coverage, named blockers, uncovered aims. "Never a percentage or productivity score." (`SKILL.md:3`) |
| `defend` | cross-cutting · guardrail | A Socratic **tutor-examiner**. Runs a probe → teach → re-probe loop before a material decision is recorded, "without grading the substance of novel claims" (`SKILL.md:3`). Verifies the author can articulate a claim; never supplies the answer. |
| `digest` | cross-cutting · inbound | `defend`'s inbound counterpart: verified comprehension of an **external** paper (depth mode), plus **extraction mode** for survey-scale breadth reading that "certifies something deliberately weaker than comprehension" (`SKILL.md:3`). |
| `literature` | shared capability | Mines and situates a literature over one citation-graph substrate (OpenAlex + Semantic Scholar): **scout** mode for leads, **position** mode for defending a committed claim against prior work. |
| `dataset` | shared capability | A thin git-tracked registry, tiered storage, a private rclone mirror, SHA-256 fixity, Croissant interop. |
| `research-init` | onboarding | Two modes: **init** (scaffold a fresh repo) and **adopt** (backfill an existing one that already has papers, data and results). |

### What is deliberately *not* here

**Engineering is delegated, not implemented** (ADR-0023,
`resources/contracts/engineering.md`). The plugin never designs, plans or writes
experiment code; it hands that to a bound backend across a contract. This is why
`backlog promote --scaffold` at the paper level *requires* `--backend`
(`cli.py:2167`): "the plugin ships no experiment backend, so a registry row with an
empty binding is not a usable paper (ADR-0013)".

---

## 3. Actors and the agency / access-control model

There is no authentication and no authorisation in the software sense. The access-control
model is **who is permitted to decide what**, enforced by refusals in the code and the
skill prose. Three actors:

| Actor | May decide |
|---|---|
| **The human researcher** | Every material claim, every promotion, every verdict, every publish decision, every rights assertion. Named in `signed-off-by`. |
| **The agent** | Proposals, mechanical transformations, projections, and factual observations. Never a decision. |
| **The engineering backend** | Runs experiments and returns run-refs. Bound per paper; the plugin ships none. |

### The agency principle

ADR-0003 and `resources/references/agency-principle.md`. The human makes and signs every
material decision. Enforced at these points:

| Enforcement | Location |
|---|---|
| Gaps cannot be waved through without a named human | `defend/record.py:285` — `if outcome in ("overridden", "acknowledged-per-gap") and not signed_off_by: raise RecordError("passing surfaced gaps requires a named --signed-off-by")` |
| A verdict with no `signed-off-by` is "not yet decided", not decided | `progress/model.py:47`; `check` raises a `gap` at `check/checks.py:1576` |
| An unsigned refutation blocks nothing | `progress/collect.py:350` — a load-bearing refuted hypothesis is named as a blocker **only** `if … other.signed_off` |
| Ranking advises, never selects | `cli.py:2124`; `skills/hypothesis-exploration/SKILL.md:183` |
| Promotion is a separate, explicit act | `cli.py:2289` |
| The machine never advances a triage disposition | `cli.py:2961` — `digest extract record` writes only `extracted` and `extraction-cells`, "never `disposition`, which is the human's decision, and a machine advancing it would be exactly the agency violation this tool exists to prevent" |
| Scaffolds seed structure, never prose | `exploration/backlog.py:580` — "seeding prose the author did not write would cut against the agency principle" |
| A dropped idea keeps its reason and is never deleted | `cli.py:2351` — "file-drawer discipline" |

### The understanding principle

ADR-0004. A decision may not be recorded until the human can articulate it. `defend` is
the guardrail: it probes, teaches, re-probes, and then `defend record` writes both the
frontmatter status and an evidentiary record (`defend/record.py:224`). It records
**observed facts only** — `defend/record.py:9`: "there is no field for a 'correct
answer', a score, or a pass/fail, and it never writes `verdict` / `decision` /
`defensible`."

### Trust tiers in literature acquisition

`literature/acquire.py` establishes a checksum on first acquisition rather than
verifying against a known one, so the metadata gate stands where `dataset` has a hash
(`acquire.py:3`). Three tiers:

| Tier | Rungs | Rule | Location |
|---|---|---|---|
| **identity** | 1–3 (`openalex-best`, `openalex-locations`, `openalex-landing`) | Ungated — the URL came from the work the citekey already resolves to | `acquire.py:1413` |
| **gated** | 4–5 (`sibling-version`, `arxiv-search`) | Must pass `evaluate_match` on title × author × year; **first-author family name is a hard gate** | `acquire.py:118`, `:276`, `:331` |
| **trusted** | 6 (`venue-resolver`) | Admitted on the operator's word, recorded as `TRUSTED`, **never** as `accept` | `acquire.py:128`, `:1405`, ADR-0038 |

The `TRUSTED` constant's docstring is the clearest statement of the access model in the
codebase (`acquire.py:124`): reporting a consumer-configured URL as `accept` "would be a
verification never performed". And `acquire.py:1396`: "an integrity tool must not
launder configuration into evidence".

Gated outcomes that are plausible but unproven land in **quarantine** with nothing
written to the registry (`acquire.py:1043`), awaiting an explicit human
`literature confirm --sha256`; there is "deliberately no 'promote whatever is in
quarantine' convenience".

### Human `confirm` steps

| Step | What it authorises | Location |
|---|---|---|
| `literature confirm --sha256` | Promote a quarantined candidate after human review | `cli.py:1317` |
| `literature confirm --file` | Adopt a hand-downloaded PDF; records `rung: manual` and an **empty, non-redistributable** license because "the tool observed nothing about the rights on a file it did not fetch" | `acquire.py:1963`, `:1976` |
| `digest extract sample --verdict` | A human's finding about a sampled batch. `verified` is **refused outright** if any drawn paper's cells could not be shown, "because the human cannot have verified what they were never shown" | `cli.py:3357` |
| `dataset ingest` → `_needs_human` | Lists the fields Croissant could not fill (`license`, `tier`, `access`, `datasheet`, `sensitivity`) for the human to confirm on register | `cli.py:1555` |

### Rights as an access decision

`PERMISSIVE_SPDX` (`acquire.py:380`) is "deliberately short and **not configurable**:
whether a license grants redistribution is a compliance judgement, and a consumer
overriding it in config would be the plugin quietly sanctioning a republication it
cannot vouch for". Absent or unrecognised ⇒ `redistributable: false`
(`acquire.py:397`). `fetch` never copies bytes into the repository; it only reports
`committable`.

### Key handling (ADR-0029, ADR-0032)

| Rule | Location |
|---|---|
| Store lives **outside any repo** by default — `$XDG_CONFIG_HOME/defendable-science/keys.json` | `core/keys.py:129` |
| Precedence `os.environ` > store > `None` | `core/keys.py:243` |
| A value never reaches argv — stdin or a hidden prompt only | `cli.py:2448` |
| A value is never echoed, logged, or returned by the reporting API | `cli.py:2483` (`_key_report` returns presence and source, never a value) |
| Least privilege: a child process gets only the variables it needs | `core/keys.py:279` (`scoped_env`), `:318` (`rclone_scoped_env`) |
| Guardrail: warn if the resolved store sits in a non-gitignored work tree | `core/keys.py:406`, surfaced at `cli.py:2403` |
| Honest about what it is not: "plaintext at rest … *not* encryption" | `core/keys.py:32` |
| `mailto` goes to OpenAlex only, never to arXiv — sending a user's email to an unrelated host "would be a privacy leak, not a nicety" | `core/http.py:229` |

*(One implementation defect in this area — the store is written world-readable and then
chmod'd — is BE-6 in [`be-tech-debt.md`](be-tech-debt.md). The model is sound; the write
is not.)*

---

## 4. Core entities

### `status:` frontmatter — the primary artifact schema

Every staged document carries one. Rendered by `scaffold/status.render()`
(`scaffold/status.py:112`); the per-template initial forms are declared once at
`scaffold/status.py:84` (`TEMPLATE_FORMS`) and guarded against drift by
`tests/test_status.py:121`.

| Field | Type | Meaning |
|---|---|---|
| `level` | `hypothesis` \| `paper` \| `thesis` | which schema applies |
| `id` | str \| null | stable artifact id; keys the artifact across backlog, registry and dashboard |
| `verdict` | `confirmed` \| `refuted` \| `inconclusive` \| `n/a` \| null | the science's answer |
| `readiness` | level-specific (`resolved`, `framing`, `defensible`, `publish`, `no-go`, …) | the decision axis |
| `signed-off-by` | str \| null | **the named human**; null means *not yet decided* |
| `load-bearing` | bool | whether refuting this invalidates the paper's claim |
| `covers` | list[str] | thesis aim ids this artifact supports |
| `blockers` | list[str] | free-text, author-flagged |
| `last-updated` | ISO date \| null | newest across the artifact |
| `understanding` | `{status: ok\|gaps, unresolved: [...]}` | written by `defend record` |
| `extraction` | `{cells, locators, in-sample, batch-check}` | written by `digest extract`; **never** on the same axis as `understanding` |

The `understanding`/`extraction` split is load-bearing: `digest/artifact.py` refuses to
write `understanding` from an extraction path because "a digest carrying an
`understanding` block reads to `progress` as 'digested & understood', which would be
false for a paper nobody has read" (`cli.py:1880`).

**Staged documents and their authority** (`scaffold/layout.py:36`, `:65`):

```
hypothesis:  hypothesis.md → strategy.md → findings.md*
paper:       pitch.md → positioning.md → ledger.md → decision.md*
thesis:      aims.md → kappa.md*
                                          * = AUTHORITATIVE_DOCUMENTS
```

The authoritative document owns the adjudication axes; siblings may carry their own
lighter `understanding` and `last-updated`, which `progress` surfaces but never treats
as the verdict source (`scaffold/layout.py:48`). Before the authoritative document
exists, the furthest stage present stands in (`progress/collect.py:176`).

### Backlog row — the one explicit state machine

`exploration/backlog.py:4`:

```
  park                add
    │                  │
    ▼                  ▼
 parked ──────────► candidate ──rank──► ranked ──promote──► promoted
    │                  │                   │
    └──────────────────┴───────drop────────┴────────────► dropped (reason required)
```

`dropped` is terminal and non-destructive — the row stays with its reason
(`cli.py:2351`). `promoted` at the paper level additionally scaffolds a paper root and
appends a `papers.md` registry row (`exploration/backlog.py:558`).

Two column profiles (`exploration/backlog.py:39`, `:51`):

| Level | Columns |
|---|---|
| hypothesis | `id, one-line, move/type, provenance, EIG, feas, interest, frame, status, note` |
| paper | `id, one-line, lens, provenance, feas, interest, status, note` |

`provenance` is required on every row — "no orphan ideas"
(`exploration/backlog.py:305`).

### Registry entry (`references.json`, CSL-JSON + a namespaced spine)

ADR-0020. The bibliography is valid CSL-JSON so it round-trips through Zotero and
pandoc; the substrate spine lives under CSL's schema-designated `custom` field,
namespaced `defendable-science` (`literature/registry.py:24`).

```
Entry(citekey, title, year, first_author_family, doi, asset, raw)   registry.py:120
└─ Asset(schema=1, pid, files[], license, redistributable,          registry.py:95
         access, mirror, acquisition)
   ├─ AssetFile(path, sha256, size, media_type)                     registry.py:34
   ├─ License(id, observed, source)  ← *observed*, not asserted     registry.py:51
   ├─ MirrorRef(remote, key)                                        registry.py:65
   └─ Acquisition(rung, url, candidate, match, fetched)             registry.py:77
```

### Triage row (`triage.yml`) — the PRISMA sidecar

`TriageRow(citekey, disposition, raw)` (`literature/registry.py:475`). `disposition` is
the human's state-machine value; the `raw` dict preserves fields the model does not
name, including the rationale text. `patch_triage` refuses to rewrite the file if it
carries comments, non-mapping rows, or any YAML anchor
(`literature/registry.py:769`, `:778`, `:785`) because "the triage sidecar's `rationale`
fields *are* the PRISMA audit trail".

### Extraction cell

`Cell(citekey, axis, value, locator, justification)`
(`digest/extraction.py:205`). A locator is **required** unless `value` is
`not-addressed`, in which case a justification is required (`extraction.py:386`). Rule 2
is the anti-gaming rule: every matrix axis must be accounted for, so an agent that finds
an axis hard cannot simply omit the cell — "a short row looks exactly like a clean row"
(`extraction.py:454`).

### Dataset entry (`datasets.yml`)

`DatasetEntry` with `FileRef`, `Retrieval`, `Citation`, `Mirror`
(`dataset/manifest.py`). Three storage tiers (ADR-0010, `TIERS` at `manifest.py:27`):

| Tier | Meaning | Resolution |
|---|---|---|
| **A** | committed in-repo | verify in place at its repo path (`retrieval.py:95`) |
| **B** | public, fetchable | cache → mirror → pooch, SHA-256 at every hop (`retrieval.py:104-128`) |
| **C** | gated / manual | **never fetches**; prints the recorded instructions (`retrieval.py:131`) |

### Check finding

`Finding(severity, check, file, message, remedy)` (`check/model.py:36`) — `remedy` is a
required field. Three severities with the exit code keyed to **severity, not count**
(`check/model.py:3`):

| Severity | Meaning | Exit |
|---|---|---|
| `invalid` | violates a shape this package owns | 1 |
| `unreadable` | could not be read or parsed, so validity is **unknown** | 1 |
| `gap` | a valid file holding incomplete science | 0 |

`check/model.py:14`: "The exit code is keyed to invalid *files*, never to incomplete
*science*: a `refuted` hypothesis or a `no-go` paper is successful science and is not a
finding of any kind."

### Dashboard artifact

`Artifact` (`progress/model.py:29`) — a frozen dataclass of *facts read from
frontmatter, never judgements*. `progress/model.py:4`: "There is deliberately no
aggregate, no score and no completion field." `unreadable` and `Milestones.unknown` are
modelled separately from absence "because 'we do not know' and 'there is nothing' are
different facts and only one of them is fine" (`progress/model.py:9`).

### Consumer layout

`Layout` (frozen, `scaffold/layout.py:76`) — four recordable roots
(`research_root`, `literature_dir`, `datasets_manifest`, `thesis_dir`,
`LAYOUT_KEYS` at `:20`); everything inside a paper is **derived and not configurable**
(`:177`). Defaults omitted when recorded (ADR-0039, `recorded_layout` at `:336`), and
every configured value is confined to the repository (`_relative`, `:241`).

---

## 5. Automation — what triggers what

### Skill → CLI invocation chain

Every CLI-invoking skill first executes `resources/ensure-tooling.md` — linked, never
inlined, from 8 of 9 call sites (`skills/progress/SKILL.md:46` is the omission).

| Skill | Invokes |
|---|---|
| `research-init` | `defendable-science init [--thesis] [--dry-run] [--root]`, `check` |
| `hypothesis-exploration` | `backlog park/add/rank/list/promote/drop --level hypothesis` |
| `paper-exploration` | the same with `--level paper`, `promote --scaffold --backend` |
| `literature` | `literature resolve/cites/refs/enrich/neighbors`, `fetch/confirm/verify/mirror` |
| `dataset` | `dataset validate/ingest/emit/fetch/verify/mirror/audit` |
| `defend` | `defend record --artifact --target --points`, `digest extract cells` |
| `digest` | `digest extract axes/record/sample/render` |
| `progress` | `check`, `progress dashboard` |
| `thesis`, `hypothesis-testing`, `paper-synthesis` | no direct CLI calls (they drive documents) |

### CLI command → file-write effects

| Command | Writes |
|---|---|
| `init` | the whole consumer tree; merges `.gitignore` append-only; **never overwrites** (`cli.py:516`) |
| `check` | nothing — read-only |
| `progress dashboard` | `dashboard.md`, wholesale; a hand-edit is correctly discarded (`cli.py:729`) |
| `backlog park/add/rank/drop` | the backlog table |
| `backlog promote --scaffold` | + paper tree, `pitch.md`, `backlog.md`, a `papers.md` row |
| `literature fetch` | blob store, quarantine, `references.json` spine, optionally the mirror |
| `literature confirm` | blob store, `references.json` spine; unlinks the quarantine sidecar |
| `defend record` | artifact `status.understanding`, a transcript, an accountability-log entry |
| `digest extract record` | digest artifact + cells block, a log entry, then `triage.yml` |
| `digest extract sample --verdict` | `batch-check` on **every** batch member, `in-sample` on drawn ones, log entries |
| `digest extract render` | `positioning.md`'s matrix, merged |
| `keys set/unset` | the out-of-repo key store |
| `dataset fetch/mirror` | blob store, the mirror |

### GitHub Actions

| Workflow | Trigger | Effect |
|---|---|---|
| `ci.yml` | push→main, every PR, merge_group | pre-commit (all hooks); test matrix py3.11–3.14 → ruff + mypy + pytest with the 100 % gate; Codecov on 3.13; `plugin-validate`; `check` alls-green aggregator (`:77`) |
| `bump-version.yml` | `workflow_dispatch` | `tools/bump_version.py` edits **`pyproject.toml` only**; opens a release PR |
| `publish.yml` | `release: published`, `workflow_dispatch` | guard: release tag must equal the pyproject version (`:34`); `uv build`; OIDC Trusted Publishing (ADR-0027) |
| `docs-publish.yml` | `release: published`, dispatch, PR on `skills/**`/`decisions/**`/`docs/**` | PR → `mint validate` + `mint broken-links`. Release → push to the docs repo, poll the live site, 404-check every nav URL (`:203`) |
| `live-validation.yml` | dispatch, **weekly cron Mon 06:00 UTC** | `DEFENDABLE_SCIENCE_LIVE=1 pytest -m live` against real OpenAlex/S2/rclone |

`dependabot.yml` covers GitHub Actions and Python deps (ADR-0036); 7 of the repo's
commits are dependabot's.

### Pre-commit hooks

`.pre-commit-config.yaml`: trailing-whitespace, end-of-file-fixer, check-yaml,
check-added-large-files, pyupgrade `--py311-plus`, and five `repo: local` hooks —
codespell, ruff, mypy, `validate-plugin.sh` (scoped to
`files: ^\.claude-plugin/.*\.json$`, `:69`), detect-secrets. The local-hook choice is
deliberate: it keeps each tool's version authored only in `pyproject.toml`'s `lint`
group rather than on a second Dependabot schedule (`.pre-commit-config.yaml:21`,
ADR-0036).

---

## 6. Glossary

**Agency principle** — the human makes and signs every material decision; the agent
proposes. ADR-0003, `resources/references/agency-principle.md`. Enforced at
`defend/record.py:285` and eight other points (§3).

**Understanding principle** — a decision may not be recorded until the human can
articulate it. ADR-0004; `defend` is its guardrail.

**Exploration→resolution firewall** — no skill both proposes a claim and adjudicates
it. `CLAUDE.md:24`; rendered as a table column at
`skills/paper-exploration/SKILL.md:41`.

**`defend`** — the Socratic tutor-examiner. Probe → teach → re-probe, before a material
decision is recorded. Never grades the substance of a novel claim
(`skills/defend/SKILL.md:3`); never supplies the answer (`:59`).

**`digest`** — `defend`'s inbound counterpart: verified comprehension of someone else's
paper. Two modes — **depth** (full comprehension, an hour or two per paper) and
**extraction** (breadth, survey-scale, certifying deliberately less). ADR-0034,
ADR-0040.

**Evidentiary point record** — ADR-0033. What `defend record` writes per probed point:
`PointRecord(point, source_quote, reader_answer, resolved, location, gap_note)`
(`defend/record.py:49`). Records what grounds the claim and what the human actually
said — observed facts, never a grade.

**Accountability log** — the append-only trail under
`<research_root>/defend-log/`, written by `defend record`, `digest extract record` and
`digest extract sample`. One trail, one writer (`defend/record.py:320`), never
overwritten (`:344`).

**Fixity** — SHA-256 as the identity of bytes. `core/fixity.py`; verified at every hop
of the resolution chain (`dataset/retrieval.py:68`), and a blob that fails is deleted
rather than left to be re-read (`literature/acquire.py:1221`).

**Content-addressed store** — `<cache_dir>/sha256/<hash>`. Overwriting is safe and
unconditional because the destination is derived from the bytes
(`literature/acquire.py:1089`).

**Tiers A / B / C** — dataset storage classes: in-repo, public-fetchable, gated-manual.
ADR-0010; `dataset/manifest.py:27`.

**Ladder / rung** — the six-step PDF acquisition sequence, best-first and lazy
(`literature/acquire.py:1358`). Rungs 1–3 identity-derived, 4–5 gated, 6 trusted.

**Match gate** — `evaluate_match` (`literature/acquire.py:276`). Title × author × year;
first-author family name is a hard gate. Verdicts: `identity`, `trusted`, `accept`,
`quarantine`, `refuse`.

**Quarantine** — plausible-but-unproven bytes parked with their evidence, **nothing
written to the registry**, awaiting an explicit human `confirm`
(`literature/acquire.py:1043`).

**Polite pool** — OpenAlex's faster tier for requests carrying a contact `mailto`.
`core/http.py:121`; the email is sent to OpenAlex only (`core/http.py:229`).

**Compat pin** — the version range the plugin declares for the package. ADR-0026;
`resources/ensure-tooling.md:26`. The two artifacts version independently and must
**never** be locked together. *(The pin currently names an unreleased version — PL-1.)*

**Failure honesty** — `CLAUDE.md:65`: never report a failure as a legitimate
empty/negative/complete result, and never surface a transient error as a raw traceback.
Implemented as type distinctions: `MirrorUnreachableError` vs. a `False` return
(`core/mirror.py:43`), `DownloadError.hard_miss` (`core/download.py:71`),
`RateLimitError` (`core/http.py:52`).

**Toulmin sextet** — the claim/ground/warrant/backing/qualifier/rebuttal structure of a
ledger entry. `resources/templates/paper/ledger.md`;
`skills/paper-synthesis/SKILL.md:90`.

**Kappa** — the framing chapter of a compilation thesis; where the defensibility
sign-off lives (`scaffold/layout.py:52`, `AUTHORITATIVE_DOCUMENTS["thesis"]`).

**Concept matrix** — the table in `positioning.md` whose columns are the axes a paper's
delta turns on. The extraction question set (`digest/extraction.py:31`); its row is a
**projection** of the recorded cells, never authored independently
(`digest/artifact.py:285`).

**Batch check** — the verdict a human records over an extraction batch after inspecting
a `max(3, 10%)` sample (ADR-0040). A `failed` verdict lands on **every** member,
sampled or not, and touches no cell — "silently repairing the caught cell would convert
that signal into a tidy-looking local fix" (`cli.py:3253`).

**Engineering delegation contract** — ADR-0023,
`resources/contracts/engineering.md`. Design, planning and code are handed to a bound
backend; the plugin never implements them.

**Experiment backend** — the per-paper binding recorded in `papers.md` that runs
experiments and returns run-refs. ADR-0013,
`resources/contracts/experiment-backend.md`. The plugin ships none, which is why
`--backend` is required (`cli.py:2167`).

---

*See [`executive-summary.md`](executive-summary.md) for the assessment, and the four
debt reports for where this design is and is not carried through.*
