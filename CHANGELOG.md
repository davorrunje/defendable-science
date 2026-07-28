# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Former name.** Entries before `0.2.0` refer to this project under its
> previous name, `honest-scholar`. Those releases really did ship under that
> name and are left unedited (ADR-0035).

## [Unreleased]

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
  `davorrunje/defendable-science` (GitHub redirects the old URLs)

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
