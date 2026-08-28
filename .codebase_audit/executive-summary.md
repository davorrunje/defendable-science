# Executive summary — `defendable-science` codebase audit

Audited 2026-08-29 against `0489114` on `literature/patch-triage-tmp-cleanup`.
Documentation-only: no source file was modified. Every finding carries a verified
`file:line`; the notable ones were reproduced.

**Headline rating: 6.5 / 10** — genuinely strong engineering discipline in the
places most projects neglect, with the debt concentrated in one area that matters
disproportionately here: the CLI/JSON contract the plugin's skills depend on.

---

## Quality rating

| Factor | Weight | Score | Justification |
|---|---:|---:|---|
| Architecture & plugin↔package boundary | 11 % | **8** | ADR-0026 is respected *in the automation*, not just the comments — `tools/bump_version.py:28` touches only the package's pyproject and no workflow references `plugin.json`. `scaffold/layout.py` is a real single definition; Protocol seams throughout; **no circular imports** and **zero functions over McCabe 10** across 17,081 LOC. Deductions: `cli.py` at 3,537 lines mixing four responsibilities (BE-15), `DEFAULT_LOG_DIR` duplicated outside `layout.py` (BE-12). |
| Test-suite quality | 12 % | **7** | A hand-built mutation check killed **7/7 non-equivalent mutants** on `core/fixity.py`; `FakeProbe` is conformance-pinned against the real `FsProbe` (`tests/test_check.py:251`); sample determinism is tested across two interpreters (`tests/test_sampling.py:79`). Deductions: **zero property-based testing** on six hand-rolled parsers of untrusted input — and two verified bugs live exactly there; no concurrency tests; `graph.py` has only hand-written idealised fixtures. ([`coverage.md`](coverage.md)) |
| Code duplication | 6 % | **6** | Source duplication is low and usually *acknowledged* (`cli.py:357` names the rule it duplicates). Test duplication is not: `_write` defined 6×, `_unstyled` 3×, 15 separate `CliRunner()`s, ~40 duplicated helpers against a 34-line `conftest.py`. One skill duplicate has already drifted (PL-8). |
| CLI & JSON-contract design | 13 % | **5** | The weakest area, and the one with the widest blast radius: **38 commands, 7 incompatible output shapes** (API-1); four commands change shape based on a flag (API-4); the exit-code taxonomy is documented on one command and applied on that one only (API-5); no version field and no stated change policy (API-9). Offset by genuinely good help-text machinery (`cli.py:120`) and the `digest extract` family, which is a model envelope. |
| Artifact / data-model quality | 12 % | **6** | Strong substrate: a namespaced spine inside valid CSL-JSON (`registry.py:24`), content-addressed storage, `unknown` as a first-class value (`retrieval.py:250`). Deductions: **no schema version on any artifact**, the shape re-implemented in four places with only one of six pairings guarded (DATA-2), no migration path (DATA-4), and a verified round-trip corruption in `render_table` (DATA-5). |
| Failure honesty & degradation | 15 % | **7** | The *design* here is a 9 — three independent type-level distinctions between "we could not ask" and "the answer is no" (`mirror.py:43`, `download.py:71`, `http.py:52`), paying off in `_exhausted` (`acquire.py:1758`). The *application* has six verified holes at the JSON boundary, including one **silent wrong value** where a malformed S2 field is recorded as a single character (BE-4 site 3), plus a bootstrap that silently keeps a stale CLI (PL-2). Highest weight because it is this repo's own stated core principle and the axis on which research integrity turns. |
| Dependency management & supply chain | 7 % | **7** | Exact-pinned dev/lint tools, a committed `uv.lock`, Dependabot (ADR-0036), OIDC Trusted Publishing (ADR-0027), a tag↔version guard (`publish.yml:34`), bandit + detect-secrets in pre-commit. Deductions: runtime deps are **floors only, no upper bounds** — `typer>=0.12` is a pre-1.0 library tested at 0.27.1; plus a global `ignore_missing_imports` and `warn_unused_ignores = false` (BE-16). |
| Git / DevOps / release discipline | 9 % | **7** | 4-Python CI matrix with an alls-green gate, pinned action SHAs, a separate weekly live-validation cron, a docs pipeline that 404-checks the live site after publishing. Deductions: `bump-version.yml:74` prints release instructions that **publish nothing** (PL-6); no plugin↔package compat gate — which is exactly how PL-1 shipped; `CHANGELOG.md` missing two released versions. |
| Bus factor & contributor scaling | 7 % | **4** | Effectively bus-factor 1. **8 of 99 merged PRs carry any review record**; the other 91 are self-merged. Three git identities for one person, no `.mailmap`. The ADR set is a real compensating control — but it documents decisions, it does not catch defects, and the four broken doc invocations (API-2) are what a second reviewer would have caught. |
| Documentation & ADR discipline | 8 % | **7** | 41 ADRs, complete index, a `Status`/`Date`/`Deciders` line on every one, and real *rejected alternatives* sections. Docstrings are explanatory rather than decorative. Deductions: six material decisions with **no** ADR — all CLI-contract ones (PL-5d); a **dangling citation to an ADR that does not exist** (PL-5c); `STATUS.md` still advertises the former project name; `docs/design/proposals/tooling-package.md:17` contradicts ADR-0026 inside a doc marked `implemented`. |
| **Weighted total** | **100 %** | **6.5** | |

