#!/usr/bin/env python3
"""Build the ``honest-scholar`` Mintlify docs site from the in-repo markdown.

This is a **standalone build tool**, not part of the shipped package (it lives in
``tools/`` and is outside the package's coverage/lint gate). It assembles the
"one portal" documented in ``docs/design/proposals/docs-site.md`` / ADR-0030 from
the repository's own markdown — nothing is hand-duplicated — and emits a complete
Mintlify site into an output directory:

* an ``index.mdx`` landing page (from ``README.md``),
* a Get-started page (from ``docs/USER-GUIDE.md``),
* one page per ``skills/*/SKILL.md``,
* a **generated** CLI reference (walked live from the ``honest_scholar`` Typer app,
  so it never drifts from the released CLI),
* the design record — specs, proposals, the ADR log, reference digests, disclosure,
* a ``docs.json`` with grouped navigation, brand colours, logo and social links,
* the brand assets (the icon mark, the light/dark navigation logos, the home-page
  hero, the social preview, and the wordmark lockups still embedded by the
  visual-identity page) copied verbatim into the site root.

Intra-repo relative markdown links are rewritten to site routes; links that point
at repo files *not* in the site become absolute ``github.com`` URLs. A link that
points at a file which does not exist is a **hard error** — the build fails loudly
rather than silently dropping content (the repo's failure-honesty rule).

Run it from the ``honest-scholar/`` package directory (so the Typer app imports)::

    cd honest-scholar
    uv run python ../tools/build_docs_site.py --out ../dist/docs-site

or from the repo root under the package project::

    uv run --project honest-scholar python tools/build_docs_site.py --out dist/docs-site

The output directory is created (and, if it already exists, emptied) by the build.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Real Click/Typer types for the CLI-reference walker below. Typer 0.27
    # vendors Click at ``typer._click`` (there is no standalone ``click``
    # dependency to import), and implements command *grouping* itself via
    # ``typer.core.TyperGroup`` rather than a vendored ``click.Group``.
    from typer._click.core import Command, Context, Parameter

# --- constants -------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
GH_REPO = "https://github.com/davorrunje/honest-scholar"
GH_BLOB = f"{GH_REPO}/blob/main/"
GH_TREE = f"{GH_REPO}/tree/main/"

SITE_NAME = "Honest Scholar"
SITE_DESCRIPTION = (
    "Research you can defend — keep your research honest, "
    "especially now that AI is in the loop."
)
# Brand palette (see assets/visual-identity.md). electric blue (#2a1cc8) is the *ground*
# — carried by the nav logos, dark surfaces, and the assets — so it stays out of
# `colors`. Mintlify's `colors.primary` drives links/buttons/active states, so the
# interactive accent is the brand Red: "a single Red accent carries every call
# to action". `light` is a brighter Red for dark-mode chrome; `dark` (which
# Mintlify uses as the primary in light mode) is a deeper Red that clears WCAG AA
# (~4.9:1) for link text on white.
PRIMARY = "#f9463c"
COLOR_LIGHT = "#ff8a7d"
COLOR_DARK = "#c9402e"

# Brand assets copied verbatim into the site root and referenced by absolute path.
FAVICON = "icon-mark.svg"
NAV_LOGO_LIGHT = "nav-logo-light.svg"  # navigation logo — light mode
NAV_LOGO_DARK = "nav-logo-dark.svg"  # navigation logo — dark mode
HERO = "docs-hero.svg"  # full-width home-page hero banner
SOCIAL_PREVIEW = "social-preview.svg"
# The wordmark lockups are still embedded by the visual-identity design page, so
# they are copied into the site even though the nav now uses the dedicated logos.
WORDMARK_LIGHT = "wordmark-lockup-light.svg"
WORDMARK_DARK = "wordmark-lockup-dark.svg"
SITE_ASSETS = (
    FAVICON,
    NAV_LOGO_LIGHT,
    NAV_LOGO_DARK,
    HERO,
    SOCIAL_PREVIEW,
    WORDMARK_LIGHT,
    WORDMARK_DARK,
)
ASSET_ROUTES = frozenset(f"/{name}" for name in SITE_ASSETS)

# Directory links that have no page of their own map to a representative route.
DIR_ALIASES = {
    "decisions": "decisions/index",
    "docs/design": "design/00-meta-spec",
}
# Asset links rewritten to the copied site asset.
ASSET_ALIASES = {f"assets/{name}": f"/{name}" for name in SITE_ASSETS}


class BuildError(Exception):
    """Raised to abort the build with an explicit, actionable message."""


# --- the site plan ----------------------------------------------------------------


def plan() -> tuple[dict[str, str | None], dict[str, object]]:
    """Enumerate the site's pages and navigation from the repository layout.

    :returns: ``(sources, navigation)`` where ``sources`` maps every site route to
        the repo-relative source markdown path (or ``None`` for a generated page),
        and ``navigation`` is the Mintlify ``navigation`` object referencing exactly
        those routes.
    :raises BuildError: If an expected source directory is missing.
    """
    sources: dict[str, str | None] = {}

    def reg(route: str, source: str | None) -> str:
        sources[route] = source
        return route

    reg("index", "README.md")
    reg("get-started/user-guide", "docs/USER-GUIDE.md")

    skills_dir = REPO_ROOT / "skills"
    skills_pages = [
        reg(f"skills/{d.name}", f"skills/{d.name}/SKILL.md")
        for d in sorted(skills_dir.iterdir())
        if (d / "SKILL.md").is_file()
    ]
    if not skills_pages:
        raise BuildError(f"no skills found under {skills_dir}")

    reg("cli-reference", None)

    spec_pages = [
        reg(f"design/{f.stem}", f"docs/design/{f.name}")
        for f in sorted((REPO_ROOT / "docs/design").glob("*.md"))
    ]
    proposal_pages = [
        reg(f"design/proposals/{f.stem}", f"docs/design/proposals/{f.name}")
        for f in sorted((REPO_ROOT / "docs/design/proposals").glob("*.md"))
    ]
    adr_pages = [reg("decisions/index", "decisions/README.md")]
    adr_pages += [
        reg(f"decisions/{f.stem}", f"decisions/{f.name}")
        for f in sorted((REPO_ROOT / "decisions").glob("[0-9]*.md"))
    ]
    ref_pages = [
        reg(f"references/{f.stem}", f"resources/references/{f.name}")
        for f in sorted((REPO_ROOT / "resources/references").glob("*.md"))
    ]
    reg("disclosure", "DISCLOSURE.md")

    navigation: dict[str, object] = {
        "groups": [
            {"group": "Overview", "pages": ["index"]},
            {"group": "Get started", "pages": ["get-started/user-guide"]},
            {"group": "Skills & methodology", "pages": skills_pages},
            {"group": "CLI reference", "pages": ["cli-reference"]},
            {
                "group": "Design & reasoning",
                "pages": [
                    {"group": "Specs", "pages": spec_pages},
                    {"group": "Proposals", "pages": proposal_pages},
                    {"group": "Decisions (ADRs)", "pages": adr_pages},
                    {"group": "Reference digests", "pages": ref_pages},
                    {"group": "Disclosure", "pages": ["disclosure"]},
                ],
            },
        ]
    }
    return sources, navigation


def _routes_in_nav(navigation: dict[str, object]) -> list[str]:
    """Flatten every page route referenced by the navigation tree, in order."""
    out: list[str] = []

    def walk(pages: object) -> None:
        # `pages` is always a list by construction (see `plan()`) — narrow with
        # isinstance rather than a blanket ignore so a genuine shape bug still
        # surfaces as an AssertionError instead of being silently swallowed.
        assert isinstance(pages, list), f"expected a list of nav entries, got {pages!r}"
        for entry in pages:
            if isinstance(entry, str):
                out.append(entry)
            elif isinstance(entry, dict):
                walk(entry["pages"])

    groups = navigation["groups"]
    assert isinstance(groups, list), (
        f"expected navigation['groups'] to be a list, got {groups!r}"
    )
    for group in groups:
        assert isinstance(group, dict), f"expected a nav group dict, got {group!r}"
        walk(group["pages"])
    return out


# --- markdown helpers -------------------------------------------------------------

_MD_INLINE = [
    (re.compile(r"`([^`]*)`"), r"\1"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"\*([^*]+)\*"), r"\1"),
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),
]


def strip_inline_markdown(text: str) -> str:
    """Reduce inline markdown (code, emphasis, links) to its plain text."""
    for pattern, repl in _MD_INLINE:
        text = pattern.sub(repl, text)
    return text


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Split a leading ``---`` frontmatter block (raw text) from the body."""
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not match:
        return None, text
    return match.group(1), match.group(2)


