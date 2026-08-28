# ADR-0043: Pydantic is permitted at the parsing boundary, and nowhere else

- Status: accepted · Date: 2026-08-29 · Deciders: Davor Runje

## Context

`CLAUDE.md` said, under Conventions → Code style: *"Pydantic is deliberately
rejected (keep the wheel light, no Rust-binary conflicts) — do not reintroduce
it."* That rule has no ADR. It nonetheless shaped three recorded decisions:
`decisions/0031-config-driven-cache-dir.md`'s Decision-drivers section reads
*"no new dependency … no Pydantic (ADR rejecting it stands)"*, pointing at a
document that does not exist; `decisions/0029-api-key-handling.md`'s
Consequences section states *"Implementation stays light-dep (stdlib JSON + a
small loader); no Pydantic, no dotenv dependency"* as a fact about that
decision; and `decisions/0038-venue-resolvers-trusted-not-gated.md` repeats it
verbatim as a reason to reject real PDF verification — *"a new dependency (the
package deliberately stays light: `requests`, `pooch`, `pyyaml`, no
Pydantic)"*. So a constraint that shaped at least three decisions had no
context, no decision drivers, no rejected alternatives, and nowhere it could be
revisited on its own terms.

Both halves of the original rationale were checked against the repo as it
exists today, and neither holds.

**"No Rust-binary conflicts" presupposes the package shares an environment
with the consumer's ML stack. It does not, by explicit design.**
`resources/ensure-tooling.md:56-59` requires an isolated `uv`/`pipx` tool
environment or a per-user state venv, *"never the consumer repo's project
env. This is what lets `defendable-science` depend freely on `typer` /
`requests` / `pyyaml` / `pooch` without touching anyone's torch/jax
install."* That isolation is itself a recorded decision (ADR-0024, and
ADR-0026's independent-versioning compatibility pin), not an aspiration.
`pydantic-core` cannot collide with a consumer's `torch`/`numpy` because it is
never installed beside them — there is no shared environment for a Rust
extension to conflict inside.

**"Keep the wheel light" describes a wheel that is already not light.**
`uv tree --no-dev` at v0.2.2 shows a 13-package runtime tree:

- `typer` pulls `rich` (→ `markdown-it-py`, `mdurl`, `pygments`),
  `shellingham`, `annotated-doc`
- `pooch` pulls `packaging`, `platformdirs`
- `requests` pulls `certifi`, `charset-normalizer`, `idna`, `urllib3`