---

## Team & contribution

| Contributor | Commits (all branches) | First | Last | Tenure | Inferred role |
|---|---:|---|---|---|---|
| Davor Runje `<davor@synthpop.ai>` | 298 | 2026-07-17 | 2026-08-29 | 43 d | Author, maintainer, sole reviewer |
| Davor Runje `<zlikowski@gmail.com>` | 64 | 2026-07-18 | 2026-08-26 | 39 d | **Same person**, second machine/identity |
| Davor Runje `<davor.runje@fer.hr>` | 34 | 2026-08-27 | 2026-08-29 | 3 d | **Same person**, institutional identity |
| `dependabot[bot]` | 7 | — | — | — | Automated dependency bumps (ADR-0036) |
| `copilot-swe-agent[bot]` | 1 | — | — | — | One-off automated contribution |

**Review process, measured.** 99 merged PRs; 92 authored by `davorrunje`, 7 by
Dependabot. **Only 8 carry any review record at all.** 92 merge commits on `main`, with
a consistent `Merge pull request #N from davorrunje/<topic>` shape and disciplined
branch prefixes (`fix/`, `feat/`, `docs/`, `literature/`, `core/`, `design/`,
`release/`). The mechanics are exemplary; the *second pair of eyes is absent*.

What that implies, stated plainly: this is a single-maintainer repository with bot
contributors and self-merged PRs. **The ADR set is the compensating control**, and it is
an unusually good one — 41 records with drivers, options and rejected alternatives means
a future maintainer can reconstruct *why*, which is the thing that normally dies with the
author. But ADRs document decisions; they do not catch defects. The four documented CLI
invocations that do not run (API-2), the compat pin naming an unreleased version (PL-1),
and the `bump-version` instructions that publish nothing (PL-6) are all things a reviewer
would plausibly have caught, and all three are user-facing. The structural answer is not
"find a reviewer" — it is **to convert the review that is missing into tests**, which is
why API-3 and API-6 are the top two recommendations below.

**Three git identities for one person** is a concrete hygiene issue: `git shortlog -sn`
reports three contributors, `git log --author` misses two-thirds of the history, and any
future contribution-graph or CITATION tooling will double-count. There is no `.mailmap`.
One file fixes it permanently:

```
# .mailmap
Davor Runje <davor@synthpop.ai> <zlikowski@gmail.com>
Davor Runje <davor@synthpop.ai> <davor.runje@fer.hr>
```

---

## Project metrics