def parse_skill_meta(frontmatter_text: str) -> tuple[str | None, str | None]:
    """Extract ``name`` and ``description`` from a SKILL.md frontmatter block.

    Parsed leniently (not via a strict YAML loader): the plugin's SKILL
    descriptions are single scalars that legitimately contain ``: `` and span
    folded lines, which a strict YAML parser rejects.
    """
    name_match = re.search(r"^name:[ \t]*(.+?)[ \t]*$", frontmatter_text, re.M)
    name = name_match.group(1).strip("\"'") if name_match else None

    desc_match = re.search(r"^description:[ \t]*(.*)$", frontmatter_text, re.M | re.S)
    description = None
    if desc_match:
        raw = re.split(r"\n(?=[A-Za-z_][\w-]*:)", desc_match.group(1), maxsplit=1)[0]
        raw = re.sub(r"^[>|][-+]?[ \t]*", "", raw.strip())
        description = " ".join(raw.split()).strip("\"'") or None
    return name, description


def extract_title(body: str, fallback: str) -> str:
    """Take the first ``# H1`` as the title, else derive one from `fallback`."""
    match = re.search(r"^#\s+(.+)$", body, re.M)
    if match:
        return strip_inline_markdown(match.group(1)).strip()
    return fallback.replace("-", " ").replace("_", " ").strip().capitalize()


