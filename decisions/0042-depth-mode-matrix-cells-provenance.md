# ADR-0042: A depth-mode digest feeds the concept matrix through the *absence* of `status.extraction`

- Status: accepted · Date: 2026-08-29 · Deciders: Davor Runje

## Context

ADR-0040 gave `digest` a second mode — extraction — so a survey can fill the concept
matrix's cells from many papers without paying depth mode's comprehension cost. Only
extraction fed the matrix: `digest extract render` reads a paper's cells out of a
delimited block (`digest/artifact.py:read_cells`) that only `write_extraction` wrote.

A depth digest establishes the same kind of locatable claims the matrix axes ask for —
problem, method, key result, assumptions, limitations — at a *higher* standard than
extraction, because a human demonstrated understanding of them rather than an agent
merely locating them. But it had no cells block, so a paper read properly could not
contribute a row without re-extracting it: duplicated work, and a record of the paper at
extraction's weaker standard despite having met the stronger one. #142 filed this as the
gap; the design spec listed it as follow-up 2 (§13).

The mechanical fix is uncontroversial and reuses everything ADR-0040 built: the same
`Cell` shape, the same mandatory locator, the same `extraction.validate` path, written
into the *same* delimited cells block `read_cells` already understands, so
`digest extract render` needs no change on the read side at all. What is not mechanical,
and is the actual subject of this ADR, is **how a reader — human or `check` — tells a
depth-sourced row apart from an extracted one**, given that the two were established at
different standards and must not be blurred (ADR-0040's guarantee-inflation hazard,
still the organizing concern here).

## Decision drivers

- **Failure honesty** (repo-wide). A depth-sourced row and an extracted row are different
  claims about the same paper; nothing may read one as the other, or as a stronger/weaker
  version of itself than it is.
- **No new false claim.** `status.extraction`'s `in-sample` / `batch-check` fields
  describe extraction's own sampling regime (ADR-0040 decision 2) — a regime that never
  ran for a depth-read paper. Writing `batch-check: pending` on such a paper would assert
  that a sampling regime applies to it, which is false.
- **Reuse over new surface.** ADR-0040 already built the validated writer, the delimited
  block, and the host-preserving render. A provenance mechanism that requires a new file
  shape, a new field the render side must learn to read, or a parallel matrix, throws that
  away for a fact that has a cheaper representation.
- **Anti-Goodhart.** A provenance signal that can be forged more cheaply than actually
  depth-reading a paper (e.g. a self-reported "source: depth" flag) is not a signal.

## Considered options

**How a row's provenance is marked.**

1. **The absence of `status.extraction`** on an artifact that carries a cells block.
   *(chosen)*
2. A new frontmatter field (e.g. `status.extraction.source: depth`) on the cells block
   itself.
3. A marker in the matrix row (a column, a footnote glyph) written by `render`.
4. A `status.extraction` block with `in-sample`/`batch-check` given placeholder values
   (`null`, or a new enum member meaning "not applicable").

**What the depth-sourced writer does when the artifact already carries `status.extraction`,
or carries no `status.understanding`.**

1. Overwrite silently, or seed a bare artifact if one is missing. *(rejected)*
2. **Refuse both directions**, leaving the artifact untouched. *(chosen)*

**Whether `digest extract render`'s default batch changes.**

1. Leave it selecting `status.extraction`-bearing artifacts only, so a depth-sourced row
   renders only via explicit `--citekey`.
2. **Widen it to any artifact with either `status.extraction` or a cells block.** *(chosen)*

## Decision

### 1. Provenance is the *absence* of `status.extraction`, not a new field

