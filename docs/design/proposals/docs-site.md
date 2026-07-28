# Proposal: rendered docs site (Mintlify)

`Status: designed 2026-07-19 · Skill: — (project infra) · Implements #6 · Decision ADR-0030`

## Context

For the pre-releases we shipped **no rendered docs site** (#6): the design record,
`README.md`, `docs/USER-GUIDE.md`, and the `defendable-science` CLI `--help` were the
documentation, all as in-repo markdown. As the plugin + package mature, a single
navigable site helps users and contributors. This proposes the site's tooling,
topology, and publish flow. (#6's body predates a rename and says
`scholar`/`scholar-tools`; the repo/package/CLI are all **`defendable-science`** —
reconciled here.)

## Decision (see ADR-0030)

Build the site with **Mintlify**, sourced from the in-repo markdown, published by
CI to a **dedicated docs repo** that Mintlify renders and serves at the custom
domain **`defendable.science`**.

Why Mintlify (full rationale + rejected alternatives — Quarto, Sphinx+MyST,
MyST-MD, Docusaurus/Starlight — in ADR-0030):

- **Ecosystem-native + proven**: Anthropic's own docs (claude.com/docs) run on
  Mintlify — a fitting, well-supported choice for a Claude-ecosystem tool.
- **Docs-as-code**: pages are markdown in git, so the **source of truth stays in
  the repo** (no hosted-provenance concern).
- **AI-native**: auto-served `llms.txt` + markdown export + MCP — apt for an
  AI-in-the-loop research tool.
- **Low maintenance / lowest lift**, and the scientific-publishing pipeline we'd
  get from Quarto/MyST-MD is **not needed** — the arXiv paper (#7) is a separate
  artifact with its own tooling.
- **Cost**: the free **Starter** tier includes a **custom domain**, AI search,
  analytics, web editor, auth, MCP; usage is metered by **AI credits (5,000/mo
  included)** — the one dimension to monitor (see Risks).

## Topology & publish flow

```
defendable-science (this repo)            defendable-science-docs (new, generated)      Mintlify
  README, USER-GUIDE, docs/design/,     docs.json + generated .mdx pages   ──▶  renders + serves
  decisions/, resources/, skills/,      (BUILD ARTIFACT — never hand-edited)     defendable.science
  defendable_science Typer CLI
        │  (source of truth)                     ▲
        └── CI build on Release ─── push ────────┘
```

- **Source of truth**: unchanged, in this repo. Nothing is authored in the docs
  repo by hand.
- **Docs repo** (e.g. `davorrunje/defendable-science-docs`): holds only the generated
  Mintlify site (`docs.json` navigation + `.mdx`/`.md` pages + assets). Mintlify
  connects to it and auto-redeploys on push.
- **Build**: a `docs-publish` workflow in *this* repo, triggered on
  **`release: published`** (reusing the release-driven pattern of ADR-0027) plus a
  manual `workflow_dispatch`, runs a builder script that:
  1. assembles the one-portal content from the source markdown,
  2. **generates the CLI reference** from the Typer app,
  3. writes `docs.json` (navigation),
  4. rewrites intra-repo relative links → site routes,
  5. pushes the result to the docs repo (deploy key / fine-grained PAT).
  Mintlify then redeploys → satisfies #6's "deploy on tag".

This gives release-gated, snapshot-able docs, keeps this repo free of Mintlify
config, and lets the builder transform content (link rewriting, CLI ref) before
publish. Because the docs repo is a **generated artifact**, #6's "no content
duplication" holds: one hand-maintained source, one generated render.

## Site scope (one portal)

Per the agreed scope — users **and** the design record:

- **Overview / landing** — from `README.md` (trimmed to the site).
- **Get started** — install (plugin marketplace + `defendable-science` CLI) + the full
  `docs/USER-GUIDE.md`.
- **Skills / methodology** (the star) — the nested generate/resolve lifecycle,
  the agency + understanding principles, the firewall, and per-skill pages sourced
  from `skills/*/SKILL.md`.
- **CLI reference** — `defendable-science` command tree, generated from the Typer app.
- **Design & reasoning** — the meta-spec + sub-specs (`docs/design/`), the ADRs
  (`decisions/`), the reference digests (`resources/references/`), `DISCLOSURE.md`.

## CLI reference generation

Generated from the Typer app so it never drifts: a build step renders the
`defendable-science` command tree to markdown (Typer's docs generation, or a small
script walking the Typer app) → included as the CLI-reference pages each build.
Regenerated on every publish, so it always matches the released CLI.

## Prerequisites (one-time, maintainer)

- Register **`defendable.science`** and point DNS at Mintlify per their custom-
  domain setup.
- Create the **`defendable-science-docs`** repo; connect it to Mintlify (Starter/free).
- Add a **deploy secret** (deploy key or fine-grained PAT scoped to the docs repo)
  to this repo's Actions secrets for the publish workflow.

## Acceptance criteria

- [ ] The site builds from the existing in-repo markdown with **no hand-maintained
      duplication** (the docs repo is a generated build artifact).
- [ ] The **CLI reference is generated from the `defendable-science` Typer app**.
- [ ] A publish workflow pushes to the docs repo on **`release: published`** (+
      manual dispatch); Mintlify redeploys.
- [ ] The site is served at **`defendable.science`**.
- [ ] `#6`'s stale `scholar`/`scholar-tools` naming is reconciled to `defendable-science`.

## Risks / open items

- **AI-credit metering** (5,000/mo on free Starter): the AI-search feature consumes
  credits; monitor usage, and disable AI search or budget if it approaches the cap.
- **Lock-in**: the *rendered* site lives on Mintlify (content is portable markdown,
  so migration to another SSG later is a build-target swap, not a content rewrite).
- **Builder details** to settle at plan time: exact Typer→markdown mechanism, the
  link-rewriting rules, and how skill pages are transformed for Mintlify front-matter.
- Deploy-secret handling in CI (least-privilege PAT/deploy key).

## Links

- Implements #6 · Decision: `decisions/0030-docs-site-mintlify.md` (ADR-0030).
- Source content: `README.md`, `docs/USER-GUIDE.md`, `docs/design/`, `decisions/`,
  `resources/`, `skills/`, `defendable-science/defendable_science/cli.py`.
- Release-driven CI pattern: ADR-0027. Light-dependency posture: ADR-0024.
- Decoupled from #7 (the arXiv paper has its own tooling).
