# Contributing to defendable-science

## Built with `superpowers` — but defendable-science does **not** require it

`defendable-science`'s own development uses the [`superpowers`](https://github.com/obra/superpowers)
engineering workflow (brainstorming → writing-plans → implementation). It is
enabled for maintainers in this repo's [`.claude/settings.json`](.claude/settings.json).

**This is a maintainer choice for building *this* plugin. Using `defendable-science` does not
require `superpowers`.** `defendable-science` names no engineering tool: its skills delegate
engineering through the **engineering-delegation contract**
([`resources/contracts/engineering.md`](resources/contracts/engineering.md)), and
each consuming repo binds whatever engineering backend it uses (or none) via
`.defendable-science/config.yml`. The build-vs-use line is deliberate (ADR-0023).

## Repo layout

- `skills/<name>/SKILL.md` — the plugin's skills (the primary deliverable).
- `resources/` — `contracts/` (experiment-backend, engineering), `substrate/`,
  `rigor/`, `templates/`, `references/` (verified-source digests).
- `docs/design/` — the specs (meta-spec + sub-specs) and `proposals/` (drafts).
- `decisions/` — MADR ADRs (one per decision, with rejected alternatives).
- `.claude-plugin/` — `plugin.json` + `marketplace.json`.

## Conventions

- **Issues & PRs via the local skills.** File follow-ups with the
  [`create-issue`](.claude/skills/create-issue/SKILL.md) skill (self-contained
  house format + the close standard) and land changes with the
  [`create-pr`](.claude/skills/create-pr/SKILL.md) skill (branch → checks →
  attributed commit → PR). The two are a matched pair (`Closes #NN` ⇄ the close
  standard).
- **Record decisions as ADRs.** Any material design decision gets a MADR entry in
  `decisions/` (context · drivers · options · decision · consequences · rejected
  alternatives), linked from `decisions/README.md`.
- **Ground claims.** Methodology decisions cite `resources/references/` digests.
- **Commit attribution.** Commits of skill-produced artifacts carry the discovery
  trailers in [`resources/commit-attribution.md`](resources/commit-attribution.md).
- **Validate before publishing:** `claude plugin validate .`
- **Test-install locally:** `/plugin marketplace add ./` then
  `/plugin install defendable-science@defendable-science`.

## Releasing

Cutting a release of the **PyPI package** (Bump version → merge → Publish to
TestPyPI/PyPI via Trusted Publishing) is documented in
[`RELEASING.md`](RELEASING.md). The package is versioned independently of the
plugin.

## Domain-neutrality

`defendable-science` must stay domain-neutral: no ML-, monotonic-network-, or repo-specific
assumptions in the plugin. Consumer-specific details (anchors, datasets, backends)
live in the consuming repo's config/content, never here.
