---
name: create-pr
description: Use when changes are ready to land on davorrunje/defendable-science — branch, run the checks, commit with this repo's attribution, and open a PR (never commit to main). Encodes the branch/commit/checks/body ritual and the Closes #NN convention. Templates live in STYLE.md.
---

# Create PR

Every change lands through a pull request. **`main` is protected — never commit
to it.** This skill encodes the repo's PR ritual so branch, checks, attribution,
and body are consistent without rediscovery. Its `Closes #NN` half is the mirror
of the paired [`create-issue`](../create-issue/SKILL.md) close standard — keep
the two in sync.

## Process

1. **Branch off `main`.** Name it `<area>/<slug>` using the same `<area>`
   vocabulary as `create-issue` (`docs`, `ci`, `core`, `literature`, `dataset`,
   `defend`, `backlog`, `skills`, `dx`, `test`, …):

   ```bash
   git fetch origin && git switch -c <area>/<slug> origin/main
   ```

   Do the work on that branch.

2. **Go green before opening** — never open a red PR. When package code changed,
   from the `defendable-science/` subdirectory:

   ```bash
   cd defendable-science
   uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
   ```

   `pytest` enforces the **100% coverage gate** — it must pass. Then, on the
   changed files:

   ```bash
   uvx codespell --ignore-words=/workspaces/scholar/.codespell-whitelist.txt <changed files>
   ```

   For plugin/markdown-only changes, run `./tools/validate-plugin.sh` and
   codespell.

3. **Commit with this repo's attribution.** Author as **Davor Runje**, add the
   Claude trailer, and disable GPG signing (SSH signing is unavailable in these
   sessions):

   ```bash
   git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" \
     commit --no-gpg-sign -F <message-file>
   ```

   The commit-message shape (subject + body + trailer) is in [STYLE.md](STYLE.md).

4. **Push and open the PR** against `main`:

   ```bash
   git push -u origin <area>/<slug>
   gh pr create --base main [--milestone "<milestone>"] --title "<title>" --body-file <body-file>
   ```

   The PR body follows STYLE.md: concise what/why, **`Closes #NN`** for every
   issue it resolves (this is what closes them — see `create-issue` § Closing),
   and the Claude Code footer. Set `--milestone` when the issues carry one.

5. **Report the PR URL.** Do **not** merge — merges are the maintainer's (see
   below).

## Hard rules

- **Never commit to `main`** (protected). Branch first, always.
- **Base on `main`, not on another feature branch.** Deleting a base branch on
  merge *closes* the dependent PR — a real failure this repo hit (#14 → #17).
  Stacked work waits for its base to merge, or is restructured onto `main`.
- **Green before opening.** The `all-green` CI gate + the 100% coverage gate are
  required; don't outsource discovering a red build to CI.
- **Attribution is not optional** — author Davor Runje + the `Co-Authored-By`
  trailer + `--no-gpg-sign` on every commit.

## Protected-main reality

- Merging is the maintainer's action; the assistant opens PRs and reports, it
  does not merge.
- CI won't run on a PR that a GitHub Action created with the default token; a
  `RELEASE_PAT` repo secret lets Actions-created PRs (e.g. the version bump) get
  CI. (Relevant only to the release automation, not hand-made PRs.)

## Red flags

- `git commit` on `main`, or a branch whose base is a soon-to-be-deleted branch.
- Opening a PR before the checks pass locally.
- A commit missing the author identity or the `Co-Authored-By` trailer.
- A PR body with no `Closes #NN` when it resolves a tracked issue, or missing the
  Claude Code footer.
