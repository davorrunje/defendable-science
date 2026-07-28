# Proposal: Shared `backlog` helper for the two exploration skills

`Status: implemented (designed 2026-07-18) · Skill: hypothesis-exploration / paper-exploration`

## Context

Both **generate** skills run the same small state machine over a markdown backlog
table, and both currently leave the mechanics unimplemented. **Interim (until the
module is implemented):** each skill orchestrates the row edits by hand / via direct
tool calls; once `defendable-science` is installed (via
[`ensure-tooling`](../../../resources/ensure-tooling.md)) the skill calls
`defendable-science backlog …` instead. The two skills:

- `hypothesis-exploration` (`../../../skills/hypothesis-exploration/SKILL.md`, §Verbs,
  § *Tooling*) drives rows in a paper's `docs/research/<paper>/backlog.md`.
- `paper-exploration` (`../../../skills/paper-exploration/SKILL.md`, §Verbs) drives
  rows in `docs/research/portfolio-backlog.md`, and on `promote` also writes the
  paper registry `docs/research/papers.md`.

They are the same shape one level apart (ADR-0005 three-level mirror; ADR-0006
two-skills-per-level, `../../../decisions/0006-two-skills-per-level.md`): identical
verbs, identical firewall, identical file-drawer discipline. Editing the table by
hand is fragile — provenance snippets are verbatim (may contain `|`), illegal
state transitions are easy to make, and drop reasons get skipped. One shared
helper removes the drift risk and makes both `TODO`s disappear at once.

## Goal

A single, level-parametric `backlog` helper that **appends** and **transitions**
rows through `parked → candidate → ranked → promoted | dropped`, while
**preserving provenance** and **recording drop reasons**. It performs the
mechanical file operations the two skills already specify; it makes **no
scientific judgment** and never selects what to promote.

## Design sketch

**One module, two column profiles.** A single module,
`defendable_science/exploration/backlog.py` (exposed as `defendable-science backlog`, shared by both
exploration skills), parameterized by `--level {hypothesis|paper}`. The row state
machine, provenance rules, and drop discipline are identical across levels; only
the scored columns and the `promote` target differ.

Row schema (shared columns in **bold**, level-specific in *italics*):

```
hypothesis: | id | one-line | move/type | provenance | EIG | feas | interest | frame | status | note |
paper:      | id | one-line | lens      | provenance |  —  | feas | interest |   —   | status | note |
```

- **id / one-line / provenance / status / note** are shared and load-bearing.
- *EIG* and *frame* (gap-spotting vs. problematization) exist only at the
  hypothesis level; the paper level ranks on feasibility × interest alone.

**Transition verbs** (invoked as `defendable-science backlog <verb>`; each validates the source
state and refuses illegal moves):

| Verb | Args | Effect | Guard |
|---|---|---|---|
| `park` | one-line, origin | append a `parked` row | provenance required |
| `add` (`generate`) | rows w/ provenance | append `candidate` rows | provenance required |
| `rank` | id, scores | set `ranked` + write scores | source ∈ {candidate, parked} |
| `promote` | id, slug | scaffold next-stage artifact, link it, set `promoted` | source = ranked; **human pick** |
| `drop` | id, reason | set `dropped`, write reason to `note` | reason required; row kept |

`park` and `add` never rank; `promote` and `drop` are terminal and **never delete**
a row (file-drawer discipline — `../01-lifecycle.md` §3).

A read-only **`list`** companion (`defendable-science backlog list [--level L] [--status S]`)
prints matching rows and mutates nothing — the everyday inspection command, the
backlog analog of `progress status`. It performs no transition, so it sits outside
the transition table above.

**Provenance preservation.** The helper copies the origin verbatim and never
paraphrases. For a scout-seeded row it stores the `source-paper-id` **plus** the
citing-context snippet returned by `literature scout` (grounding:
`../../../resources/references/citation-scouting.md`); for EDA, `eda:<dataset-id>` +
observation; for hand-parked, `own`. Because snippets can contain table-breaking
characters, the helper is responsible for escaping on write and round-tripping on
read (see Open questions on the storage format).

