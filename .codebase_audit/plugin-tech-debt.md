# The plugin — technical debt

The plugin is the **primary deliverable** and is invisible to every tool in the package's
CI: ruff, mypy, bandit and pytest never open it, and `tools/validate-plugin.sh` reads
only two JSON manifests. 11 skills (2,955 markdown lines), 26 `resources/` files, a
design record, 41 ADRs, and two `.claude-plugin/` manifests.

**Headline.** The prose discipline is genuinely strong — the exploration→resolution
firewall holds in all 11 skills, failure honesty is enforced explicitly and repeatedly,
and all 41 ADRs are indexed with a `Status` line. Almost every finding below is **drift
between the markdown and reality**, and one of them ships broken today.

---

## Priority index

| # | Finding | Severity |
|---|---|---|
| PL-1 | The bootstrap pins a package version that has never been released | **High** |
| PL-2 | The pin is never passed to any install command, and there is no upgrade path | **High** |
| PL-3 | Domain-neutrality violations: the author's own research domain ships as the canonical example | **Medium** |
| PL-4 | `STATUS.md` advertises the former project name and a two-release-old version | **Medium** |
| PL-5 | ADR hygiene: a dangling reference to an ADR that does not exist, and six unrecorded material decisions | **Medium** |
| PL-6 | `bump-version.yml` prints release instructions that publish nothing | **Medium** |
| PL-7 | Design record contradicts shipped decisions and lists resolved open items | **Medium** |
| PL-8 | Duplication across skills, with one copy already drifted | **Low** |
| PL-9 | Skill structure is inconsistent in five specific ways | **Low** |
| PL-10 | `CHANGELOG.md` is missing two released versions; `CITATION.cff` has drifted | **Low** |

Skill↔CLI drift is reported from the CLI side in
[`api-tech-debt.md`](api-tech-debt.md) API-2/API-3; the plugin-side view is PL-11 at the
end.

---

## High

### PL-1 — The bootstrap pins a package version that has never been released

`resources/ensure-tooling.md:26` pins the install to:

```
`defendable-science>=0.3.0,<0.4.0` — the minimum package version this plugin
release requires, up to the next incompatible boundary
```

But `defendable-science/pyproject.toml:7` reads `version = "0.2.2"`, the newest git tag
is `v0.2.2` (`git tag --list` → `v0.0.0a0, v0.1.0, v0.2.0, v0.2.1, v0.2.1rc0,
v0.2.1rc1, v0.2.2`), and `.claude-plugin/plugin.json:3` is `0.2.2`. **0.3.0 does not
exist on PyPI.**

The file knows. `resources/ensure-tooling.md:73` calls it "that same **unreleased**
`0.3.0` line". `RELEASING.md:87` says to raise the floor when a skill starts calling a
CLI capability an earlier release did not have — which is correct policy, and was
followed ahead of the release rather than with it.

The consequence is not theoretical: a consumer who installs the plugin today and lets a
skill run the documented bootstrap gets a PyPI resolution failure on step 3. The
git-subdirectory fallback (`resources/ensure-tooling.md:37`) would rescue it, but only
if the agent reads past the failure to find it, and the fallback is framed as being for
"an unreleased `<ref>`, or PyPI unreachable" rather than for this.

**Nothing checks it.** Not `tools/validate-plugin.sh` (JSON manifests only), not the
test suite, not any workflow. The pin is a string in a markdown file that no code reads.

**Fix** — release 0.3.0, or lower the floor to `>=0.2.2,<0.3.0` until it lands; then add
the guard. The test is in [`api-tech-debt.md`](api-tech-debt.md) API-6 and is ~15 lines.

Related: the pin's own explanation enumerates
`digest extract axes | record | sample | render`
(`resources/ensure-tooling.md:72`) and omits `cells`, which
`skills/defend/SKILL.md:134` and `skills/digest/SKILL.md:512` now depend on.

---

### PL-2 — The pin is never applied, and there is no upgrade path

Two defects in the same file, both arguably worse than the version number.

**The constraint never reaches a command.** Every literal install line is bare:

`resources/ensure-tooling.md:28`
```
   - `uv tool install defendable-science` — installs Python + deps in an isolated tool
     env; or run ad hoc with `uvx defendable-science …` (no persistent install).
   - else `pipx install defendable-science`.
   - else `python3 -m venv "$XDG_STATE_HOME/defendable-science/venv-<ref>"` (fallback:
     `~/.local/state/defendable-science/…`) then that venv's `pip install defendable-science`.
```

The version constraint exists only in the surrounding prose at `:26`. An agent executing
the procedure literally installs **whatever is latest**, which is precisely what the
compat pin exists to prevent. Every one of those three lines should read
`'defendable-science>=0.3.0,<0.4.0'`.

