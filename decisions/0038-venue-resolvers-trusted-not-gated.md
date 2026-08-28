# ADR-0038: Rung 6 (`venue_resolvers`) is *trusted*, not gated — and says so

- Status: accepted · Date: 2026-08-27 · Deciders: Davor Runje

> **Refined by ADR-0043.** The "no Pydantic" clause in the light-dependency argument
> below is superseded by ADR-0043. The rest of this decision stands.

## Context

ADR-0037 established a three-way match gate (accept / quarantine / refuse) over
the acquisition ladder's search-derived rungs, on the principle that "a wrong
PDF one keystroke from a citekey is worse than no PDF." The design spec
(`docs/superpowers/specs/2026-08-27-literature-asset-acquisition-design.md`
§5.1) marks rung 6 — the consumer-configured `venue_resolvers` templates —
**gated: yes**, and the code complied: `RUNG_VENUE` was in `GATED_RUNGS`, so
every rung-6 candidate went through `evaluate_match`.

The gate was vacuous there, and worse than vacuous. `venue_candidates` builds
its candidate with `candidate_from_work(work, url, RUNG_VENUE)` — from the
**anchor work**, the same OpenAlex record the citekey already resolved to. So
`evaluate_match(entry, candidate)` compared the registry entry against metadata
derived from its own resolved work, never against whatever the consumer's
`url_template` actually points at. It could not do anything but pass.

The consequence was not a missing check but a **false record**. Rung 6
candidates landed in the audit trail as:

```json
"match": {"verdict": "accept", "title": "exact", "author": "exact", "year": "exact"}
```

A reader of that report — the whole point of `MatchRecord` being per-axis, per
ADR-0037, is that "a refusal is explainable" — sees three exact axes and
concludes the bytes were checked against the venue URL. Nothing was. The
`%PDF-` magic-byte test in `looks_like_pdf` was the only real constraint, and
it accepts *any* PDF, including the wrong paper's.

`venue_candidates`'s docstring already carried a `.. warning::` saying exactly
this, which is how #105 came to be filed. A warning in a docstring does not
reach the person reading a JSON report.

## Decision drivers

- **Failure honesty (repo-wide rule).** Never let an uncertain condition be
  reported as a legitimate result. A fabricated `accept` in an integrity tool's
  own audit trail is the sharpest possible version of that failure.
- **Never guess at a citation binding** (ADR-0037). Where we cannot verify, the
  record must say we did not verify — not stay silent, and not claim otherwise.
- **Domain-neutrality.** `venue_resolvers` exists precisely so ML-venue logic
  stays out of the plugin (ADR-0037); it is consumer config by construction, and
  the plugin has no way to know what a consumer's template resolves to.
- **Proportionate cost.** Rung 6 ships empty (`venue_resolvers: []`) and is
  entirely opt-in, so exposure is low; the remedy should be proportionate.

## Options considered

1. **Real verification.** Fetch the resolved URL and extract title / author /
   year from what it serves, then run `evaluate_match` against *that*.
2. **Document the posture only.** Leave the code as-is; record in an ADR that
   rung 6 is trusted-by-configuration.
3. **Report the truth: a `trusted` verdict.** Take rung 6 out of `GATED_RUNGS`
   and record a distinct verdict stating that the candidate was admitted on the
   operator's configuration and not verified.

## Decision

**Option 3**, with this ADR as the documentation option 2 asked for.

- `RUNG_VENUE` leaves `GATED_RUNGS`. The set now means what its name says.
- A new verdict, `TRUSTED`, sits alongside `IDENTITY` (ungated because identity
  was established by resolution) and `ACCEPT` (gated and passed). It carries a
  `reason` naming the situation: admitted on a consumer-configured venue
  resolver, not verified against the URL's own record, `%PDF-` is the only gate.
- No axis is populated, because no axis was compared. `title`, `author` and
  `year` stay `null` rather than reporting `exact`.

Option 1 was rejected as disproportionate: a rung-6 URL *is* the PDF, so
verifying it means extracting text from PDF bytes — a new capability, a new
dependency (the package deliberately stays light: `requests`, `pooch`, `pyyaml`,
no Pydantic), and an unreliable one. Venues that expose cheaper metadata at a
stable URL are the exception. Buying a weak check at that price, for an opt-in
rung that ships empty, is not worth it.

Option 2 was rejected on its own: it leaves the false `accept` in the report.
Documenting a known-misleading output is not the same as not emitting it.

## Consequences

- The audit trail distinguishes three provenances instead of conflating two:
  `identity` (the URL came from the anchor's own record), `trusted` (the
  operator vouched), `accept` (a gate compared and it passed).
- **Rung 6 no longer inherits `evaluate_match`'s thin-metadata refusal.** An
  entry missing title / year / first author used to have its rung-6 candidates
  refused. That refusal was about the *entry's* metadata and said nothing about
  the consumer's template, so it was incidental protection, not principled; it
  is gone. A consumer who configures a resolver gets it applied.
- The spec's §5.1 rung table ("gated: yes" for rung 6) is superseded here. The
  spec is left unedited as the historical design record, per how ADRs work in
  this repo.
- A consumer relying on `venue_resolvers` gets a report that tells them plainly
  that this rung is theirs to vouch for. That is the actual protection: an
  operator who knows the tool is not checking can check.

## Rejected alternatives

- **Fetch-and-parse PDF text to verify** (option 1) — cost and dependency weight
  out of proportion to an opt-in, empty-by-default rung. Revisit if
  `venue_resolvers` ever ships non-empty, which ADR-0037 forbids on
  domain-neutrality grounds.
- **Quarantine every rung-6 candidate.** Would force a human `confirm` on every
  venue-resolved PDF. Punishes the consumer for using a documented feature, and
  the human confirming has no more information than the template author had.
- **Drop rung 6 entirely.** The generic rungs cover the cases that motivated the
  feature (ADR-0037), but the escape hatch is cheap and the alternative for an
  exotic venue is hand-downloading every PDF.

## References

- #105 (the issue), #104 (the sibling landing-page recall fix in the same PR)
- ADR-0037 (`0037-literature-asset-acquisition.md`) — the gate this refines
- `defendable-science/defendable_science/literature/acquire.py` —
  `GATED_RUNGS`, `TRUSTED`, `_gate`, `venue_candidates`
- `docs/superpowers/specs/2026-08-27-literature-asset-acquisition-design.md`
  §5.1 — the superseded "gated: yes" rung table
