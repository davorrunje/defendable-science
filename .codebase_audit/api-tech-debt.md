# The CLI + JSON contract surface

**Framing.** This package has no HTTP API. Its public interface is the
`defendable-science <group> <cmd>` command tree and **the JSON each command prints**,
because markdown skills parse that output and branch on it. A change to a JSON key is
a breaking change to a consumer exactly as a REST field rename would be. `cli.py` is
the authoritative Typer tree; `skills/**/SKILL.md` are the clients.

Tree measured 2026-08-29 by walking the live Click tree: **38 commands** across 8
groups.

---

## Priority index

| # | Finding | Severity |
|---|---|---|
| API-1 | No response envelope: 38 commands, 7 incompatible output shapes | **High** |
| API-2 | Four skill/doc invocations do not run against the shipped CLI | **High** |
| API-3 | Nothing tests the skill↔CLI contract | **High** |
| API-4 | Output shape switches on a flag: `--all` returns an array, the bare form an object | **High** |
| API-5 | Exit-code taxonomy is inconsistent; only one command distinguishes transport failure | **Medium** |
| API-6 | The compat pin names a package version that has never been released | **Medium** |
| API-7 | Failures are plain-text stderr, not machine-readable | **Medium** |
| API-8 | Unbounded result sets: no `--limit`/`--offset` anywhere | **Medium** |
| API-9 | No version field in any emitted JSON, and no stated policy for a breaking change | **Medium** |
| API-10 | Chatty commands the skills must loop over | **Low** |
| API-11 | Flag-combination validation is ad hoc | **Low** |
| API-12 | Nine design-record invocations describe flags that never existed | **Low** |

Documentation coverage is a non-finding: every command has a MyST field-list
docstring, and `DocstringTyper` (`cli.py:120`) strips the field list out of `--help`
so the two conventions do not collide. `tests/test_cli_help.py` walks the whole tree
and enforces it. That is better than most CLIs manage.

---

## High

### API-1 — No response envelope: 38 commands, 7 incompatible output shapes

Every command was read and its `typer.echo(json.dumps(...))` payload recorded.

| Shape | Commands | Payload |
|---|---|---|
| **A. `{ok, …, error, errors[]}`** — a real envelope | `digest extract axes/cells/record/sample/render` (`cli.py:2673`, `:2740`, `:2833`, `:3188`, `:3519`) | `ok` bool, per-item `errors[]`, whole-run `error` |
| **B. `{ok, …}`** — partial | `dataset validate` (`cli.py:1529`), `dataset verify` (`cli.py:1704`), `dataset audit` (`cli.py:1768`), `literature verify` (`acquire.py:2214`) | `ok`, no `error` field |
| **C. domain dict, no `ok`** | `init` (`cli.py:576`), `check` (`cli.py:657`), `progress dashboard` (`cli.py:757`), `defend record` (`cli.py:1940`), `literature fetch` (`acquire.py:2120`), `literature confirm` (`acquire.py:935`), `literature mirror` (`acquire.py:2317`), `dataset mirror` (`cli.py:1739`), `dataset ingest` (`cli.py:1560`), `literature resolve` (`graph.py:221`) | success inferred from the exit code or from a domain field |
| **D. bare array** | `literature cites` (`cli.py:932`), `literature refs` (`cli.py:944`), `literature enrich` (`cli.py:964`), `dataset fetch` (`cli.py:1682`), `dataset emit --all` (`cli.py:1589`), `backlog list` (`cli.py:2110`), `keys list` (`cli.py:2522`), `keys check` (`cli.py:2533`) | no envelope at all |
| **E. bare object** | `backlog park/add/rank/drop` and `promote` without `--scaffold` (`cli.py:2035`), `literature neighbors` (`cli.py:990`), `dataset emit <id>` (`cli.py:1596`) | the row / result, nothing else |
| **F. array *or* object depending on a flag** | `literature verify` (`cli.py:1402`), `literature mirror` (`cli.py:1467`), `dataset emit` (`cli.py:1589` vs `:1596`), `backlog promote` (`cli.py:2339` vs `:2340`) | see API-4 |
| **G. plain text, not JSON** | `doctor` (`cli.py:242`), `keys set` (`cli.py:2479`), `keys unset` (`cli.py:2546`), `keys path` (`cli.py:2555`), `check --text` (`cli.py:645`) | human-readable lines |

There is no consistent way to answer "did this succeed?", "is this empty?" or "what
went wrong?" across the tree. A skill must know, per command, which of seven
conventions applies. The newest family (shape A, added with `digest extract`) got it
right and nothing was retrofitted.

Two smaller inconsistencies in the same area:

- **`literature refs` alone omits `indent=2`.** `cli.py:944`:
  ```python
        typer.echo(
            json.dumps(graph_mod.refs(_openalex_id(client, identifier), client=client))
        )
  ```
  Every one of its 20 siblings passes `indent=2`. A consumer diffing or hashing output
  sees two formats.
- **`literature fetch` duplicates rows across buckets.** `acquire.py:2151`:
  ```python
        report[outcome.bucket].append(outcome.as_json())
        if outcome.committable:
            report["committable"].append(outcome.as_json())
  ```
  A committable outcome appears in both `fetched[]` and `committable[]` as two
  independent copies of the same 14-key object. A consumer counting rows across
  buckets over-counts; the payload roughly doubles for an open-access sweep.

**Fix** — one envelope helper, applied to new commands immediately and to shape B–F
commands at the next major bump (this is a breaking change; see API-9):

```python
# cli/_emit.py
from typing import Any, NoReturn


def emit(
    payload: dict[str, Any],
    *,
    ok: bool,
    error: str | None = None,
    errors: list[dict[str, Any]] | None = None,
    exit_code: int | None = None,
) -> NoReturn:
    """Print one command's result in the house envelope and exit.

    Every command answers the same three questions in the same three keys, so a
    skill never has to know which of seven conventions a command follows:
    ``ok`` (did the whole run succeed), ``error`` (the one thing that stopped it,
    or ``null``), ``errors`` (the per-item failures, ``[]`` when there were none).
    An empty ``errors`` with ``ok: true`` is a *legitimately empty* result; the
    same list with ``ok: false`` is a failed run — the distinction the
    failure-honesty rule exists to preserve.

    :param payload: The command's own domain keys, merged in at the top level.
    :param ok: Whether the run did what it was asked.
    :param error: The whole-run failure, if any.
    :param errors: Per-item failures.
    :param exit_code: Override; defaults to 0 when `ok`, else 1.
    """
    typer.echo(
        json.dumps(
            {
                "ok": ok,
                "api_version": 1,
                **payload,
                "error": error,
                "errors": errors or [],
            },
            indent=2,
        )
    )
    raise typer.Exit(code=exit_code if exit_code is not None else (0 if ok else 1))
```

Bare-array commands wrap their list under a named key (`{"ok": true, "works": [...]}`),
which also gives them somewhere to put the pagination fields API-8 wants. The three
plain-text `keys` commands should gain JSON output rather than lose their text
(`keys path` is read by shell scripts); add `--json` to those three specifically.

---

### API-2 — Four skill/doc invocations do not run against the shipped CLI

Extracted every `defendable-science …` / `dsci …` invocation from `skills/**`,
`resources/**`, `docs/**`, `README.md`, `CHANGELOG.md`, `STATUS.md` and checked each
against the live tree. Four hard failures — each reproduced.

**(a) `docs/USER-GUIDE.md:182` — wrong-case flag**
```
defendable-science backlog rank <id> --EIG high --feas med --interest high \
```
The option is `--eig` (`cli.py:2119`). `EIG` is the *table column* name
(`exploration/backlog.py:44`), not the flag. → `No such option: --EIG`, exit 2.

**(b) `docs/guides/dataset.md:32` — missing required positional, in the example that
defines the guide's own convention**
```bash
# Anything in a shell block is a real command, verbatim.
defendable-science dataset verify
```
`identifier` is required (`cli.py:1687`). → `Missing argument 'IDENTIFIER'.`, exit 2.
The block immediately above it (`docs/guides/dataset.md:28`) says "You are not meant to
type it into a shell" about quote blocks — so this is the line asserting that shell
blocks *are* verbatim, and it is broken.

**(c) `docs/guides/dataset.md:139` — same command, and the prose asks for a sweep**
```bash
defendable-science dataset verify
```
The surrounding prose (`docs/guides/dataset.md:142`) reads *"do the bytes on this
machine still match what I published?"* — a whole-manifest question. `verify` has no
`--all` and no optional-id form; the sweep is `dataset audit` (`cli.py:1744`, id
optional). So this is both a broken command and the wrong command.

**(d) `skills/hypothesis-exploration/SKILL.md:56` — a documented column header the CLI
refuses**
```
| id | one-line hypothesis | move/type | provenance | EIG | feas | interest | frame | status | note |
```
The canonical column is `one-line` (`exploration/backlog.py:39`). This is load-bearing
because `skills/hypothesis-exploration/SKILL.md:79` tells the agent to *"edit the
`backlog.md` table directly, keeping the column order above so the `backlog` verbs
(`rank`, `promote`, `list`) can parse it."* `Backlog.columns` uses the file's own header
(`exploration/backlog.py:169`) and `_append` calls
`_require("id", "one-line", "provenance", "status")` (`exploration/backlog.py:303`), so
a table built to this documented spec is permanently unwritable:

```
backlog table cannot carry required column(s) ['one-line']: its header is
['id', 'one-line hypothesis', ...]; add them, or migrate the table to the
hypothesis profile ['id', 'one-line', ...]
```

The error message is excellent. The document that caused it is the problem.

**Fix**: `--EIG` → `--eig`; both `dataset verify` calls → `dataset verify imagenet-c`
(or `dataset audit` at `:139` if the sweep is meant); `one-line hypothesis` →
`one-line`. All four are one-token edits. The systemic fix is API-3.

---

### API-3 — Nothing tests the skill↔CLI contract

`defendable-science/tests/test_plugin_content.py` is the only test that opens a
`SKILL.md`. It asserts exactly one thing —
`test_no_skill_hard_codes_the_research_tree` (`tests/test_plugin_content.py:52`) greps
for the literal `docs/research/` in prose — and it **deliberately skips fenced code
blocks** (`tests/test_plugin_content.py:70`), which is where every CLI invocation
lives.

`tests/test_cli_help.py:90` walks the whole Click tree but only asserts the help text
carries no MyST markup. `tools/validate-plugin.sh` reads only the two
`.claude-plugin/*.json` manifests and never opens `skills/`. `.pre-commit-config.yaml:69`
scopes the plugin hook to `files: ^\.claude-plugin/.*\.json$`, so editing a SKILL.md
triggers nothing but whitespace and codespell.

All four API-2 failures are mechanically detectable. This is the highest-value missing
test in the repository.

**Fix**:

```python
# tests/test_skill_cli_contract.py
"""Every documented invocation must run against the shipped Typer tree.

The plugin's skills are its clients: a skill that names a flag the CLI dropped is
a broken skill, and nothing else in the suite reads a `SKILL.md` code fence
(`test_plugin_content.py` explicitly skips them). Four such breaks were shipping
when this guard was written.
"""

import re
import shlex
from pathlib import Path

import pytest
from typer.main import get_command

from defendable_science.cli import app

ROOT = Path(__file__).resolve().parents[2]
DOCS = [
    *ROOT.glob("skills/*/SKILL.md"),
    *ROOT.glob("resources/**/*.md"),
    *ROOT.glob("docs/guides/*.md"),
    ROOT / "docs/USER-GUIDE.md",
    ROOT / "README.md",
]
_INVOCATION = re.compile(r"^\s*(?:\$ )?(?:defendable-science|dsci)\s+(.+?)(?:\s*\\)?$", re.M)


def _invocations() -> list[tuple[Path, int, str]]:
    out = []
    for doc in DOCS:
        for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if (m := _INVOCATION.match(line)) and "<" not in m.group(1).split()[0]:
                out.append((doc, n, m.group(1)))
    return out


@pytest.mark.parametrize(("doc", "line", "invocation"), _invocations())
def test_documented_invocation_resolves(doc, line, invocation):
    root = get_command(app)
    try:
        argv = shlex.split(invocation)
    except ValueError:
        pytest.skip(f"{doc.name}:{line}: not shell-parseable (prose)")
    cmd, rest = root, argv
    while rest and hasattr(cmd, "commands"):
        name, *rest = rest
        assert name in cmd.commands, (
            f"{doc.relative_to(ROOT)}:{line}: no such command {name!r} "
            f"(have {sorted(cmd.commands)})"
        )
        cmd = cmd.commands[name]
    known = {o for p in cmd.params for o in getattr(p, "opts", [])}
    for token in rest:
        if token.startswith("-") and "<" not in token:
            assert token.split("=")[0] in known, (
                f"{doc.relative_to(ROOT)}:{line}: {cmd.name} has no {token!r} "
                f"(have {sorted(known)})"
            )
```

Plus a second, tiny guard for API-2(d) — the documented backlog headers against
`columns_for(level)`:

```python
def test_documented_backlog_header_matches_the_column_profile():
    """A header a skill tells the author to hand-write must be one `Backlog` accepts."""
    text = (ROOT / "skills/hypothesis-exploration/SKILL.md").read_text("utf-8")
    documented = [c.strip() for c in re.search(r"^\| id \|.*$", text, re.M)[0].strip("|").split("|")]
    assert documented == columns_for("hypothesis")
```

Wire both into `ci.yml`'s existing `test` job — no new workflow needed.

---

### API-4 — Output shape switches on a flag

Four commands return a JSON **array** with `--all` and a JSON **object** without it.

`defendable-science/defendable_science/cli.py:1402`
```python
    output: Any = (
        reports[0].as_json() if citekeys is not None else [r.as_json() for r in reports]
    )
```
`defendable-science/defendable_science/cli.py:1467`
```python
    output: Any = reports[0] if citekeys is not None else reports
```

