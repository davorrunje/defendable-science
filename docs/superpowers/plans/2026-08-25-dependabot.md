# Automated Dependency Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate the dependency maintenance done by hand in PR #78 — weekly Dependabot PRs for the package's dev/lint toolchain and for GitHub Actions, plus a scheduled workflow for the `pre-commit` hook revs Dependabot cannot reach.

**Architecture:** Two declarative files and one ADR. `.github/dependabot.yml` scopes `uv` updates to development dependencies (protecting the deliberately wide runtime floors), groups minors/patches with `ruff`+`mypy` split into their own group, and leaves majors ungrouped so they arrive alone. `.github/workflows/pre-commit-autoupdate.yml` mirrors `bump-version.yml`'s existing create-pull-request pattern. Nothing auto-merges; every PR goes through the normal protected-`main` review.

**Tech Stack:** GitHub Dependabot (`uv` + `github-actions` ecosystems), GitHub Actions, `peter-evans/create-pull-request@v7`, `pre-commit`, `uv`.

**Spec:** [`docs/superpowers/specs/2026-08-25-dependabot-design.md`](../specs/2026-08-25-dependabot-design.md) — approved. Read it before starting; it records the *why* for every knob below.

## Global Constraints

- **Never commit to `main`.** Work continues on the existing branch `build/dependabot-config`, which already carries the spec commit `a27423f`. Open a PR; do not merge it.
- **Commit attribution:** author `Davor Runje <davor@synthpop.ai>`, `--no-gpg-sign`, and a `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` trailer. Conventional-Commits subjects (`build(deps)`, `ci`, `docs`).
- **These four runtime dependencies must never appear in `dependabot.yml` and must never be edited by it:** `typer>=0.12`, `requests>=2.31`, `pyyaml>=6.0`, `pooch>=1.8` (in `defendable-science/pyproject.toml` `[project.dependencies]`).
- **No auto-merge anywhere.** No `gh pr merge --auto`, no auto-approve workflow, no `dependabot.yml` merge directives.
- **Exact schedule values:** Dependabot `weekly` / `monday` / `07:00` / `Etc/UTC`; autoupdate workflow cron `0 8 * * 1`.
- **Exact cooldown:** `default-days: 7`, on the `uv` entry only — `cooldown` is not supported for `github-actions`.
- **Commit-message prefixes:** `build(deps)` for the `uv` entry, `ci(deps)` for the `github-actions` entry.
- **Group order is load-bearing:** `python-linters` (patterns `["ruff", "mypy"]`) must precede `python-tooling` (patterns `["*"]`); a dependency joins the first group it matches.
- **Every group restricts `update-types` to `["minor", "patch"]`** so majors stay ungrouped and arrive as their own PR.
- Repo checks that must pass before the PR: `pre-commit run --all-files` and `./tools/validate-plugin.sh` from the repo root. No package source changes, so the `pytest`/coverage gate is unaffected — run it anyway if `defendable-science/` is touched.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `.github/dependabot.yml` | create | The only Dependabot configuration. Two update entries: `uv` at `/defendable-science`, `github-actions` at `/`. |
| `.github/workflows/pre-commit-autoupdate.yml` | create | Scheduled + dispatchable `pre-commit autoupdate` → PR. Covers the hook `rev:` pins Dependabot cannot see. |
| `decisions/0036-automated-dependency-updates.md` | create | MADR record of the *policy* (scope, no auto-merge, cooldown, risk-split grouping) and its rejected alternatives. |
| `decisions/README.md` | modify (append one row) | The ADR index. |
| GitHub label `dependencies` | create (via `gh`) | Dependabot only applies labels that already exist. |
| GitHub issue | create (via `gh`) | Follow-up: the twice-pinned `codespell`/`detect-secrets`. |

Deliberately unchanged: every existing workflow, `.pre-commit-config.yaml`, and all package source.

---

### Task 1: The `dependencies` label and `.github/dependabot.yml`

The label comes first: Dependabot silently skips labels that don't exist, so creating it after the config would leave the first batch of PRs unlabeled.

**Files:**
- Create: `.github/dependabot.yml`
- Test: `/tmp/check_dependabot.py` (a throwaway assertion script — do **not** commit it)

**Interfaces:**
- Consumes: nothing.
- Produces: the file `.github/dependabot.yml`; the group names `python-linters`, `python-tooling`, `actions`, referenced by Task 3's ADR and Task 6's verification.

