# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Former name.** Entries before `0.2.0` refer to this project under its
> previous name, `honest-scholar`. Those releases really did ship under that
> name and are left unedited (ADR-0035).

## [Unreleased]

### Added

- **`literature fetch | confirm | verify | mirror`** — the literature registry
  now closes the same PDF-provenance loop `dataset` already had: `fetch`
  acquires a paper's PDF through a generic acquisition ladder (OpenAlex
  locations, PDF-serving landing pages, sibling-version and arXiv search, an
  empty-by-default `venue_resolvers` config hook), `confirm` promotes a
  quarantined candidate or adopts a manually downloaded PDF, `verify` re-hashes
  on-disk bytes offline, and `mirror` pushes to / probes the configured rclone
  remote. Every search-derived candidate passes a three-way match gate
  (accept / quarantine / refuse) with first-author family name as a hard
  gate, so a wrong-author false positive is refused rather than silently
  bound to a citekey (see ADR-0037). `fetch` never writes PDF bytes into the
  consumer's repository, under any flag. This is the tooling `skills/digest/
  SKILL.md` step 1 required but that did not previously exist.
  A download that fails is never filed as "this paper has no PDF": each failure
  is recorded per URL in the report's `failures[]`, a blocked ladder is an
  `errors[]` row (exit 1) rather than a `manual[]` one, and a `429` from a PDF
  host aborts the sweep with `complete: false` exactly as a metadata throttle
  does.
- **The consumer layout is recorded once, and every command resolves paths from
  it** ([ADR-0039](decisions/0039-recorded-consumer-layout.md)). The tree was
  previously restated in each command's options and in nine documents, so the
  caller had to know it: `backlog list` wanted `--backlog`, `promote --scaffold`
  wanted `--paper-root` or `--research-root`, and `dataset` wanted `--manifest`.
  All of them now derive their paths from one definition, and a repo that
  diverges from the default tree records the divergence in an optional four-key
  `layout:` block in `.defendable-science/config.yml` — `research_root`,
  `literature_dir`, `datasets_manifest`, `thesis_dir`. Omitted keys keep the
  default so a conventional repo records nothing; an unknown key is an error
  rather than a silent no-op, and a path escaping the work tree is refused
  outright. Explicit options still win where they exist.
  The repository root is now discovered by walking up from the cwd, so every
  command behaves the same from a paper directory as from the top. That fixed
  two ways paths could land in the wrong place: the root was being derived as
  `research_root.parent.parent`, which is correct only for the default
  `docs/research` and silently wrong for any other research root, and a relative
  `cache_dir` was anchored to the cwd, so `dataset fetch` run from a
  subdirectory wrote its cache into a directory `research-init` had never
  gitignored. Relative `cache_dir`, `literature.registry` and `literature.triage`
  values all anchor to the repo root now.
- **`defendable-science init [--root PATH] [--thesis] [--dry-run]`** — scaffolds
  a consumer repo, rendering every machine-read file from the package that
  already owns its shape rather than from prose an agent retypes. A
  prose-scaffolded repo was dead on arrival: both backlog tables carried headers
  no column profile accepts and `papers.md` an invented fourth column, so
  `backlog park` and `backlog promote --scaffold` both failed on a freshly
  onboarded repo. `init` writes `papers.md`, the portfolio backlog,
  `references.json`, `triage.yml`, `datasets.yml`, `config.yml`,
  `rclone.conf.example` and a `dashboard.md` stub — and with `--thesis` the
  thesis aims stub, `milestones.yml` and `kappa/` — each asserted in the test
  suite against the loader that consumes it, so two runs agree and the result
  parses.
  It is idempotent and non-destructive: a file already present is reported
  `exists` and left exactly as the author wrote it, which is why there is no
  `--force`; `.gitignore` is the single exception and is merged append-only.
  `--dry-run` produces the report a real run would and writes nothing, and a run
  that fails prints no report at all — a partial scaffold must never read as a
  finished one. Unset machine-read fields are `null` or their empty collection,
  never a `<...>` placeholder: a placeholder parses as a real value, which is how
  a scaffolded `readiness: <synthesis | defensible>` used to reach `progress` as
  a real readiness. The dashboard stub says plainly that no generator has run
  rather than projecting a fabricated state.

### Changed

- **`docs/USER-GUIDE.md` restructured around the `Guides` nav group.** The single
  page carried a paragraph per capability and nothing deeper; five new
  per-capability guides now hold the depth it implied, following
  `docs/guides/literature.md`'s conventions:
  [`dataset`](docs/guides/dataset.md) (tiers as a license question, the
  resolution chain, the mirror, what `audit` checks beyond fixity),
  [`experiment-backend`](docs/guides/experiment-backend.md) (the four
  capabilities, what a minimal implementation looks like, why the plugin ships
  none), [`defend`](docs/guides/defend.md) (the three targets and what is
  off-limits in each, the persona levers, the evidentiary record),
  [`progress`](docs/guides/progress.md) (the four roll-ups and the Goodhart
  argument), and [`keys`](docs/guides/keys.md) (precedence, relocation, the
  plaintext-at-rest caveat). The user guide keeps onboarding plus the lifecycle
  walkthrough and links out.
  Every page now applies the literature guide's shell-block-vs-quote-block
  convention: `progress status`, `defend claim`, `hypothesis-exploration park`
  and `paper-exploration generate` were shown in bare code blocks that read as
  shell commands but are skill modes, and are now quote blocks with the real
  `defendable-science backlog …` invocation alongside where one exists. (#103)
- **`backlog promote --scaffold` performs the handoff both exploration skills
  already documented.** The scaffolders existed and were tested, but no CLI
  command reached them — `backlog --help` listed only
  `park|add|list|rank|promote|drop`, and `promote`'s own docstring deferred
  scaffolding to "a follow-up step" that nothing implemented. Since skills reach
  the package only through the CLI, `promote` was a status flip and the entire
  handoff (paper root, `paper/pitch.md`, the per-paper `backlog.md`, the
  `papers.md` registry row, the hypothesis folder and `hypothesis.md`) had to be
  done by hand. `promote` now takes `--scaffold` plus the level's options
  (`--paper-root`, or `--research-root` + `--backend`; `--slug`/`--date` for the
  hypothesis folder name) and reports the created paths as
  `{"row": …, "artifacts": …}`. Scaffolding runs *before* the backlog is written,
  so a refused scaffold leaves the row `ranked` and retryable rather than
  `promoted` with nothing on disk. The flag is opt-in: plain `promote` still
  flips the status and emits the bare row, so `--backend` does not become
  mandatory on every paper-level promote (ADR-0013). (#113)
- **Substrate spine promoted to `custom.defendable-science`.** The PDF
  provenance record (`pid`, `files[]`, `license`, `mirror`, `acquisition`)
  lives under CSL-JSON's own `custom` namespace, not as top-level item
  properties — the CSL schema forbids the latter, which would have made
  `references.json` schema-invalid (ADR-0037). `docs/design/02-literature.md`
  §4 and `skills/literature/SKILL.md` are corrected to match.
- `sha256_file` / `blob_path` / `RetrievalError` and the rclone `Mirror`
  promoted from `dataset/retrieval.py` to `core/fixity.py` / `core/mirror.py`
  as shared substrate primitives; `dataset` behaviour is unchanged.
- `resources/ensure-tooling.md`'s compatible package range bumped to
  `>=0.3.0,<0.4.0` for the new verbs.

### Fixed

- **A promoted paper is tracked from the moment it is scaffolded.**
  `scaffold_paper` wrote a two-line `pitch.md` with no status frontmatter, while
  `scaffold_hypothesis` one level down wrote the full status block. Since
  `progress dashboard` is a *pure projection* of that frontmatter, a freshly
  promoted paper was registered in `papers.md`, had a root and a pitch, and
  contributed nothing to the dashboard until someone hand-wrote the block —
  registered but untracked. The pitch is now seeded from a `_PAPER_TEMPLATE`
  mirroring `resources/templates/paper/pitch.md`, carrying the backlog row's
  one-line and provenance and today's date; the prose stays the template's
  comment prompts, because a tracked *stub* is the goal and seeding prose the
  author did not write would cut against the agency principle. The plugin's
  `resources/` is not readable from the package — the wheel ships only
  `defendable_science` and the two artifacts release on separate cadences
  (ADR-0026) — so the duplication is deliberate and a test fails on any drift in
  the status block, for the hypothesis pair as well as the new paper one.
  `resources/templates/paper/pitch.md` gained the `## Provenance` section its
  hypothesis counterpart already had. (#96)
- **Rung 6 (`venue_resolvers`) no longer reports a verification it never
  performed.** `RUNG_VENUE` was in `GATED_RUNGS`, so every consumer-configured
  venue candidate ran through `evaluate_match` — but `venue_candidates` builds
  its candidate from the *anchor work*, the same OpenAlex record the citekey
  already resolved to. The gate was therefore comparing the registry entry
  against itself and could not do anything but pass, landing
  `{"verdict": "accept", "title": "exact", "author": "exact", "year": "exact"}`
  in the audit trail for a URL nothing had checked. Rung 6 is now recorded with a
  new `trusted` verdict and a reason naming the situation, with all three axes
  `null` because none was compared; `%PDF-` remains the only real constraint, and
  now the report says so. **Behaviour change:** rung 6 no longer inherits
  `evaluate_match`'s thin-metadata refusal — that refusal was about the entry's
  own metadata, not the consumer's template, so a resolver now applies even to an
  entry missing title/year/author. See ADR-0038 for why fetch-and-parse
  verification was rejected as disproportionate. (#105)
- **Suffix-less PDF-serving landing pages are recovered instead of dropped
  unseen.** The landing rung kept only `landing_page_url`s whose string ended in
  `.pdf`, so a publisher serving a PDF from an extension-less path (arXiv's
  `/pdf/2409.11078` is the observed shape) was filtered out before
  `looks_like_pdf`'s magic-byte check could accept it, and the paper went to
  `manual[]` for a human to click. `.pdf`-shaped URLs still come first and stay
  unbounded; up to `LANDING_SNIFF_LIMIT` (3) suffix-less ones now follow and are
  judged on their bytes. The cap is what keeps a work with a long `locations[]`
  array from turning into one round-trip per entry. (#104)
- **`backlog` no longer rewrites the documents it edits.** `Backlog.loads()` was
  prose-tolerant but `dumps()`/`save()` emitted only the table, so the
  `load → mutate → save` round trip behind every `backlog park|add|rank|promote|
  drop` deleted every non-table line — a heading and its explanatory prose gone
  on the first `park`. Worse, rows were parsed against the *file's* header but
  serialized against `columns_for(level)`, so a hand-written table with any other
  column layout was written back with its row count preserved and its cells
  **blank**: nothing looked wrong, and the content was gone. The parser now
  retains the prose before and after the table plus the file's own header, and
  `save` splices only the table region back. A mutation that a host header cannot
  carry (no `id`/`status`, or `drop` with no `note` column) raises
  `BacklogError` naming the missing columns and both layouts, rather than writing
  cells that serialization would drop; columns a consumer has *added* survive and
  are left empty on new rows. **Existing consumer backlogs may already carry this
  damage — check `git log -p` on your `portfolio-backlog.md` and `backlog.md`
  files.** (#94)
- **`promote` inserts the `papers.md` row into the registry table**, wherever that
  table sits in the document, instead of appending it at end-of-file with a
  hardcoded three-column shape. A registry documented with prose after the table
  got a stray row orphaned below the prose, and a registry extended with e.g.
  `readiness` / `covers (thesis aims)` columns got a ragged three-cell row; both
  meant the registry half of `promote` had to be done by hand. The row now
  matches the host header's column count with extra columns left empty, and a
  registry table missing `paper-id`/`root`/`backend`, or whose rows are not
  anchored by a GFM separator, is refused loudly rather than corrupted. (#95)
- **A minted backlog id is no longer cut mid-word.** The 40-character cap
  truncated blindly, yielding ids like
  `a-survey-of-monotonicity-methods-in-mach`; since a paper-level id becomes the
  `paper-id` keying the paper across backlog, registry, dashboard and `progress`,
  this made `--id` effectively mandatory. It now truncates on a word boundary.
  (#94)
- `skills/literature/SKILL.md` §Tooling no longer claims a PRISMA-log or
  concept-matrix generator that was never implemented; the CSL-JSON registry
  loader/patcher and triage sidecar reader it also claimed are real as of
  this release.
- **`codespell` and `detect-secrets` versions are authored in one place.** Each
  was pinned twice — a remote hook `rev:` in `.pre-commit-config.yaml` and a `==`
  pin in `defendable-science/pyproject.toml`'s `lint` group — on two independent
  Dependabot schedules (`pre-commit` and `uv`), which had already drifted once.
  Both now run as `repo: local` hooks via `tools/codespell.sh` /
  `tools/detect-secrets.sh`, leaving the `lint` group's pins as the single source
  of truth; `pre-commit-hooks` and `pyupgrade` are the only remote `rev:`s left.
  Hook behaviour is unchanged (same `args`, same `exclude`). (#79)

## [0.2.0] - 2026-07-28

**The project is renamed from Honest Scholar to Defendable Science** (ADR-0035).
The name now describes what the tool verifies — that the work can be defended —
rather than a virtue it cannot audit. This is a breaking change for every
consumer.

### Changed — BREAKING

- **Plugin install**: `/plugin install honest-scholar@honest-scholar` →
  `/plugin install defendable-science@defendable-science`
- **CLI**: `honest-scholar` → `defendable-science`; short alias `hsch` → `dsci`
- **PyPI distribution**: `honest-scholar` → `defendable-science`.
  `uv tool uninstall honest-scholar && uv tool install defendable-science`
- **Python module**: `honest_scholar` → `defendable_science`
- **Project config dir**: `.honest-scholar/` → `.defendable-science/`
  (rename it by hand; also update your `.gitignore`)
- **Environment variables**: `HONEST_SCHOLAR_KEYS_PATH` →
  `DEFENDABLE_SCIENCE_KEYS_PATH`, `HONEST_SCHOLAR_LIVE` →
  `DEFENDABLE_SCIENCE_LIVE`
- **Commit trailer**: `HonestScholar-Skill:` → `DefendableScience-Skill:`
- **Docs**: `honest-scholar.science` → `defendable.science`
- **Repository**: `davorrunje/honest-scholar` →
  `davorrunje/defendable-science`

### Removed

- The `honest-scholar` PyPI and TestPyPI distributions are **abandoned with no
  forwarding release**. `0.1.1` remains their final version. There is no
  deprecation shim; migrate with the steps above.

## [0.1.1] - 2026-07-21

Package patch (metadata + docs). The plugin is unchanged (still `0.1.0`).

### Fixed

- PyPI project links: `Documentation` now points to a distinct URL
  (`honest-scholar.science/get-started/user-guide`) so it renders separately from
  `Homepage` (both previously pointed at the same URL, which PyPI collapsed).

### Changed

- Package README describes the honest failure handling (retry + `Retry-After`,
  distinct actionable errors, never a silent miss or a traceback) instead of the
  vague "degrade gracefully".

## [0.1.0] - 2026-07-19

First public release — a Claude Code plugin for the scientific research workflow,
plus the `honest-scholar` CLI it calls. The two artifacts are versioned
independently (ADR-0026); this is `0.1.0` for both.

### Added

- **Plugin — 10 skills** across the nested generate/resolve lifecycle:
  `hypothesis-exploration` / `hypothesis-testing`, `paper-exploration` /
  `paper-synthesis`, `thesis`, the shared `literature` and `dataset` capabilities,
  cross-cutting `progress` and `defend`, and `research-init` onboarding — behind
  the exploration→resolution firewall and the agency + understanding principles.
  Distributed via the repo's git self-marketplace.
- **`honest-scholar` package** (PyPI, installed isolated) — a Typer CLI with fully
  implemented groups: `literature` (OpenAlex + Semantic Scholar citation graph),
  `dataset` (manifest / Croissant / SHA-256 retrieval / rclone mirror / audit),
  `defend record`, `backlog`, `doctor`, `keys`, and `--version`. Strict mypy;
  **100% statement + branch test coverage** gate.
- Honest failure handling: rate-limit / transient errors are distinct from a
  genuine not-found and never surface as tracebacks; unified, gitignored API-key
  store (`keys`) with env-var precedence and least-privilege scoped env for child
  processes.
- **Rendered docs site** at [honest-scholar.science](https://honest-scholar.science)
  (Mintlify) — generated from the repo's markdown on release (user guide, skills,
  CLI reference, and the full design record), gated in CI by a real MDX compile +
  build-time and post-publish broken-link checks.
- **Design record**: the meta-spec + four sub-specs, 30 MADR ADRs, verified-source
  reference digests, and the visual identity.
- **Release & CI engineering**: independent plugin/package versioning with a
  compatibility pin (ADR-0026), GitHub-Release-driven PyPI publishing via Trusted
  Publishing / OIDC (ADR-0027), the 100% coverage gate (ADR-0028), a repo `CLAUDE.md`,
  and local `create-issue` / `create-pr` skills.
