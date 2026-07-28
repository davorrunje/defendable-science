# ADR-0035: Rename the project from Honest Scholar to Defendable Science

- Status: accepted · Date: 2026-07-28 · Deciders: Davor Runje

## Context

The project shipped `v0.1.0` (2026-07-19) and `v0.1.1` (2026-07-21) as
`honest-scholar`: a GitHub repo, a Claude Code plugin, a PyPI distribution, a
CLI, and a docs site at `honest-scholar.science`.

The name leads with *honesty* — a property of the researcher. The methodology
leads with *defensibility* — a property of the work, and the thing the tool can
actually verify. Every load-bearing mechanism is about defence: the
exploration→resolution firewall (no skill both proposes a claim and adjudicates
it), `defend` as a Socratic tutor-examiner, `digest` as its inbound counterpart,
named human sign-off on every material decision. The tagline was already
"research you can defend". A new visual identity built on the QED tombstone (∎,
"demonstrated") made the mismatch plain.

`honest-scholar` also overstates what the tool does. It cannot certify that
research is honest — `DISCLOSURE.md` says so explicitly — and a name that
implies otherwise is exactly the kind of unearned claim the project's own voice
rules reject.

## Decision drivers

- The name should describe what the tool verifies, not a virtue it cannot audit.
- Alignment with the new visual identity and the QED mark, already authored.
- Cost of renaming rises monotonically with adoption; nine days after first
  release it is near its lifetime minimum.
- Two artifacts version independently (ADR-0026), so the rename must not couple
  them.

## Considered options

1. **Rename everything to `defendable-science`**, drop the old PyPI
   distributions with no forwarding release. *(chosen)*
2. **Keep `honest-scholar`.** Zero cost, permanent mismatch between the name,
   the identity, and the methodology.
3. **Dual-name**: rename the project, keep the distribution and CLI as
   `honest-scholar`. Avoids breaking installs, but leaves the most-typed
   identifier contradicting everything around it, and doubles the vocabulary a
   new contributor must learn.
4. **Rename with a forwarding release**: publish a final `honest-scholar`
   version whose only content is a deprecation notice depending on
   `defendable-science`. Kinder to existing installs, but the population is
   very likely zero and the shim would outlive its usefulness on PyPI forever.

## Decision

Option 1. The full naming map is recorded in
`docs/superpowers/specs/2026-07-28-defendable-science-rename-design.md`. In
summary: repo, plugin, marketplace, PyPI + TestPyPI distribution, console
script (`defendable-science`, short alias `dsci`, replacing `hsch`), Python
module (`defendable_science`), project config dir (`.defendable-science/`),
environment variables (`DEFENDABLE_SCIENCE_*`), commit trailer
(`DefendableScience-Skill:`), and the docs home at `defendable.science`.

Both artifacts move to `0.2.0` — a breaking change under `0.x`. The alignment is
coincidental; they continue to version independently.

The word *honest* is retained as vocabulary. "Failure honesty", "honest stop",
"an honest ledger", and the `honest AI use` citation keyword are precise
technical terms and are unaffected.

## Consequences

- **The old PyPI and TestPyPI distributions are abandoned with no forwarding
  release.** Anyone who ran `uv tool install honest-scholar` is stranded at
  `0.1.1` with no in-band signal that the project moved. Mitigated only by this
  ADR, the CHANGELOG, and GitHub's repo redirect.
- **Existing consumer repos break** and must be migrated by hand:
  1. `git mv .honest-scholar .defendable-science`
  2. rename `HONEST_SCHOLAR_KEYS_PATH` → `DEFENDABLE_SCIENCE_KEYS_PATH` and
     `HONEST_SCHOLAR_LIVE` → `DEFENDABLE_SCIENCE_LIVE` wherever they are set
  3. update `.gitignore` entries pointing at `.honest-scholar/`
  4. reinstall the plugin:
     `/plugin install defendable-science@defendable-science`
  5. reinstall the CLI: `uv tool uninstall honest-scholar`, then
     `uv tool install defendable-science`
- **ADRs 0001–0034 were rewritten to the new name**, trading some historical
  fidelity for a repo that reads as one coherent artifact. This ADR is the
  single place that records the former name.
- **The `0.1.0` and `0.1.1` CHANGELOG entries keep the old name verbatim.**
  Those releases really did ship under it; rewriting them would be the kind of
  tidy lie the failure-honesty rule exists to prevent.
- **Two names had to be secured before the work could proceed**, and neither was
  held when the rename was designed: the `defendable-science` distribution on
  PyPI/TestPyPI, and the `defendable.science` domain — which appeared registered
  in a registrar panel but was absent from the registry (RDAP 404) and had to be
  re-registered. A registrar panel is not evidence of registration; RDAP is.

## Rejected alternatives

See *Considered options* 2–4 above. Option 4 was the closest call: it is
strictly kinder to existing users, and was rejected only because the user
population nine days after first release is very likely zero, and a permanent
deprecation shim on PyPI is a lasting cost to avoid a transient one.

## Links

`docs/superpowers/specs/2026-07-28-defendable-science-rename-design.md` (the
full naming map this ADR defers to);
`docs/superpowers/plans/2026-07-28-defendable-science-rename.md` (the
implementation plan); `resources/ensure-tooling.md` (carries the
compatibility pin this rename bumped); `docs/design/visual-identity.md` (the
v2 identity, built on the QED mark, that motivated the rename);
`CHANGELOG.md` (the retained `0.1.0`/`0.1.1` entries, which keep the old name
verbatim); ADR-0026 (independent versioning of the two artifacts — this
rename's `0.2.0` alignment is coincidental); ADR-0030 (the docs site, whose
domain moved from `honest-scholar.science` to `defendable.science`).
