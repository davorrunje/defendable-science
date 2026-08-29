"""Every documented CLI invocation must resolve against the shipped Typer tree.

The plugin's skills are the CLI's clients: a skill naming a flag the CLI dropped
is a broken skill, and the consumer only finds out at the point of use. Nothing
else in the suite reads a code fence — ``tests/test_plugin_content.py`` opens
``SKILL.md`` but *deliberately skips* fenced blocks, which is exactly where every
invocation lives — so this guard covers the gap from the other side.

Four invocations were shipping broken when it was written: a wrong-case
``--EIG``, two ``dataset verify`` calls missing their required identifier, and a
backlog header the writer refuses.

Follows ``tests/test_plugin_content.py`` and ``tests/test_status.py``: the wheel
ships only ``defendable_science`` and cannot read plugin content (ADR-0026), so
the plugin↔package contract can only be enforced from a repo checkout, in tests.

Two deliberate limits, each earned by a false positive found while writing this:

*Structure, not values.* Option values are never type-converted, because
documentation writes placeholders (``<id>``, ``<paper>``) where a real run takes
data. A documented call is checked for commands, flags and argument arity.

*A fence is a command; an inline span is a reference.* ``docs/guides/dataset.md``
states the convention itself — "Anything in a shell block is a real command,
verbatim" — against quote blocks you are "not meant to type into a shell". So a
fenced line is held to full arity, while an inline span is only checked for the
names it uses. An inline span is also skipped where the prose *negates* it: three
guides say "There is no ``defendable-science literature scout`` command", and
documenting a command's absence must not read as drift.
"""

from __future__ import annotations

import re
import shlex
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

import pytest
import typer.main

from defendable_science.cli import app
from defendable_science.exploration.backlog import columns_for

if TYPE_CHECKING:
    from collections.abc import Iterator

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Documents whose invocations are meant to run as written. ``docs/design/`` and
#: ``docs/superpowers/`` are deliberately excluded: they are dated design records
#: and historical plans describing what was proposed *at the time*, so a flag
#: that never shipped is an accurate record rather than a defect.
_DOCS: list[Path] = sorted(
    {
        *(_REPO_ROOT / "skills").glob("*/SKILL.md"),
        *(_REPO_ROOT / "resources").rglob("*.md"),
        *(_REPO_ROOT / "docs" / "guides").glob("*.md"),
        _REPO_ROOT / "docs" / "USER-GUIDE.md",
        _REPO_ROOT / "README.md",
    }
)

#: Both console-script names in ``pyproject.toml``'s ``[project.scripts]``.
_ENTRYPOINTS = ("defendable-science", "dsci")
_NAMES = "|".join(_ENTRYPOINTS)

_FENCE = re.compile(r"^\s*(?:```|~~~)")
#: A shell line starting an invocation: optional prompt, then an entrypoint.
_LINE_START = re.compile(rf"^\s*(?:\$\s+)?(?:{_NAMES})\s+(.*)$")
#: An inline code span; ``re.S`` so a span wrapped across a line break is one match.
_INLINE = re.compile(r"`([^`]+)`", re.S)
_INLINE_START = re.compile(rf"^(?:{_NAMES})\s+(.*)$", re.S)
#: Shell syntax ending the command proper; everything after is redirection or
#: another command. ``<`` must be followed by whitespace so a ``<placeholder>``
#: value is not mistaken for an input redirect.
_SHELL_BREAK = re.compile(r"\s(?:\||&&|;|2?>>?|<<?\s)")
#: A blockquote continuation marker. Skills document tooling inside ``>`` quotes,
#: so a span wrapped across such a line carries a leading ``>`` that would
#: otherwise read as an output redirect and truncate the invocation.
_QUOTE_MARKER = re.compile(r"^\s*>\s?", re.M)
#: Usage-synopsis grammar — ``[--flag]``, ``(a| b)``, ``x|y``. These describe a
#: command's shape rather than calling it, so arity and flag checks would both be
#: meaningless. ``...`` counts only as a *standalone* token (``--citekey KEY
#: ...``); inside a path it is an elision of real directories
#: (``docs/research/.../strategy.md``) and the call is runnable.
_SYNOPSIS = re.compile(r"[\[\]()|…]|(?<!\S)\.\.\.")
#: A placeholder standing in for the command itself: ``defendable-science <group> <cmd>``.
_TEMPLATE = re.compile(r"^[<{]")
#: Prose that documents a command's *absence*, e.g. "There is no ``X`` command".
#: Matched against the text between the previous code span and this one, so an
#: unrelated "not" earlier in the sentence cannot suppress a real invocation.
_NEGATION = re.compile(r"\b(no|not|never|instead of|rather than)\b[^.`]*$", re.I)


