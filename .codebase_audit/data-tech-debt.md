# The git-native artifact / data layer

**Framing.** There is no database. Persistence is **files in a git repository**:
markdown with YAML frontmatter, a CSL-JSON bibliography, a YAML triage sidecar, a
Croissant-interop dataset manifest, an on-disk HTTP response cache, a content-addressed
blob store, an out-of-repo JSON key store, and an append-only accountability log. Git
is the transaction log and the audit trail (ADR-0018).

Every category below is the original template's, mapped onto that substrate.

---

## Alembic: not applicable — and the real analogue is a genuine gap

`alembic history` / `alembic current` do not run: there is no database, no ORM, no
`alembic.ini`, and no migration directory anywhere in the repository. Recording that
plainly rather than skipping it, because the *analogue* is real and, in this repo, more
consequential than a DB migration would be. See **DATA-4**.

---

## Priority index

| # | Finding | Severity |
|---|---|---|
| DATA-1 | Multi-file writes are non-atomic and un-rolled-back; the claim lands before the evidence | **High** |
| DATA-2 | No single authoritative schema per artifact; the shape is re-implemented in four places | **High** |
| DATA-3 | Externally-derived strings flow into filesystem paths unchecked | **High** |
| DATA-4 | No artifact schema version and no migration path for already-initialised repos | **High** |
| DATA-5 | `render_table` corrupts a host document on round-trip | **High** |
| DATA-6 | Read-modify-write with no locking; two concurrent invocations silently lose one update | **Medium** |
| DATA-7 | Full-file re-read and re-write per item: O(n²) I/O on registry sweeps | **Medium** |
| DATA-8 | Every lookup is a linear scan or a full tree walk; no index | **Medium** |
| DATA-9 | The HTTP cache never expires and has no negative-caching policy | **Medium** |
| DATA-10 | Destructive overwrite of recorded evidence; git alone is the undo | **Medium** |
| DATA-11 | Four silent-data-loss doors from duplicate keys | **Medium** |
| DATA-12 | Manifest values are coerced, not validated | **Low** |
| DATA-13 | Frontmatter round-trip is not byte-preserving on CRLF | **Low** |

---

## High

### DATA-1 — Multi-file writes are non-atomic and un-rolled-back

Three commands write several files, or a file plus a registry update, with no
transaction. In each the *claim* is durable before the *evidence* is.

**(a) `defend record`.** `defend/record.py:288`:
```python
    artifact_path = Path(artifact)
    if record_understanding:
        patched = patch_understanding(...)
        artifact_path.write_text(patched, encoding="utf-8")     # 1. the claim
    transcript_path: Path | None = None
    if transcript is not None:
        transcript_path = artifact_path.with_name(f"defend-{date}.md")
        transcript_path.write_text(transcript, encoding="utf-8")  # 2.
    ...
    log_entry_path = _append_log(Path(log_dir), entry)            # 3. the evidence
```
A failure at step 3 leaves the artifact reading
`status.understanding: {"status": "ok", "unresolved": []}` with **no accountability-log
entry**. `progress` and `check` both read the frontmatter, not the log, so the false
claim reaches the dashboard. For a tool whose stated purpose is defensible claims, this
is the worst orientation the two writes could have.

**(b) `digest extract record`.** Identical shape at `digest/artifact.py:548`, plus a
second stage: `cli.py:2966` then patches `triage.yml`. That second stage *is* handled
correctly — the cells are written first deliberately, and a triage refusal is reported
under a separate `triage_not_updated[]` bucket with a `kind` discriminator
(`cli.py:2982`), reasoned out at `cli.py:2961`. Good design applied to the second
boundary and not the first.

**(c) `backlog promote --scaffold`.** `exploration/backlog.py:598`:
```python
    root = layout.paper_dir(paper_id)
    if root.exists():
        raise BacklogError(f"{root} already exists — refusing to overwrite")
    layout.hypotheses_dir(paper_id).mkdir(parents=True)
    docs_dir = layout.paper_docs_dir(paper_id)
    docs_dir.mkdir(parents=True)
    layout.backlog(paper_id).write_text(...)
    (docs_dir / "pitch.md").write_text(...)
    append_papers_registry(layout.papers_registry, paper_id, ..., backend)
```
If `append_papers_registry` raises — a `papers.md` missing a required column
(`exploration/backlog.py:533`), a duplicate `paper-id` (`:538`), a ragged table
(`:527`) — the paper tree with its two files is already on disk and unregistered.

`cli.py:2334` catches the `BacklogError` and exits 1 without saving the backlog, so the
row correctly stays `ranked`. But **the operation is not retryable**: the next attempt
hits `root.exists()` at `exploration/backlog.py:599` and refuses. The command's own
docstring claims otherwise:

`defendable-science/defendable_science/cli.py:2296`
```
    Scaffolding runs *before* the backlog is written, so a refused scaffold (the
    artifact already exists) leaves the row ``ranked`` and the operation
    retryable, never ``promoted`` with nothing on disk.
```
That holds for the `root.exists()` refusal it names, and not for the registry refusal.
The user must delete a directory by hand, with no message telling them so.

**Rollback story: there is none.** No command unwinds a partial write. The implicit
answer is `git checkout`, which fails for the common case — a repo mid-session with
other uncommitted work — and does nothing for the cache and key store, which are
gitignored.

**Fix** — order the writes so the durable-first item is the one that is safe to orphan,
and make the multi-file case reversible:

```python
# exploration/backlog.py — scaffold_paper
    root = layout.paper_dir(paper_id)
    if root.exists():
        raise BacklogError(f"{root} already exists — refusing to overwrite")
    # Reserve the registry row first. A row with no tree is a visible, fixable
    # inconsistency the author can see in `papers.md`; a tree with no row is
    # invisible to `progress` and `check`, and blocks its own retry at the
    # `root.exists()` guard above.
    append_papers_registry(layout.papers_registry, paper_id, registry_root(layout, root), backend)
    try:
        layout.hypotheses_dir(paper_id).mkdir(parents=True)
        docs_dir = layout.paper_docs_dir(paper_id)
        docs_dir.mkdir(parents=True)
        write_atomic(layout.backlog(paper_id), Backlog(...).dumps())
        write_atomic(docs_dir / "pitch.md", _PAPER_TEMPLATE.format(...))
    except OSError:
        shutil.rmtree(root, ignore_errors=True)   # nothing else wrote here yet
        remove_papers_registry_row(layout.papers_registry, paper_id)
        raise
    return root
```

For `defend record` and `write_extraction`, see BE-3 in
[`be-tech-debt.md`](be-tech-debt.md): write the log entry first, then the artifact.

**Single-file atomicity is a separate, broader gap** — 15 of 18 write sites use a plain
`write_text` on the destination with no temp-and-rename, including
`positioning.md`'s full rewrite (`cli.py:3509`), the key store (`core/keys.py:201`) and
every backlog table. Full inventory and the shared `write_atomic` helper are in BE-2.

---

### DATA-2 — No single authoritative schema per artifact

Each artifact type's shape is defined **four times**, in four languages, with nothing
tying them together.

Take the paper `decision.md` status block:

| Where | What defines the shape | File |
|---|---|---|
| **Writer** | `status.render("paper", …)` emits the field set | `defendable-science/defendable_science/scaffold/status.py:94` |
| **Template** | the literal YAML a human sees and edits | `resources/templates/paper/decision.md` |
| **Reader** | `_artifact()` reads `id`, `verdict`, `readiness`, `signed-off-by`, `load-bearing`, `covers`, `blockers`, `last-updated`, `understanding` | `defendable-science/defendable_science/progress/collect.py:310-328` |
| **Validator** | `_check_frontmatter_document` re-derives required/known fields and enums | `defendable-science/defendable_science/check/checks.py:821`, `:756`, `:796` |

Four places that must agree, and there is **no shared constant**. `_check_unknown_fields`
(`check/checks.py:756`) and `_check_enum_field` (`:796`) encode the permitted keys and
values inside the checker; `progress/collect.py` reads by string literal; the template
is hand-written markdown.

Two guards exist and they are good, but they cover only one edge of the square:

- `tests/test_status.py:121` parametrises over all nine shipped
  `resources/templates/**.md` and asserts each status block byte-matches
  `scaffold/status.render()` — **template ↔ writer**.
- `tests/test_status.py:179` pins `resources/templates/README.md`'s documented field
  set and order — **docs ↔ writer**.

Nothing pins **reader ↔ writer** or **validator ↔ writer**. Adding a field to
`status.py` and to the templates leaves `progress/collect.py` silently ignoring it and
`check/checks.py` reporting it as unknown. The `AUTHORITATIVE_DOCUMENTS` /
`STAGED_DOCUMENTS` pair (`scaffold/layout.py:36`, `:65`) is the counter-example done
right: one dict, read by `init`, `check` and `progress`, with a comment explaining why
it is written out rather than derived.

There is a fifth definition off to one side:
`skills/progress/SKILL.md:80-98` ships a 19-line copy of the status frontmatter,
byte-identical today to `resources/templates/README.md:82-100`. The README copy is
guarded by `tests/test_status.py:179`; **the skill copy is not**, so it drifts on the
next schema change.

The same four-way split applies to the registry spine — `Asset`/`AssetFile`/`License`
dataclasses (`literature/registry.py:95-118`), `asset_to_json` (`:366`), the
`_decode_*` ladder (`:205-287`), and `_check_references` (`check/checks.py:1352`) — and
to the dataset manifest.

**Fix — one Pydantic model per artifact type at the parse boundary, and generate the
rest from it.** Now sanctioned for exactly this surface:

```python
# scaffold/schema.py  (new)
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Understanding(BaseModel):
    """The block `defend record` writes and `progress` surfaces."""
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "gaps"]
    unresolved: list[str] = []


class PaperStatus(BaseModel):
    """The `status:` block of a paper-level staged document.

    One definition, four consumers: `status.render` emits it, `check` validates
    against it, `progress` reads it, and the shipped template is generated from
    it. Before this model those four were four independent transcriptions of the
    same field table, with test guards on only one of the six pairings.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: int = Field(default=1, alias="schema-version")
    id: str | None = None
    verdict: Literal["confirmed", "refuted", "inconclusive", "n/a"] | None = None
    readiness: Literal["draft", "submittable", "publish", "no-go"] | None = None
    signed_off_by: str | None = Field(default=None, alias="signed-off-by")
    load_bearing: bool = Field(default=False, alias="load-bearing")
    covers: list[str] = []
    blockers: list[str] = []
    last_updated: str | None = Field(default=None, alias="last-updated")
    understanding: Understanding | None = None
```

Then:

- `status.render()` emits `PaperStatus.model_json_schema()`'s field order — the template
  is generated, not transcribed.
