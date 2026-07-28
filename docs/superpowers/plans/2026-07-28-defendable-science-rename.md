# Defendable Science Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename every identifier of both shipped artifacts from `honest-scholar` to `defendable-science`, leaving no residue outside the historical record, with the full test/lint/docs gate green.

**Architecture:** A reviewed one-shot `perl` sweep script performs the mechanical substitution across 115 tracked text files using ordered rules; two `git mv`s relocate the package directory and Python module; four categories of content the script cannot produce (version bumps, a new ADR, the CHANGELOG entry, prose passes) are hand-written; a residue gate plus the existing 100%-coverage suite, strict mypy, and a strict docs build prove the result.

**Tech Stack:** Bash + Perl (sweep), `uv` + pytest + mypy + ruff (package gate), pre-commit, Mintlify docs builder (`tools/build_docs_site.py`), MADR (ADRs), Keep a Changelog.

## Global Constraints

- **Spec of record:** `docs/superpowers/specs/2026-07-28-defendable-science-rename-design.md` (commit `5f483ac`). Its naming map is authoritative; nothing else is.
- **Branch:** `feat/rename-defendable-science`. **Never commit to `main`** — it is protected.
- **Commit authorship:** author `Davor Runje <davor@synthpop.ai>`, with trailer `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`. Commits are SSH-signed via Secretive and may require a Touch ID prompt; if signing fails with "agent refused operation", the human must run the commit from an interactive terminal.
- **Coverage gate is hard:** `fail_under = 100` (statement + branch). Never lower it, never add a blanket `# pragma: no cover`.
- **Pydantic is rejected** — do not introduce it.
- **Versions:** plugin `0.1.0` → `0.2.0`; package `0.1.1` → `0.2.0`. Coincidental alignment only — do **not** couple them (ADR-0026).
- **The word *honest* is vocabulary, not only a name.** "failure honesty", "honest stop", "an honest ledger", the `honest AI use` CITATION keyword, and `fix/rate-limit-honesty` all stay. Only the product *name* moves. No rule matches bare `honest`.
- **Four files quote the old name deliberately** and must survive verbatim: `CHANGELOG.md` (the `0.1.0`/`0.1.1` entries), `decisions/0035-rename-to-defendable-science.md`, the spec above, and this plan.
- **Do not touch the `honest-scholar.science` Cloudflare zone.** It serves the live docs and is the only possible 301 source for URLs frozen in the published `0.1.0`/`0.1.1` PyPI metadata.
- **Cutover steps 0 and 0b (PyPI name reservation, domain registration) are out of scope for this plan.** They are human dashboard actions in the spec. The domain is done; the PyPI name is **not yet reserved**.

---

### Task 1: Write and dry-run the sweep script

The script is the change. It gets its own review gate before a single file is rewritten. This task also corrects two defects found in the spec after it was committed.

**Files:**
- Create: `tools/rename-sweep.sh`
- Modify: `docs/superpowers/specs/2026-07-28-defendable-science-rename-design.md:96-105` (rule list), `:169-170` (residue-gate regex)

**Interfaces:**
- Consumes: nothing.
- Produces: `tools/rename-sweep.sh`, invoked as `./tools/rename-sweep.sh --dry-run` (prints file count and per-rule occurrence counts, changes nothing) or `./tools/rename-sweep.sh --apply` (rewrites files in place). Task 2 calls `--apply`. Task 7 deletes the script.

**Spec defect being corrected here.** Shields.io escapes a literal hyphen by doubling it, so two badges contain `honest--scholar`:

```
README.md:12       https://img.shields.io/badge/docs-honest--scholar.science-2a1cc8...
DISCLOSURE.md:66   https://img.shields.io/badge/AI%20use-disclosed%20with%20honest--scholar-f9463c...
```

Neither the spec's rules nor its residue gate (`honest[-_. ]?scholar` — `?` allows only **one** separator) matches `honest--scholar`. Both would survive silently in the project's two most visible badges. The rule list below adds two targeted rules, and the gate regex changes `?` to `*`.

These two need *different* replacements: the README badge is the **domain** (`honest-scholar.science` → `defendable.science`, which loses its hyphen entirely), while the DISCLOSURE badge is the **name** (→ `defendable--science`, which shields.io renders as `defendable-science`).