class Invocation(NamedTuple):
    """One documented call site."""

    line: int
    args: str
    #: ``fence`` lines are verbatim commands; ``inline`` spans are references.
    kind: Literal["fence", "inline"]


def _fenced_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(line number, line)`` for lines inside a fenced code block.

    Prose names the product constantly ("the defendable-science user guide"), so
    only code context counts as an invocation.

    :param text: The document's markdown.
    :returns: The fenced lines, the fence markers themselves excluded.
    """
    in_fence = False
    for number, line in enumerate(text.splitlines(), 1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            yield number, line


def _join_continuations(lines: list[tuple[int, str]]) -> Iterator[tuple[int, str]]:
    """Fold trailing-backslash continuations into one logical line.

    Without this a flag on the second physical line is never checked — and the
    repo's own multi-line examples put half their flags there.

    :param lines: ``(line number, line)`` pairs, in document order.
    :returns: ``(line number of the first physical line, joined text)`` pairs.
    """
    start: int | None = None
    parts: list[str] = []
    for number, line in lines:
        stripped = line.strip()
        if start is None:
            start = number
        parts.append(stripped.removesuffix("\\").strip())
        if not stripped.endswith("\\"):
            yield start, " ".join(p for p in parts if p)
            start, parts = None, []
    if start is not None:  # pragma: no cover - a fence ending mid-continuation
        yield start, " ".join(p for p in parts if p)


def _without_fences(text: str) -> str:
    """Blank every fenced line, keeping the line count so numbering survives.

    A ```` ``` ```` marker is three backticks, so scanning the raw document for
    inline spans mis-pairs every span after the first fenced block — and captures
    a bare fence's whole body as one "span". Both were happening: the guard saw
    44 of 67 real inline invocations, and whole files yielded none.

    :param text: The document's markdown.
    :returns: `text` with fenced regions replaced by empty lines.
    """
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def _invocations(text: str) -> Iterator[Invocation]:
    """Yield every documented invocation in `text`.

    :param text: The document's markdown.
    :returns: An iterator of invocations, entrypoint name already stripped.
    """
    fenced = list(_fenced_lines(text))
    for number, line in _join_continuations(fenced):
        if match := _LINE_START.match(line):
            yield Invocation(number, match.group(1), "fence")

    prose = _without_fences(text)
    for match in _INLINE.finditer(prose):
        span = _QUOTE_MARKER.sub(" ", match.group(1)).strip()
        if not (inner := _INLINE_START.match(span)):
            continue
        # Only back to the previous span on this line: an unrelated negation
        # earlier in the sentence must not discard a real invocation.
        before = prose[: match.start()].rsplit("\n", maxsplit=1)[-1]
        if _NEGATION.search(before):
            continue
        number = prose.count("\n", 0, match.start()) + 1
        yield Invocation(number, " ".join(inner.group(1).split()), "inline")


class Case(NamedTuple):
    """A documented invocation, located."""

    doc: str
    line: int
    args: str
    kind: Literal["fence", "inline"]


def _cases() -> list[Case]:
    """Collect every documented invocation across `_DOCS`, for parametrisation."""
    return [
        Case(str(doc.relative_to(_REPO_ROOT)), found.line, found.args, found.kind)
        for doc in _DOCS
        for found in _invocations(doc.read_text(encoding="utf-8"))
    ]


_CASES = _cases()


def _argv(args: str) -> list[str] | None:
    """Split `args` into argv, or ``None`` when it is not a runnable command.

    :param args: The documented argument string.
    :returns: The tokens up to the first shell operator, or ``None`` for a usage
        synopsis, a bare template, or text that will not lex.
    """
    head = _SHELL_BREAK.split(f" {args}", maxsplit=1)[0]
    if _SYNOPSIS.search(head):
        return None
    try:
        # `comments=True` drops a trailing `# explanation`, which the guides use
        # heavily and which would otherwise count as positional arguments.
        argv = shlex.split(head, comments=True)
    except ValueError:
        return None
    if not argv or _TEMPLATE.match(argv[0]):
        return None
    return argv


