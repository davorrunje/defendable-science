# honest-scholar — Decision Log (ADRs)

MADR-style Architecture Decision Records for the `honest-scholar` plugin. Each records
the context, the options considered, the rejected alternatives **and why**, and
links to the spec section + grounding digest. Captured 2026-07-17 during the
design session; the reasoning here is not reconstructable from the specs alone.
Migrates to the plugin's `decisions/` alongside `resources/references/`.

> Purpose beyond the record: this log is the raw material for a planned blog
> post / paper explaining the skills and the reasoning behind them — the intent
> is eventually to write that *using* `honest-scholar` (`paper-synthesis` + `defend`).

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-separate-plugin-repo.md) | Package the workflow as a standalone plugin, not in-mononet | accepted |
| [0002](0002-scientific-scope-only.md) | Scientific scope only; engineering delegated via a contract | accepted |
| [0003](0003-agency-principle.md) | Agency principle — assistants, not researchers | accepted |
| [0004](0004-understanding-principle-and-defend.md) | Understanding principle + the `defend` skill | accepted |
| [0005](0005-three-level-mirror.md) | Three-level mirror; thesis as a partial mirror | accepted |
| [0006](0006-two-skills-per-level.md) | Two pipeline skills per level (generate/resolve) | accepted |
| [0007](0007-literature-one-skill-two-modes.md) | `literature` = one skill, scout/position modes | accepted |
| [0008](0008-literature-bib-plus-triage.md) | Literature registry = standard bib + triage sidecar | accepted |
| [0009](0009-dataset-thin-manifest.md) | `dataset` one skill + thin `datasets.yml` (reject DVC/DataLad/lakeFS) | accepted |
| [0010](0010-storage-tiers.md) | Tiers A/B/C by (license × access); mirror ≠ redistribution grant | accepted |
| [0011](0011-rclone-mirror-sha256.md) | rclone private mirror; SHA-256 authoritative fixity | accepted |
| [0012](0012-shared-substrate.md) | Shared asset substrate — share the mechanism, not the file | accepted |
| [0013](0013-experiment-backend-contract.md) | Experiment-backend *contract* + pluggable backend | accepted |
| [0014](0014-progress-cross-cutting.md) | `progress` cross-cutting; semantic roll-up; anti-Goodhart | accepted |
| [0015](0015-defend-cross-cutting.md) | `defend` cross-cutting; guardrail stop-and-confirm; teaching; non-grading | accepted |
| [0016](0016-mentor-personas.md) | Mentor personas author-selectable; no personality inference | accepted |
| [0017](0017-research-init-one-skill.md) | `research-init` one skill, init/adopt modes | accepted |
| [0018](0018-git-native-source-of-truth.md) | Git-native plain text as source of truth; cross-repo out of scope | accepted |
| [0019](0019-public-plugin-visibility.md) | Public plugin, named `honest-scholar` | accepted |
| [0020](0020-bib-format-csl-json.md) | CSL-JSON source of truth; BibTeX exported on demand | accepted |
| [0021](0021-thesis-gate-per-gap-confirmation.md) | Thesis gate — per-gap acknowledged confirmation | accepted |
| [0022](0022-license-apache-2.0.md) | License the plugin under Apache-2.0 | accepted |
| [0023](0023-engineering-delegation-contract.md) | Delegate engineering via a contract, not a named tool | accepted |
| [0024](0024-tooling-package-and-bootstrap.md) | Supporting tooling = one package (Typer CLI, optional MCP) + markdown `ensure-tooling` bootstrap | accepted |
| [0025](0025-disclosure-and-citation-growth.md) | Honest AI-use disclosure + citation as the growth mechanism (auto-proposed by `paper-synthesis`) | accepted |
| [0026](0026-independent-versioning-compat-pin.md) | Independent plugin/package versioning with a compatibility pin | accepted |
| [0027](0027-release-driven-oidc-publish.md) | Publish via GitHub Releases + PyPI Trusted Publishing (OIDC, no tokens) | accepted |
| [0028](0028-100-percent-coverage-gate.md) | 100% statement + branch coverage gate on the package | accepted |
| [0029](0029-api-key-handling.md) | Unified API-key handling — a CLI-managed JSON store (not `.env`), stdin writes, scoped in-memory env for children | accepted |
| [0030](0030-docs-site-mintlify.md) | Docs site on Mintlify, published from a generated docs repo to `honest-scholar.science` | accepted |
| [0031](0031-config-driven-cache-dir.md) | Source the cache root from `config.yml` (`cache_dir:`), not a hardcoded literal | accepted |
| [0032](0032-keys-store-outside-repo-by-default.md) | Key store defaults outside the repo (XDG); in-repo store is an explicit, gitignored opt-in with a committable-store runtime guardrail | accepted |

Format: MADR (Markdown Any Decision Records). Deciders: Davor Runje (with Claude).