- [ ] **Step 1: Write the sweep script**

Create `tools/rename-sweep.sh`:

```bash
#!/usr/bin/env bash
# One-shot rename sweep: honest-scholar -> defendable-science.
#
# Deleted in the final commit of the rename PR; it exists so the mechanical
# transformation is auditable in review rather than a 115-file mystery diff.
# Spec: docs/superpowers/specs/2026-07-28-defendable-science-rename-design.md
#
#   ./tools/rename-sweep.sh --dry-run   # report only, change nothing
#   ./tools/rename-sweep.sh --apply     # rewrite in place
set -euo pipefail

MODE="${1:-}"
case "$MODE" in
  --dry-run|--apply) ;;
  *) echo "usage: $0 --dry-run|--apply" >&2; exit 2 ;;
esac

cd "$(git rev-parse --show-toplevel)"

# Files that deliberately quote the old name and must survive verbatim, plus
# the lockfile (regenerated by `uv lock`, never patched). This script must
# also exclude itself: its own substitution rules below contain the search
# strings, so `git grep` would otherwise select this file too.
EXCLUDE_RE='^(honest-scholar/uv\.lock|docs/superpowers/specs/2026-07-28-defendable-science-rename-design\.md|docs/superpowers/plans/2026-07-28-defendable-science-rename\.md|tools/rename-sweep\.sh)$'

# Tracked, text (-I skips binaries), and actually containing a match.
# NOTE: git grep -E does NOT support \b (verified on this repo), so the
# selection pattern uses bare `hsch`. That is a deliberate superset -- the
# word-boundary constraint is enforced by the perl rule below, and selecting an
# extra file that contains no real match is harmless (perl rewrites nothing).
FILES=$(git grep -lIiE 'honest[-_. ]*scholar|hsch' | grep -vE "$EXCLUDE_RE" || true)

if [ -z "$FILES" ]; then
  echo "no matching files -- nothing to do"; exit 0
fi

echo "files in scope: $(printf '%s\n' "$FILES" | wc -l | tr -d ' ')"

if [ "$MODE" = "--dry-run" ]; then
  echo "--- occurrences per rule (before) ---"
  for r in 'honest-scholar-docs' 'honest--scholar\.science' 'honest-scholar\.science' \
           'honest--scholar' 'HONEST_SCHOLAR' 'HonestScholar' 'Honest Scholar' \
           'honest_scholar' 'honest-scholar'; do
    n=$(printf '%s\n' "$FILES" | tr '\n' '\0' | xargs -0 grep -ohE "$r" 2>/dev/null | wc -l | tr -d ' ')
    printf '  %-26s %s\n' "$r" "$n"
  done
  n=$(printf '%s\n' "$FILES" | tr '\n' '\0' \
      | xargs -0 perl -ne 'print "x\n" while /\bhsch\b/g' 2>/dev/null | wc -l | tr -d ' ')
  printf '  %-26s %s\n' '\bhsch\b' "$n"
  echo "(dry run -- nothing written)"
  exit 0
fi

# Order is load-bearing:
#   * the two `.science` rules must precede the bare name rules, else the
#     domain becomes defendable-science.science / defendable--science.science;
#   * honest--scholar (shields.io escaped hyphen) must precede honest-scholar.
# Rule 1 is redundant with the bare rule but is listed to make the docs-repo
# rename explicit. Perl runs in byte mode: non-ASCII passes through untouched.
printf '%s\n' "$FILES" | tr '\n' '\0' | xargs -0 perl -pi -e '
  s/honest-scholar-docs/defendable-science-docs/g;
  s/honest--scholar\.science/defendable.science/g;
  s/honest-scholar\.science/defendable.science/g;
  s/honest--scholar/defendable--science/g;
  s/HONEST_SCHOLAR/DEFENDABLE_SCIENCE/g;
  s/HonestScholar/DefendableScience/g;
  s/Honest Scholar/Defendable Science/g;
  s/honest_scholar/defendable_science/g;
  s/honest-scholar/defendable-science/g;
  s/\bhsch\b/dsci/g;
'

echo "sweep applied to $(printf '%s\n' "$FILES" | wc -l | tr -d ' ') files"
```

- [ ] **Step 2: Make it executable and dry-run it**

```bash
chmod +x tools/rename-sweep.sh
./tools/rename-sweep.sh --dry-run
```

