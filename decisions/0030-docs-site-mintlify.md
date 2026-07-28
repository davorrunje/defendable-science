# ADR-0030: Docs site on Mintlify, published from a generated docs repo

- Status: accepted · Date: 2026-07-19 · Deciders: Davor Runje

## Context

`defendable-science` had no rendered docs site (#6) — the design record, `README.md`,
`docs/USER-GUIDE.md`, and the CLI `--help` were the docs, all as in-repo markdown.
A single navigable "one portal" site (users **and** the design record) is now
wanted. The choice must fit the project's posture: it targets the **whole research
community** (not ML-only, so mononet's Sphinx is not a default), prefers
**single-binary / light dependencies over heavy toolchains**, keeps a **git-native
source of truth** ("no hosted services as source of truth"), and has a separate
future arXiv paper (#7).

## Decision drivers

- Wide, non-ML research audience; professional, navigable result.
- Source of truth stays as markdown in git.
- Low maintenance; minimal toolchain weight.
- Ecosystem fit (a Claude-ecosystem tool) is a plus.
- The arXiv paper (#7) is **decoupled** — no need for a docs→paper publishing
  pipeline.
- Deploy should be release-gated (#6: "on tag").

## Considered options

1. **Quarto** — single binary (pandoc-based), language-agnostic, one source →
   site + book + arXiv PDF.
2. **Sphinx + MyST** (PyData/Furo) — the Python-docs incumbent; heavier config;
   closest to mononet.
3. **MyST-MD** — scientific-markdown engine (JATS/PDF export); Node-based, young.
4. **Docusaurus / Astro Starlight** — modern web-docs; full Node toolchain;
   product- not research-oriented.
5. **Mintlify** — hosted docs-as-code platform; markdown/MDX in git; AI-native.
   *(chosen)*

## Decision

**Mintlify**, sourced from the in-repo markdown, published by CI to a **dedicated,
generated docs repo** (`defendable-science-docs`) that Mintlify renders at the custom
domain **`defendable.science`**.

- **Ecosystem-native + proven**: Anthropic's own docs (claude.com/docs) run on
  Mintlify — well-supported, fitting for a Claude-ecosystem tool.
- **Docs-as-code**: pages are markdown in git → source of truth stays in the repo;
  the "no hosted services as source of truth" clause is about provenance/data, not
  docs rendering, so it is not violated.
- **AI-native**: auto `llms.txt` + markdown export + MCP — apt for an
  AI-in-the-loop research tool.
- **Cost**: the free **Starter** tier includes a **custom domain**, AI search,
  analytics, web editor, auth, and MCP; usage is metered by **AI credits (5,000/mo
  included)**.
- **Topology**: this repo stays the single source of truth and free of Mintlify
  config; a CI build (on `release: published` + manual dispatch, per ADR-0027)
  assembles the one-portal content, **generates the CLI reference from the Typer
  app**, writes `docs.json`, rewrites links, and pushes to the generated docs repo.
  The docs repo is a **build artifact, never hand-edited** — so #6's "no content
  duplication" holds.

## Consequences

- A polished, ecosystem-native site at `defendable.science`, release-gated, on
  the free tier, with the markdown source owned in-repo.
- One-time maintainer setup: register the domain + DNS, create the docs repo,
  connect Mintlify, add a least-privilege deploy secret to CI.
- **AI-credit metering** is the cost/usage dimension to monitor (throttle or
  disable AI search if it nears the cap).
- **Lock-in is bounded**: the rendered site is Mintlify's, but content is portable
  markdown — switching SSG later is a build-target swap, not a content rewrite.
- No scientific-publishing pipeline; acceptable because #7 is decoupled.

## Rejected alternatives

- **Quarto** — the strongest self-owned/single-binary option and would single-
  source #7, but that synergy is unneeded (paper decoupled), and it is less
  ecosystem-native and more setup than Mintlify for a pure markdown portal.
- **Sphinx + MyST** — most mature, but heaviest config, Python-flavored, and
  optically anchored to mononet (explicitly not the target audience).
- **MyST-MD** — most ethos-aligned for scientific records, but Node-based and the
  youngest/least-settled ecosystem.
- **Docusaurus / Starlight** — slick but a full Node toolchain (against the light-
  dependency posture) and product- rather than research-oriented, with MDX lock-in.
- **Self-hosted vs Mintlify**: hosting lock-in was judged acceptable given the
  portable markdown source and the ecosystem/effort benefits.

## Links

`docs/design/proposals/docs-site.md` (the design); #6 (implements); #7 (decoupled
paper); ADR-0027 (release-driven CI pattern); ADR-0024 (light-dependency posture).
Mintlify pricing + Anthropic case study consulted 2026-07-19.
