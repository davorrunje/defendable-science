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
#: Pipeline separators, split *before* matching so an invocation downstream of a
#: pipe is still extracted rather than discarded with its whole line.
_PIPELINE = re.compile(r"\s(?:\||&&|;)\s")
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
#: The phrase must sit immediately before the span — only words and spaces may
#: follow it — so an unrelated negation elsewhere in the sentence cannot suppress
#: a real invocation. Any punctuation between the two (``resources/templates/README.md``
#: has "…has **not** been generated); `defendable-science progress dashboard`…")
#: means the negation is not about this span.
_NEGATION = re.compile(r"\b(no|not|never|instead of|rather than)\b[\w\s]{0,24}$", re.I)


class Invocation(NamedTuple):
    """One documented call site."""

    line: int
    args: str
    #: ``fence`` lines are verbatim commands; ``inline`` spans are references.
    kind: Literal["fence", "inline"]


def _fenced_blocks(text: str) -> Iterator[list[tuple[int, str]]]:
    r"""Yield each fenced code block as its own list of ``(line number, line)``.

    Prose names the product constantly ("the defendable-science user guide"), so
    only code context counts as an invocation. Blocks stay separate so a fence
    whose last line ends in ``\`` cannot fold the *next* fence's first line into
    a bogus joined command reported at the wrong line.

    :param text: The document's markdown.
    :returns: One list per block, the fence markers themselves excluded.
    """
    block: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), 1):
        if _FENCE.match(line):
            if in_fence and block:
                yield block
            block, in_fence = [], not in_fence
            continue
        if in_fence:
            block.append((number, line))
    if block:  # pragma: no cover - a document ending inside an unclosed fence
        yield block


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
    for block in _fenced_blocks(text):
        for number, line in _join_continuations(block):
            # Split the pipeline first: an invocation is not always the head of
            # its line. `docs/guides/keys.md` documents
            # `echo "$MY_KEY" | defendable-science keys set S2_API_KEY`, which
            # anchoring to the line start missed entirely.
            for segment in _PIPELINE.split(line):
                if match := _LINE_START.match(segment.strip()):
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

    # A required *option* omitted from a verbatim example exits 2 exactly as a
    # missing positional does. Eight commands in the tree have one.
    given = {token.partition("=")[0] for token in rest}
    for param in command.params:
        if param.param_type_name == "option" and param.required:
            assert given & set(param.opts), (
                f"{where}: `{_name(command)}` requires {param.opts[0]}, "
                f"which the documented call omits"
            )


def test_the_guard_actually_found_invocations() -> None:
    """A glob or regex that silently matched nothing would make this vacuous.

    The floors sit ~15% below the real counts: tight enough that losing a chunk
    of the corpus fails (an earlier revision asserted ``>= 40`` against 101
    actual, which is how a backtick-pairing bug that hid a third of the inline
    spans went unnoticed), loose enough that ordinary docs edits do not.
    """
    counts = Counter(c.kind for c in _CASES)
    #: kind -> (floor, count when written). Floors sit ~15% below the real count.
    floors: dict[Literal["fence", "inline"], tuple[int, int]] = {
        "fence": (50, 58),
        "inline": (55, 63),
    }
    remedy = (
        "if invocations were removed on purpose, lower the floor in this test; "
        "if not, the extractor has stopped seeing part of the corpus"
    )
    for kind, (floor, when_written) in floors.items():
        assert counts[kind] >= floor, (
            f"{kind} invocations dropped to {counts[kind]}, below the {floor} "
            f"floor ({when_written} when written) — {remedy}"
        )
    total = sum(floor for floor, _ in floors.values())
    assert len(_CASES) >= total, f"{counts} — {remedy}"
    documents = {c.doc for c in _CASES}
    # Every skill that documents a command must contribute at least one case;
    # `hypothesis-exploration` and `dataset` silently yielded zero before the
    # fence-blanking fix.
    for skill in ("hypothesis-exploration", "dataset", "digest", "progress"):
        assert any(d == f"skills/{skill}/SKILL.md" for d in documents), (
            f"no invocation found in skills/{skill}/SKILL.md"
        )
    assert any(d.startswith("docs/") for d in documents), documents


def test_an_invocation_downstream_of_a_pipe_is_extracted() -> None:
    """`docs/guides/keys.md:54` pipes into the CLI; it used to yield nothing."""
    found = list(
        _invocations(
            '```bash\necho "$MY_KEY" | defendable-science keys set S2_API_KEY\n```'
        )
    )
    assert found == [Invocation(2, "keys set S2_API_KEY", "fence")], found


def test_a_negation_after_an_earlier_span_does_not_suppress_this_one() -> None:
    """The negation must sit immediately before the span it disowns."""
    found = list(
        _invocations(
            "| `defendable-science init` (a stub saying it has not been "
            "generated); `defendable-science progress dashboard` generates it |"
        )
    )
    assert [f.args for f in found] == ["init", "progress dashboard"], found


def test_a_trailing_backslash_does_not_leak_across_a_fence_boundary() -> None:
    """Each fenced block joins its own continuations, so blocks cannot merge."""
    found = list(
        _invocations(
            "```bash\ndefendable-science check \\\n```\n\n"
            "```bash\ndefendable-science progress dashboard\n```\n"
        )
    )
    assert [(f.line, f.args) for f in found] == [
        (2, "check"),
        (6, "progress dashboard"),
    ], found


def test_a_missing_required_option_is_caught() -> None:
    """A verbatim example omitting a required option exits 2 at the point of use."""
    with pytest.raises(AssertionError, match="requires --provenance"):
        test_documented_invocation_resolves(
            Case("x.md", 1, 'backlog park "idea"', "fence")
        )


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
    """A negation elsewhere in the sentence is not about this span.

    "has **not** been generated by `defendable-science init`" says `init` writes
    the stub — it does not say `init` is absent, so `init` must still be checked.
    An earlier revision of the rule dropped it, and this test asserted that
    wrongly; the punctuation between the negation and the span is the signal.
    """
    found = list(
        _invocations(
            "a stub saying it has **not** been generated by "
            "`defendable-science init`; run `defendable-science progress dashboard`.\n"
        )
    )
    assert [f.args for f in found] == ["init", "progress dashboard"], found


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
