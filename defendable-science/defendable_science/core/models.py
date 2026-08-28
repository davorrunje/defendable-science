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