Expected output — these counts are measured from the tree at commit `5f483ac`:

```
files in scope: 115
--- occurrences per rule (before) ---
  honest-scholar-docs        9
  honest--scholar\.science   1
  honest-scholar\.science    24
  honest--scholar            2
  HONEST_SCHOLAR             20
  HonestScholar              15
  Honest Scholar             24
  honest_scholar             133
  honest-scholar             701
  \bhsch\b                   3
(dry run -- nothing written)
```

Counts overlap by design: the 701 `honest-scholar` total includes the 9 `-docs` and 24 `.science` occurrences, which earlier rules consume first, leaving 668 for the bare rule. Likewise `honest--scholar` (2) includes the 1 `.science` badge.

If `files in scope` is not 115, **stop** — the tree has drifted from the spec and the plan's assertions no longer hold.

- [ ] **Step 3: Verify nothing was written**

```bash
git status --porcelain
```

Expected: only `?? tools/rename-sweep.sh`. If any tracked file shows as modified, the dry-run path is broken — fix before proceeding.

- [ ] **Step 4: Correct the spec's rule list**

In `docs/superpowers/specs/2026-07-28-defendable-science-rename-design.md`, replace the fenced rule block (lines 96–105) with:

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

Then replace the paragraph immediately above it (lines 90–94) with:

```markdown
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

- [ ] **Step 5: Correct the spec's residue gate**

In the same file, change the residue-gate command (lines ~169-170) from `honest[-_. ]?scholar` to `honest[-_. ]*scholar`:

```bash
grep -rniE 'honest[-_. ]*scholar|\bhsch\b' \
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=.worktrees .
```

Add this sentence directly beneath that code block:

```markdown
The `*` (not `?`) is deliberate: `?` allows only one separator character and
would silently miss the shields.io `honest--scholar` badge form.
```

- [ ] **Step 6: Verify the corrected gate catches the badge form**

```bash
printf 'honest--scholar\n' | grep -iE 'honest[-_. ]*scholar' && echo CAUGHT
```

Expected: prints `honest--scholar` then `CAUGHT`.

- [ ] **Step 7: Commit**

```bash
git add tools/rename-sweep.sh docs/superpowers/specs/2026-07-28-defendable-science-rename-design.md
git commit -F- <<'EOF'
build(rename): add the one-shot sweep script and fix two spec defects

The script performs the mechanical honest-scholar -> defendable-science
substitution with ordered rules, so the transformation is reviewable on its
own before any file is rewritten. Deleted again in the final commit of this PR.

Corrects the spec: shields.io escapes hyphens by doubling them, so README.md
and DISCLOSURE.md contain `honest--scholar` in badge URLs. Neither the spec's
rules nor its residue gate (`honest[-_. ]?scholar` -- one optional separator)
matched that form; both badges would have survived the rename silently. Adds
two targeted rules and widens the gate to `honest[-_. ]*scholar`.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 2: Execute the sweep, move the directories, get the suite green

**Files:**
- Modify: 115 tracked text files (mechanical)
- Move: `honest-scholar/` → `defendable-science/`; `defendable-science/honest_scholar/` → `defendable-science/defendable_science/`
- Regenerate: `defendable-science/uv.lock`

**Interfaces:**
- Consumes: `tools/rename-sweep.sh --apply` from Task 1.
- Produces: the package importable as `defendable_science`, console scripts `defendable-science` and `dsci`, project config dir `.defendable-science/`, env vars `DEFENDABLE_SCIENCE_LIVE` / `DEFENDABLE_SCIENCE_KEYS_PATH`, and `defendable_science.core.keys.STORE_PATH_ENV == "DEFENDABLE_SCIENCE_KEYS_PATH"`. Tasks 3–7 build on this tree.

- [ ] **Step 1: Confirm the suite is green before touching anything**

```bash
cd "$(git rev-parse --show-toplevel)/honest-scholar"
uv sync
uv run pytest -q
```

Expected: all tests pass, coverage 100%. If it is red now, **stop** — fix or report first; a rename must not be blamed for a pre-existing failure.

- [ ] **Step 2: Apply the sweep**

```bash
cd "$(git rev-parse --show-toplevel)"
./tools/rename-sweep.sh --apply
```

