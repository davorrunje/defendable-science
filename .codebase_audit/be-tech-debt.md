# Package internals — technical debt

Scope: `defendable-science/defendable_science/` (17,081 LOC, 41 files). Measured
2026-08-29 against `0489114`. All line numbers verified by reading the file.

Everything below is **debt in an otherwise disciplined codebase**. `uv run pytest -q`
is 1562 passed / 14 skipped at 100.00 % statement *and* branch coverage; `uv run mypy`
is clean over 79 files under `strict = true`; `uv run ruff check` is clean; bandit
reports 2 Low findings, both `random` for jitter/sampling and both correct. Read the
"Positive patterns to preserve" section at the end before acting on any of this.

**Note on Pydantic.** The repo owner has lifted the blanket Pydantic prohibition
*for the external-input parsing boundary only* (see the constraint note in
`plugin-tech-debt.md` → ADR hygiene). Fixes in **BE-9** are therefore written as
Pydantic v2 models. Everywhere else, stdlib `dataclasses` remain the norm and no
fix below proposes changing that.

---

## Priority index

| # | Finding | Severity |
|---|---|---|
| BE-1 | Path traversal from an externally-derived citekey writes outside the repo | **High** |
| BE-2 | The atomic write-temp-then-rename idiom is applied to 3 of 18 write sites | **High** |
| BE-3 | `defend record` mutates the claim before writing the evidence, with no rollback | **High** |
| BE-4 | Six unvalidated JSON boundaries: four tracebacks and one silently wrong value | **High** |
| BE-5 | The rclone and `git` subprocesses have no timeout | **Medium** |
| BE-6 | The key store is written world-readable, then chmod'd, and non-atomically | **Medium** |
| BE-7 | Per-item HTTP round-trips where OpenAlex offers a batch filter | **Medium** |
| BE-8 | `check` walks and re-parses every artifact three times per run | **Medium** |
| BE-9 | External JSON/YAML is parsed by hand; wrong shapes crash or coerce silently | **Medium** |
| BE-10 | `dict[str, Any]` used as a de-facto schema (42 occurrences in one module) | **Medium** |
| BE-11 | Injectable-callable fields typed `object`, forcing four `type: ignore[operator]` | **Medium** |
| BE-12 | Layout constants duplicated outside `scaffold/layout.py` | **Medium** |
| BE-13 | `keys check` shadows the top-level `check` command at module scope | **Low** |
| BE-14 | Unescaped title interpolated into an OpenAlex filter expression | **Low** |
| BE-15 | God modules — quantified, and *not* the problem it looks like | **Low** |
| BE-16 | `warn_unused_ignores = false` + `ignore_missing_imports = true` weaken strict mypy | **Low** |

No circular imports were found (see BE-15). No global mutable state beyond
`HttpClient._last_request`, which is instance-scoped and correct. No bare
`except:`, no `except Exception: pass`, no mutable default arguments.

---

## High

### BE-1 — Path traversal from an externally-derived citekey writes outside the repository

`Layout.digest()` interpolates a caller-supplied citekey straight into a path with no
sanitisation and no containment check:

`defendable-science/defendable_science/scaffold/layout.py:144`
```python
def digest(self, citekey: str) -> Path:
    """Return the digest artifact of `citekey`."""
    return self.digests_dir / f"{citekey}.md"
```

The citekey reaches it from a JSON file the agent writes. `cell_from_mapping`
(`digest/extraction.py:239`) type-checks the field but never constrains its content:

`defendable-science/defendable_science/digest/extraction.py:230`
```python
_CELL_FIELD_TYPES: dict[str, tuple[tuple[type, ...], str]] = {
    "citekey": ((str,), "a string"),
    ...
```

Call sites that feed it: `cli.py:2732`, `cli.py:2927`, `cli.py:3071`, `cli.py:3121`,
`cli.py:3409`. Same class of hole in `Layout.paper_dir` / `backlog` / `positioning`
(`layout.py:179`, `:183`, `:195`), reached from `backlog promote --id`.

**Reproduced.** With a one-cell `--cells` file whose citekey is
`../../../../../../tmp/dsaudit/PWNED`, `digest extract record` created
`/tmp/tmp/dsaudit/PWNED.md` — outside the work tree — and `mkdir(parents=True)`'d the
intervening directories to get there (`cli.py:2931`, `digest/artifact.py:547`). The
run then exited 1 only because the *log* filename carried the same `..` into a
directory that did not exist; the artifact write had already succeeded.

The codebase already knows this rule. `acquire.py:1019` sanitises exactly this input
for the cache, with a comment explaining why:

`defendable-science/defendable_science/literature/acquire.py:1019`
```python
def _safe_name(citekey: str) -> str:
    """Reduce a citekey to a filename-safe token.
    ...
    One containing a path separator would otherwise write outside the cache, which
    is not a risk worth carrying for a field nobody validates.
    """
    return _UNSAFE_NAME.sub("_", citekey)
```

And `layout._relative` (`layout.py:241`) and `cli._repo_relative` (`cli.py:359`) both
enforce repo containment on *config-supplied* paths. Neither rule was applied to the
derived per-artifact paths. The protection is inconsistent, not absent — which is what
makes it a systemic finding rather than a one-off.

**Fix** — validate the identifier at the layout boundary, so every derived path is
covered by one rule:

```python
# scaffold/layout.py
_SAFE_ID = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def _safe_id(kind: str, value: str) -> str:
    """Return `value` if it is a usable single path component, else refuse.

    :raises LayoutError: If it is empty, carries a path separator, or is a
        relative-path token — an identifier that escaped the tree would put a
        research artifact somewhere no reviewer will look for it.
    """
    if not _SAFE_ID.match(value) or value in (".", ".."):
        msg = (
            f"{kind} {value!r} is not a usable path component: use only "
            "letters, digits, '.', '_' and '-'"
        )
        raise LayoutError(msg)
    return value


def digest(self, citekey: str) -> Path:
    """Return the digest artifact of `citekey`."""
    return self.digests_dir / f"{_safe_id('citekey', citekey)}.md"
```

Apply the same call in `paper_dir`, `backlog`, `positioning`, `hypothesis_dir`
(with `slug`), and in `append_log_entry`'s `stem`
(`defend/record.py:343`) — that one builds a filename from the same untrusted value.

---

### BE-2 — The atomic write idiom is applied to 3 of 18 write sites

Commit `0489114` ("remove the orphan `.tmp` patch_triage leaves on a failed write")
hardened one writer. The pattern it hardened is not applied anywhere else, and the
sites that lack it include the most integrity-critical files the tool owns.

Full inventory (`grep -rn "write_text\|\.replace(\|\.open(\"w"`, each verified):

| Site | Writes | Temp+rename | `.tmp` cleanup |
|---|---|---|---|
| `literature/registry.py:827` | `triage.yml` | yes | **yes** |
| `literature/registry.py:468` | `references.json` spine | yes | **no** |
| `core/http.py:177` | HTTP response cache entry | yes | no (benign — cache) |
| `defend/record.py:293` | artifact `status.understanding` | **no** | — |
| `defend/record.py:298` | defend transcript | **no** | — |
| `defend/record.py:348` | accountability-log entry | **no** | — |
| `digest/artifact.py:548` | digest artifact + cells block | **no** | — |
| `digest/artifact.py:579` | digest `status.extraction` | **no** | — |
| `literature/acquire.py:1069` | quarantine sidecar JSON | **no** | — |
| `core/keys.py:201` | the API key store | **no** | — |
| `exploration/backlog.py:242` | backlog table | **no** | — |
| `exploration/backlog.py:486` | `hypothesis.md` | **no** | — |
| `exploration/backlog.py:541` | `papers.md` registry | **no** | — |
| `exploration/backlog.py:604`, `:608` | paper backlog + pitch | **no** | — |
| `scaffold/init_repo.py:81`, `:121` | scaffold files, `.gitignore` merge | **no** | — |
| `cli.py:696` | `dashboard.md` | **no** | — |
| `cli.py:3509` | `positioning.md` matrix merge | **no** | — |

`cli.py:3506` is the sharpest case. `digest extract render` reads the author's
positioning document, merges, and truncates-and-rewrites it in place:

