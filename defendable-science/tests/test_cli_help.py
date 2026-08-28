"""``--help`` output must never leak MyST field-list markup (#152).

Typer renders a command's raw docstring as its ``--help`` text when no
explicit ``help=`` is given, but ``CLAUDE.md`` requires MyST field-list
docstrings (``:param:``/``:returns:``/``:raises:``) for maintainers, mypy and
the docs build. `defendable_science.cli.DocstringTyper` reconciles the two by
deriving each command's ``--help`` text from the docstring's prose only. This
module walks the full Click command tree — so a command added later is
covered automatically — and pins that no leaf leaks field-list syntax.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import typer
from typer.testing import CliRunner

if TYPE_CHECKING:
    from collections.abc import Iterator

from defendable_science.cli import (
    _prose_only,
    _role_target,
    _strip_inline_roles,
    app,
)

runner = CliRunner()

# The full set of MyST field-list markers actually used in cli.py docstrings
# (confirmed by grepping `^\s*:\w` there); `:rtype` is included even though
# unused today, matching the issue's acceptance criterion.
_FIELD_MARKERS = (":param", ":returns", ":raises", ":rtype")


def _unstyled(text: str) -> str:
    """Strip ANSI styling from rendered help.

    Rich styles parts of the output when colour is forced, which can split a
    marker like ``:param`` with escape sequences, so a plain substring search
    finds nothing. CI sets ``FORCE_COLOR``, so a test asserting on raw
    ``--help`` output passes on a developer's machine and fails there — assert
    on the text a reader sees, not on how a terminal happened to paint it.
    See ``tests/test_progress_cli.py::_unstyled`` for the same helper.

    :param text: Raw, possibly ANSI-styled, command output.
    :returns: `text` with SGR escape sequences removed.
    """
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _flatten(text: str) -> str:
    """Collapse Rich's panel borders and line-wrap newlines to single spaces.

    Rich wraps option help text inside a bordered panel, so a phrase can be
    split by a ``│`` border plus a newline rather than by plain whitespace.

    :param text: Unstyled command output that may be wrapped across lines.
    :returns: `text` with panel borders removed and every run of whitespace
        collapsed to one space, so a multi-word substring survives regardless
        of terminal width.
    """
    return re.sub(r"\s+", " ", text.replace("│", " ")).strip()


def _iter_commands(
    command: Any, path: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], Any]]:
    """Yield every command and group in the tree rooted at `command`.

    Typer vendors its own Click fork (``typer._click``) rather than depending
    on an installed ``click`` package, so this walks the tree structurally
    (``commands`` is a group's mapping of name to sub-command) instead of
    importing Click types directly.

    :param command: The Typer/Click command (or group) to walk.
    :param path: The argv path already taken to reach `command`.
    :returns: A depth-first iterator of (`path`, `command`) pairs, covering
        `command` itself and every nested subcommand.
    """
    yield path, command
    sub_commands = getattr(command, "commands", None)
    if sub_commands:
        for name, sub in sub_commands.items():
            yield from _iter_commands(sub, (*path, name))


def test_no_command_help_leaks_a_myst_field_list() -> None:
    """Every registered command/group's ``--help`` is free of field-list syntax."""
    root = typer.main.get_command(app)
    seen = []
    for path, _command in _iter_commands(root):
        result = runner.invoke(app, [*path, "--help"])
        assert result.exit_code == 0, (path, result.output)
        output = _unstyled(result.stdout)
        for marker in _FIELD_MARKERS:
            assert marker not in output, (path, marker, output)
        seen.append(path)

    # Sanity check the walk actually reached every documented group, so a
    # change that (e.g.) stops recursing into subgroups can't pass silently.
    for group in ("literature", "dataset", "defend", "backlog", "keys", "digest"):
        assert (group,) in seen
    assert ("digest", "extract") in seen
    assert ("progress", "dashboard") in seen
    # Root + ~9 groups + ~35 leaf commands, give or take.
    assert len(seen) > 30


def test_init_help_keeps_prose_and_option_help() -> None:
    result = runner.invoke(app, ["init", "--help"])
    assert result.exit_code == 0
    output = _flatten(_unstyled(result.stdout))
    assert (
        "Scaffold the consumer layout, and report every path considered as JSON."
        in output
    )
    assert "Also scaffold the optional thesis tree." in output
    assert "Report what would be written; write nothing." in output


def test_check_help_keeps_prose_and_option_help() -> None:
    result = runner.invoke(app, ["check", "--help"])
    assert result.exit_code == 0
    output = _flatten(_unstyled(result.stdout))
    assert "Report the repo's validity state as JSON." in output
    assert "Print a human-readable summary instead of JSON." in output


def test_defend_record_help_keeps_prose_and_option_help() -> None:
    result = runner.invoke(app, ["defend", "record", "--help"])
    assert result.exit_code == 0
    output = _flatten(_unstyled(result.stdout))
    assert "Record a" in output
    assert "examination: patch understanding + log." in output
    assert "Transcript file, or '-' for stdin." in output


def test_prose_only_strips_a_field_list_and_dedents() -> None:
    doc = """Summary line.

    More prose here.

    :param x: something
    :returns: a value
    :raises ValueError: whatever
    """
    assert _prose_only(doc) == "Summary line.\n\nMore prose here."


def test_prose_only_leaves_a_fieldless_docstring_unchanged_modulo_dedent() -> None:
    doc = """Only prose, no fields.

    Second paragraph.
    """
    assert _prose_only(doc) == "Only prose, no fields.\n\nSecond paragraph."


def test_prose_only_of_none_or_empty_is_empty() -> None:
    assert _prose_only(None) == ""
    assert _prose_only("") == ""


def test_prose_only_strips_an_inline_role_in_the_kept_prose() -> None:
    doc = """Mentions :func:`resolve_root` inline.

    :param x: something
    """
    assert _prose_only(doc) == "Mentions resolve_root inline."


def test_strip_inline_roles_renders_tilde_targets_as_their_last_component() -> None:
    text = "See :func:`resolve_root` and :class:`~pkg.mod.Thing`."
    assert _strip_inline_roles(text) == "See resolve_root and Thing."


def test_role_target_passes_through_a_plain_target() -> None:
    assert _role_target("resolve_root") == "resolve_root"


def test_role_target_resolves_a_tilde_prefixed_dotted_target() -> None:
    assert _role_target("~pkg.mod.Thing") == "Thing"
