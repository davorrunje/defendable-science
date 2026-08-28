# Design — Pydantic at the parsing boundary (ADR-0043, then JSON adoption)

**Date:** 2026-08-29
**Author:** Davor Runje
**Status:** Approved design; not yet implemented.
**Scope:** [#169](https://github.com/davorrunje/defendable-science/issues/169) — phase 1
records the decision, phase 2 lands its first adoption across the JSON boundaries.

> Replaces the blanket prohibition at [`CLAUDE.md:64`](../../../CLAUDE.md), which was never
> backed by an ADR yet is cited as a driver by ADR-0029, ADR-0031 and ADR-0038.
> Governed by the repo's **failure-honesty** rule and by ADR-0028's 100% coverage gate.

## 1. Problem

`CLAUDE.md` says *"Pydantic is deliberately rejected (keep the wheel light, no Rust-binary
conflicts) — do not reintroduce it."* That rule has no ADR.
`decisions/0031-config-driven-cache-dir.md:31-32` reads *"no Pydantic (ADR rejecting it
stands)"*, pointing at a document that does not exist; ADR-0029 and ADR-0038 repeat the
prohibition as a decision driver. So a constraint that shaped at least three recorded
decisions has no context, no drivers, no rejected alternatives, and nowhere it can be
revisited.

Both halves of the original rationale were checked against the repo and neither holds.

**"No Rust-binary conflicts"** presupposes the package shares an environment with the
consumer's ML stack. It does not, by explicit design: `resources/ensure-tooling.md:56-59`
requires an isolated `uv`/`pipx` tool env or a per-user state venv, *"never the consumer
repo's project env. This is what lets `defendable-science` depend freely on `typer` /
`requests` / `pyyaml` / `pooch` without touching anyone's torch/jax install."*
`pydantic-core` cannot collide with a consumer's `torch`/`numpy` because it is never
installed beside them.

**"Keep the wheel light"** describes a wheel that is already not light. `uv tree --no-dev`
at v0.2.2 shows a 13-package runtime tree: `typer` pulls `rich` (→ `markdown-it-py`,
`mdurl`, `pygments`), `shellingham`, `annotated-doc`; `pooch` pulls `packaging`,
`platformdirs`; `requests` pulls `certifi`, `charset-normalizer`, `idna`, `urllib3`.
Adding `pydantic` adds `pydantic-core`, `annotated-types`, `typing-extensions` and
`typing-inspection` — a real download-size increase, since `pydantic-core` ships a compiled
per-platform wheel, but a difference of degree, not of kind. The other three are pure Python.

What the decision is weighed against is the cost of the status quo. The package hand-parses
input it did not write at 10 `yaml.safe_load` sites and 10+ `json.loads` sites across nine
modules, each re-implementing "is the key present / is the value the type we assumed / what
now". Ad-hoc `data.get(key, default)` is exactly the construct the failure-honesty rule
exists to prevent: a field missing because a response was truncated and a field legitimately
absent collapse into the same value at the point of use, so the caller can no longer tell
"failed" from "legitimately empty".

Six defects were verified against `main` and are the concrete justification for phase 2:

| # | Site | Defect | Symptom |
| --- | --- | --- | --- |
| 1 | `literature/graph.py:256-257` | `for work in page.get("results", [])` passes each element straight to `enrich_work(work)` with no `isinstance` check, though the *page* is checked at `:254` | A non-dict element raises `AttributeError` mid-pagination — a raw traceback |
| 2 | `literature/graph.py:81-86` (`_abstract`) | `index.items()` assumes `abstract_inverted_index` is a mapping | A string or list value raises `AttributeError` |
| 3 | `literature/graph.py:348-351` (`_aggregate_s2_edges`) | `edge["contexts"][0]` / `edge["intents"][0]` assume a non-empty *list* | A bare string silently yields **its first character** as the citation context — a wrong value, no error, straight into the record |
| 4 | `literature/graph.py:110-116` (`enrich_work`) | `publication_year` / `cited_by_count` pass through untyped | A string year propagates into the enrichment record and out through emitted CLI JSON |
| 5 | `literature/acquire.py:1939-1943` | `json.loads` then `data["candidate"]` … with four `cast()` calls | Bare `KeyError` on a malformed sidecar; `cast` has no runtime check, so `rung: 7` flows on as a str-typed int and mypy is actively misled |
| 6 | `cli.py:1549` | The parsed doc goes to `entry_from_croissant`, which calls `json_ld.get("name")` at `dataset/manifest.py:548` | A top-level JSON array raises `AttributeError`, which is **not** in the `except (OSError, json.JSONDecodeError, ManifestError)` tuple at `cli.py:1551` — a traceback instead of the documented exit 1 |