`defendable-science/defendable_science/cli.py:3505`
```python
try:
    before = path.read_text(encoding="utf-8")
    merged = render_mod.render_matrix(path, rows)
    if merged != before:
        path.write_text(merged, encoding="utf-8")
```

The command's own docstring (`cli.py:3441`) promises "**Nothing is ever deleted.**" A
crash or a full disk between truncate and flush deletes everything after the write
offset — the taxonomy prose, the PRISMA log, the author's own delta.

`registry.py:468` is the near-miss: the same file already contains the fixed version
350 lines below it.

`defendable-science/defendable_science/literature/registry.py:468`
```python
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(
        json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    tmp.replace(target)
```

**Fix** — promote the already-correct helper to `core/` and route every artifact write
through it:

```python
# core/atomic.py  (new, ~15 lines)
from pathlib import Path


def write_atomic(target: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write `text` to `target` via a sibling ``.tmp``, cleaned up on failure.

    :param target: The file to write; its parent must exist.
    :param text: The full new contents.
    :raises OSError: If the write or the replace fails; no orphan ``.tmp`` is
        left behind either way.
    """
    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        tmp.replace(target)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
```

Then `registry._write_triage_atomically` (`registry.py:817`) becomes a one-line call,
`registry.py:468-472` becomes `write_atomic(target, json.dumps(...) + "\n")`, and the
15 direct `write_text` sites above each lose one line and gain crash-safety. This is a
mechanical change with no behavioural difference on the success path.

---

### BE-3 — `defend record` mutates the claim before writing the evidence, with no rollback

`record()` performs three writes in the wrong order and with no transaction:

`defendable-science/defendable_science/defend/record.py:288`
```python
    artifact_path = Path(artifact)
    if record_understanding:
        patched = patch_understanding(
            artifact_path.read_text(encoding="utf-8"), status, gaps, last_updated=date
        )
        artifact_path.write_text(patched, encoding="utf-8")     # 1. the claim

    transcript_path: Path | None = None
    if transcript is not None:
        transcript_path = artifact_path.with_name(f"defend-{date}.md")
        transcript_path.write_text(transcript, encoding="utf-8")  # 2.
    ...
    log_entry_path = _append_log(Path(log_dir), entry)            # 3. the evidence
```

If step 3 fails — an unwritable `log_dir`, a full disk — the artifact's frontmatter
already reads `status.understanding: {"status": "ok", "unresolved": []}` while **no
accountability-log entry exists**. `cli.py:1937` catches the `OSError` and exits 1
honestly, but the on-disk state is the one thing this tool exists to prevent: a
recorded claim of verified understanding with no evidence behind it. `progress` and
`check` both read the frontmatter, not the log, so the false claim propagates to the
dashboard.

`digest/artifact.py:548-551` has the identical ordering: `write_extraction` writes
`status.extraction` to the artifact, then appends the log.

A second, independent problem in the same area: `append_log_entry` uses a
check-then-write race on an append-only audit log.

`defendable-science/defendable_science/defend/record.py:343`
```python
    target = log_dir / f"{date}-{stem}.yml"
    n = 2
    while target.exists():
        target = log_dir / f"{date}-{stem}-{n}.yml"
        n += 1
    target.write_text(body, encoding="utf-8")
```

Two concurrent runs both observe the same free name and the second silently overwrites
the first's evidence. The docstring at `record.py:337` states "Never overwrites: … the
log is append-only evidence" — which is exactly the guarantee the `exists()`/`write`
gap breaks.

**Fix** — evidence first, claim second, and make the log write exclusive:

```python
# defend/record.py — append_log_entry
    log_dir.mkdir(parents=True, exist_ok=True)
    n = 1
    while True:
        suffix = "" if n == 1 else f"-{n}"
        target = log_dir / f"{date}-{stem}{suffix}.yml"
        try:
            # "x" fails if the name was taken between the check and the write,
            # which `exists()` cannot rule out — the log is append-only evidence.
            with target.open("x", encoding="utf-8") as handle:
                handle.write(body)
        except FileExistsError:
            n += 1
            continue
        return target
```

```python
# defend/record.py — record(), reordered
    entry = LogEntry(...)                       # build first, write first
    log_entry_path = _append_log(Path(log_dir), entry)
    try:
        if record_understanding:
            patched = patch_understanding(...)
            write_atomic(artifact_path, patched)   # BE-2's helper
        if transcript is not None:
            transcript_path = artifact_path.with_name(f"defend-{date}.md")
            write_atomic(transcript_path, transcript)
    except OSError:
        # The log entry is evidence of an examination that happened; the artifact
        # patch is a claim about it. An orphan evidence row is safe to leave and
        # honest to read; an orphan claim is not.
        raise
```

An orphan log entry with no frontmatter patch is recoverable and reads correctly to a
reviewer. The current failure mode is neither. Apply the same reordering to
`digest/artifact.write_extraction` (`digest/artifact.py:548`).

---

### BE-4 — Six unvalidated JSON boundaries: four tracebacks and one silently wrong value

`CLAUDE.md:65` requires that a failure "never let a transient error surface as a raw
traceback", and that a failure never be "silently reported as a legitimate … result".
Six sites violate one or the other. **All six were reproduced independently for this
audit**; each is also tracked in **#169**.

The debt here is **concentrated, not uniform** — four of the six are in
`literature/graph.py`, which is the one module that projects a third party's JSON
straight into the CLI's own output. The rest of the package's external-input parsing is
good, and is listed under *Positive patterns to preserve* (item 8) rather than here.

| # | Site | Symptom | Class |
|---|---|---|---|
| 1 | `literature/graph.py:256` | `AttributeError` mid-pagination | traceback |
| 2 | `literature/graph.py:81` | `AttributeError` | traceback |
| 3 | `literature/graph.py:348` | **a single character** recorded as the citation context | **silent wrong value** |
| 4 | `literature/graph.py:110` | wrong-typed values pass into emitted JSON | silent wrong value |
| 5 | `literature/acquire.py:1939` | `KeyError` / `JSONDecodeError` | traceback |
| 6 | `cli.py:1549` → `dataset/manifest.py:548` | `AttributeError` | traceback |

**Site 3 is the most serious, and it is worse than a wrong type.**
`_aggregate_s2_edges` indexes into whatever S2 returned:

`defendable-science/defendable_science/literature/graph.py:345`
```python
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        if out["context_snippet"] is None and edge.get("contexts"):
            out["context_snippet"] = edge["contexts"][0]
        if out["intent"] is None and edge.get("intents"):
            out["intent"] = edge["intents"][0]
```

The `isinstance(edge, dict)` guard is there — the *field* guard is not. Reproduced:

```python
_aggregate_s2_edges([{"contexts": "the whole sentence", "intents": "background"}], out)
# out["context_snippet"] == 't'
# out["intent"]          == 'b'
```

If Semantic Scholar ever returns a bare string where the docs promise a list, the tool
records the letter `t` as the sentence in which a paper was cited, and `b` as the
citation intent — and emits both as legitimate values with no `degraded` marker, in the
same shape it uses for real data (`literature/graph.py:379-382` reserves `degraded` for
the no-key case). A researcher reading `literature enrich --context` gets a confident,
wrong answer about how a work was cited. This is precisely the failure the whole module
is otherwise built to prevent, and it is the only place in the package I found where a
malformed upstream field becomes a *plausible-looking* value rather than a crash or a
`None`.

**Site 1** — the page is checked, the elements are not:

`defendable-science/defendable_science/literature/graph.py:254`
```python
        if not isinstance(page, dict):
            raise HttpError(f"{OPENALEX}/works: citation page is not a JSON object")
        for work in page.get("results", []):
            record = enrich_work(work)
```
Reproduced: a `results` array containing a string raises
`AttributeError: 'str' object has no attribute 'get'` from inside `enrich_work`
(`graph.py:96`), mid-pagination, after an arbitrary number of pages have already been
accumulated. The guard one line above shows the author knew to check the envelope; the
elements were missed.