Expected: `sweep applied to 115 files`.

- [ ] **Step 3: Move the package directory and the module**

```bash
git mv honest-scholar defendable-science
git mv defendable-science/honest_scholar defendable-science/defendable_science
```

- [ ] **Step 4: Regenerate the lockfile**

The lockfile was excluded from the sweep because it must be regenerated, not patched — its content hashes would otherwise be wrong.

```bash
cd defendable-science
uv lock
grep -n 'name = "defendable-science"' uv.lock
```

Expected: the grep prints a match. If it still says `honest-scholar`, `pyproject.toml`'s `[project] name` did not get rewritten — investigate before continuing.

- [ ] **Step 5: Run the test suite against the renamed module**

```bash
uv sync
uv run pytest -q
```

Expected: all tests pass **and** the coverage report header reads `defendable_science`, not `honest_scholar`. A stale `--cov=honest_scholar` in `pyproject.toml` measures a module that no longer exists, reports 0%, and would fail `fail_under = 100` — if you see 0% or "module not imported", that is the cause.

- [ ] **Step 6: Verify the console scripts resolve**

```bash
uv run defendable-science --version
uv run dsci --version
```

Expected: both print the same version string (still `0.1.1` at this point — Task 3 bumps it).

- [ ] **Step 7: Run the residue gate**

```bash
cd "$(git rev-parse --show-toplevel)"
grep -rniE 'honest[-_. ]*scholar|\bhsch\b' \
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=.worktrees . \
  | grep -vE '^(\./)?(CHANGELOG\.md|docs/superpowers/(specs|plans)/2026-07-28-defendable-science-rename)' \
  || echo "CLEAN"
```

Expected: `CLEAN`. Any other line is a miss — fix it by hand and re-run. `decisions/0035-*.md` does not exist yet (Task 4), so it is not in the filter above.

- [ ] **Step 8: Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
git add -A
git commit -F- <<'EOF'
refactor(rename)!: honest-scholar -> defendable-science across both artifacts

Mechanical sweep (tools/rename-sweep.sh) over 115 tracked files, plus:
  git mv honest-scholar defendable-science
  git mv .../honest_scholar .../defendable_science
  uv lock (regenerated, not patched)

Renames the Python module, console scripts (defendable-science + dsci), the
.defendable-science/ project config dir, DEFENDABLE_SCIENCE_* env vars, the
DefendableScience-Skill: commit trailer, the plugin and marketplace names, and
the docs home at defendable.science.

BREAKING CHANGE: consumers must rename .honest-scholar/ and HONEST_SCHOLAR_*
by hand, and reinstall the plugin under its new name. Version bumps, the ADR,
the CHANGELOG entry, and the prose passes land in following commits.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 3: Bump both artifact versions

The sweep moves names, never numbers. `tools/bump_version.py` only edits the pyproject, so the other two are manual.

**Files:**
- Modify: `.claude-plugin/plugin.json:3`, `defendable-science/pyproject.toml` (`[project] version`), `CITATION.cff:19`

**Interfaces:**
- Consumes: the renamed tree from Task 2.
- Produces: version `0.2.0` in all three files. Task 5's CHANGELOG entry and Task 7's release notes reference it.

- [ ] **Step 1: Bump the plugin**

In `.claude-plugin/plugin.json` line 3, change `"version": "0.1.0",` to `"version": "0.2.0",`.

- [ ] **Step 2: Bump the package**

In `defendable-science/pyproject.toml`, change `version = "0.1.1"` to `version = "0.2.0"`.

- [ ] **Step 3: Bump the citation metadata**

In `CITATION.cff` line 19, change `version: 0.1.1` to `version: 0.2.0`.

- [ ] **Step 4: Verify all three agree**

```bash
cd "$(git rev-parse --show-toplevel)"
grep -h '"version"' .claude-plugin/plugin.json
grep -h '^version' defendable-science/pyproject.toml CITATION.cff
```

Expected: `0.2.0` three times, no `0.1.0` or `0.1.1`.

- [ ] **Step 5: Confirm the pin in ensure-tooling matches**

The sweep rewrote the distribution name in the compat pin but not its bounds. The plugin must require the version that first carries the new name.

```bash
grep -n 'defendable-science>=' resources/ensure-tooling.md
```