- `check_frontmatter` replaces `_check_unknown_fields` / `_check_enum_field` with
  `PaperStatus.model_validate(block)` and maps each `ValidationError` entry onto a
  `Finding`, keeping the existing severity model (`check/model.py:26`) and the remedy
  text — which is the part worth preserving.
- `progress/collect.py` reads typed attributes instead of `status.get("verdict")`.

**Important caveat.** `progress/collect.py`'s tolerance is *deliberate* and must
survive: `_strings` (`progress/collect.py:64`) accepts `blockers: awaiting the rerun`
as a one-element list because "dropping it because the YAML type was not the expected
one would hide a blocker, which is the one thing the dashboard exists to show". Use
`model_validate` in `check` (strict, reports the problem) and keep the tolerant reader
in `progress` (never drops data). Two readers with two jobs, one schema — not one
strict reader that silently discards.

Tracking: this reverses `CLAUDE.md:64`; the reconciliation is filed as **#169** (see
[`plugin-tech-debt.md`](plugin-tech-debt.md)).

---

### DATA-3 — Externally-derived strings flow into filesystem paths unchecked

Cross-reference: **BE-1** in [`be-tech-debt.md`](be-tech-debt.md) has the full analysis
and the reproduction. Summarised here because it is a property of the *storage layer*,
not just of one function.

`Layout` derives every artifact path by interpolating an identifier with no validation
— `digest()` (`scaffold/layout.py:144`), `paper_dir()` (`:179`), `backlog()` (`:183`),
`positioning()` (`:195`), `hypothesis_dir()` (`:199`) — and
`append_log_entry` does the same for the log filename (`defend/record.py:343`). The
identifiers come from a CSL-JSON `id`, a `--cells` JSON payload, or `backlog --id`.

**Reproduced**: a cell whose citekey is `../../../../../../tmp/dsaudit/PWNED` caused
`digest extract record` to create `/tmp/tmp/dsaudit/PWNED.md` outside the work tree,
creating intermediate directories on the way.

The same repository already enforces this rule in three other places —
`acquire._safe_name` (`literature/acquire.py:1019`), `layout._relative`
(`scaffold/layout.py:241`), `cli._repo_relative` (`cli.py:359`) — which is why this is
an inconsistency finding rather than an oversight.

**Related, unfixed in the dataset layer**: `_validate_files`
(`dataset/manifest.py:386`) checks that `path` is non-empty and that the checksum
matches `SHA256_RE`, and nothing else. A Tier-A entry with `path: ../../etc/passwd`
loads with **zero validation errors**, and `retrieval._resolve_file`
(`dataset/retrieval.py:96`) then joins it to `repo_root`:

```python
    if entry.tier == "A":
        repo_path = Path(ref.path)
        if not repo_path.is_absolute():
            repo_path = repo_root / repo_path
        if verified(repo_path, ref.sha256):
            return repo_path
```

The checksum gate makes this read-only and mostly harmless in practice — you can only
"fetch" a file whose SHA-256 you already knew. But `dataset verify` will then report
that out-of-tree path as `verified`, and the manifest is a file a collaborator sends
you. Add the containment check to `_validate_files`, where the other manifest rules
live.

**Unsafe deserialisation: none.** Every YAML load is `yaml.safe_load` —
`core/config.py:92`, `literature/registry.py:506`, `dataset/manifest.py:312`,
`progress/collect.py:456`, `digest/artifact.py:329` — plus `yaml.compose(...,
Loader=yaml.SafeLoader)` at `registry.py:684`. `yaml.load` appears nowhere. All dumps
are `yaml.safe_dump`. There is no zip/tar extraction anywhere in the package, so
zip-slip does not apply. rclone is invoked with a fixed argv list and no shell
(`core/mirror.py:132`), so argument injection does not apply. The one XML parse
(`literature/acquire.py:745`) uses `xml.etree` with `# nosec B405/B314` on a feed from
a known host and catches `ParseError`; hardening it against entity expansion with
`defusedxml` is a reasonable follow-up but not a live exposure at Atom-feed scale.

---

### DATA-4 — No artifact schema version, and no migration path

Alembic is not applicable. The analogue is: **what happens to a researcher's existing
artifacts when the schema moves?**

**There is no schema-version field on any artifact.** Grep confirms: no
`schema-version`, `schema_version` or `apiVersion` in `resources/templates/**` or in
`scaffold/status.py`. The one exception proves the point — the registry spine *does*
carry one:

`defendable-science/defendable_science/literature/registry.py:26`
```python
#: Spine schema version, so a future migration need not guess.
SCHEMA = 1
```
written at `registry.py:376`, read at `:277`. Nothing consumes it: no code branches on
`asset.schema`, and there is no migration to guess for. So the mechanism exists in
exactly one place, is unused, and is absent from the artifacts that actually matter
(the frontmatter of every hypothesis, paper and thesis document).

**There is no migration or upgrade command.** The CLI has no `migrate`, no `upgrade`,
no `--fix`. `init` explicitly refuses to touch existing files:

`defendable-science/defendable_science/cli.py:516`
```
    **Existing files are never overwritten** — a file already there is reported
    ``exists`` and left exactly as the author wrote it, which is why there is no
    ``--force``: re-running only fills the gaps.
```
That is the right default. It also means `init` is not, and cannot become, the upgrade
path: re-running against a repo scaffolded by an older version fills gaps and leaves
every stale field in place.