**Site 2** — `_abstract` assumes a mapping (`literature/graph.py:81`):
```python
    index = work.get("abstract_inverted_index")
    if not index:
        return None
    for word, where in index.items():
```
Reproduced: `abstract_inverted_index: ["a", "b"]` → `AttributeError: 'list' object has
no attribute 'items'`. The falsy guard handles `null` and `{}` but not a wrong type.

**Site 4** — untyped pass-through into emitted JSON (`literature/graph.py:110`):
```python
        "title": work.get("display_name") or work.get("title"),
        "year": work.get("publication_year"),
        "cited_by_count": work.get("cited_by_count"),
```
Reproduced: `publication_year: "not-a-year"` emerges as the *string* `'not-a-year'` in
`literature enrich`'s JSON. No crash, no marker. A consumer that sorts or filters on
`year` gets a `TypeError` at its own boundary, or worse, a lexicographic sort. Note the
contrast with `acquire.candidate_from_work` (`literature/acquire.py:549`), which reads
the *same* two fields and does guard them:
```python
        year=year if isinstance(year, int) else None,
        title=title if isinstance(title, str) else None,
```
So the rule exists in the codebase and was applied in one of the two readers of the
same upstream record.

**Site 5 — a truncated quarantine sidecar.** `_write_quarantine` moves the PDF
atomically and then writes the sidecar non-atomically (BE-2):

`defendable-science/defendable_science/literature/acquire.py:1068`
```python
    src.replace(pdf)
    (directory / f"{sha}.json").write_text(
        json.dumps({...}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
```

`confirm_quarantined` then reads it back with unguarded indexing:

`defendable-science/defendable_science/literature/acquire.py:1939`
```python
    data: dict[str, Any] = json.loads(sidecar.read_text(encoding="utf-8"))
    candidate = cast("dict[str, Any]", data["candidate"])
    match = cast("dict[str, Any]", data["match"])
    rung = cast("str", data["rung"])
    url = cast("str | None", data["url"])
```

A run interrupted during the sidecar write leaves a present-but-truncated file. The
`is_file()` guard at `acquire.py:1916` passes; `json.loads` then raises
`JSONDecodeError`, or the four lookups raise `KeyError`. `lit_confirm` catches only
`RetrievalError` (`cli.py:1360`). The four `cast()`s are the tell — see the `cast()`
sub-finding in BE-10.

**Site 6 — `dataset ingest` on a non-object JSON document.** Reproduced:

```
$ defendable-science dataset ingest arr.json      # file contains: []
AttributeError: 'list' object has no attribute 'get'
```

`defendable-science/defendable_science/cli.py:1548`
```python
    try:
        doc = json.loads(Path(croissant).read_text(encoding="utf-8"))
        entry = manifest_mod.entry_from_croissant(doc)
    except (OSError, json.JSONDecodeError, manifest_mod.ManifestError) as exc:
```

`entry_from_croissant` is annotated `json_ld: dict[str, Any]` (`manifest.py:534`) and
calls `json_ld.get("name")` at `manifest.py:548` with no runtime shape check. Strict
mypy is satisfied because `json.loads` returns `Any`. The `except` clause at
`cli.py:1551` does not list `AttributeError`, so the documented exit 1 becomes a
traceback.

**Fix for sites 1–4** — the guards these sites need already exist elsewhere in the same
package; this is applying them consistently, and is what a `_WorkIn` model (BE-9) does
declaratively:

```python
# literature/graph.py:254 — guard the elements, not just the envelope
        for work in page.get("results", []):
            if not isinstance(work, dict):
                # A page whose elements are not works is a page we cannot read.
                # Skipping silently would return a short frontier as if complete —
                # the same reason the envelope check above is a hard error.
                raise HttpError(f"{OPENALEX}/works: citation page holds a non-work entry")
            record = enrich_work(work)

# literature/graph.py:81 — a wrong-typed index is no abstract, not a crash
    index = work.get("abstract_inverted_index")
    if not isinstance(index, dict):
        return None

# literature/graph.py:345 — a scalar where a list was promised is *not* data
        contexts = edge.get("contexts")
        if out["context_snippet"] is None and isinstance(contexts, list) and contexts:
            snippet = contexts[0]
            out["context_snippet"] = snippet if isinstance(snippet, str) else None

# literature/graph.py:110 — the guard `acquire.candidate_from_work:549` already uses
    year = work.get("publication_year")
    cited = work.get("cited_by_count")
    ...
        "year": year if isinstance(year, int) else None,
        "cited_by_count": cited if isinstance(cited, int) else None,
```

For site 3 specifically, consider marking the record `degraded` rather than silently
`None`, reusing the mechanism already at `literature/graph.py:382` — "S2 returned
something we could not read" and "S2 returned nothing" are different facts, and this
module distinguishes exactly that pair everywhere else.

**Fix for site 5** — same file, same style as its neighbours:

```python
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        candidate = data["candidate"]
        match = data["match"]
        rung = data["rung"]
        url = data["url"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RetrievalError(
            f"quarantine sidecar {sidecar} is unreadable ({exc}) — most likely a "
            "run interrupted mid-write. Delete it and the matching .pdf, then "
            "re-run `literature fetch --refetch` for this citekey."
        ) from exc
    if not (isinstance(candidate, dict) and isinstance(match, dict)
            and isinstance(rung, str) and (url is None or isinstance(url, str))):
        raise RetrievalError(f"quarantine sidecar {sidecar} has the wrong shape …")
```

For **site 6**, see BE-9 — that surface is better served by a parse model than by
widening an `except` clause.

**Where I differ from #169's framing.** #169 lists these as six parsing defects. Sites
3 and 4 are worth separating out: they are not tracebacks, they are **silent wrong
values emitted as legitimate CLI output**, and by this repository's own severity logic
(`CLAUDE.md:65`) that is the more serious class. A traceback is loud and the researcher
re-runs; a citation context reading `'t'` is indistinguishable from a real one and can
end up quoted in a related-work section. I would fix 3 first, not last.

---

## Medium

### BE-5 — The rclone and `git` subprocesses have no timeout

Three subprocess call sites; one passes a timeout.

`defendable-science/defendable_science/cli.py:221` — correct:
```python
        proc = subprocess.run(  # nosec B603 - `path` resolved from PATH; fixed args
            [path, "--version"],
            capture_output=True, text=True, timeout=10, check=False,
        )
```

`defendable-science/defendable_science/core/mirror.py:149` — no timeout:
```python
        kwargs: dict[str, object] = {"capture_output": True, "check": False}
        if self.env is not None:
            kwargs["env"] = {**os.environ, **self.env}
        try:
            proc = self.run(  # nosec B603 - fixed rclone args, no shell
                self._cmd(*args), **kwargs
            )
```

`defendable-science/defendable_science/core/keys.py:393` — no timeout:
```python
        proc = run(  # nosec B603 - fixed git args, no shell
            ["git", "check-ignore", "-q", str(path)],
            capture_output=True, check=False,
            cwd=str(cwd) if cwd is not None else None,
        )
```

Blast radius for `mirror.py`: every `dataset fetch|mirror|audit` and
`literature fetch|mirror` hangs indefinitely against a stalled remote, a hung DNS
lookup, or an rclone build that prompts on stdin. `mirror_entry` calls `check()`
once per file in a loop (`acquire.py:2330`), so a `literature mirror --all` over a
degraded remote hangs on the first entry with no output and no way to attribute it.
There is no `stdin=subprocess.DEVNULL` either, so an interactive rclone prompt blocks
forever rather than failing.

**Fix**:

```python
# core/mirror.py — on the Mirror dataclass, beside `rclone_bin`
    #: Per-call ceiling for one rclone invocation. A mirror we cannot reach must
    #: fail as `MirrorUnreachableError`, not hang a sweep — the same distinction
    #: `ABSENT_EXIT_CODES` draws, applied to the time axis.
    timeout: float = 300.0

# ... in _run_ok
        kwargs: dict[str, object] = {
            "capture_output": True,
            "check": False,
            "timeout": self.timeout,
            "stdin": subprocess.DEVNULL,
        }
        try:
            proc = self.run(self._cmd(*args), **kwargs)
        except FileNotFoundError as exc:
            raise RetrievalError(
                "rclone not found on PATH — install it or unset the mirror"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise MirrorUnreachableError(
                f"rclone {args[0]} on {self.remote!r} did not answer within "
                f"{self.timeout:.0f}s — the mirror could not be reached, so "
                "whether it holds this key is unknown",
                returncode=-1,
            ) from exc
```