def strip_leading_h1(body: str) -> str:
    """Remove the first top-level ``# H1`` line (Mintlify renders the title)."""
    return re.sub(r"^\s*#\s+.+?(\n+)", "", body, count=1)


_MASTHEAD_RE = re.compile(r'\A\s*<p align="center">.*?</p>\s*', re.S)


def strip_leading_masthead(body: str) -> str:
    """Drop a leading centred ``<p align="center">…</p>`` banner block.

    Both ``README.md`` and ``docs/USER-GUIDE.md`` open with a raw-HTML wordmark
    masthead for GitHub. The site has its own logo/chrome, and MDX would escape
    that raw ``<img>`` block into literal text — so it is trimmed here.
    """
    return _MASTHEAD_RE.sub("", body, count=1)


def first_paragraph_description(body: str) -> str | None:
    """Derive a one-line description from the first prose paragraph of `body`."""
    for block in re.split(r"\n\s*\n", body.strip()):
        block = block.strip()
        if not block:
            continue
        head = block.splitlines()[0].lstrip()
        if not head or head[0] in "-*>|#<!:" or head.startswith("```"):
            continue
        text = strip_inline_markdown(" ".join(block.split())).strip()
        if text:
            return truncate(text, 160)
    return None


def truncate(text: str, limit: int) -> str:
    """Truncate `text` to at most `limit` characters on a word boundary."""
    if len(text) <= limit:
        return text
    cut = text[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,.;:—-")
    return f"{cut}…"


def yaml_quote(value: str) -> str:
    """Return `value` as a double-quoted YAML scalar."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def frontmatter(title: str, description: str | None) -> str:
    """Render a Mintlify page frontmatter block."""
    lines = ["---", f"title: {yaml_quote(title)}"]
    if description:
        lines.append(f"description: {yaml_quote(description)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


# --- MDX safety -------------------------------------------------------------------


_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_AUTOLINK_RE = re.compile(r"<((?:https?://|mailto:)[^>\s]+)>")


def _autolink_to_markdown(match: re.Match[str]) -> str:
    """Convert a Markdown autolink to an explicit ``[text](url)`` link.

    Mintlify's MDX parser reads a raw ``<https://…>`` autolink as a JSX tag and
    fails on the ``//``. Rewriting it to an ordinary Markdown link keeps it
    clickable while being MDX-safe. A ``mailto:`` link shows the bare address.
    """
    url = match.group(1)
    text = url[len("mailto:") :] if url.startswith("mailto:") else url
    return f"[{text}]({url})"


def _escape_prose(segment: str) -> str:
    """Escape MDX-hostile characters in a non-code text segment.

    The generated site carries no intentional JSX, so anything tag- or
    expression-like in prose must be neutralised or MDX compilation fails:

    * HTML comments (``<!-- … -->``) are dropped — they are not valid MDX.
    * Markdown autolinks (``<https://…>``, ``<mailto:…>``) are rewritten to
      explicit ``[text](url)`` links so they still render (a raw autolink is
      parsed as JSX and breaks the build).
    * every remaining ``<`` becomes ``&lt;`` (a bare ``<foo>``, ``<0.05``, or
      ``</x>`` in prose is otherwise read as a JSX tag), and ``{`` / ``}`` (JSX
      expression delimiters) become HTML entities.
    """
    segment = _HTML_COMMENT_RE.sub("", segment)
    segment = _AUTOLINK_RE.sub(_autolink_to_markdown, segment)
    segment = segment.replace("{", "&#123;").replace("}", "&#125;")
    return segment.replace("<", "&lt;")


def _escape_prose_region(region: str) -> str:
    """Escape a non-fenced region, preserving inline code spans (even multi-line).

    ``[^`]*?`` spans newlines, so a backtick code span that wraps across a soft
    line break is matched as one token and left intact — its ``{`` / ``<`` are not
    touched.
    """
    parts = re.split(r"(`+[^`]*?`+)", region)
    return "".join(p if p.startswith("`") else _escape_prose(p) for p in parts)


def mdx_safe(text: str) -> str:
    """Make `text` safe to embed in an MDX page, leaving fenced code untouched."""
    out: list[str] = []
    prose: list[str] = []
    code: list[str] = []
    fence: str | None = None

    def flush_prose() -> None:
        if prose:
            out.append(_escape_prose_region("\n".join(prose)))
            prose.clear()

    for line in text.split("\n"):
        stripped = line.lstrip()
        marker = stripped[:3] if stripped[:3] in ("```", "~~~") else None
        if fence is None and marker:
            flush_prose()
            fence = marker
            code = [line]
        elif fence is not None and stripped.startswith(fence):
            code.append(line)
            out.append("\n".join(code))
            fence = None
        elif fence is not None:
            code.append(line)
        else:
            prose.append(line)
    flush_prose()
    if fence is not None:  # an unterminated fence — emit verbatim
        out.append("\n".join(code))
    return "\n".join(out)


def mdx_hazards(text: str) -> list[str]:
    """Report residual MDX-hostile constructs in a *finished* page's prose.

    A best-effort, deliberately independent sanity check (it does not reuse
    :func:`_escape_prose`, so a bug there is caught): after fenced and inline code
    are removed, a literal ``<`` (JSX tag) or ``{`` / ``}`` (JSX expression) in
    prose is something Mintlify's MDX parser would reject — the sanitizer should
    have turned it into an entity. Returned strings are ``"line:col message"``
    describing each hazard; an empty list means clean.
    """
    # The YAML frontmatter is not MDX — its `{ }` / `<` are harmless. Skip it,
    # keeping a line offset so reported positions match the file.
    fm_text, body = split_frontmatter(text)
    offset = text.count("\n", 0, len(text) - len(body)) if fm_text is not None else 0

    # Blank fenced-code lines (keep length so line/col stay accurate).
    masked: list[str] = []
    fence: str | None = None
    for line in body.split("\n"):
        stripped = line.lstrip()
        marker = stripped[:3] if stripped[:3] in ("```", "~~~") else None
        if fence is None and marker:
            fence = marker
            masked.append(" " * len(line))
        elif fence is not None:
            if stripped.startswith(fence):
                fence = None
            masked.append(" " * len(line))
        else:
            masked.append(line)

    # Blank inline code spans (which may wrap across a soft line break),
    # preserving newlines so reported positions stay correct.
    def _blank(match: re.Match[str]) -> str:
        return "".join("\n" if ch == "\n" else " " for ch in match.group(0))

    blob = re.sub(r"`+[^`]*?`+", _blank, "\n".join(masked))

    hazards: list[str] = []
    for lineno, line in enumerate(blob.split("\n"), start=1 + offset):
        for col, ch in enumerate(line, start=1):
            if ch in "<{}":
                hazards.append(f"{lineno}:{col} unescaped {ch!r} (JSX-hostile)")
    return hazards


# --- link rewriting ---------------------------------------------------------------

_LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(\s+\"[^\"]*\")?\s*\)")


def _resolve_target(
    target: str, source: str, route_map: dict[str, str], routes: set[str]
) -> tuple[str, str | None]:
    """Resolve one markdown link target for the page generated from `source`.

    :returns: ``(new_target, error)`` — `error` is set only for a link that points
        at a repository path which does not exist.
    """
    if target.startswith(("#", "/", "//", "mailto:")) or re.match(
        r"^[a-z][a-z0-9+.-]*://", target
    ):
        return target, None

    path_part, sep, anchor = target.partition("#")
    anchor = f"#{anchor}" if sep else ""
    if not path_part:
        return target, None

    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), path_part))
    key = resolved.rstrip("/")

    if key in route_map:
        route = route_map[key]
        if f"/{route}" not in {f"/{r}" for r in routes}:  # pragma: no cover
            return target, f"{source}: link {target!r} maps to unknown route {route!r}"
        return f"/{route}{anchor}", None
    if key in ASSET_ALIASES:
        return f"{ASSET_ALIASES[key]}{anchor}", None
    if key in DIR_ALIASES:
        return f"/{DIR_ALIASES[key]}{anchor}", None

    abspath = REPO_ROOT / resolved
    if abspath.is_dir():
        return f"{GH_TREE}{resolved}{anchor}", None
    if abspath.exists():
        return f"{GH_BLOB}{resolved}{anchor}", None
    return target, f"{source}: broken link {target!r} → {resolved!r} does not exist"