- [ ] **Step 1: Create the label (idempotent)**

```bash
gh label create dependencies \
  --description "Dependency updates (Dependabot + pre-commit autoupdate)" \
  --color ededed || gh label list --search dependencies
```

Expected: either `✓ Label "dependencies" created` or, if it already exists, the
`gh label list` fallback prints the existing row. Both are success.

- [ ] **Step 2: Write the failing check**

This is the test for a config file: it asserts the spec's mechanical
requirements. Write it to `/tmp/check_dependabot.py`:

```python
import sys, yaml

cfg = yaml.safe_load(open(".github/dependabot.yml"))
assert cfg["version"] == 2, cfg["version"]
entries = {e["package-ecosystem"]: e for e in cfg["updates"]}
assert set(entries) == {"uv", "github-actions"}, sorted(entries)

uv = entries["uv"]
assert uv["directory"] == "/defendable-science", uv["directory"]
assert uv["allow"] == [{"dependency-type": "development"}], uv["allow"]
assert uv["cooldown"] == {"default-days": 7}, uv["cooldown"]
assert uv["commit-message"]["prefix"] == "build(deps)"
assert uv["labels"] == ["dependencies"]
assert uv["schedule"] == {
    "interval": "weekly", "day": "monday",
    "time": "07:00", "timezone": "Etc/UTC",
}, uv["schedule"]
# Group order is load-bearing: linters must be matched before the catch-all.
assert list(uv["groups"]) == ["python-linters", "python-tooling"], list(uv["groups"])
assert uv["groups"]["python-linters"]["patterns"] == ["ruff", "mypy"]
assert uv["groups"]["python-tooling"]["patterns"] == ["*"]

gha = entries["github-actions"]
assert gha["directory"] == "/", gha["directory"]
assert gha["commit-message"]["prefix"] == "ci(deps)"
assert "cooldown" not in gha, "cooldown is unsupported for github-actions"
assert list(gha["groups"]) == ["actions"], list(gha["groups"])

# Majors must stay ungrouped so they arrive as their own PR.
for entry in (uv, gha):
    for name, group in entry["groups"].items():
        assert group["update-types"] == ["minor", "patch"], (name, group)
        assert group["applies-to"] == "version-updates", (name, group)

# The runtime floors must never be NAMED in the config. Dependency names appear
# only as quoted values (patterns/ignore), so match those — a bare substring
# search false-positives on the key `open-pull-requests-limit`.
import re
quoted = set(re.findall(r'"([A-Za-z0-9_.-]+)"', open(".github/dependabot.yml").read()))
for dep in ("typer", "requests", "pyyaml", "pooch"):
    assert dep not in quoted, f"runtime dependency {dep!r} must not be named"
assert "ignore" not in uv, "the floors are protected by `allow`, not by `ignore`"

print("dependabot.yml: all assertions pass")
```

- [ ] **Step 3: Run it to confirm it fails**

```bash
uv run --project defendable-science python /tmp/check_dependabot.py
```

Expected: `FileNotFoundError: [Errno 2] No such file or directory: '.github/dependabot.yml'`

- [ ] **Step 4: Write the config**

Create `.github/dependabot.yml` with exactly this content:

```yaml
version: 2

# Automated dependency updates (ADR-0036). Scope, grouping and cadence rationale:
# docs/superpowers/specs/2026-08-25-dependabot-design.md
updates:
  # ── Python — the package's dev/lint toolchain ────────────────────────────
  - package-ecosystem: "uv"
    directory: "/defendable-science"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "07:00"
      timezone: "Etc/UTC"
    # [project.dependencies] are deliberately wide floors so consumers can
    # co-install; only the dev/lint groups' == pins may move.
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
      # ruff is 0.x and mypy majors move fast, so their *minor* bumps are the
      # breaking ones; they get a PR of their own.
      python-linters:
        applies-to: version-updates
        patterns: ["ruff", "mypy"]
        update-types: ["minor", "patch"]
      python-tooling:
        applies-to: version-updates
        patterns: ["*"]
        update-types: ["minor", "patch"]

  # ── GitHub Actions ──────────────────────────────────────────────────────
  # No cooldown: unsupported for this ecosystem.
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

- [ ] **Step 5: Run the check again**

```bash
uv run --project defendable-science python /tmp/check_dependabot.py
```

Expected: `dependabot.yml: all assertions pass`

- [ ] **Step 6: Run the repo hooks**

```bash
uvx pre-commit run --all-files
```

Expected: every hook `Passed` (`check-yaml` is the one that matters here).

- [ ] **Step 7: Commit**

```bash
git add .github/dependabot.yml
git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" \
  commit --no-gpg-sign -m "$(cat <<'EOF'
ci: add Dependabot config for the uv toolchain and Actions

Weekly version updates for the package's dev/lint pins (uv, scoped to
development dependencies so the wide runtime floors stay as authored) and for
GitHub Actions. Minors/patches are grouped, with ruff+mypy split into their own
group because their minor bumps carry the breaking changes; majors stay
ungrouped so they arrive one PR at a time. 7-day cooldown on the Python side
(unsupported for Actions). Nothing auto-merges.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `.github/workflows/pre-commit-autoupdate.yml`