`core/keys.py:393` wants `timeout=10` and `except subprocess.TimeoutExpired: return None`
— the function already returns `None` for "git could not answer", so a timeout maps
cleanly onto the existing contract.

---

### BE-6 — The key store is written world-readable, then chmod'd, and non-atomically

`defendable-science/defendable_science/core/keys.py:198`
```python
    resolved = store_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dict(sorted(mapping.items())), indent=2) + "\n"
    resolved.write_text(payload, encoding="utf-8")
    resolved.chmod(0o600)
```

Two problems in five lines:

1. **Mode race.** `write_text` creates the file at `0666 & ~umask` — `0644` on a
   default system. The secret is on disk and world-readable for the interval between
   line 201 and line 202. On a shared host or a CI runner that is a real window.
2. **Non-atomic full rewrite.** `set_key` (`keys.py:212`) and `unset_key`
   (`keys.py:224`) both do load → mutate → `write_store`, i.e. every single-key
   operation rewrites the whole store. An interruption during line 201 truncates the
   file and loses **every** stored credential, not just the one being set. The module
   docstring's honesty section (`keys.py:32`) discusses plaintext-at-rest but not this.

**Fix** — create the temp file with the mode already correct, then rename:

```python
import os
import tempfile


def write_store(mapping: Mapping[str, str], path: str | Path | None = None) -> None:
    """Write `mapping` to the store, creating it ``0600`` from the first byte.

    The payload lands in a ``0600`` temp file in the store's own directory and is
    then renamed over the target, so the secret is never momentarily world-readable
    (the ``write`` then ``chmod`` order left a window) and an interrupted write can
    never truncate the store and lose every other key.
    """
    resolved = store_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dict(sorted(mapping.items())), indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=resolved.parent, prefix=".keys-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        os.chmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        tmp.replace(resolved)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
```

(`tempfile.mkstemp` already creates at `0600`; the explicit `chmod` documents the
intent and survives an exotic umask.)

---

### BE-7 — Per-item HTTP round-trips where OpenAlex offers a batch filter

The N+1 analogue. Three sites, all in `literature/graph.py`, all one call per item
against an API that accepts up to 50 ids in one `filter=openalex_id:W1|W2|…` query.

`defendable-science/defendable_science/literature/graph.py:403`
```python
def _cocitation(openalex_id, citers, client, top):
    counter: Counter[str] = Counter()
    for citer in citers:
        citer_id = citer["id"]["openalex"]
        if citer_id:
            for ref in refs(citer_id, client=client):     # 1 HTTP call per citer
```

`defendable-science/defendable_science/literature/graph.py:417`
```python
def _coupling(openalex_id, client, top, frontier):
    counter: Counter[str] = Counter()
    for ref in refs(openalex_id, client=client)[:frontier]:
        for citer in cites(ref, client=client, max_results=frontier):  # ≥1 per ref
```

With the default `frontier = 50` (`graph.py:436`), `literature neighbors --kind both`
issues roughly 100 sequential requests. `HttpClient.openalex_rps` defaults to 10.0
(`core/http.py:149`), so the proactive throttle alone floors it at ~10 s of wall clock
for one neighbour query — before any retry.

`defendable-science/defendable_science/literature/graph.py:374`
```python
    for wid in openalex_ids:
        record = enrich_work(_fetch_work(client, wid))    # 1 call per id
```

And the CLI doubles it — `enrich` resolves each identifier separately before enriching:

`defendable-science/defendable_science/cli.py:962`
```python
        ids = [_openalex_id(client, ident) for ident in identifiers]
        rows = graph_mod.enrich(ids, client=client, with_context=with_context)
```

So `literature enrich A B C` costs six round-trips where two would do. A single
unresolvable identifier also aborts the whole batch (`_openalex_id` raises
`typer.Exit(1)` at `cli.py:883`), discarding the work already done on the others.

The on-disk response cache (`core/http.py:155`) blunts the *repeat* cost but not the
first run, which is the one a researcher waits on.

**Fix** — add one batch helper and route the three loops through it:

```python
# literature/graph.py
#: OpenAlex accepts up to 50 ids in one `openalex_id:` OR-filter.
BATCH = 50


def fetch_works(openalex_ids: list[str], *, client: HttpClient) -> dict[str, dict[str, Any]]:
    """Fetch many works in ``ceil(n/50)`` requests instead of ``n``.

    :returns: work-id → work record, for every id the API returned. An id the
        API did not return is **absent** from the mapping rather than mapped to
        an empty dict: "OpenAlex has no such work" and "we did not ask" must not
        collapse into the same value.
    """
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(openalex_ids), BATCH):
        chunk = openalex_ids[start : start + BATCH]
        page = client.get_json(
            f"{OPENALEX}/works",
            {"filter": "openalex_id:" + "|".join(chunk), "per-page": str(BATCH)},
        )
        if not isinstance(page, dict):
            raise HttpError(f"{OPENALEX}/works: batch page is not a JSON object")
        for work in page.get("results", []):
            if isinstance(work, dict) and (wid := _short_id(work.get("id"))):
                out[wid] = work
    return out
```

`enrich` becomes a single `fetch_works` call plus a list comprehension; `_cocitation`
becomes one `fetch_works(citer_ids)` followed by reading `referenced_works` off each
returned record — which removes the `refs()` call entirely, since the batch response
already carries that field. Expected reduction for `neighbors --kind both`: ~100
requests → ~4.

---

### BE-8 — `check` walks and re-parses every artifact three times per run

`run_checks` (`check/checks.py:2097`) composes seven families. Three of them
independently glob the tree and re-read every staged document, and `Probe` has no
memoisation:

- `check_frontmatter` → `staged_documents(layout, probe)` at `check/checks.py:937`,
  then `read_or_finding(path, …)` per document at `check/checks.py:828`
- `check_cross_artifact` → `_check_dashboard_consistency` → `projected_ids` at
  `check/checks.py:1746` → `collect()` → `staged_documents` at
  `progress/collect.py:214` and `read_or_finding` at `progress/collect.py:242`
- `check_cross_artifact` → `_check_artifact_rules` → `staged_documents` at
  `check/checks.py:1806`, then `read_or_finding` at `check/checks.py:1820`

`aims.md` is read a fourth time (`progress/collect.py:409` and
`check/checks.py:1812`). `FsProbe.read_text` (`check/probe.py:62`) goes straight to
the filesystem every time, and each read is followed by a fresh
`scaffold.status.parse` / `yaml.safe_load`.

Cost is `3 × (glob + read + YAML-parse)` per staged document. A portfolio of 8 papers
with 4 hypotheses each is ~100 staged documents, so ~300 reads and ~300 YAML parses
per `check` — and `check` is the command `research-init` tells users to run routinely.
The same tree is walked again by `progress dashboard`.

`run_checks` already deduplicates the *findings* this produces (`check/checks.py:2128`),
which is the symptom being managed rather than the cause.

**Fix** — a memoising probe decorator; no call site changes:

```python
# check/probe.py
class CachingProbe:
    """A `Probe` that reads each path once per run.

    `run_checks` composes seven families over one immutable snapshot of the repo,
    and three of them walk the same staged documents. Re-reading is not merely
    slow: two families reading a file at different instants could disagree about
    it, and a check report must describe one state of the tree.
    """

    def __init__(self, inner: Probe) -> None:
        self._inner = inner
        self._text: dict[Path, str | OSError] = {}
        self._glob: dict[tuple[Path, str], list[Path]] = {}

    def read_text(self, path: Path) -> str:
        if path not in self._text:
            try:
                self._text[path] = self._inner.read_text(path)
            except OSError as exc:
                self._text[path] = exc
        hit = self._text[path]
        if isinstance(hit, OSError):
            raise hit
        return hit

    def glob(self, root: Path, pattern: str) -> list[Path]:
        key = (root, pattern)
        if key not in self._glob:
            self._glob[key] = self._inner.glob(root, pattern)
        return list(self._glob[key])

    # exists / is_dir / is_gitignored: delegate, memoised the same way
```