def rewrite_links(
    body: str,
    source: str,
    route_map: dict[str, str],
    routes: set[str],
    errors: list[str],
    site_links: set[str],
) -> str:
    """Rewrite every intra-repo link in `body`; collect errors and site links."""

    def repl(match: re.Match[str]) -> str:
        bang, textseg, target, title = match.groups()
        new_target, error = _resolve_target(target, source, route_map, routes)
        if error:
            errors.append(error)
            return match.group(0)
        stem = new_target.split("#", 1)[0]
        if new_target.startswith("/") and stem not in ASSET_ROUTES:
            site_links.add(stem)
        return f"{bang}[{textseg}]({new_target}{title or ''})"

    return _LINK_RE.sub(repl, body)


# --- CLI reference generation -----------------------------------------------------


def _clean_command_help(help_text: str | None) -> str:
    """Return the prose part of a command docstring (drop RST field lists)."""
    if not help_text:
        return ""
    kept: list[str] = []
    for line in help_text.strip("\n").split("\n"):
        if re.match(r"\s*:(param|arg|returns?|raises|type|rtype|yields?)\b", line):
            break
        kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept).strip())


def _cell(text: str) -> str:
    """Escape a value for use inside a markdown table cell."""
    return " ".join((text or "").split()).replace("|", "\\|") or "—"