If it reads `>=0.1.0,<0.2.0`, change **every** occurrence to `>=0.2.0,<0.3.0`. Expected afterwards: all matches read `defendable-science>=0.2.0,<0.3.0`.

- [ ] **Step 6: Commit**

```bash
git add .claude-plugin/plugin.json defendable-science/pyproject.toml CITATION.cff resources/ensure-tooling.md
git commit -F- <<'EOF'
chore(release): plugin and package to 0.2.0, pin >=0.2.0,<0.3.0

The rename is breaking, so a minor bump under 0.x is the honest signal and the
numbers stay monotone with the CHANGELOG. The alignment is coincidental --
plugin and package continue to version independently (ADR-0026).

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 4: Write ADR-0035 and index it

**Files:**
- Create: `decisions/0035-rename-to-defendable-science.md`
- Modify: `decisions/README.md` (append a row to the table, above the trailing `Format:` line)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the single document recording the former name. Task 6's residue-gate filter and Task 7's final gate both allowlist this path.

- [ ] **Step 1: Write the ADR**

Create `decisions/0035-rename-to-defendable-science.md`:

```markdown
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
```

- [ ] **Step 2: Add the index row**

In `decisions/README.md`, insert this row immediately after the `0034` row and before the blank line preceding `Format: MADR ...`:

```markdown
| [0035](0035-rename-to-defendable-science.md) | Rename the project to Defendable Science — repo, plugin, distribution, CLI, config dir, env vars, and docs domain; old PyPI packages dropped | accepted |
```

- [ ] **Step 3: Verify the link resolves and the table is well-formed**

```bash
cd "$(git rev-parse --show-toplevel)"
test -f decisions/0035-rename-to-defendable-science.md && echo "ADR exists"
grep -c '^| \[' decisions/README.md
tail -3 decisions/README.md
```

Expected: `ADR exists`; the row count increases by exactly 1 versus `git show HEAD:decisions/README.md | grep -c '^| \['`; and the `Format: MADR ...` line is still last.

- [ ] **Step 4: Commit**

```bash
git add decisions/0035-rename-to-defendable-science.md decisions/README.md
git commit -F- <<'EOF'
docs(adr): ADR-0035 record the rename to Defendable Science

Context, drivers, the four options considered, and the consequences --
including the abandoned PyPI distributions, the hand-migration steps for
existing consumer repos, and the two names that were unsecured when the rename
was designed.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 5: Add the CHANGELOG entry

**Files:**
- Modify: `CHANGELOG.md` (insert beneath `## [Unreleased]` at line 8; add a former-name note near the top)

**Interfaces:**
- Consumes: version `0.2.0` from Task 3, ADR-0035 from Task 4.
- Produces: the consumer-facing migration record. Task 7's release notes quote it.

- [ ] **Step 1: Add the former-name note**

In `CHANGELOG.md`, immediately after the "and this project adheres to Semantic Versioning" line (line 6) and before `## [Unreleased]`, insert:

```markdown

> **Former name.** Entries before `0.2.0` refer to this project under its
> previous name, `honest-scholar`. Those releases really did ship under that
> name and are left unedited (ADR-0035).
```

- [ ] **Step 2: Add the 0.2.0 entry**

Immediately after `## [Unreleased]`, insert:

```markdown

## [0.2.0] - 2026-07-28

**The project is renamed from Honest Scholar to Defendable Science** (ADR-0035).
The name now describes what the tool verifies — that the work can be defended —
rather than a virtue it cannot audit. This is a breaking change for every
consumer.

### Changed — BREAKING

- **Plugin install**: `/plugin install honest-scholar@honest-scholar` →
  `/plugin install defendable-science@defendable-science`
- **CLI**: `honest-scholar` → `defendable-science`; short alias `hsch` → `dsci`
- **PyPI distribution**: `honest-scholar` → `defendable-science`.
  `uv tool uninstall honest-scholar && uv tool install defendable-science`
- **Python module**: `honest_scholar` → `defendable_science`
- **Project config dir**: `.honest-scholar/` → `.defendable-science/`
  (rename it by hand; also update your `.gitignore`)
- **Environment variables**: `HONEST_SCHOLAR_KEYS_PATH` →
  `DEFENDABLE_SCIENCE_KEYS_PATH`, `HONEST_SCHOLAR_LIVE` →
  `DEFENDABLE_SCIENCE_LIVE`
- **Commit trailer**: `HonestScholar-Skill:` → `DefendableScience-Skill:`
- **Docs**: `honest-scholar.science` → `defendable.science`
- **Repository**: `davorrunje/honest-scholar` →
  `davorrunje/defendable-science` (GitHub redirects the old URLs)

### Removed

- The `honest-scholar` PyPI and TestPyPI distributions are **abandoned with no
  forwarding release**. `0.1.1` remains their final version. There is no
  deprecation shim; migrate with the steps above.
```

