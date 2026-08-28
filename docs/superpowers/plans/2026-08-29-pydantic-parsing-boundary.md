# Pydantic at the Parsing Boundary — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record ADR-0043 (Pydantic is permitted only where data *enters the process*), then adopt it across the package's JSON boundaries, fixing six verified defects — three of which are failure-honesty violations.

**Architecture:** One new module, `core/models.py`, holds two base model configs and three parse helpers, and is the **only** module in the package that imports `ValidationError`. Every boundary calls a helper and hands it its own domain error type; the helper translates Pydantic's structured errors into that type with the field path and reason. No caller ever catches `ValidationError`. Internal value objects stay stdlib `dataclasses` — Pydantic is for reading, never for emitting.

**Tech Stack:** Python 3.11+, Pydantic v2, Typer, pytest + pytest-cov (100% statement+branch gate), strict mypy, ruff.

**Spec:** [`docs/superpowers/specs/2026-08-29-pydantic-parsing-boundary-design.md`](../specs/2026-08-29-pydantic-parsing-boundary-design.md) — read it before starting; this plan argues from it.

**Issue:** [#169](https://github.com/davorrunje/defendable-science/issues/169)

## Global Constraints

- **Never commit to `main`.** Work on branch `core/pydantic-parsing-boundary`, already created off `origin/main`. Open PRs with the local `create-pr` skill.
- All package commands run from the **`defendable-science/` subdirectory**. The module directory is `defendable_science/` (underscore).
- **100% statement + branch coverage is a hard gate** (`fail_under = 100`, ADR-0028). Every validation branch and every degradation branch needs a test. `# pragma: no cover` only for genuinely unreachable code, with a stated reason.
- `uv run mypy` must pass **strict** (`strict = true`, `disallow_any_generics = true`, `warn_return_any = true`, `python_version = "3.11"`).
- `uv run ruff check` and `uv run ruff format` must pass. Line length 88, `target-version = "py311"`.
- **Python 3.11 floor.** `requires-python = ">=3.11,<3.15"`. Do **not** use PEP 695 generic syntax (`def f[T: BaseModel]`) — that needs 3.12. Use `TypeVar`.
- **MyST field-list docstrings** on public API (`:param:` / `:returns:` / `:raises:`); types come from annotations, never repeated in the docstring.
- **No Pydantic model over package-internal or emit-only data** (ADR-0043 decision point 2). Internal value objects stay stdlib `dataclasses`.
- **Failure honesty:** never let a failure surface as a legitimate empty/negative result, and never let it surface as a raw traceback.
- Commits are authored `Davor Runje <davor@synthpop.ai>` with a `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` trailer. Use `git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" commit`.

---

## File Structure

**Created:**

| Path | Responsibility |
| --- | --- |
| `decisions/0043-pydantic-at-the-parsing-boundary.md` | The ADR. |
| `defendable-science/defendable_science/core/models.py` | The two base model configs, the three parse helpers, the error formatter. The only importer of `ValidationError`. |
| `defendable-science/tests/test_models.py` | Tests for `core/models.py` in isolation. |

**Modified:**

| Path | Change |
| --- | --- |
| `CLAUDE.md` | The Code-style bullet's Pydantic sentence. |
| `decisions/README.md` | The 0043 index row. |
| `decisions/0029-api-key-handling.md`, `0031-config-driven-cache-dir.md`, `0038-venue-resolvers-trusted-not-gated.md` | Amendment blockquotes only. |
| `docs/design/proposals/dataset-manifest-tooling.md` | Amendment note only. |
| `defendable-science/pyproject.toml` | `pydantic` dependency; ruff `flake8-type-checking` config. |
| `defendable-science/uv.lock` | Regenerated. |
| `defendable-science/defendable_science/literature/graph.py` | The OpenAlex/S2 models; defects 1–4. |
| `defendable-science/defendable_science/literature/acquire.py` | The sidecar model; defect 5. |
| `defendable-science/defendable_science/dataset/manifest.py` | Croissant top-level validation; defect 6. |
| `defendable-science/defendable_science/core/keys.py` | Consolidation. |
| `defendable-science/defendable_science/literature/registry.py` | Consolidation. |
| `defendable-science/tests/test_literature.py`, `test_acquire.py`, `test_manifest.py`, `test_cli_commands.py`, `test_keys.py` | Regression + updated tests. |

**Deliberately untouched:** `defendable-science/defendable_science/core/http.py` (spec §3.5 — `get_json` and the response cache stay generic); `docs/superpowers/plans/*.md` (dated historical record).

---

## Task 1: ADR-0043 and the documentation edits

Phase 1 of the spec. No package code changes, so no pytest cycle — the gate is a grep and the plugin validator.

**Files:**
- Create: `decisions/0043-pydantic-at-the-parsing-boundary.md`
- Modify: `decisions/README.md`, `CLAUDE.md`, `decisions/0029-api-key-handling.md`, `decisions/0031-config-driven-cache-dir.md`, `decisions/0038-venue-resolvers-trusted-not-gated.md`, `docs/design/proposals/dataset-manifest-tooling.md`

**Interfaces:**
- Consumes: nothing.
- Produces: ADR-0043, cited by every later task's commit message and by the `CLAUDE.md` rule that governs them.

- [ ] **Step 1: Confirm 0043 is free**

```bash
cd /home/davor/projects/PhD/defendable-science
ls decisions/ | grep -E '^004[0-9]'
git branch -a --format='%(refname:short)' | head -40
```

Expected: `0042-depth-mode-matrix-cells-provenance.md` is the highest. If another branch has claimed 0043, use the next free number and adjust every reference in this plan accordingly.

- [ ] **Step 2: Read the model ADR for register and structure**

```bash
cat decisions/0041-dashboard-generated-by-the-cli.md
sed -n '1,12p' decisions/0029-api-key-handling.md   # the amendment-blockquote convention
```

- [ ] **Step 3: Write the ADR**

Create `decisions/0043-pydantic-at-the-parsing-boundary.md` in MADR shape — the same section order and register as 0041. Lift the context material from spec §1 (the two-halves rebuttal, the dependency-tree numbers, the six-defect table) rather than paraphrasing it.

The Decision section carries exactly these five points, spelled out (spec §3.1, §3.2, §3.3, §4):

1. **The boundary is data entering the process.** A model is warranted for anything the package reads that it did not construct in this process: third-party API responses, human- or publisher-authored files (Croissant, CSL-JSON, YAML frontmatter, `config.yml`, the key store), and its own on-disk artifacts read back by a later invocation (the acquire quarantine sidecar). Provenance is explicitly *not* the test — state why, citing that the sidecar is ours and still crosses a boundary.
2. **Nothing the package only emits gets a model.** Internal value objects stay stdlib `dataclasses`; strict mypy is already the guarantee. Do not convert an existing dataclass that never touches untrusted input; do not model a shape the package both writes and reads within one process. A Pydantic model over package-internal or emit-only data is a review finding.
3. **A boundary model is the authoritative schema for its shape.** The writer, the shipped template under `resources/templates/` and the corresponding rule in `check/checks.py` derive from it *or are guarded against it in tests*. A model that duplicates a schema still written longhand elsewhere has not paid for itself.
4. **A `ValidationError` never escapes the boundary.** Caught in exactly one module and converted to the calling module's existing explicit failure signal — a `Finding`, a non-zero exit, an error object in the JSON envelope — carrying the field path and reason. Never a bare traceback, never swallowed into a default. Which signal is a per-boundary choice: a paginated OpenAlex page hard-fails as one unit, while a best-effort S2 bundle skips the bad member and marks the loss in the record's existing `degraded` list.
5. **Adoption is incremental and per-boundary**, each slice landing with the tests that cover it. ADR-0028's 100% statement + branch gate is unchanged and applies to the validation and degradation branches too.

The Rejected-alternatives section carries all five, each with its *why* (spec §4): keep the blanket rejection · Pydantic everywhere replacing `dataclasses` · `jsonschema` (validates without parsing — the payload stays an untyped dict, call sites keep hand-unpacking, mypy learns nothing) · `TypedDict` + hand-written validators (the status quo with a name) · `attrs` + `cattrs` (close call; loses because Pydantic's structured error objects drop straight into point 4 where `cattrs` would need the hand-written translation layer being removed).

Consequences: `requires-python = ">=3.11,<3.15"` makes the wheel matrix a release-time check; the scope-creep risk into a general model layer is bounded by point 2.

Status line: `accepted`. Deciders: Davor Runje (with Claude), matching the footer note in `decisions/README.md`.

- [ ] **Step 4: Append the index row**

In `decisions/README.md`, add one row immediately after the 0042 row, in the same one-line-summary style as its neighbours:

```markdown
| [0043](0043-pydantic-at-the-parsing-boundary.md) | Pydantic is permitted only where data *enters the process* (third-party responses, human-authored files, our own artifacts read back by a later invocation) — internal value objects stay stdlib `dataclasses`, a boundary model is the authoritative schema for its shape, and a `ValidationError` is caught in one module and converted to the caller's explicit failure signal, never a traceback | accepted |
```

- [ ] **Step 5: Replace the prohibition in `CLAUDE.md`**

In the **Code style** bullet under `## Conventions`, replace:

> **Pydantic is deliberately rejected** (keep the wheel light, no Rust-binary conflicts) — do not reintroduce it.

with:

> **Pydantic is scoped to the parsing boundary** (ADR-0043): it validates data *entering the process* — third-party API responses, human-authored files, our own artifacts read back by a later invocation — and nothing else. Internal value objects and anything the package only emits stay stdlib `dataclasses`. A `ValidationError` is translated to the module's explicit failure signal in `core/models.py`, never re-raised.

Leave the rest of the bullet (Python 3.11+, line length, MyST docstrings, strict mypy, the `resources/references/` sentence) exactly as it is.

- [ ] **Step 6: Add the three ADR amendment blockquotes**

Use the house convention already at `decisions/0029-api-key-handling.md:5-7` — a blockquote immediately after the status line. **Do not edit the decision text of any of the three.**

In `decisions/0029-api-key-handling.md`, after the existing `> **Refined by ADR-0032.**` blockquote:

```markdown
> **Refined by ADR-0043.** The "no Pydantic" driver below is superseded: Pydantic is
> now permitted where data enters the process, which includes reading the key store.
> The rest of this decision stands.
```

In `decisions/0031-config-driven-cache-dir.md`, after the status line:

```markdown
> **Refined by ADR-0043.** The "ADR rejecting it stands" reference below pointed at a
> document that was never written. ADR-0043 is that decision, and it *permits* Pydantic
> at the parsing boundary. The rest of this decision stands.
```

In `decisions/0038-venue-resolvers-trusted-not-gated.md`, after the status line:

```markdown
> **Refined by ADR-0043.** The "no Pydantic" clause in the light-dependency argument
> below is superseded by ADR-0043. The rest of this decision stands.
```

- [ ] **Step 7: Add the proposal amendment note**

In `docs/design/proposals/dataset-manifest-tooling.md`, add a short note near the top (not at `:46-47` / `:129-130` themselves — the sketch text is a point-in-time record and is not rewritten):

```markdown
> **Amended by [ADR-0043](../../../decisions/0043-pydantic-at-the-parsing-boundary.md).**
> The "no `pydantic`" constraint recorded below no longer holds. Croissant ingest now
> validates its top level through a Pydantic boundary model; everything else in this
> proposal stands as shipped.
```

- [ ] **Step 8: Run the grep gate and the plugin validator**

```bash
cd /home/davor/projects/PhD/defendable-science
grep -rn "Pydantic is deliberately rejected\|ADR rejecting it stands" . --exclude-dir=.git
```

Expected: **only** hits under `docs/superpowers/plans/` (the dated historical plans, deliberately untouched) and inside the new ADR / spec where the old wording is quoted as history. No hit in `CLAUDE.md`, in `decisions/00{29,31,38}-*.md` decision text, or in `docs/design/proposals/`.

```bash
./tools/validate-plugin.sh
pre-commit run --all-files
```

Expected: both pass.

- [ ] **Step 9: Commit**

```bash
cd /home/davor/projects/PhD/defendable-science
git add decisions/ CLAUDE.md docs/design/proposals/dataset-manifest-tooling.md
git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" commit -m "docs(decisions): scope Pydantic to the parsing boundary (ADR-0043)

Replaces CLAUDE.md's blanket prohibition, which never had an ADR yet was
cited as a driver by ADR-0029, ADR-0031 and ADR-0038 — the last of those
pointing at a document that was never written.

Both halves of the original rationale fail against the repo: the package
is installed isolated from the consumer's ML env (ADR-0024/0026,
resources/ensure-tooling.md), so pydantic-core cannot collide with anyone's
torch; and the runtime tree is already 13 packages.

Refs #169

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: The dependency and `core/models.py`

Spec §5.1 and §5.2 slice 1. The load-bearing task: everything after it funnels through this seam.

**Files:**
- Modify: `defendable-science/pyproject.toml`
- Modify: `defendable-science/uv.lock` (regenerated, not hand-edited)
- Create: `defendable-science/defendable_science/core/models.py`
- Test: `defendable-science/tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces — every later task imports from `defendable_science.core.models`:
  - `ExternalModel` — `BaseModel` subclass, `ConfigDict(extra="ignore", strict=True, populate_by_name=True)`
  - `OwnedModel` — `BaseModel` subclass, `ConfigDict(extra="forbid", strict=True, populate_by_name=True)`
  - `parse_obj(model: type[T], payload: object, *, source: str, error: Callable[[str], Exception]) -> T`
  - `parse_json(model: type[T], text: str, *, source: str, error: Callable[[str], Exception]) -> T`
  - `parse_each(model: type[T], items: Iterable[object]) -> tuple[list[T], int]`
  - where `T = TypeVar("T", bound=BaseModel)`

- [ ] **Step 1: Add the dependency and verify the wheel matrix**

In `defendable-science/pyproject.toml`, `[project].dependencies` — keep the existing four, append:

```toml
dependencies = [
    "typer>=0.12",
    "requests>=2.31",
    "pyyaml>=6.0",
    "pooch>=1.8",
    "pydantic>=2.13,<3",
]
```

`>=2.13` is chosen because `pydantic-core` 2.48.0 publishes `cp311`–`cp315` wheels, covering the whole of `requires-python = ">=3.11,<3.15"`. Confirm this is still true before committing:

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
python3 -c "
import json, re, urllib.request
c = json.load(urllib.request.urlopen('https://pypi.org/pypi/pydantic-core/json'))
v = c['info']['version']
tags = sorted({m for f in c['releases'][v] for m in re.findall(r'cp3\d+', f['filename'])})
print(v, tags)
"
```

Expected: the tag list includes `cp311`, `cp312`, `cp313` and `cp314`. If it does not, raise the floor to a release that does and say so in the commit message.

- [ ] **Step 2: Configure ruff so it does not break Pydantic**

The package uses `from __future__ import annotations` with `TYPE_CHECKING` imports, and ruff's `TCH` rules are enabled. Pydantic must resolve a model's annotations **at runtime**, so `TCH` moving those imports into a `TYPE_CHECKING` block would break validation with a `PydanticUndefinedAnnotation` at import time.

Add to `defendable-science/pyproject.toml`, after the `[tool.ruff.lint.isort]` block:

```toml
[tool.ruff.lint.flake8-type-checking]
# Pydantic resolves a model's annotations at runtime, so the types a model's
# fields reference must stay imported at runtime — not moved into a
# `TYPE_CHECKING` block by TCH00x (ADR-0043).
runtime-evaluated-base-classes = [
    "pydantic.BaseModel",
    "defendable_science.core.models.ExternalModel",
    "defendable_science.core.models.OwnedModel",
]
```

- [ ] **Step 3: Sync, lock, and confirm the tree**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv sync && uv lock
uv tree --no-dev
```

Expected: exactly five additions to the runtime tree — `pydantic`, `pydantic-core`, `annotated-types`, `typing-extensions` and `typing-inspection`. Nothing else. `typing-inspection` is a genuine pydantic 2.13 transitive (pure Python, no compiled artifact), so it does not touch the compiled-wheel axis ADR-0043 weighed. If a *sixth* appears, stop and report it.

- [ ] **Step 4: Write the failing tests for the seam**

Create `defendable-science/tests/test_models.py`:

```python
from __future__ import annotations

import pytest

from defendable_science.core import models


class _Widget(models.ExternalModel):
    name: str
    count: int | None = None


class _Sealed(models.OwnedModel):
    name: str


class _Boom(Exception):
    """A stand-in for a module's own domain error."""


def test_parse_obj_returns_the_model() -> None:
    got = models.parse_obj(
        _Widget, {"name": "a", "count": 2}, source="s", error=_Boom
    )
    assert got.name == "a"
    assert got.count == 2


def test_parse_obj_ignores_unknown_fields_on_an_external_model() -> None:
    got = models.parse_obj(
        _Widget, {"name": "a", "surprise": 1}, source="s", error=_Boom
    )
    assert got.name == "a"


def test_parse_obj_rejects_unknown_fields_on_an_owned_model() -> None:
    with pytest.raises(_Boom, match=r"store\.json: surprise: "):
        models.parse_obj(
            _Sealed, {"name": "a", "surprise": 1}, source="store.json", error=_Boom
        )


def test_parse_obj_is_strict_about_scalar_types() -> None:
    # The defect-4 guarantee: a stringified number is rejected, not coerced.
    with pytest.raises(_Boom, match=r"count: "):
        models.parse_obj(_Widget, {"name": "a", "count": "2"}, source="s", error=_Boom)


def test_parse_obj_names_the_source_and_every_bad_field() -> None:
    with pytest.raises(_Boom) as caught:
        models.parse_obj(_Widget, {"count": "x"}, source="api/works", error=_Boom)
    message = str(caught.value)
    assert message.startswith("api/works: ")
    assert "name: " in message
    assert "count: " in message
    assert "; " in message


def test_parse_obj_reports_a_nested_field_path() -> None:
    class _Outer(models.ExternalModel):
        inner: _Widget

    with pytest.raises(_Boom, match=r"inner\.name: "):
        models.parse_obj(_Outer, {"inner": {}}, source="s", error=_Boom)


def test_parse_obj_reports_a_non_object_payload_at_the_root() -> None:
    with pytest.raises(_Boom, match=r"s: <root>: "):
        models.parse_obj(_Widget, [1, 2], source="s", error=_Boom)


def test_parse_json_parses_text() -> None:
    got = models.parse_json(_Widget, '{"name": "a"}', source="s", error=_Boom)
    assert got.name == "a"


def test_parse_json_folds_a_decode_error_into_the_domain_error() -> None:
    with pytest.raises(_Boom, match=r"f\.json: invalid JSON: "):
        models.parse_json(_Widget, "{oops", source="f.json", error=_Boom)


def test_parse_json_folds_a_validation_error_into_the_domain_error() -> None:
    with pytest.raises(_Boom, match=r"f\.json: name: "):
        models.parse_json(_Widget, "{}", source="f.json", error=_Boom)


def test_parse_each_keeps_the_valid_and_counts_the_skipped() -> None:
    items, skipped = models.parse_each(
        _Widget, [{"name": "a"}, "not-a-mapping", {"name": "b"}, {"count": 1}]
    )
    assert [w.name for w in items] == ["a", "b"]
    assert skipped == 2


def test_parse_each_on_an_all_valid_list_skips_nothing() -> None:
    items, skipped = models.parse_each(_Widget, [{"name": "a"}])
    assert len(items) == 1
    assert skipped == 0


def test_validation_error_is_caught_in_exactly_one_module() -> None:
    # ADR-0043 decision point 4: the translation lives in one place.
    import pathlib
    import subprocess

    root = pathlib.Path(models.__file__).parent.parent
    out = subprocess.run(  # noqa: S603
        ["grep", "-rln", "ValidationError", str(root)],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    assert [pathlib.Path(p).name for p in out] == ["models.py"]
```

- [ ] **Step 5: Run the tests to verify they fail**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run pytest tests/test_models.py -v --no-cov
```

Expected: collection error — `ModuleNotFoundError: No module named 'defendable_science.core.models'`.

- [ ] **Step 6: Write `core/models.py`**

```python
"""Validated parsing where data enters the process (ADR-0043).

Every JSON payload the package reads but did not construct in *this* process —
a third-party API response, a publisher- or human-authored file, one of its own
on-disk artifacts read back by a later invocation — is validated here, and a
:class:`~pydantic.ValidationError` is translated into the calling module's own
error type before it can escape.

This is the **only** module in the package that imports ``ValidationError``
(ADR-0043 decision point 4). A malformed payload must reach the user as an
explicit, actionable failure naming the field and the reason — never as a bare
traceback, and never swallowed into a default that a caller cannot distinguish
from legitimately-absent data.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

T = TypeVar("T", bound=BaseModel)


class ExternalModel(BaseModel):
    """Base for a payload written by a third party.

    ``extra="ignore"`` because OpenAlex, Semantic Scholar and Croissant
    publishers add fields without notice, and an unmodelled addition is not an
    error. ``strict=True`` because a *type* change is: a stringified year must
    be rejected, never coerced into looking correct.
    """

    model_config = ConfigDict(extra="ignore", strict=True, populate_by_name=True)


class OwnedModel(BaseModel):
    """Base for one of our own on-disk artifacts, read back by a later run.

    ``extra="forbid"`` because an unexpected key in a file this package wrote
    means a version mismatch between the writer and the reader, which is worth
    surfacing rather than ignoring.
    """

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


def _explain(exc: ValidationError) -> str:
    """Render a validation failure as ``<field path>: <reason>`` pairs.

    :param exc: The failure to render.
    :returns: Every error, ``"; "``-joined; a root-level failure is located as
        ``<root>`` so the message never reads as if a field were unnamed.
    """
    parts = []
    for err in exc.errors():
        location = ".".join(str(part) for part in err["loc"]) or "<root>"
        parts.append(f"{location}: {err['msg']}")
    return "; ".join(parts)


def parse_obj(
    model: type[T],
    payload: object,
    *,
    source: str,
    error: Callable[[str], Exception],
) -> T:
    """Validate an already-parsed JSON value, or raise the caller's domain error.

    :param model: The boundary model to validate against.
    :param payload: The decoded JSON value.
    :param source: What is being parsed — a path or a URL — for the message.
    :param error: The calling module's own error type (``RegistryError``,
        ``ManifestError``, ``HttpError``, ``RetrievalError``, …).
    :returns: The validated model.
    :raises Exception: `error`, carrying `source`, the field path and the
        reason. Never a ``ValidationError``, never a bare traceback.
    """
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise error(f"{source}: {_explain(exc)}") from exc


def parse_json(
    model: type[T],
    text: str,
    *,
    source: str,
    error: Callable[[str], Exception],
) -> T:
    """Parse and validate JSON text, folding a decode error into the same signal.

    A caller reading a file gets one error idiom for "this is not JSON" and for
    "this is JSON of the wrong shape", so neither can reach the user raw.

    :param model: The boundary model to validate against.
    :param text: The raw JSON text.
    :param source: What is being parsed — a path or a URL — for the message.
    :param error: The calling module's own error type.
    :returns: The validated model.
    :raises Exception: `error`, carrying `source` and either the decode failure
        or the field path and reason.
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise error(f"{source}: invalid JSON: {exc}") from exc
    return parse_obj(model, payload, source=source, error=error)


def parse_each(model: type[T], items: Iterable[object]) -> tuple[list[T], int]:
    """Validate each item independently, keeping the valid ones.

    For a **best-effort** collection, where one malformed member must not
    destroy the rest — an S2 citation-edge page, say. The caller is handed the
    skip count precisely so the loss can be surfaced explicitly (a ``degraded``
    marker, a warning) rather than vanishing: a silently dropped member is the
    failure the honesty rule targets. A collection that must be complete should
    use :func:`parse_obj` on a model of the whole container instead.

    :param model: The boundary model each item is validated against.
    :param items: The raw items.
    :returns: ``(valid_items, skipped_count)``.
    """
    valid: list[T] = []
    skipped = 0
    for item in items:
        try:
            valid.append(model.model_validate(item))
        except ValidationError:
            skipped += 1
    return valid, skipped
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run pytest tests/test_models.py -v --no-cov
```

Expected: all pass.

- [ ] **Step 8: Try the `pydantic.mypy` plugin, and drop it if it does not hold**

Add to `defendable-science/pyproject.toml` under `[tool.mypy]`:

```toml
plugins = ["pydantic.mypy"]
```

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run mypy
```

If it passes, keep it. If the plugin errors against the pinned mypy version, **remove the two lines and move on** — it is a nicety, not load-bearing, and the strict config already carries the weight. Note which way it went in the commit message.

- [ ] **Step 9: Run the full gate**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest -q
```

Expected: all four pass, coverage at 100%.

- [ ] **Step 10: Commit**

```bash
cd /home/davor/projects/PhD/defendable-science
git add defendable-science/pyproject.toml defendable-science/uv.lock \
        defendable-science/defendable_science/core/models.py \
        defendable-science/tests/test_models.py
git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" commit -m "feat(core): add the validated-parsing seam at the process boundary

Pins pydantic>=2.13,<3 (pydantic-core ships cp311-cp315 wheels, covering
requires-python) and adds core/models.py: two base configs split by who
wrote the data, and three helpers that translate a ValidationError into
the calling module's own error type.

This is the only module that imports ValidationError (ADR-0043 point 4).
parse_each exists so a best-effort collection can skip a bad member and
report the count, without any caller catching ValidationError itself.

Refs #169

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `graph.py` — defects 1, 2, 3 and 4

Spec §5.2 slice 2. Four defects share one root cause, so they are fixed together.

**Files:**
- Modify: `defendable-science/defendable_science/literature/graph.py` — `_abstract` (`:79-87`), `enrich_work` (`:90-116`), `_fetch_work` (`:119-131`), `_s2_crossref` (`:154-179`), `resolve` (`:182-229`), `cites` (`:232-263`), `refs` (`:266-274`), `_s2_context` (`:288-336`), `_aggregate_s2_edges` (`:339-355`), `enrich` (`:358-400`)
- Test: `defendable-science/tests/test_literature.py`

**Interfaces:**
- Consumes: `ExternalModel`, `parse_obj`, `parse_each` from `defendable_science.core.models` (Task 2).
- Produces: `graph.OpenAlexWork`, `graph.WorksPage`, `graph.S2ExternalIds`, `graph.S2CitationEdge`. `graph.enrich_work` changes signature to `enrich_work(work: OpenAlexWork) -> dict[str, Any]`; `graph._abstract` changes to `_abstract(index: dict[str, list[int]] | None) -> str | None`. The **emitted JSON shape is unchanged** — the enrichment record stays a `dict[str, Any]` (ADR-0043 point 2; the dataclass rewrite is #174).

- [ ] **Step 1: Write the four failing regression tests**

Append to `defendable-science/tests/test_literature.py`. These reproduce the exact symptoms from spec §1's table.

```python
def test_cites_rejects_a_non_dict_result_row() -> None:
    """Defect 1: a junk row raised AttributeError mid-pagination."""
    from defendable_science.core.http import HttpError

    client = _client(
        {
            "https://api.openalex.org/works": {
                "results": [_WORK, "not-a-work"],
                "meta": {"next_cursor": None},
            }
        }
    )
    with pytest.raises(HttpError, match=r"results\.1"):
        graph.cites("W1", client=client)


def test_enrich_work_rejects_a_non_mapping_inverted_index() -> None:
    """Defect 2: `index.items()` raised AttributeError on a string."""
    from defendable_science.core.http import HttpError

    bad = {**_WORK, "abstract_inverted_index": "Hello world"}
    with pytest.raises(HttpError, match=r"abstract_inverted_index"):
        graph.parse_work(bad, source="test")


def test_s2_edge_with_a_string_contexts_never_yields_one_character() -> None:
    """Defect 3: `edge["contexts"][0]` on a bare string yielded its first char."""
    out: dict[str, object] = {
        "s2": None,
        "context_snippet": None,
        "intent": None,
        "is_influential": None,
    }
    skipped = graph._aggregate_s2_edges([{"contexts": "Hello", "intents": []}], out)
    assert out["context_snippet"] != "H"
    assert out["context_snippet"] is None
    assert skipped == 1


def test_enrich_marks_degraded_when_an_s2_edge_is_skipped() -> None:
    """Defect 3, at the seam a consumer actually reads."""
    oa = "https://api.openalex.org"
    s2 = "https://api.semanticscholar.org/graph/v1"
    client = _client(
        {
            f"{oa}/works/W1": _WORK,
            f"{s2}/paper/DOI:10.1234/abc": {"externalIds": {"CorpusId": 7}},
            f"{s2}/paper/DOI:10.1234/abc/citations": {
                "data": [{"contexts": "Hello", "intents": [], "isInfluential": False}]
            },
        },
        s2_key="k",
    )
    (record,) = graph.enrich(["W1"], client=client, with_context=True)
    assert record["context_snippet"] is None
    assert record["degraded"] == ["context", "intent", "is_influential"]


def test_enrich_work_rejects_a_string_publication_year() -> None:
    """Defect 4: a string year propagated into the record and out through the CLI."""
    from defendable_science.core.http import HttpError

    bad = {**_WORK, "publication_year": "2023"}
    with pytest.raises(HttpError, match=r"publication_year"):
        graph.parse_work(bad, source="test")
```

`_client(...)` is the existing helper in `tests/test_literature.py`. Read its definition first — if it does not already take an `s2_key` keyword, extend it rather than writing a second fixture; the existing S2 tests in that file show the established way to configure a key.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run pytest tests/test_literature.py -k "defect or non_dict_result or inverted_index or one_character or degraded_when or string_publication" -v --no-cov
```

Expected: failures. Specifically `test_s2_edge_with_a_string_contexts_never_yields_one_character` asserts `out["context_snippet"] is None` and currently gets `"H"` — that is the wrong-value bug, visible.

- [ ] **Step 3: Add the models to `graph.py`**

Insert after the `OPENALEX` / `S2` constants. Note the aliases: S2's payload is camelCase and ruff's `N815` forbids a mixedCase class attribute, so the Python field names stay snake_case and Pydantic maps them.

```python
from pydantic import Field

from defendable_science.core.models import ExternalModel, parse_each, parse_obj


class _Source(ExternalModel):
    display_name: str | None = None


class _PrimaryLocation(ExternalModel):
    source: _Source | None = None


class _Author(ExternalModel):
    display_name: str | None = None


class _Authorship(ExternalModel):
    author: _Author | None = None


class _WorkIds(ExternalModel):
    arxiv: str | None = None


class OpenAlexWork(ExternalModel):
    """An OpenAlex work object, as far as this package reads it."""

    id: str | None = None
    doi: str | None = None
    ids: _WorkIds = Field(default_factory=_WorkIds)
    display_name: str | None = None
    title: str | None = None
    publication_year: int | None = None
    cited_by_count: int | None = None
    primary_location: _PrimaryLocation | None = None
    authorships: list[_Authorship] = Field(default_factory=list)
    abstract_inverted_index: dict[str, list[int]] | None = None
    referenced_works: list[str] = Field(default_factory=list)


class _PageMeta(ExternalModel):
    next_cursor: str | None = None


class WorksPage(ExternalModel):
    """One cursor-paginated page of the OpenAlex ``/works`` endpoint."""

    results: list[OpenAlexWork] = Field(default_factory=list)
    meta: _PageMeta = Field(default_factory=_PageMeta)


class _ExternalIdBundle(ExternalModel):
    doi: str | None = Field(default=None, alias="DOI")
    arxiv: str | None = Field(default=None, alias="ArXiv")
    corpus_id: int | str | None = Field(default=None, alias="CorpusId")


class S2ExternalIds(ExternalModel):
    """A Semantic Scholar paper's ``externalIds`` response."""

    external_ids: _ExternalIdBundle = Field(
        default_factory=_ExternalIdBundle, alias="externalIds"
    )


class S2CitationEdge(ExternalModel):
    """One incoming citation edge from S2's ``/citations`` endpoint."""

    contexts: list[str] = Field(default_factory=list)
    intents: list[str] = Field(default_factory=list)
    is_influential: bool = Field(default=False, alias="isInfluential")


def parse_work(payload: object, *, source: str) -> OpenAlexWork:
    """Validate an OpenAlex work payload, or fail the call.

    A malformed work is a hard error rather than a skipped row: returning a
    partial frontier as if it were complete is the failure this package exists
    to prevent (ADR-0043 decision point 4).

    :param payload: The raw work object.
    :param source: The URL it came from, for the message.
    :returns: The validated work.
    :raises HttpError: If `payload` is not a well-formed OpenAlex work.
    """
    from defendable_science.core.http import HttpError

    return parse_obj(OpenAlexWork, payload, source=source, error=HttpError)
```

`_ExternalIdBundle.corpus_id` is `int | str | None` because S2 has been observed returning both; `strict=True` would reject the other one otherwise, and a corpus id is only ever interpolated into a string.

If ruff's `TCH` rule still wants to move the `pydantic` / `core.models` imports into the `TYPE_CHECKING` block, the config from Task 2 Step 2 is missing or incomplete — fix that rather than adding a `# noqa`.

- [ ] **Step 4: Rewrite `_abstract` and `enrich_work` against the model**

```python
def _abstract(index: dict[str, list[int]] | None) -> str | None:
    """Reconstruct an abstract from OpenAlex's inverted index, if present."""
    if not index:
        return None
    positions: list[tuple[int, str]] = []
    for word, where in index.items():
        positions.extend((pos, word) for pos in where)
    return " ".join(word for _, word in sorted(positions))


def enrich_work(work: OpenAlexWork) -> dict[str, Any]:
    """Project a validated OpenAlex work into the stable enrichment record shape.

    :param work: A validated OpenAlex work object.
    :returns: ``{id{…}, title, year, venue, cited_by_count, authors, abstract}``.
    """
    source = work.primary_location.source if work.primary_location else None
    authors = [
        a.author.display_name
        for a in work.authorships
        if a.author and a.author.display_name
    ]
    return {
        "id": {
            "openalex": _short_id(work.id),
            "doi": _strip_doi(work.doi),
            "s2": None,
            "arxiv": _short_id(work.ids.arxiv) if work.ids.arxiv else None,
        },
        "title": work.display_name or work.title,
        "year": work.publication_year,
        "venue": source.display_name if source else None,
        "cited_by_count": work.cited_by_count,
        "authors": authors,
        "abstract": _abstract(work.abstract_inverted_index),
    }
```

The returned value stays a `dict[str, Any]` — that is deliberate. ADR-0043 point 2 forbids a Pydantic model over data the package only emits, and the dataclass rewrite of this record is tracked separately as #174.

- [ ] **Step 5: Rewrite `_fetch_work`, `resolve`, `cites` and `refs`**

```python
def _fetch_work(client: HttpClient, openalex_id: str) -> OpenAlexWork:
    """Fetch one OpenAlex work by its ``W…`` id.

    :raises HttpError: If the 200 body is not a well-formed work object (wrong
        shape, or no ``id``); a hollow ``{}`` is never returned in its place.
    """
    from defendable_science.core.http import HttpError

    url = f"{OPENALEX}/works/{openalex_id}"
    work = parse_work(client.get_json(url), source=url)
    if not work.id:
        raise HttpError(f"{url}: response is not an OpenAlex work object")
    return work
```

In `cites`, replace the page handling at `:250-262`:

```python
        raw = client.get_json(
            f"{OPENALEX}/works",
            {"filter": f"cites:{openalex_id}", "per-page": "200", "cursor": cursor},
        )
        page = parse_obj(
            WorksPage, raw, source=f"{OPENALEX}/works", error=HttpError
        )
        for work in page.results:
            record = enrich_work(work)
            record["provenance"] = {"source_id": openalex_id, "via": "openalex"}
            results.append(record)
            if max_results is not None and len(results) >= max_results:
                return results
        cursor = page.meta.next_cursor
```

The `if not isinstance(page, dict)` guard at `:254-255` is deleted — `parse_obj` subsumes it, and a non-object page now fails as `…/works: <root>: Input should be a valid dictionary`. Keep the `:241-243` docstring's `:raises HttpError:` clause and widen its wording from "not a JSON object" to "not a well-formed citation page".

In `refs`, `work.referenced_works` replaces `work.get("referenced_works", [])`:

```python
    work = _fetch_work(client, openalex_id)
    return [rid for ref in work.referenced_works if (rid := _short_id(ref))]
```

In `resolve`, replace the hand-parse at `:218-229`. A payload that fails validation is neither a genuine miss nor a clean fetch, so it takes the **transport-error** discriminator the function already defines — which `cli.py:910-911` maps to exit 3. Reporting it as `{resolved: False}` alone would be the "failed vs. legitimately empty" collapse:

```python
    from defendable_science.core.http import HttpError, RateLimitError
    ...
    try:
        payload = client.get_json(lookup)
    except RateLimitError:
        raise
    except HttpError as exc:
        if exc.status_code == 404:
            return {"resolved": False, "reason": str(exc)}
        return {"resolved": False, "reason": str(exc), "transport_error": True}
    try:
        work = parse_work(payload, source=lookup)
    except HttpError as exc:
        # A 200 body of the wrong shape is not a miss — a consumer must not
        # record it as "no such paper" (ADR-0043 decision point 4).
        return {"resolved": False, "reason": str(exc), "transport_error": True}
    if not work.id:
        return {"resolved": False, "reason": "no work found"}
    return {
        "resolved": True,
        "openalex": _short_id(work.id),
        "doi": _strip_doi(work.doi),
        "s2": None,
        "arxiv": _short_id(work.ids.arxiv) if work.ids.arxiv else None,
        "title": work.display_name or work.title,
        "year": work.publication_year,
    }
```

- [ ] **Step 6: Rewrite the S2 paths**

`_s2_crossref` at `:174-178`:

```python
    ids = parse_obj(
        S2ExternalIds, paper, source=f"{S2}/paper/{s2_id}", error=HttpError
    ).external_ids
    if ids.doi:
        return "doi", ids.doi
    if ids.arxiv:
        return "arxiv", ids.arxiv
    return None
```

The existing `isinstance(paper, dict)` fallback at `:174` is deleted; a non-object body now raises `HttpError`, which the enclosing `except HttpError: return None` at `:172-173` does **not** cover, because that `try` block wraps only the `get_json` call. Move the `parse_obj` call **outside** the `try` so a malformed 200 body is a hard error while an HTTP failure stays a soft miss — the two are different conditions and must not collapse.

`_aggregate_s2_edges` — the signature gains a return value so the caller can mark the loss:

```python
def _aggregate_s2_edges(edges: list[Any], out: dict[str, Any]) -> int:
    """Fold S2 citation edges into `out` (representative snippet / intent / flag).

    Best effort by design: a malformed edge is skipped rather than failing an
    optional enrichment, but the count is returned so the caller can mark the
    loss instead of hiding it (ADR-0043 decision point 4).

    :param edges: The raw ``/citations`` edge list.
    :param out: The context bundle mutated in place.
    :returns: How many edges were skipped as malformed.
    """
    parsed, skipped = parse_each(S2CitationEdge, edges)
    for edge in parsed:
        if out["context_snippet"] is None and edge.contexts:
            out["context_snippet"] = edge.contexts[0]
        if out["intent"] is None and edge.intents:
            out["intent"] = edge.intents[0]
        if edge.is_influential:
            out["is_influential"] = True
    if out["is_influential"] is None and parsed:
        out["is_influential"] = False
    return skipped
```

`edge.contexts` is `list[str]`, so `edge.contexts[0]` can no longer index into a string. That is defect 3, closed at the type level.

`_s2_context` — thread the count out, and use the model for the `externalIds` fetch too:

```python
    corpus = None
    if meta:
        corpus = parse_obj(
            S2ExternalIds, meta, source=f"{S2}/paper/{s2_paper_id}", error=HttpError
        ).external_ids.corpus_id
    if corpus is not None:
        out["s2"] = f"CorpusId:{corpus}"
    ...
    edges = page.get("data", []) if isinstance(page, dict) else []
    out["edges_skipped"] = _aggregate_s2_edges(edges, out)
    return out
```

`meta` is `{}` on the `except HttpError` path at `:315-316`, so the `if meta:` guard keeps that soft-miss behaviour intact.

`enrich` at `:394-398` — set `degraded` when edges were skipped:

```python
                if bundle.get("s2"):
                    record["id"]["s2"] = bundle["s2"]
                record["context_snippet"] = bundle["context_snippet"]
                record["intent"] = bundle["intent"]
                record["is_influential"] = bundle["is_influential"]
                if bundle.get("edges_skipped"):
                    record["degraded"] = ["context", "intent", "is_influential"]
```

`edges_skipped` is an internal key of the bundle, not of the emitted record — do not copy it onto `record`. The `{"context_snippet": None, ...}` literal at `:388-392` (the no-S2-id path) has no `edges_skipped` key, which is why `.get` is used rather than `[...]`.

`enrich` at `:376` becomes `record = enrich_work(_fetch_work(client, wid))` unchanged — `_fetch_work` now returns the model, which is what `enrich_work` wants.

- [ ] **Step 7: Update the two tests that call the changed internals**

`tests/test_literature.py:235`:

```python
def test_enrich_work_reconstructs_abstract() -> None:
    rec = graph.enrich_work(graph.parse_work(_WORK, source="test"))
    assert rec["abstract"] == "Hello world"
    assert rec["venue"] == "ICML"
    assert rec["authors"] == ["D. Runje"]
```

`tests/test_literature.py:368`:

```python
    assert graph._abstract(None) is None  # no inverted index
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run pytest tests/test_literature.py -v --no-cov
```

Expected: all pass, including the five new regression tests. If an existing test now fails on a *message* change (e.g. one asserting `"citation page is not a JSON object"`), update the assertion to the new wording — the assertion change must be visible in the diff, not worked around by keeping the old branch alive.

- [ ] **Step 9: Close the coverage gaps**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run pytest tests/test_literature.py --cov=defendable_science.literature.graph --cov-report=term-missing -q
```

Add a test for every uncovered line. The ones most likely to be missed:

- `resolve`'s new malformed-200 path returning `transport_error: True`
- `_fetch_work`'s `if not work.id` branch (a `{}` body)
- `_s2_crossref`'s `arxiv` branch and its `return None` branch
- `_s2_context`'s `if meta:` false branch (the S2 `HttpError` soft miss)
- `_aggregate_s2_edges`'s `if out["is_influential"] is None and parsed` false branch (an empty edge list)

- [ ] **Step 10: Run the full gate**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest -q
```

Expected: all pass, coverage 100%.

- [ ] **Step 11: Commit**

```bash
cd /home/davor/projects/PhD/defendable-science
git add defendable-science/defendable_science/literature/graph.py \
        defendable-science/tests/test_literature.py
git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" commit -m "fix(literature): validate the OpenAlex and S2 payloads at the boundary

Four defects with one root cause — the graph client hand-unpacked
third-party JSON:

- a non-dict row in a /works page raised AttributeError mid-pagination
- a non-mapping abstract_inverted_index raised AttributeError
- an S2 edge whose 'contexts' was a bare string silently yielded its
  *first character* as the citation context — a wrong value, no error
- a stringified publication_year propagated into the enrichment record
  and out through the emitted CLI JSON

An OpenAlex page hard-fails as one unit: a truncated frontier returned as
if complete is worse than a loud failure. S2 stays best-effort — a bad
edge is skipped and the loss is marked in the record's existing
'degraded' list rather than vanishing.

The enrichment record stays a dict; modelling what the package emits is
forbidden by ADR-0043 point 2 and is tracked as #174.

Refs #169

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: The acquire quarantine sidecar — defect 5

Spec §5.2 slice 3. The sidecar is written by one invocation (`acquire.py:1069-1081`) and read back by a later one (`:1939-1943`) — our own data, still crossing a process boundary, so it is in scope under ADR-0043 point 1 and takes `OwnedModel`.

**Files:**
- Modify: `defendable-science/defendable_science/literature/acquire.py` — the model near the other module-level types, the read at `:1939-1943`
- Test: `defendable-science/tests/test_acquire.py`

**Interfaces:**
- Consumes: `OwnedModel`, `parse_json` from `defendable_science.core.models` (Task 2).
- Produces: `acquire.QuarantineSidecar` with fields `candidate: dict[str, Any]`, `match: dict[str, Any]`, `rung: str`, `url: str | None`.

- [ ] **Step 1: Write the failing tests**

Append these to `defendable-science/tests/test_acquire.py`, in the `# --- task 12: confirm` section that starts at `:2220`. They reuse that section's existing helpers: `_registry`, `_ctx`, `_quarantine` (which parks a candidate through the module's own `a._write_quarantine` and returns the parked PDF's path), the `PDF_SHA` constant, and the module alias `a` for `defendable_science.literature.acquire`.

```python
def test_confirm_rejects_a_sidecar_missing_a_required_field(tmp_path: Path) -> None:
    """Defect 5: `data["candidate"]` raised a bare KeyError."""
    _path, entry = _registry(tmp_path)
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher())
    parked = _quarantine(tmp_path, entry, ctx)
    sidecar = parked.parent / f"{PDF_SHA}.json"
    sidecar.write_text(json.dumps({"rung": "oa", "url": None}), encoding="utf-8")

    with pytest.raises(RetrievalError, match=r"candidate: "):
        a.confirm_quarantined(entry, ctx, PDF_SHA)


def test_confirm_rejects_a_sidecar_whose_rung_is_the_wrong_type(
    tmp_path: Path,
) -> None:
    """Defect 5: `cast("str", data["rung"])` let an int through as a str."""
    _path, entry = _registry(tmp_path)
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher())
    parked = _quarantine(tmp_path, entry, ctx)
    (parked.parent / f"{PDF_SHA}.json").write_text(
        json.dumps({"candidate": {}, "match": {}, "rung": 7, "url": None}),
        encoding="utf-8",
    )

    with pytest.raises(RetrievalError, match=r"rung: "):
        a.confirm_quarantined(entry, ctx, PDF_SHA)


def test_confirm_rejects_a_sidecar_with_an_unexpected_key(tmp_path: Path) -> None:
    """``extra="forbid"``: a key the writer never emits means a version skew."""
    _path, entry = _registry(tmp_path)
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher())
    parked = _quarantine(tmp_path, entry, ctx)
    (parked.parent / f"{PDF_SHA}.json").write_text(
        json.dumps(
            {"candidate": {}, "match": {}, "rung": "oa", "url": None, "extra": 1}
        ),
        encoding="utf-8",
    )

    with pytest.raises(RetrievalError, match=r"extra: "):
        a.confirm_quarantined(entry, ctx, PDF_SHA)


def test_confirm_rejects_a_sidecar_that_is_not_json(tmp_path: Path) -> None:
    _path, entry = _registry(tmp_path)
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher())
    parked = _quarantine(tmp_path, entry, ctx)
    (parked.parent / f"{PDF_SHA}.json").write_text("{oops", encoding="utf-8")

    with pytest.raises(RetrievalError, match=r"invalid JSON"):
        a.confirm_quarantined(entry, ctx, PDF_SHA)


def test_the_writer_emits_what_the_reader_validates(tmp_path: Path) -> None:
    """ADR-0043 point 3: the model is authoritative for this shape.

    The writer builds the payload from the Candidate/Match dataclasses rather
    than from the model (converting those would breach ADR-0043 point 2), so
    this round-trip is what holds the two in agreement.
    """
    _path, entry = _registry(tmp_path)
    ctx = _ctx(tmp_path, FakeClient({}), NeverFetcher())
    parked = _quarantine(tmp_path, entry, ctx)

    text = (parked.parent / f"{PDF_SHA}.json").read_text(encoding="utf-8")
    parsed = a.QuarantineSidecar.model_validate_json(text)

    assert parsed.rung == a.RUNG_SIBLING
    assert parsed.url == "http://x/sib.pdf"
```

The function under test is `acquire.confirm_quarantined` (`acquire.py:1890`); the read being replaced is at `:1939-1943`, inside it.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run pytest tests/test_acquire.py -k "sidecar or writer_emits" -v --no-cov
```

Expected: `KeyError: 'candidate'`, a silently-passing wrong type, a raw `json.JSONDecodeError`, and an `AttributeError` on the missing model.

- [ ] **Step 3: Add the model**

Near the other module-level types in `acquire.py`:

```python
from defendable_science.core.models import OwnedModel, parse_json


class QuarantineSidecar(OwnedModel):
    """The ``<sha>.json`` this package parks beside a quarantined PDF.

    Written by one invocation and read back by a later ``confirm``, so it
    crosses a process boundary and is validated on the way in (ADR-0043
    decision point 1). ``extra="forbid"``: an unexpected key means the writer
    and the reader disagree about the format, which is worth surfacing.
    """

    candidate: dict[str, Any]
    match: dict[str, Any]
    rung: str
    url: str | None = None
```

`url` carries a default because the writer emits `candidate.url`, which is nullable; `candidate`, `match` and `rung` are required, which is what turns the old `KeyError` into a named error.

- [ ] **Step 4: Replace the read**

At `acquire.py:1939-1944`, replace the six lines (the `json.loads`, the four `cast()` calls, and the `cast` inside `_license_from_observed`):

```python
    data = parse_json(
        QuarantineSidecar,
        sidecar.read_text(encoding="utf-8"),
        source=str(sidecar),
        error=RetrievalError,
    )
    candidate = data.candidate
    match = data.match
    rung = data.rung
    url = data.url
    observed = candidate.get("license")
    license = _license_from_observed(observed if isinstance(observed, str) else None)
```

`candidate` is `dict[str, Any]`, so `candidate.get("license")` is still `Any` and needs the `isinstance` narrowing that replaces the old `cast`. Modelling the candidate's interior is out of scope here — `Candidate` is an internal dataclass with its own `as_json()`, and giving it a second Pydantic definition would breach ADR-0043 point 2.

Confirm the `cast` import is still used elsewhere in the module; if not, remove it from the imports — ruff's `F401` will flag it.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run pytest tests/test_acquire.py -v --no-cov
grep -n "cast(" defendable_science/literature/acquire.py | sed -n '1,10p'
```

Expected: tests pass; no `cast(` remains anywhere between lines 1935 and 1950.

- [ ] **Step 6: Run the full gate and commit**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest -q
cd /home/davor/projects/PhD/defendable-science
git add defendable-science/defendable_science/literature/acquire.py \
        defendable-science/tests/test_acquire.py
git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" commit -m "fix(literature): validate the quarantine sidecar instead of casting it

The confirm path read a sidecar written by an *earlier* invocation with
json.loads + four cast() calls. cast is a compile-time assertion with no
runtime check, so a sidecar carrying 'rung: 7' passed cast(\"str\", ...)
and flowed on as a str-typed int — mypy actively misled. A missing key
raised a bare KeyError.

Both now surface as a RetrievalError naming the file and the field. A
round-trip test holds the writer at :1069-1081 in agreement with the
model, per ADR-0043 point 3.

Refs #169

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Croissant ingest — defect 6

Spec §5.2 slice 4. `ManifestError` is already in `cli.py:1551`'s except tuple, so validating **inside** `entry_from_croissant` makes that tuple truthful with no CLI change.

**Files:**
- Modify: `defendable-science/defendable_science/dataset/manifest.py` — `entry_from_croissant` (`:534`onward)
- Test: `defendable-science/tests/test_manifest.py`

**Interfaces:**
- Consumes: `ExternalModel`, `parse_obj` from `defendable_science.core.models` (Task 2).
- Produces: no new public name. `entry_from_croissant`'s signature widens from `dict[str, Any]` to `object`, so `cli.py:1549`'s `json.loads` result can be handed to it whatever its shape.

- [ ] **Step 1: Write the failing tests**

Append to `defendable-science/tests/test_manifest.py`:

`tests/test_manifest.py` already imports `json`, `pytest`, `app`, the `CliRunner` instance as `runner`, and aliases `defendable_science.dataset.manifest` as `m`.

```python
def test_ingest_a_top_level_array_exits_1_not_a_traceback(tmp_path: Path) -> None:
    """Defect 6: AttributeError escaped cli.py's except tuple as a traceback."""
    croissant = tmp_path / "x.json"
    croissant.write_text("[1, 2]", encoding="utf-8")

    result = runner.invoke(app, ["dataset", "ingest", str(croissant)])

    assert result.exit_code == 1
    assert "ingest failed" in result.output
    assert not isinstance(result.exception, AttributeError)


def test_entry_from_croissant_rejects_a_non_mapping_document() -> None:
    with pytest.raises(m.ManifestError, match=r"croissant: <root>: "):
        m.entry_from_croissant([1, 2])
```

`result.output` rather than `result.stderr`: check how the sibling `test_cli_ingest_emits_draft` at `:221` reads the runner's output and match it, since whether the `CliRunner` splits streams depends on how it was constructed.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run pytest tests/test_manifest.py -k "top_level_array or non_mapping_document" -v --no-cov
```

Expected: an `AttributeError: 'list' object has no attribute 'get'` surfacing as `result.exception`, not a clean exit 1.

- [ ] **Step 3: Add the model and validate at the top of the function**

In `manifest.py`, near the other module-level types:

```python
from pydantic import Field

from defendable_science.core.models import ExternalModel, parse_obj


class CroissantDocument(ExternalModel):
    """The parts of a published Croissant / schema.org ``Dataset`` we read.

    ``extra="ignore"``: a real Croissant file carries a great deal of JSON-LD
    this package has no use for, and an unmodelled field is not an error. What
    *is* an error is a document that is not an object at all, or whose
    ``distribution`` is not a list — both of which used to reach
    :func:`entry_from_croissant` and raise an ``AttributeError`` that escaped
    the CLI's ``except`` tuple as a traceback.
    """

    name: str | None = None
    alternate_name: str | None = Field(default=None, alias="alternateName")
    distribution: list[Any] = Field(default_factory=list)
```

Then in `entry_from_croissant`, replace the signature and the first two statements:

```python
def entry_from_croissant(json_ld: object) -> DatasetEntry:
    """Ingest a published Croissant document into a *draft* registry entry.

    Fills what the Croissant carries and leaves human-owned fields (``tier``,
    ``retrieval``, ``datasheet``, ``sensitivity``) unset — the caller flags them
    as TODO on register. Never guesses a tier or a license grant.

    :param json_ld: A parsed Croissant / schema.org ``Dataset`` document, of any
        shape — it is validated here rather than assumed.
    :returns: A partial :class:`DatasetEntry` draft.
    :raises ManifestError: If the document is not a JSON object, has no usable
        ``name``, or a ``distribution`` entry is a malformed ``FileObject`` (not
        a mapping, or missing ``contentUrl`` / ``sha256``). A malformed file is
        surfaced, never silently dropped — "no distribution" is distinct from
        "a bad file".
    """
    doc = parse_obj(
        CroissantDocument, json_ld, source="croissant", error=ManifestError
    )
    if not doc.name:
        raise ManifestError("croissant: document has no 'name' to derive an id from")
    entry_id = str(doc.alternate_name or doc.name)
    title = str(doc.name) if str(doc.name) != entry_id else None
```

Then replace `json_ld.get("distribution") or []` in the loop with `doc.distribution`. Leave the per-`distribution` `isinstance` checks and their `ManifestError` messages exactly as they are — they already name the index and distinguish a bad file from no file, which is the message quality the spec protects.

Keep the `# A round-tripped export carries the stable slug in alternateName` comment.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run pytest tests/test_manifest.py tests/test_cli_commands.py -v --no-cov
```

Expected: all pass, including the pre-existing `test_cli_ingest_emits_draft` and `test_ingest_bad_file_exits_1`.

- [ ] **Step 5: Verify the acceptance criterion by hand**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
printf '[1,2]' > /tmp/x.json && uv run defendable-science dataset ingest /tmp/x.json; echo "exit=$?"
```

Expected: a one-line `ingest failed: croissant: <root>: Input should be a valid dictionary…` on stderr and `exit=1`. **No traceback.**

- [ ] **Step 6: Run the full gate and commit**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest -q
cd /home/davor/projects/PhD/defendable-science
git add defendable-science/defendable_science/dataset/manifest.py \
        defendable-science/tests/test_manifest.py
git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" commit -m "fix(dataset): validate a Croissant document's top level before reading it

entry_from_croissant was typed dict[str, Any] and immediately called
json_ld.get('name'), so a Croissant file whose top level is a JSON array
raised AttributeError — which is not in cli.py's
'except (OSError, JSONDecodeError, ManifestError)' tuple, so it escaped
as a traceback instead of the documented exit 1.

Validating inside the function makes that tuple truthful with no CLI
change. The per-distribution checks keep their existing messages.

Refs #169

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Consolidate the already-honest JSON sites

Spec §5.2 slice 5. These sites already validate honestly — they `isinstance`-check, raise a typed domain error naming the file, and distinguish malformed from absent. Pydantic here is a **consolidation**, not a bug fix, which is why they go last.

**The spec's acceptance criterion is "route through the shared helper *with no loss of message quality*". Applied honestly, that admits two of the five and excludes three.** Convert `core/keys.py` and `literature/registry.py`; leave the other three and record why in the commit message. Do not convert a site whose message would get worse — under ADR-0043 point 3, a model that does not pay for itself has not earned its place.

**Files:**
- Modify: `defendable-science/defendable_science/core/keys.py:168-185`
- Modify: `defendable-science/defendable_science/literature/registry.py:290-307`
- Test: `defendable-science/tests/test_keys.py`, `defendable-science/tests/test_lit_registry.py`

**Interfaces:**
- Consumes: `parse_json`, `ExternalModel` from `defendable_science.core.models` (Task 2).
- Produces: no new public names.

- [ ] **Step 1: Convert `core/keys.py`**

The store is a JSON object of strings. Replace the body of the loader at `:168-185` (keep the docstring, updating only the `:raises:` wording if the message changes). Add `from pydantic import ConfigDict, RootModel` and `from defendable_science.core.models import parse_json` to the module's imports:

```python
class _KeyStore(RootModel[dict[str, str]]):
    """The on-disk key store: a flat JSON object of string values."""

    model_config = ConfigDict(strict=True)
```

```python
    resolved = store_path(path)
    if not resolved.is_file():
        return {}
    return dict(
        parse_json(
            _KeyStore,
            resolved.read_text(encoding="utf-8"),
            source=str(resolved),
            error=ValueError,
        ).root
    )
```

`RootModel` is imported from `pydantic`; it does not derive from `ExternalModel`/`OwnedModel` because a root model of a plain mapping has no `extra` to configure. The early `return {}` for an absent file stays — "no store" is legitimately empty and must not become an error.

- [ ] **Step 2: Update the three assertions this changes, deliberately**

`tests/test_keys.py:117` asserted `"expected a JSON object"`; `:124` and `:386` asserted `"must be a string"`. Pydantic's wording differs. Run them, read the new messages, and update each assertion to the new text — do **not** reshape the code to preserve the old strings.

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run pytest tests/test_keys.py -v --no-cov
```

Each updated assertion must still prove the two things that matter: the message names the **file**, and it names the **offending key**. If either is missing from Pydantic's rendering, the conversion has lost quality — revert `keys.py` and record it alongside the three sites below.

- [ ] **Step 3: Convert `literature/registry.py:_parse_items`**

Add `from pydantic import RootModel` and `from defendable_science.core.models import parse_json` to `registry.py`'s imports.

```python
class _CslItems(RootModel[list[Any]]):
    """A CSL-JSON bibliography: an array of item objects."""


def _parse_items(text: str, target: Path) -> list[Any]:
    """Parse CSL-JSON items from text.

    :param text: The JSON text to parse.
    :param target: The path (for error messages).
    :returns: The parsed array of items.
    :raises RegistryError: If the text is not valid JSON or is not a JSON array.
    """
    return parse_json(
        _CslItems, text, source=str(target), error=RegistryError
    ).root
```

- [ ] **Step 4: Run the tests and update any message assertion**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run pytest tests/test_lit_registry.py -v --no-cov
```

- [ ] **Step 5: Leave the other three, and be able to say why**

Do **not** convert these. Record the reasons in the commit message:

- `cli.py:2383-2395` (`_parse_json_object`) — returns `None` on malformed input **by design**; stdin that is not a JSON object is treated as a single value, not an error. It has no domain error to translate to, so `parse_json` is the wrong shape for it.
- `cli.py:1805-1823` (`--points`) and `cli.py:2774-2800` (`--cells`) — a model over the container would replace two `isinstance` branches, but per-item construction still goes through `record_mod.point_record_from_mapping` / `extraction_mod.cell_from_mapping`, which build **internal dataclasses** and do their own field validation. The model would duplicate a schema still written longhand next to it, which ADR-0043 point 3 says has not paid for itself — and it would degrade three user-facing messages that `tests/test_digest_cli.py:954-963` asserts (`--cells item 2 must be a JSON object, got str` → Pydantic's `2: Input should be a valid dictionary`), losing the `--cells item N` framing that tells a user *which* flag and *which* element.

- [ ] **Step 6: Run the full gate**

```bash
cd /home/davor/projects/PhD/defendable-science/defendable-science
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest -q
grep -rln "ValidationError" defendable_science/
```

Expected: all pass at 100% coverage, and the grep returns exactly one path — `defendable_science/core/models.py`.

- [ ] **Step 7: Commit**

```bash
cd /home/davor/projects/PhD/defendable-science
git add defendable-science/defendable_science/core/keys.py \
        defendable-science/defendable_science/literature/registry.py \
        defendable-science/tests/test_keys.py defendable-science/tests/test_lit_registry.py
git -c user.name="Davor Runje" -c user.email="davor@synthpop.ai" commit -m "refactor(core): route the honest JSON readers through the shared seam

The key store and the CSL-JSON reader already validated honestly; this is
consolidation onto one error idiom, not a bug fix. Three assertions in
test_keys.py move to Pydantic's wording — deliberately, and still proving
the message names both the file and the offending key.

Three of the five candidate sites are deliberately left alone:
_parse_json_object returns None by design and has no domain error to
translate to; --points and --cells still delegate per-item construction to
*_from_mapping over internal dataclasses, so a container model would
duplicate a schema written longhand beside it (ADR-0043 point 3) and would
cost the '--cells item N' framing the CLI tests assert.

Refs #169

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Final verification and the PR

**Files:** none modified.

- [ ] **Step 1: Run every acceptance criterion from spec §7**

```bash
cd /home/davor/projects/PhD/defendable-science
grep -rn "Pydantic is deliberately rejected\|ADR rejecting it stands" . --exclude-dir=.git
ls decisions/0043-*.md
grep -c "0043" decisions/README.md
cd defendable-science
uv tree --no-dev | grep -E "pydantic|annotated-types|typing-extensions|typing-inspection"
grep -rln "ValidationError" defendable_science/
grep -n "cast(" defendable_science/literature/acquire.py | awk -F: '$1 > 1930 && $1 < 1960'
printf '[1,2]' > /tmp/x.json && uv run defendable-science dataset ingest /tmp/x.json; echo "exit=$?"
uv run mypy
uv run pytest -q
```

Expected, in order: no hit outside `docs/superpowers/plans/`; the ADR exists; the index row is there; four packages added; `ValidationError` in one file; no `cast(` in the sidecar read; `exit=1` with a message and no traceback; mypy clean; the suite green at 100%.

- [ ] **Step 2: Run the repo-root checks**

```bash
cd /home/davor/projects/PhD/defendable-science
./tools/validate-plugin.sh
pre-commit run --all-files
```

- [ ] **Step 3: Open the PR**

Use the local `create-pr` skill. The body must carry `Closes #169`, and must state the two places this landed differently from the issue as filed:

1. The boundary rule is "data entering the process", not provenance — the issue's own wording did not cover the acquire sidecar, which it then asked us to model (spec §3.1).
2. Slice 5 converted two of five sites, not five. `_parse_json_object` has no domain error to translate to; `--points` and `--cells` would duplicate a longhand schema and degrade asserted CLI messages. Both exclusions follow from the issue's own "with no loss of message quality" criterion (Task 6 Step 5).

Also note that `enrich_work`'s output shape — which the issue floated modelling — was filed as #174 instead, because ADR-0043 point 2 forbids a Pydantic model over data the package only emits.