Items 3, 5 and 6 are failure-honesty violations in the `CLAUDE.md` sense.

Separately, an artifact's shape is re-stated in four places that can drift — the writer, the
reader, the shipped template under `resources/templates/`, and the rule in `check/checks.py`
— with nothing structural holding them in agreement.

## 2. Goals and non-goals

**Goals.**

1. An ADR that records where Pydantic is permitted, in a form that can be applied to the next
   case and revisited if it proves wrong.
2. Every document citing the old prohibition points at the new ADR or is marked as a
   statement about its own implementation.
3. `pydantic` as a pinned runtime dependency, with the wheel matrix verified against
   `requires-python`.
4. One shared `ValidationError` → domain-error seam, so the translation exists in exactly one
   module.
5. Defects 1–6 fixed, each with a regression test reproducing its exact symptom.
6. The five already-honest JSON sites consolidated onto the shared seam without losing
   message quality.

**Non-goals.**

- **YAML boundaries.** `core/frontmatter.py`, `scaffold/status.py:153`,
  `digest/artifact.py:259,386`, `progress/collect.py:456`, `literature/registry.py:506`,
  `core/config.py:92` and `dataset/manifest.py:312` (`datasets.yml`) stay hand-parsed. They
  are author-written rather than machine-generated, and the frontmatter schemas are the ones
  entangled with `resources/templates/` and `check/checks.py`; collapsing that four-way drift
  is a larger design task deserving its own issue once the JSON idiom has settled.