- [ ] **Step 3: Verify the old entries are untouched**

```bash
cd "$(git rev-parse --show-toplevel)"
grep -n "honest-scholar" CHANGELOG.md
```

Expected: matches appear **only** inside the former-name note, the `0.2.0`
migration bullets, and the pre-existing `0.1.1` / `0.1.0` sections. The `0.1.1`
section must still read `honest-scholar.science/get-started/user-guide` and
`the honest-scholar CLI` verbatim — if the sweep rewrote those, restore them
with `git show 5f483ac:CHANGELOG.md`.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -F- <<'EOF'
docs(changelog): 0.2.0 -- the rename, with consumer migration steps

Lists every renamed surface a consumer touches and states plainly that the old
PyPI distributions are abandoned with no forwarding release. The 0.1.0 and
0.1.1 entries keep the old name verbatim: those releases shipped under it.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 6: Prose passes where substitution reads badly

The sweep produces grammatical but sometimes awkward text. These files are read by humans first and need a hand.

**Files:**
- Modify: `README.md`, `defendable-science/README.md`, `docs/USER-GUIDE.md`, `STATUS.md`, `DISCLOSURE.md`, `CITATION.cff`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `CLAUDE.md`, `docs/design/proposals/tooling-package.md`

**Interfaces:**
- Consumes: the swept tree from Task 2.
- Produces: no code interface. Task 7 gates on the docs build, which renders `README.md`, `DISCLOSURE.md`, and `docs/USER-GUIDE.md`.

- [ ] **Step 1: Fix the two shields.io badges**

Verify the sweep's rules 2 and 4 produced the right result — these are the ones the original spec would have missed.

```bash
cd "$(git rev-parse --show-toplevel)"
grep -n "img.shields.io" README.md DISCLOSURE.md
```

Expected: `README.md` contains `badge/docs-defendable.science-2a1cc8` (**not**
`defendable--science.science`), and `DISCLOSURE.md` contains
`disclosed%20with%20defendable--science` (the doubled hyphen is correct here —
shields.io renders it as a single hyphen). Fix by hand if either is wrong.

- [ ] **Step 2: Fix the stale skill count in `STATUS.md`**

