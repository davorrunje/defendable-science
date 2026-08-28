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


def set_field(fm_lines: list[str], key: str, value: str) -> list[str]:
    """Set ``status.<key>`` to `value`, preserving any trailing comment.

    Replaces the existing line if present; otherwise inserts it directly under
    the ``status:`` block. Indentation is taken from the block's children.

    :param fm_lines: The frontmatter lines (mutated copy returned).
    :param key: The child key under ``status:`` (e.g. ``understanding``).
    :param value: The rendered YAML value.
    :returns: The updated frontmatter lines.
    :raises FrontmatterError: If there is no ``status:`` block.
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
            # A YAML comment needs whitespace before '#' (or the value is entirely
            # a comment); a '#' *inside* a value is not a comment delimiter.
            raw_value = match.group(1)
            comment = ""
            cmatch = re.search(r"\s#(.*)$", f" {raw_value}")
            if cmatch:
                comment = f"  # {cmatch.group(1).strip()}"
            lines[i] = f"{child_indent}{key}: {value}{comment}"
            return lines

    lines.insert(status_idx + 1, f"{child_indent}{key}: {value}")
    return lines
