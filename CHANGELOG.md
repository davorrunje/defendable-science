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

### Changed

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

- `skills/literature/SKILL.md` §Tooling no longer claims a PRISMA-log or
  concept-matrix generator that was never implemented; the CSL-JSON registry
  loader/patcher and triage sidecar reader it also claimed are real as of
  this release.

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