Same at `cli.py:1589` vs `:1596` (`dataset emit --all` vs `dataset emit <id>`), and
`backlog promote` emits a bare row (`cli.py:2339` → `_emit_row`) or
`{"row": …, "artifacts": …}` (`cli.py:2340`) depending on `--scaffold`.

The `output: Any` annotation at both sites is the type system reporting the problem.
A skill parsing `literature verify` must branch on its own flags to know whether to
index `[0]` or read a key — and if it guesses wrong it gets a `TypeError` from `jq` or
a silent wrong read.

**Fix** — always return the collection, and let arity be a property of the data:

```python
    reports = [acquire_mod.verify_entry(e, cache_dir=cache_dir) for e in entries]
    emit(
        {"entries": [r.as_json() for r in reports]},
        ok=all(r.ok for r in reports),
    )
```

`backlog promote` always emits `{"row": …, "artifacts": … | null}` — `null` when
`--scaffold` was not given, which is a fact the caller can read rather than infer.

---

## Medium

### API-5 — Exit-code taxonomy is inconsistent

The intended taxonomy is documented once, on one command:

`defendable-science/defendable_science/cli.py:895`
```
    :raises typer.Exit: Code ``0`` on a resolution. Code ``1`` on a genuine
        miss (no such paper). Code ``2`` on a Click/Typer usage error … Code
        ``3`` on a transport failure (``transport_error: true`` in the JSON) —
        deliberately distinct from ``2`` so a caller can never confuse "you
        typed it wrong" with "the network failed".
```

That reasoning is right and it is applied to `literature resolve` alone
(`cli.py:911`). Every other network command routes through `_http_guard`, which
collapses every transport failure to 1:

`defendable-science/defendable_science/cli.py:864`
```python
    except RateLimitError as exc:
        typer.echo(f"rate-limited by Semantic Scholar after {client.max_retries} retries …", err=True)
        raise typer.Exit(code=1) from exc
    except HttpError as exc:
        typer.echo(f"literature request failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
```

So `literature cites <id>` exits 1 both when the paper has no citations *and* when the
network died — the exact confusion `resolve`'s docstring says must never happen.
`RateLimitError` is a distinct type all the way up from `core/http.py:52` and is
discarded at the last step.

Observed codes across the tree:

| Code | Meaning | Emitted by |
|---|---|---|
| 0 | success | all |
| 1 | *everything else*: not-found, integrity failure, transport failure, config error, write failure | all |
| 2 | usage error | Click's own; plus `_one_of_citekey_or_all` (`cli.py:1227`), `_paper_dir_or_exit` (`cli.py:1989`), `_resolve_backlog` (`cli.py:2012`), `_open_backlog` (`cli.py:2028`), `_check_scaffold_opts` (`cli.py:2169`), `_set_many` (`cli.py:2431`), `set_` (`cli.py:2470`, `:2475`) |
| 3 | transport failure | `literature resolve` only (`cli.py:911`) |

Two commands use 1 where their siblings use 2 for the same class of mistake:
`dataset emit` with neither an id nor `--all` exits **1** (`cli.py:1593`), while
`literature fetch` in the identical situation exits **2** (`cli.py:1227`).

No failure path exits 0 — that part is sound, and `_fetch_report_exit_code`
(`cli.py:1231`) is a good example: it returns 1 when the sweep is incomplete
specifically so "no CI loop reads a half-swept registry as a finished one".

**Fix** — make `_http_guard` honour the taxonomy already written down, and document it
once in `--help`:

```python
#: The house exit codes. 3 and 4 are distinct because a researcher's next action
#: differs: retry later vs. investigate the bytes.
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_TRANSPORT, EXIT_INTEGRITY = 0, 1, 2, 3, 4

@contextmanager
def _http_guard(client: HttpClient) -> Iterator[None]:
    try:
        yield
    except RateLimitError as exc:
        typer.echo(f"rate-limited after {client.max_retries} retries — …", err=True)
        raise typer.Exit(code=EXIT_TRANSPORT) from exc
    except HttpError as exc:
        # A 404 is a fact about the paper (EXIT_FAILED); anything else is a fact
        # about us, and a caller must be able to tell them apart without parsing
        # the message — the distinction `literature resolve` already documents.
        code = EXIT_FAILED if exc.status_code == 404 else EXIT_TRANSPORT
        typer.echo(f"literature request failed: {exc}", err=True)
        raise typer.Exit(code=code) from exc
```

and change `cli.py:1593` to `EXIT_USAGE`. Reserve 4 for a checksum/fixity mismatch
(`literature verify`, `dataset verify`, `dataset audit`), which today is
indistinguishable from a missing manifest.

---

### API-6 — The compat pin names a package version that has never been released