**Files:**
- Create: `.github/workflows/pre-commit-autoupdate.yml`
- Reference (do not modify): `.github/workflows/bump-version.yml` — the create-pull-request pattern this mirrors.

**Interfaces:**
- Consumes: the `dependencies` label from Task 1; the `lint` dependency group's pinned `pre-commit==4.6.2`.
- Produces: workflow name `pre-commit autoupdate` (used verbatim by Task 6's `gh workflow run`), PR branch `build/pre-commit-autoupdate`.

**Note on verification:** `workflow_dispatch` only works once the file is on the
default branch, so this task's runtime proof happens in Task 6 after the PR
merges. Local verification here is limited to YAML validity and the assertions
below — say so plainly rather than implying the workflow was exercised.

- [ ] **Step 1: Write the failing check**

Write `/tmp/check_autoupdate.py`:

```python
import yaml

path = ".github/workflows/pre-commit-autoupdate.yml"
wf = yaml.safe_load(open(path))
# PyYAML resolves the `on:` key to the boolean True (YAML 1.1); GitHub does not.
triggers = wf[True]
assert "workflow_dispatch" in triggers, triggers
assert triggers["schedule"] == [{"cron": "0 8 * * 1"}], triggers["schedule"]
assert wf["permissions"] == {"contents": "write", "pull-requests": "write"}

steps = wf["jobs"]["autoupdate"]["steps"]
by_id = {s["id"]: s for s in steps if "id" in s}
assert by_id["hooks"]["continue-on-error"] is True, "a hard hook failure must still yield a PR"
assert "continue-on-error" not in by_id["cpr"], "the PR step must never swallow failures"

raw = open(path).read()
assert "secrets.RELEASE_PAT || github.token" in raw, "mirror bump-version.yml's token fallback"
assert "branch: build/pre-commit-autoupdate" in raw, "fixed branch → update in place, no PR pile-up"
assert "uv run --project defendable-science pre-commit autoupdate" in raw, "use the pinned pre-commit"
assert "peter-evans/create-pull-request@v7" in raw
print("pre-commit-autoupdate.yml: all assertions pass")
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
uv run --project defendable-science python /tmp/check_autoupdate.py
```

Expected: `FileNotFoundError: … '.github/workflows/pre-commit-autoupdate.yml'`

- [ ] **Step 3: Write the workflow**

Create `.github/workflows/pre-commit-autoupdate.yml` with exactly this content:

````yaml
name: pre-commit autoupdate

# Bumps the `rev:` pins of the REMOTE hooks in .pre-commit-config.yaml and opens
# a PR. Dependabot has no `pre-commit` ecosystem, so this is the counterpart to
# .github/dependabot.yml (ADR-0036). The three local hooks (lint, typecheck,
# plugin-validate) are tools/*.sh and have no revs.

on:
  workflow_dispatch:
  schedule:
    - cron: "0 8 * * 1" # Mondays 08:00 UTC — an hour after Dependabot's batch

permissions:
  contents: write
  pull-requests: write

jobs:
  autoupdate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v8.3.1
      - name: Sync the lint group (for the pinned pre-commit)
        run: uv sync --project defendable-science --group lint
      - name: pre-commit autoupdate
        id: update
        run: |
          uv run --project defendable-science pre-commit autoupdate \
            2>&1 | tee /tmp/autoupdate.log
          if git diff --quiet -- .pre-commit-config.yaml; then
            echo "changed=false" >> "$GITHUB_OUTPUT"
          else
            echo "changed=true" >> "$GITHUB_OUTPUT"
          fi
          {
            echo "### \`pre-commit autoupdate\`"
            echo ""
            echo '```'
            cat /tmp/autoupdate.log
            echo '```'
          } >> "$GITHUB_STEP_SUMMARY"
      - name: Run the updated hooks
        id: hooks
        if: steps.update.outputs.changed == 'true'
        continue-on-error: true # a hard failure must still produce a reviewable PR
        run: |
          uv run --project defendable-science pre-commit run --all-files \
            2>&1 | tee /tmp/hooks.log
      - name: Summarize the hook outcome
        id: outcome
        if: steps.update.outputs.changed == 'true'
        run: |
          if [ "${{ steps.hooks.outcome }}" = "success" ]; then
            echo "note=All hooks pass with the updated revs." >> "$GITHUB_OUTPUT"
          else
            echo "note=:warning: **\`pre-commit run --all-files\` FAILED** with the updated revs. Autofixes (if any) are included here; the remaining failures need a human." >> "$GITHUB_OUTPUT"
          fi
          {
            echo "tail<<HOOKTAIL"
            tail -n 40 /tmp/hooks.log
            echo "HOOKTAIL"
          } >> "$GITHUB_OUTPUT"
      - name: Open PR
        id: cpr
        if: steps.update.outputs.changed == 'true'
        uses: peter-evans/create-pull-request@v7
        with:
          # A RELEASE_PAT (if set) lets the commit trigger CI on the PR;
          # otherwise the default token is used and CI won't auto-run (see body).
          token: ${{ secrets.RELEASE_PAT || github.token }}
          branch: build/pre-commit-autoupdate
          base: main
          title: "build(deps): pre-commit hook autoupdate"
          author: Davor Runje <davor@synthpop.ai>
          committer: Davor Runje <davor@synthpop.ai>
          labels: dependencies
          commit-message: |
            build(deps): pre-commit hook autoupdate

            Bump the remote hooks' `rev:` pins, plus any fixes the updated hooks
            applied to tracked files.
          body: |
            `pre-commit autoupdate` bumped the remote hook `rev:` pins in
            `.pre-commit-config.yaml`. Dependabot has no `pre-commit` ecosystem,
            so this workflow is its counterpart (ADR-0036).

            **Hook run:** ${{ steps.outcome.outputs.note }}

            <details><summary><code>pre-commit run --all-files</code> — last 40 lines</summary>

            ```
            ${{ steps.outcome.outputs.tail }}
            ```

            </details>

            > If no CI checks appear on this PR, it was created with `GITHUB_TOKEN`
            > (which can't trigger workflows). Add a `RELEASE_PAT` repo secret, or
            > re-run CI / admin-merge.
      - name: Report no-op
        if: steps.update.outputs.changed != 'true'
        run: |
          echo "### No hook rev changes — no PR opened." >> "$GITHUB_STEP_SUMMARY"
````

- [ ] **Step 4: Run the check again**

```bash
uv run --project defendable-science python /tmp/check_autoupdate.py
```

Expected: `pre-commit-autoupdate.yml: all assertions pass`

- [ ] **Step 5: Confirm the local hooks still pass**

```bash
uvx pre-commit run --all-files
```

Expected: all hooks `Passed`.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/pre-commit-autoupdate.yml
git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" \
  commit --no-gpg-sign -m "$(cat <<'EOF'
ci: add a scheduled pre-commit autoupdate workflow

Dependabot has no `pre-commit` ecosystem, so the remote hooks' `rev:` pins never
move on their own. Runs `pre-commit autoupdate` weekly with the lint group's
pinned pre-commit, runs the updated hooks so their autofixes land in the same
PR, and opens a PR via the same create-pull-request pattern bump-version.yml
uses. A hard hook failure still produces a reviewable PR (with the failure in
the body) rather than a silent no-op week.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: ADR-0036 and the index row

**Files:**
- Create: `decisions/0036-automated-dependency-updates.md`
- Modify: `decisions/README.md` — append one row after the `0035` row (currently the last row of the table).

**Interfaces:**
- Consumes: the group names and policy from Task 1, the workflow from Task 2 (both are referenced by the ADR).
- Produces: the identifier `ADR-0036`, already referenced in the comment headers of both files created above.

- [ ] **Step 1: Write the ADR**

Create `decisions/0036-automated-dependency-updates.md`:

```markdown
# ADR-0036: Automated dependency updates — Dependabot for the dev toolchain and Actions, a scheduled autoupdate for hook revs, no auto-merge

- Status: accepted · Date: 2026-08-25 · Deciders: Davor Runje

## Context

Dependency maintenance was manual: PR #78 bumped six tool pins and 21 locked
versions by hand. The repo carries three independent version surfaces — the
package's `dev`/`lint` pins plus `uv.lock`, the action refs in
`.github/workflows/**`, and the remote hook `rev:` pins in
`.pre-commit-config.yaml` — and each drifts on its own schedule. The
`codespell` hook rev had already drifted from the `lint` group's pin.

The package is a **library** installed beside a consumer's own environment, so
`[project.dependencies]` are deliberately wide floors (`typer>=0.12`,
`requests>=2.31`, `pyyaml>=6.0`, `pooch>=1.8`). Raising them would narrow what
consumers can co-install for no benefit.

## Decision drivers

- Automate the mechanical part without surrendering the review decision.
- Never narrow the runtime floors.
- Batch enough to stay reviewable on a solo-maintained repo; isolate the bumps
  that actually break things.
- Don't review a release the same day it ships — yanked and compromised
  releases are usually caught within days.
- One pattern for Action-created PRs, not two (`bump-version.yml` already
  established it).

## Considered options

1. **Dependabot scoped to development dependencies, minors/patches grouped with
   `ruff`+`mypy` split out, majors ungrouped, 7-day cooldown, plus a scheduled
   `pre-commit autoupdate` workflow. No auto-merge.**
2. Dependabot with `versioning-strategy: increase` across all dependencies,
   floors included.
3. Ungrouped Dependabot — one PR per dependency.
4. Patch-level auto-merge once CI is green.
5. No Dependabot: a scheduled `uv lock --upgrade` workflow that opens a PR.

## Decision

Option 1.

- **Scope:** `allow: dependency-type: "development"` on the `uv` entry, so only
  the `dev`/`lint` `==` pins and `uv.lock` move. The runtime floors are never
  rewritten.
- **Grouping:** minors and patches are grouped; `ruff` and `mypy` form their own
  group ahead of the catch-all. Plain semver misplaces the risk for this
  toolchain — `ruff` is 0.x and `mypy` majors move fast, so a *minor* bump
  (ruff 0.15.21 → 0.16.4) is the one that rewrites files or surfaces new
  errors repo-wide. Majors are excluded from every group and therefore arrive
  one PR at a time.
- **Cadence:** weekly, Mondays 07:00 UTC, with `cooldown: default-days: 7` on
  the Python side. `cooldown` is unsupported for `github-actions`, so that entry
  has no freshness delay.
- **Hook revs:** `.github/workflows/pre-commit-autoupdate.yml` runs
  `pre-commit autoupdate` weekly (Mondays 08:00 UTC), runs the updated hooks so
  their autofixes land in the same PR, and opens a PR through
  `peter-evans/create-pull-request@v7` with the same `RELEASE_PAT || github.token`
  fallback `bump-version.yml` uses.
- **No auto-merge**, of any update type. `main` is protected, merging is the
  maintainer's action, and the agency principle says the human signs material
  decisions — a green tool bump is still a decision.

## Consequences

- At most three or four dependency PRs a week, each reviewable as a unit, each
  through the full green gate.
- A formatter or type-checker change is never buried in a batch with type stubs.
- The runtime install surface stays as wide as authored; Dependabot cannot
  narrow it.
- A CVE fix published on a Tuesday waits up to a week on the version-update
  path. Security *alerts* are unaffected — this is a version-update policy.
- `codespell` and `detect-secrets` remain pinned in two places, now bumped by
  two independent automations; the durable fix (making the `lint` pins the
  single source) is tracked as a follow-up issue.
- Dependabot PRs deviate from the house `<area>/<slug>` branch and
  commit-attribution conventions. Accepted: those govern human PRs.

## Rejected alternatives

- **Option 2 (floors included)** — would rewrite `typer>=0.12` to the latest
  release, narrowing consumer co-installation for no gain, and would need
  reverting on most PRs.
- **Option 3 (ungrouped)** — maximum bisectability at roughly 6–10 PRs per
  cycle, each demanding the full gate. Too much review load for a
  solo-maintained repo.
- **Option 4 (patch auto-merge)** — even with a 100% coverage gate and strict
  mypy, a green tool bump can change formatting or lint semantics. Landing it
  in `main` unseen contradicts the agency principle for a saving measured in
  seconds.
- **Option 5 (`uv lock --upgrade` workflow)** — hand-rolls what Dependabot's
  `uv` support already does and gives up per-dependency changelogs,
  compatibility scores, and security-update PRs.
```

- [ ] **Step 2: Append the index row**

In `decisions/README.md`, immediately after the `0035` row, add:

```markdown
| [0036](0036-automated-dependency-updates.md) | Automated dependency updates — Dependabot for the dev toolchain + Actions, scheduled `pre-commit autoupdate`, no auto-merge | accepted |
```

- [ ] **Step 3: Verify the index and file agree**

```bash
grep -c "0036" decisions/README.md   # expect: 1
ls decisions/0036-automated-dependency-updates.md
uvx codespell --ignore-words=.codespell-whitelist.txt \
  decisions/0036-automated-dependency-updates.md decisions/README.md
```

Expected: `1`, the path echoed, and no codespell output.

- [ ] **Step 4: Commit**

```bash
git add decisions/0036-automated-dependency-updates.md decisions/README.md
git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" \
  commit --no-gpg-sign -m "$(cat <<'EOF'
docs(decisions): ADR-0036 automated dependency updates

Record the policy behind .github/dependabot.yml and the pre-commit autoupdate
workflow: development-scoped updates so the runtime floors stay wide, risk-split
grouping (ruff/mypy alone), weekly cadence with a 7-day cooldown, and no
auto-merge of any update type. Rejected alternatives kept: floor-raising,
per-dependency PRs, patch auto-merge, and a hand-rolled uv lock --upgrade
workflow.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: The follow-up issue for the twice-pinned tools

**Files:** none — this task creates a GitHub issue.

**Interfaces:**
- Consumes: ADR-0036 (the issue cites it as the reason the duplication now has two bumpers).
- Produces: an issue number, referenced by Task 5's PR body.

- [ ] **Step 1: Create the issue with the `create-issue` skill**

Use the local `create-issue` skill (`.claude/skills/create-issue/SKILL.md`) so
the house format is applied. The issue must be completable by a session that has
only the repo and the issue text. It must contain:

- **Context:** `codespell` and `detect-secrets` are each pinned twice — a `rev:`
  in `.pre-commit-config.yaml` and a `==` pin in the `lint` dependency group of
  `defendable-science/pyproject.toml`. The hook rev had already drifted once
  from the `lint` pin before PR #78 reconciled the two locations. After
  ADR-0036 two independent automations bump them (Dependabot for the pin,
  `pre-commit-autoupdate.yml` for the rev), so the drift recurs on a schedule
  whenever the two automations bump on different weeks.
- **Goal:** one source of truth per tool version.
- **Where (exact locations):** `.pre-commit-config.yaml` — the `codespell-project/codespell`
  repo block (`rev: v2.4.3`) and the `Yelp/detect-secrets` block (`rev: v1.5.0`);
  `defendable-science/pyproject.toml` — the `lint` group's `codespell==` and
  `detect-secrets==` pins.
- **Proposed approach:** convert both to `repo: local` hooks driven by the `lint`
  group (the pattern `lint`, `typecheck`, and `plugin-validate` already use via
  `tools/*.sh`), leaving `pyupgrade` and `pre-commit-hooks` as the only
  autoupdate-managed revs.
- **Acceptance criteria:** each of the two tools' versions appears in exactly one
  file; `pre-commit run --all-files` passes; CI green; the `pre-commit autoupdate`
  workflow no longer proposes revs for these two.
- **References:** ADR-0036, the design spec
  `docs/superpowers/specs/2026-08-25-dependabot-design.md` (§ "Known duplication"),
  PR #78 (where the drift surfaced).

- [ ] **Step 2: Record the issue number**

```bash
gh issue list --limit 5 --search "codespell detect-secrets in:title"
```

Expected: the new issue appears. Note its number for Task 5.

---

### Task 5: Open the PR

**Files:** none — this task opens the pull request.

**Interfaces:**
- Consumes: commits from Tasks 1–3, the issue number from Task 4.
- Produces: a PR number, used by Task 6.

- [ ] **Step 1: Confirm the branch state**

```bash
git log --oneline origin/main..HEAD    # expect 4 commits: spec, config, workflow, ADR
git status -sb                          # expect a clean tree
```

- [ ] **Step 2: Final green check**

```bash
uvx pre-commit run --all-files
./tools/validate-plugin.sh
```

Expected: all hooks `Passed`; `✔ Validation passed`.

- [ ] **Step 3: Open the PR with the `create-pr` skill**

Use the local `create-pr` skill (`.claude/skills/create-pr/SKILL.md`). Title:

```
ci: automate dependency updates (Dependabot + pre-commit autoupdate)
```

The body must state: what the two files do; that runtime floors are
out of scope by construction (`allow: dependency-type: development`); that
nothing auto-merges; that ADR-0036 records the policy; that the autoupdate
workflow's runtime behaviour **cannot be verified until it is on `main`**
(`workflow_dispatch` requires the default branch), with Task 6's post-merge
checklist quoted; and a link to Task 4's issue as the tracked follow-up (a
plain link, **not** `Closes #NN` — that issue is not resolved by this PR).

- [ ] **Step 4: Wait for CI and report**

```bash
until [ -z "$(gh pr checks <PR> 2>/dev/null | awk '$2=="pending"')" ]; do sleep 15; done
gh pr checks <PR>
```

Expected: `pre-commit`, `plugin-validate`, `build-check`, `check`, and the four
`test (3.11–3.14)` jobs all `pass`; `live-link-check` and `publish` `skipping`.
Do **not** merge — merging is the maintainer's action.

---

### Task 6: Post-merge first-run verification

Run only after the maintainer merges Task 5's PR. This is where the spec's
acceptance criteria are actually settled — a Dependabot config cannot be proven
by unit test.

**Files:** none.

**Interfaces:**
- Consumes: the merged config and workflow.
- Produces: a verification report, plus (if criteria fail) follow-up fixes.

- [ ] **Step 1: Confirm Dependabot parsed the config**

Open the repo's **Insights → Dependency graph → Dependabot** tab. Expected: both
`uv` and `github-actions` listed with a "Last checked" time and **no** config
parse error. A parse error appears here and nowhere else — the file is not
validated by CI.

- [ ] **Step 2: Force a run instead of waiting for Monday**

On that same tab, press **Check for updates** for each ecosystem.

- [ ] **Step 3: Check the results against the spec's criteria**

```bash
gh pr list --label dependencies --state open
```

Verify, per the spec's acceptance list:
- a `uv` PR touches only dev/lint pins and `uv.lock`, never `[project.dependencies]`;
- a `mypy` bump rewrites **both** the `dev` and `lint` occurrences in one PR;
- `ruff`/`mypy` are in a PR separate from `pytest*`/`types-*`/`codespell`;
- a major bump, if any is available, arrives as its own PR;
- no PR for a release younger than 7 days;
- PRs carry the `dependencies` label, `build(deps)`/`ci(deps)` subjects, and CI runs;
- no PRs for `pypa/gh-action-pypi-publish@release/v1` or `re-actors/alls-green@release/v1`.

**If zero PRs appear:** this is the spec's documented unknown — Dependabot may
not classify PEP 735 `dependency-groups` as `development`. Zero PRs means
*investigate*, never *success*. Check the Dependabot run log on that tab for
"no dependencies to update", then apply the spec's fallback: drop the `allow`
filter and add `ignore` entries for `typer`, `requests`, `pyyaml`, and `pooch`
by name, noting in the PR that `ignore` also suppresses their security updates.

- [ ] **Step 4: Exercise the autoupdate workflow**

```bash
gh workflow run "pre-commit autoupdate"
until [ -n "$(gh run list --workflow='pre-commit autoupdate' --limit 1 --json conclusion -q '.[0].conclusion')" ]; do sleep 10; done
gh run list --workflow="pre-commit autoupdate" --limit 1
gh pr list --head build/pre-commit-autoupdate
```

Expected: a PR if any of the four remote hook revs is stale, labeled
`dependencies`, with the hook outcome quoted in its body; or, if all four are
already current, no PR — satisfied by the run's job summary explicitly
reporting no rev changes, not by silence.

- [ ] **Step 5: Prove quiet weeks are quiet**

After that PR merges, dispatch the workflow again:

```bash
gh workflow run "pre-commit autoupdate"
```

Expected: the run succeeds, the job summary says `No hook rev changes — no PR
opened.`, and `gh pr list --head build/pre-commit-autoupdate` is empty.

- [ ] **Step 6: Report**

Report each acceptance criterion as met or not met, with the PR/run links as
evidence. State any criterion that could not be exercised (e.g. no major bump
was available) as *not yet verified* rather than passed.
