# Audit prompt

The spec that produced the reports in this directory, kept here so the audit can
be **re-run after fixes** and the results compared. Hand this file to an agent
working in an isolated git worktree.

It is deliberately adapted to *this* repo. A generic web-app audit template
(FastAPI roles, SQLAlchemy models, Alembic migrations, Celery tasks, async
patterns) does not fit and produces invented findings; § Stack reality records
how each of those categories was remapped, and every remapping is load-bearing.

**First run:** 2026-08-29, against `main` at `baae091`. Result: 6.5 / 10.

---

## Ground rules

- **Audit only.** Do not modify, refactor or "fix" any source file, test, config
  or doc. The only files you create are under `.codebase_audit/`.
- **Do not open GitHub issues.** The report is the deliverable; recommendations
  live in it. The maintainer triages and files.
- **Cite `path/to/file.py:LINE` for every finding.** A finding without a line
  citation is not a finding. Verify each citation by reading the file — never
  cite from memory, and never trust a line number you did not confirm after your
  last edit to your understanding of the file.
- **Provide concrete fix snippets**, showing current code and proposed
  replacement — not prose descriptions of a fix.
- **Systemic issues only.** Recurring patterns, or single issues with broad blast
  radius. No one-off nitpicks.
- **No code style or formatting findings.** ruff, a strict pre-commit stack and
  strict mypy already handle that. Nothing about line length, import order, quote
  style, naming or docstring formatting.
- **No architectural rewrites.** Identify debt and gaps. Do not propose replacing
  Typer, adding a database, introducing async, or removing Pydantic from the
  parsing boundary (see § Sanctioned decisions).
- **Be calibrated, in both directions.** This repo has genuinely high discipline
  in places — a 100% branch-coverage gate, strict mypy, 40+ ADRs, a deliberate
  failure-honesty posture. Do not manufacture severity to fill a template; if a
  category has no real finding, say so in one line and move on. Equally, do not
  soften a real problem. A short report of true findings beats a padded one.
  *The first run's most useful moves were downgrades:* `cli.py` is 3,500+ lines
  but no function exceeds McCabe 10, so the god-module concern was reported Low
  with the measurement attached; and a mutation spot-check killed 7/7
  non-equivalent mutants, so the report states the coverage gate is not theatre.
- **Where a category has no analogue, write "Not applicable — <one-line why>"**
  rather than inventing a finding.
- **Weight severity by research integrity.** This tool exists to produce
  defensible scientific claims. A silent wrong value that enters the record is
  categorically worse than a crash: a traceback announces itself, a plausible
  wrong answer does not. Rank accordingly — the first run ranked one
  silent-wrong-value defect above four tracebacks on exactly this reasoning.

## Stack reality

Verify anything you doubt, but do not re-derive from scratch.

Two independently-versioned artifacts:

1. **The plugin** (repo root) — the *primary* deliverable. Markdown skills in
   `skills/<name>/SKILL.md`, plus `resources/` (contracts, templates, rigor,
   references), `docs/design/`, `decisions/` (MADR ADRs), `.claude-plugin/`.
2. **The package** (`defendable-science/`, module `defendable_science/`) — a
   Typer CLI the skills shell out to. Published to PyPI, installed **isolated**
   from the consumer's ML env.

There is **no** web framework, **no** ORM, **no** database, **no** Alembic, **no**
Celery/Redis/S3 and **no** async. Runtime deps are `typer`, `requests`, `pyyaml`,
`pooch`, plus the optional `rclone` binary invoked as a subprocess.

| Generic audit category | This repo's analogue |
| --- | --- |
| REST API surface | The `defendable-science <group> <cmd>` tree and **the JSON each command emits** — skills parse it, so a shape change is a breaking API change |
| HTTP status codes | Exit-code discipline: does every failure exit non-zero, and are failure classes distinguishable? |
| Roles / auth / middleware | The agency boundary — what the agent may decide vs. what needs a human signature; `defend`; the trusted/gated/quarantine tiers; API-key handling |
| Rate limiting | Outbound politeness: OpenAlex polite pool, User-Agent, backoff on 429/5xx |
| ORM / models / migrations | Git-native files: YAML frontmatter, CSL-JSON, Croissant manifests, an on-disk HTTP cache, a key store, a literature registry |
| Missing indexes | Full-directory walks and registry rescans per invocation; cost as a consumer repo grows to hundreds of papers |
| Transaction boundaries | Atomicity of multi-file writes; the write-temp-then-rename idiom, applied consistently or not |
| Migrations | Artifact schema evolution in *already-initialised consumer repos*: no schema-version field, no upgrade path, `research-init adopt` behaviour on pre-existing files |
| Soft delete | Whether the evidentiary audit trail is ever destructively overwritten |
| Async / concurrency | Blocking-I/O discipline (timeouts, retry, subprocess handling) and partial-write races |
| N+1 queries | Redundant uncached network round-trips and repeated filesystem walks |
| Pydantic validation | Hand-rolled parsing of untrusted external input — see § Sanctioned decisions |
| Raw SQL injection | `yaml.load` vs `safe_load`, path traversal from externally-derived names, zip-slip, rclone argument injection, URL/query construction from unescaped input |
| Coverage % by module | Coverage *quality* — the gate already forces 100% (see § Coverage) |