`resources/ensure-tooling.md:26` pins the bootstrap to `defendable-science>=0.3.0,<0.4.0`.
`defendable-science/pyproject.toml:7` reads `version = "0.2.2"`; the newest git tag is
`v0.2.2`. **0.3.0 does not exist on PyPI.** The file itself says so
(`resources/ensure-tooling.md:73`, "that same unreleased `0.3.0` line").

Two further defects in the same bootstrap, both of which matter more than the number:

- **The pin is never passed to any install command.** Every literal is bare —
  `uv tool install defendable-science` (`resources/ensure-tooling.md:28`),
  `pipx install defendable-science` (`:30`), `pip install defendable-science` (`:32`).
  The constraint exists only in the surrounding prose at `:26`, so an agent executing
  the documented procedure installs whatever is latest.
- **There is no upgrade path.** Step 1 (`:16`) says "If it matches the pinned version →
  done", but the pin is a *range* and "matches" is undefined. On a mismatch the
  procedure falls through to step 3's bare `uv tool install`, which is a **no-op** on an
  already-installed older version. ADR-0026 line 35 promises the bootstrap
  "installs/**upgrades**"; this file never upgrades. A stale CLI is silently kept — a
  failure-honesty violation in the one document whose entire job is honest
  bootstrapping.

The pin also enumerates `digest extract axes | record | sample | render`
(`resources/ensure-tooling.md:72`) and omits `cells`, which
`skills/defend/SKILL.md:134` and `skills/digest/SKILL.md:512` now depend on.

