<!-- defendable-science design spec -->

# Scaffold, check, and layout: making a defendable-science repo verifiable

Design for issues [#120](https://github.com/davorrunje/defendable-science/issues/120)
(scaffold every file from a single source), [#121](https://github.com/davorrunje/defendable-science/issues/121)
(a repo-wide `check`), and [#122](https://github.com/davorrunje/defendable-science/issues/122)
(a machine-readable consumer layout).

## Problem

`research-init` invokes no CLI verb. Every file it "scaffolds" is typed by the
agent from the prose in `skills/research-init/SKILL.md § What it scaffolds`, so
the shape of each machine-read file is re-derived on every run. The consequences
are recorded in the three issues and reproduced against CLI 0.2.2:

- A freshly initialized repo is **dead on arrival**. Both backlog tables carried
  headers no column profile accepts, and `papers.md` carried a column
  `REGISTRY_COLUMNS` disallows, so `backlog park` and `backlog promote --scaffold`
  both failed on a brand-new scaffold.
- **Nothing detects it.** Validation exists only per-artifact and only for
  datasets; there is no repo-wide check, so a broken repo is discovered when some
  unrelated command trips over it, or never.
- **Unfilled placeholders parse as real values.** `readiness: <synthesis |
  defensible>` is valid YAML, so `progress` reads a bogus readiness instead of
  seeing "unset" — violating the documented invariant *absence means "not yet
  set," never zero* invisibly.
- **The layout is prose only.** It is restated in eight `SKILL.md` files, two
  design docs, and fragments of Python, and there is nowhere for an adopted repo
  to record a divergent layout. So a repo-wide check has nothing authoritative to
  check against.

Three sources of truth exist for shapes that *are* templated: the skill prose,
`resources/templates/`, and Python string literals (`_HYPOTHESIS_TEMPLATE`,
`_PAPER_TEMPLATE`). That duplication has already drifted once — commit 9142dd0
fixed an embedded copy missing the status frontmatter the shipped template always
carried. A drift guard exists (`defendable-science/tests/test_backlog.py:852`) but
covers only two of the nine templates.

## Decisions

Four decisions frame everything below. Each was chosen over the alternatives
recorded in *Rejected alternatives*.

1. **The package owns every machine-read shape and renders it.** A new
   `defendable-science init` writes the ten currently-untemplated files, because
   the package already owns their columns and validators.
   `resources/templates/` keeps only the human-authored prose skeletons.
2. **The layout is a bounded key set.** Four roots are recordable in
   `.defendable-science/config.yml`; everything inside a paper is derived and not
   configurable.
3. **One frontmatter renderer.** `scaffold/status.py` is the only place the status
   field set and per-level enums are written; every template carrying a status
   block is drift-guarded against it.
4. **Four sequential PRs.** `check --fix` and a real `progress dashboard`
   generator are follow-up issues, not this milestone.

## Architecture

One new sub-package plus one new module, following the verb-per-package
convention of `literature/`, `dataset/`, `defend/`, `exploration/`:

```
defendable_science/
  core/
    config.py          + repo-root discovery (load_config signature unchanged)
  scaffold/            NEW — pure renderers; no I/O in the kernel
    layout.py          Layout dataclass: the ONE definition of the consumer tree
    status.py          status-frontmatter field set, per-level enums, render()
    render.py          renderers for every machine-read file `init` writes
    init.py            the writer: Layout + options -> list of actions
  check/               NEW — pure checker kernel
    model.py           Finding (severity, check, file, message, remedy), Report
    checks.py          individual checks, each a pure function over a Probe
  cli.py               + two top-level commands: `init`, `check`
```

Three rules hold the boundaries:

- **`scaffold/` renders, `check/` reads.** `check` imports `scaffold.layout` and
  `scaffold.status` for the shapes, and reuses the existing `Backlog.loads`,
  `load_registry`, `load_triage`, `manifest.load` and `load_config` validators. It
  reimplements no validator.
- **Kernels are pure and injectable** (`CLAUDE.md § Architecture`). Renderers
  return strings; checks take an injected `Probe` (`read_text` / `exists` /
  `glob`). Only `init.py`'s writer and the CLI adapters touch disk. This is what
  makes the 100% branch gate reachable without a fixture repo per branch.
- **`cli.py` stays thin.** It is already 1750 lines; `init` and `check` get
  adapters only (load config, resolve layout, call kernel, emit JSON, exit).

Note: #122 states that `--paper-root` / `--research-root` are required on every
invocation. They are required only for `--scaffold` (`cli.py:1379`
`_check_scaffold_opts`); `--backlog` already defaults, but to a bare cwd-relative
`"backlog.md"`, which the resolver replaces.

## PR1 — the layout resolver (closes #122)

`scaffold/layout.py`, a frozen dataclass of four recorded roots with derived
accessors:

```python
@dataclass(frozen=True)
class Layout:
    repo_root: Path
    research_root: Path      # default: docs/research
    literature_dir: Path     # default: <research_root>/literature
    datasets_manifest: Path  # default: datasets.yml (repo root)
    thesis_dir: Path         # default: <research_root>/thesis
```

Derived and **not** configurable: `papers_registry`, `portfolio_backlog`,
`dashboard` (under `research_root`); `paper_dir(paper_id)`, `backlog(paper_id)`,
`hypotheses_dir(paper_id)`, `paper_docs_dir(paper_id)`,
`hypothesis_dir(paper_id, slug)`; `aims`, `milestones`, `kappa_dir` (under
`thesis_dir`). Keeping the inside of a paper fixed is what lets every skill,
`progress` and `check` know where a paper's parts are.

`layout.py` also holds the set of **known staged documents** (`hypothesis.md`,
`findings.md`, `pitch.md`, `decision.md`, `kappa.md`, `aims.md`), so `init`,
`check` and the drift tests read one list.

Four design points:

1. **Defaults derive from `research_root`, not from literal strings.** Setting
   `research_root: writing/` moves `literature/` and `thesis/` with it. Only
   `datasets_manifest` is anchored at the repo root, matching its current
   position. Without this, a one-key override silently leaves literature behind.
2. **`.defendable-science/` is fixed.** It holds `config.yml` itself, so it cannot
   be relocated by `config.yml`. `cache_dir` stays exactly as ADR-0031 defines
   it; the resolver reads it rather than re-deriving it.
3. **No tri-state `thesis_dir`.** With defaults-omitted semantics an omitted key
   already means "use the default", so it cannot also mean "not a thesis repo".
   Instead the Layout always knows where a thesis tree would live, and
   thesis-ness is a fact on disk: `init --thesis` creates it, `check` requires
   thesis artifacts only if the directory exists.
4. **Repo-root discovery.** Layout paths are repo-root-relative, so
   `find_repo_root()` walks up for `.defendable-science/` and falls back to the
   cwd, with a `--root` option on the new commands. Today the CLI silently
   assumes cwd == repo root; this makes running from a subdirectory work instead
   of resolving against the wrong place.

**Config schema.** `layout:` accepts exactly the four keys, all optional; a repo
matching the default writes nothing. Resolution order is `config.yml layout:`
then the packaged default.

**Validation.** `LayoutError(ValueError)`, surfaced by the CLI as exit 1 with an
actionable message:

- an unknown key is an error that lists the four valid keys — never a silent
  ignore;
- a non-string value is an error;
- an absolute path or a `..` escape is rejected: a layout key pointing outside
  the repo would let `init` and `check` write beyond the work tree.

**Wiring.** `_layout_or_exit()` joins `_load_config_or_exit` / `_cache_root` in
`cli.py`. `--backlog`, `--paper-root` and `--research-root` become `None`-defaulted
overrides resolved from the layout; explicit values still win, and
`_check_scaffold_opts` stops demanding them when the layout resolves. One real
bug is fixed here: `backlog.py:666` `_registry_root` derives the repo root as
`research.parent.parent`, which is wrong once `research_root` is `writing/`.

**ADR.** ADR-0039 (0038 is the current last) records bounded key set vs. fixed
layout vs. full per-file block, appended to `decisions/README.md`.

## PR2 — `init` and the template boundary (closes #120)

`defendable-science init [--root PATH] [--thesis] [--dry-run]` — idempotent,
non-destructive, JSON-emitting. Per file it reports `created`, `exists` or
`merged`, never `overwritten`; an existing file is left alone, matching
`research-init`'s "re-running fills gaps only" guardrail. `--dry-run` reports
without writing.

| File | Rendered from |
|---|---|
| `papers.md` | `REGISTRY_COLUMNS` (new `registry_dumps()` beside `Backlog.dumps`) |
| `portfolio-backlog.md` | `Backlog(level="paper").dumps()` (exists) |
| `<paper>/backlog.md` | `Backlog(level="hypothesis").dumps()` (exists, via `scaffold_paper`) |
| `literature/references.json` | `[]` — valid CSL-JSON |
| `literature/triage.yml` | empty mapping, shaped for `load_triage` |
| `datasets.yml` | empty-but-valid manifest (`dataset validate` -> `ok: true`) |
| `.defendable-science/config.yml` | the five bindings as **`null` + comment** |
| `.defendable-science/rclone.conf.example` | remote name/type only, no credentials |
| `dashboard.md` | GENERATED header + an honest "no generator yet" body |
| `.gitignore` | **append-only merge** of the three entries |

Three points:

- **`config.yml` ships `null`s, never placeholder strings.** This is #120's last
  acceptance criterion and #121's placeholder bug in miniature. Everything `init`
  writes obeys *absence means "not yet set"*, and `check` enforces it.
- **`resources/templates/` does not grow by ten files.** Its `README.md § What
  produces what` gains a row per machine-read file whose *Produced by* is
  `defendable-science init`, plus a note that the CLI renders these because the
  package owns their columns and validators. The README's `§ Status-frontmatter
  convention` block enters the drift-guard parametrization: the field set is
  written out there, so it is a third editable copy today.
- **`dashboard.md` is honest about having no generator.** `SKILL.md` claims the
  file is generated by `progress dashboard`, but `progress` is a skill with no CLI
  backing. Rather than write a fake projection, `init` writes a stub saying so;
  the real generator is a follow-up issue.

`skills/research-init/SKILL.md § What it scaffolds` keeps the layout tree as
orientation, drops every implied schema, and calls `defendable-science init` after
the `ensure-tooling` bootstrap. `§ Adopt` gains the propose-a-`layout:`-block path
from PR1, with human confirmation, as an alternative to relocating files.
`resources/ensure-tooling.md`'s lower bound moves to the version shipping
`init`/`check` — it currently reads `>=0.3.0,<0.4.0` against a released 0.2.2, so
if 0.3.0 is unreleased this may already be covered; confirm against the changelog
rather than assume.

## PR3 — `defendable-science check` (closes #121 core)

Three severities; the exit code keys off severity, not count:

| Severity | Meaning | Exit |
|---|---|---|
| `invalid` | the file violates a shape the package owns | 1 |
| `unreadable` | could not read or parse it — validity is *unknown* | 1 |
| `gap` | valid file, incomplete science — an honest state | 0 |

`unreadable` is its own severity for `CLAUDE.md § Failure honesty`: "failed to
read `references.json`" must never render as "0 references, all fine". Each
finding carries `{severity, check, file, message, remedy}` with a copy-pasteable
remedy. Output is JSON by default (skills are the primary caller; it matches
`dataset validate`), with `--text` for a `doctor`-style summary.

**`invalid`:** a backlog or registry header that cannot carry its column profile
(with the migration hint the current error already produces); a `papers.md` row
whose `root` is missing or whose `backend` is empty; a missing `status:` block on
a known staged document; an out-of-enum `verdict` or `readiness` for the level; an
unreplaced `<...>` in any machine-read field; invalid CSL-JSON; a `triage.yml` key
with no matching reference id; a `datasets.yml` failing manifest validation; an
unparseable `config.yml`; an unknown `layout:` key; a `cache_dir` that is not
gitignored; a missing *required* layout path. The required set is the registries
plus `config.yml` — a repo with no papers yet is complete, not broken, so a paper
directory is required only for a `paper-id` that `papers.md` registers.

**`gap`** (reported, exit 0): `covers: [aim-N]` with no such aim in
`thesis/aims.md`; a `verdict` set with `signed-off-by: null`; `evidence: []` on a
`resolved` or `published` artifact; `experiment_backend: null`; and `dashboard.md`
not mentioning an artifact id present on disk, or mentioning one that is not.
That last is how a stale dashboard is detected **without** a generator: an id-set
comparison needs no reference rendering.

**A `refuted` hypothesis or a `no-go` paper is never a finding of any kind.** The
exit code is keyed to invalid *files*, never to incomplete *science*.

Only the known staged documents are frontmatter-checked; other markdown files are
ignored, so an author's scratch notes are not errors. Prose bodies are never
placeholder-scanned — templates legitimately contain `<...>` in prose.

The headline regression guard: **a repo freshly created by `init` passes `check`
with exit 0 and zero `invalid` findings** — the direct answer to the `backlog
park` failure quoted in #120 and #121.

## PR4 — skill wiring and docs

Eight skills hard-code `docs/research/...` paths (`digest`,
`hypothesis-exploration`, `hypothesis-testing`, `paper-exploration`,
`paper-synthesis`, `progress`, `research-init`, `thesis`) — the ninth copy of the
layout. PR4 is a bounded sweep plus two wirings:

- **`research-init`** calls `check` at the end of both modes and reports findings
  instead of declaring success. It is the one place that asserts "you now have a
  working repo", so it is the one place that must verify it.
- **`progress`** runs `check` before reporting and treats `unreadable` as *cannot
  report on this artifact*, never as an absent status. `progress` calls itself a
  pure projection; a projection that quietly drops rows is a lie.
- **The other six** stop spelling out `docs/research/<paper>/...` and stop passing
  `--backlog` / `--paper-root`; they say the CLI resolves paths from the repo's
  layout. Where a concrete path aids comprehension it stays, explicitly labelled
  *the default layout, for illustration*.
- **`docs/design/00-meta-spec.md § 5`** and **`01-lifecycle.md § 7`** keep their
  narrative and replace the restated tree with a pointer to the single definition.

## Testing

Per PR, all hermetic and under the 100% statement+branch gate (ADR-0028):

- **PR1** — default resolution; each of the four overrides; unknown key;
  non-string value; absolute path; `..` escape; `find_repo_root` found and
  not-found; `_registry_root` correct under a non-default `research_root` (the bug
  this PR fixes); `backlog promote --scaffold` with no `--paper-root` /
  `--research-root`.
- **PR2** — every rendered file parses through its own loader (`Backlog.loads`,
  `load_registry`, `load_triage`, `manifest.load`, `load_config`); table headers
  equal `HYPOTHESIS_COLUMNS` / `PAPER_COLUMNS` / `REGISTRY_COLUMNS`; no
  machine-read field holds a `<...>` string; idempotence (a second `init` reports
  `exists` and leaves a byte-identical tree); the `.gitignore` merge preserves
  existing content; the drift guard at `tests/test_backlog.py:852` generalized to
  all nine templates plus the README block, asserted against `status.render`.
- **PR3** — one test per `invalid` message, each asserting the message names the
  file *and* a remedy; one per `gap`; `unreadable` distinguished from
  valid-and-empty; no raw traceback on any input, including a binary file where
  JSON is expected; the exit-code matrix (clean 0, gaps-only 0, any invalid 1).
- **PR4** — `./tools/validate-plugin.sh`, plus a guard that no
  `skills/**/SKILL.md` contains a hard-coded `docs/research/` path outside an
  explicitly-labelled illustration. That guard stops the tenth copy of the layout
  from reappearing.
- **The acceptance smoke, end to end** (PR3): `init` -> `backlog park --level
  paper` -> `backlog park --level hypothesis` -> `backlog promote --scaffold` ->
  `dataset validate` -> `check`, with no path options passed. That sequence is the
  literal failure quoted in #120 and #121.

Verification per PR: `cd defendable-science && uv run pytest -q && uv run mypy &&
uv run ruff check`, plus `pre-commit run --all-files` and
`./tools/validate-plugin.sh` for plugin-side changes.

## Follow-up issues

Filed with the `create-issue` skill, self-contained per the house standard:

1. **`check --fix`** — dry-run by default, an explicit flag to write. Repairs only
   the mechanically safe (missing directories and `.gitkeep`s, a missing
   `.gitignore` entry, a lossless table-header migration). Must never write a
   `verdict`, `signed-off-by`, an `evidence` entry, a dataset `license` or `tier`
   — those are material decisions requiring human sign-off (meta-spec § 2.1) —
   with a test proving it refuses.
2. **A real `progress dashboard` generator** — makes the GENERATED header true and
   turns the stale-dashboard `gap` into an enforceable rule.

## Rejected alternatives

- **Ten new markdown templates plus drift tests** (the literal reading of #120).
  Preserves the plugin/package boundary exactly as ADR-0026 draws it and adds no
  CLI surface, but the agent still hand-copies ten files, so `init`
  reproducibility still rests on a model following prose, and each shape still
  lives in two editable places with CI as the only link.
- **Generating `resources/templates/` from code and committing both.** Gives one
  editable definition and a browsable template directory, but adds a build step
  and a generated-files-in-git convention while still leaving agent-typed `init`
  unreproducible — it fixes drift, not "two `init` runs disagree".
- **A single `research_root` override.** The cheapest layout, and what #122 itself
  leans toward, but it does not cover the divergences #122 names for `adopt`
  (references in a shared `bib/`, datasets under `data/`); those repos would have
  to relocate files, reducing "record what you find" to "record where the tree
  lives".
- **A full per-file `layout:` block** with `{paper_id}` interpolation. Maximum
  `adopt` flexibility, but the largest validation surface, and two
  defendable-science repos could look nothing alike — weakening the "tracked the
  same way everywhere" promise in `research-init`'s own description.
- **Stripping the status block from the prose templates entirely**, with the CLI
  prepending it. The strongest single-source guarantee, but a template read on its
  own would no longer show the author the block they will fill, and any
  hand-created document would start with no frontmatter, which `progress` reads as
  an untracked artifact.
- **Keeping the current arrangement and only widening the drift guard.** The
  smallest diff, but the field set stays written out in the templates, the Python
  literals, and `resources/templates/README.md` — three places kept in step by
  tests rather than by construction, which is what #120 asks to end.
- **One branch for all three issues.** #120 and #121 are near-meaningless apart
  under the generator approach, but a single review touching the package, eight
  skills, the templates, two design docs and an ADR is hard to review carefully
  and hard to revert in pieces.

## References

- Issues #120, #121, #122
- `skills/research-init/SKILL.md`, `skills/progress/SKILL.md`
- `resources/templates/README.md`, `resources/ensure-tooling.md`
- `defendable-science/defendable_science/exploration/backlog.py`,
  `defendable-science/defendable_science/cli.py`,
  `defendable-science/defendable_science/core/config.py`
- `docs/design/00-meta-spec.md` (§ 2.1 agency, § 5 boundary),
  `docs/design/01-lifecycle.md` (§ 7 layout, § 8 material decisions)
- ADR-0017 (research-init: one skill, two modes), ADR-0018 (git-native source of
  truth), ADR-0023 (engineering delegation), ADR-0026 (plugin/package version
  boundary), ADR-0028 (coverage gate), ADR-0031 (config-driven `cache_dir`)
- Commit 9142dd0 — prior drift between an embedded literal and a shipped template
