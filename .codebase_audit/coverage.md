# Coverage

## The measured result

```
$ cd defendable-science && uv run pytest -q
1562 passed, 14 skipped in 16.36s

TOTAL   4976 stmts   0 miss   1498 branch   0 partial   100%
Required test coverage of 100.0% reached. Total coverage: 100.00%
```

100.00 % statement **and** branch, across all 41 modules, no exceptions and no `omit`.
`fail_under = 100` (`defendable-science/pyproject.toml:113`) with `--cov-branch`
(`:106`). Also clean: `uv run mypy` (79 files, `strict = true`), `uv run ruff check`,
`uv run bandit -r defendable_science/` (2 Low, both correct uses of `random`).

Corrections to the baseline metrics I was given: source is **17,081 LOC across 41 files**
(not 15,930/29 — the earlier count appears to exclude `__init__.py` files and predates
`cli.py` reaching 3,537 and `checks.py` reaching 2,136); tests are **21,833 LOC across
36 files** (not 20,285/29); `check/checks.py` is 2,136 (not 1,511),
`tests/test_check.py` is 2,528 (not 1,698), and there is a
`tests/test_digest_cli.py` at 1,338 that the baseline list omits. There are 42 files in
`decisions/` — 41 ADRs plus the index. Skills total 2,955 markdown lines, not 2,881.

## Why this document is not a table of percentages

Grouping modules by coverage would print `100%` forty-one times. The gate makes line
and branch coverage true by construction, so the only useful question is **what a 100 %
branch gate structurally cannot catch**, and whether the assertions behind those covered
lines are load-bearing.

Short answer, evidenced below: **this is not coverage theatre.** A hand-built mutation
spot-check killed 7/7 non-equivalent mutants. Fakes are conformance-pinned against their
real counterparts. Error branches routinely assert message *text*, not just an exception
type. The real gaps are concentrated in five places — adversarial parser input,
external-service contract realism, cross-process concurrency, test-suite structure, and
the plugin.

---

## 1. Strongly tested

No material gap found in: `core/fixity.py`, `core/download.py`, `core/mirror.py`,
`literature/registry.py`, `dataset/manifest.py` (shape errors), `check/model.py`,
`check/checks.py`, `check/probe.py`, all four `digest/` modules, all three `progress/`
modules, all four `scaffold/` modules, `exploration/backlog.py`.

Three things deserve specific credit because they are rare at any scale:

- **`tests/test_check.py:251` — `test_the_fake_probe_models_the_real_one`.** Pins
  `FakeProbe` against the real `FsProbe` on a real filesystem across `glob`, `exists`,
  `is_dir` and empty directories. This converts "we tested against a fake" from an
  assumption into a *checked* claim, and roughly 150 downstream check/progress tests
  inherit the guarantee. Almost no codebase does this.
- **`tests/test_sampling.py:79` — `test_select_sample_is_stable_across_processes`.**
  Spawns two interpreters with different `PYTHONHASHSEED` and compares the draws. The
  determinism of `select_sample` is what stops a researcher re-rolling until an easy
  sample comes up (`cli.py:3243`), and a same-process test cannot establish it.
- **`tests/test_digest_cli.py:1294`.** An AST-level assertion that `write_extraction`
  has exactly one call site, inside `validate`'s loop — testing a structural invariant
  ("validation and writing are one action", `cli.py:2869`) rather than a behaviour.

