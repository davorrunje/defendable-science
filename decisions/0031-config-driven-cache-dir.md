# ADR-0031: Source the cache root from `config.yml` (`cache_dir:`), not a hardcoded literal

- Status: accepted · Date: 2026-07-22 · Deciders: Davor Runje

## Context

`research-init` scaffolded a project's `.gitignore` with `.datasets-cache/`, but
`defendable_science/cli.py` hardcoded the directory it actually wrote to as
`.defendable-science/cache/datasets` (the dataset content-addressed cache,
`_DATASET_CACHE`) and `.defendable-science/cache/http` (the literature HTTP cache,
inside `_lit_client`) — two independent literals that were never reconciled with
the scaffold. This surfaced during onboarding of a real consumer repo
(`davorrunje/mononet`): after `dataset fetch`/`verify` and a `literature` run,
cached bytes landed under `.defendable-science/cache/…`, which the scaffolded
`.gitignore` did **not** exclude (risk of committing large cached blobs), while
the gitignored `.datasets-cache/` was dead — never written to, and misleading
about where the cache actually lives (`defendable-science#65`). This was a known open
item — sub-spec 4 §7 flagged "`.datasets-cache/` vs `.defendable-science/`" as
needing reconciliation before this fix.

## Decision drivers

- The path `research-init` gitignores and the path the CLI writes to must be
  the same path, **by construction** — not by two hand-synced literals.
- Consumers occasionally need the cache elsewhere (a scratch volume, a CI cache
  mount) — worth a one-line override, not a code change.
- Keep the change minimal and consistent with the existing config-loading
  pattern (`_lit_client` already reads `literature.mailto` from
  `.defendable-science/config.yml`, with the same invalid-YAML/mapping error
  handling this ADR reuses).
- No new dependency (stdlib + the existing `pyyaml`-backed `load_config`); no
  Pydantic (ADR rejecting it stands).

## Considered options

1. **Minimal**: point `research-init`'s scaffold at whatever `cli.py` already
   hardcodes (`.defendable-science/cache/`), leaving both sides as literals.
2. **Config-driven** *(chosen)*: add a `cache_dir:` key to
   `.defendable-science/config.yml` (default `.defendable-science/cache/`); `cli.py`
   resolves the dataset cache (`<cache_dir>/datasets`) and the literature HTTP
   cache (`<cache_dir>/http`) from it; `research-init` gitignores exactly that
   configured path.
3. Separate `dataset.cache_dir` / `literature.cache_dir` keys per capability.

## Decision

Option 2. A single top-level `cache_dir:` key in `.defendable-science/config.yml`,
default `.defendable-science/cache/` when absent. `defendable_science/cli.py` gains a
shared `_cache_root(config)` resolver (invalid-type → a clean `typer.Exit(1)`,
matching the existing config-error convention, never a raw traceback) that both
`_dataset_cache_dir()` (`<cache_dir>/datasets`) and `_lit_client()`
(`<cache_dir>/http`) call — one source of truth for both capabilities'
sub-caches. `research-init`'s scaffold and prose now reference
`.defendable-science/cache/` (via `cache_dir:`) instead of the dead
`.datasets-cache/`, and `.gitignore` excludes exactly that configured path.

## Consequences

- A fresh `research-init` + `dataset fetch`/`verify` + a `literature` run
  leaves no un-ignored cache files — scaffold and runtime cannot drift apart,
  because both read from the same config key.
- One config key covers both capabilities' caches; a consumer who wants the
  cache elsewhere sets `cache_dir:` once.
- `.datasets-cache/` is retired from the scaffold — not left as a second,
  inert path (the "both-and-neither" failure mode this ADR closes).
- Reads `.defendable-science/config.yml` on every `dataset fetch/verify/mirror/audit`
  invocation (previously these commands did not touch config at all); a
  malformed `config.yml` now surfaces as a clean exit 1 on those commands too,
  consistent with how `literature` commands already behaved.

## Rejected alternatives

- **Minimal (point the scaffold at the hardcoded literal)** — fixes today's
  drift but leaves two independent literals that can drift again on the next
  edit; does not answer the acceptance criterion that scaffold and runtime
  cannot drift *by construction*.
- **Per-capability cache keys** — no present need for dataset and literature
  caches to live in different places, and it multiplies the scaffold/runtime
  reconciliation surface this ADR exists to shrink.

## Links

`defendable-science/defendable_science/cli.py` (`_cache_root`, `_dataset_cache_dir`,
`_lit_client`); `defendable-science/defendable_science/core/config.py` (`load_config`);
`skills/research-init/SKILL.md`; `docs/design/03-dataset.md` §7 (the open item
this closes); `defendable-science#65`; ADR-0029 (the config-error-handling
convention this reuses).