Then `cli.py:640` becomes `probe = CachingProbe(FsProbe())` and
`cli.py:754` likewise. Caching the raised `OSError` matters: an unreadable file must
stay unreadable for every family, or the dedup at `checks.py:2128` starts hiding a
real inconsistency.

---

### BE-9 — External JSON/YAML is parsed by hand; wrong shapes crash or coerce silently

Five untrusted-input surfaces. The guard quality is **not uniform**, and the split
matters for what to fix:

| Surface | Parser | Guard quality |
|---|---|---|
| OpenAlex work records — **`graph.py`** | `literature/graph.py:90`, `:232-274` | **unguarded** — BE-4 sites 1, 2, 4 |
| OpenAlex work records — **`acquire.py`** | `literature/acquire.py:508-675` | good `isinstance` ladder per field; ~42 `dict[str, Any]` but every read is checked |
| Semantic Scholar responses | `literature/graph.py:288-355` | envelope checked, **fields unguarded** — BE-4 site 3 |
| Croissant JSON-LD | `dataset/manifest.py:534` | **assumes a top-level object** — BE-4 site 6 |
| `datasets.yml` | `dataset/manifest.py:221-336` | structurally good, but coerces (below) |
| Registry / triage / key store / point records / cells | `registry.py:290`, `keys.py:170`, `cli.py:1805`, `cli.py:2774`, `extraction.py:239` | **good — see Positive patterns item 7** |
| Artifact YAML frontmatter | `scaffold/status.py`, `progress/collect.py:64-119` | deliberately tolerant, and correctly so |

The two rows worth reading together are the first two: the *same* upstream record is
parsed by two modules, and only `acquire.py` guards it. The rule exists in the codebase;
`graph.py` predates its consistent application.

Two distinct defects rather than one:

**(i) Missing shape checks that become tracebacks or wrong values** — the six sites in
BE-4.

**(ii) Coercion where validation is meant.** `dataset/manifest.py:226`:

```python
    try:
        path = str(raw["path"])
        sha256 = str(raw["sha256"])
    except KeyError as exc:
        raise ManifestError(f"{where}: file missing required key {exc}") from exc
```

A manifest written `path: [a, b]` silently becomes the *string* `"['a', 'b']"`. Same
at `manifest.py:268` for `id` and `manifest.py:240` for `retrieval.kind`. The
subsequent `validate()` pass (`manifest.py:443`) checks the checksum *format*
(`SHA256_RE`, `manifest.py:24`) so a mangled sha is caught, but a mangled `path` or
`id` is not — it reaches `retrieval._resolve_file` (`dataset/retrieval.py:96`) as a
path.

**Fix — Pydantic v2 at the parsing boundary.** Now sanctioned for exactly this
surface. Model the *wire shape*, keep the existing `dataclasses` as the internal
value objects, and convert once at the seam:

```python
# dataset/manifest.py
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _FileRefIn(BaseModel):
    """The wire shape of one ``files[]`` element in ``datasets.yml``.

    ``strict`` is on deliberately: this manifest is the fixity spine, and a
    ``path`` written as a list must be refused, not stringified into
    ``"['a', 'b']"`` the way ``str(raw["path"])`` did.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    path: str
    sha256: str = Field(pattern=r"^(sha256:)?[0-9a-f]{64}$")
    size: int | None = None


class _CroissantIn(BaseModel):
    """The subset of a Croissant / schema.org ``Dataset`` document we ingest."""

    model_config = ConfigDict(extra="ignore")  # published Croissant carries much more

    name: str
    alternateName: str | None = None
    version: str | None = None
    license: str | None = None
    description: str | None = None
    identifier: str | None = None
    citeAs: str | None = None
    distribution: list[_DistributionIn] = []


def entry_from_croissant(json_ld: object) -> DatasetEntry:
    """Ingest a published Croissant document into a *draft* registry entry.

    :param json_ld: The decoded document. Typed ``object`` rather than
        ``dict[str, Any]``: the value comes from ``json.loads`` on a file the
        tool did not write, and the old annotation let a JSON array reach
        ``.get()`` and traceback (audit BE-4a).
    :raises ManifestError: If the document is not a Croissant ``Dataset`` shape.
    """
    try:
        doc = _CroissantIn.model_validate(json_ld)
    except ValidationError as exc:
        raise ManifestError(f"croissant: {_render(exc)}") from exc
    ...
```

with one shared renderer so Pydantic's error text never leaks as-is:

```python
def _render(exc: ValidationError) -> str:
    """Render a `ValidationError` as one actionable line per bad field.

    Pydantic's own ``str(exc)`` carries a URL and a model class name that mean
    nothing to a researcher editing YAML; this names the field path and the
    problem, which is what the rest of this package's messages do.
    """
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or '<document>'}: {e['msg']}"
        for e in exc.errors()
    )
```

One `_WorkIn` model with `extra="ignore"` then covers **BE-4 sites 1–4 at once**, since
`enrich_work`, `cites` and `candidate_from_work` all read the same record:

```python
class _S2Edge(BaseModel):
    """One Semantic Scholar citation edge.

    ``contexts``/``intents`` are lists in the documented schema. Typing them as
    lists here is what stops a bare string being indexed to its first character
    and recorded as the sentence a paper was cited in (audit BE-4 site 3).
    """
    model_config = ConfigDict(extra="ignore")

    contexts: list[str] = []
    intents: list[str] = []
    isInfluential: bool | None = None


class _WorkIn(BaseModel):
    """The subset of an OpenAlex work this package reads.

    ``extra="ignore"`` deliberately: a real work record carries 40+ fields we do
    not use, and a new upstream field must not break a running install. But a
    field we *do* read arriving with the wrong type is a fact about the upstream
    response, not something to coerce — `publication_year: "n.d."` must become
    ``None``, never the string.
    """
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    display_name: str | None = None
    title: str | None = None
    publication_year: int | None = None
    cited_by_count: int | None = None
    abstract_inverted_index: dict[str, list[int]] | None = None
    authorships: list[_Authorship] = []
    locations: list[_Location] = []
    best_oa_location: _Location | None = None
    primary_location: _Location | None = None
    open_access: _OpenAccess | None = None
    referenced_works: list[str] = []
```

with `model_validate` at the two entry points (`_fetch_work`, `graph.py:119`, and the
pagination loop at `graph.py:256`) — after which the `isinstance` ladders in
`acquire.py:508`, `:536`, `:562`, `:612`, `:651`, `:1320`, `:1344` become attribute
reads. Apply the same to the quarantine sidecar (BE-4 site 5), where a model is strictly
better than the five `cast()`s.

**Where stdlib remains the better answer.** Do *not* convert:

- `core/config.py:81` — the check is "is it a mapping", three lines, already correct.
- `core/keys.py:170` — already validates object-ness and per-value string-ness with a
  message naming the path and the key. A model would be equivalent, not better.
- `literature/registry.py:290` and its `_decode_*` ladder — the tolerance there is
  deliberate (unusable rows skipped, not fatal) and the error messages name the entry
  *index*, which Pydantic's default `loc` rendering would not match without the custom
  renderer above. Convert only if the renderer lands first.