- **A general model layer.** Converting existing `dataclasses` is explicitly out (§3.2).
- **Modelling `enrich_work`'s output** as a CLI response envelope. Real drift, and §3.2 forbids
  a Pydantic model over emit-only data; it needs a stdlib dataclass instead. Filed as
  [#174](https://github.com/davorrunje/defendable-science/issues/174).
- **Rewriting `docs/superpowers/plans/*.md`.** Five of them restate "no Pydantic"; they are
  dated historical plans and editing them would falsify the record.

## 3. Decisions

Five, settled during brainstorming. §3.1–3.3 become ADR-0043's decision points; §3.4–3.5 are
the phase-2 behaviours the ADR's point 4 leaves open.

### 3.1 The boundary is *data entering the process*, not provenance

A Pydantic model is warranted for anything the package **reads that it did not construct in
this process**: third-party API responses, human- or publisher-authored files (Croissant,
CSL-JSON, frontmatter, `config.yml`, the key store), and its own on-disk artifacts read back
by a later invocation — the acquire quarantine sidecar.

The issue as filed drew the line by *provenance* ("third-party, or authored by a human or
outside party"). That wording does not cover its own examples: the sidecar at
`acquire.py:1069-1081` is written by us, and phase 2 models it. A rule stated as provenance
would need a carve-out; stated as "entering the process" it needs none, and it makes "is this
a finding?" answerable in review.

### 3.2 Nothing the package only emits gets a model

Internal value objects stay stdlib `dataclasses` — strict mypy is already the guarantee for
objects the package constructs itself. Do not convert an existing dataclass that never touches
untrusted input, and do not introduce a model for a shape the package both writes and reads
within one process. A Pydantic model over package-internal or emit-only data is a review
finding.

*Rejected:* Pydantic everywhere, replacing `dataclasses`. Buys nothing where mypy already
holds, costs a rewrite across ~30 modules. An architectural change, not debt repayment.

### 3.3 A boundary model is the authoritative schema for its shape

Where a boundary model exists, the writer, the shipped template and the corresponding `check`
rule derive from it **or are guarded against it in tests**, collapsing the four-way drift to
one source. A model that merely duplicates a schema still written longhand elsewhere has not
paid for itself.

This bites mainly in the deferred YAML phase. In phase 2 it applies to the sidecar, and it is
satisfied by the *test* arm rather than the derive arm: `acquire.py:1069-1081` builds the
payload from `candidate.as_json()` / `match.as_json()`, and rewriting the writer to construct
through the model would drag internal dataclasses into Pydantic in violation of §3.2. A
round-trip test asserting that what the writer emits validates against the model holds the two
in agreement without that cost.

### 3.4 A page hard-fails; a best-effort bundle degrades with the existing marker

ADR-0043's point 4 says a `ValidationError` becomes the module's explicit failure signal. Which
signal is a per-boundary choice, and the two providers differ.

**OpenAlex hard-fails the whole call.** One invalid row out of 200 raises a named `HttpError`
carrying the field path. This matches the contract already documented at `graph.py:241-243` —
*"stopping silently here would return a truncated frontier as if complete, so it is a hard
error"* — and OpenAlex's schema is stable enough that a type violation is an anomaly, not
routine noise.

*Accepted risk:* a third-party data glitch takes down a `cites()` call. That is the deliberate
trade; for an integrity tool a truncated frontier returned as if complete is worse.

*Rejected:* skip the row and carry a `skipped` marker (every caller and every emitted envelope
must then honour it — more surface, more branches); hard-fail structure but null out bad
scalars (exactly the "failed vs. legitimately empty" collapse the rule forbids).

**S2 citation edges skip and mark.** `_s2_context` is documented best-effort — an S2 miss
yields all-`None` — and S2 is the flakier provider, so a malformed edge must not kill an
optional enrichment. Each edge is validated individually; malformed ones are skipped; a
non-zero skip count adds `["context", "intent", "is_influential"]` to the `degraded` list
`enrich` already sets at `graph.py:382`. No new vocabulary, the loss is visible in the emitted
record, and defect 3's single-character context becomes impossible.

*Rejected:* hard-fail like OpenAlex (breaks the best-effort contract); extend the existing
silent `continue` (fixes the wrong value but a dropped edge stays invisible to the caller).

### 3.5 `HttpClient.get_json` and the response cache stay generic

`core/http.py:187` returns `JsonValue` and is shared by every caller; the model belongs at the
call site that knows the expected shape, not in the transport. The response cache at
`core/http.py:155-167` keeps storing raw JSON — validating on the way *out* of the cache is
what protects against a poisoned entry, and that happens at the call site too.

## 4. Phase 1 — record the decision

`decisions/0043-pydantic-at-the-parsing-boundary.md`, MADR shape (Context · Decision drivers ·
Considered options · Decision · Consequences · Rejected alternatives), register matching
`decisions/0041-dashboard-generated-by-the-cli.md`. §1's context material is lifted into it.

**Confirm 0043 is still free before writing** — 0042 is the highest on `main`, but other
branches may have claimed it.

Its five decision points are §3.1, §3.2, §3.3, the `ValidationError`-never-escapes rule
(realised by §3.4 and §5.1), and: **adoption is incremental and per-boundary**, each slice
landing with the tests that cover it, ADR-0028's gate unchanged and applying to the validation
and degradation branches too.

Rejected alternatives recorded with why:

- **Keep the blanket rejection** — preserves the lighter wheel, a real cost; preserves the
  four-way drift, the hand-rolled parsing at ~20 sites, and three ADRs citing a document that
  was never written.
- **Pydantic everywhere, replacing `dataclasses`** — §3.2.
- **`jsonschema`** — genuinely cheaper on the dependency axis (pure Python, no compiled wheel).
  Rejected because it validates without *parsing*: the payload is still an untyped `dict`, call
  sites keep hand-unpacking, mypy learns nothing, and the drift is untouched.
- **`TypedDict` + hand-written validators** — zero new deps, fully mypy-visible; the strongest
  case against. Rejected as the status quo with a name: those validators *are* the hand-rolled
  code being re-implemented per boundary.
- **`attrs` + `cattrs`** — comparable ergonomics, pure Python, a close call. Rejected for the
  narrower ecosystem around JSON-shaped external input, and because Pydantic's structured error
  objects drop straight into the failure signal §5.1 requires, where `cattrs` would need a
  hand-written translation layer — the very thing being removed.

Consequences worth stating: `requires-python = ">=3.11,<3.15"` constrains the acceptable
Pydantic version to one publishing wheels across that whole range, which becomes a release-time
check; and the risk of scope creep into a general model layer is bounded by §3.2 — a reviewer
should treat a Pydantic model over package-internal data as a finding.

**Document edits.**

| File | Change |
| --- | --- |
| `decisions/README.md` | Index row appended after the 0042 row |
| `CLAUDE.md:64` | The "Pydantic is deliberately rejected" sentence replaced by the scoped rule (boundary-only, `dataclasses` internally, `ValidationError` → explicit failure signal), citing ADR-0043 |
| `decisions/0029-api-key-handling.md` | Amendment blockquote after the status line |
| `decisions/0031-config-driven-cache-dir.md` | Amendment blockquote; the dangling *"ADR rejecting it stands"* now resolves |
| `decisions/0038-venue-resolvers-trusted-not-gated.md` | Amendment blockquote |
| `docs/design/proposals/dataset-manifest-tooling.md` | Short amendment note at `:46-47,129-130`; the design sketch itself is not rewritten — it is a point-in-time proposal for already-shipped tooling |

The amendment blockquotes use the house convention already at
`decisions/0029-api-key-handling.md:5-7` — `> **Refined by ADR-0043.** …` immediately after the
status line. Their decision text is **not** rewritten.

## 5. Phase 2 — the seam and the models

### 5.1 `core/models.py` — the only module that imports `ValidationError`

Two base configs, distinguished by who wrote the data:

- **`ExternalModel`** — `ConfigDict(extra="ignore", strict=True)`. Third-party APIs and
  publisher-authored files (OpenAlex, S2, Croissant); they add fields without notice.
- **`OwnedModel`** — `ConfigDict(extra="forbid", strict=True)`. Our own on-disk artifacts read
  back later (the acquire sidecar, the key store); an unexpected key there is a version
  mismatch worth surfacing.

`strict=True` is what buys defect 4: `"2024"` will not coerce to `int`.

Three public functions over one private formatter:

```python
def parse_obj(
    model: type[T], payload: object, *, source: str, error: Callable[[str], Exception]
) -> T:
    """Validate an already-parsed JSON value, or raise the caller's domain error."""

def parse_json(
    model: type[T], text: str, *, source: str, error: Callable[[str], Exception]
) -> T:
    """Parse and validate JSON text, folding a decode error into the same signal."""

def parse_each(model: type[T], items: Iterable[object]) -> tuple[list[T], int]:
    """Validate each item independently; return the valid ones and the count skipped."""
```

`T` is a classic `TypeVar("T", bound=BaseModel)` — **not** PEP 695 `[T: BaseModel]` syntax,
which needs Python 3.12 while `requires-python` is `>=3.11`.

`parse_obj` / `parse_json` raise `error(msg)` where `msg` is `f"{source}: {loc}: {reason}"`,
every error joined by `; ` — matching the message quality already set by `core/keys.py:181-183`
and `literature/registry.py:303-306`. `source` is a path or URL; `error` is the module's own
type (`RegistryError`, `ManifestError`, `HttpError`, `RetrievalError`, …).

`parse_json` folding `json.JSONDecodeError` into the same domain error is what lets the
consolidation sites collapse a two-branch try/`isinstance` into one call.

`parse_each` exists so a best-effort collection (§3.4's S2 edges) can skip bad members
**without** any caller catching `ValidationError`.

### 5.2 Slices

Land as separate PRs against #169, in order.

**Slice 1 — dependency and seam.** Add `pydantic>=2.13,<3` to `[project].dependencies` in
`defendable-science/pyproject.toml`; `uv sync && uv lock`; confirm `uv tree --no-dev` adds only
`pydantic`, `pydantic-core`, `annotated-types`, `typing-extensions` and `typing-inspection`.
Verified at design time: `pydantic-core` 2.48.0 ships `cp311`–`cp315` wheels, covering
`>=3.11,<3.15`. Try the `pydantic.mypy` plugin under `[tool.mypy]` against the pinned mypy and
drop it if it does not hold — it is a nicety, not load-bearing. Then `core/models.py` and its
tests.

**Slice 2 — `graph.py`, defects 1–4.** Models: `OpenAlexWork` (`id`, `doi`, `ids.arxiv`,
`display_name`/`title`, `publication_year`, `cited_by_count`,
`primary_location.source.display_name`, `authorships[].author.display_name`,
`abstract_inverted_index` as
`dict[str, list[int]] | None`, `referenced_works`), `WorksPage` (`results` +
`meta.next_cursor`), `S2ExternalIds`, `S2CitationEdge` (`contexts: list[str]`,
`intents: list[str]`, `isInfluential: bool`). The works page hard-fails as one unit per §3.4,
killing defects 1, 2 and 4 together. S2 edges go through `parse_each` and set the `degraded`
marker per §3.4.

**Slice 3 — the acquire sidecar, defect 5.** `QuarantineSidecar(OwnedModel)` with required
`candidate` / `match` / `rung` / `url`. All four `cast()` calls at `acquire.py:1940-1943` are
deleted; the `KeyError` becomes a named `RetrievalError` naming the field. Plus the §3.3
round-trip test asserting what `acquire.py:1069-1081` writes validates against the model.

**Slice 4 — Croissant, defect 6.** Validate the top level **inside** `entry_from_croissant`
(`dataset/manifest.py:534`), raising `ManifestError`. `ManifestError` is already in
`cli.py:1551`'s except tuple, so the tuple becomes truthful with no CLI change. Keep the
existing per-`distribution` checks or fold them into the model.

**Slice 5 — consolidation.** `core/keys.py:170-184`, `literature/registry.py:290-307`
(`_parse_items`), `cli.py:1805-1823` (`--points`), `cli.py:2383-2395` (`_parse_json_object`)
and `cli.py:2774-2800` (`--cells`) route through the helpers. These five already validate
honestly — they `isinstance`-check, raise a typed domain error naming the file, and distinguish
malformed from absent. For them Pydantic is a **consolidation**, not a bug fix: one error idiom
instead of five. They are the pattern being generalised *from*, which is why they go last.
Their existing tests keep asserting the same messages, or an assertion changes deliberately and
visibly in the diff.

## 6. Testing

ADR-0028's 100% statement + branch gate is unchanged and applies to the validation and
degradation branches.

- Each of defects 1–6 gets a regression test reproducing the exact symptom from §1's table.
  Defect 3's test asserts specifically that a bare-string `contexts` never yields a single
  character as the context.
- Each model gets three paths: valid, malformed, and **degradation** — proving the domain error
  surfaces with a usable message naming the field, rather than a `ValidationError` or a
  traceback.
- Defect 6 is additionally verified end-to-end:
  `printf '[1,2]' > /tmp/x.json && uv run defendable-science dataset ingest /tmp/x.json` exits 1
  with a message, not a traceback.
- `grep -rn "ValidationError" defendable_science/` shows it caught in exactly one module.
- `uv run pytest -q` and `uv run mypy` both pass.

## 7. Acceptance criteria

**Phase 1**

- [ ] `decisions/0043-pydantic-at-the-parsing-boundary.md` exists, MADR form, carrying the five
      decision points and the rejected alternatives of §4
- [ ] `decisions/README.md` has the 0043 index row, appended after 0042
- [ ] `CLAUDE.md:64` states the scoped rule and cites ADR-0043
- [ ] ADR-0029, ADR-0031 and ADR-0038 carry `> **Refined by ADR-0043.**` amendment notes; their
      decision text is not rewritten
- [ ] `docs/design/proposals/dataset-manifest-tooling.md` carries an amendment note;
      `docs/superpowers/plans/*.md` are untouched
- [ ] `grep -rn "Pydantic is deliberately rejected\|ADR rejecting it stands" .` returns nothing

**Phase 2**

- [ ] `pydantic>=2.13,<3` in `[project].dependencies`; `uv lock` updated
- [ ] `uv tree --no-dev` adds only `pydantic`, `pydantic-core`, `annotated-types`,
      `typing-extensions` and `typing-inspection` (the last is a pure-Python pydantic 2.13
      transitive; no compiled artifact, so the ADR's wheel-weight argument is unaffected)
- [ ] `ValidationError` is caught in exactly one module
- [ ] Defect 1: a `results` page with a non-dict element yields a named `HttpError`
- [ ] Defect 2: a non-mapping `abstract_inverted_index` is rejected explicitly
- [ ] Defect 3: an edge whose `contexts` is a bare string never yields one character; the skip
      is visible in `degraded`
- [ ] Defect 4: `publication_year: "2024"` is rejected, not propagated
- [ ] Defect 5: no `cast()` calls remain at `acquire.py:1939-1943`; a malformed sidecar raises a
      named error naming the field
- [ ] Defect 6: `dataset ingest` on a top-level JSON array exits 1 with a message
- [ ] The five already-honest sites route through the shared helper with no loss of message
      quality
- [ ] `uv run pytest -q` passes with the 100% gate intact; `uv run mypy` passes strict
- [ ] No Pydantic model over package-internal or emit-only data (§3.2)

## 8. References

- `CLAUDE.md:64` — the prohibition being replaced; `CLAUDE.md:62` — material decisions get an ADR
- `decisions/0029-api-key-handling.md:5-7` (amendment-note convention), `:84`
- `decisions/0031-config-driven-cache-dir.md:31-32` — the dangling reference
- `decisions/0038-venue-resolvers-trusted-not-gated.md:76-77`
- `decisions/0041-dashboard-generated-by-the-cli.md` — register and structure to match
- ADR-0024, ADR-0026 — the isolated-install model the §1 rebuttal rests on
- ADR-0028 — the coverage gate
- `resources/ensure-tooling.md:56-59` — the isolation guarantee
- `docs/design/proposals/literature-citation-graph-client.md` — the design behind `graph.py`
- `docs/design/proposals/dataset-manifest-tooling.md:46-47,129-130`
- `defendable-science/pyproject.toml` — `requires-python`, current runtime dependencies