`write_depth_cells` (`digest/artifact.py`) writes **only** the delimited cells block —
the same `_render_block`/`_locate_block`/`_splice_block` machinery `write_extraction`
already uses — and never touches `status.extraction`. A cells block with
`status.extraction` present is extraction-sourced (today's only case, unchanged); a cells
block with `status.extraction` absent is depth-sourced. `has_extraction_or_cells`
(`digest/artifact.py`) is the one predicate that reads this composite fact, used by
`extract render`'s default-batch discovery (below); nothing about `read_cells` or
`render_matrix` changes, since neither ever looked at `status.extraction` to begin with —
they only ever read the cells block.

This is not a new invariant bolted on; it falls directly out of two things ADR-0040
already established: `status.extraction`'s block is written by exactly one function
(`write_extraction`), and it describes a regime (sampling) that is meaningless without an
extraction having happened. A depth-sourced cells block simply never goes through that
function, so the field it would have written is, correctly, never there.

### 2. `write_depth_cells` refuses in both directions rather than seeding or overwriting

Unlike `write_extraction`, which may seed a bare artifact for a paper nothing has
touched (a paper skipped for want of a PDF still gets *some* artifact once its cells are
recorded), `write_depth_cells` **requires an existing artifact carrying
`status.understanding`**. Depth-sourced cells restate claims a depth digest already
certified; there is nothing honest to seed if that certification never happened, and
silently creating a bare artifact would let a depth-sourced cells block exist for a paper
nobody actually read at depth.

It also **refuses an artifact that already carries `status.extraction`**. Allowing it to
proceed would let a depth-sourced write silently override extraction's cells on the same
artifact — the exact direction of blurring ADR-0040 organized its whole design against,
just inverted. The human's remedy in that case is `digest extract record`, named in the
refusal.

Both refusals leave the artifact byte-identical: a rejected write is not a partial one.

### 3. `digest extract render`'s default batch is *every artifact with recorded cells*, not every artifact `status.extraction` names

This is the one place the "no change needed on the render side" claim (§13 of the design
spec) turned out to be incomplete, and worth recording precisely because it was not
obvious in advance. `read_cells` and `render_matrix` needed zero changes — proven by
tests that name an artifact explicitly. But `extract render`'s *default* batch (no
`--citekey`) was discovered via `_extraction_batch`, which filters strictly on
`has_extraction`. Left as-is, every depth-sourced cells block would be silently excluded
from a bulk render while the run still reported `ok: true` — exactly the "silently
skipped inside a bulk render that still reports success" failure #142's acceptance
criteria forbid, and a real one: a survey author who ran `digest extract render` with no
arguments, as the skill has always shown, would simply never see their properly-read
papers' rows appear, with no error to explain why.

The fix is a second predicate, `has_extraction_or_cells`, used only by `extract render`'s
default-batch discovery; `digest extract sample`'s batch stays `has_extraction`-only
(`_extraction_batch`, unchanged), because extraction's sampling regime is meaningless for
a depth-sourced paper and folding it in there would let a bulk sample draw a paper that
regime never touched. An artifact that declares `status.extraction` but is missing its
cells block (a pre-existing corruption case, unrelated to this ADR) still surfaces as a
read error when its cells are gathered, exactly as it did before — `has_extraction_or_cells`
does not change that path, only adds the depth-sourced one alongside it.

**Review of this change caught one more instance of the same failure class**, on the other
side of the same predicate: a depth digest with `status.understanding` but **no** cells
block at all is correctly excluded from the default batch by `has_extraction_or_cells`
(there is nothing of it to render), but exclusion alone left it unmentioned anywhere —
`batch`, `errors`, and stderr all stayed silent about it, so a survey author who read a
paper at depth and forgot to run `digest depth cells record` would see a clean `ok: true`
bulk render with no sign that paper was ever a candidate. This is the same "silent skip in
a bulk render that reports success" #142's acceptance criteria forbid, just triggered by
"no cells recorded yet" rather than "cells block missing after being declared" (§3's
original finding). Fixed with a third predicate, `has_understanding_without_cells`, and a
`pending` list in `extract render`'s default-batch report (plus a stderr line per pending
citekey) — deliberately **not** folded into `errors` and not affecting `ok`, since an
unrecorded paper is an incomplete population, not a defect in the run that did happen.

### 4. The accountability log gets a distinct `kind`

`write_depth_cells` appends to the same accountability log `write_extraction` does
(ADR-0033), with `kind: depth-cells` rather than `kind: extraction` — cheap, since both
writers already share `_log_body`, parameterized by `kind`. An auditor reading the log
alone, without opening the artifact, can tell which standard produced each entry.

## Consequences

- A paper read at depth can contribute a matrix row without re-extraction, at the
  standard it actually met, via `digest depth cells record` (mirrors `digest extract
  record`'s shape: validated cells in, one paper's worth, the same locator and
  `not-addressed` rules).