def _walk(root: Any, argv: list[str], where: str) -> tuple[Any, list[str]]:
    """Resolve leading subcommand names, returning the command and the rest.

    :param root: The root Click command.
    :param argv: The invocation's tokens.
    :param where: ``path:line``, for the failure message.
    :returns: ``(resolved command, remaining tokens)``.
    """
    command, rest = root, list(argv)
    while rest and not rest[0].startswith("-"):
        subcommands = getattr(command, "commands", None)
        if not subcommands:
            break
        name = rest[0]
        assert name in subcommands, (
            f"{where}: `{name}` is not a command of `{_name(command)}` "
            f"(have {sorted(subcommands)})"
        )
        command, rest = subcommands[name], rest[1:]
    return command, rest


def _name(command: Any) -> str:
    """Return the command's own name, for a failure message."""
    return str(getattr(command, "name", None) or "defendable-science")


def _options(command: Any) -> dict[str, Any]:
    """Map every option string `command` accepts to its parameter."""
    index: dict[str, Any] = {}
    for param in command.params:
        if param.param_type_name != "option":
            continue
        for opt in (*param.opts, *getattr(param, "secondary_opts", ())):
            index[opt] = param
    return index


def _arguments(command: Any) -> list[Any]:
    """Return the command's positional parameters, in declaration order."""
    return [p for p in command.params if p.param_type_name == "argument"]


def _count_positionals(rest: list[str], options: dict[str, Any], where: str) -> int:
    """Check every flag against `options` and count the positional arguments.

    :param rest: Tokens after the command path.
    :param options: The command's accepted option strings.
    :param where: ``path:line``, for the failure message.
    :returns: The number of positional arguments the call passes.
    """
    positionals = 0
    index = 0
    while index < len(rest):
        token = rest[index]
        index += 1
        if not token.startswith("-") or token == "-":
            positionals += 1
            continue
        if token == "--":
            return positionals + len(rest) - index
        name, _, inline_value = token.partition("=")
        if name in ("--help", "-h"):
            continue
        assert name in options, f"{where}: no option {name!r} (have {sorted(options)})"
        param = options[name]
        if not inline_value and not getattr(param, "is_flag", False):
            index += max(param.nargs, 0)
    return positionals


@pytest.mark.parametrize("case", _CASES, ids=[f"{c.doc}:{c.line}" for c in _CASES])
def test_documented_invocation_resolves(case: Case) -> None:
    """A documented command, its flags and its argument arity all exist."""
    where = f"{case.doc}:{case.line}"
    argv = _argv(case.args)
    if argv is None:
        pytest.skip(f"{where}: a synopsis or template, not a runnable invocation")

    command, rest = _walk(typer.main.get_command(app), argv, where)
    positionals = _count_positionals(
        rest, _options(command), f"{where}: `{_name(command)}`"
    )

    if case.kind == "inline":
        # An inline span names a command; it is not obliged to be a complete
        # call. `resources/templates/README.md` lists `backlog promote
        # --scaffold` in a "what writes this file" table, with no row id.
        return

    required = [p.name for p in _arguments(command) if p.required]
    assert positionals >= len(required), (
        f"{where}: `{_name(command)}` requires {required} but the documented "
        f"call passes {positionals} positional argument(s)"
    )
    arguments = _arguments(command)
    # No `arguments and` guard: `all([])` is True and `sum([])` is 0, so a
    # command taking *no* positionals is exactly the case that must be checked —
    # `defendable-science check junk` exits 2, and used to pass this guard.
    if all(p.nargs > 0 for p in arguments):
        accepted = sum(p.nargs for p in arguments)
        assert positionals <= accepted, (
            f"{where}: `{_name(command)}` takes at most {accepted} positional "
            f"argument(s), but the documented call passes {positionals}"
        )


def test_the_guard_actually_found_invocations() -> None:
    """A glob or regex that silently matched nothing would make this vacuous.

    The floors are close to the real counts on purpose. An earlier revision
    asserted ``>= 40`` against 101 actual cases, which is why a backtick-pairing
    bug that lost a third of the inline corpus went unnoticed: any floor slack
    enough to never need updating is also slack enough to hide silent drift.
    """
    assert len(_CASES) >= 95, f"only found {len(_CASES)} invocations"
    by_kind = Counter(c.kind for c in _CASES)
    assert by_kind["fence"] >= 30, by_kind
    assert by_kind["inline"] >= 60, by_kind
    documents = {c.doc for c in _CASES}
    # Every skill that documents a command must contribute at least one case;
    # `hypothesis-exploration` and `dataset` silently yielded zero before the
    # fence-blanking fix.
    for skill in ("hypothesis-exploration", "dataset", "digest", "progress"):
        assert any(d == f"skills/{skill}/SKILL.md" for d in documents), (
            f"no invocation found in skills/{skill}/SKILL.md"
        )
    assert any(d.startswith("docs/") for d in documents), documents


