# Automated dependency updates: Dependabot for uv, GitHub Actions, and pre-commit

**Status:** approved, ready to plan
**Amended 2026-08-25:** the original design used a bespoke
`.github/workflows/pre-commit-autoupdate.yml` workflow for hook `rev:` pins,
on the premise that Dependabot lacks a `pre-commit` ecosystem. That premise
was false — see the "Dependabot `pre-commit` ecosystem" section below, which
replaces it.
**Date:** 2026-08-25

Automate the dependency maintenance currently done by hand (PR #78 bumped six
tool pins and 21 locked versions manually). One deliverable:

`.github/dependabot.yml` — weekly version updates for the package's **dev and
lint toolchain** (`uv`), for **GitHub Actions**, and for the **pre-commit**
hook `rev:` pins in `.pre-commit-config.yaml`.

No existing workflow changes. No source changes. Nothing here touches either
artifact's version, so no release is implied (see `RELEASING.md`).

## Scope

| In scope | Out of scope |
|---|---|
| `uv` dev/lint pins in `defendable-science/pyproject.toml` + `uv.lock` | `[project.dependencies]` runtime floors |
| Action refs in `.github/workflows/**` and `.github/actions/**` | The two unversionable `@release/v1` branch refs |
| The four remote hook `rev:` pins in `.pre-commit-config.yaml` | De-duplicating the twice-pinned tools (follow-up issue) |
| | Auto-merge of any kind |

**Runtime floors stay as authored.** `typer>=0.12`, `requests>=2.31`,
`pyyaml>=6.0`, `pooch>=1.8` are deliberately wide so the package can be
installed beside a consumer's own pins. Raising them would narrow that surface
for no benefit, so Dependabot is scoped away from them entirely.

**No auto-merge.** `main` is protected, merging is the maintainer's action, and
the agency principle (`docs/design/00-meta-spec.md`) says the human signs
material decisions. A green tool bump is still a decision.

## `.github/dependabot.yml`

```yaml
version: 2

updates:
  # ── Python — the package's dev/lint toolchain ────────────────────────────
  - package-ecosystem: "uv"
    directory: "/defendable-science"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "07:00"
      timezone: "Etc/UTC"
    # [project.dependencies] are deliberately wide floors (typer>=0.12, …) so
    # consumers can co-install; only the dev/lint groups' == pins may move.
    allow:
      - dependency-type: "development"
    cooldown:
      default-days: 7
    open-pull-requests-limit: 5
    commit-message:
      prefix: "build(deps)"
    labels: ["dependencies"]
    groups:
      # Order matters — a dependency joins the FIRST group it matches.
      python-linters:
        applies-to: version-updates
        patterns: ["ruff", "mypy"]
        update-types: ["minor", "patch"]
      python-tooling:
        applies-to: version-updates
        patterns: ["*"]
        update-types: ["minor", "patch"]

  # ── GitHub Actions ──────────────────────────────────────────────────────
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "07:00"
      timezone: "Etc/UTC"
    cooldown:
      default-days: 7
    open-pull-requests-limit: 5
    commit-message:
      prefix: "ci(deps)"
    labels: ["dependencies"]
    groups:
      actions:
        applies-to: version-updates
        patterns: ["*"]
        update-types: ["minor", "patch"]

  # ── pre-commit hooks — keeps `rev:` pins in .pre-commit-config.yaml current
  - package-ecosystem: "pre-commit"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "07:00"
      timezone: "Etc/UTC"
    cooldown:
      default-days: 7
    open-pull-requests-limit: 5
    commit-message:
      prefix: "build(deps)"
    labels: ["dependencies"]
    groups:
      hooks:
        applies-to: version-updates
        patterns: ["*"]
        update-types: ["minor", "patch"]
```

### Why each knob

- **`allow: dependency-type: "development"`** — the mechanism that protects the
  runtime floors. Documented as supported for `uv`.
- **`cooldown: default-days: 7`** — skips releases younger than a week, so
  day-0 releases that get yanked, or a freshly compromised version, are not
  reviewed on the day they land. Per GitHub's options reference,
  `cooldown.default-days` **is** supported for `github-actions` (and for
  `pre-commit`); only the `semver-major-days` / `semver-minor-days` /
  `semver-patch-days` sub-options are unsupported there, because those need a
  version-based ecosystem to classify a release as major/minor/patch, which
  `github-actions` refs don't have. All three entries carry the same 7-day
  `default-days` cooldown.
