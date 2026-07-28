# PR Style

The concrete templates for landing changes on `davorrunje/defendable-science`.
See [SKILL.md](SKILL.md) for the process and the hard rules.

## Branch name

`<area>/<slug>`

- `<area>` mirrors the commit-scope / issue vocabulary: `docs`, `ci`, `build`,
  `skills`, `core`, `literature`, `dataset`, `defend`, `backlog`, `plugin`,
  `dx`, `test`, `fix`, `feat`.
- `<slug>` is a short kebab-case description: `fix/rate-limit-honesty`,
  `docs/claude-md`, `dx/local-skills`.

## Commit message

```
<type>(<scope>): <concise imperative subject>

<body — what changed and why, wrapped ~72 cols. Reference issues/PRs/ADRs by
number. State the behavioral change, not just the mechanics.>

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

- `<type>` is Conventional-Commits style: `feat`, `fix`, `docs`, `test`, `ci`,
  `build`, `chore`, `refactor`.
- `<scope>` is the `<area>` (e.g. `literature`, `dataset`, `bench`→n/a here,
  `skills`, `package`).
- Commit as **Davor Runje** with `--no-gpg-sign`:
  `git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" commit --no-gpg-sign -F <file>`.
- Commits of **skill-produced artifacts** (not repo-dev commits) additionally
  carry the discovery trailers from `resources/commit-attribution.md`
  (`Generated-with:` / `DefendableScience-Skill:`).

## PR title

`<type>(<scope>): <concise summary>` — same shape as the commit subject
(e.g. `fix(package): honest rate-limit handling`). Append `(closes #NN)` when it
usefully signals scope.

## PR body

```markdown
## What

One or two sentences: the change and why it matters (the behavioral/user-visible
effect, not a file list).

## Details   (optional)

Bullets for the notable pieces — the non-obvious decisions, trade-offs, or a
"deliberately not changed" note. Reference ADRs/issues by number.

Closes #NN            <!-- one per issue this PR resolves; this is what closes them -->

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- **`Closes #NN`** for every issue the PR resolves — merging then closes and
  links them (the mirror of `create-issue` § Closing; keep in sync). Use one
  `Closes #NN` line per issue; a single PR may close several (e.g. a matched
  pair of sibling issues).
- Always end with the `🤖 Generated with [Claude Code](https://claude.com/claude-code)`
  footer.
- Pass the body via `--body-file` to avoid multi-line shell-quoting problems.

## Commands

```bash
git fetch origin && git switch -c <area>/<slug> origin/main
# … work + go green (see SKILL.md) …
git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" commit --no-gpg-sign -F msg.txt
git push -u origin <area>/<slug>
gh pr create --base main --title "<title>" --body-file body.md [--milestone "v0.1.0 — first final"]
```

Base is **always `main`** (never a soon-to-be-deleted feature branch — see
SKILL.md hard rules).