**What `research-init adopt` does with pre-existing files**: `adopt` is a *skill* mode
(`skills/research-init/SKILL.md:36`), not a CLI command — the tree has no `adopt`
(confirmed against the live Typer tree). It resolves to the same
`defendable-science init` plus human judgement about where things go, so the same
gap-filling semantics apply.

**What `check` does with an artifact written by an older package version.** This is the
concrete failure. `_check_unknown_fields` (`check/checks.py:756`) reports any field it
does not recognise. So:

- a field **removed** in a new version → every existing artifact reports `invalid`, and
  `check` exits 1, on a repo the researcher has not touched;
- a field **added** → `_required` reports it missing on every existing artifact;
- a field whose **semantics changed** → nothing at all is reported. The old value is
  read as if it meant the new thing. For a field like `readiness` or `signed-off-by`
  this silently changes what a dashboard and a defensibility gate assert.

The third is the dangerous one, and it is precisely the failure the repo's own
failure-honesty rule exists to prevent — applied to time rather than to network errors.

**This has already happened once.** `CHANGELOG.md`'s `[Unreleased]` section records
that `progress dashboard` grew `scaffold.status.SIGNED_READINESS` and that "`check`
grew the matching rule, which its `verdict: n/a` exemption had been hiding". A
sign-off rule changed meaning. There is no note about what that does to a thesis
artifact written the week before, and no version on the artifact to tell them apart.

**Fix** — add the field now, while there is one schema version to declare:

```python
# scaffold/status.py
#: The artifact frontmatter schema version. Bumped when a field is removed or
#: given new semantics — never for a purely additive change, which an older
#: reader ignores harmlessly. Written into every scaffolded artifact so a future
#: `migrate` has something to branch on rather than a guess, and so `check` can
#: say "written by an older version" instead of "invalid".
SCHEMA_VERSION = 1
```

emitted by `status.render()` into every template, with three consequences:

1. `check` distinguishes three cases instead of one — *current and invalid*
   (`invalid`, exit 1), *older schema* (a new `outdated` severity, exit 0, remedy
   "run `defendable-science migrate`"), *newer schema* (`unreadable`, exit 1: this CLI
   cannot know what the fields mean, and guessing is the one thing it must not do).
2. `_check_unknown_fields` stops firing on old artifacts.
3. A `migrate` command becomes writable, with the same posture as the rest of the tool:
   `--dry-run` by default, per-file report, never touching a file it cannot parse, and
   atomic writes (BE-2).

Until then the honest interim is a documented statement in
`resources/templates/README.md` that artifact schemas are unversioned and that a
package upgrade may require hand-editing — which is at least true, and is not currently
said anywhere.

---

### DATA-5 — `render_table` corrupts a host document on round-trip

Every markdown table this tool writes — the two backlogs, `papers.md`, the concept
matrix in `positioning.md` — goes through one renderer, and it escapes data cells but
not header cells.

`defendable-science/defendable_science/core/mdtable.py:443`
```python
def render_table(header: list[str], rows: list[Row]) -> str:
    """Render `rows` as a GFM table in `header`'s column order."""
    lines = [
        "| " + " | ".join(header) + " |",              # <-- raw
        "|" + "|".join("---" for _ in header) + "|",
    ]
    lines.extend(
        "| " + " | ".join(escape_cell(row.get(c, "")) for c in header) + " |"
        for row in rows                                 # <-- escaped
    )
```

`escape_cell` (`core/mdtable.py:117`) exists and is correct; line 446 does not call it.
`split_cells` un-escapes on the way in, so a header cell containing an escaped pipe is
parsed correctly and then re-emitted unescaped.

**Reproduced:**

```
input:            | a \| b | c |
                  |---|---|
                  | 1 | 2 |

parsed header:    ['a | b', 'c']            # 2 columns, correct
round-tripped:    | a | b | c |             # 3 columns — escape dropped
re-parse:         TableError: ragged t row: 2 cells, header has 3 (['1', '2'])
```

So `backlog add` on a table whose header contains a pipe writes a file that the very
next `backlog list` cannot read. The document is corrupted in place, silently, by a
successful command. `Backlog.save` (`exploration/backlog.py:242`) is a plain
`write_text`, so there is no `.tmp` and no prior copy — see DATA-1.

A pipe in a header is unusual but not exotic: `| metric (a\|b) |`, `| P(y\|x) |`.

**Fix** — one call:

```python
    lines = [
        "| " + " | ".join(escape_cell(c) for c in header) + " |",
        ...
```

and a round-trip property test, which is the class of test that would have caught it:

```python
@pytest.mark.parametrize("cell", ["a | b", "a\\b", "a\nb", "|", ""])
def test_table_round_trips_pathological_headers(cell):
    """`parse(render(x)) == x` — the invariant every writer here depends on."""
    src = splice("", "", [cell, "c"], [{cell: "1", "c": "2"}])
    doc = parse_document(src, row_label="t")
    assert doc.header == [cell, "c"]
```

---

## Medium

### DATA-6 — Read-modify-write with no locking

`grep -rn "fcntl\|filelock\|LOCK_EX\|threading.Lock\|multiprocessing" defendable_science/`
returns **zero hits**. There is no locking anywhere; concurrency safety rests entirely
on `Path.replace` being atomic.

That is sufficient for the two content-addressed stores — the HTTP cache
(`core/http.py:169`) and the blob store (`literature/acquire.py:1086`) — where the
destination is derived from the bytes, so a racing writer writes identical content.
`_store_blob`'s comment says exactly this (`literature/acquire.py:1089`).

It is **not** sufficient for the four read-modify-write files:

| File | Writer | Race |
|---|---|---|
| `references.json` | `patch_asset` (`literature/registry.py:432`) | reads all items, mutates one spine, rewrites all. Two concurrent `literature fetch` runs → the second's rewrite discards the first's spine. |
| `triage.yml` | `patch_triage` (`literature/registry.py:695`) | same shape. Called in a loop by `digest extract record` (`cli.py:2968`). |
| the key store | `set_key`/`unset_key` (`core/keys.py:205`, `:217`) | load → mutate → full rewrite (`core/keys.py:212`). Concurrent `keys set` loses one key. Also non-atomic — see BE-6. |
| any backlog table | `Backlog.load` … `save` (`exploration/backlog.py:225`, `:240`) | the CLI loads, mutates, saves across a whole command. |

There is also a scratch-file collision: `_land_bytes` writes every download to a
per-citekey path (`literature/acquire.py:1456`):
```python
    dest = ctx.cache_dir / "incoming" / f"{_safe_name(entry.citekey)}.part"
```
Two `literature fetch` runs on the same citekey — a rerun after a hang, say — write the
same `.part` concurrently, and whichever finishes second gets hashed.

Finally, `append_log_entry`'s `while target.exists(): … write_text`
(`defend/record.py:345`) is a check-then-write race **on the append-only audit log**;
see BE-3 for the `open("x")` fix.

Nothing documents a single-writer constraint, and no test runs two invocations against
one repo.

**Fix** — a small advisory lock around the four RMW writers is proportionate and needs
no new dependency:

```python
# core/lockfile.py
import fcntl
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def exclusive(target: Path, *, timeout: float = 30.0):
    """Hold an advisory lock on a sibling ``.lock`` while `target` is rewritten.

    Only the read-modify-write files need this — `references.json`, `triage.yml`,
    a backlog table, the key store — where a second process's rewrite would
    discard the first's update. The content-addressed stores do not: their
    destination is derived from the bytes, so a racing writer writes the same
    thing.
    """
    lock = target.with_name(target.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)   # add a timeout via signal or a poll loop
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
```

`fcntl` is POSIX-only. If Windows support is intended (the classifiers say 3.11–3.14
but name no OS), an `os.open(..., O_CREAT | O_EXCL)` sentinel with a stale-lock timeout
is the portable alternative. Either way, the honest minimum is to **document the
single-writer constraint** in `resources/ensure-tooling.md` and have the skills not
parallelise these commands.

---

### DATA-7 — Full-file re-read and re-write per item

`patch_asset` re-reads and re-parses the **entire** `references.json`, then re-serialises
and rewrites all of it, for every single entry:

`defendable-science/defendable_science/literature/registry.py:456`
```python
    target = Path(path)
    items = _read_items(target)          # full read + json.loads
    index = _locate(items, citekey)      # linear scan
    ...
    tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", …)
    tmp.replace(target)
```

It is called once per bound entry from `_bind` (`literature/acquire.py:1621`), which
`fetch_all` drives over the whole registry (`literature/acquire.py:2140`). So a
`literature fetch --all` over an *n*-entry registry performs **n full parses and n full
rewrites** of an *n*-entry file — O(n²) bytes. For 400 papers with a populated spine
(~2 KB/entry, so ~800 KB) that is ~320 MB of I/O churn, and 400 opportunities for the
race in DATA-6.

`patch_triage` is the same shape (`literature/registry.py:766-814`) and additionally
runs `_alias_groups` — a full `yaml.compose` plus a graph walk (`registry.py:651`) —
on every call. `cli.py:2966` calls it once per recorded paper.

**Fix** — a batch writer beside the single one, used by the sweep:

```python
def patch_assets(path: str | Path, assets: Mapping[str, Asset]) -> None:
    """Replace many entries' spines in one read-modify-write.

    `patch_asset` is right for a single human-driven acquisition; a sweep over an
    n-entry registry calling it n times re-parses and rewrites the whole file n
    times, which is O(n²) and gives a concurrent writer n chances to interleave.
    """
    target = Path(path)
    items = _read_items(target)
    by_id = {_opt_str(i.get("id")): n for n, i in enumerate(items) if isinstance(i, dict)}
    for citekey, asset in assets.items():
        index = by_id.get(citekey)
        if index is None:
            raise RegistryError(f"no entry {citekey!r} in the registry")
        ...
    write_atomic(target, json.dumps(items, indent=2, ensure_ascii=False) + "\n")
```

`fetch_all` accumulates `{citekey: asset}` and flushes once. That does change one
property worth naming: today a sweep interrupted at entry 200 has 200 spines on disk;
with a single flush it has none. Flush per batch of ~25 rather than once, so an
interruption loses at most a batch and the bytes are still cached (`_bind`'s error path
already says "the bytes are in the cache, so re-run", `literature/acquire.py:1631`).

---

### DATA-8 — Every lookup is a linear scan or a full tree walk

There is no index of any kind. Nothing is memoised across a command.

| Lookup | Implementation | Cost |
|---|---|---|
| citekey → entry | `Registry.get` — linear scan (`literature/registry.py:159`) | O(n); called per key inside `_select`'s loop (`literature/acquire.py:2071`) → **O(n²)** for `--all` |
| citekey → item index | `_locate` — two linear scans (`literature/registry.py:420`, `:423`) | O(n) per `patch_asset` |
| dataset id → entry | `_entry_or_exit` — linear scan (`cli.py:1631`) | O(n), once per command |
| dataset id → entry | `emit` — a second, separate scan (`cli.py:1594`) | O(n) |
| all staged documents | `staged_documents` — glob per document name (`check/checks.py:723`) | full tree walk, **×3 per `check`** (BE-8) |
| extraction batch | `layout.digests_dir.glob("*.md")` + read + parse each (`cli.py:3026`) | full read of every digest, per `sample`/`render` |
| backlog row → row | `Backlog.get` — linear scan (`exploration/backlog.py:249`) | O(n) |