- **Two Python groups, linters first.** Grouping minors and patches while
  leaving majors ungrouped splits by risk, but plain semver misplaces the risk
  for this toolchain: `ruff` is 0.x and `mypy` majors move fast, so the *minor*
  bump is the breaking one (ruff 0.15.21 → 0.16.4 in PR #78 was the riskiest
  change in that batch). Pulling `ruff` and `mypy` into their own group means a
  formatter or type-checker change — the kind that rewrites files or surfaces
  new errors repo-wide — is always reviewable on its own. Costs at most one
  extra PR per week.
- **Commit prefixes `build(deps)` / `ci(deps)`** so squash-merged subjects keep
  the Conventional-Commits shape the history already uses.
- **`labels: ["dependencies"]`** — Dependabot only applies labels that already
  exist, so rollout creates it first.
- **`package-ecosystem: "pre-commit"`** — bumps the `rev:` pins in
  `.pre-commit-config.yaml` directly. Grouped and prefixed the same way as
  `uv` (`build(deps)`) since both land in the package's toolchain surface.

### Expected first-run behaviour

`mypy` is pinned **twice** (`dev` and `lint`, both `2.3.1`, deliberately — the
`dev` copy keeps `--only-group dev` able to run the CLI). A bump must rewrite
both occurrences in one PR, or the two groups drift apart inside
`pyproject.toml`. This is an acceptance check, not an assumption.

Actions currently pin `actions/checkout@v7`, `actions/setup-python@v6`,
`actions/cache@v6`, `actions/setup-node@v4`, `actions/upload-artifact@v4`,
`actions/download-artifact@v4`, `codecov/codecov-action@v5`,
`lycheeverse/lychee-action@v2`, `peter-evans/create-pull-request@v7` (major tags)
and `astral-sh/setup-uv@v8.3.1` (exact). Only the exact pin can move on a
minor/patch; the major tags move only when a new major ships, as its own PR.
`pypa/gh-action-pypi-publish@release/v1` and `re-actors/alls-green@release/v1`
are branch refs and will never be updated — their absence from PRs is expected.

## Dependabot `pre-commit` ecosystem

`package-ecosystem: "pre-commit"` exists and is documented in GitHub's
`dependabot-options-reference`. It covers the four remote hook repos —
`pre-commit/pre-commit-hooks` (v6.0.0), `asottile/pyupgrade` (v3.21.2),
`codespell-project/codespell` (v2.4.3), `Yelp/detect-secrets` (v1.5.0) — by
rewriting the `rev:` pin in `.pre-commit-config.yaml` directly, the same way
the `uv` entry rewrites `pyproject.toml`. The three local hooks (`lint`,
`typecheck`, `plugin-validate`) are `tools/*.sh` and have no revs, so they are
outside every ecosystem's reach.

No bespoke workflow, no `contents: write` permission, and no
`peter-evans/create-pull-request` step are needed — Dependabot opens the PR
itself, exactly as it does for `uv` and `github-actions`.

### Why this replaces the earlier workflow design

The original design in this document proposed
`.github/workflows/pre-commit-autoupdate.yml`: a scheduled job running
`pre-commit autoupdate` and then the updated hooks, on the (false) premise
that Dependabot lacks a `pre-commit` ecosystem. A whole-branch review, checked
against GitHub's own reference docs, found that premise wrong, plus one
correctness bug the workflow would have shipped with: its piped `run` steps
had no `shell: bash`, so `pipefail` was never active and a hook failure would
have exited 0 — silently defeating the `continue-on-error`/failure-quoting
design meant to keep failures visible.

The workflow's one genuine advantage — running the updated hooks in the same
job so `pyupgrade`/whitespace autofixes land in the same PR as the rev bump —
is real and the `pre-commit` ecosystem cannot replicate it (Dependabot
rewrites the `rev:` pin; it does not run the hooks). That trade-off is
accepted: a red PR from a stale hook fixing itself. See ADR-0036's Rejected
alternatives for the full comparison.

## Known duplication (deliberately not fixed here)

