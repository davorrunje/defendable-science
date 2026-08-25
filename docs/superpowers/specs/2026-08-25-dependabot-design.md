# Automated dependency updates: Dependabot + pre-commit autoupdate

**Status:** approved, ready to plan
**Date:** 2026-08-25

Automate the dependency maintenance currently done by hand (PR #78 bumped six
tool pins and 21 locked versions manually). Two deliverables:

1. `.github/dependabot.yml` — weekly version updates for the package's **dev and
   lint toolchain** (`uv`) and for **GitHub Actions**.
2. `.github/workflows/pre-commit-autoupdate.yml` — the counterpart for
   `.pre-commit-config.yaml` hook `rev:` pins, which Dependabot cannot reach
   (there is no `pre-commit` ecosystem).

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
    open-pull-requests-limit: 5
    commit-message:
      prefix: "ci(deps)"
    labels: ["dependencies"]
    groups:
      actions:
        applies-to: version-updates
        patterns: ["*"]
        update-types: ["minor", "patch"]
```

### Why each knob

- **`allow: dependency-type: "development"`** — the mechanism that protects the
  runtime floors. Documented as supported for `uv`.
- **`cooldown: default-days: 7`** — skips releases younger than a week, so
  day-0 releases that get yanked, or a freshly compromised version, are not
  reviewed on the day they land. Per GitHub's options reference `cooldown` is
  **not** supported for `github-actions`, so the Actions entry has no freshness
  delay.
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

## `.github/workflows/pre-commit-autoupdate.yml`

Covers the four remote hook repos — `pre-commit/pre-commit-hooks` (v6.0.0),
`asottile/pyupgrade` (v3.21.2), `codespell-project/codespell` (v2.4.2),
`Yelp/detect-secrets` (v1.5.0). The three local hooks (`lint`, `typecheck`,
`plugin-validate`) are `tools/*.sh` and have no revs.

```yaml
on:
  workflow_dispatch:
  schedule:
    - cron: "0 8 * * 1"        # Mondays 08:00 UTC — one hour after Dependabot

permissions:
  contents: write
  pull-requests: write

jobs:
  autoupdate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v8.3.1
      - run: uv sync --project defendable-science --group lint
      - id: update
        run: |
          uv run --project defendable-science pre-commit autoupdate \
            | tee /tmp/autoupdate.log
          # changed=true|false from `git diff --quiet -- .pre-commit-config.yaml`
      - id: hooks
        if: steps.update.outputs.changed == 'true'
        continue-on-error: true
        run: uv run --project defendable-science pre-commit run --all-files
      - if: steps.update.outputs.changed == 'true'
        uses: peter-evans/create-pull-request@v7
        with:
          token: ${{ secrets.RELEASE_PAT || github.token }}
          branch: build/pre-commit-autoupdate
          base: main
          title: "build(deps): pre-commit hook autoupdate"
          author: Davor Runje <davor@synthpop.ai>
          committer: Davor Runje <davor@synthpop.ai>
          labels: dependencies
```

### Why each decision

- **Mirrors `bump-version.yml`.** Same `peter-evans/create-pull-request@v7`,
  same `RELEASE_PAT || github.token` fallback, same author/committer identity,
  and the same caveat in the PR body: created with the default token, the PR
  gets no CI checks and needs a re-run or an admin merge.
- **Hooks run after the bump, in the same job.** `pyupgrade` and the whitespace
  hooks rewrite files; running them here puts the autofixes in the same PR
  instead of handing over a red PR to fix by hand.
- **`continue-on-error` on the hook step, never on the PR step.** A hook that
  fails un-autofixably still yields a PR, with the failure quoted in the body
  and CI red on top of it. Letting the job die instead would produce a silent
  no-op week indistinguishable from "nothing to update" — the exact
  failure-vs-legitimately-empty confusion `CLAUDE.md` forbids.
- **No PR on quiet weeks**, and a fixed branch name so an unreviewed PR is
  updated in place rather than duplicated.
- **`pre-commit` comes from the pinned `lint` group**, so the autoupdate is
  performed by the same `pre-commit==4.6.2` CI enforces.
- **Runs an hour after Dependabot** so the two streams don't interleave on the
  same Monday morning.

## Known duplication (deliberately not fixed here)

`codespell` and `detect-secrets` are each pinned twice — a hook `rev:` and a
`lint` group `==` — and after this change two independent automations bump them.
They are already drifted (hook `v2.4.2` vs. pin `2.4.3`).

Not fixed here: the durable fix is to delete the duplication (convert both to
local hooks driven by the `lint` pins, as `lint`/`typecheck`/`plugin-validate`
already are), which is a separate change from adding automation. A guard script
would instead be machinery to police a duplication that should not exist. This
ships as a **self-contained follow-up issue**, per the `create-issue` house
standard.

## Acceptance criteria

Config correctness is observed on a forced first run — the Dependabot tab's
*Check for updates* button and one `workflow_dispatch` — not waited for.

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
- [ ] Autoupdate dispatched once opens a PR bumping the `codespell` rev off
      `v2.4.2`; dispatched again after that merges, it opens **no** PR.
- [ ] A follow-up issue exists for the twice-pinned tools.

## Unknowns and fallbacks

Two behaviours could not be confirmed from GitHub's documentation and are
therefore checks, not assumptions:

1. **Does an ungrouped major reliably get its own PR** when the groups restrict
   `update-types` to minor/patch? Acceptance criterion 6 verifies it. If not, add
   an explicit third group with `update-types: ["major"]`.
2. **Does Dependabot's `uv` support classify PEP 735 `dependency-groups` as
   `development`** for the `allow` filter? If it does not, the symptom is **zero
   PRs** on the first forced check. Zero PRs means *investigate*, never *success*.
   Fallback: drop the `allow` filter and instead `ignore` the four runtime
   dependencies by name — accepting that `ignore` also suppresses their security
   updates, which is why it is the fallback and not the primary.

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