| Metric | Value |
|---|---|
| Source | **17,081 LOC** across **41** `.py` files |
| Tests | **21,833 LOC** across **36** files |
| Test : source ratio | **1.28 : 1** |
| Coverage | **100.00 %** statement **and** branch (`fail_under = 100`, `--cov-branch`) |
| Test run | **1562 passed, 14 skipped** in 16.4 s |
| mypy | clean, 79 files, `strict = true` |
| ruff | clean; **0** functions over McCabe 10 |
| bandit | 2 Low (both correct uses of `random`) |
| Largest modules | `cli.py` 3,537 · `literature/acquire.py` 2,350 · `check/checks.py` 2,136 |
| Largest suites | `test_acquire.py` 2,933 · `test_check.py` 2,528 · `test_digest_cli.py` 1,338 |
| Commits on `main` | **374** |
| Commits, all branches | **404** |
| Merge commits on `main` | **92** |
| PRs (all states / merged) | **101 / 99** |
| Merged PRs with any review | **8 of 99** |
| Open issues | **11** |
| Skills | **11**, **2,955** markdown lines |
| ADRs | **41** (+ index) |
| `# pragma: no cover` | **6** |
| Project age | 2026-07-17 → 2026-08-29 (**43 days**) |
| Avg commits/week (main) | **≈ 61** |

*Corrections to the baseline I was given: source is 17,081/41 not 15,930/29 (the earlier
count omits `__init__.py` files and predates recent growth); tests 21,833/36 not
20,285/29; `check/checks.py` is 2,136 not 1,511; merge commits 92 not 94; PRs 101 not 99;
skills 2,955 lines not 2,881.*

---

## What works

1. **Failure honesty is implemented as types, not as a convention.** The distinction
   between "we could not ask" and "the answer is no" is a real, tested type distinction
   in three independent layers: `MirrorUnreachableError` vs. a `False` return keyed on
   rclone's exit code (`core/mirror.py:40`, `:160`); `DownloadError.hard_miss` keyed on
   404/410 (`core/download.py:71`); `RateLimitError` as a distinct subclass so a throttle
   can never be recorded as a miss (`core/http.py:52`). It pays off in `_exhausted`
   (`literature/acquire.py:1758`), which buckets an exhausted ladder as `manual` **only**
   when nothing was blocked, and in `AuditReport.mirror_present: dict[str, bool | None]`
   (`dataset/retrieval.py:250`), where `None` genuinely means unknown. Almost nothing at
   this scale gets this right.

2. **The ADR set.** 41 records, complete index (`decisions/README.md:15`), a
   `Status`/`Date`/`Deciders` line on every one, and genuine rejected-alternatives
   sections — `0026:51` on why locked versions were rejected, `0038:74` on why
   PDF-text verification was rejected as disproportionate. For a single-maintainer repo
   this is the difference between a codebase that can be inherited and one that cannot.

3. **Explicit, narrow injection seams.** `Probe` (`check/probe.py:13`), `Session` /
   `Response` (`core/http.py:61`), `StreamSession` (`core/download.py:118`), `Runner`
   (`core/mirror.py:83`), `GitRunner` (`core/keys.py:355`), `SearchClient` /
   `MirrorClient` (`literature/acquire.py:53`), `TierBFetcher`
   (`dataset/retrieval.py:44`). All structural Protocols. CLAUDE.md's claim that the
   kernels are injectable holds, and `tests/test_check.py:251` *pins the fake against the
   real one* — converting "we tested a fake" from an assumption into a checked claim.

4. **Refusal over silent repair, everywhere.** `patch_triage` refuses a sidecar carrying
   comments, non-mapping rows, or any YAML anchor (`literature/registry.py:769`, `:778`,
   `:785`) rather than reshaping a human's file — with `_alias_groups`
   (`registry.py:651`) walking the *composed node graph* to avoid false-positiving on
   interned scalars, which is the single best piece of reasoning in the repository.
   `set_field` refuses to overwrite a comment it cannot round-trip
   (`core/frontmatter.py:158`). Refetch drift refuses rather than rebinding
   (`acquire.py:1532`).

5. **Every error message carries a remedy.** Not one bare "invalid input" in the package.
   `Finding.remedy` is a *required* field of the model (`check/model.py:36`), and the
   free-text errors follow the same discipline (`frontmatter.py:158`,
   `registry.py:770`, `acquire.py:1258`, `core/config.py:52`).

6. **The agency principle is enforced in code, not just described.** Gaps cannot be waved
   through without a named human (`defend/record.py:285`); an unsigned refutation blocks
   nothing (`progress/collect.py:350`); `digest extract record` writes two factual
   scalars and *never* `disposition`, because "a machine advancing it would be exactly
   the agency violation this tool exists to prevent" (`cli.py:2961`); scaffolds seed
   structure but never prose (`exploration/backlog.py:580`).

