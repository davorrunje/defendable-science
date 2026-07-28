# Rename: Honest Scholar → Defendable Science

**Status:** approved, ready to plan
**Date:** 2026-07-28

Rename the project, both shipped artifacts, and every identifier they expose,
from `honest-scholar` to `defendable-science`. The new visual identity is
already in `assets/` and `docs/design/visual-identity.md`; this change makes the
rest of the repo agree with it.

The rename is **total**: no identifier keeps the old name outside the historical
record. The old PyPI and TestPyPI packages are abandoned with no forwarding
release.

## Scope

Two independently-versioned artifacts change name together (CLAUDE.md, ADR-0026):
the **plugin** at the repo root and the **package** in the `honest-scholar/`
subdirectory. Roughly 890 occurrences across 116 tracked files, plus two
directory renames.

Out of scope: the eleven skill names (`defend`, `digest`, `literature`, …) are
verbs and do not change; the word *honest* as vocabulary does not change (see
[Vocabulary](#vocabulary)).

## Naming map

This table is the specification. The sweep implements it; nothing else is
authoritative.

| Surface | Now | After |
|---|---|---|
| GitHub repo | `davorrunje/honest-scholar` | `davorrunje/defendable-science` |
| Docs repo | `davorrunje/honest-scholar-docs` | `davorrunje/defendable-science-docs` |
| Docs domain | `honest-scholar.science` | `defendable.science` |
| Plugin name (`plugin.json`, `marketplace.json`) | `honest-scholar` | `defendable-science` |
| Plugin install | `/plugin install honest-scholar@honest-scholar` | `/plugin install defendable-science@defendable-science` |
| PyPI + TestPyPI distribution | `honest-scholar` | `defendable-science` |
| Package subdirectory | `honest-scholar/` | `defendable-science/` |
| Python module | `honest_scholar` | `defendable_science` |
| Console script | `honest-scholar` | `defendable-science` |
| Short alias | `hsch` | `dsci` |
| Project config dir | `.honest-scholar/` | `.defendable-science/` |
| Env vars | `HONEST_SCHOLAR_LIVE`, `HONEST_SCHOLAR_KEYS_PATH` | `DEFENDABLE_SCIENCE_LIVE`, `DEFENDABLE_SCIENCE_KEYS_PATH` |
| Commit trailer | `HonestScholar-Skill:` | `DefendableScience-Skill:` |
| Isolated-install state dir | `$XDG_STATE_HOME/honest-scholar/` | `$XDG_STATE_HOME/defendable-science/` |
| ensure-tooling compat pin | `honest-scholar>=0.1.0,<0.2.0` | `defendable-science>=0.2.0,<0.3.0` |
| Plugin version | `0.1.0` | `0.2.0` |
| Package version | `0.1.1` | `0.2.0` |
| Display name in prose | Honest Scholar | Defendable Science |

### Versioning

Both artifacts land on `0.2.0`. The rename is a breaking change, so a minor bump
under `0.x` is the honest signal, and the numbers stay monotone with the
CHANGELOG. The alignment is coincidental — plugin and package continue to
version independently (ADR-0026), and this change must not introduce any
coupling between them.

### Vocabulary

*Honest* is a technical term in this repo, not only a product name. These stay
exactly as they are:

- **failure honesty** — the CLAUDE.md convention name
- **honest stop** — `resources/ensure-tooling.md`
- **an honest ledger** — `STATUS.md`
- `honest AI use` — a `CITATION.cff` keyword
- `honest, defensible AI-assisted research` — the CITATION abstract phrasing

Only prose where the *name* was the grammatical subject is rewritten
(`honest-scholar gives your workflow…` → `Defendable Science gives…`). The
rename rules below match `honest-scholar` / `honest_scholar` / `Honest Scholar`
and never bare `honest`, so this holds automatically; the hand-written prose
pass must preserve it deliberately.

## The sweep

A script, `tools/rename-sweep.sh`, performs the mechanical substitution, so the
transformation is auditable rather than a 116-file mystery diff. It lands as the
PR's **first** commit and is deleted in the PR's **last** commit: reviewers can
read it in the commit history, and the merged tree does not carry a one-shot
script forever.

It runs over every tracked file, excluding `.git/`, `.venv/`, `.worktrees/`, the
package lockfile (regenerated, not patched), and **this spec plus its
implementation plan** — those two deliberately quote the old name throughout and
must survive verbatim.

Rules apply **in this order**. Two ordering constraints are load-bearing: the
`.science` rules (2, 3) must precede the bare-name rules, or the domain becomes
`defendable-science.science`; and rule 2 must precede rule 4. Rules 2 and 4
exist because shields.io escapes a literal hyphen by doubling it, so
`README.md` and `DISCLOSURE.md` contain `honest--scholar` in badge URLs — a form
the bare rule does not match. They need different replacements: rule 2 is the
*domain* (which loses its hyphen entirely), rule 4 is the *name* (where
`defendable--science` renders as `defendable-science`). Rule 1 is redundant with
rule 9 and is listed only to make the docs-repo rename explicit.

```
1  honest-scholar-docs       → defendable-science-docs
2  honest--scholar\.science  → defendable.science      (shields.io escaped hyphen)
3  honest-scholar\.science   → defendable.science
4  honest--scholar           → defendable--science     (shields.io escaped hyphen)
5  HONEST_SCHOLAR            → DEFENDABLE_SCIENCE
6  HonestScholar             → DefendableScience
7  Honest Scholar            → Defendable Science
8  honest_scholar            → defendable_science
9  honest-scholar            → defendable-science
10 \bhsch\b                  → dsci
```

Rule 10 is word-boundary anchored and hits exactly three sites
(`honest-scholar/pyproject.toml`, `docs/design/proposals/tooling-package.md`).

Then the directory moves, via `git mv` so history follows the files:

```bash
git mv honest-scholar defendable-science
git mv defendable-science/honest_scholar defendable-science/defendable_science
cd defendable-science && uv lock      # regenerate; do not sed the lockfile
```

### Hand-written, not generated

Four pieces the script cannot produce:

**0. Version bumps.** The sweep only moves names, never numbers. Three files
need a hand edit: `.claude-plugin/plugin.json` (`0.1.0` → `0.2.0`),
`defendable-science/pyproject.toml` (`0.1.1` → `0.2.0`), and `CITATION.cff`
(`version: 0.1.1` → `0.2.0`). `tools/bump_version.py` only touches the
pyproject; the other two are manual.

**1. `decisions/0035-rename-to-defendable-science.md`** — a MADR ADR: context
(the identity now leads with defensibility, matching the new visual identity and
the `defend` / `digest` exploration→resolution firewall), decision drivers,
options considered (rename / keep / dual-name), the decision, and consequences.
The consequences section must state explicitly that the old PyPI and TestPyPI
distributions are abandoned with no forwarding release, and that any existing
consumer repo must rename its `.honest-scholar/` directory and
`HONEST_SCHOLAR_*` environment variables by hand. Append the entry to
`decisions/README.md`.

**2. `CHANGELOG.md`** — a new `0.2.0` entry describing the rename as breaking,
listing each renamed surface a consumer touches (plugin install string, CLI
command, PyPI name, config dir, env vars). The existing `0.1.0` and `0.1.1`
entries keep `honest-scholar` verbatim: those releases really did ship under
that name, and rewriting them would be the kind of tidy lie the repo's
failure-honesty rule exists to prevent. A one-line note at the top of the file
records that entries before `0.2.0` refer to the project's former name.

**3. Prose passes** where substitution is grammatical but reads badly — read and
edit these by hand rather than trusting the sweep:

- `README.md` — the opening paragraph and the banner `alt` text
- `defendable-science/README.md` — this becomes the **PyPI long description**, so
  it is the first thing a package visitor reads; 30 occurrences
- `docs/USER-GUIDE.md` — the primary user document, 35 occurrences, the highest
  count outside a superseded plan
- `STATUS.md` — the two-artifact summary and the Released section. While here,
  fix the stale count: it says "All 10 skills" but `digest` (#68) made eleven
- `DISCLOSURE.md` — the disclosure boilerplate a consumer copies into their own work
- `CITATION.cff` — `title`, `abstract`, and the `message` field
- `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` descriptions
- `CLAUDE.md` — the "What this repo is" section
- `docs/design/proposals/tooling-package.md:96` — asserts the distribution name
  "is reserved on both PyPI and TestPyPI". After the sweep that becomes a claim
  about `defendable-science`, which is only true once cutover step 0 is done

### Residue gate

After the sweep:

```bash
grep -rniE 'honest[-_. ]*scholar|\bhsch\b' \
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=.worktrees .
```

The `*` (not `?`) is deliberate: `?` allows only one separator character and
would silently miss the shields.io `honest--scholar` badge form.

must return matches only in these four files, which quote the old name
deliberately:

- `CHANGELOG.md` — the `0.1.0` / `0.1.1` released entries and the former-name note
- `decisions/0035-rename-to-defendable-science.md` — the ADR recording the move
- `docs/superpowers/specs/2026-07-28-defendable-science-rename-design.md` — this spec
- the matching plan under `docs/superpowers/plans/`

Any other match fails the change.

### Full gate before the PR opens

Run from `defendable-science/` unless noted:

- `uv run pytest -q` — the 100% branch-coverage gate. The module rename touches
  `--cov=honest_scholar` in `pyproject.toml`; a stale value reports 0% coverage
  against a module that no longer exists and must not slip through. Confirm the
  run reports coverage against `defendable_science`.
- `uv run mypy` — strict; also covers `../tools`.
- `uv run ruff check` and `uv run ruff format --check`.
- `pre-commit run --all-files` from the repo root — note
  `.pre-commit-config.yaml` references the lockfile by path twice (lines 30, 76)
  and both must move to `defendable-science/uv.lock`.
- `./tools/validate-plugin.sh` from the repo root.
- `uv run --project defendable-science python tools/build_docs_site.py --out /tmp/docs-site`
  — the only check that proves the Typer app still imports under its new module
  name (`tools/build_docs_site.py` imports `honest_scholar.cli` directly).

### Files needing attention beyond substitution

Substitution is correct for these but they are the ones that break the release
if missed, so verify each explicitly:

- `defendable-science/pyproject.toml` — `[project] name`, `[project.scripts]`
  both entries, `[project.urls]` all five, `[tool.hatch.build.targets.*]
  include`, `[tool.mypy] files`, `[tool.pytest.ini_options] addopts` and
  `markers`, `[tool.ruff] include`.
- `.github/workflows/ci.yml` — `--project` flags and `working-directory`.
- `.github/workflows/publish.yml` — the version-guard `grep` path and
  `working-directory`; the trusted-publisher comment block.
- `.github/workflows/docs-publish.yml` — `--project`, the docs-repo checkout,
  the `SITE` env var, the `llms.txt` host regex, the lychee `--include` pattern,
  and the docs bot's `git config user.name`.
- `.github/workflows/bump-version.yml` and `tools/bump_version.py` — the
  pyproject path and the release-PR title/body strings.
- `tools/lint.sh`, `tools/typecheck.sh` — the `cd` target.
- `tools/build_docs_site.py` — `GH_REPO`, the import, the Typer `info_name`, and
  the rendered command prefixes.
- `.gitignore` — the three `.honest-scholar/` entries.
- `codecov.yml` — the pyproject path in the comment.
- `resources/ensure-tooling.md` — every install command, the compat pin, the
  git-subdirectory fallback URL, and the state-dir paths.
- `resources/commit-attribution.md` and all **eleven** `skills/*/SKILL.md` — the
  `HonestScholar-Skill:` trailer.
- `.claude/skills/create-issue/STYLE.md` and `.claude/skills/create-pr/` — repo
  slug, package dir, and module name. Leave `fix/rate-limit-honesty` and
  `fix(package): honest rate-limit handling` untouched; those are the word
  *honest*, not the name.

## Cutover

Ordered. Steps 0 and 0b secure names that are currently **unowned** and are
unrecoverable if someone else takes them; steps 3 and 4 gate the release jobs.

0. **Reserve the distribution name on PyPI and TestPyPI first.** Verified
   available on both as of 2026-07-28 (`/pypi/defendable-science/json` → 404).
   This is the one step with an unrecoverable failure mode: if the name is taken
   between now and the release, every other decision in this spec has to be
   redone. The project already did this for `honest-scholar` by publishing a
   `0.0.0a0` pre-release to both indexes
   (`docs/design/proposals/tooling-package.md:96`); repeat that. A *pre-release*
   matters: `pip install defendable-science` will not resolve to `0.0.0a0` by
   default, so the placeholder cannot be mistaken for a working install. Upload
   with an API token — trusted publishing (step 3) cannot run yet, since the
   repo is not renamed and `pyproject.toml` still declares the old name.
0b. **Register `defendable.science`** — ✅ **done 2026-07-28.** Registered at
   Cloudflare Registrar; RDAP confirms status `add period` and delegation to
   `paul`/`susan.ns.cloudflare.com`, the same pair as the existing
   `honest-scholar.science` zone. The zone itself is empty; records come in step 4.
   *Recorded because it nearly derailed the plan:* a 101domains order placed a
   week earlier displayed as "Processing" with a 2027 expiry, but the domain had
   never reached the registry — registry whois returned "No Data Found" and RDAP
   404. A registrar panel is not evidence of registration; RDAP is. A refund from
   101domains is outstanding and is not a blocker.
1. `gh repo rename defendable-science`. GitHub redirects keep the open PR and
   every existing URL working.
2. Rename the docs repo to `defendable-science-docs`. **Verify Mintlify's GitHub
   connection afterward** — a repo rename can drop it and require reconnecting
   in the dashboard.
3. Register pending trusted publishers on **PyPI and TestPyPI** for distribution
   `defendable-science`, repo `davorrunje/defendable-science`, workflow
   `publish.yml`, environments `pypi` and `testpypi`. Without this the release
   job fails at the OIDC exchange.
4. Stand up `defendable.science` **before** tagging: nameserver delegation, the
   Mintlify custom-domain record (mirror the proxied record in the existing
   `honest-scholar.science` Cloudflare zone), and TLS issuance. It must be
   *serving*, not merely configured, before step 7 — `docs-publish.yml`'s
   `live-link-check` job polls `https://defendable.science/llms.txt` and fails
   the release if it is not. Do **not** repoint or delete anything in the
   `honest-scholar.science` zone: it serves the live docs today, and it is the
   only possible 301 source for the permanent links already published in the
   `0.1.0` / `0.1.1` PyPI metadata and `CITATION.cff`.
5. Merge the PR.
6. `workflow_dispatch` → TestPyPI. Verify with
   `uv tool install --index https://test.pypi.org/simple/ defendable-science`,
   then `defendable-science --version` and `dsci doctor`.
7. Tag `v0.2.0` and publish the GitHub Release. This fires both the PyPI publish
   and the docs publish.
8. Locally: `mv ~/Projects/PhD/honest-scholar ~/Projects/PhD/defendable-science`
   and `git remote set-url origin`. Set the repo's social preview image from
   `assets/social-preview.svg`.

## Verification

The residue gate proves the strings changed. It does not prove the artifacts
work. After the release:

1. `/plugin marketplace add ./ && /plugin install defendable-science@defendable-science`
2. Run one skill end-to-end that shells out through `ensure-tooling` —
   `literature` is the cheapest — and confirm the bootstrap resolves the new
   PyPI name and records `.defendable-science/config.yml` with
   `tooling: { cli: defendable-science, version: 0.2.0 }`.
3. Confirm `https://defendable.science/` serves the built site and the README
   badges resolve.

## Consequences and accepted costs

- **The old PyPI name is abandoned with no forwarding release.** Anyone who ran
  `uv tool install honest-scholar` is stranded at `0.1.1` with no in-band signal
  that the project moved. Mitigated only by the ADR, the CHANGELOG, and the
  GitHub redirect. The package has been on PyPI for nine days (`0.1.0`
  2026-07-19, `0.1.1` 2026-07-21), so that population is very likely zero — but
  this is a real cost, not a free rename.
- **Existing consumer repos break.** `.honest-scholar/config.yml`,
  `HONEST_SCHOLAR_KEYS_PATH`, and the installed plugin name all change with no
  compatibility shim. The ADR must give the manual migration steps.
- **ADRs 0001–0034 are rewritten to the new name.** This trades some historical
  fidelity for a repo that reads as one coherent artifact. ADR-0035 is the
  single place that records the former name and the reason for the move.
- **Two of the three names this rename depends on were unowned when it was
  designed.** `defendable-science` on PyPI/TestPyPI was never reserved, and
  `defendable.science` was believed registered but was not (see cutover steps 0
  and 0b). Neither is recoverable if claimed by someone else, and no amount of
  code review would have surfaced either — they are facts about the world, not
  the repo. Verify both are held before any of the mechanical work starts.
- **`dsci` reads adjacently to "data science."** Accepted: it is short,
  pronounceable, and unclaimed, and the primary command is always the unambiguous
  `defendable-science`.

<p align="right"><img src="../../../assets/qed-endmark.svg" alt="QED" width="22"></p>