`digest` (#68) made eleven skills; the file still says ten. Change:

```
- **All 10 skills** authored and reviewed (`skills/*/SKILL.md`, each with valid
  `name`/`description` frontmatter): `research-init`, `hypothesis-exploration`,
```

to:

```
- **All 11 skills** authored and reviewed (`skills/*/SKILL.md`, each with valid
  `name`/`description` frontmatter): `research-init`, `hypothesis-exploration`,
```

and add `digest` to that list after `defend`. Then check the rest of the file for other "10 skills" phrasing:

```bash
grep -n "10 skills\|ten skills" STATUS.md README.md docs/USER-GUIDE.md
```

Expected afterwards: no matches.

- [ ] **Step 3: Rewrite the `DISCLOSURE.md` prose**

The sweep turns "Honest Scholar" into "Defendable Science" mechanically, which mostly works, but three spots need judgement. Verify and adjust:

- Line 1 heading should read `# Disclosing AI use — and citing Defendable Science`.
- The "Not a seal of honesty" bullet must still make sense: it should read
  "**Not a seal of honesty.** Defendable Science does not certify that your
  research is honest…". Keep the word *honesty* in the bullet label — it is the
  claim being disclaimed, not the product name.
- The BibTeX `title` field should read:
  `{defendable-science: a research-workflow plugin for honest, defensible AI-assisted research}`.
  Keep "honest, defensible" — that is the description of the research, not the
  product name.

- [ ] **Step 4: Rewrite the package README opening**

`defendable-science/README.md` becomes the PyPI long description. Its first paragraph after the sweep reads "**Defendable Science** helps you keep research honest…", which is correct and should stay — the tool does help keep research honest. Verify the *self-reference* line reads:

```markdown
This package is the **CLI / tooling** behind the
[`defendable-science` Claude Code plugin](https://github.com/davorrunje/defendable-science).
```

and that the sentence naming the command reads "provides the `defendable-science` command it calls".

- [ ] **Step 5: Check the remaining prose files**

For each, read the name-bearing sentences and confirm they read naturally:

```bash
cd "$(git rev-parse --show-toplevel)"
grep -n "Defendable Science\|defendable-science" README.md docs/USER-GUIDE.md CLAUDE.md \
  CITATION.cff .claude-plugin/plugin.json .claude-plugin/marketplace.json | head -40
```

Specifically confirm:
- `README.md` banner alt text is `alt="Defendable Science"`.
- `docs/USER-GUIDE.md` line 5 comment reads `<!-- defendable-science user guide -->`.
- `.claude-plugin/marketplace.json` description reads
  `"defendable-science — the scientist's research-workflow plugin for Claude Code."`.
- `CITATION.cff` `title:` reads `defendable-science` and the `message:` field
  names Defendable Science.

- [ ] **Step 6: Qualify the name-reservation claim**

`docs/design/proposals/tooling-package.md` now asserts the `defendable-science`
name "is reserved on both PyPI and TestPyPI (pre-release `0.0.0a0` published)".
That is not yet true — it is cutover step 0. Change that bullet to:

```markdown
- **Names claimed:** distribution `defendable-science`, CLI `defendable-science`
  (+ short alias `dsci`); the name must be reserved on both PyPI and TestPyPI by
  publishing a `0.0.0a0` pre-release before the first real release (cutover
  step 0 in the rename spec).
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -F- <<'EOF'
docs(rename): prose passes where substitution read badly

Hand-edits the files a human reads first: both shields.io badges (the escaped
honest--scholar form), the package README that becomes the PyPI long
description, DISCLOSURE.md's heading and BibTeX title, the user guide, and the
plugin/marketplace descriptions. Also fixes STATUS.md's stale "All 10 skills"
-- digest (#68) made eleven -- and qualifies the tooling-package claim that the
new distribution name is already reserved, which it is not yet.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 7: Full gate, remove the sweep script, open the PR

**Files:**
- Delete: `tools/rename-sweep.sh`

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces: a PR ready for review. Cutover steps 0–8 in the spec follow it and are human actions.

- [ ] **Step 1: Package gate**

```bash
cd "$(git rev-parse --show-toplevel)/defendable-science"
uv run pytest -q
uv run mypy
uv run ruff check
uv run ruff format --check
```

Expected: tests pass with **100%** coverage reported against `defendable_science`; mypy clean (it also type-checks `../tools`); ruff clean.

- [ ] **Step 2: Repo gate**

```bash
cd "$(git rev-parse --show-toplevel)"
pre-commit run --all-files
./tools/validate-plugin.sh
```

Expected: both pass. If pre-commit fails on the lockfile, confirm both `.pre-commit-config.yaml` references now read `defendable-science/uv.lock`:

```bash
grep -n "uv.lock" .pre-commit-config.yaml
```

- [ ] **Step 3: Docs build — the only check that proves the Typer app still imports**

```bash
cd "$(git rev-parse --show-toplevel)"
uv run --project defendable-science python tools/build_docs_site.py --out /tmp/docs-site
```

Expected: exits 0 and prints `built defendable-science docs site → /tmp/docs-site`. A failure here almost certainly means `tools/build_docs_site.py`'s `from defendable_science.cli import app` cannot resolve.

- [ ] **Step 4: Confirm the generated CLI reference uses the new command name**

```bash
grep -rc "defendable-science" /tmp/docs-site/ | head -5
grep -rn "honest-scholar\|honest_scholar" /tmp/docs-site/ || echo "CLEAN"
```

Expected: `CLEAN` — no old name anywhere in the generated site.

- [ ] **Step 5: Verify the release-critical workflow paths**

No local gate executes the GitHub workflows, so a wrong path here stays invisible
until a release fails. Check each by eye.

```bash
cd "$(git rev-parse --show-toplevel)"
grep -n "defendable-science\|defendable_science\|defendable\.science" \
  .github/workflows/ci.yml \
  .github/workflows/publish.yml \
  .github/workflows/docs-publish.yml \
  .github/workflows/bump-version.yml \
  .github/workflows/live-validation.yml \
  .github/actions/report-published/action.yml \
  tools/bump_version.py tools/lint.sh tools/typecheck.sh \
  codecov.yml .gitignore
```

Confirm specifically:

- `ci.yml` — every `--project defendable-science` and
  `working-directory: defendable-science`; `files: defendable-science/coverage.xml`
- `publish.yml` — the version-guard reads
  `grep -m1 '^version' defendable-science/pyproject.toml`; `working-directory:
  defendable-science`; `path: defendable-science/dist/`
- `docs-publish.yml` — `--project defendable-science`; docs-repo checkout is
  `repository: davorrunje/defendable-science-docs`; `SITE:
  https://defendable.science`; the `llms.txt` host regex and the lychee
  `--include` pattern both read `defendable\.science`; the bot's
  `git config user.name "defendable-science docs bot"`
- `bump-version.yml` + `tools/bump_version.py` — the pyproject path and the
  release-PR title/body strings
- `live-validation.yml` — `DEFENDABLE_SCIENCE_LIVE: "1"`
- `tools/lint.sh`, `tools/typecheck.sh` — the `cd` target
- `.gitignore` — all three `.defendable-science/` entries

A miss in `publish.yml`'s version guard is the worst case: it would refuse to
publish, or publish the wrong version.

- [ ] **Step 6: Final residue gate**

```bash
cd "$(git rev-parse --show-toplevel)"
grep -rniE 'honest[-_. ]*scholar|\bhsch\b' \
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=.worktrees . \
  | grep -vE '^(\./)?(CHANGELOG\.md|decisions/0035-rename-to-defendable-science\.md|docs/superpowers/(specs|plans)/2026-07-28-defendable-science-rename)' \
  || echo "CLEAN"
```

Expected: `CLEAN`. Anything else fails the change.

- [ ] **Step 7: Remove the sweep script**

It has done its job and is visible in this PR's history.

```bash
git rm tools/rename-sweep.sh
git commit -F- <<'EOF'
build(rename): remove the one-shot sweep script

Its purpose was reviewability of the mechanical substitution; that review is
preserved in this PR's commit history. Keeping a single-use rename script in
tools/ would be dead weight.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

- [ ] **Step 8: Re-run the fast gate after the deletion**

Removing a file from `tools/` can affect mypy's `../tools` include and pre-commit's file list.

```bash
cd defendable-science && uv run mypy && cd ..
pre-commit run --all-files
```

Expected: both clean.

- [ ] **Step 9: Push and open the PR**

Use the repo's `create-pr` skill (`.claude/skills/create-pr/SKILL.md`), which encodes the house branch/commit/checks/body ritual. The PR body must state:

- that this is a **breaking** rename, both artifacts to `0.2.0`;
- the consumer migration steps (copy from the CHANGELOG `0.2.0` entry);
- a link to ADR-0035 and to the spec;
- **that cutover steps 0–4 in the spec are prerequisites for merge**: reserve
  `defendable-science` on PyPI and TestPyPI, rename both GitHub repos, register
  the trusted publishers, and get `defendable.science` serving. Step 0 is
  unrecoverable if someone else takes the name; step 4 will fail the release's
  `live-link-check` job if the domain is not live.

```bash
git push -u origin feat/rename-defendable-science
```

---

## Out of scope — human cutover actions

These are in the spec, not this plan, and cannot be done by an implementing agent:

| Step | Action | Status |
|---|---|---|
| 0 | Reserve `defendable-science` on PyPI + TestPyPI (`0.0.0a0`) | **not done — the one unrecoverable risk** |
| 0b | Register `defendable.science` | ✅ done 2026-07-28 (Cloudflare) |
| 1 | `gh repo rename defendable-science` | not done |
| 2 | Rename docs repo; re-verify Mintlify's GitHub connection | not done |
| 3 | Register trusted publishers for the new distribution | not done |
| 4 | DNS + Mintlify custom domain; must be *serving* before tagging | not done |
| 5–8 | Merge, TestPyPI dry run, tag `v0.2.0`, local dir rename + social preview | not done |
