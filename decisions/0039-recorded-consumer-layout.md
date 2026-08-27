# ADR-0039: The consumer layout is a bounded set of four recordable roots, not prose and not a free-form path map

- Status: accepted · Date: 2026-08-27 · Deciders: Davor Runje

## Context

`defendable-science` reads and writes a tree in the consumer's repository:
`docs/research/papers.md`, `docs/research/portfolio-backlog.md`, a directory per
paper, `docs/research/literature/{references.json,triage.yml}`, `datasets.yml`,
and — for a thesis repo — `docs/research/thesis/`. Until this decision that tree
existed only as prose. It was restated in eight `SKILL.md` files, in
`docs/design/00-meta-spec.md` § 5 and `docs/design/01-lifecycle.md` § 7, and in
fragments of Python: default option values in `cli.py`, and a repo root derived
in `exploration/backlog.py` as `research_root.parent.parent`.

Two consequences followed, both reported in
[#122](https://github.com/davorrunje/defendable-science/issues/122):

- **Nothing can validate the tree.** A repo-wide `check` (#121) needs an
  authoritative statement of where things belong; nine informal copies are not
  one. The copies had already diverged in behaviour — the grandparent guess in
  `backlog.py` is wrong for any repo whose research root is not two levels down,
  and every command silently assumed the cwd *was* the repo root.
- **An adopted repo has nowhere to say it differs.** `research-init`'s `adopt`
  mode (ADR-0017) exists to record what is already on disk. #122 names the
  divergences it meets in practice: references kept in a shared `bib/`, datasets
  under `data/`, writing under something other than `docs/`. With no recordable
  layout, `adopt` can only ask the author to move their files.

ADR-0031 already established the pattern for this class of problem: when a path
is both scaffolded and read at runtime, source it from
`.defendable-science/config.yml` once instead of keeping two literals in step by
hand. This ADR applies that pattern to the content tree, which is larger and
therefore needs a decision about *how much* of it is recordable.

## Decision drivers

- **A repo-wide `check` needs one definition to check against** — by
  construction, not by tests keeping copies aligned.
- **`adopt` must be able to record what it finds** (ADR-0017), or it degrades
  into "relocate your repository to match ours".
- **A defendable-science repo should be legible to someone who has seen another
  one.** `research-init`'s own description promises work is "tracked the same way
  everywhere"; unlimited configurability would make that false.
- **Plain files in git remain the source of truth** (ADR-0018), so the layout is
  recorded in the same committed YAML as everything else, not in a lockfile or a
  tool-managed state directory.
- **Every recordable path is an attack surface on the work tree.** This is an
  integrity tool; a configured path that escapes the repository would let it
  read and write outside the repository it is supposed to be documenting.
- **Validation cost is real.** Each recordable key needs type checking, escape
  checking, an error message, and branch-covered tests (ADR-0028).

## Considered options

1. **A fixed layout with a single `research_root` override.** One key; everything
   else derived from it. The cheapest option, and the one #122 itself leans
   toward.
2. **A bounded set of four recordable roots** *(chosen)* — `research_root`,
   `literature_dir`, `datasets_manifest`, `thesis_dir` — in an optional
   `layout:` block, with everything inside a paper derived and not configurable.
3. **A full per-file `layout:` block** naming each artifact, with `{paper_id}`
   interpolation for the per-paper paths.

## Decision

Option 2. `defendable_science/scaffold/layout.py` holds a frozen `Layout`
dataclass — the one definition of the consumer tree — and `resolve_layout()`
reads an optional `layout:` block from `.defendable-science/config.yml`.
The block accepts exactly the four keys, all optional; a repo matching the
default records nothing at all. Resolution order is the `layout:` block, then
the packaged default.

Everything else is **derived and not configurable**: `papers.md`,
`portfolio-backlog.md` and `dashboard.md` under `research_root`;
`references.json` and `triage.yml` under `literature_dir`; `aims.md`,
`milestones.yml` and `kappa/` under `thesis_dir`; and the whole inside of a
paper — `<paper_id>/backlog.md`, `hypotheses/<slug>/`, `paper/`. Keeping the
inside of a paper fixed is what lets every skill, `progress` and `check` know
where a paper's parts are from the paper id alone.

Defaults derive from the **resolved** `research_root`, not from literal strings,
so `research_root: writing` carries `literature_dir` and `thesis_dir` with it.
Only `datasets_manifest` is anchored at the repo root, matching where it already
sits. The repo root itself is discovered by `core.config.find_repo_root()`,
which walks up for `.defendable-science/` and falls back to the resolved start
directory (an un-onboarded directory is not an error — `init` is the command you
run there).

Invalid input is an error, never a silent fallback: an unknown key is rejected
with the four valid keys listed, a non-string or empty value is rejected, and an
absolute path or a `..` escape is rejected because a layout key pointing outside
the work tree would let the tooling read and write beyond the repository. All of
these raise `LayoutError`, which the CLI surfaces as a clean exit 1 with an
actionable message, matching the config-error convention ADR-0031 established
(never a raw traceback).

## Consequences

- **One override does the expected thing.** Because defaults derive from the
  resolved `research_root`, a repo that keeps everything under `writing/` sets
  one key. Without this, a one-key override would silently leave literature and
  the thesis behind in `docs/research/`.
- **`.defendable-science/` is fixed and cannot be relocated**, because it holds
  `config.yml` itself. `cache_dir` stays exactly as ADR-0031 defines it; the
  layout reads it rather than re-deriving it.
- **Thesis-ness is a fact on disk, not a config flag.** With defaults-omitted
  semantics an omitted key already means "use the default", so it cannot also
  mean "this is not a thesis repo" — a tri-state `thesis_dir` would overload one
  absence with two meanings. Instead the layout always knows where a thesis tree
  *would* live; `init --thesis` creates it and `check` requires thesis artifacts
  only when the directory exists (both land with #120 and #121).
- **Commands work from a subdirectory.** Repo-root discovery removes the
  cwd-is-the-repo-root assumption. It also fixed a real bug it exposed:
  `exploration/backlog.py` derived the repo root as `research_root.parent.parent`
  when rendering a `papers.md` row, which is wrong for any non-default
  `research_root`; `scaffold_paper` now takes the resolved `Layout` instead, so
  the guess is gone rather than corrected.
- **Relative values inside `config.yml` now anchor to the repo root, not the
  cwd.** `cache_dir`, `literature.registry` and `literature.triage` describe
  locations in the *repository*; resolving them against the cwd meant a command
  run from a paper directory read a different registry and wrote caches to a
  directory `research-init` had never gitignored. This is a behaviour change for
  anyone who was invoking the CLI from a subdirectory and relying on the old
  resolution — but the old resolution was the bug.
- **The per-file path defaults in `cli.py` are gone.** `--backlog`,
  `--paper-root` and `--research-root` become `None`-defaulted overrides
  resolved from the layout (an explicit value still wins), and the literature
  registry/triage defaults now come from the layout rather than from module-level
  path literals. There is no longer any hard-coded consumer path in the CLI.
- **A known asymmetry, stated rather than hidden:** `layout:` keys are confined
  to the repository, but `cache_dir` is only *anchored*, not confined, so
  `cache_dir: ../../elsewhere` still escapes. ADR-0031 deliberately allows an
  off-repo cache (a scratch volume, a CI mount), so closing this needs a
  decision rather than a patch. Tracked as
  [#123](https://github.com/davorrunje/defendable-science/issues/123); not fixed
  here.
- **The recordable surface is a commitment.** Four keys is now the contract
  `adopt` and `check` are written against; widening it later is cheap, narrowing
  it is a breaking change for any repo that recorded a key.

## Rejected alternatives

- **A fixed layout with a single `research_root` override** (option 1) — the
  cheapest, and #122's own leaning. Rejected because it does not cover the
  divergences `adopt` exists for: references in a shared `bib/`, datasets under
  `data/`. Neither sits under a research root, so neither can be expressed by
  moving one. Those repos would have to relocate files, which reduces "record
  what you find" to "record where the tree lives".
- **A full per-file `layout:` block with `{paper_id}` interpolation** (option 3)
  — maximum flexibility for `adopt`, and it would let a repo keep literally any
  arrangement. Rejected on two counts. It is the largest validation surface: every
  artifact becomes a key that can be misspelled, escape the repo, collide with
  another key, or interpolate wrongly, and each of those needs an error path and
  a covered branch. And it would let two defendable-science repos look nothing
  alike, weakening the "tracked the same way everywhere" promise in
  `research-init`'s own description — the point of the methodology is that a
  reader who knows one repo can read the next one.
- **A tri-state `thesis_dir` (unset / a path / explicitly disabled)** to mark a
  repo as non-thesis. Rejected because it collides with defaults-omitted
  semantics, and because it would make thesis-ness a claim in config that can
  disagree with the tree on disk — exactly the kind of unverifiable assertion
  `check` exists to eliminate.
- **Leaving the layout as prose and hard-coding the defaults** — the status quo.
  It is the smallest diff, but it leaves nothing for `check` to check against,
  no way for `adopt` to record a divergence, and nine copies to keep in step by
  review.

## Links

- [#122](https://github.com/davorrunje/defendable-science/issues/122) (this
  decision), [#120](https://github.com/davorrunje/defendable-science/issues/120)
  (`init`), [#121](https://github.com/davorrunje/defendable-science/issues/121)
  (`check`), [#123](https://github.com/davorrunje/defendable-science/issues/123)
  (the `cache_dir` confinement follow-up)
- ADR-0031 (`0031-config-driven-cache-dir.md`) — the config-driven-path precedent
  this mirrors; ADR-0017 (`research-init`: one skill, two modes) — why `adopt`
  needs a recordable layout; ADR-0018 (git-native source of truth) — why it is
  recorded in committed YAML; ADR-0028 (the coverage gate the validation
  branches are written against)
- `defendable-science/defendable_science/scaffold/layout.py` (`Layout`,
  `LAYOUT_KEYS`, `resolve_layout`, `LayoutError`);
  `defendable-science/defendable_science/core/config.py` (`find_repo_root`);
  `defendable-science/defendable_science/cli.py` (`_layout_or_exit`,
  `_repo_relative`); `defendable-science/defendable_science/exploration/backlog.py`
  (`scaffold_paper`, `registry_root`)
- `docs/superpowers/specs/2026-08-27-scaffold-check-layout-design.md` § *PR1* —
  the design this records