def _default_cell(param: Parameter) -> str:
    """Render an option's default value for a table cell."""
    default = getattr(param, "default", None)
    if getattr(param, "is_flag", False):
        return f"`{str(bool(default)).lower()}`"
    if default in (None, ""):
        return "—"
    return f"`{default}`"


def _render_command(
    cmd: Command, ctx_cls: type[Context], parent_ctx: Context | None, path: list[str]
) -> str:
    """Render one Typer/Click command (or group) to a markdown section."""
    # Local import: `generate_cli_reference` already imports `honest_scholar`/typer
    # lazily so the rest of this module works without either installed; mirror
    # that here rather than importing typer unconditionally at module scope.
    from typer.core import TyperGroup

    ctx = ctx_cls(cmd, info_name=path[-1], parent=parent_ctx)
    is_group = isinstance(cmd, TyperGroup)
    params: list[Parameter] = [
        p for p in cmd.get_params(ctx) if getattr(p, "name", None) != "help"
    ]
    arguments = [p for p in params if getattr(p, "param_type_name", "") == "argument"]
    options = [p for p in params if getattr(p, "param_type_name", "") == "option"]

    level = "##" if len(path) == 2 else "###"
    parts = [f"{level} `{' '.join(path)}`", ""]
    prose = _clean_command_help(getattr(cmd, "help", None))
    if prose:
        parts += [prose, ""]

    if not is_group:
        usage = list(path)
        if options:
            usage.append("[OPTIONS]")
        for arg in arguments:
            name = (getattr(arg, "name", "") or "").upper()
            usage.append(name if getattr(arg, "required", False) else f"[{name}]")
        parts += ["```text", " ".join(usage), "```", ""]

    if arguments:
        parts += ["| Argument | Required | Description |", "|---|---|---|"]
        for arg in arguments:
            name = (getattr(arg, "name", "") or "").upper()
            required = "yes" if getattr(arg, "required", False) else "no"
            parts.append(
                f"| `{name}` | {required} | {_cell(getattr(arg, 'help', '') or '')} |"
            )
        parts.append("")

    if options:
        parts += ["| Option | Default | Description |", "|---|---|---|"]
        for opt in options:
            flags = ", ".join(f"`{o}`" for o in getattr(opt, "opts", []))
            parts.append(
                f"| {flags} | {_default_cell(opt)} "
                f"| {_cell(getattr(opt, 'help', '') or '')} |"
            )
        parts.append("")

    if is_group:
        # `is_group` is exactly `isinstance(cmd, TyperGroup)`, but that narrowing
        # doesn't survive the assignment above — re-assert it here so mypy knows
        # `cmd` has `list_commands`/`get_command` (real `TyperGroup`-only methods).
        assert isinstance(cmd, TyperGroup)
        for name in cmd.list_commands(ctx):
            sub = cmd.get_command(ctx, name)
            # `get_command` is `dict.get` under the hood; `name` always comes from
            # this same `commands` mapping via `list_commands`, so it is never None.
            assert sub is not None, f"list_commands returned unknown command {name!r}"
            parts.append(_render_command(sub, ctx_cls, ctx, [*path, name]))

    return "\n".join(parts)


