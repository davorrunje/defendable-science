# ADR-0025: Honest AI-use disclosure + citation as the growth mechanism

- Status: accepted · Date: 2026-07-18 · Deciders: Davor Runje

## Context

`defendable-science` should become widely used. The mission-aligned growth vector is
the honesty mission itself: research venues increasingly require an **AI-use
disclosure**, and a truthful, structured disclosure that names the protocol
followed both helps the author and points other researchers to the tool. This is
the publication-level analog of the commit-attribution trailer
(`resources/commit-attribution.md`).

## Decision drivers

- Growth that *serves* users, not spam — a disclosure they'd want anyway.
- Must be **honest**: the tool cannot certify honesty; a hollow "seal" would be
  hypocritical for an integrity tool (anti-Goodhart).
- Must be **automatic at the right moment** — a passive doc won't spread; the
  author shouldn't have to remember it.
- Must respect **agency**: proposed, author-owned, opt-in — never auto-inserted.

## Considered options

1. **Ship a truthful, provenance-backed AI-use disclosure + citation, and have
   `paper-synthesis` proactively PROPOSE them at finalize (opt-in, author-owned).**
2. Passive docs only (a template in the repo, no workflow step).
3. Auto-insert a disclosure/citation into the paper.
4. A "certified honest" badge/seal.

## Decision

Option 1. Add `DISCLOSURE.md` (disclosure template + how-to-cite + optional badge)
and `CITATION.cff`. `paper-synthesis`, after the publish `decision` is signed off,
**proactively proposes** an AI-use disclosure **generated from the actual
provenance/sign-off record** plus the citation — for the author to review, edit,
adopt, or decline. Citation is the GitHub repo now, transitioning to an arXiv
preprint then a published paper.

## Consequences

- A discovery vector aligned with the mission; every published paper that carries
  the disclosure exposes defendable-science to researchers and reviewers.
- The disclosure is evidence-based (from the record), so it is honest and not a
  hollow sticker.
- `paper-synthesis` gains a finalize-time proposal step; `DISCLOSURE.md` +
  `CITATION.cff` are maintained.

## Rejected alternatives

- **Passive docs only** — won't spread (no automatic step); the author forgets it.
- **Auto-insert** — violates agency; the author must author and own the statement.
- **"Certified honest" badge** — the tool can't certify honesty; a hollow seal is
  Goodhart-bait and hypocritical for an integrity tool.

## Links

`DISCLOSURE.md`; `CITATION.cff`; `skills/paper-synthesis/SKILL.md` (the proposal
step); `resources/commit-attribution.md` (the git-level analog); agency +
anti-Goodhart principles (meta-spec §2.1, §3.6).