The atomic-write testing is also genuinely strong, and recent (`0489114`, #144): both
failure modes of `patch_asset`/`patch_triage` are tested with an orphan-`.tmp` assertion
*and* a byte-identical-original assertion at `tests/test_lit_registry.py:341`, `:483`,
`:502`, `:518`, `:559`, `:625`, `:712`. Mid-stream body death with a real
`requests.exceptions.ChunkedEncodingError`, asserting the partial file was removed:
`tests/test_download.py:225`; disk-full at `:251`. Partial-scaffold recovery:
`tests/test_cli_commands.py:928` and `tests/test_backlog.py:806`.

---

## 2. Weakly tested — code executed, weakly asserted

| Module / site | Gap |
|---|---|
| `core/http.py:345` | The `except requests.RequestException` retry branch is `# pragma: no cover - network`. `grep RequestException tests/` → **zero hits**. The session is a constructor parameter and `FakeSession` (`tests/test_literature.py:41`) could reach it in three lines. This is the most operationally common HTTP failure (DNS, reset, read timeout) and the branch where a transport failure must set `rate_limited = False` and still consume a retry — i.e. exactly where a connection reset could be mistyped as a throttle. |
| `dataset/retrieval.py:111` | `mirror.get(...) and verified(blob, ref.sha256)` — no test covers *the mirror returns True but the bytes fail SHA-256*. `MirrorHit` (`tests/test_retrieval.py:290`) always writes a correct payload. Branch coverage cannot see it because both conditions share one arc. The **literature** front-end has this exact test (`tests/test_acquire.py:1208`); the dataset one does not. |
| `defend/record.py:293-311` | The write-ordering hazard (BE-3 / DATA-1) is untested in both directions: no test makes `_append_log` fail after the artifact is patched, and no test passes a nonexistent artifact path to `record()`. |
| `digest/artifact.py:548` | Same shape, same absence. |
| `exploration/backlog.py:601-618` | `tests/test_backlog.py:143` and `:128` test each half of `scaffold_paper`; nothing composes them, so the non-retryable partial scaffold (DATA-1c) is uncovered. |
| `cli.py:1791` | `_parse_acks` silently accepts an item with no `::`, producing `{"gap": "<whole string>", "by": ""}` → outcome `acknowledged-per-gap` with **nobody named**, in a code path whose purpose is naming the human who waved a gap through. Only well-formed input is tested (`tests/test_record.py:568`). |
| `literature/graph.py:459` | `neighbors`' `capped` flag is only ever asserted `False` (`tests/test_literature.py:460`). No hermetic test drives `len(citers) >= frontier` to assert `capped is True` — and `capped` exists specifically so truncation is never silent. Single assignment expression, so branch coverage cannot see it. |

**Pattern (a): exit-code-only assertions.** Present but inconsistent rather than
systemic — peers in the same files do assert messages. Notable instances:
`tests/test_cli_commands.py:63`, `:70`, `:154`, `:161`, `:251`;
`tests/test_acquire_cli.py:872`, `:884`, `:904`, `:919`;
`tests/test_literature.py:340`, `:489`, `:742`;
`tests/test_cache_config.py:50`, `:82`, `:129`.

The four `test_acquire_cli.py` config-validation tests are the ones that matter: those
messages *are* the actionability guarantee the CLI advertises ("the message names the
offending key"), and none of the four checks that the key is named.
`tests/test_check_cli.py:300` asserts `>= 1` on counts, so it cannot fail if
deduplication over-collapses by one.

**Pattern (b): mock-argument assertions.** Mostly *correct* uses, not smells.
`tests/test_mirror.py:46`/`:65` assert rclone's argv — for a subprocess wrapper the argv
**is** the observable output. `tests/test_cli_commands.py:91`/`:385` use spies that
delegate to the real function. One genuinely decorative pair:
`tests/test_check.py:2121` and `:2140` supply a `.gitignore` line that
`FakeProbe(gitignore={...})` overrides, so they would pass with any line — and the file
comments say so and point at `test_gitignore.py`.

**Pattern (c): over-mocking.** Essentially absent. Only five `monkeypatch.setattr` sites
across the whole check/digest/cli/progress/scaffold slice, each either wrapping the real
callee or forcing a real `OSError`.

---

## 3. Effectively untested

- **`dataset/retrieval._pooch_fetch`** (`dataset/retrieval.py:50`) — the only real
  Tier-B fetcher, `# pragma: no cover`, and `pooch` is untyped so
  `ignore_missing_imports = true` (`pyproject.toml:85`) makes its return `Any`. Neither
  the type checker nor the hermetic suite constrains it. The live suite does.
- **`core/gitignore.literal_covers`** (`core/gitignore.py:84`) — no direct test;
  exercised only incidentally as a helper inside `tests/test_check.py:226`.
- **`core/frontmatter.py`** — no dedicated test file. Covered indirectly through
  `tests/test_record.py:292-320` and `tests/test_digest_artifact.py:596-770`, which are
  good on unterminated fences and the comment round-trip refusal, but the module is a
  hand-rolled parser used by two front-ends and has no suite of its own.

---

## 4. All six `# pragma: no cover` sites, and the coverage config

Every one carries a reason comment. That is already better than most.

| Site | Code | Verdict |
|---|---|---|
| `defendable_science/__init__.py:14` | `except PackageNotFoundError:` | **Legitimate** — cannot fire when installed. |
| `defendable_science/cli.py:3536` | `if __name__ == "__main__":` | **Legitimate**; also matched by `exclude_also`, so doubly excluded. |
| `defendable_science/literature/registry.py:687` | `if not isinstance(root, yaml.MappingNode):` | **Legitimate** — `triage_mapping` already narrowed the shape, and the comment says so. |
| `defendable_science/dataset/retrieval.py:50` | `def _pooch_fetch(...)` | **Legitimate but consequential** — an injectable seam, and the live suite exercises the real one. See §5. |
| `defendable_science/cli.py:228` | `except (OSError, subprocess.SubprocessError):` in `_tool_report` | **Borderline escape hatch.** Trivially testable by monkeypatching `subprocess.run`. Low severity — diagnostic output only. |
| `defendable_science/core/http.py:345` | `except requests.RequestException as exc:` | **Escape hatch hiding a reachable branch.** The stated reason ("network") no longer holds: `session` is a constructor parameter and `FakeSession` already exists. |

**Coverage config** (`defendable-science/pyproject.toml:112-120`):

```toml
[tool.coverage.report]
fail_under = 100
show_missing = true
exclude_also = [
    "if TYPE_CHECKING:",
    "\\.\\.\\.",
    "if __name__ == .__main__.:",
    "pragma: no cover",
]
```

There is **no `omit` and no `exclude_lines`** — the whole package is measured. Judging
each pattern: `if TYPE_CHECKING:` and `if __name__ == .__main__.:` are standard and
correct. `pragma: no cover` is redundant (coverage.py excludes it by default) and
harmless. `"\\.\\.\\."` is the one worth naming: it is a regex on the *line*, intended
for `Protocol` stubs, and would equally excuse a real `...` body in shipped code.
Nothing currently abuses it. **No pattern silently excludes real code today.**

---

## 5. Live-marked tests

Two files, gated by `pytestmark` at `tests/test_live_retrieval.py:39` and
`tests/test_live_literature.py:24`. These are the 14 skipped.

**Exercised only under `DEFENDABLE_SCIENCE_LIVE=1`:**

*OpenAlex / Semantic Scholar* (`tests/test_live_literature.py`) — real `graph.resolve`
on an OpenAlex id (`:49`), an arXiv id with `vN` suffix stripping (`:56`), non-empty
`graph.refs` (`:64`), real **cursor pagination** with a cap (`:70`), `graph.neighbors`
co-citation (`:77`), keyless-S2 graceful degradation (`:83`, `:91`), and S2-keyed
enrichment plus the CorpusId→externalIds→OpenAlex resolution chain (`:101`, `:110`,
additionally gated on `S2_API_KEY`).

*pooch / rclone* (`tests/test_live_retrieval.py`) — real `pooch.retrieve` over a
localhost HTTP server (`:100`) including wrong-hash rejection (`:107`); the real
`rclone` binary against a local-filesystem alias remote: `copyto`/`lsf` round-trip
(`:116`), mirror-hit-instead-of-redownload (`:129`), audit mirror presence (`:149`). All
rclone tests skip if the binary is absent (`:47`).

**What that means for confidence — better than "skipped by default" suggests, with one
hole:**

- These are **not** developer-only. `.github/workflows/live-validation.yml:12` runs them
  on a **weekly cron (Mon 06:00 UTC)** plus `workflow_dispatch`, on ubuntu-latest with
  rclone installed and `S2_API_KEY` from secrets. Upstream drift is caught within ≤7
  days.
- They are **not a PR gate** (`ci.yml:81` requires only `pre-commit`, `test`,
  `plugin-validate`), which is correct — a PR must not fail because OpenAlex is down.
  But the workflow has **no notification or issue-filing step**, so a scheduled failure
  is a red mark on a tab nobody opens.
- **The hole: `literature/acquire.py` — 2,350 LOC, the largest literature module — has
  zero live coverage.** The live suite touches only `graph.py`. Acquire's PDF-acquisition
  ladder, its OA-location parsing, and its content-type/magic-byte logic are validated
  exclusively against three trimmed fixtures. Drift in `best_oa_location` or
  `locations[].pdf_url` would be caught by *neither* suite.

---

## 6. Integration coverage for external services

**Fixtures are real-but-trimmed, and there are only three.**
`tests/fixtures/openalex/{sill1997,monokan_journal,monokan_arxiv}.json`, 895–1,288 bytes
each. They carry genuine upstream markers (`W2293093810`, a real MAG id, a real
`papers.nips.cc` URL, `"best_oa_location": null`), so they are recorded responses
hand-reduced to the fields the code reads — a real OpenAlex work is 20–50 KB. Loaded at
`tests/test_acquire.py:368-375`, used nowhere else.

**`graph.py` — the actual OpenAlex + S2 client — has zero recorded fixtures.** It is
tested exclusively against hand-written idealised dicts: 83 `_client(...)` /
`FakeSession(...)` constructions in `tests/test_literature.py`, with inline payloads like
`{"display_name": "A Title", "publication_year": 2023, ...}`
(`tests/test_literature.py:205-211`, `:374`, `:431`, `:567`, `:588`, `:599`, `:612`,
`:634`).

Fake transports: `tests/test_literature.py:20` `FakeResponse` / `:41` `FakeSession`
(routing dict → response, records `calls`); `tests/test_download.py:16`/`:41`;
`tests/test_acquire_cli.py:39`/`:55`; `tests/test_acquire.py:575` `FakeClient`;
`tests/test_retrieval.py:42`/`:53` and `tests/test_mirror.py:16`/`:26` for rclone.

**Is upstream contract drift detectable by the hermetic suite? Structurally, no.**
`FakeSession.get` returns whatever the test registered for a URL. It validates nothing
about the outbound query and cannot know what the real endpoint returns. Nothing
re-fetches the three fixtures and diffs them against upstream, and nothing asserts the
hand-written dicts resemble a real payload. **Hand-written fixtures that can never fail
is a real finding here**, mitigated — but only for `graph.py` — by the weekly live job.

**Fix**: a `tests/fixtures/openalex/` refresh script run by the live job, which
re-fetches each recorded work and fails if a field the code reads has disappeared; plus
at least one `acquire.py` live test driving the ladder against a known open-access DOI.

---

## 7. Concurrency and robustness coverage

Replaces "missing async test coverage" — there is no async anywhere (`grep -rn
"async def\|await \|asyncio" defendable_science/` → 0; ruff's `ASYNC` rules are enabled
at `pyproject.toml:142` and clean).

**What exists** — the atomic-write and partial-write tests listed in §1, and they are
good.

**What does not:**

- **Zero cross-process concurrency tests.** No test runs two CLI invocations against one
  cache directory, one `triage.yml`, or one registry.
- **No locking exists to test.** `grep -rn
  "fcntl\|filelock\|LOCK_EX\|threading.Lock\|multiprocessing" defendable_science/` → 0
  hits. Safety rests entirely on rename atomicity, which is sufficient for the two
  content-addressed stores and **not** for the four read-modify-write files (DATA-6).
- **`literature/acquire.py:1068` and `:1099`** use a bare `src.replace(dest)` with no
  `.tmp`-cleanup wrapper and no failure test, unlike `registry.py`.
- **No `fsync` before `replace`** anywhere, so a power-loss window remains. Defensible,
  but undocumented.
- **The write-then-log ordering hazard** (BE-3, DATA-1) — three instances, none tested
  in the failing direction.

A two-process test is cheap and would pin the constraint whichever way it is resolved:

```python
def test_two_concurrent_triage_patches_do_not_lose_an_update(tmp_path):
    """`patch_triage` is read-modify-write; without a lock the second run's
    rewrite discards the first's row. Whether that is fixed or documented as a
    single-writer constraint, it should not be discovered by a researcher."""
```

---

## 8. Missing edge cases

**Property-based / fuzz testing: definitively none.** No `hypothesis` (the library) in
`pyproject.toml:47-62` or `uv.lock`, no `@given`, no `atheris`, no fuzz corpus. Every
"hypothesis" hit in the repo is the domain term. The suite is 100 %-branch-covered and
**entirely example-based**. That combination is exactly where the two verified bugs
below live.

**`core/mdtable.py`** — fence and ambiguity handling are exceptionally covered
(`tests/test_mdtable.py:200-227` fence variants, `:234-267` duplicate headings,
`:93-123` ragged rows and separators). But **a verified round-trip bug survives**:
`render_table` escapes row cells and joins the header raw
(`core/mdtable.py:446` vs `:450`), so `| a \| b | c |` parses to a 2-column header,
re-emits as `| a | b | c |`, and the next parse raises `TableError: ragged t row: 2
cells, header has 3`. Reproduced. A lossless-round-trip API silently corrupts the host
document. See DATA-5. Also untested: duplicate header columns, CRLF, empty input.

**`dataset/manifest.py`** — verified: `id: null` becomes the literal string `'None'`;
`license: [a, b]` becomes `"['a', 'b']"` via `_opt_str`'s `str(value)`
(`dataset/manifest.py:187`) and then **passes** the `if not entry.license` required-check
at `:366`; `path: ../../etc/passwd` loads with **zero validation errors**
(`_validate_files`, `:386`, checks only non-empty plus checksum shape). For a fixity
tool, unvalidated paths in a manifest is the notable one. Also untested: duplicate YAML
keys (last wins, silently), YAML anchors (no guard at all here, unlike `triage.yml`),
whitespace-only input, thousands of entries.

**`literature/registry.py`** — anchor/alias handling is the strongest thing in the
suite: whole-row (`tests/test_lit_registry.py:609`), nested (`:692`), in-list (`:715`),
merge key (`:762`), scalar reuse (`:785`), cyclic self-reference (`:738`). But three
gaps: duplicate top-level citekeys in `triage.yml` silently lose a row on rewrite
(untested, unguarded — the one round-trip shape with no guard); a duplicate `id` in
`references.json` silently takes the first; and **verified**, `load_triage` raises an
uncaught `RecursionError` on deeply nested YAML because `registry.py:506` catches only
`yaml.YAMLError`:

```
$ triage_mapping(Path("x.yml"), "a: " + "["*600 + "]"*600)
RecursionError: maximum recursion depth exceeded
```

A raw traceback from a parsed file — the failure-honesty rule's exact prohibition.
`dataset/manifest.py:312` has the identical gap. (No BibTeX parser exists; the registry
is CSL-JSON only, per ADR-0020.)

**`digest/extraction.py`** — best-covered parser in the set: wrong-typed and unknown
fields, blank locators, duplicate columns, malformed regex config
(`tests/test_extraction.py:413-458`, `:241-270`). Untested: an explicit `null` field;
unicode/NBSP in axis names, where matching is exact string equality
(`digest/extraction.py:390`); and ReDoS in user-supplied `locator_patterns` — that each
pattern compiles is validated (`extraction.py:314`), match time is not.

**`core/frontmatter.py`** — untested: empty input; **CRLF**, where `rebuild()` joins with
`"\n"` (`core/frontmatter.py:48`) and silently rewrites the whole file LF-only in a
module whose contract is "leave every other byte alone" (DATA-13); duplicate `status:`
blocks, where `set_field` patches the first and `yaml.safe_load` reads the last, so a
successful write changes nothing a reader sees.

**`core/gitignore.py`** — `check_ignore` is well covered including real `git init` trees
(`tests/test_gitignore.py:66-97`). `literal_covers` has no direct test. Untested:
negation lines; trailing whitespace (git treats it as significant, `.strip()` here does
not); Windows separators against the `startswith(line + "/")` test at
`core/gitignore.py:113`.

**Systematically absent across all six parsers:** CRLF and Windows paths · duplicate
keys (four independent silent-loss doors — DATA-11) · very large payloads · unicode
beyond a single Latin-1 accent (no emoji, RTL, or combining characters anywhere) · path
traversal in parsed content · recursion limits.

Adding `hypothesis` for these six would be the highest-leverage single change to the
suite. A round-trip property would have caught the `mdtable` bug on the first run:

```python
@given(st.lists(st.text(min_size=1), min_size=1, unique=True), ...)
def test_table_round_trips(header, rows):
    """`parse(render(x)) == x` — the invariant every table writer depends on."""
```

---

## 9. Test-suite maintainability

21,833 test LOC against 17,081 source LOC (1.28:1). The *tests* are excellent; the
*scaffolding* around them is copy-paste-grown.

`tests/conftest.py` is **34 lines and provides exactly one thing**: an autouse fixture
(`tests/conftest.py:17`) pointing `HOME`/`XDG_CONFIG_HOME` at a throwaway directory and
clearing `DEFENDABLE_SCIENCE_KEYS_PATH`. Well-documented and correct. It provides **no
shared builders, no `CliRunner`, no tmp-repo factory, no fakes.**

Measured consequences:

- **15 test files each construct their own `CliRunner()`** — `test_acquire_cli`,
  `test_backlog`, `test_check_cli`, `test_cli`, `test_cli_commands`, `test_cli_help`,
  `test_digest_cli`, `test_digest_render`, `test_init_repo`, `test_keys`,
  `test_literature`, `test_manifest`, `test_progress_cli`, `test_record`,
  `test_sampling`.
- **`_unstyled` — the identical `re.sub(r"\x1b\[[0-9;]*m", "", text)` — is defined three
  times**: `tests/test_cli_help.py:38`, `tests/test_progress_cli.py:228`,
  `tests/test_cli_commands.py:733`.
- **`_write` is defined six times with six different signatures**:
  `tests/test_digest_render.py:64`, `tests/test_manifest.py:53`,
  `tests/test_extraction.py:32`, `tests/test_lit_registry.py:14`,
  `tests/test_digest_artifact.py:53`, `tests/test_retrieval.py:15`.
- **`_scaffolded()` is near-duplicated** at `tests/test_check.py:233` and
  `tests/test_progress.py:342` — the same seven renderer calls, the progress copy just
  omitting the `.gitignore` line.
- **`_repo` ×3** (`tests/test_digest_render.py:286`, `tests/test_digest_cli.py:72`,
  `tests/test_sampling.py:154`), `_init` ×3, plus ×2 duplicates of `_write_triage`,
  `_write_config`, `_spine`, `_seed_blob`, `_run`, `_registry`, `_raising_run`,
  `_quarantine`, `_item`, `_fake_run`, `_entry`, `_cells`, `_artifact`.
- **Only 3 of 36 test files use `@pytest.fixture` at all.** Four `class` definitions
  across the 2,933 lines of `test_acquire.py`; one across the 2,528 of `test_check.py`.
  `parametrize` is used but sparsely (8 in `test_acquire.py`, 3 in `test_check.py`).
  The two largest suites are flat modules of 167 and 163 top-level functions.
- One cross-file import stands in for a conftest: `tests/test_progress.py:10`,
  `from test_check import FakeProbe, _doc  # the shared filesystem fake (#121)`. It
  works only because pytest inserts `tests/` on `sys.path` — fragile, and an explicit
  admission that a shared-fixture home is missing.

This is a maintainability finding, not a correctness one. But `conftest.py` is doing
roughly 1 % of the job it could, and the duplication tax lands on every new test.

---

## 10. The untested half of the repo — the plugin

The plugin is the primary deliverable and is invisible to every tool above.

**`tools/validate-plugin.sh` validates two JSON files.** If `claude` is on PATH it defers
to `claude plugin validate .` (this *is* what runs locally — verified: "Validating
marketplace manifest … ✔ Validation passed"). Otherwise the inline Python fallback
(`tools/validate-plugin.sh:15-58`) checks that `.claude-plugin/plugin.json` parses, is a
dict, and has non-empty `name`/`version`/`description`; and that
`.claude-plugin/marketplace.json` parses, is a dict, has a non-empty `name`, and a
non-empty `plugins` list whose entries each have `name` and a non-null `source`.
**That is the entire check. It never opens `skills/`.**

**`tests/test_plugin_content.py` (99 lines) asserts exactly three things**: (1)
`tests/test_plugin_content.py:52` — parametrised over all `skills/*/SKILL.md`, no line
in *prose* contains the literal `docs/research/` unless it sits inside a fence or matches
an allow-list regex (`:19`); (2) `:65` — the glob matched ≥ 8 skills, so the guard is not
vacuous; (3) `:70` — a self-test of the fence-tracking helper. It checks **one
hard-coded string**, and it deliberately **skips fenced code blocks**, which is where
every CLI invocation lives.

**Three more plugin-content guards do exist**, and they are good ones:

- `tests/test_status.py:121` — parametrised drift guard: all nine shipped
  `resources/templates/**.md` status blocks must byte-match `scaffold/status.render()`;
  `:179`/`:192` guard `templates/README.md`; `:204` pins that no machine-read field
  carries a placeholder.
- `tests/test_render.py:147` — `resources/templates/thesis/milestones.yml` must match the
  renderer.
- `tests/test_layout.py:326` — asserts `AUTHORITATIVE_DOCUMENTS["thesis"] == "kappa.md"`
  is consistent with what `kappa.md` and `aims.md` actually say.

**What can still break silently:**

- All 11 `skills/*/SKILL.md` — 2,955 lines. No frontmatter validation, no link checking,
  and **no check that a `defendable-science <group> <cmd>` named in a skill still exists
  in the Typer tree**. Four such breaks are shipping right now (API-2).
- 14 of 26 `resources/` files entirely unguarded: `contracts/*.md`, all eight
  `references/*.md`, `rigor/rigor-kit.md`, `substrate/asset-registry.md`,
  `commit-attribution.md`, and `ensure-tooling.md`.
- **`resources/ensure-tooling.md:26` is the concrete demonstration**: it pins the
  bootstrap to `defendable-science>=0.3.0,<0.4.0`. The in-tree package is `0.2.2`
  (`defendable-science/pyproject.toml:7`), `plugin.json` is `0.2.2`, the newest tag is
  `v0.2.2`, and `CHANGELOG.md:12` still has 0.3.0's content under `## [Unreleased]`. The
  bootstrap instruction every skill executes names a version that does not exist. Nothing
  — not `validate-plugin.sh`, not the suite, not CI — checks that pin against reality.

The two tests that close most of this are in
[`api-tech-debt.md`](api-tech-debt.md) API-3 (invocation-resolves) and API-6
(pin-is-satisfiable). Both are short, both belong in the existing `test` job.

---

## 11. Mutation spot-check — `core/fixity.py`

No mutation tool is installed (`mutmut`/`cosmic-ray` absent from PATH and `uv.lock`), so
this was hand-built: `defendable_science/` and `tests/` copied to `/tmp`, mutants applied
there, suite run via the existing venv. **The repository was never modified; the scratch
copy is deleted.** Four repo-root-coupled template guards fail in a `/tmp` copy, so
`test_status.py`/`test_layout.py`/`test_plugin_content.py` were excluded and
`test_render.py::test_rendered_milestones_matches_the_shipped_template` was held as a
constant 1-failure baseline — a mutant counts as SURVIVED at exactly 1 failure.

| Mutant | Result |
|---|---|
| M1 `bare_sha256`: drop `.lower()` | KILLED (4 tests) |
| M2 `bare_sha256`: drop `.strip()` | KILLED (2) |
| M3 `bare_sha256`: `[-1]` → `[0]` | KILLED (30) |
| M4 `blob_path`: drop the `sha256/` shard segment | KILLED (29) |
| M5 `verified`: `is_file()` → `exists()` | SURVIVED — **equivalent mutant** (a directory yields `IsADirectoryError`, an `OSError` subclass caught at `core/fixity.py:65` → the same `False`) |
| M6 `verified`: `==` → `!=` (sanity check) | KILLED (21) |
| M7 `verified`: unreadable file → `True` | KILLED (3) |
| M8 `sha256_file`: chunk 1 MiB → 1 byte | SURVIVED — **equivalent mutant, as predicted** (validates the harness is not producing false kills) |
| M9 `sha256_file`: `sha256` → `sha512` | KILLED (36) |

**Mutation score: 7/7 non-equivalent mutants killed (100 %)**, with both equivalent
mutants correctly surviving. Empirical evidence that in the fixity core — the module the
whole integrity story rests on — the 100 % line coverage is backed by real assertion
strength rather than execution alone.

---

## Key gaps to address

Ranked by impact on **research integrity** and on a consumer's ability to trust an
artifact this tool produced.

1. **Nothing tests the skill↔CLI contract, and four invocations are broken today**
   (API-2, API-3). A skill that names a flag the CLI dropped fails in front of a
   researcher mid-workflow. One parametrised test closes it.
2. **Nothing tests that the compat pin is satisfiable** (API-6). The shipped bootstrap
   names an unreleased version; ~15 lines of test prevent a recurrence.
3. **The write-then-log ordering hazard is untested in the failing direction** — three
   instances (`defend/record.py:293`, `digest/artifact.py:548`,
   `exploration/backlog.py:601`). This is the failure where an artifact claims verified
   understanding with no evidence behind it, which is categorically the worst thing this
   tool can do. Two `monkeypatch` tests.
4. **`core/mdtable.render_table` silently corrupts a host document** (DATA-5) —
   verified, and the class of bug a single round-trip property test eliminates.
5. **Unvalidated paths and coerced scalars in `datasets.yml`** (DATA-3, DATA-12) —
   verified: `path: ../../etc/passwd` produces zero validation errors in a fixity tool.
6. **`RecursionError` from deeply nested YAML** in `literature/registry.py:506` and
   `dataset/manifest.py:312` — verified raw traceback, against the repo's own rule.
7. **`core/http.py:345`'s pragma hides the most common HTTP failure.** Drop it and test
   the branch through the existing `FakeSession`; this is where a connection reset must
   not be mistyped as a throttle.
8. **`literature/acquire.py` has no live coverage at all** (§5) — 2,350 LOC of upstream
   parsing validated against three hand-trimmed fixtures.
9. **Zero concurrency tests, and no locking to test** (§7, DATA-6). Either add the lock
   or document the single-writer constraint — but discovering it as a lost `triage.yml`
   row is the wrong way for a researcher to learn it.
10. **No property-based testing on six hand-rolled parsers of untrusted input** (§8).
    Adding `hypothesis` to the dev group would have caught items 4 and 5 mechanically.
11. **`conftest.py` provides one fixture** (§9). Moving `_unstyled`, `CliRunner`,
    `_scaffolded` and `FakeProbe` into it removes ~40 duplicated definitions and the
    `sys.path`-dependent cross-file import at `tests/test_progress.py:10`.

---

*Cross-references: [`be-tech-debt.md`](be-tech-debt.md) for the implementation side of
items 3, 6 and 7; [`data-tech-debt.md`](data-tech-debt.md) for 4, 5 and 9;
[`api-tech-debt.md`](api-tech-debt.md) for 1 and 2;
[`plugin-tech-debt.md`](plugin-tech-debt.md) for §10.*