**`promote` scaffolds and links the next-stage artifact.** This is the only verb
that touches files outside the backlog, and only on an explicit human pick:

- *hypothesis level* → create `docs/research/<paper>/hypotheses/<YYYY-MM-DD-slug>/`,
  write `hypothesis.md` from the shared template with the status frontmatter block
  (`../../../resources/templates/`; frontmatter contract in
  `../../../skills/progress/SKILL.md`), carry the provenance forward, then set the
  row to `promoted` with a relative link to the folder. Hand-off to
  `hypothesis-testing`.
- *paper level* → scaffold the paper root (`hypotheses/`, `backlog.md`, `paper/`),
  seed `paper/pitch.md` from the row, **and append the registry row to
  `docs/research/papers.md`** (`paper-id → root + backend:` binding). A backlog
  candidate is not in `papers.md` until promoted — the backlog is proposals, the
  registry is committed papers. Hand-off to `paper-synthesis`.

**Interaction with `papers.md`.** The helper only ever *appends* a registry row on
paper-level `promote`; it never edits an existing registry row and never sets a
`decision.md` verdict. `progress` (`../../../skills/progress/SKILL.md`) reads the
registry + artifact frontmatter read-only (**not** the backlog table) and is
unchanged by this proposal.

## Dependencies & posture

- **Light-dep:** `pyyaml` + stdlib only (matches `literature`'s
  `defendable_science/literature/graph.py` and the substrate). `pyyaml` covers the status
  frontmatter it writes on
  `promote` and the `papers.md` row; the backlog table itself is plain markdown.
- **Firewall — proposes only.** Every verb but `promote` stays inside exploration;
  `promote` runs only on an explicit human pick and is the sole path out. The
  helper mechanically scaffolds and links — it never ranks by fiat, never
  auto-promotes the top row, and never writes a verdict (meta-spec §2.1, §2.3,
  `../00-meta-spec.md`).
- **Interim path stays valid.** Until the module lands, both skills keep editing
  the table by hand in the documented column order; the `defendable-science backlog` command is
  additive.

## Open questions

1. **Storage format.** Keep the human-readable markdown table and have the helper
   escape/round-trip provenance, or back the backlog with a YAML sidecar rendered
   to markdown for reading? The table is author-friendly and already parsed by
   `rank`/`list`; a sidecar is safer for verbatim snippets. Leaning: keep the
   table, escape on write.
2. **Slug ownership.** Does `promote` mint the `<YYYY-MM-DD-slug>` / `paper-id`, or
   does the human supply it? (`paper-id` must be stable and never reused.)
3. **Concurrency.** Two sessions appending to one backlog — is a simple
   append-only + git-merge posture enough, or is a lock needed?

## Acceptance criteria

- One helper serves both levels via `--level`, with the two column profiles above.
- All five verbs implemented; illegal transitions rejected with a clear message.
- `park`/`add` refuse a row without provenance; `drop` refuses without a reason and
  retires (never deletes) the row.
- Scout provenance (`source-paper-id` + citing-context snippet) is stored verbatim
  and survives a read/write round-trip unaltered.
- `promote` scaffolds the correct next-stage artifact, writes its status
  frontmatter, links it from the row, and — at paper level — appends the
  `papers.md` registry row; it runs only on an explicit id argument (human pick).
- No verb writes a verdict or `decision.md`; `progress` continues to read the
  registry + artifact frontmatter unchanged (it does not read the backlog table).
- Deps limited to `pyyaml` + stdlib.

## Links

- `../../../skills/hypothesis-exploration/SKILL.md` — verbs, row schema, the `TODO`.
- `../../../skills/paper-exploration/SKILL.md` — portfolio backlog, `papers.md`.
- `../../../skills/progress/SKILL.md` — status frontmatter this helper writes.
- `../00-meta-spec.md` §2.1/§2.3 — agency + firewall.
- `../01-lifecycle.md` §3 — file-drawer / rigor kit.
- `../../../decisions/0006-two-skills-per-level.md` — two-skills-per-level.
- `../../../resources/references/citation-scouting.md` — provenance grounding.