**Fix** — release 0.3.0 or drop the floor to `>=0.2.2,<0.3.0`; put the constraint in
every command; define the mismatch action; and add the CI guard that would have caught
it (API-3's file is the natural home):

```python
def test_the_compat_pin_is_satisfiable():
    """The bootstrap's pinned range must admit a package version that exists.

    `ensure-tooling.md` is the first thing every skill executes. A floor above
    the newest release makes the documented PyPI path fail for every consumer,
    which is what shipped in 0.2.2.
    """
    pin = re.search(
        r"defendable-science>=([\d.]+),<([\d.]+)",
        (ROOT / "resources/ensure-tooling.md").read_text("utf-8"),
    )
    floor = Version(pin.group(1))
    shipped = Version(
        re.search(r'^version = "(.+)"', (ROOT / "defendable-science/pyproject.toml").read_text("utf-8"), re.M).group(1)
    )
    assert floor <= shipped, (
        f"ensure-tooling.md pins >={floor} but the package is {shipped}; "
        f"release {floor} or lower the floor"
    )
```

---

### API-7 — Failures are plain-text stderr, not machine-readable

`grep -c 'err=True' cli.py` → **57**. Only the five `digest extract` commands emit a
failure as JSON as well; every other error path writes prose to stderr and exits
non-zero, leaving nothing structured on stdout.

`defendable-science/defendable_science/cli.py:1447`
```python
        typer.echo(
            "no 'literature.mirror' configured in .defendable-science/config.yml",
            err=True,
        )
        raise typer.Exit(code=1)
```

The `digest extract` family shows the intended pattern, and the comment says exactly
why (`cli.py:2668`):

> Emitted on the refusal too, and `axes` is then `null` rather than `[]`: all four
> verbs report the same way, and a caller must never be able to read a matrix this run
> could not parse as a matrix with no axes.

That reasoning applies to the other 33 commands and was not extended to them. A skill
scripting `literature mirror --all` gets an empty stdout and a prose sentence on
stderr, so it must regex an English message to distinguish "no mirror configured"
from "the mirror is unreachable" from "one file is corrupt" — three cases with three
different human remedies.

**Fix** — API-1's `emit()` with `ok=False` on every failure path, plus a stable
`error.kind` discriminator so a skill matches on a token rather than a sentence:

```python
        emit(
            {},
            ok=False,
            error={
                "kind": "mirror-not-configured",
                "message": "no 'literature.mirror' in .defendable-science/config.yml",
                "remedy": "add a `literature.mirror.remote`, or drop --check",
            },
        )
```

The `kind`/`message`/`remedy` triple is already the shape of `check.model.Finding`
(`check/model.py:36`) — reuse it rather than inventing a second one.

---

### API-8 — Unbounded result sets

No command has `--limit` or `--offset`. Two caps exist and neither is a general
mechanism: `literature cites --max` (`cli.py:918`, default `0` = unlimited) and
`literature neighbors --top` (`cli.py:974`, default 20).

`literature cites` with no `--max` paginates to exhaustion at 200 rows/page
(`literature/graph.py:249`), accumulating every record in memory before serialising:

`defendable-science/defendable_science/literature/graph.py:247`
```python
    results: list[dict[str, Any]] = []
    cursor: str | None = "*"
    while cursor:
        page = client.get_json(..., {"filter": f"cites:{openalex_id}", "per-page": "200", "cursor": cursor})
        ...
        cursor = (page.get("meta") or {}).get("next_cursor")
    return results
```

For a canonical paper (say 40,000 citations) that is 200 requests, and each record
carries a reconstructed abstract from the inverted index (`graph.py:79`) — call it
2 KB — so ~80 MB held in memory and then `json.dumps(..., indent=2)`'d to stdout in
one go. There is no way to ask for the first page.

Also unbounded: `dataset emit --all` (whole manifest, `cli.py:1588`), `backlog list`
(whole table, `cli.py:2109`), `literature verify --all` / `mirror --all` (whole
registry, `cli.py:1400`/`:1457`), `digest extract sample` (every cell of every drawn
paper, `cli.py:3081`), `keys list` (bounded in practice). Every one also reads its
whole source file into memory first — `Path.read_text` at `registry.py:363`,
`manifest.py:350`, `backlog.py:230`.

**Fix** — a shared option pair and one cursor field in the envelope:

```python
_Limit = Annotated[int, typer.Option("--limit", min=0, help="Max rows; 0 = all.")]
_Offset = Annotated[int, typer.Option("--offset", min=0, help="Rows to skip.")]
```

with the envelope carrying `{"total": n, "offset": k, "limit": m, "truncated": bool}`.
`truncated` matters most: `neighbors` already reports `capped`
(`literature/graph.py:459`) precisely so truncation is never silent, and that principle
should be the tree's, not one command's.

For `cites` specifically, change the default from unlimited to a documented cap and
make unlimited the explicit opt-in — the current default is a footgun that only fires
on the most-cited papers, i.e. the ones a literature review is most likely to start
from.

---

### API-9 — No version field in emitted JSON, and no stated policy for a breaking change

No command emits a schema or API version. `--version` prints the package version
(`cli.py:190`) but nothing on stdout ties a JSON document to the CLI that produced it.
`ADR-0026` governs *package* versioning and the compat pin; it says nothing about the
JSON contract. Searching the ADR set for the output shape returns nothing (confirmed by
the plugin audit: no ADR covers the JSON envelope or the exit codes).

So the current policy is: a skill pins `defendable-science>=0.3.0,<0.4.0` and hopes.
Since the pin's *floor* is what gets bumped when a skill needs a new capability
(`resources/ensure-tooling.md:65`), and the ceiling only moves on a minor bump, a
breaking output change inside `0.3.x` would be invisible to the pin.

The consequence is already visible in the shape drift catalogued in API-1: five
different envelope conventions accreted across five feature waves, and nothing forced a
decision about whether changing an older one was allowed.

**Fix** — three parts:

1. `"api_version": 1` in the envelope (API-1's helper already emits it).
2. An ADR recording the contract and the change policy: *additive changes (a new key)
   are minor; removing or retyping a key, or changing an exit code's meaning, bumps
   `api_version` and the pin ceiling*.
3. A golden-output test per command so a shape change cannot land silently:

```python
@pytest.mark.parametrize("argv", [["dataset", "validate", …], …])
def test_output_shape_is_stable(argv, snapshot):
    """The emitted key set is the plugin's contract; a diff here is a breaking change."""
    result = CliRunner().invoke(app, argv)
    assert sorted(json.loads(result.stdout)) == snapshot
```

---

## Low

### API-10 — Chatty commands the skills must loop over

Read against the skills' actual invocation patterns:

- **`literature enrich`** already takes `list[str]` (`cli.py:951`) — good — but resolves
  each identifier with its own round-trip first (`cli.py:962`) and then fetches each
  work separately (`literature/graph.py:375`). See BE-7 in
  [`be-tech-debt.md`](be-tech-debt.md); the CLI-facing consequence is that a single
  unresolvable identifier aborts the whole batch (`cli.py:883`) and discards the work
  already done on the others. A batch command should report per-item failures in
  `errors[]`, not exit.
- **`literature resolve`** takes exactly one identifier (`cli.py:888`).
  `skills/literature/SKILL.md` drives it per citekey during triage, so a 40-paper
  screening is 40 process launches. Each launch re-reads `config.yml` (twice — see
  BE-7), rebuilds the `HttpClient`, and re-resolves the layout.
- **`literature confirm`** is one citekey per invocation (`cli.py:1318`), so working the
  `manual[]` worklist a sweep produced is N launches. `fetch`/`verify`/`mirror` all
  have `--all`; `confirm` does not, which is defensible (each promotion is a human act)
  but means the batch case has no path.
- **`digest extract cells`** is one citekey (`cli.py:2689`) while its four siblings all
  accept `--citekey` repeatably or `--all`. Inconsistent within one group.

**Fix** — make `resolve` variadic like `enrich`, add `--citekey` repeatability to
`extract cells`, and change batch commands from fail-fast to
`errors[]`-and-continue (the posture `fetch_all` already takes at
`literature/acquire.py:2148`).

---

### API-11 — Flag-combination validation is ad hoc

Three different mechanisms for the same job:

`defendable-science/defendable_science/cli.py:1223` — helper, exit 2, prose:
```python
    if bool(citekey) == all_flag:
        typer.echo("give exactly one of CITEKEY or --all, not neither or both", err=True)
        raise typer.Exit(code=2)
```
`defendable-science/defendable_science/cli.py:1347` — inline copy of the same rule:
```python
    if bool(sha256) == bool(file):
        typer.echo("give exactly one of --sha256 or --file, not neither or both", err=True)
        raise typer.Exit(code=2)
```
`defendable-science/defendable_science/cli.py:3290` — `BadParameter` instead:
```python
    if bool(citekey) == all_papers:
        raise typer.BadParameter("give exactly one of --citekey (repeatable) or --all: …")
```

`BadParameter` is the right one — Click renders it with usage context — and only the
newest command uses it.

Enum values are validated in three places too: `--level` in a helper
(`cli.py:2026`), `--verdict` inline (`cli.py:3296`), `--kind` in the kernel
(`literature/graph.py:452`), `--target` in the kernel (`defend/record.py:277`). None
uses Typer's `enum` support, so none appears in `--help` as a choice list and none is
tab-completable. `--size` has a hand-rolled range check (`cli.py:3300`) where
`typer.Option(min=1)` would do it declaratively and document itself.

Path existence is checked inconsistently: `--root` goes through `resolve_root`
(`core/config.py:17`, strict and well-reasoned), but `--file` (`cli.py:1325`),
`--cells` (`cli.py:2855`), `--points` (`cli.py:1838`) and `--transcript`
(`cli.py:1850`) are plain `str` and fail at read time. `--file` is handled cleanly
(`literature/acquire.py:1990` raises `RetrievalError`); the other three rely on
`cli.py:1937`/`:2917` catching `OSError`.

**Fix** — one helper and Typer's declarative validators:

```python
def _exactly_one(**named: object) -> None:
    """Refuse unless exactly one of the named options was supplied.

    :raises typer.BadParameter: Naming all of them, so the message reads the same
        wherever the rule is enforced.
    """
    given = [k for k, v in named.items() if v]
    if len(given) != 1:
        flags = ", ".join(f"--{k.replace('_', '-')}" for k in named)
        raise typer.BadParameter(
            f"give exactly one of {flags} — got {given or 'none'}"
        )
```

and, for the enums, `class Verdict(str, Enum)` so Typer renders the choices in
`--help` and rejects the rest before the body runs. Use
`typer.Option(exists=True, dir_okay=False)` on the four file-taking options.

---

### API-12 — Nine design-record invocations describe flags that never existed

Not agent-executed, but each file is headed `Status: implemented`, which invites a
reader to trust it:

| Location | Documents | Reality |
|---|---|---|
| `docs/design/proposals/literature-citation-graph-client.md:36` | `--json`, `--provenance-dir` | **no `--json` flag exists anywhere in the tree** |
| `:43` | `resolve --id` | `resolve` has no options (`cli.py:888`) |
| `:44` | `cites --per-page --max --since` | only `--max` (`cli.py:918`) |
| `:45` | `refs --max` | `refs` has no options (`cli.py:937`) |
| `:46` | `enrich --fields --context` | only `--context` (`cli.py:953`) |
| `docs/design/proposals/dataset-manifest-tooling.md:118` | `ingest --into` | no `--into` (`cli.py:1539`) |
| `:119` | `emit -o` | no `-o`; prints to stdout (`cli.py:1565`) |
| `docs/design/proposals/dataset-retrieval-mirror-tooling.md:102` | `dataset verify [<id>\|--all]` | no `--all`; id required (`cli.py:1687`) |

The last one is almost certainly the origin of API-2(b) and (c) — the guide was written
from the proposal rather than from the CLI.

**Fix** — either re-title these sections "as designed" and add a pointer to the
generated CLI reference, or regenerate them from the Typer tree.
`tools/build_docs_site.py` already walks that tree for the docs site, so the
authoritative rendering exists; the proposals just predate it.

---

## Correct-but-fragile

Documented behaviours that work today but rest on an unstated assumption.

- **`skills/dataset/SKILL.md:57`** and **`docs/design/03-dataset.md:28`** both say
  `verify` reports `` `verified-against-registry` `` — backticked, so it reads as a
  literal key. It exists nowhere in the package; `VerifyReport` emits
  `{entry_id, verified[], missing[], corrupt[], ok}` (`dataset/retrieval.py:171`,
  serialised at `cli.py:1704`). The phrase traces to methodology prose in
  `resources/references/dataset-management-standards.md:55`.
- **`skills/research-init/SKILL.md:70`** describes "one entry per path considered, each
  `created` | `exists` | `merged`, plus a `counts` object". `counts` is named
  correctly; the array is under **`actions`** (`cli.py:581`) and the skill names
  neither it nor the `{path, status}` element shape.
- **`skills/hypothesis-exploration/SKILL.md:73`** and
  **`skills/paper-exploration/SKILL.md:63`** say `promote --scaffold` "reports the
  created path(s) as JSON". The key is **`artifacts`**, beside `row` (`cli.py:2340`).
  Unnamed, and see API-4.
- **`skills/defend/SKILL.md:112`** and **`docs/guides/defend.md:52`** list three
  `--target` values; the CLI accepts four (`paper-comprehension`,
  `defend/record.py:33`). Used correctly elsewhere
  (`skills/digest/SKILL.md:120`), but the tables read as exhaustive.
- **`docs/guides/defend.md:125`** says `--log-dir` "defaults to
  `docs/research/defend-log`". The default is layout-anchored
  (`cli.py:1907`), so the literal path holds only for the default layout — the exact
  thing `tests/test_plugin_content.py` guards against in skills but not in guides.
- **`skills/progress/SKILL.md:46`** invokes `defendable-science check` and
  `progress dashboard` but is the only CLI-invoking skill that never links
  `resources/ensure-tooling.md`. The other eight all do.

**Verified correct — no action needed.** The skills' JSON-key claims were checked
against each command's `json.dumps` payload and these all hold:
`skills/progress/SKILL.md:58` (`ok`, `changed`, `artifact_count`, `findings` ←
`cli.py:757`); the whole `skills/digest/SKILL.md` extraction contract at `:210`,
`:307`, `:316`, `:379`, `:384`, `:464` (← `cli.py:2673`, `:2833`, `:3188`, `:3519`);
`skills/defend/SKILL.md:134` (← `cli.py:2740`); `skills/literature/SKILL.md:193`,
`:222`, `:229` (← `literature/acquire.py:128`, `:865`, `:2123`); and the fourteen-key
fetch-report row in `docs/guides/literature.md:224-315`, which matches
`literature/acquire.py:935` verbatim. That is a substantial contract, documented
accurately.

---

## Positive patterns to preserve

1. **The `digest extract` envelope is the model the rest of the tree should adopt.**
   `{ok, error, errors[], …}` with `error` for the whole-run failure and `errors[]` for
   per-item ones, emitted on *every* outcome including the refusal. The reasoning at
   `cli.py:2668`, `cli.py:2810` and `cli.py:3164` is explicit about why — including the
   decision to report `axes: null` rather than `[]` on a matrix that could not be
   parsed, and to split `verdict` from `verdict_requested` because "a key called
   `verdict` reading `verified` on a run that wrote nothing is one careless read away
   from being taken for the outcome".

2. **Exit codes keyed to severity, not to count.** `check` exits 1 on
   `invalid`/`unreadable` and 0 on `gap` (`check/model.py:31`), so "incomplete science"
   never fails a build while "an unreadable file" always does. That is the right axis
   and it is documented in the model rather than in a command.

3. **`_fetch_report_exit_code`** (`cli.py:1231`) returns 1 when `complete` is false,
   specifically so an incomplete sweep cannot be read as a finished one. Most tools
   would return 0 with a warning.

4. **`DocstringTyper`** (`cli.py:120`) resolves the MyST-docstring/`--help` collision
   at the framework level, so no command can regress. Enforced by
   `tests/test_cli_help.py` walking the whole tree.

5. **Politeness is real.** `mailto` is added for OpenAlex only and *never* for arXiv,
   with the privacy reasoning spelled out (`core/http.py:229`); the S2 key goes in a
   header, never a query parameter (`core/http.py:206`); per-host proactive rate caps
   default below each provider's documented ceiling (`core/http.py:128-137`).

6. **No key can leak through the CLI.** `keys set` takes the value from stdin or a
   hidden prompt, never argv (`cli.py:2448`); `_key_report` returns presence and source
   but never a value (`cli.py:2483`); `scoped_env` hands a child process only the
   variables that child needs (`core/keys.py:279`); and `keys set` warns when the
   resolved store sits in a non-gitignored work tree (`cli.py:2403`). The one defect in
   this area is the file-mode race at `core/keys.py:201` (BE-6), not the CLI surface.

---

*Cross-references: implementation-side detail for API-5/7/8 in
[`be-tech-debt.md`](be-tech-debt.md) (BE-4, BE-7); the plugin's side of API-2/3/6 in
[`plugin-tech-debt.md`](plugin-tech-debt.md); the missing tests in
[`coverage.md`](coverage.md).*
