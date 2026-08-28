<!-- defendable-science staged-document templates -->

# Staged-document templates

Fillable skeletons for every staged document the `defendable-science` pipeline produces.
The skills *draft* these as proposals; the **author authors and decides**. Copy a
template into the consumer repo at the location its skill scaffolds, then fill it
in — replace every `<...>` placeholder and delete the guidance comments as you go.

These are skeletons, not essays. Keep them short. The science is in the content
you add, not in prose the template ships with.

**This directory holds the prose skeletons only.** The machine-read files — the
registries, the backlogs, the config, the dashboard — are *not* templated here;
`defendable-science init` renders each one from the package, because the package
already owns its columns and validators. A second copy here would be a second
editable definition of a shape a loader has to parse, and the two would drift.
The one thing both sides do write is the status frontmatter block, which is why
it has a drift guard (see below).

## What produces what

| Template | Produced by (skill · stage) | Deployed to |
|---|---|---|
| `hypothesis/hypothesis.md` | `hypothesis-testing` · claim | `docs/research/<paper>/hypotheses/<YYYY-MM-DD-slug>/hypothesis.md` |
| `hypothesis/strategy.md` | `hypothesis-testing` · strategy (rigor kit + defend) | `.../<slug>/strategy.md` |
| `hypothesis/design-plan-README.md` | *pointer only* — design/plan are **delegated to the bound engineering backend** | `.../<slug>/{design,plan}.md` |
| `hypothesis/findings.md` | `hypothesis-testing` · findings (**material decision**) | `.../<slug>/findings.md` |
| `paper/pitch.md` | `paper-exploration` · promote scaffolds the stub (status frontmatter + the backlog row's one-line and provenance); `paper-synthesis` · pitch develops it | `docs/research/<paper>/paper/pitch.md` |
| `paper/positioning.md` | `paper-synthesis` · positioning | `.../paper/positioning.md` |
| `paper/ledger.md` | `paper-synthesis` · sections (Toulmin-sextet claim→evidence ledger) | `.../paper/ledger.md` |
| `paper/decision.md` | `paper-synthesis` · decision (**material decision**) | `.../paper/decision.md` |
| `thesis/aims.md` | `defendable-science init --thesis` scaffolds the stub; `thesis` · framing develops it | `docs/research/thesis/aims.md` |
| `thesis/kappa.md` | `thesis` · synthesis + defensibility (**material decision**) | `docs/research/thesis/kappa/kappa.md` |
| `thesis/milestones.yml` | `defendable-science init --thesis` (configurable program gates, none started) | `docs/research/thesis/milestones.yml` |

The machine-read files have no template — each is rendered by the command named
here, from the module that owns its shape. Locations are the default layout; a
repo that records a `layout:` block in `.defendable-science/config.yml` gets the
same files at the paths it recorded.

| File | Produced by | Deployed to |
|---|---|---|
| `papers.md` | `defendable-science init` | `docs/research/papers.md` |
| `portfolio-backlog.md` | `defendable-science init` | `docs/research/portfolio-backlog.md` |
| `dashboard.md` | `defendable-science init` (a stub saying it has not been generated); `defendable-science progress dashboard` generates it, and is its only writer | `docs/research/dashboard.md` |
| `references.json` | `defendable-science init` (empty CSL-JSON) | `docs/research/literature/references.json` |
| `triage.yml` | `defendable-science init` | `docs/research/literature/triage.yml` |
| `datasets.yml` | `defendable-science init`; the `dataset` skill's `register` verb appends entries | `datasets.yml` |
| `config.yml` | `defendable-science init` — every binding `null`, never a placeholder | `.defendable-science/config.yml` |
| `rclone.conf.example` | `defendable-science init` (remote name and type only) | `.defendable-science/rclone.conf.example` |
| `.gitignore` | `defendable-science init` — **append-only merge**, never a rewrite | repo root |
| `<paper>/backlog.md` | `defendable-science backlog promote --scaffold` | `docs/research/<paper>/backlog.md` |

`thesis/milestones.yml` is the one file with a foot in both tables: it is a
shipped template *and* rendered by `init --thesis`, so `tests/test_render.py`
holds the two to one schema.

Design/plan (hypothesis) and outline/plan (paper) are **engineering**, delegated to
the bound engineering backend via the engineering-delegation contract (its
`design` → `plan` capabilities); `defendable-science` ships no templates for them. See
`hypothesis/design-plan-README.md`.

## Status-frontmatter convention

Every hypothesis / paper / thesis artifact carries one `status:` block in its
markdown frontmatter — the single source of truth `progress`
(`../../skills/progress/SKILL.md`) reads and rolls up. There is deliberately no
separate progress file.

The **definition** of the field set, its order, and the per-level enums lives in
`defendable-science/defendable_science/scaffold/status.py`; what follows is the
human-facing reference that mirrors it, with example values filled in. **The
field set and its order cannot drift** —
`defendable-science/tests/test_status.py` checks this block against
`status.render`, the same guard it runs over the nine shipped templates. The
enums in the comments below are *not* guarded, so read
`status.VERDICTS`/`status.READINESS` if a value here looks wrong.

**Field set:**

```yaml
status:
  level: hypothesis            # hypothesis | paper | thesis
  id: 2026-07-17-monotone-depth
  verdict: refuted             # hypothesis: pending|confirmed|refuted|inconclusive
                               # paper:      no-go|publish (once decided)
                               # thesis:     n/a (uses defensible below)
  readiness: resolved          # hypothesis: pending|resolved
                               # paper: drafting|under-review|published (sub-states of done)
                               # thesis: framing|synthesis|defensible
  signed-off-by: "D. Runje"    # named human on any material decision (§2.1); null until signed
  signed-off-date: 2026-07-17
  evidence: [run-ref://…]      # backend run-refs backing the verdict — never hand-copied numbers
  covers: [aim-2]              # paper→thesis: which aims this artifact supports
  load-bearing: true           # hypothesis→paper: does refutation block the parent's claim?
  understanding: {status: ok, unresolved: []}   # written by the `defend` skill; surfaced, never scored
  blockers: []                 # free-text blockers the author flags
  last-updated: 2026-07-17
```

Conventions that hold across every template:

- **Absence means "not yet set," never zero.** Leave a field `null`/`[]` until it
  is real; do not invent a value.
- **`verdict` and `readiness` are distinct axes.** A `refuted` hypothesis is a
  *resolved, done, valid* outcome — successful science, not a failure or a red
  mark. Never treat `refuted` (or a paper `no-go`) as failed.
- **Material decisions require a named human sign-off.** A `verdict` on a
  hypothesis, `verdict: publish|no-go` on a paper, and thesis `defensible` are only
  real once `signed-off-by` + `signed-off-date` are set. Until then `progress`
  reports the decision as *not yet decided*. The **`defend` guardrail fires before
  every sign-off** (a mock viva at the thesis gate); it surfaces gaps, the human
  may override, the override is logged — it is a stop-and-confirm, not a hard block.
- **Evidence is backend run-refs, never hand-copied numbers.** `evidence:` lists
  the run-refs that back the verdict; result numbers in the body are written only
  by the backend `tables` capability. See
  `../../resources/contracts/experiment-backend.md`.
- **`progress` is read-only.** It reads this block and never writes it (except the
  generated dashboard). Status is *written* by the resolve skills, the human
  sign-off, and `defend` (the `understanding` field).

Grounding: `../../docs/design/01-lifecycle.md` (§3 rigor, §4 templates, §8 material
decisions); `../../skills/progress/SKILL.md`; `../../resources/rigor/rigor-kit.md`.
