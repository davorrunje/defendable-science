# Proposal: `defendable-science` package (Typer CLI, optional MCP)

`Status: implemented (designed 2026-07-18) · Umbrella for the supporting-script proposals`

## Context

Per ADR-0024, the plugin's executable tooling ships as **one Python package**,
not loose `scripts/*.py`. The five supporting-script proposals become **modules**
of this package; this doc is the umbrella that organizes them and defines the
shared shape (packaging, CLI, bootstrap, optional MCP). The plugin stays
pure-markdown; skills call the CLI after the [`ensure-tooling`](../../../resources/ensure-tooling.md)
procedure.

## Package

`defendable-science` (distribution name; exposes the **`defendable-science`** CLI). It lives as a
**`defendable-science/` subdirectory of this plugin repo** — a monorepo, co-versioned
with the plugin, not a separate repo. Isolated env (ADR-0024) — free to depend on
`typer` + `requests` (HTTP) + `pyyaml` + `pooch` without touching a consumer's ML
environment.

```
defendable-science/                     # subdirectory of the plugin repo
├── pyproject.toml                 # deps + [project.scripts] defendable-science / dsci = defendable_science.cli:app + [project.optional-dependencies] mcp
├── defendable_science/
│   ├── core/                      # shared: requests-based http client, on-disk cache, config read, provenance
│   ├── literature/graph.py        # ← proposal: literature-citation-graph-client
│   ├── dataset/manifest.py        # ← proposal: dataset-manifest-tooling
│   ├── dataset/retrieval.py       # ← proposal: dataset-retrieval-mirror-tooling (+ rclone/pooch)
│   ├── defend/record.py           # ← proposal: defend-record-helper
│   ├── exploration/backlog.py     # ← proposal: exploration-backlog-helper
│   ├── cli.py                     # Typer app — the authoritative interface
│   └── mcp/ (later)               # thin MCP wrapper over the same modules
└── tests/
```

## CLI (authoritative)

A Typer command tree that mirrors the skill verbs; each command emits JSON:

```
defendable-science literature resolve | cites | refs | enrich | neighbors
defendable-science dataset    validate | ingest | emit | fetch | verify | mirror | audit
defendable-science defend     record
defendable-science backlog    park | add | list | rank | promote | drop   # shared by both exploration skills
defendable-science --version
```

(`register` / `export` are *skill* verbs that call these CLI commands — `register`
runs `ingest`+`validate`, `export` is `emit`; `add` realizes the `generate` verb.)

The skills invoke these via Bash (after `ensure-tooling`). Typer is consistent
with the experiment backend's CLI choice (ADR-0013).

## MCP (later)

A thin server exposing the same `core`/module functions as typed tools, declared
in `plugin.json → mcpServers` so Claude Code can auto-launch it. Deferred (ADR-0024,
CLI-first); nothing depends on it. Adding it is a wrapper, not a rewrite.

## Bootstrap

Install/upgrade is handled entirely by [`ensure-tooling`](../../../resources/ensure-tooling.md):
detect `uv`→`pipx`→`python3`, install isolated + pinned (prefer `uv tool install`,
which also provisions Python), record the CLI in `.defendable-science/config.yml`, stop with
instructions if the env can't self-heal.

Distribution is **PyPI-first** — the primary install is the published
`defendable-science` package:

```
uv tool install defendable-science
# ad-hoc, no persistent install:
uvx defendable-science …
```

The **git-subdirectory install is the fallback** (an unreleased ref, or PyPI
unreachable); release candidates are validated from **TestPyPI** first:

```
uv tool install "git+https://github.com/davorrunje/defendable-science.git#subdirectory=defendable-science"
uvx --from "git+https://github.com/davorrunje/defendable-science.git#subdirectory=defendable-science" defendable-science …
```

## Decided

- **House HTTP client = `requests`** (applies to `core`, used by literature + any
  http fetch). `pooch` already pulls it, so it is a zero-net-dep choice; no async
  surface is needed. Used everywhere an HTTP call is made.
- **Distribution = PyPI-first**: primary install is the published `defendable-science`
  package (`uv tool install defendable-science`, or `uvx defendable-science …` ad-hoc);
  release candidates are validated from **TestPyPI** first. The git-subdirectory
  install (`uv tool install "git+…#subdirectory=defendable-science"`) is the fallback
  for unreleased refs or when PyPI is unreachable.
- **Names claimed:** distribution `defendable-science`, CLI `defendable-science` (+ short
  alias `dsci`); the name is reserved on both PyPI and TestPyPI (pre-release
  `0.0.0a0` published).

## Open questions

- **MCP timing:** ship the wrapper in v0.1, or wait for a concrete need?
- **Version pin source:** how the plugin communicates its pinned `defendable-science`
  version to `ensure-tooling`. Since the package is co-versioned in the same repo,
  a git ref/tag (or a `VERSION` file read by the skills) — pick the mechanism.

## Acceptance criteria

- [x] `defendable-science` skeleton: `pyproject.toml`, `core/`, Typer `cli.py`, `tests/`.
- [x] `defendable-science --version` works via an isolated `uv tool` / `pipx` / venv install.
- [x] `ensure-tooling` provisions it on a machine with only `uv` (no prior Python).
- [x] Each module implemented per its own proposal; CLI subcommands wired.
- [x] Skills updated: interim manual / direct-tool-call orchestration replaced with
      `ensure-tooling` + `defendable-science …` calls.
- [ ] (Later) MCP wrapper exposing the same functions.

## Links

- ADR-0024 (this decision); `resources/ensure-tooling.md`.
- Module proposals: `literature-citation-graph-client.md`,
  `dataset-manifest-tooling.md`, `dataset-retrieval-mirror-tooling.md`,
  `defend-record-helper.md`, `exploration-backlog-helper.md`.