def generate_cli_reference() -> str:
    """Render the ``honest-scholar`` Typer command tree to markdown."""
    import typer
    from typer._click.core import Context
    from typer.core import TyperGroup

    from honest_scholar.cli import app

    root = typer.main.get_command(app)
    root_ctx = Context(root, info_name="honest-scholar")
    intro = _clean_command_help(getattr(root, "help", None))

    body = [
        intro,
        "",
        "Every command emits JSON on success and a clear, non-zero exit with an "
        "actionable message on failure. Run `honest-scholar --version` to print the "
        "installed version. This page is generated from the Typer app on every "
        "build, so it always matches the released CLI.",
        "",
    ]
    if not isinstance(
        root, TyperGroup
    ):  # pragma: no cover - the app always has >1 command
        raise BuildError("honest-scholar CLI root is not a command group")
    for name in root.list_commands(root_ctx):
        sub = root.get_command(root_ctx, name)
        assert sub is not None, f"list_commands returned unknown command {name!r}"
        body.append(_render_command(sub, Context, root_ctx, ["honest-scholar", name]))
    return "\n".join(body)


# --- page assembly ----------------------------------------------------------------


def build_page(
    route: str,
    source: str | None,
    route_map: dict[str, str],
    routes: set[str],
    errors: list[str],
    site_links: set[str],
) -> str:
    """Assemble one MDX page (frontmatter + transformed body)."""
    if source is None:  # the generated CLI reference
        title = "CLI reference"
        description = "The honest-scholar command tree, generated from the Typer app."
        raw = generate_cli_reference()
        body = rewrite_links(
            raw, "docs/USER-GUIDE.md", route_map, routes, errors, site_links
        )
        return frontmatter(title, description) + "\n" + mdx_safe(body).strip() + "\n"

    text = (REPO_ROOT / source).read_text(encoding="utf-8")
    fm_text, body = split_frontmatter(text)
    skill_name, skill_desc = parse_skill_meta(fm_text) if fm_text else (None, None)

    if route == "index":
        # README opens with a centred HTML masthead + badges, then a `---` rule;
        # drop everything through that rule and use the canonical site identity.
        lines = body.split("\n")
        if "---" in lines:
            body = "\n".join(lines[lines.index("---") + 1 :])
        title, description = SITE_NAME, SITE_DESCRIPTION
        # Full-width home-page hero above the intro text. A Markdown image is the
        # MDX-safe construct here (no raw JSX for the sanitizer to mangle); the
        # target is a copied site asset, so rewrite_links leaves it untouched.
        body = f"![{SITE_NAME}](/{HERO})\n\n{body.lstrip()}"
    elif skill_name:  # a SKILL.md
        title = skill_name
        description = truncate(skill_desc or title, 200)
        body = strip_leading_h1(body)
    else:
        # docs/USER-GUIDE.md opens with the same centred wordmark masthead as the
        # README; strip it before deriving the title/description (the site has its
        # own chrome, and the raw <img> block is not valid MDX).
        body = strip_leading_masthead(body)
        fallback = Path(source).stem
        title = extract_title(body, fallback)
        description = first_paragraph_description(strip_leading_h1(body)) or title
        body = strip_leading_h1(body)

    body = rewrite_links(body, source, route_map, routes, errors, site_links)
    return (
        frontmatter(title, description or None) + "\n" + mdx_safe(body).strip() + "\n"
    )