---

## Critical gaps

### 1. The skill↔CLI contract is unenforced, and four invocations are broken today
*(High — [`api-tech-debt.md`](api-tech-debt.md) API-2, API-3)*

| Location | Break | Effect |
|---|---|---|
| `docs/USER-GUIDE.md:182` | `--EIG` (the flag is `--eig`, `cli.py:2119`) | `No such option`, exit 2 |
| `docs/guides/dataset.md:32` | `dataset verify` with no required positional | `Missing argument`, exit 2 — in the block that *defines* the guide's "shell blocks are verbatim" convention |
| `docs/guides/dataset.md:139` | same, and the prose asks for a whole-manifest sweep (`dataset audit`) | wrong command *and* broken |
| `skills/hypothesis-exploration/SKILL.md:56` | documents the column `one-line hypothesis`; the CLI requires `one-line` (`exploration/backlog.py:303`) | a table built to spec is **permanently unwritable** |

`tests/test_plugin_content.py` is the only test that opens a `SKILL.md`; it asserts one
hard-coded string and **deliberately skips fenced code blocks** (`:70`) — where every
invocation lives. One parametrised test closes the whole class.

### 2. The shipped bootstrap names a package version that does not exist
*(High — [`plugin-tech-debt.md`](plugin-tech-debt.md) PL-1, PL-2)*

- `resources/ensure-tooling.md:26` pins `defendable-science>=0.3.0,<0.4.0`.
- `defendable-science/pyproject.toml:7` is `0.2.2`; newest tag `v0.2.2`. **0.3.0 was never released.**
- The pin is **never passed to any install command** — `:28`, `:30`, `:32` are all bare.
- There is **no upgrade path**: a mismatch falls through to a bare `uv tool install`, a
  no-op against an existing older install. ADR-0026:35 promises "installs/**upgrades**".
  A stale CLI is kept silently — a failure-honesty violation in the one file whose job
  is honest bootstrapping.