- `progress/collect.py:64` (`_strings`) — its tolerance is a *deliberate* documented
  behaviour ("an author who typed `blockers: awaiting the rerun` meant exactly what
  they wrote"). A strict model here would drop a blocker, which is the one thing the
  dashboard exists to show.
- `defend/record.point_record_from_mapping` (`record.py:87`) and
  `extraction.cell_from_mapping` (`extraction.py:239`) — these already do exactly what
  a model would, with better messages, and their `resolved: bool` strictness is
  hand-tuned for a documented reason (`record.py:90`). A model would be equivalent,
  not better. If they *are* converted for uniformity, they need
  `ConfigDict(strict=True)` or Pydantic's lax mode will accept `"false"` for
  `resolved` and reintroduce the bug the docstring describes.

Dependency tradeoff for adding `pydantic>=2`: see the analysis at the end of
`plugin-tech-debt.md` → *The Pydantic reversal*. Short version: the CLI is installed
**isolated** from the consumer's environment (`resources/ensure-tooling.md`, "Notes →
Isolation"), so the "Rust-binary conflict" half of `CLAUDE.md:64` does not apply; and
the existing `pyyaml` dependency already ships a compiled C extension (`_yaml`,
3.1 MB installed here — larger than `rich`), so the "light wheel" half is already
breached.

---

### BE-10 — `dict[str, Any]` used as a de-facto schema

Strict mypy passes, but the types carry no information about the most important data
structure in the package. Counts by module (`grep -c "dict\[str, Any\]"`):

```
literature/acquire.py   42      cli.py                18      literature/graph.py     17
literature/registry.py   9      digest/artifact.py     7      dataset/manifest.py      5
check/checks.py          4      progress/collect.py    2      others                   4
```

The OpenAlex work record is threaded as an untyped `dict[str, Any]` through
`acquire.py` — `candidate_from_work:536`, `_location_urls:562`, `_landing_locations:612`,
`identity_candidates:651`, `sibling_candidates:686`, `venue_candidates:793`,
`_resolve_work:1280`, `_all_landing_urls:1320`, `_access_from_work:1344`, `_ladder:1358`,
`_accept:1650`, `_try_candidate:1693`, `_exhausted:1758`, `acquire_one:1819`. Every one
of them re-derives the shape with `isinstance` checks; a typo in a key name is invisible
to mypy and produces a silent `None` at runtime.

Same for the sweep report, which is built as a bare dict and dispatched into by string:

`defendable-science/defendable_science/literature/acquire.py:2120`
```python
    report: dict[str, Any] = {
        "complete": True, "not_attempted": 0,
        "fetched": [], "cached": [], "quarantined": [], "manual": [],
        "committable": [], "errors": [],
    }
```
`defendable-science/defendable_science/literature/acquire.py:2151`
```python
        report[outcome.bucket].append(outcome.as_json())
```

`report[outcome.bucket]` is a `KeyError` waiting on any bucket constant that is not
also a report key. The `BUCKET_*` constants (`acquire.py:859-869`) keep it correct
today, and the comment at `acquire.py:867` explains why `BUCKET_ERROR` is plural — a
naming contortion that exists only to make this string dispatch line up.

#### `cast()` as a substitute for validation — the whole-package sweep

Run down as a pattern rather than as one site. There are **six `cast()` calls in the
package**, and the split is clean:

| Site | Call | Verdict |
|---|---|---|
| `literature/acquire.py:1940` | `cast("dict[str, Any]", data["candidate"])` | **validation substitute** |
| `literature/acquire.py:1941` | `cast("dict[str, Any]", data["match"])` | **validation substitute** |
| `literature/acquire.py:1942` | `cast("str", data["rung"])` | **validation substitute** |
| `literature/acquire.py:1943` | `cast("str \| None", data["url"])` | **validation substitute** |
| `literature/acquire.py:1944` | `cast("str \| None", candidate.get("license"))` | **validation substitute** |
| `core/download.py:134` | `cast("StreamSession", requests.Session())` | **legitimate** |

So five of six are the same four lines of `confirm_quarantined` (BE-4 site 5), and the
sixth is a genuine structural-typing narrowing — `requests.Session` satisfies the
`StreamSession` Protocol but mypy cannot infer it, which is the textbook use.

The pattern is therefore **confined, not endemic** — but where it occurs it is the worst
form of it. `data` is the result of `json.loads` on a file the tool wrote and a crash may
have truncated; every one of the five casts asserts to mypy a fact that nothing checks
at runtime, on the one code path whose job is to promote unverified bytes into the
registry after human review. `cast()` here does not merely fail to help: it actively
tells the type checker to stop asking, which is why strict mypy is clean over a function
that raises `KeyError` on realistic input.

**Fix**: the runtime guard in BE-4's site-5 snippet, after which all five casts delete —
`isinstance` narrowing gives mypy the same information *and* checks it. If the sidecar
gains a Pydantic model under BE-9 instead, `model_validate` subsumes both.

Worth adopting as a standing rule, since the count is currently six: **a `cast()` over a
value that came from `json.loads`, `yaml.safe_load`, or an HTTP response is a bug**;
`cast()` is for narrowing a type the checker cannot see, not for asserting a shape the
program has not verified. A grep for `cast(` in review would keep this at one
legitimate site.

**Fix** — a `TypedDict` for the report (no new dependency, no runtime cost), and the
`_WorkIn` Pydantic model from BE-9 for the OpenAlex record:

```python
# literature/acquire.py
from typing import TypedDict


class FetchReport(TypedDict):
    """The sweep report's shape — the `literature fetch` JSON contract.

    A `TypedDict` rather than a dataclass because this *is* the emitted JSON and
    is built incrementally by bucket; typing it makes ``report[outcome.bucket]``
    checkable instead of a `KeyError` waiting on a constant nobody re-read.
    """

    complete: bool
    not_attempted: int
    fetched: list[dict[str, Any]]
    cached: list[dict[str, Any]]
    quarantined: list[dict[str, Any]]
    manual: list[dict[str, Any]]
    committable: list[dict[str, Any]]
    errors: list[dict[str, Any]]
```

and make the dispatch total instead of dynamic:

```python
_BUCKET_KEY: dict[str, Literal["fetched", "cached", "quarantined", "manual", "errors"]] = {
    BUCKET_FETCHED: "fetched", BUCKET_CACHED: "cached",
    BUCKET_QUARANTINED: "quarantined", BUCKET_MANUAL: "manual",
    BUCKET_ERROR: "errors",
}
```

---

### BE-11 — Injectable-callable fields typed `object`, forcing four `type: ignore[operator]`

`defendable-science/defendable_science/core/http.py:144`
```python
    sleep: object = time.sleep
    clock: object = time.monotonic
```

Every use then needs a suppression — `core/http.py:265`, `:270`, `:271`, `:361`:

```python
        now: float = self.clock()  # type: ignore[operator]
```

Four of the package's eight `# type: ignore` comments come from this one pair. The
annotation is presumably a workaround for mypy treating a `Callable`-annotated class
attribute with a function default as a method. The standard fix keeps full typing:

```python
from collections.abc import Callable
from dataclasses import dataclass, field

@dataclass
class HttpClient:
    ...
    #: Sleep function for backoff and throttling (injectable for tests).
    sleep: Callable[[float], None] = field(default=time.sleep)
    #: Monotonic clock for the proactive throttle (injectable for tests).
    clock: Callable[[], float] = field(default=time.monotonic)
```

`field(default=…)` on a dataclass stores the function in the instance `__dict__`, so it
is never bound as a method, and mypy accepts the call sites with no suppression. The
other two `type: ignore`s in `http.py`'s vicinity disappear with it.

The remaining suppressions are: `cli.py:133`/`:154` (`Typer.command` override — genuine
and unavoidable), `cli.py:2030` (below), and `cli.py:2526` (BE-13).

`defendable-science/defendable_science/cli.py:2026`
```python
    if level not in ("hypothesis", "paper"):
        typer.echo(f"--level must be 'hypothesis' or 'paper', got {level!r}", err=True)
        raise typer.Exit(code=2)
    resolved = path or _resolve_backlog(level)
    return resolved, backlog_mod.Backlog.load(resolved, level)  # type: ignore[arg-type]
```

The validation is right there; mypy just cannot narrow `str` to `Level`. Use a
`TypeGuard` and the ignore goes away:

```python
def _is_level(value: str) -> TypeGuard[backlog_mod.Level]:
    """Narrow a raw ``--level`` to the two the backlog module accepts."""
    return value in ("hypothesis", "paper")
```

Also note `warn_unused_ignores = false` (`pyproject.toml:94`) — see BE-16 — means a
suppression that stops being necessary is never reported.

---

### BE-12 — Layout constants duplicated outside `scaffold/layout.py`

`scaffold/layout.py:1` states it is "The single definition of the consumer content
layout". It is not, for the accountability log:

`defendable-science/defendable_science/defend/record.py:34`
```python
DEFAULT_LOG_DIR = Path("docs/research/defend-log")
```

`Layout` has no `defend_log` property, so all three CLI call sites reach into this
constant and take *only its last component*, discarding the `docs/research` prefix that
would contradict a configured `research_root`:

`defendable-science/defendable_science/cli.py:1907`
```python
    log_root = (
        Path(log_dir)
        if log_dir is not None
        else layout.research_root / record_mod.DEFAULT_LOG_DIR.name
    )
```

Repeated verbatim at `cli.py:2908` and `cli.py:3311`, the latter two reading it through
a re-export (`digest/artifact.py:39`) so the same constant is reachable by two names.
The `.name` trick works only because the constant's first two components happen to equal
`DEFAULT_RESEARCH_ROOT` (`layout.py:31`); change either and they silently disagree.

**Fix** — one property, three call sites collapse:

```python
# scaffold/layout.py — on Layout
    @property
    def defend_log(self) -> Path:
        """The append-only accountability log every examination writes into.

        Under ``research_root``, not the repo root: it is research evidence, and
        a repo that moved its research tree moves its evidence with it.
        """
        return self.research_root / "defend-log"
```

Then `record.DEFAULT_LOG_DIR` is deleted (the `record()` keyword already has no sane
default outside a layout — make `log_dir` required), and each CLI site becomes
`Path(log_dir) if log_dir is not None else layout.defend_log`.

Second instance: the containment rule is written twice, and the second copy says so.

`defendable-science/defendable_science/cli.py:357`
```python
    # Same containment rule as `_relative` in scaffold/layout.py: a relative
    # value must stay inside the repository.
    if resolved != repo_root and repo_root not in resolved.parents:
```
versus `defendable-science/defendable_science/scaffold/layout.py:242`
```python
    if resolved != repo_root and repo_root not in resolved.parents:
```

They differ in one respect that matters: `layout._relative` refuses an absolute path
outright (`layout.py:238`), `cli._repo_relative` honours it (`cli.py:353`). That
divergence is deliberate and documented (`cli.py:341`) — but it is the kind of
divergence that only stays deliberate while both copies are read together. Extract the
shared predicate to `core/`:

```python
# core/paths.py
def within(repo_root: Path, resolved: Path) -> bool:
    """Return whether `resolved` is `repo_root` or lies under it."""
    return resolved == repo_root or repo_root in resolved.parents
```

Third instance: `dataset/manifest.py:301` and `:339` both default `path` to the string
literal `"datasets.yml"`, which duplicates `layout.DEFAULT_DATASETS_MANIFEST`
(`layout.py:32`). No caller uses the default, so it is latent rather than active.

---

## Low

### BE-13 — `keys check` shadows the top-level `check` command at module scope

`defendable-science/defendable_science/cli.py:599`
```python
@app.command()
def check(
```
`defendable-science/defendable_science/cli.py:2526`
```python
@keys.command()  # type: ignore[no-redef]
def check() -> None:  # noqa: F811
```

Both suppressions exist to silence the collision rather than to resolve it. Typer is
unaffected (each is registered on a different group before the rebind), but
`defendable_science.cli.check` at import time is the *keys* one, so any future
programmatic reference, doc-generation walk, or test that imports the symbol gets the
wrong command. `tools/build_docs_site.py` walks the Typer tree rather than the module
namespace today, which is the only reason this has not bitten.

**Fix** — name the function for what it is and keep the CLI name in the decorator:

```python
@keys.command("check")
def keys_check() -> None:
    """Report presence/absence and source of each key as JSON (never a value)."""
```

Both suppressions delete. Note that the sibling commands already follow this
convention (`lit_fetch`, `lit_confirm`, `extract_axes`, `list_keys`, `set_`, `list_`),
so this is one straggler, not a pattern.

---

### BE-14 — Unescaped title interpolated into an OpenAlex filter expression

`defendable-science/defendable_science/literature/acquire.py:713`
```python
    page = client.get_json(
        f"{OPENALEX}/works",
        {"filter": f"title.search:{entry.title}", "per-page": str(SEARCH_LIMIT)},
    )
```

`entry.title` comes from the human's `references.json`. OpenAlex's `filter` grammar
uses `,` for AND and `|` for OR, so a title containing either — *extremely* common:
"Deep Learning, Revisited", "A|B testing" — produces a filter expression the caller
did not intend. The failure mode is not a crash: it is a **different query**, silently
returning different siblings or none, which routes a paper to the `manual[]` worklist
that rung 4 could have found.

No test covers it — `grep -rn "title.search" tests/` returns nothing. This is the
"legitimately empty vs. we asked the wrong question" distinction the module is
otherwise scrupulous about (`acquire.py:1758` `_exhausted` exists for exactly that).

**Fix** — strip the two delimiters before interpolating, and say why:

```python
#: OpenAlex's `filter` grammar reserves `,` (AND) and `|` (OR); a title carrying
#: either would be parsed as two filters. `title.search` is a full-text match, so
#: dropping them narrows nothing that matters — and the gate re-checks the title
#: on the real record anyway.
_FILTER_RESERVED = re.compile(r"[,|]")

    search = _FILTER_RESERVED.sub(" ", entry.title)
    page = client.get_json(
        f"{OPENALEX}/works",
        {"filter": f"title.search:{search}", "per-page": str(SEARCH_LIMIT)},
    )
```

with a test asserting that a comma-bearing title still finds its sibling.

Related, lower still: `venue_candidates` calls `template.format(**fields)` on a
consumer-supplied template (`acquire.py:846`). The `except (KeyError, IndexError,
ValueError)` at `:847` covers malformed templates, and `fields` holds only strings, so
there is no attribute-traversal exposure. A pathological width spec
(`{doi:>999999999}`) could allocate a large string; the template is the operator's own
config, so this is noted for completeness rather than as a recommendation.

---

### BE-15 — God modules: quantified, and *not* the problem it looks like

The three largest modules are big, but their *functions* are not:

| Module | LOC | Top-level defs | Max McCabe |
|---|---|---|---|
| `cli.py` | 3,537 | 38 commands + 34 helpers | ≤ 10 |
| `literature/acquire.py` | 2,350 | 46 | ≤ 10 |
| `check/checks.py` | 2,136 | 40 | ≤ 10 |

`uv run ruff check --select C901 --config 'lint.mccabe.max-complexity=10'` reports
**zero** violations across the package; lowering the threshold to 6 surfaces 26. So
the size is docstring-dense composition of small functions, not tangled logic. Roughly
half of `cli.py`'s bulk is MyST docstrings, several of which are 40+ lines of genuine
design rationale (`cli.py:2694-2730`, `cli.py:3240-3289`).

The one structural cost that *is* real: `cli.py` mixes four unrelated
responsibilities that would be independently testable if split —

1. config/layout resolution helpers (`cli.py:261-458`, ~200 lines, 9 functions)
2. output shaping (`_emit_row:2033`, `_emit_record_report:2798`, `_emit_sample_report:3145`)
3. per-group command bodies
4. the `DocstringTyper` help-text machinery (`cli.py:62-172`)

**Proposed split boundaries** (no rewrite, pure code movement):

- `cli/_config.py` ← `_load_config_or_exit`, `_explicit_root_or_exit`, `_layout_or_exit`,
  `_repo_relative`, `_cache_root`, `_lit_block`, `_lit_str`, `_rps_from_config`,
  `_lit_acquisition`, `_lit_mirror`, `_lit_registry_paths`, `CacheDirError`
- `cli/_help.py` ← `_role_target`, `_strip_inline_roles`, `_prose_only`, `DocstringTyper`
- `cli/_emit.py` ← the three report emitters and the envelope helper `api-tech-debt.md`
  API-1 proposes
- `cli/{literature,dataset,digest,backlog,keys}.py` ← one `DocstringTyper` sub-app each,
  registered from `cli/__init__.py`

That leaves `cli/__init__.py` at roughly 300 lines of composition. Do this **only if**
the file becomes hard to navigate in practice; it is not currently causing defects, and
the priority-ordered items above are worth more.

`acquire.py` divides cleanly along its own section comments — `# --- rungs`,
`# --- outcome buckets`, `# --- the sweep`, `# --- verify`, `# --- mirror` — into
`acquire/ladder.py`, `acquire/gate.py`, `acquire/sweep.py`, `acquire/fixity.py`. Same
caveat.

**Import graph: no cycles.** The one near-cycle is acknowledged and correctly handled —
`progress.collect` imports `check.checks` at module scope (`progress/collect.py:29`),
and `check.checks._check_dashboard_consistency` imports `progress.collect` *inside the
function* with a comment saying why (`check/checks.py:1732`). Everything else is a
strict `cli → {front-ends} → core` layering.

---

### BE-16 — `warn_unused_ignores = false` + `ignore_missing_imports = true` weaken strict mypy

`defendable-science/pyproject.toml:85`
```toml
ignore_missing_imports = true
```
`defendable-science/pyproject.toml:94`
```toml
warn_unused_ignores = false
```
`defendable-science/pyproject.toml:98`
```toml
disallow_any_unimported = false
```

`strict = true` (line 81) is set, and then three of its guarantees are individually
switched back off. Concretely:

- `pooch` is untyped, so `pooch.retrieve` (`dataset/retrieval.py:59`) returns `Any` and
  `Path(got)` at `:65` is unchecked. That is the *only* real Tier-B fetch path and it
  also carries `# pragma: no cover` (`retrieval.py:50`), so neither the type checker nor
  the test suite constrains it. See `coverage.md`.
- `warn_unused_ignores = false` means the eight `# type: ignore` comments are never
  re-validated; several (BE-11) are already removable.

**Fix** — narrow the escape hatches rather than dropping them:

```toml
warn_unused_ignores = true

[[tool.mypy.overrides]]
# pooch ships no type information. Scope the exemption to it instead of the
# whole dependency graph, so a future untyped import is a decision, not a default.
module = ["pooch.*"]
ignore_missing_imports = true
```

and delete the global `ignore_missing_imports = true`. Expect a handful of new errors
in `dataset/retrieval.py` on the first run; they are the point.

---

## Positive patterns to preserve

These are load-bearing and should survive any refactor.

1. **Failure honesty is implemented, not just stated.** The distinction between
   "we could not ask" and "the answer is no" is a real, tested type distinction in three
   independent layers: `MirrorUnreachableError` vs. a `False` return keyed on rclone's
   exit code (`core/mirror.py:40`, `:160-172`); `DownloadError.hard_miss` keyed on
   404/410 vs. everything else (`core/download.py:71`); `RateLimitError` as a distinct
   subclass so a throttle can never be recorded as a miss (`core/http.py:52`). The
   payoff is `_exhausted` (`literature/acquire.py:1758`), which buckets an exhausted
   ladder as `manual` only when nothing was *blocked*, and `AuditReport.mirror_present:
   dict[str, bool | None]` (`dataset/retrieval.py:250`), where `None` genuinely means
   unknown. Almost nothing at this scale gets this right.

2. **Explicit, injectable seams.** `Probe` (`check/probe.py:13`), `Session` /
   `Response` (`core/http.py:61`, `:78`), `StreamSession` (`core/download.py:118`),
   `Runner` (`core/mirror.py:83`), `GitRunner` (`core/keys.py:355`), `SearchClient` /
   `MirrorClient` (`literature/acquire.py:53`, `:79`), `TierBFetcher`
   (`dataset/retrieval.py:44`). All structural `Protocol`s, all narrow. CLAUDE.md's
   claim that the kernels are injectable holds; the only residual coupling is
   `Path.cwd()` reached via `find_repo_root` (`core/config.py:74`) and the `repo_root`
   defaults at `dataset/retrieval.py:157` and `:212`, all of which the CLI overrides.

3. **Surgical, comment-preserving writers.** `core/frontmatter.set_field`
   (`frontmatter.py:102`) edits one key and refuses rather than destroying an
   annotation it cannot round-trip (`frontmatter.py:158`). `registry.patch_triage`
   (`registry.py:695`) refuses a sidecar carrying comments, non-mapping rows, or any
   YAML anchor — with `_alias_groups` (`registry.py:651`) walking the *composed node
   graph* rather than the constructed objects, precisely to avoid false-positiving on
   interned scalars. That comment (`registry.py:657-663`) is the single best piece of
   reasoning in the codebase.

4. **Refusal over silent repair.** `_refuse_unvalidated` (`digest/artifact.py:451`),
   `_check_verdict` (`digest/artifact.py:421`), refetch drift (`acquire.py:1532`),
   `_write_quarantine` writing nothing to the registry (`acquire.py:1043`),
   `scaffold_paper` refusing an existing root (`exploration/backlog.py:599`). The tool
   consistently prefers an actionable stop to a plausible guess.

5. **Every error message carries a remedy.** Not a single bare "invalid input" in the
   package. `Finding.remedy` is a required field of the model (`check/model.py:36`),
   and the free-text errors follow the same discipline —
   `frontmatter.py:158`, `registry.py:770`, `acquire.py:1258`, `cli.py:1325`,
   `core/config.py:52`.

6. **Rate-limit politeness is proactive, not just reactive.** `_throttle`
   (`core/http.py:244`) paces *before* sending, per host key, with independent caps for
   OpenAlex / S2 / arXiv (`core/http.py:148-150`) sourced from each provider's published
   guidance. Most clients only implement the reactive half.

7. **Most external-input parsing is already honest — do not churn it.** BE-4's six
   sites are the exception, and it is worth being precise about how much of the surface
   is done well, because a blanket "add validation everywhere" would damage more than it
   fixed. These five sites are the standard the six should be brought up to:

   - `core/keys.py:170` — checks the JSON is an object *and* that every value is a
     string, and raises a `ValueError` naming the resolved path and the offending key.
     A missing store is `{}`; a malformed one is an error. Absent ≠ malformed.
   - `literature/registry.py:290` — `_parse_items` distinguishes "invalid JSON" from
     "not a JSON array" with two different messages, both naming the file
     (`registry.py:301`, `:303`); `load_registry_text` then rejects a non-object entry
     and an entry with no `id`, naming the *index* (`registry.py:334`, `:337`). The
     `_decode_*` ladder beneath it (`registry.py:205-287`) is tolerant by design —
     unusable rows are skipped rather than fatal — which is right for a spine the tool
     wrote, and is documented as such.
   - `cli.py:1805` — `_parse_points` checks valid JSON, then array, then per-item
     object, then delegates to `point_record_from_mapping`
     (`defend/record.py:87`), which type-checks every field with a phrasing table
     (`record.py:77`). The comment at `record.py:90` explains why `resolved` must be
     strictly `bool`: Python truthiness would read `"false"` as `True` and drop a gap
     from the artifact's `unresolved` list. That is validation reasoned from the
     consequence of getting it wrong.
   - `cli.py:2383` — `_parse_json_object` returns `None` for both "not JSON" and "JSON
     but not an object", and the caller treats that as "the stdin was a single value",
     which is a deliberate and documented two-way branch rather than a swallowed error.
   - `cli.py:2774` — `_parse_cells` refuses an empty array explicitly, because "a run
     that recorded no cells and exited 0 would report a failed extraction as a completed
     one" (`cli.py:2758`), and prefixes every per-item error with the item index.

   `digest/extraction.py:239` (`cell_from_mapping`) belongs in this list too: it refuses
   *unknown* keys rather than dropping them, because "silently ignoring a misspelled
   `locater` would turn a typo into a cell with no locator at all, which rule 1 would
   then blame on the wrong thing" (`extraction.py:242`).

8. **Bandit is clean and the two `nosec` sites are justified.** `# nosec B404`
   (`cli.py:18`, `core/mirror.py:21`, `core/keys.py:42`) and `# nosec B603`
   (`cli.py:221`, `core/mirror.py:153`, `core/keys.py:393`) all annotate fixed-argument,
   no-shell invocations. `# nosec B405/B314` on `xml.etree` (`acquire.py:745`, `:749`)
   parses an arXiv Atom feed with `ParseError` caught at `:750`; the residual XXE
   surface is worth a follow-up note but the annotation is honest about what it is.

---

*Cross-references: the CLI/JSON contract findings are in [`api-tech-debt.md`](api-tech-debt.md);
the artifact-layer and atomicity consequences in [`data-tech-debt.md`](data-tech-debt.md);
assertion strength and the untested surfaces in [`coverage.md`](coverage.md).*