**There is no upgrade path.** Step 1 says:

`resources/ensure-tooling.md:16`
```
1. **Fast path.** If a recorded invocation exists (`.defendable-science/config.yml →
   tooling.cli`) or `defendable-science` is on `PATH`, run `defendable-science --version`. If it matches
   the pinned version → **done**.
```

The pin is a *range*, so "matches" has no defined rule. And there is no stated action on
a mismatch — the procedure simply falls through to step 3's bare `uv tool install`,
which is a **no-op** against an already-installed older version (`uv` needs
`--force`, or `uv tool upgrade`). So a consumer with 0.2.0 installed runs the bootstrap,
gets no error, and continues with a CLI that lacks the verbs the skill is about to call.

ADR-0026 line 35 promises the bootstrap "installs/**upgrades**". `ensure-tooling.md`
never upgrades. This is a **failure-honesty violation in the one document whose entire
job is honest bootstrapping** — the stale CLI is kept silently, and the first symptom is
an unrelated-looking "no such command" three steps later.

**Fix** — define the comparison and the action:

```markdown
1. **Fast path.** Run `defendable-science --version`. If the version **satisfies the
   pinned range** below → done. If it is **below the floor**, go to step 3 and install
   with `--force` (`uv tool install --force`, `pipx install --force`,
   `pip install --upgrade`) — a bare install is a no-op on an existing tool env and
   would silently leave the old CLI in place. If it is **at or above the ceiling**,
   stop and say so: this plugin release does not know that CLI's output contract, and
   guessing is the one thing it must not do.
```

**Credit where due** — the other failure modes in this file are handled well and should
not be touched: no network / no toolchain → "**Honest stop.** … Never fake tooling
output" (`resources/ensure-tooling.md:50`); environment mutation requires consent and
forbids a silent `curl … | sh` (`:45`); PyPI unreachable → the git-subdirectory fallback
(`:37`); and isolation from the consumer's ML environment is stated and reasoned
(`:56`).

---

## Medium

### PL-3 — Domain-neutrality violations

`CLAUDE.md:66` forbids ML-, monotonic-network- and consumer-repo-specific assumptions in
plugin content. All of the following are in shipped `skills/` or `resources/`.

**The author's own domain (monotonic networks) as the canonical example:**

- `skills/digest/SKILL.md:257` — the worked extraction example is
  `"citekey": "sill1997monotonic"`, `"value": "architectural — monotone by
  construction"`, axis `"partial monotonicity"`, justification `"scoped to
  fully-monotone inputs"`. A consumer in clinical research or economics reads their
  tool's reference example as a monotonic-network survey.
- `skills/progress/SKILL.md:83` — `id: 2026-07-17-monotone-depth`, duplicated verbatim
  at `resources/templates/README.md:85`.
- `skills/paper-exploration/SKILL.md:78` — "The construction that gave monotonicity in
  domain A — does it transfer to domain B?"
- `skills/literature/SKILL.md:82` — "anchor = the group's ICML'23 paper → … snippet
  reads *'unlike [anchor], our method needs no lattice'*". Both `ICML` and `lattice` are
  the author's exact context.
- `skills/research-init/SKILL.md:170` and `:227` — "a monotonic-network repo is only one
  example consumer" and "*(Example: in a monotonic-network repo, the foundational paper
  is the anchor…)*". Self-aware hedging, but it still ships the domain as *the*
  illustration.
- `skills/paper-exploration/SKILL.md:185` — the guardrail itself reads "No
  **monotonic-network** or ML assumptions live here", naming the author's domain inside
  the rule forbidding it. Should read "no domain-specific assumptions".

**ML jargon used as if universal:**

- `skills/hypothesis-testing/SKILL.md:70` — the single worked strategy example is
  "pruning to 50% sparsity doesn't hurt accuracy … pruned vs. dense test accuracy". A
  clinical or economics user has no anchor for the shape of a strategy.
