"""Host-preserving YAML-frontmatter editing for markdown artifacts.

An artifact's frontmatter is a human's file: it carries comments, key order and
whitespace that the person who wrote it chose. These helpers set one key under
the ``status:`` block and leave every other byte alone — the same posture
:mod:`defendable_science.core.mdtable` takes toward the table inside a document.

Promoted here (unchanged) from ``defend/record.py`` when ``digest`` extraction
needed the same editing without importing another front-end's private helpers,
exactly as ``core/fixity.py``, ``core/mirror.py``, ``core/download.py`` and
``core/mdtable.py`` were promoted before it.
"""

from __future__ import annotations

import re


class FrontmatterError(ValueError):
    """Raised when a document's YAML frontmatter is missing or malformed."""


def split_frontmatter(text: str) -> tuple[list[str], list[str]]:
    """Split a markdown doc into (frontmatter lines, body lines).

    :param text: The document's markdown content.
    :returns: The frontmatter lines (without the ``---`` fences) and the body
        lines.
    :raises FrontmatterError: If there is no terminated ``---`` frontmatter
        block.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError("artifact has no YAML frontmatter")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], lines[i + 1 :]
    raise FrontmatterError("artifact has an unterminated frontmatter block")


def rebuild(fm_lines: list[str], body_lines: list[str]) -> str:
    """Reassemble a document from frontmatter and body lines.

    :param fm_lines: The frontmatter lines, without their ``---`` fences.
    :param body_lines: The body lines.
    :returns: The reassembled document, newline-terminated.
    """
    parts = ["---", *fm_lines, "---", *body_lines]
    return "\n".join(parts) + "\n"


def _split_comment(raw_value: str) -> tuple[str, str]:
    """Split a YAML value's text from its trailing comment.

    A YAML comment needs whitespace before ``#`` (or the value is entirely a
    comment); a ``#`` *inside* a value is not a comment delimiter.

    :param raw_value: Everything after ``key:`` on the line.
    :returns: The value text (stripped), and the rendered trailing comment
        (``""`` when there is none).
    """
    padded = f" {raw_value}"
    cmatch = re.search(r"\s#(.*)$", padded)
    if cmatch is None:
        return raw_value.strip(), ""
    return padded[: cmatch.start()].strip(), f"  # {cmatch.group(1).strip()}"


def _block_value_extent(lines: list[str], start: int, child_indent: str) -> int:
    """Return the index one past the block mapping nested under ``lines[start]``.

    ``lines[start]`` is a ``key:`` line whose value is empty, so the value is
    whatever more-indented lines follow it. Blank lines inside the block are
    consumed; blank lines *after* it are not, so a reader's spacing survives.

    :param lines: The frontmatter lines.
    :param start: Index of the ``key:`` line.
    :param child_indent: The indentation of ``status:``'s own children.
    :returns: The exclusive end index of the key's value.
    """
    end = start + 1
    i = start + 1
    while i < len(lines):
        line = lines[i]
        if line.strip():
            if len(line) - len(line.lstrip()) <= len(child_indent):
                break
            end = i + 1
        i += 1
    return end


def set_field(fm_lines: list[str], key: str, value: str) -> list[str]:
    """Set ``status.<key>`` to `value`, preserving any trailing comment.

    Replaces the existing value if the key is present — whether it was written
    inline (``key: {…}``) or as an indented **block mapping** underneath, which
    is how a human following a documented example writes it. Replacing only the
    ``key:`` line of a block mapping would orphan its children and leave the
    frontmatter unparseable, so the whole value goes. Otherwise the key is
    inserted directly under the ``status:`` block. Indentation is taken from
    the block's children.

    :param fm_lines: The frontmatter lines (mutated copy returned).
    :param key: The child key under ``status:`` (e.g. ``understanding``).
    :param value: The rendered YAML value.
    :returns: The updated frontmatter lines.
    :raises FrontmatterError: If there is no ``status:`` block, or if the block
        mapping being replaced carries a comment. A comment on a value this
        call is about to overwrite cannot be round-tripped, and destroying a
        human's annotation silently is the failure `patch_triage` refuses for
        the same reason.
    """
    lines = list(fm_lines)
    status_idx = next(
        (i for i, ln in enumerate(lines) if re.match(r"^status:\s*$", ln)), None
    )
    if status_idx is None:
        raise FrontmatterError("artifact frontmatter has no 'status:' block")

    child_indent = "  "
    for ln in lines[status_idx + 1 :]:
        if ln.strip() and (stripped_indent := len(ln) - len(ln.lstrip())) > 0:
            child_indent = " " * stripped_indent
            break

    key_pat = re.compile(rf"^{re.escape(child_indent)}{re.escape(key)}:\s*(.*)$")
    for i in range(status_idx + 1, len(lines)):
        line = lines[i]
        # Stop at a dedent back to top level (end of the status block).
        if line.strip() and not line.startswith(child_indent):
            break
        match = key_pat.match(line)
        if match:
            value_text, comment = _split_comment(match.group(1))
            end = i + 1 if value_text else _block_value_extent(lines, i, child_indent)
            annotated = [ln for ln in lines[i + 1 : end] if _split_comment(ln)[1]]
            if annotated:
                raise FrontmatterError(
                    f"'status.{key}' is a block mapping carrying a comment "
                    f"({annotated[0].strip()!r}), and this write replaces the "
                    "whole value — move the note onto the "
                    f"'{key}:' line or remove it, then re-run"
                )
            lines[i:end] = [f"{child_indent}{key}: {value}{comment}"]
            return lines

    lines.insert(status_idx + 1, f"{child_indent}{key}: {value}")
    return lines