**Growth to a realistic consumer.** A three-year PhD portfolio is plausibly 8 papers ×
4 hypotheses ≈ 100 staged documents, a 400-entry bibliography, and 200 digest
artifacts. Then:

- `defendable-science check` — 3 tree walks, ~300 file reads, ~300 YAML parses.
- `literature fetch --all` — 400 `Registry.get` scans over 400 entries (160,000
  comparisons, cheap) plus DATA-7's 400 full parses and rewrites (not cheap).
- `digest extract sample --all` — reads and parses all 200 digests to determine
  membership (`cli.py:3026`), then reads the drawn ones **again** (`cli.py:3073`).
- `digest extract render` — the same 200 reads a third time (`cli.py:3411`).

None of this is fatal; all of it is avoidable with per-run memoisation rather than a
persistent index.

**Fix — memoise within a run, do not build an index file.** A cache file is the wrong
answer here: it would be a second source of truth for data whose whole point is that
git is the source of truth, and a stale index in an integrity tool is worse than a slow
scan.

```python
# literature/registry.py — on Registry
    def __post_init__(self) -> None:
        self._by_citekey = {e.citekey: e for e in self.entries}

    def get(self, citekey: str) -> Entry | None:
        """Return the entry with this citekey, or ``None``.

        Indexed at load: `_select` calls this once per key over the whole
        registry, so the linear scan it replaced was quadratic on a sweep.
        """
        return self._by_citekey.get(citekey)
```

plus `CachingProbe` for the `check`/`progress` walks (BE-8), and a single
`read_cells` pass in `digest extract sample`/`render` whose result is threaded through
rather than re-read.

---

### DATA-9 — The HTTP cache never expires and has no negative-caching policy

`defendable-science/defendable_science/core/http.py:155`
```python
    def _cached(self, key: str) -> JsonValue | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / f"{key}.json"
        if path.is_file():
            try:
                data: JsonValue = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
            return data
        return None
```

Assessed against the template's categories:

- **TTL / expiry: none.** No mtime check, no max-age, no `--refresh` flag on any
  command. An OpenAlex record cached today is served unchanged in a year. The module
  docstring frames this as intentional — "the provenance root — never silently
  refreshed within a run" (`core/http.py:4`) — and *within a run* that is exactly
  right. Across runs it is unbounded, and nothing says so to the user. There is no
  documented way to invalidate one entry; the only lever is deleting the whole
  `<cache_dir>/http` directory, which nothing tells you to do.
- **Cache-key collisions: no.** `_cache_key` (`core/http.py:92`) is
  `sha256(url + "?" + urlencode(sorted(params)))`. Sorted params make it canonical.
  One real subtlety, correctly handled: `mailto` is added to `query` *before* the key is
  computed (`core/http.py:202`, key at `:208`), so a polite-pool and an anonymous
  request are different entries. Correct — they can return different bodies.
  `get_text` is deliberately uncached (`core/http.py:223`).
- **Error responses are never cached: correct.** `_store` is only reached after
  `_fetch` returns (`core/http.py:212`), and every non-200 raises. So a 404 or a 429 is
  never poisoned into the cache. This is the single most important property of the
  three and it is right.
- **Concurrency: safe.** Temp-then-rename at `core/http.py:176`, content-addressed key,
  so a racing writer writes identical bytes. The one gap is the orphan `.tmp` on a
  failed write (BE-2), which is benign here.
- **Unbounded growth.** No size cap and no eviction. A literature sweep with
  `neighbors` caches ~100 work records per anchor at 20–50 KB each.

**Fix** — keep the within-run immutability and add the two missing levers:

```python
    #: How long a cached response stays authoritative. `None` means forever, which
    #: is the current behaviour and is right for a provenance root *within* a run —
    #: but a record cached a year ago is not evidence about the paper today, and
    #: there is presently no way to say so.
    max_age: float | None = None

    def _cached(self, key: str) -> JsonValue | None:
        ...
        if self.max_age is not None and time.time() - path.stat().st_mtime > self.max_age:
            return None
```

driven by `literature.cache_max_age` in `config.yml` (defaulting to `None`, so nothing
changes for anyone who does not set it), plus a `defendable-science literature refresh
[<identifier>]` that evicts one key or the group. Document the growth characteristic in
`skills/literature/SKILL.md` beside the existing cache note.

---

### DATA-10 — Destructive overwrite of recorded evidence

The audit trail is genuinely append-only in one place and not in the others.

**Append-only, correctly:**
- The accountability log — `append_log_entry` (`defend/record.py:320`) never reuses a
  filename, suffixing `-2`, `-3` (`defend/record.py:344`). Written by both `defend
  record` and `digest extract record`/`sample`, one trail
  (`digest/artifact.py:549`, `:667`). The docstring calls it "append-only evidence"
  (`defend/record.py:337`). Weakened only by the TOCTOU race in DATA-6 / BE-3.