`codespell` and `detect-secrets` are each pinned twice — a hook `rev:` and a
`lint` group `==` — and after this change two independent Dependabot
ecosystems (`uv` and `pre-commit`) bump them. The two locations currently
agree (`codespell` at `2.4.3`, `detect-secrets` at `1.5.0` in both places):
they had drifted before PR #78 reconciled them. The duplication itself is
unchanged, and with two independent weekly ecosystems now bumping each tool,
drift recurs whenever they bump on different weeks.

Not fixed here: the durable fix is to delete the duplication (convert both to
local hooks driven by the `lint` pins, as `lint`/`typecheck`/`plugin-validate`
already are), which is a separate change from adding automation. A guard script
would instead be machinery to police a duplication that should not exist. This
ships as a **self-contained follow-up issue**, per the `create-issue` house
standard.

## Acceptance criteria

Config correctness is observed on a forced first run — the Dependabot tab's
*Check for updates* button on each of the three entries — not waited for.

- [ ] `dependabot.yml` parses with no error in the repo's Dependabot tab.
- [ ] The `dependencies` label exists before the config lands.
- [ ] A `uv` PR modifies only dev/lint pins and `uv.lock`; `[project.dependencies]`
      is untouched.
- [ ] A `mypy` bump rewrites **both** the `dev` and `lint` occurrences in one PR.
- [ ] `ruff`/`mypy` arrive in a PR separate from `pytest*`/`types-*`/`codespell`.
- [ ] A major bump arrives as its own PR (see Unknowns).
- [ ] No PR for a release younger than 7 days.
- [ ] PRs carry the `dependencies` label and a `build(deps)`/`ci(deps)` subject,
      and CI runs on them.
- [ ] No PRs for the two `@release/v1` branch refs.
- [ ] The `pre-commit` ecosystem opens a PR if any of the four remote hook
      revs is stale, and legitimately opens none if all four are already
      current; in the latter case the criterion is met by the Dependabot tab
      explicitly showing "up to date" for that ecosystem, not by silence.
- [ ] A follow-up issue exists for the twice-pinned tools (issue #79).

## Unknowns and fallbacks

Two behaviours could not be confirmed from GitHub's documentation and are
therefore checks, not assumptions:

1. **Does an ungrouped major reliably get its own PR** when the groups restrict
   `update-types` to minor/patch? Acceptance criterion 6 verifies it. If not, add
   an explicit third group with `update-types: ["major"]`.

   **Settled by the first real run.** Dependabot parsed the config and opened
   five `github-actions` PRs (#81, #83, #84, #85, #86), each a major bump
   arriving alone, exactly as the ungrouped-major design intended. Confirmed;
   no fallback needed.

2. **Does Dependabot's `uv` support classify PEP 735 `dependency-groups` as
   `development`** for the `allow` filter? If it does not, the symptom is **zero
   PRs** on the first forced check. Zero PRs means *investigate*, never *success*.
   Fallback: drop the `allow` filter and instead `ignore` the four runtime
   dependencies by name — accepting that `ignore` also suppresses their security
   updates, which is why it is the fallback and not the primary.

   **Not settled by the first real run.** The first run opened zero `uv` PRs —
   the symptom this unknown flagged as needing investigation, not assumed
   success. Investigation found a legitimate explanation unrelated to the
   `allow` filter: all ten dev/lint pins were already at their latest PyPI
   release (verified by hand against PyPI at the time). Zero PRs is therefore
   the correct, non-silent outcome for this run, but it does *not* exercise
   the `allow: dependency-type: "development"` classification of PEP 735
   `dependency-groups` — that remains open until a pin actually goes stale and
   either produces a PR (settled) or stays silent past its normal cadence
   (regression, investigate the `allow` filter first).

## Does this need an ADR?

Recommended: **yes, a short one.** This sets a maintenance *policy*, not just a
config — dev-only scope, no auto-merge, a 7-day cooldown, risk-split grouping —
and the repo already records comparable process decisions as ADRs (ADR-0026
plugin↔package version pinning, ADR-0028 the coverage gate). The rejected
alternatives are worth preserving: auto-merge, floor-raising, per-dependency PRs,
and a scheduled `uv lock --upgrade` workflow instead of Dependabot. Decide before
implementation; if adopted, the ADR lands in the same PR and is appended to
`decisions/README.md`.

## Accepted deviations from house convention

Dependabot's PRs use `dependabot/*` branch names and carry no `Co-Authored-By`
attribution. The `create-pr` conventions (`<area>/<slug>` branches, authored
commits with trailers) govern human PRs; bot PRs are exempt.