- `skills/paper-synthesis/SKILL.md:103` ("on tabular benchmarks") and `:132` ("the two
  in-distribution benchmarks tested, not out-of-distribution"), mirrored into
  `resources/templates/paper/ledger.md:34` and `:57` — so the *template* a consumer
  fills in carries it.
- `resources/contracts/experiment-backend.md:66` and `:68` — "GPU fan-out", "a `doit` +
  GPU-pool executor". Contract-level, so every consumer reads it.
- `skills/dataset/SKILL.md:45` and `:60` — "a venue (e.g. NeurIPS D&B)" as the only
  venue named.

**Personal identifiers:** `skills/progress/SKILL.md:90` and
`resources/templates/README.md:92` both ship `signed-off-by: "D. Runje"` as the example
value. (No hardcoded filesystem paths or emails elsewhere in `skills/`/`resources/`;
`marketplace.json`'s owner email is a legitimate manifest field.)

**Maintainer convention leaking into consumer skills:**
`skills/hypothesis-testing/SKILL.md:179` and `skills/paper-synthesis/SKILL.md:185` both
instruct **"Follow-ups become issues, not TODOs — … captured as a self-contained GitHub
issue"**. That is `CLAUDE.md`'s house standard for *this* repository; it assumes the
consumer uses GitHub Issues, and it appears in only 2 of the 11 skills.

**Fix** — a domain-neutrality pass replacing each example with a neutral one (the
`digest` and `hypothesis-testing` examples are the two a new user hits first), plus a
grep guard in the same test file as API-3:

```python
_LEAKED = re.compile(r"\b(monoton\w*|ICML|NeurIPS|lattice|GPU|sparsity|D\. Runje)\b", re.I)


@pytest.mark.parametrize("doc", [*ROOT.glob("skills/*/SKILL.md"), *ROOT.glob("resources/**/*.md")])
def test_plugin_content_is_domain_neutral(doc):
    """CLAUDE.md forbids the author's own domain in shipped plugin content.

    `test_plugin_content.py` guards one hard-coded path this way already; the
    domain-neutrality rule is the other half of the same promise.
    """
```
with an allow-list for the places that legitimately name a domain to disclaim it.

---

### PL-4 — `STATUS.md` advertises the former project name and a two-release-old version

`README.md:42` sends readers to `STATUS.md` for "the current ledger". Its entire
"Released" section is pre-rename:

`STATUS.md:39`
```markdown
- **`v0.1.0` — first final** (2026-07-19). The plugin (10 skills) and the
  `honest-scholar` CLI are published: the package is on **PyPI**
  (`uv tool install honest-scholar`), the `v0.1.0` tag doubles as the plugin's
  marketplace pin, and the docs are live at
  [honest-scholar.science](https://honest-scholar.science/).
```

The project was renamed by ADR-0035; the current release is `v0.2.2`; the docs are at
`defendable.science`. A reader following that `uv tool install honest-scholar` installs
the wrong package or nothing.

The same file contradicts itself on the skill count: `STATUS.md:15` says "**All 11
skills**", `STATUS.md:39` says "(10 skills)".

`STATUS.md:22` also under-reports the CLI — it lists `literature`, `dataset`,
`defend record`, `backlog` and `doctor`, omitting `init`, `check`, `progress dashboard`,
`keys` and the whole `digest` group, all of which ship.

---

### PL-5 — ADR hygiene

**(a) The index is complete and the status discipline is real.** All 41 ADRs (0001–0041)
are indexed in `decisions/README.md:15-55` with no gaps and no orphan files, and every
ADR carries `- Status: accepted · Date: … · Deciders: …` on line 3. This is the
strongest single artifact in the repository and is genuinely unusual.

**(b) No ADR is superseded-in-fact but unmarked.** ADR-0035 renamed the project, and the
old name survives only inside ADR-0035 itself and two `docs/superpowers/` design records
— a correct historical record. `decisions/0019-public-plugin-visibility.md:1` already
reads "named `defendable-science`". The one soft issue:
`decisions/0001-separate-plugin-repo.md:1` still titles itself "not in-mononet",
accurate as history but the only ADR title carrying a consumer repo name.

**(c) A dangling reference to an ADR that does not exist.** `decisions/0031` cites a
Pydantic-rejecting ADR as an authority:

`decisions/0031-config-driven-cache-dir.md:31`
```markdown
- No new dependency (stdlib + the existing `pyyaml`-backed `load_config`); no
  Pydantic (ADR rejecting it stands).
```

**There is no such ADR.** Grepping the full set returns no ADR whose subject is
Pydantic, dependencies, or the light-wheel posture. The prohibition lives in exactly one
place — `CLAUDE.md:64` — and is a *contributor-guidance* file that `CLAUDE.md:14`
itself says "is **not** a shipped artifact". Three ADRs and two design proposals cite it
secondhand as though it were a decision record:

| Location | Text |
|---|---|
| `CLAUDE.md:64` | "**Pydantic is deliberately rejected** (keep the wheel light, no Rust-binary conflicts) — do not reintroduce it" |
| `decisions/0031-config-driven-cache-dir.md:32` | "no Pydantic (**ADR rejecting it stands**)" ← the dangling reference |
| `decisions/0029-api-key-handling.md:84` | "Implementation stays light-dep (stdlib JSON + a small loader); no Pydantic, no dotenv dependency." |
| `decisions/0038-venue-resolvers-trusted-not-gated.md:76` | "a new dependency (the package deliberately stays light: `requests`, `pooch`, `pyyaml`, no Pydantic)" |
| `docs/design/proposals/dataset-manifest-tooling.md:46` | "No new heavy deps (no `jsonschema`, no `pydantic`, no `datasets`); validation is hand-rolled" |
| `docs/design/proposals/dataset-manifest-tooling.md:129` | "**Deps:** `pyyaml` + stdlib `json` only. No `jsonschema`, no `pydantic`" |
| `defendable-science/defendable_science/check/model.py:18` | "Stdlib only — ``dataclasses``, not ``pydantic``." |
| `defendable-science/defendable_science/progress/model.py:13` | "Stdlib only — ``dataclasses``, not ``pydantic``." |
| `defendable-science/defendable_science/core/gitignore.py:20` | "CLAUDE.md's light-wheel constraint is about not adding new *runtime dependencies* (**that is why Pydantic was rejected**)" |

Plus five `docs/superpowers/plans/*.md` restatements — `2026-07-27-digest-skill-plan.md:14`,
`2026-07-28-defendable-science-rename.md:17`, `2026-08-27-literature-asset-acquisition.md:19`,
`2026-08-27-scaffold-check-layout.md:18`, `2026-08-28-digest-extraction-mode.md:19`.

**Fourteen restatements of a rule that no ADR ever established** — and CLAUDE.md's own
convention (`CLAUDE.md:62`) is that
"material design decisions → a MADR ADR". A dependency-posture rule cited by three ADRs
is material by any reading.

**This is the finding, and it is independent of whether the rule is right.** A governing
constraint that lives only in contributor guidance, is cited secondhand as an ADR, and
has no context/drivers/options/rejected-alternatives record, cannot be revisited on the
evidence — which is exactly what an ADR set exists to make possible. The repo owner has
now sanctioned Pydantic at the external-input parsing boundary; the reconciliation of
`CLAUDE.md:64` and the eight in-repo restatements is **tracked in #169** and has not
landed, so every citation above is reported as found on `main`.

For the record, the two halves of the original rationale, verified against this repo:

- *"No Rust-binary conflicts"* — **does not apply.** The CLI is installed **isolated**
  from the consumer's environment: `resources/ensure-tooling.md:56` — "the install lives
  in a `uv`/`pipx` tool env or a per-user state venv — never the consumer repo's project
  env. This is what lets `defendable-science` depend freely on `typer` / `requests` /
  `pyyaml` / `pooch` without touching anyone's torch/jax install." A `pydantic-core`
  wheel in an isolated tool env cannot conflict with anything.
- *"Keep the wheel light"* — **already breached by an existing dependency.** `pyyaml`
  ships a compiled C extension (`_yaml`, confirmed: `yaml.CSafeLoader` is present and
  `_yaml` resolves to a built module in this venv) at **3.1 MB installed** — larger than
  `rich` at 2.7 MB. And `typer` 0.27 pulls `rich` → `markdown-it-py` → `mdurl` +
  `pygments`, plus `shellingham` and `annotated-doc`; `pooch` pulls `platformdirs`,
  `packaging` and `requests`. The four "exactly" runtime dependencies resolve to
  fourteen packages. Pydantic v2 adds `pydantic-core` (~1.8 MB per platform wheel) and
  `annotated-types`. The real tradeoff is **one more compiled wheel and a wider
  build/platform matrix, against deleting six hand-rolled parsers of untrusted input
  that currently produce four tracebacks and one silently wrong value** (BE-4). On this
  evidence the tradeoff favours adopting it at the parsing boundary, which is what the
  owner decided.

**(d) The "every material decision gets an ADR" claim does not hold.** Six material,
cross-cutting decisions with no ADR:

| Decision | Where it lives | ADR |
|---|---|---|
| The JSON envelope + exit-code taxonomy | `cli.py:895` (the only written statement), `skills/digest/SKILL.md:207` | **none** — ADR-0024 mentions neither JSON nor exit codes |
| The `check` severity model (`invalid`/`unreadable`/`gap`, exit keyed to severity not count) | `check/model.py:3`, skill-facing at `skills/research-init/SKILL.md:158` | **none** |
| The atomic write-temp-then-rename idiom | `literature/registry.py:740`, `:817`, `core/http.py:173` | **none** — and it recently produced a bug (`0489114`) |
| Proactive per-host rate limiting, and `RateLimitError` distinct from a 404 | `core/http.py:5`, `:53`, `:244` | **none** |
| The `DocstringTyper` help-text convention | `cli.py:120`, guarded by `tests/test_cli_help.py` | **none** |
| `--root` discovery vs. explicit root | `core/config.py:17`, `:61` | **partial** — ADR-0039 covers the `layout:` block but contains no `--root` reference |

*Has an ADR, correctly:* the `max(3, 10%)` sampling rule
(`decisions/0040-digest-extraction-mode.md:150`), including its "convention rather than
a statistical guarantee" caveat.

The pattern is clean: **methodology decisions get ADRs; CLI-contract decisions do not.**
Every gap is package-side. The first two are the ones the skills actually depend on and
would most reward writing up — the JSON envelope in particular, because
[`api-tech-debt.md`](api-tech-debt.md) API-1 shows five incompatible conventions
accreted in its absence, with nothing forcing a decision about whether changing an older
one was allowed.

---

### PL-6 — `bump-version.yml` prints release instructions that publish nothing

`.github/workflows/bump-version.yml:74` (in the PR body it opens) and `:95` (in the job
summary) both tell the maintainer:

```
git tag v${version} && git push origin v${version}   # → publish.yml → PyPI
```

`publish.yml:10` triggers on `release: [published]` and `workflow_dispatch` — **not** on
a tag push. `RELEASING.md:72` says so explicitly: *"Don't push a bare `v*` tag — the
trigger is the **Release**, not the tag."*

So the release automation's own output contradicts the release runbook, and following it
silently publishes nothing — the failure is an absence, which is the hardest kind to
notice.

**Fix**: replace both strings with the `gh release create` invocation from
`RELEASING.md:60`.

---

### PL-7 — Design record contradicts shipped decisions and lists resolved open items

**`docs/design/00-meta-spec.md`** — the file `CLAUDE.md:18` says to read first:

- `:455` — the plugin/consumer table says "**the 7 skills**". There are 11, and the tree
  66 lines above at `:378` correctly lists all 11. Internally contradictory.
- `:348` — open item "*whether the thesis defensibility gate is made blocking*".
  **Resolved by ADR-0021** (non-blocking, per-gap sign-off), which
  `docs/design/01-lifecycle.md:212` correctly marks resolved.
- `:558` — open item "`.defendable-science/` vs existing conventions — confirm the config
  directory name". Settled by ADR-0035 and shipped everywhere.
- `:560` — open item "Thesis milestone schema … resolve in sub-spec 1".
  `resources/templates/thesis/milestones.yml` ships, and is guarded by
  `tests/test_render.py:147`.
- `:498` — "four sub-specs (each date-prefixed under `docs/superpowers/specs/`)". They
  live at `docs/design/01-04`.
- `:432` — the paper tree omits `pitch.md` and `plan.md`, both present at
  `skills/research-init/SKILL.md:106`.
- `:371` — "Working name `defendable-science`". Not a working name since ADR-0035.

**`docs/design/01-lifecycle.md`** — header `:5` correctly reads "Status: Implemented",
but `## 10. Open items` (`:210-221`) lists three items that shipped: the design/plan
delegation seam (ADR-0023 + `resources/contracts/engineering.md`), the Toulmin ledger
format (`resources/templates/paper/ledger.md` + `skills/paper-synthesis/SKILL.md:90`),
and the status-frontmatter schema (`skills/progress/SKILL.md:80`). Only the ADR-0021
item is marked resolved. Sub-specs 02/03/04 are correctly headed.

**`docs/design/proposals/`** — 7 of 9 correctly marked `Status: implemented`. Two
problems, one of which is a direct contradiction:

- `docs/design/proposals/tooling-package.md:17` and `:104` describe the package as "a
  monorepo, **co-versioned** with the plugin". That is precisely what **ADR-0026
  rejected** (`decisions/0026-independent-versioning-compat-pin.md:51`, "Locked versions
  — forces no-op bumps"). The proposal predates the ADR by one day and was never
  corrected — in a document headed `Status: implemented`. Since plugin and package are
  *numerically identical* at `0.2.2` today, a reader has no external signal that the
  proposal is wrong.
- `docs/design/proposals/docs-site.md:3` — `Status: designed 2026-07-19`, but ADR-0030
  is accepted, `.github/workflows/docs-publish.yml` exists, and the site is live.
- Stale interim paragraphs survive inside implemented proposals:
  `docs/design/proposals/defend-record-helper.md:8` still says "the skill … marks it
  unimplemented. **Interim (until the module is implemented):**"; same at
  `docs/design/proposals/exploration-backlog-helper.md:8`.

The nine invocation-level staleness items in these same proposals are in
[`api-tech-debt.md`](api-tech-debt.md) API-12.

---

## Low

### PL-8 — Duplication across skills and `resources/`

| Duplicated block | Locations | Drifted? |
|---|---|---|
| Status-frontmatter YAML (19 lines) | `skills/progress/SKILL.md:80-98` ⇄ `resources/templates/README.md:82-100` | **No — byte-identical.** But only one copy is guarded: `tests/test_status.py:179` pins the README copy. The skill copy is unguarded and will drift on the next schema change. |
| Concept-matrix shape rules | `skills/literature/SKILL.md:120-139` ⇄ `skills/digest/SKILL.md:225-240` | **Yes.** `literature` lists 5 rules; `digest`'s refusal list at `:236` adds "a missing `\|---\|` separator", "ragged rows" and "an unnamed column". A matrix author reading only `literature` does not know all the refusals — and `_checked_axes` (`digest/extraction.py:132`) enforces the longer list. |
| `check` reporting paragraph | `skills/research-init/SKILL.md:156-162` ⇄ `:254-260` | No — verbatim, within one file, 100 lines apart. |
| `defend`↔`digest` cross-reference essay | `skills/defend/SKILL.md:161-182` ⇄ `skills/digest/SKILL.md:508-521` ⇄ ADR-0040 | Partially — three copies of one rationale. |
| Commit-attribution ritual (7 lines) | all 11 skills (`hypothesis-exploration:190` … `digest:585`) | No — identical modulo the skill name, and each already links `resources/commit-attribution.md`. |
| "Follow-ups become issues" guardrail | `hypothesis-testing:179` ⇄ `paper-synthesis:185` | No — identical, but in only 2 of 11 (and see PL-3). |

**Should become `resources/` includes:** the status-frontmatter block (one canonical
copy, with `tests/test_status.py`'s guard extended to it); the concept-matrix shape
rules (two copies already disagree); and the `check` paragraph deduped within
`research-init`.

**Done well, and worth naming:** `ensure-tooling` is **never** inlined. All eight call
sites are links — `hypothesis-exploration:69`, `paper-exploration:57`, `defend:75` and
`:135`, `digest:193`, `literature:279`, `dataset:112` and `:165`, `research-init:52`.
That is exactly right. **One gap:** `skills/progress/SKILL.md:46` tells the agent to run
`defendable-science check` and `progress dashboard` but never references
`ensure-tooling` — the only CLI-invoking skill without a bootstrap link. (`thesis`
invokes no CLI, so its omission is correct.)

---

### PL-9 — Skill structure is inconsistent

All 11 SKILL.md files use exactly `name` + `description` frontmatter, and every `name`
matches its directory. That part is clean. Five inconsistencies:

| Skill | H1 | Verb-surface section | Guardrails | Composition |
|---|---|---|---|---|
| hypothesis-exploration | ✗ | `## Verbs` :33 | :167 | :145 |
| hypothesis-testing | ✓ :6 | `## Staged documents` :41 | :162 | :145 |
| paper-exploration | ✗ | `## Verbs` :39 | :164 | :148 |
| paper-synthesis | ✗ | `## Staged documents` :28 | :159 | :139 |
| thesis | ✗ | `## Modes` :37 | :147 | :130 |
| progress | ✗ | `## Verbs` :42 | :212 | **✗** |
| defend | ✗ | `## Targets` :110 | **`## Hard constraints` :256** | **✗** |
| digest | ✗ | `## Two modes…` :22 | :550 | :523 |
| literature | ✗ | `## Modes` :39 | :252 | :234 |
| dataset | ✓ :11 | `## Verbs` :50 | :193 | :178 |
| research-init | ✓ :6 | `## Modes` :36 | :282 | :262 |

1. **H1 in only 3 of 11**, and `skills/dataset/SKILL.md:11` is lowercase `# dataset`
   while the other two are Title Case.
2. **`defend` alone names its guardrail section `## Hard constraints`**
   (`skills/defend/SKILL.md:256`) — same content, different heading, on the one section
   a reader most needs to find by name.
3. **`progress` and `defend` have no `## Composition`**, despite being the two most
   cross-cutting skills.
4. **The verb surface is named four ways** — `Verbs` ×4, `Modes` ×4, `Staged documents`
   ×2, `Targets` ×1 — and only `skills/defend/SKILL.md:193` has an `## Invocation`
   section; the other ten fold it into When-to-use.
5. **The tooling callout alternates form**: a blockquote in
   `hypothesis-exploration:67`, `paper-exploration:54`, `defend:74`, `dataset:110`; a
   real `## Tooling` heading in `literature:275`.

**On `digest` at 593 lines vs `thesis` at 177**: mostly justified — ~340 lines
(`skills/digest/SKILL.md:186-521`) are extraction mode, four CLI verbs with a report and
refusal taxonomy each. Two chunks are genuine bloat: `:225-240` re-specifies matrix
rules `skills/literature/SKILL.md:120` already owns (PL-8), and `:161-182` is ADR
reasoning duplicated from ADR-0040. `thesis` at 177 is correctly short — it is a partial
mirror (`skills/thesis/SKILL.md:13`) with less machinery. The gap is a complexity gap,
not a quality gap.

**The firewall itself is not a finding — it holds.** Checked across all six named
skills. `skills/hypothesis-exploration/SKILL.md` does rank (`:116`), the closest thing
to adjudication, and fences it three times: "advisory inputs to the human's ordering,
not an automatic gate" (`:118`), "recommends; it does not select the testing slate"
(`:141`), "Ranking advises, never selects… Do not auto-promote the top row" (`:183`).
`skills/paper-exploration/SKILL.md:41` puts a **Firewall column in the verb table**, with
`promote` the only row marked "human disposes". `hypothesis-testing:36` and
`paper-synthesis:24` each explicitly refuse the generate side. `progress` never scores —
`skills/progress/SKILL.md:191` is an Anti-Goodhart section with an explicit
do-not-compute list at `:203` and, at `:227`, "If a future request asks for a
percentage… decline and point here — this is a design invariant, not a missing
feature." `defend` never supplies the answer (`skills/defend/SKILL.md:59`; the
`grill-me` inverted-epistemics contrast at `:263` is the sharpest statement of it in the
repo).

One **disclosed weakening** worth naming, which is not a violation: in `digest`
extraction mode the agent authors the claim — it reads papers and writes matrix cells
(`skills/digest/SKILL.md:245-340`) that `render` merges into the author's positioning
document (`:413`), backed only by a `max(3, 10%)` human sample. The skill confronts this
head-on rather than hiding it: `:32` "Extraction does **not** certify comprehension";
`:342` "if the agent also checked the sample, extraction would certify **nothing**";
`:371` the sample size "is a **convention, not a statistical guarantee**". That is the
honest handling of an inherently weaker guarantee and is the best-written passage in the
plugin.

---

### PL-10 — `CHANGELOG.md` is missing two released versions; `CITATION.cff` has drifted

- `CHANGELOG.md` headings are `[Unreleased]` (`:12`), `[0.2.0]` (`:341`), `[0.1.1]`,
  `[0.1.0]`. **`0.2.1` and `0.2.2` are missing entirely**, despite both tags existing and
  `pyproject.toml:7` reading `0.2.2`. `publish.yml:34` guards tag↔version but not
  tag↔changelog, which is how both shipped with no entry. The honest former-name note at
  `CHANGELOG.md:8` is good practice and should stay.
- `CITATION.cff:19` reads `version: 0.2.0` against a package at `0.2.2`. ADR-0026 lines
  46-47 explicitly flag this as manual and required-at-release; it has drifted two
  patches.
- `README.md:133` — "To pin a fixed release, add `"ref": "v0.2.0"`". Latest tag is
  `v0.2.2`.

---

### PL-11 — Skill↔CLI drift, from the plugin's side

Four documented invocations do not run; full analysis and fixes in
[`api-tech-debt.md`](api-tech-debt.md) API-2. From the plugin's perspective the
important one is `skills/hypothesis-exploration/SKILL.md:56`, because it is the only
break inside a `skills/` file and it instructs the author to hand-build a backlog table
with a column name (`one-line hypothesis`) that `Backlog._require`
(`exploration/backlog.py:303`) then permanently refuses.

The reason none of this is caught: `tests/test_plugin_content.py` is the only test that
opens a SKILL.md, it asserts one hard-coded string, and it **deliberately skips fenced
code blocks** (`tests/test_plugin_content.py:70`) — which is where every invocation
lives. `.pre-commit-config.yaml:69` scopes the plugin hook to
`files: ^\.claude-plugin/.*\.json$`, so editing a skill triggers only whitespace and
codespell.

---

## Packaging and the two-artifact rule — verified clean

Plugin version `0.2.2` (`.claude-plugin/plugin.json:3`); package version `0.2.2`
(`defendable-science/pyproject.toml:7`). Numerically identical, which is not itself a
violation but means nothing would visibly break if they *were* being locked.

**The automation respects ADR-0026, verified in the code and not just the comments.**
`tools/bump_version.py:28` targets only `_ROOT / "defendable-science" / "pyproject.toml"`
and `:133` writes only that file. No workflow or script touches `plugin.json` —
confirmed by grep across `.github/`. The intent is documented three times
(`tools/bump_version.py:15`, `.github/workflows/bump-version.yml:7`, `:69`). Clean.

**Trigger → effect:**

| Workflow | Trigger | Effect |
|---|---|---|
| `ci.yml` | push→main, every PR, merge_group | `pre-commit` (all hooks, `--hook-stage manual`); `test` matrix py3.11–3.14 → ruff + mypy + pytest with the 100 % gate, Codecov on 3.13 only; `plugin-validate`; `check` alls-green aggregator (`:77`) |
| `bump-version.yml` | `workflow_dispatch` only | Runs `tools/bump_version.py`, edits **pyproject only**, opens a `release:` PR via `RELEASE_PAT` |
| `publish.yml` | `release: published`; `workflow_dispatch` | Guard: release tag must equal pyproject version (`:34`, refuses otherwise); `uv build`; OIDC Trusted Publishing to TestPyPI or PyPI |
| `docs-publish.yml` | `release: published`; `workflow_dispatch`; PR on paths incl. `skills/**`, `decisions/**`, `docs/**` | PR → strict build + `mint validate` + `mint broken-links`, no push. Release → build, validate, push to the docs repo, then poll the live site and 404-check every nav URL (`:203`) plus lychee internal links |
| `live-validation.yml` | `workflow_dispatch`; **weekly cron Mon 06:00 UTC** | Installs rclone, runs `DEFENDABLE_SCIENCE_LIVE=1 pytest -m live --no-cov` against real OpenAlex/S2 |

`publish.yml`'s tag↔version guard and `docs-publish.yml`'s live-404 sweep are both
notably careful.

**CI gaps.** `tools/validate-plugin.sh` runs unconditionally in CI (`ci.yml:68`) but is
nearly a no-op there: `claude` is not installed in that job, so it always takes the
structural fallback, which checks only that the two JSON files parse and carry a handful
of keys. It never opens `skills/`. Nothing validates SKILL.md frontmatter — a malformed
`name`, a name/directory mismatch, or a missing `description` passes every gate. The
only real skill-content gate is `docs-publish.yml`'s PR job (`mint validate` +
`mint broken-links`), whose path filter lists `resources/references/**` but **not**
`resources/templates/`, `resources/rigor/`, `resources/contracts/` or
`resources/ensure-tooling.md` — so a PR touching only the bootstrap file skips it
entirely. And **nothing checks plugin↔package compatibility**, which is exactly how PL-1
shipped.

---

## Positive patterns to preserve

1. **The ADR set is the best artifact in the repository.** 41 ADRs, a complete index
   (`decisions/README.md:15`), a `Status`/`Date`/`Deciders` line on every one, and real
   *rejected alternatives* sections — `decisions/0026:51` explains why locked versions
   were rejected, `decisions/0038:74` why PDF-text verification was rejected as
   disproportionate. For a single-maintainer repo with no second reviewer this is the
   compensating control, and it works.

2. **The exploration→resolution firewall is maintained in prose, not just claimed.** See
   PL-9. `skills/paper-exploration/SKILL.md:41`'s Firewall column and
   `skills/progress/SKILL.md:227`'s "decline and point here — this is a design
   invariant, not a missing feature" are the two mechanisms doing the most work.

3. **Failure honesty is written into the skills, not only the code.**
   `resources/ensure-tooling.md:50` ("Never fake tooling output"),
   `skills/digest/SKILL.md:207` (parse defensively rather than assuming JSON on every
   non-zero exit), `skills/digest/SKILL.md:32`/`:342`/`:371` (extraction certifies less
   than comprehension, and says so three times).

4. **`ensure-tooling` is linked, never inlined** — 8 of 8 call sites (PL-8). The one
   piece of duplication that would matter most is the one that was avoided.

5. **Consent and honest-stop are first-class in the bootstrap.**
   `resources/ensure-tooling.md:45` forbids a silent `curl … | sh` and requires the
   user's confirmation before mutating their environment. Rare, and correct.

6. **Templates are guarded against renderer drift.** `tests/test_status.py:121`
   parametrises over all nine shipped `resources/templates/**.md` and asserts each
   status block byte-matches `scaffold/status.render()`; `:179` pins
   `templates/README.md`'s field set and order; `:204` pins that no machine-read field
   ships a placeholder; `tests/test_render.py:147` pins `milestones.yml`. This is the
   pattern the skill copies (PL-8) and the CLI invocations (PL-11) still need.

7. **The plugin/consumer boundary is stated and mostly held.**
   `docs/design/00-meta-spec.md:455`'s table (skill-count error aside) draws the line
   clearly, and `resources/ensure-tooling.md:56` explains the isolation property that
   makes it work.

---

*Cross-references: [`api-tech-debt.md`](api-tech-debt.md) API-2/3/6/12 for the
invocation and pin drift; [`coverage.md`](coverage.md) §10 for what
`tools/validate-plugin.sh` does and does not check; [`be-tech-debt.md`](be-tech-debt.md)
BE-4/BE-9 for the parsing debt the Pydantic decision addresses.*