- `backlog drop` records a reason and never deletes a row (`cli.py:2351`, "file-drawer
  discipline"). Exactly right.
- Quarantine — nothing reaches the registry without an explicit human `confirm`
  (`literature/acquire.py:1043`), and there is "deliberately no 'promote whatever is in
  quarantine' convenience".
- Refetch drift refuses rather than rebinding (`literature/acquire.py:1532`).

**Destructively overwritten:**

1. **`status.understanding`** — `set_field` (`core/frontmatter.py:166`) replaces the
   value in place. A second `defend record` on the same artifact overwrites the first
   verdict. The *log* keeps both, so the evidence survives; but the artifact — the thing
   `progress` and `check` read — shows only the latest. A gap resolved and later
   re-opened leaves no trace in the artifact.
2. **`status.extraction`** — `_set_extraction_key` (`digest/artifact.py:554`) and
   `write_extraction` (`digest/artifact.py:546`) replace the cells block wholesale. Re-extracting
   a paper discards the previous cells. `write_extraction`'s `in_sample=False` reset is
   deliberate and documented (`digest/artifact.py:511`, "the flag can never outlive the
   cells it certified") — good — but the superseded cells themselves are simply gone.
3. **`dashboard.md`** — rewritten wholesale by design (`cli.py:729`, "a pure
   projection … a hand-edit is (correctly) discarded"). Correct, and not a finding.
4. **`positioning.md`'s matrix** — `render_matrix` re-emits the table
   (`cli.py:3507`). The command is careful about *deletion* ("Nothing is ever deleted",
   `cli.py:3441`) but a changed cell overwrites the prior value with no record. Combined
   with DATA-5 and the non-atomic write, this is the riskiest writer in the tool.

**Is git the undo?** Partly, and the reliance is undocumented. It works for the four
artifacts above, which are tracked. It does **not** cover the cache, the blob store or
the key store, all gitignored — so `confirm_quarantined`'s
`sidecar.unlink(missing_ok=True)` (`literature/acquire.py:1959`) permanently destroys
the match record for a promoted candidate, and nothing else holds it. And it only works
if the researcher commits between examinations, which nothing enforces and no skill
requires.

**Fix** — for the two evidentiary blocks, keep a bounded history in the artifact rather
than a single value:

```yaml
status:
  understanding:
    status: gaps
    unresolved: ["the identifiability argument"]
    superseded:                      # newest first, capped at N
      - {date: 2026-08-14, status: ok, unresolved: []}
```

`set_field` already refuses to destroy an annotation it cannot round-trip
(`core/frontmatter.py:158`), which is the same instinct — this extends it from comments
to prior values. Cheaper interim: have `defend record` refuse to overwrite a *resolved*
understanding block with a different verdict unless `--supersede` is given, naming the
log entry that recorded the first one.

For the quarantine sidecar, move it to `<cache>/quarantine/<citekey>/confirmed/` rather
than unlinking it.

---

### DATA-11 — Four silent-data-loss doors from duplicate keys

Each of the four persisted formats loses data on a duplicate key, silently, in a
different way:

1. **`triage.yml` duplicate citekeys.** `yaml.safe_load` keeps the last
   (`literature/registry.py:506`); `patch_triage` then rewrites from the parsed dict
   (`registry.py:805`), so the earlier row and its PRISMA rationale vanish. This is the
   one round-trip shape with **no guard**, in a module that otherwise refuses comments
   (`registry.py:769`), non-mapping rows (`:778`) and every anchor shape (`:785`)
   precisely to avoid this class of loss.
2. **`references.json` duplicate `id`.** `_locate` returns the first
   (`literature/registry.py:421`); `load_registry_text` appends both
   (`registry.py:338`), so `Registry.get` and `_locate` can disagree about which entry
   a citekey means.
3. **Markdown table duplicate header columns.** `_checked_axes` catches this for the
   concept matrix, with an excellent comment about why the whole header must be checked
   and not just the axes (`digest/extraction.py:166-178`). `Backlog.loads`
   (`exploration/backlog.py:195`) and `append_papers_registry`
   (`exploration/backlog.py:522`) have **no** such check, and a row is a dict keyed by
   header (`core/mdtable.py`), so `| id | id |` silently collapses two cells into one.
4. **Duplicate `status:` blocks in frontmatter.** `set_field` patches the first
   (`core/frontmatter.py:126`); `yaml.safe_load` reading the same file takes the last
   (`digest/artifact.py:329`, `scaffold/status.py`). So a successful write changes
   nothing a reader sees. `set_field` already guards against a *duplicate child key*
   for exactly this reason — "a duplicate key silently shadows the value just written"
   (`core/frontmatter.py:144`) — and not against a duplicate parent block.

**Fix** — the check already written for the concept matrix, applied to the other three:

```python
# literature/registry.py — in triage_mapping, before returning
    seen: set[str] = set()
    dupes = sorted({str(k) for k in _duplicate_keys(text)})
    if dupes:
        raise RegistryError(
            f"{target}: citekeys {dupes} appear more than once — YAML keeps only "
            "the last, so a rewrite would delete the others' rationale. Merge "
            "them by hand, then re-run."
        )
```
(implemented over the composed node graph, the way `_alias_groups` already is at
`registry.py:684`, so it sees what `safe_load` collapses); the same test in
`Backlog.loads` and `append_papers_registry` against the header; and a
duplicate-`status:` check in `split_frontmatter`.

---

## Low

### DATA-12 — Manifest values are coerced, not validated

`dataset/manifest.py:226`:
```python
        path = str(raw["path"])
        sha256 = str(raw["sha256"])
```
and `_opt_str` (`manifest.py:185`) does `str(value)` on anything truthy. So:

- `id: null` → the literal string `'None'` (verified);
- `license: [a, b]` → `"['a', 'b']"` (verified), which then **passes**
  `_validate_required`'s `if not entry.license` check at `manifest.py:366`;
- `path: 12345` → `"12345"`.

The checksum is the one field with a real format check (`SHA256_RE`, `manifest.py:24`,
applied at `:386`). Everything else is stringified into something that looks valid.

Fix: covered by DATA-2's Pydantic model with `ConfigDict(strict=True)` — a `path` given
as a list is refused, not stringified. This is the clearest single case for the
sanctioned Pydantic scope: the manifest is the fixity spine, and the current parser's
tolerance is not a feature.

---

### DATA-13 — Frontmatter round-trip is not byte-preserving on CRLF

`core/frontmatter.py`'s contract is that it changes one key and leaves "every other byte
alone" (`core/frontmatter.py:4`). `split_frontmatter` uses `text.splitlines()`
(`core/frontmatter.py:32`), which consumes `\r\n`, and `rebuild` rejoins with `"\n"`
(`core/frontmatter.py:48`):

```python
    parts = ["---", *fm_lines, "---", *body_lines]
    return "\n".join(parts) + "\n"
```

So `defend record` on a CRLF artifact — a Windows collaborator, or a repo without
`core.autocrlf` — rewrites the entire file to LF. The diff shows every line changed, and
the one-key edit becomes unreviewable. The same applies to `core/mdtable.splice`.

Fix: detect the dominant terminator in `split_frontmatter` and thread it through
`rebuild`, or document that artifacts are LF-only and add a `.gitattributes` line to the
`init` scaffold (`scaffold/render.py`), which is the cheaper and probably better answer.

---

## Positive patterns to preserve

1. **Content-addressed storage with the checksum as the identity.** `blob_path`
   (`core/fixity.py`), `sha256:`-prefixed refs, `_store_blob`'s unconditional overwrite
   because "the destination is derived from the bytes, so anything already there is the
   same bytes" (`literature/acquire.py:1089`). This makes the cache and the mirror
   idempotent and concurrency-safe for free, and it is why DATA-6 is bounded to four
   files rather than everything.

2. **Verify-at-every-hop.** `_resolve_file` (`dataset/retrieval.py:68`) checks the
   SHA-256 after the cache read, after the mirror pull, and after the Tier-B fetch, and
   treats a mismatch as *absent* so the chain continues. `_resolve_recorded`
   (`literature/acquire.py:1183`) goes further and **deletes** a blob that failed
   verification, because "leaving a known-bad blob at the content-addressed path would
   have every later run re-read the same bad bytes" (`acquire.py:1196`).

3. **Surgical writers that refuse rather than round-trip.** `patch_asset` mutates one
   namespaced object and preserves unknown top-level keys, unknown `custom` sub-keys and
   key order (`literature/registry.py:433`) — so a Zotero namespace survives.
   `patch_triage` refuses a file with comments, non-mapping rows, or any anchor
   (`registry.py:769`, `:778`, `:785`) rather than silently reshaping a human's file.
   The `_alias_groups` node-graph walk (`registry.py:651`) is the most careful piece of
   parsing in the repository.

4. **Namespaced extension of a standard format.** The substrate spine lives under
   CSL-JSON's schema-designated `custom` field (`literature/registry.py:3`), so
   `references.json` stays valid CSL-JSON and round-trips through Zotero and pandoc. The
   file remains the researcher's, not the tool's.

5. **`unknown` is a first-class value.** `AuditReport.mirror_present: dict[str, bool |
   None]` (`dataset/retrieval.py:250`) — `None` means the mirror could not be reached,
   distinct from `False`. `Milestones(unknown=True)` (`progress/collect.py:422`) — the
   gate list is unknown, never an empty one. `VerifyReport.ok` returns `False` for an
   entry with nothing recorded, because "`verify --all` on a fresh registry must say
   'nothing is verified', not 'everything checks out'" (`literature/acquire.py:2198`).

6. **The layout is resolved from one module and confined to the repo.**
   `scaffold/layout.py` derives every path, `_relative` refuses a `layout:` value that
   escapes the work tree (`layout.py:241`), and `recorded_layout` (`layout.py:336`) is a
   true inverse of the resolver so a written block round-trips. `layout_from_overrides`
   (`layout.py:315`) deliberately routes `init`'s CLI options through the *same*
   validation as a config block "rather than a second copy of the rule that could drift
   from it". DATA-3 is a gap in the per-artifact derivation, not in this.

7. **Determinism where it is load-bearing.** The dashboard has no timestamp in the file
   and a total sort order (`cli.py:733`) specifically so `check`'s stale-dashboard
   comparison is meaningful, and both sides of that comparison come from `progress`
   (`check/checks.py:1707`). `select_sample` is stable across processes and is tested
   with two interpreters at different `PYTHONHASHSEED`
   (`tests/test_sampling.py:79`) — so nobody can re-roll a sample until an easy one
   comes up.

---

*Cross-references: the write-site inventory and the `write_atomic` helper are BE-2, the
traversal reproduction is BE-1, and the repeated-parse costs are BE-8, all in
[`be-tech-debt.md`](be-tech-debt.md). The JSON-shape half of DATA-2 is API-1 in
[`api-tech-debt.md`](api-tech-debt.md). Test-side gaps are in
[`coverage.md`](coverage.md).*