def build_docs_json(navigation: dict[str, object]) -> dict[str, object]:
    """Assemble the Mintlify ``docs.json`` configuration."""
    return {
        "$schema": "https://mintlify.com/docs.json",
        "theme": "mint",
        "name": SITE_NAME,
        "description": SITE_DESCRIPTION,
        "colors": {"primary": PRIMARY, "light": COLOR_LIGHT, "dark": COLOR_DARK},
        "favicon": f"/{FAVICON}",
        "logo": {"light": f"/{NAV_LOGO_LIGHT}", "dark": f"/{NAV_LOGO_DARK}"},
        "seo": {"metatags": {"og:image": f"/{SOCIAL_PREVIEW}"}},
        "navigation": navigation,
        "navbar": {"links": [{"label": "GitHub", "href": GH_REPO}]},
        "footer": {"socials": {"github": GH_REPO}},
    }


# --- driver -----------------------------------------------------------------------


def build(out: Path) -> dict[str, int]:
    """Build the whole site into `out`. Raises :class:`BuildError` on any problem."""
    sources, navigation = plan()
    nav_routes = _routes_in_nav(navigation)

    # nav and the source table must describe exactly the same set of pages.
    if set(nav_routes) != set(sources):
        missing = set(sources) - set(nav_routes)
        extra = set(nav_routes) - set(sources)
        raise BuildError(
            f"navigation/pages mismatch (missing={missing}, extra={extra})"
        )

    route_map = {src: route for route, src in sources.items() if src}
    routes = set(sources)
    errors: list[str] = []
    site_links: set[str] = set()

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    for route, source in sources.items():
        page = build_page(route, source, route_map, routes, errors, site_links)
        dest = out / f"{route}.mdx"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page, encoding="utf-8")
        # Local MDX sanity — surface obvious breakage without a Node/Mintlify
        # toolchain. The authoritative gate is `mint validate` in CI.
        for hazard in mdx_hazards(page):
            errors.append(f"{route}.mdx:{hazard}")

    # Every intra-site link must resolve to a real page.
    for link in sorted(site_links):
        if link.lstrip("/") not in routes:
            errors.append(f"intra-site link {link!r} resolves to no page")

    # Copy the brand assets into the site root (favicon, logo lockups, social).
    for name in SITE_ASSETS:
        asset_src = REPO_ROOT / "assets" / name
        if not asset_src.is_file():
            raise BuildError(f"missing asset {asset_src}")
        shutil.copy2(asset_src, out / name)

    # Emit and re-parse docs.json to guarantee validity.
    docs_json = build_docs_json(navigation)
    docs_text = json.dumps(docs_json, indent=2) + "\n"
    json.loads(docs_text)
    (out / "docs.json").write_text(docs_text, encoding="utf-8")

    if errors:
        raise BuildError(
            "build failed with "
            f"{len(errors)} link error(s):\n  - " + "\n  - ".join(sorted(errors))
        )

    nav_groups = navigation["groups"]
    assert isinstance(nav_groups, list), (
        f"expected navigation['groups'] to be a list, got {nav_groups!r}"
    )
    return {
        "pages": len(sources),
        "groups": len(nav_groups),
        "site_links": len(site_links),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Build the honest-scholar docs site.")
    parser.add_argument(
        "--out", required=True, type=Path, help="Output directory for the site."
    )
    args = parser.parse_args(argv)

    try:
        stats = build(args.out.resolve())
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"built honest-scholar docs site → {args.out}")
    print(
        f"  {stats['pages']} pages across {stats['groups']} top-level nav groups; "
        f"{stats['site_links']} intra-site links verified; docs.json valid; "
        f"{len(SITE_ASSETS)} brand assets copied."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