### 3. Six unvalidated JSON boundaries — four tracebacks and one *silently wrong value*
*(High — [`be-tech-debt.md`](be-tech-debt.md) BE-4; tracked in #169)*

All six reproduced. The worst is not a crash:

```python
_aggregate_s2_edges([{"contexts": "the whole sentence", "intents": "background"}], out)
# out["context_snippet"] == 't'      # literature/graph.py:349
# out["intent"]          == 'b'      # literature/graph.py:351
```

If Semantic Scholar returns a bare string where the docs promise a list, the tool records
the letter `t` as the sentence in which a paper was cited, emits it as a legitimate value
with no `degraded` marker, and a researcher may quote it in a related-work section.
Four of the six are in `literature/graph.py`; the *same* upstream record is parsed
correctly by `acquire.py:549`, so the rule exists and was applied to one of two readers.
Also reproduced: `dataset ingest` on a JSON array → raw `AttributeError` traceback
(`cli.py:1549`).

### 4. Writes are non-atomic, and the claim lands before the evidence
*(High — [`be-tech-debt.md`](be-tech-debt.md) BE-2/BE-3, [`data-tech-debt.md`](data-tech-debt.md) DATA-1)*

**3 of 18 write sites** use the temp-then-rename idiom that commit `0489114` just
hardened. The 15 that do not include `defend record`'s artifact patch, the accountability
log, the digest artifact, the key store, every backlog table, and `positioning.md`'s full
rewrite (`cli.py:3509`) — whose docstring promises "**Nothing is ever deleted**".

Worse than the atomicity is the **ordering**. `defend/record.py:288` patches the
artifact's `status.understanding` and *then* writes the accountability-log entry. If the
log write fails, the artifact claims verified understanding **with no evidence behind
it** — and `progress` and `check` read the frontmatter, not the log. For a tool whose
entire purpose is defensible claims, this is the single worst on-disk state it can
produce. Same shape at `digest/artifact.py:548`.

### 5. Externally-derived identifiers reach the filesystem unchecked
*(High — [`be-tech-debt.md`](be-tech-debt.md) BE-1)*

**Reproduced**: a `--cells` entry whose citekey is `../../../../../../tmp/dsaudit/PWNED`
caused `digest extract record` to write `/tmp/tmp/dsaudit/PWNED.md` **outside the work
tree**, creating intermediate directories on the way. `Layout.digest`
(`scaffold/layout.py:144`), `paper_dir` (`:179`), `backlog` (`:183`), `positioning`
(`:195`) and `append_log_entry` (`defend/record.py:343`) all interpolate an untrusted
identifier with no validation — while the same repository enforces exactly this rule in
three other places (`acquire.py:1019`, `layout.py:241`, `cli.py:359`). It is an
inconsistency, not an oversight.

### 6. No artifact schema version, and no migration path
*(High — [`data-tech-debt.md`](data-tech-debt.md) DATA-2, DATA-4)*

No `schema-version` on any artifact. The registry spine has one (`registry.py:26`,
"so a future migration need not guess") and nothing reads it. There is no `migrate`
command, and `init` explicitly never overwrites (`cli.py:516`) so it cannot become one.
When a field's *semantics* change, `check` reports nothing at all — the old value is read
as if it meant the new thing. **This has already happened once**: `CHANGELOG.md`'s
`[Unreleased]` records that a sign-off rule changed and "`check` grew the matching rule,
which its `verdict: n/a` exemption had been hiding", with no note about existing
artifacts. Compounding it, each artifact's shape is defined in four places — writer,
template, reader, validator — and only **one of the six pairings** is guarded by a test
(`tests/test_status.py:121`).

---

## Risk assessment

Weighted by impact on **research integrity**. A silent wrong answer is categorically
worse than a crash: a crash is re-run, a wrong citation context ends up in a manuscript.

| Risk | Severity | Likelihood | Blast radius |
|---|---|---|---|
| A recorded claim of verified understanding with no evidence behind it (gap 4) | **Critical** | Low | One artifact, permanently, invisibly — the exact failure the tool exists to prevent |
| A malformed upstream field emitted as a plausible value (gap 3, BE-4 site 3) | **Critical** | Low–Med | Any `literature enrich --context` output; may reach a related-work section |
| A skill fails mid-workflow on a documented invocation (gap 1) | High | **Certain** — 4 live | Every consumer following `USER-GUIDE` or `guides/dataset`; erodes trust in the tool |
| Bootstrap resolves nothing on a fresh install (gap 2) | High | **Certain** | Every new consumer taking the documented PyPI path |
| Silently stale CLI after a bootstrap (gap 2, PL-2) | High | Medium | Skills calling verbs the installed CLI lacks; symptom appears three steps later |
| Artifact written outside the work tree (gap 5) | High | Low | Filesystem beyond the repo; data loss if it lands on an existing file |
| Partial write corrupts `positioning.md` (gap 4, DATA-5) | High | Low | The author's taxonomy prose and PRISMA log, unrecoverable outside git |
| `render_table` corrupts a table on round-trip (DATA-5) | High | Low | Any table with a pipe in a header; the next read fails |
| Existing artifacts break or silently change meaning on upgrade (gap 6) | High | Medium | A researcher's whole thesis tree; no version to branch on |
| Concurrent invocations lose a `triage.yml` row (DATA-6) | Medium | Low | PRISMA rationale, silently |
| Contract drift with OpenAlex/S2 undetected by the hermetic suite | Medium | Medium | Bounded to ≤7 days by the weekly live job — but that job has **no failure notification**, and `acquire.py` has no live coverage at all |
| `typer` major bump breaks an isolated install (no upper bound) | Medium | Low | Every fresh `uvx` install |
| Bus factor 1 (§Team) | Medium | — | The whole project; mitigated by the ADR set |

---

## Recommendations

### Immediate (week 1–2)

1. **Fix the four broken invocations** and add the guard test — API-2, API-3. One-token
   edits plus ~40 lines of parametrised test. Resolves gap 1.
2. **Fix the compat pin**: release 0.3.0 or lower the floor to `>=0.2.2`, put the
   constraint in all three install commands, define the mismatch action — PL-1, PL-2,
   plus the `test_the_compat_pin_is_satisfiable` guard in API-6. Resolves gap 2.
3. **Guard the six JSON boundaries** — BE-4. The `isinstance` checks already exist at
   `acquire.py:549`; apply them in `graph.py`. Fix **site 3 first**: it is the only
   silent-wrong-value in the set. Resolves gap 3.
4. **Reorder `defend record` and `write_extraction`**: log entry first, artifact second —
   BE-3, DATA-1. Twenty lines, and it removes the Critical-severity risk row.
5. **Escape the header in `render_table`** (`core/mdtable.py:446`) — one call to a
   function that already exists — plus a round-trip property test. DATA-5.
6. **Add `.mailmap`** — three lines, permanent fix for the identity split.

### Short-term (month 1)

7. **Extract `write_atomic` to `core/` and route all 18 write sites through it** — BE-2.
   Mechanical; no behavioural change on the success path. Completes gap 4.
8. **Validate identifiers at the `Layout` boundary** — BE-1's `_safe_id`. Resolves gap 5.
9. **Adopt Pydantic v2 at the parsing boundary** — BE-9, DATA-2, DATA-12, and #169. This
   is now sanctioned (see the note below). One `_WorkIn` model closes BE-4 sites 1–4 at
   once; a strict `_FileRefIn` closes the manifest coercion. Do **not** convert the
   internal dataclasses, and do **not** convert `progress/collect.py:64`, whose tolerance
   is deliberate and documented.
10. **Add a `schema-version` field now**, while there is one version to declare — DATA-4.
    It costs one line today and is unrecoverable later. Resolves the forward-compat half
    of gap 6.
11. **Fix `bump-version.yml:74`/`:95`** to use `gh release create` — PL-6 — and add
    `CHANGELOG` entries for 0.2.1/0.2.2 plus the `CITATION.cff` bump.
12. **Rewrite `STATUS.md`'s "Released" section** — it advertises the former project name
    and a `uv tool install honest-scholar` that installs the wrong thing. PL-4.
13. **Add failure notification to `live-validation.yml`** — the weekly job is the only
    upstream-drift detector and a red run on a cron tab is easy to miss.

### Medium-term (month 2–3)

14. **Adopt the JSON envelope across the tree** — API-1, API-7, API-9. Breaking, so it
    belongs with an `api_version: 1` field, an ADR recording the contract and its change
    policy, and golden-output tests. This is the single largest quality lever in the
    repository.
15. **Unify the exit-code taxonomy** — API-5. `literature resolve`'s docstring already
    specifies it correctly; apply it in `_http_guard`.
16. **Write the six missing ADRs** — PL-5d. The JSON envelope and the `check` severity
    model first: skills depend on both, and API-1 shows five conventions accreted in the
    envelope's absence.
17. **Consolidate `conftest.py`** — `coverage.md` §9. Moving `_unstyled`, `CliRunner`,
    `_scaffolded` and `FakeProbe` removes ~40 duplicated definitions and the
    `sys.path`-dependent cross-file import at `tests/test_progress.py:10`.
18. **Add `hypothesis` for the six hand-rolled parsers** — `coverage.md` §8. A round-trip
    property would have caught DATA-5 on the first run, and the `RecursionError` at
    `registry.py:506` shortly after.
19. **Batch the OpenAlex round-trips** — BE-7. `neighbors --kind both` currently issues
    ~100 sequential requests where ~4 would do.
20. **Resolve the concurrency question** — DATA-6. Either add the advisory lock or
    document the single-writer constraint; discovering it as a lost `triage.yml` row is
    the wrong way for a researcher to learn it.
21. **Domain-neutrality pass** — PL-3, starting with `skills/digest/SKILL.md:257` and
    `skills/hypothesis-testing/SKILL.md:70`, the two examples a new user hits first.

---

## A note on the Pydantic recommendations

The repo owner has **lifted the blanket Pydantic prohibition for the external-input
parsing boundary only** — API responses, Croissant, CSL-JSON, user YAML and config.
Stdlib `dataclasses` remain the norm for internal value objects, and no recommendation
here proposes changing that. The reconciliation of `CLAUDE.md:64` is **tracked in
#169** and has not landed, so this audit reports the repository as it stands.

Two things verified rather than assumed:

- **The "no Rust-binary conflicts" rationale does not apply.** The CLI is installed
  *isolated* from the consumer's environment — `resources/ensure-tooling.md:56`: "never
  the consumer repo's project env. This is what lets `defendable-science` depend freely
  on `typer` / `requests` / `pyyaml` / `pooch` without touching anyone's torch/jax
  install."
- **The "keep the wheel light" rationale is already breached by an existing dependency.**
  `pyyaml` ships a compiled C extension (`_yaml`; `yaml.CSafeLoader` present) at **3.1 MB
  installed — larger than `rich` at 2.7 MB**. And the four "exactly" runtime dependencies
  resolve to fourteen packages via `typer → rich → markdown-it-py`, `pooch →
  platformdirs`, and so on.

The **finding** that stands regardless of the decision is a governance one, reported in
[`plugin-tech-debt.md`](plugin-tech-debt.md) PL-5c: the prohibition is restated in
**fourteen places** — `CLAUDE.md:64`, three ADRs, one design proposal (twice), three
source docstrings, and five superpowers plans — and **no ADR ever established it**.
`decisions/0031-config-driven-cache-dir.md:32` cites "(ADR rejecting it stands)", a
**dangling reference to an ADR that does not exist**. A governing constraint that lives
only in contributor guidance, is cited secondhand as a decision record, and has no
context/drivers/rejected-alternatives write-up cannot be revisited on the evidence —
which is precisely what an ADR set exists to make possible.

---

## The other six reports

| File | Contents |
|---|---|
| [`project-brief.md`](project-brief.md) | The research-methodology domain, the actors and agency/access-control model, every core entity and state machine, the trigger→effect automation tables, and a domain glossary |
| [`be-tech-debt.md`](be-tech-debt.md) | Package internals — 16 findings: traversal, atomicity, subprocess timeouts, key-store modes, N+1 HTTP, repeated parses, validation gaps, `cast()` misuse, type weaknesses |
| [`api-tech-debt.md`](api-tech-debt.md) | The CLI + JSON contract — 12 findings: response shapes, skill drift, exit codes, pagination, versioning, error models |
| [`data-tech-debt.md`](data-tech-debt.md) | The git-native artifact layer — 13 findings: transaction boundaries, schema authority, migration, indexes, cache policy, append-only evidence |
| [`coverage.md`](coverage.md) | The measured result, then coverage *quality*: weak/strong per module, all six pragmas, the live suite, fixture realism, edge cases, and a mutation spot-check |
| [`plugin-tech-debt.md`](plugin-tech-debt.md) | The markdown deliverable — 11 findings: the bootstrap, domain-neutrality, ADR hygiene, doc staleness, packaging, skill structure |

Plus [`AUDIT-PROMPT.md`](AUDIT-PROMPT.md) — the spec that produced these reports,
kept so the audit can be **re-run after fixes** and the results compared. It
carries the stack remapping, the calibration rules, the known-good sites not to
churn, the sanctioned decisions, and a re-run mode that classifies every prior
finding as fixed / persisting / new.

---

## Closing assessment

This repository is **six weeks old** and already has a 100 %-branch coverage gate that is
not theatre, a strict-mypy-clean 17 kLOC package, 41 ADRs with rejected alternatives, and
a failure-honesty model I would hold up as a reference implementation. That is a genuinely
unusual standard, and the audit should not be read as saying otherwise.

The debt has one clear shape. **The package's internal discipline outran the discipline
applied to its public surfaces.** Six months of careful reasoning went into whether an
unreachable mirror is the same as an absent file — and none into whether every command
answers "did this succeed?" the same way. Six invariants are enforced by tests inside
`defendable_science/`, and zero across the boundary to the eleven markdown clients that
consume it. That is why four documented invocations are broken, why the bootstrap names a
version that does not exist, and why five JSON conventions accreted without anyone having
to decide whether that was allowed.

The fix is not more discipline. It is **pointing the existing discipline at the
boundary**: the two tests in recommendations 1 and 2 would have caught the two
certain-likelihood risks in the table above, and cost roughly an afternoon.