def test_inline_spans_survive_a_preceding_fenced_block() -> None:
    """Backtick parity must not shift across a fence (the 44-of-67 bug)."""
    found = list(
        _invocations(
            "```bash\ndefendable-science check\n```\n\n"
            "Then run `defendable-science progress dashboard` to refresh it.\n"
        )
    )
    assert found == [
        Invocation(2, "check", "fence"),
        Invocation(5, "progress dashboard", "inline"),
    ], found


def test_a_bare_fence_body_is_not_read_as_one_inline_span() -> None:
    """An unlabelled fence's backticks used to swallow its whole body."""
    found = list(
        _invocations(
            "```\ndefendable-science init --dry-run\n"
            "defendable-science literature verify --all\n```\n"
        )
    )
    assert [f.kind for f in found] == ["fence", "fence"], found


def test_an_elided_path_is_not_a_synopsis() -> None:
    """`...` inside a path is an elision; only a standalone `...` is grammar."""
    assert _argv("defend record --artifact docs/research/.../strategy.md") == [
        "defend",
        "record",
        "--artifact",
        "docs/research/.../strategy.md",
    ]
    assert _argv("digest extract sample --citekey KEY ...") is None


def test_an_unrelated_negation_does_not_discard_an_invocation() -> None:
    """Only the text since the previous code span counts as the negation."""
    found = list(
        _invocations(
            "a stub saying it has **not** been generated by "
            "`defendable-science init`; run `defendable-science progress dashboard`.\n"
        )
    )
    assert [f.args for f in found] == ["progress dashboard"], found


def test_a_blockquote_continuation_does_not_truncate_a_span() -> None:
    """Skills document tooling inside `>` quotes; `>` is not a redirect here."""
    found = list(
        _invocations(
            "> **Tooling.** Append is the `defendable-science backlog\n> park` verb."
        )
    )
    assert found == [Invocation(1, "backlog park", "inline")], found


def test_the_guard_reads_fenced_blocks_and_joins_continuations() -> None:
    """The gap this exists to close: `test_plugin_content.py` skips fences."""
    found = list(
        _invocations(
            "prose names the defendable-science user guide\n"
            "\n"
            "```bash\n"
            "defendable-science check --strict \\\n"
            "    --root .\n"
            "```\n"
        )
    )
    assert found == [Invocation(4, "check --strict --root .", "fence")], found


def test_the_guard_reads_an_inline_span_wrapped_across_a_line_break() -> None:
    """Skills name commands mid-sentence, and the span can wrap."""
    found = list(_invocations("Append is the `defendable-science backlog\npark` verb."))
    assert found == [Invocation(1, "backlog park", "inline")], found


def test_the_guard_skips_a_documented_absence() -> None:
    """Documenting a command's absence must not read as drift."""
    assert not list(
        _invocations("There is no `defendable-science literature scout` command.")
    )


def test_the_guard_skips_a_usage_synopsis() -> None:
    """Bracket/pipe grammar describes a command's shape, it does not call it."""
    assert _argv("digest extract sample (--citekey KEY ...| --all) [--size N]") is None


def test_the_guard_drops_a_trailing_shell_comment() -> None:
    """The guides annotate examples heavily; a comment is not an argument."""
    assert _argv("keys path      # print the resolved store path") == ["keys", "path"]


def test_documented_backlog_header_matches_the_column_profile() -> None:
    """A header a skill tells the author to hand-write must be one `Backlog` accepts.

    ``skills/hypothesis-exploration/SKILL.md`` tells the agent to keep the
    documented column order "so the ``backlog`` verbs can parse it", so a header
    that drifts from :func:`columns_for` makes the table permanently unwritable:
    ``Backlog._append`` refuses it.
    """
    skill = _REPO_ROOT / "skills" / "hypothesis-exploration" / "SKILL.md"
    header = re.search(r"^\|\s*id\s*\|.*$", skill.read_text(encoding="utf-8"), re.M)
    assert header is not None, f"{skill.name}: no backlog header row found"
    documented = [c.strip() for c in header.group(0).strip().strip("|").split("|")]
    assert documented == columns_for("hypothesis")