- The matrix itself carries no visible provenance marker on the row — a reader who wants
  to know which standard produced a given row must open that paper's digest artifact and
  check for `status.extraction`. This is a real cost, accepted deliberately: the
  alternative (a marker column or footnote in `positioning.md`) would need `render_matrix`
  to plumb provenance through the merge, coupling a pure table-splice function to a fact
  about *how the row's source paper was read* that has nothing to do with rendering a
  table.
- `check_extraction`'s cell-validation family (`check/checks.py`, defendable-science#147)
  only validates a digest's cells when `status.extraction` is present
  (`if extraction is None: continue`). Under this design, a depth-sourced cells block has
  no `status.extraction`, so `check_extraction` does not validate it — its locators, its
  axis correctness, nothing. This is a real gap, filed as a separate, self-contained
  follow-up (defendable-science#167) rather than folded into this change: extending
  `check_extraction` to also validate a cells block with no `status.extraction` is a
  distinct unit of work (deciding what "invalid" means with no `status.extraction.cells`
  count to check against, and reusing `_check_cell` for a population `check_extraction`
  was not written to see) that deserves its own review rather than riding along on an
  already-large issue.
- `has_extraction` itself is unchanged and keeps its original meaning ("this paper was
  extracted") for every caller that still needs exactly that fact
  (`digest extract sample`, `check_extraction`).

## Rejected alternatives

- **A new frontmatter field marking source.** E.g. `status.extraction.source: depth` (or
  a parallel `status.depth-cells` block echoing `status.extraction`'s shape). Either
  requires a field on a block that, per ADR-0040, is only ever written by
  `write_extraction` — putting anything there for a depth-sourced row reintroduces exactly
  the shared-field blurring ADR-0040 rejected for `status.understanding` vs
  `status.extraction` in the first place, one level down.
- **A marker in the rendered matrix row** (an extra column, a footnote glyph on the
  citekey). Couples `render_matrix` — a pure, host-preserving table splice with no
  knowledge of where a cell came from — to provenance, and forces every future consumer of
  the matrix (a human skimming it, a future automated reader) to parse a convention out of
  a markdown table rather than reading a fact off the source artifact. Provenance already
  has a home: the artifact that was actually read.
- **`status.extraction` with placeholder `in-sample`/`batch-check` values** (`null`, or a
  new `"n/a"` verdict). Was the closest alternative to the chosen design, and rejected for
  the reason ADR-0040 already gives for rejecting a single `sampled:` field: any value in
  those two fields is read as a finding about *this paper's* sampling, and a paper that was
  never in an extraction batch has no sampling finding to report, positive or placeholder.
- **Seeding a bare artifact for `write_depth_cells`, mirroring `write_extraction`.**
  `write_extraction`'s seed exists because a paper can legitimately have extracted cells
  and nothing else (never read, never mirrored). A depth-sourced cells block has no
  equivalent legitimate "nothing else" case — it is only ever authored *because* a depth
  digest already exists — so seeding one would let the write succeed for a paper nobody
  actually read at depth, which is the one thing this whole design exists to prevent.
- **Allowing `write_depth_cells` to overwrite an already-extracted artifact.** Would let a
  depth-sourced write erase extraction's cells (and the `status.extraction` block that
  makes them legible as extraction's), destroying the batch's accountability-log linkage
  without any refusal to catch it.
- **Leaving `extract render`'s default batch as `status.extraction`-only.** Technically
  correct (an explicit `--citekey` still renders a depth-sourced row), but leaves the
  common case — "render everything I've recorded" — silently incomplete, which is
  precisely the "silent skip inside a bulk render that reports success" #142's acceptance
  criteria was written to forbid.
- **Folding the `check_extraction` gap into this change.** Considered and rejected on
  scope grounds alone, not because it is unimportant: deciding what "invalid" means for a
  cells block with no `status.extraction.cells` count to check against is a distinct
  design question, and #142 was already large enough without it. Filed as
  defendable-science#167.

## Links

`decisions/0040-digest-extraction-mode.md` (the extraction mode this builds on, and the
guarantee-inflation hazard this ADR extends);
`defendable-science/defendable_science/digest/{artifact,extraction,render}.py`;
`defendable-science/defendable_science/cli.py` (`depth_cells_record`, `_render_batch`,
`_extraction_batch`, `_digest_batch`); `skills/digest/SKILL.md` § "The extraction
artifact"; ADR-0033 (the shared accountability log); #142 (this work);
defendable-science#167 (the `check_extraction` follow-up).
