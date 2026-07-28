# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`defendable-science` ships **two independently-versioned artifacts** — this split is the single most important thing to understand:

1. **The plugin** (repo root) — the primary deliverable. Markdown **skills** (`skills/<name>/SKILL.md`) plus `resources/`, the design record, and `.claude-plugin/{plugin.json,marketplace.json}`. Pure markdown; distributed as a git self-marketplace. Versioned by `plugin.json` (semver).
2. **The `defendable-science` package** (`defendable-science/` subdirectory) — a **Typer CLI** the skills shell out to. Published to PyPI, installed **isolated** from a consumer's ML env. Versioned by `defendable-science/pyproject.toml` (PEP 440).

They release on separate cadences; the plugin pins a compatible package range in [`resources/ensure-tooling.md`](resources/ensure-tooling.md) (ADR-0026). Do **not** lock the two versions together, and do not bump `plugin.json` from the package's version-bump automation.

This is guidance for **working on this repo**. It is *not* a shipped artifact and must stay out of the plugin's domain-neutral content.

## Read-first orientation

- [`docs/design/00-meta-spec.md`](docs/design/00-meta-spec.md) — the whole picture (identity, the nested-lifecycle architecture, the plugin↔consumer boundary). **Read this before touching design or skills.** Sub-specs are `docs/design/01-04`; CLI-module designs are `docs/design/proposals/`.
- [`decisions/`](decisions/) — MADR ADRs (index in `decisions/README.md`). The *why* behind material choices, with rejected alternatives. **Any material design decision gets a new ADR** here (append to the index).
- [`CONTRIBUTING.md`](CONTRIBUTING.md), [`RELEASING.md`](RELEASING.md) — contributor + release mechanics. Don't restate them; link.

## Architecture (the big picture)

**The methodology (plugin skills).** One object×action shape across three nested levels, each with a *generate* (propose) and *resolve* (dispose) skill, behind an exploration→resolution **firewall** (no skill both proposes a claim and adjudicates it):

- hypothesis (within a paper): `hypothesis-exploration` → `hypothesis-testing`
- paper (portfolio): `paper-exploration` → `paper-synthesis`
- thesis (optional top): `thesis`

Cross-cutting: `progress` (reads status frontmatter → dashboard; never a productivity score), `defend` (Socratic tutor-examiner guardrail), and `digest` (defend's inbound counterpart — verified comprehension of external papers). Shared capabilities: `literature`, `dataset`. Onboarding: `research-init` (`init`/`adopt`). Two load-bearing principles run through everything: **agency** (the human makes and signs every material decision) and **understanding** (`defend` verifies + teaches before a decision is recorded). *Engineering* (design/plan/code) is deliberately **delegated** to a bound backend via the engineering-delegation contract (ADR-0023) — the plugin never implements it.

**The package mirrors the skill verbs.** `defendable-science/defendable_science/` (note the underscore): `core/` (a caching `requests` HTTP client + config), `literature/graph.py` (OpenAlex + Semantic Scholar), `dataset/{manifest,retrieval}.py` (manifest/Croissant + pooch/rclone fixity), `defend/record.py`, `exploration/backlog.py`, `cli.py` (the authoritative Typer tree). Each command emits JSON; skills call `defendable-science <group> <cmd>` after the `ensure-tooling` bootstrap. Kernels/parsers are pure and injectable (HTTP transport, the rclone `run`, the Tier-B fetcher) so everything is tested without network or the rclone binary.

## Commands

Package work runs from the **`defendable-science/` subdirectory**:

```bash
cd defendable-science
uv sync                                          # install / sync
uv run pytest -q                                 # full suite — enforces 100% branch coverage
uv run pytest tests/test_literature.py::test_resolve_openalex  # a single test
uv run ruff check      # lint      (or ./tools/lint.sh from root)
uv run ruff format     # format
uv run mypy            # strict    (or ./tools/typecheck.sh from root)
```

- **100% statement+branch coverage is a hard gate** (`fail_under = 100`, ADR-0028). New code lands with the tests that cover it, including error/degradation branches. `# pragma: no cover` only for genuinely unreachable branches, with a reason.
- **Live/integration tests are opt-in** and skipped by default (`@pytest.mark.live`). They hit real OpenAlex/S2 + real pooch/rclone: `DEFENDABLE_SCIENCE_LIVE=1 uv run pytest -m live --no-cov` (rclone tests skip if the binary is absent). The hermetic suite + coverage gate stay intact without them.

From the repo root (plugin side):

```bash
./tools/validate-plugin.sh          # claude plugin validate (structural fallback if the CLI is absent)
pre-commit run --all-files          # ruff, mypy, codespell, bandit, detect-secrets
/plugin marketplace add ./ && /plugin install defendable-science@defendable-science   # test-install the plugin
```

## Conventions

- **Never commit to `main`** — it is protected. Branch, then open a PR (see `PULL_REQUEST_GUIDE.md`).
- **Material design decisions → a MADR ADR** in `decisions/` (context · drivers · options · decision · consequences · rejected alternatives), linked from `decisions/README.md`.
- **Follow-ups become self-contained GitHub issues** — a future session has only the repo + the issue text, so include the context, exact `file:line` locations, and acceptance criteria to complete it cold. Don't leave deferred work only in a spec, PR comment, or `TODO`. Use the local **`create-issue`** skill ([`.claude/skills/create-issue/`](.claude/skills/create-issue/SKILL.md)), which encodes this house standard (open + close); open PRs with the **`create-pr`** skill ([`.claude/skills/create-pr/`](.claude/skills/create-pr/SKILL.md)).
- **Code style**: Python 3.11+, line length 88, **MyST field-list docstrings** on public API (`:param:`/`:returns:`/`:raises:`; types come from annotations), strict mypy, stdlib `dataclasses` for value objects. **Pydantic is deliberately rejected** (keep the wheel light, no Rust-binary conflicts) — do not reintroduce it. Ground methodology claims in `resources/references/` digests.
- **Failure honesty**: this is an integrity tool — never let a failure or uncertain condition be silently reported as a legitimate empty/negative/complete result, and never let a transient error surface as a raw traceback. Distinguish "failed" from "legitimately empty"; degrade with an explicit, actionable signal.
- **Domain-neutrality**: no ML-, monotonic-network-, or consumer-repo-specific assumptions in the plugin. Consumer specifics live in the consuming repo's config/content.
- **Commits**: dev commits are authored **Davor Runje `<davor@synthpop.ai>`** with a `Co-Authored-By: Claude …` trailer. Commits of *skill-produced artifacts* additionally carry the discovery trailers in [`resources/commit-attribution.md`](resources/commit-attribution.md).

## Development posture

This repo is built with the [`superpowers`](https://github.com/obra/superpowers) workflow (brainstorming → writing-plans → implementation), enabled in `.claude/settings.json`. That is a maintainer choice for building *this* plugin; **using** `defendable-science` requires no engineering tool (engineering is delegated via the contract, ADR-0023). The author is Davor Runje — default to a senior-collaborator tone.