Adding `pydantic` adds three more: `pydantic-core`, `annotated-types` and
`typing-extensions` — a real download-size increase, since `pydantic-core`
ships a compiled per-platform wheel, but a difference of *degree*, not of
*kind*, against a tree that already carries a Rust-adjacent dependency
footprint (`urllib3`, `rich`'s C-accelerated paths) and eight indirect
packages before Pydantic is even considered.

What the rule was weighed against is the cost of the status quo it protected.
The package hand-parses input it did not write at 10 `yaml.safe_load` sites
and 10+ `json.loads` sites across nine modules, each re-implementing "is the
key present / is the value the type we assumed / what now." Ad-hoc
`data.get(key, default)` at those sites is exactly the construct the
repo-wide failure-honesty rule exists to prevent: a field missing because a
response was truncated, and a field legitimately absent, collapse into the
same value at the point of use — the caller can no longer tell "failed" from
"legitimately empty."

Six defects were verified against `main` and are the concrete justification
for adopting Pydantic rather than continuing to hand-roll the boundary:

| # | Site | Defect | Symptom |
| --- | --- | --- | --- |
| 1 | `literature/graph.py:256-257` | `for work in page.get("results", [])` passes each element straight to `enrich_work(work)` with no `isinstance` check, though the *page* is checked at `:254` | A non-dict element raises `AttributeError` mid-pagination — a raw traceback |
| 2 | `literature/graph.py:81-86` (`_abstract`) | `index.items()` assumes `abstract_inverted_index` is a mapping | A string or list value raises `AttributeError` |
| 3 | `literature/graph.py:348-351` (`_aggregate_s2_edges`) | `edge["contexts"][0]` / `edge["intents"][0]` assume a non-empty *list* | A bare string silently yields **its first character** as the citation context — a wrong value, no error, straight into the record |
| 4 | `literature/graph.py:110-116` (`enrich_work`) | `publication_year` / `cited_by_count` pass through untyped | A string year propagates into the enrichment record and out through emitted CLI JSON |
| 5 | `literature/acquire.py:1939-1943` | `json.loads` then `data["candidate"]` … with four `cast()` calls | Bare `KeyError` on a malformed sidecar; `cast` has no runtime check, so `rung: 7` flows on as a str-typed int and mypy is actively misled |
| 6 | `cli.py:1549` | The parsed doc goes to `entry_from_croissant`, which calls `json_ld.get("name")` at `dataset/manifest.py:548` | A top-level JSON array raises `AttributeError`, which is **not** in the `except (OSError, json.JSONDecodeError, ManifestError)` tuple at `cli.py:1551` — a traceback instead of the documented exit 1 |

Items 3, 5 and 6 are failure-honesty violations in the `CLAUDE.md` sense: a
malformed input is silently turned into a plausible-looking wrong value (3),
or turned into an undocumented crash instead of the documented clean exit
(5, 6).

Separately from correctness, an artifact's shape is re-stated in up to four
places that can drift with no structural mechanism holding them in
agreement: the writer, the reader, the shipped template under
`resources/templates/`, and the corresponding rule in `check/checks.py`.

## Decision drivers

- **Failure honesty (repo-wide rule).** A malformed input must surface as an
  explicit, actionable signal — never a raw traceback, never silently
  coerced into a plausible-looking wrong value, never collapsed into the same
  outcome as a legitimately absent field.
- **The original rationale, re-examined, does not hold** (see Context): the
  isolated-install architecture (ADR-0024/0026) removes the Rust-conflict
  premise, and the existing 13-package tree removes the "light wheel" premise
  as a categorical objection.
- **A rule with no ADR cannot be revisited on its own terms.** Three later
  ADRs inherited it as an unexamined driver; one of them (0031) cites a
  document that was never written.
- **ADR-0028's 100% coverage gate is unconditional** — whatever this decision
  adopts must keep validation and degradation branches inside that gate, not
  carve out an exception.
- **Domain-neutrality.** The decision must be a statement about parsing
  untrusted input in general, not about any one provider or file format.
- **Proportionate scope.** The fix is for a boundary problem; it must not
  become a license to rewrite code that already works and is already
  strict-mypy-checked.

## Considered options

1. **Keep the blanket rejection.** Leave `CLAUDE.md`'s rule as-is; fix the six
   defects with more hand-written `isinstance` checks.
2. **Pydantic everywhere, replacing `dataclasses`.** Adopt Pydantic as the
   package's general value-object layer.
3. **`jsonschema`.** Validate untrusted JSON against schema documents without
   introducing a parsing library.
4. **`TypedDict` + hand-written validators.** Formalize the status quo with
   type annotations but no runtime library.
5. **`attrs` + `cattrs`.** A structured, pure-Python parse/validate library as
   a lighter-weight alternative to Pydantic.
6. **Pydantic scoped to the parsing boundary** *(chosen)*. Adopt Pydantic only
   for data entering the process from outside it; keep everything else as
   stdlib `dataclasses`.

## Decision

Option 6. Five points, in the order they were settled:

**1. The boundary is data entering the process — not provenance.** A Pydantic
model is warranted for anything the package **reads that it did not construct
in this process**: third-party API responses (OpenAlex, Semantic Scholar),
human- or publisher-authored files (Croissant JSON-LD, CSL-JSON, YAML
frontmatter, `config.yml`, the key store), and its own on-disk artifacts read
back by a later invocation — concretely, the acquire quarantine sidecar.
Provenance is explicitly **not** the test: the issue as filed drew the line by
who authored the data ("third-party, or authored by a human or outside
party"), and that wording does not cover its own leading example — the
sidecar at `acquire.py:1069-1081` is written by *us*, in a prior invocation of
this same process, yet still crosses a process boundary when a later
invocation reads it back and must not simply trust its own past self's bytes
on disk. A rule stated as provenance needs a carve-out for that case; a rule
stated as "does this data enter the process" needs none, and it makes "is a
model warranted here?" answerable in review without first asking who wrote
the bytes.

**2. Nothing the package only emits gets a model.** Internal value objects
stay stdlib `dataclasses` — strict mypy is already the guarantee for objects
the package constructs itself entirely in-process. Do not convert an existing
`dataclasses` type that never touches untrusted input to Pydantic, and do not
introduce a Pydantic model for a shape the package both writes and reads
within one process. A Pydantic model over package-internal or emit-only data
is a review finding, not a stylistic preference.

**3. A boundary model is the authoritative schema for its shape.** Where a
boundary model exists, the writer, the shipped template under
`resources/templates/`, and the corresponding rule in `check/checks.py`
derive from it, **or are guarded against it in tests**. A model that merely
duplicates a schema still written longhand elsewhere has not paid for itself.
The "guarded in tests" arm exists precisely for the case where deriving the
writer from the model would drag an internal `dataclasses` object into
Pydantic in violation of point 2 — e.g. the acquire sidecar is built from
`candidate.as_json()` / `match.as_json()`, so what proves agreement is a
round-trip test asserting that what the writer emits validates against the
model, not a rewrite of the writer.

**4. A `ValidationError` never escapes the boundary.** It is caught in exactly
one module and converted to the calling module's existing, explicit failure
signal — a `Finding`, a non-zero exit, an error object in the JSON envelope —
carrying the field path and the reason. Never a bare traceback, never
swallowed into a default value. *Which* signal is a per-boundary choice: a
paginated OpenAlex page hard-fails as one unit, because a truncated frontier
silently returned as if complete is worse than failing the call outright;
while a best-effort Semantic Scholar citation-edge bundle skips the one bad
member and records the loss in the record's existing `degraded` list, because
that enrichment is already documented best-effort and a malformed edge must
not take down the whole call. Both are instances of the same rule — a
`ValidationError` becomes an explicit signal, not a default — applied to two
different existing failure vocabularies.

**5. Adoption is incremental and per-boundary.** Each slice lands with the
tests that cover it; there is no single migration commit. ADR-0028's 100%
statement + branch coverage gate is unchanged and applies in full to the new
validation and degradation branches, exactly as it already applies to
everything else in the package.

## Consequences

- `pydantic` becomes a pinned runtime dependency of the package. Its version
  range must publish wheels across the whole of the package's
  `requires-python = ">=3.11,<3.15"`; that becomes a release-time check
  (verified at design time: `pydantic-core` 2.48.0 ships `cp311`–`cp315`
  wheels), not a one-time decision — a future Python floor or ceiling change
  must re-check this.
- The scope-creep risk into a general model layer is bounded by point 2: a
  reviewer treats a Pydantic model over package-internal or emit-only data as
  a finding against this ADR, not as a matter of taste.
- `decisions/0029-api-key-handling.md`, `decisions/0031-config-driven-cache-dir.md`
  and `decisions/0038-venue-resolvers-trusted-not-gated.md` each carry a
  `> **Refined by ADR-0043.**` amendment blockquote; their decision text is
  unchanged, because none of the outcomes they recorded depended on the "no
  Pydantic" clause being correct, only on it being unexamined.
  `docs/design/proposals/dataset-manifest-tooling.md` similarly carries an
  amendment note; its shipped design is unaffected because the manifest's
  YAML boundary is a deliberate non-goal here (see Rejected alternatives and
  the companion design document for the deferred YAML phase).
- `CLAUDE.md`'s Code-style bullet states the scoped rule and cites this ADR in
  place of the blanket prohibition.
- This ADR records the decision only. The concrete adoption — `core/models.py`
  as the sole module importing `ValidationError`, and the fix for defects 1–6
  — is a separate, later phase of work, tracked against the same issue.

## Rejected alternatives

- **Keep the blanket rejection.** Preserves the lighter wheel — a real, if
  small, cost avoided — but preserves the four-way schema drift, the
  hand-rolled parsing at roughly twenty sites across nine modules, the six
  verified defects above, and three ADRs citing a rule that itself cites a
  document that was never written. The rule could not even be evaluated
  without first writing the ADR it lacked.
- **Pydantic everywhere, replacing `dataclasses`.** Buys nothing where strict
  mypy already holds the guarantee — internal value objects the package both
  constructs and consumes in-process are not where the six defects live —
  and costs a rewrite across roughly thirty modules. An architectural change
  in search of a problem, not debt repayment; rejected by point 2 of the
  Decision.
- **`jsonschema`.** Genuinely cheaper on the dependency axis: pure Python, no
  compiled wheel. Rejected because it validates *without parsing*: the
  payload stays an untyped `dict` after validation succeeds, call sites keep
  hand-unpacking it field by field, mypy learns nothing about its shape, and
  the four-way schema drift (writer / reader / template / `check` rule) is
  completely untouched — a schema document becomes a fifth place to keep in
  sync rather than removing one of the existing four.
- **`TypedDict` + hand-written validators.** Zero new dependencies, fully
  mypy-visible — the strongest case among the rejected options. Rejected as
  the status quo with a name: the "hand-written validators" *are* the
  hand-rolled per-boundary parsing this decision exists to stop
  re-implementing, just annotated. It does not produce a single shared
  `ValidationError` → domain-error seam (point 4), so each boundary keeps
  its own bespoke translation from "field missing or wrong type" to a
  failure signal.
- **`attrs` + `cattrs`.** Comparable ergonomics to Pydantic, pure Python, a
  genuinely close call. Rejected for a narrower ecosystem around JSON-shaped
  external input, and — the deciding factor — because Pydantic's structured
  error objects (field path + reason, per failing item) drop straight into
  the single failure-signal seam point 4 requires, where `cattrs` would need
  a hand-written translation layer from its own exception shape to that
  seam — the very kind of per-boundary translation code this decision exists
  to remove.

## Links

- `CLAUDE.md` (Conventions → Code style) — the prohibition this ADR replaces
- `decisions/0024-tooling-package-and-bootstrap.md`, `decisions/0026-independent-versioning-compat-pin.md`
  — the isolated-install architecture the "no Rust-binary conflicts" premise
  is checked against
- `decisions/0028-100-percent-coverage-gate.md` — the coverage gate applied
  unchanged to the new boundary code
- `decisions/0029-api-key-handling.md`, `decisions/0031-config-driven-cache-dir.md`,
  `decisions/0038-venue-resolvers-trusted-not-gated.md` — the three decisions
  that inherited the unexamined rule, each amended by this ADR
- `docs/design/proposals/dataset-manifest-tooling.md` — the manifest design
  amended by this ADR; its YAML boundary is deferred, not adopted, here
- `resources/ensure-tooling.md:56-59` — the isolated-install guarantee
- `docs/superpowers/specs/2026-08-29-pydantic-parsing-boundary-design.md` —
  the design record this ADR is drawn from, including the phase-2 adoption
  plan (`core/models.py`, the per-boundary slices, and the six defects' fixes)