## Sanctioned decisions

Things that look like findings but are settled. Do not report them as debt.

- **Pydantic is permitted at the external-input parsing boundary** — third-party
  API responses, and disk formats a human or outside party authored (Croissant,
  CSL-JSON, YAML frontmatter, `config.yml`, the key store). It is **not** a
  general model layer: internal value objects stay stdlib `dataclasses`, and a
  `ValidationError` must be caught at the boundary and degraded into an explicit
  failure signal, never a traceback or a silent default. Tracked in **#169**.
  - At the time of the first run this was decided but not yet recorded, so
    `CLAUDE.md` still carried a blanket "Pydantic is deliberately rejected" and
    several ADRs cited it secondhand. **Check whether #169 has landed** before
    reporting that inconsistency.
  - Do **not** recommend Pydantic for sites that already validate honestly.
    Several do — see § Known-good.
- **Engineering is delegated** via the contract in ADR-0023. The plugin never
  implements design/plan/code, and that is deliberate.
- **`progress` never emits a score.** No rolled-up number, percentage or
  completion bar; gaps are named, never counted (ADR-0014, ADR-0041). A
  "missing summary metric" is not a finding, it is the design.
- **The dashboard has no timestamp** (ADR-0041), so regeneration is byte-stable.
- **`resources/templates/` is guarded against `scaffold/status.py`** by
  `tests/test_status.py`, because the wheel cannot read plugin content
  (ADR-0026). The status block has a single definition; do not report it as
  four-way drift.

## Known-good — do not recommend churning these

The first run's most important calibration. These already do the right thing;
report them under "Positive patterns to preserve", not as debt:

- `core/keys.py:170-184`, `literature/registry.py:290-307`, `cli.py:1805-1823`,
  `cli.py:2383-2395`, `cli.py:2774-2800` — JSON parsers that `isinstance`-check,
  raise typed domain errors naming the file, and distinguish malformed from
  absent.
- `core/config.py:81-98`, `literature/registry.py:505-516`,
  `digest/artifact.py:256-271,385-390`, `progress/collect.py:456-490`,
  `dataset/manifest.py:301-330` — the YAML equivalents. `progress/collect.py`
  separates unreadable / invalid / missing-key / wrong-type, each with a remedy.
- `core/frontmatter.py` — a deliberately host-preserving *line editor* that
  refuses a write it cannot round-trip. Replacing it with a YAML round-trip
  would destroy user comments and key order. Never recommend that.
- `core/http.py:169-180` — write-temp-then-rename on the cache. The pattern
  other write sites should follow.

## Open issues — cite, do not re-recommend

Check each is still open before relying on this list; if one has landed, verify
the fix rather than repeating the finding.

- **#169** — Pydantic ADR + adoption at the JSON boundaries. Covers six verified
  defects in `literature/graph.py`, `literature/acquire.py` and `cli.py:1549`.
- **#171** — the YAML boundaries: the status-block enums are declared in
  `scaffold/status.py` but enforced only in `check/checks.py`, so `progress`
  renders an invalid `verdict` as though it were a decision.
- **#173** — the silent-wrong-value sites outside #169: the unescaped OpenAlex
  `filter` in `acquire.py:713` and the `str()` coercion in `dataset/manifest.py`.

Where a finding of yours matches one of these, note "tracked in #NNN" beside it.
Where it does not, report it normally. **Audit independently — do not skip a
finding because you assume an issue covers it, and say so if you disagree with
one.** A second run that only echoes the first is worth nothing.

## Setup — measure, do not assume

```bash
cd defendable-science && uv sync
uv run pytest -q                       # hermetic suite + coverage
uv run mypy                            # strict
uv run ruff check                      # for C901 complexity counts only, NOT style findings
uv run bandit -r defendable_science/
cd .. && ./tools/validate-plugin.sh
git log --format='%an|%ae|%ad' --date=short
git log --merges --format='%s'
```

Also read `.github/workflows/`, `.pre-commit-config.yaml`, `codecov.yml`,
`tools/`, `RELEASING.md`, `CONTRIBUTING.md`, `STATUS.md`.

**Measure every metric yourself.** The first run was handed baseline numbers that
were wrong (a truncated `find` had undercounted the package by twelve files) and
correcting them was the right call. Do not carry numbers forward from the
existing reports either — recount, and note any drift. Never present an
unmeasured number as measured; if a command fails or is slow, say what happened.

Alembic is absent; record that explicitly in `data-tech-debt.md` and audit the
real analogue (artifact schema evolution) rather than skipping the section.

## Deliverables

Seven files in `.codebase_audit/`. The seventh is not optional — the plugin is
the primary deliverable and is invisible to pytest, mypy and ruff.

