<!-- defendable-science staged-document templates -->

# Staged-document templates

Fillable skeletons for every staged document the `defendable-science` pipeline produces.
The skills *draft* these as proposals; the **author authors and decides**. Copy a
template into the consumer repo's `docs/research/` tree at the location its skill
scaffolds, then fill it in — replace every `<...>` placeholder and delete the
guidance comments as you go.

These are skeletons, not essays. Keep them short. The science is in the content
you add, not in prose the template ships with.

## What produces what

| Template | Produced by (skill · stage) | Deployed to |
|---|---|---|
| `hypothesis/hypothesis.md` | `hypothesis-testing` · claim | `docs/research/<paper>/hypotheses/<YYYY-MM-DD-slug>/hypothesis.md` |
| `hypothesis/strategy.md` | `hypothesis-testing` · strategy (rigor kit + defend) | `.../<slug>/strategy.md` |
| `hypothesis/design-plan-README.md` | *pointer only* — design/plan are **delegated to the bound engineering backend** | `.../<slug>/{design,plan}.md` |
| `hypothesis/findings.md` | `hypothesis-testing` · findings (**material decision**) | `.../<slug>/findings.md` |
| `paper/pitch.md` | `paper-synthesis` · pitch | `docs/research/<paper>/paper/pitch.md` |
| `paper/positioning.md` | `paper-synthesis` · positioning | `.../paper/positioning.md` |
| `paper/ledger.md` | `paper-synthesis` · sections (Toulmin-sextet claim→evidence ledger) | `.../paper/ledger.md` |
| `paper/decision.md` | `paper-synthesis` · decision (**material decision**) | `.../paper/decision.md` |
| `thesis/aims.md` | `thesis` · framing | `docs/research/thesis/aims.md` |
| `thesis/kappa.md` | `thesis` · synthesis + defensibility (**material decision**) | `docs/research/thesis/kappa/kappa.md` |
| `thesis/milestones.yml` | `thesis` · framing (configurable program gates) | `docs/research/thesis/milestones.yml` |

Design/plan (hypothesis) and outline/plan (paper) are **engineering**, delegated to
the bound engineering backend via the engineering-delegation contract (its
`design` → `plan` capabilities); `defendable-science` ships no templates for them. See
`hypothesis/design-plan-README.md`.

## Status-frontmatter convention

Every hypothesis / paper / thesis artifact carries one `status:` block in its
markdown frontmatter — the single source of truth `progress`
(`../../skills/progress/SKILL.md`) reads and rolls up. There is deliberately no
separate progress file. **Field set (copied verbatim from `progress/SKILL.md`):**

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
