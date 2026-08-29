from __future__ import annotations

import pytest

from defendable_science.core import models


class _Widget(models.ExternalModel):
    name: str
    count: int | None = None


class _Sealed(models.OwnedModel):
    name: str


class _BoomError(Exception):
    """A stand-in for a module's own domain error."""


def test_parse_obj_returns_the_model() -> None:
    got = models.parse_obj(
        _Widget, {"name": "a", "count": 2}, source="s", error=_BoomError
    )
    assert got.name == "a"
    assert got.count == 2


def test_parse_obj_ignores_unknown_fields_on_an_external_model() -> None:
    got = models.parse_obj(
        _Widget, {"name": "a", "surprise": 1}, source="s", error=_BoomError
    )
    assert got.name == "a"


def test_parse_obj_rejects_unknown_fields_on_an_owned_model() -> None:
    with pytest.raises(_BoomError, match=r"store\.json: surprise: "):
        models.parse_obj(
            _Sealed, {"name": "a", "surprise": 1}, source="store.json", error=_BoomError
        )


def test_parse_obj_is_strict_about_scalar_types() -> None:
    # The defect-4 guarantee: a stringified number is rejected, not coerced.
    with pytest.raises(_BoomError, match=r"count: "):
        models.parse_obj(
            _Widget, {"name": "a", "count": "2"}, source="s", error=_BoomError
        )


def test_parse_obj_names_the_source_and_every_bad_field() -> None:
    with pytest.raises(_BoomError) as caught:
        models.parse_obj(_Widget, {"count": "x"}, source="api/works", error=_BoomError)
    message = str(caught.value)
    assert message.startswith("api/works: ")
    assert "name: " in message
    assert "count: " in message
    assert "; " in message


def test_parse_obj_reports_a_nested_field_path() -> None:
    class _Outer(models.ExternalModel):
        inner: _Widget

    with pytest.raises(_BoomError, match=r"inner\.name: "):
        models.parse_obj(_Outer, {"inner": {}}, source="s", error=_BoomError)


def test_parse_obj_reports_a_non_object_payload_at_the_root() -> None:
    with pytest.raises(_BoomError, match=r"s: <root>: "):
        models.parse_obj(_Widget, [1, 2], source="s", error=_BoomError)


def test_parse_obj_names_the_received_type_at_the_root() -> None:
    # Diagnostic parity with the pre-consolidation hand-rolled messages
    # (Task 6 review): the received value's type is named, not just the
    # field path and reason.
    with pytest.raises(_BoomError, match=r"<root>: .*\(got list\)$"):
        models.parse_obj(_Widget, [1, 2], source="s", error=_BoomError)


def test_parse_obj_names_the_received_type_not_the_value_for_a_container() -> None:
    # The type name, never the value, appears in the message — an input can
    # be an entire API response, and a multi-megabyte error message is its
    # own failure mode.
    with pytest.raises(_BoomError) as caught:
        models.parse_obj(
            _Widget,
            {"name": "a", "count": ["a-very-long-and-distinctive-marker"]},
            source="s",
            error=_BoomError,
        )
    message = str(caught.value)
    assert "(got list)" in message
    assert "a-very-long-and-distinctive-marker" not in message


def test_parse_json_parses_text() -> None:
    got = models.parse_json(_Widget, '{"name": "a"}', source="s", error=_BoomError)
    assert got.name == "a"


def test_parse_json_folds_a_decode_error_into_the_domain_error() -> None:
    with pytest.raises(_BoomError, match=r"f\.json: invalid JSON: "):
        models.parse_json(_Widget, "{oops", source="f.json", error=_BoomError)


def test_parse_json_folds_a_validation_error_into_the_domain_error() -> None:
    with pytest.raises(_BoomError, match=r"f\.json: name: "):
        models.parse_json(_Widget, "{}", source="f.json", error=_BoomError)


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
    out = subprocess.run(
        ["grep", "-rln", "--include=*.py", "ValidationError", str(root)],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    assert [pathlib.Path(p).name for p in out] == ["models.py"]