1. **`executive-summary.md`** — rating out of 10 with a weighted scoring table
   over: architecture & plugin↔package boundary; test-suite quality (not raw
   coverage %); code duplication; CLI/JSON-contract design; artifact/data model;
   failure honesty & degradation; dependency management & supply chain;
   git/DevOps/release discipline; bus factor & contributor scaling;
   documentation & ADR discipline. Plus: contributor table (with merge-commit
   analysis and how many merged PRs carry a review record); project metrics;
   what works (4–6, cited); critical gaps (top 5–6, systemic, cited); risk table
   (risk · severity · likelihood · blast radius); recommendations grouped
   Immediate / Short-Term / Medium-Term; links to the other six.
   **Write this last**, so its scores are traceable to the detail files.
2. **`project-brief.md`** — domain documentation derived from the code and
   skills, not the README: the three nested levels and the exploration→resolution
   firewall; actors and the agency/access-control model with `file:line` for each
   enforcement point; every entity with attributes, statuses and state machines;
   an automation trigger→effect table; a concepts glossary.
3. **`be-tech-debt.md`** — package internals. God modules (quantify: functions
   per module, C901 hotspots); type-annotation weakness despite strict mypy
   (hunt `Any`, `cast(`, `type: ignore` — **`cast()` as a substitute for runtime
   validation is a package-wide pattern worth sweeping for**); exception
   handling and failure-honesty violations; blocking-I/O discipline and
   non-atomic writes; redundant network/filesystem work; dependency-injection
   claims vs. reality; hardcoded config/paths/magic strings; unvalidated
   untrusted input; the real injection surface; circular imports; global mutable
   state; duplication. End with "Positive patterns to preserve".
4. **`api-tech-debt.md`** — the CLI + JSON contract. Inventory every command's
   output shape and tabulate it; exit-code discipline; unbounded result sets;
   option validation; outbound politeness; thin/missing help text; key leakage
   into output, logs or cache; the plugin↔package compat pin; machine-readable
   error shapes; chatty commands. **Highest-value automated check: extract every
   `defendable-science …` / `dsci …` invocation from `skills/**`, `resources/**`
   and `docs/**`, and verify each command, subcommand and flag against the real
   Typer tree in `cli.py`.** The first run found four that do not run. Nothing
   tests this. End with "Positive patterns to preserve".
5. **`data-tech-debt.md`** — the git-native artifact layer, per the mapping
   table. Alembic explicitly N/A. End with "Positive patterns to preserve".
6. **`coverage.md`** — the gate forces 100% branch coverage, so grouping modules
   by percentage is a table of identical numbers. Report the measured result,
   then audit what a 100% gate structurally cannot catch: strongly vs. weakly
   asserted vs. incidentally covered; every `# pragma: no cover` and
   `exclude_also` pattern judged individually; what only `@pytest.mark.live`
   exercises; whether fixtures are recorded responses or idealised hand-written
   ones; concurrency and crash-recovery; malformed/`null`/huge/unicode inputs;
   whether the hand-rolled parsers are fuzzed; test-suite duplication; and the
   untested plugin half. A mutation spot-check is worth doing if cheap — the
   first run hand-built a harness in `/tmp` and covered one module.
7. **`plugin-tech-debt.md`** — skill consistency and firewall integrity;
   domain-neutrality violations; skill↔CLI drift from the plugin side;
   duplication across skills and `resources/`; the `ensure-tooling.md` bootstrap
   and its compat pin; ADR hygiene (superseded-but-unmarked, and material
   decisions in the code with no ADR); spec-vs-reality drift in `docs/design/`;
   packaging and the two-artifact versioning rule (ADR-0026). End with "Positive
   patterns to preserve".

## Method

1. Set up, run the tooling, collect real numbers.
2. Deep-read the package **and** the plugin before writing anything, so findings
   are consistent and cross-references accurate.
3. You may parallelise drafting after that shared pass, but you own final
   consistency: no contradictory claims between files, no duplicate findings
   presented as distinct, every citation verified. Read everything a subagent
   produces before committing.
4. Cross-link the reports; write the executive summary last.

## Re-run mode

When a previous report set exists in this directory, additionally:

- **Classify every prior finding** as `fixed` / `partially fixed` / `persisting`
  / `no longer applicable`, with the evidence. A finding marked fixed needs the
  commit or PR that fixed it and a citation showing the current code.
- **Verify, do not assume.** A closed issue is not proof; read the code.
- **Say what got worse.** New debt since the last run matters as much as
  progress, especially in modules that were recently touched.
- Add a short **`delta.md`** (an eighth file) leading with the score change and
  the fixed/persisting/new counts, then the per-finding table. Keep the seven
  main reports current in themselves — a reader should not have to reconstruct
  the present state by replaying deltas.
- Re-measure every metric and note drift from the previous run's figures.

## Finishing

Open a PR with the local **`create-pr`** skill (`.claude/skills/create-pr/`).
Never commit to `main`. Commit only `.codebase_audit/`; verify with `git status`
that nothing else is staged. Authored **Davor Runje `<davor@synthpop.ai>`** with
the `Co-Authored-By: Claude` trailer — these are not skill-produced research
artifacts, so the discovery trailers do not apply. No `Closes #`.

In the PR body: state it is documentation-only, give the headline rating (and
the delta on a re-run), summarise the top findings with links into the report
files, and list anything you could not complete and why.
