"""The repo-wide checker (#121)."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

import pytest

from defendable_science.check import checks as c
from defendable_science.check import model as m
from defendable_science.check.probe import FsProbe
from defendable_science.scaffold import render as r
from defendable_science.scaffold import status as st
from defendable_science.scaffold.layout import Layout


def _finding(severity: str) -> m.Finding:
    return m.Finding(
        severity=severity,  # type: ignore[arg-type]
        check="tables",
        file="docs/research/papers.md",
        message="something is wrong",
        remedy="run `defendable-science init`",
    )


def test_a_clean_report_is_ok_and_exits_zero() -> None:
    report = m.Report(findings=[])

    assert report.ok is True
    assert report.exit_code == 0
    assert report.counts == {"invalid": 0, "unreadable": 0, "gap": 0}


def test_gaps_alone_do_not_fail_the_run() -> None:
    report = m.Report(findings=[_finding("gap")])

    assert report.ok is True
    assert report.exit_code == 0
    assert report.counts["gap"] == 1


@pytest.mark.parametrize("severity", ["invalid", "unreadable"])
def test_invalid_and_unreadable_both_fail_the_run(severity: str) -> None:
    report = m.Report(findings=[_finding(severity)])

    assert report.ok is False
    assert report.exit_code == 1


def test_to_json_is_shaped_like_the_other_commands() -> None:
    payload = m.Report(findings=[_finding("invalid")]).to_json()

    assert payload["ok"] is False
    assert payload["counts"]["invalid"] == 1
    assert payload["findings"] == [
        {
            "severity": "invalid",
            "check": "tables",
            "file": "docs/research/papers.md",
            "message": "something is wrong",
            "remedy": "run `defendable-science init`",
        }
    ]


def test_fs_probe_reads_globs_and_reports_existence(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.md").write_text("hello", encoding="utf-8")
    probe = FsProbe()

    assert probe.exists(tmp_path / "a" / "x.md") is True
    assert probe.exists(tmp_path / "a" / "nope.md") is False
    assert probe.read_text(tmp_path / "a" / "x.md") == "hello"
    assert probe.glob(tmp_path, "**/*.md") == [tmp_path / "a" / "x.md"]


def test_fs_probe_globs_nothing_under_a_missing_root(tmp_path: Path) -> None:
    assert FsProbe().glob(tmp_path / "absent", "**/*.md") == []


def test_fs_probe_read_text_raises_oserror_for_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(OSError, match=r"absent\.md"):
        FsProbe().read_text(tmp_path / "absent.md")


def test_fs_probe_read_text_raises_oserror_for_a_binary_file(tmp_path: Path) -> None:
    # `UnicodeDecodeError` subclasses `ValueError`, not `OSError`, so it would
    # sail past every `except OSError:` in the checks and surface as a raw
    # traceback. `FsProbe` re-raises it so each check has one error branch.
    binary = tmp_path / "binary.md"
    binary.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(OSError, match="is not valid UTF-8"):
        FsProbe().read_text(binary)


# --- the layout and table check families (#121) ------------------------------


def _matches(parts: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    """Match path segments against glob segments, ``**`` spanning any depth.

    Segment-wise on purpose: a bare `fnmatch` lets ``*`` cross ``/``, so
    ``hypotheses/*/hypothesis.md`` would match at any depth and a fake built on
    it would report matches `pathlib.Path.glob` never returns.
    """
    if not pattern:
        return not parts
    if pattern[0] == "**":
        return any(_matches(parts[i:], pattern[1:]) for i in range(len(parts) + 1))
    return (
        bool(parts)
        and fnmatch(parts[0], pattern[0])
        and _matches(parts[1:], pattern[1:])
    )


class FakeProbe:
    """A filesystem built from a ``{path: text}`` map. Directories are implied."""

    def __init__(self, files: dict[Path, str], unreadable: set[Path] | None = None):
        self.files = files
        self.unreadable = unreadable or set()

    def exists(self, path: Path) -> bool:
        return path in self.files or any(path in p.parents for p in self.files)

    def read_text(self, path: Path) -> str:
        if path in self.unreadable:
            raise OSError(f"{path}: simulated read failure")
        if path not in self.files:
            raise OSError(f"{path}: no such file")
        return self.files[path]

    def glob(self, root: Path, pattern: str) -> list[Path]:
        """Match `pattern` against each file's path relative to `root`.

        Files only — the map holds no directory entries — so a pattern meant to
        select directories (``**/*``) will not match them. Every check globs for
        files, which is what `test_the_fake_probe_models_the_real_one` pins.
        """
        pat = tuple(pattern.split("/"))
        return sorted(
            p
            for p in self.files
            if root in p.parents and _matches(p.relative_to(root).parts, pat)
        )


ROOT = Path("/repo")
LAYOUT = Layout.default(ROOT)


def _scaffolded() -> dict[Path, str]:
    """Return the file map a clean `init` produces (the regression baseline)."""
    return {
        LAYOUT.papers_registry: r.render_papers_registry(),
        LAYOUT.portfolio_backlog: r.render_portfolio_backlog(),
        LAYOUT.dashboard: r.render_dashboard(),
        LAYOUT.references: r.render_references(),
        LAYOUT.triage: r.render_triage(),
        LAYOUT.datasets_manifest: r.render_datasets_manifest(),
        LAYOUT.config_file: r.render_config(),
        ROOT / ".gitignore": "\n".join(r.gitignore_entries(r.DEFAULT_CACHE_DIR)) + "\n",
    }


def _registry(*rows: str) -> str:
    return "| paper-id | root | backend |\n|---|---|---|\n" + "".join(rows)


def test_the_fake_probe_models_the_real_one(tmp_path: Path) -> None:
    """The fake is the seam every later check family is tested through."""
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "x.md").write_text("hi", encoding="utf-8")
    (tmp_path / "a" / "y.txt").write_text("no", encoding="utf-8")
    fake = FakeProbe(
        {tmp_path / "a" / "b" / "x.md": "hi", tmp_path / "a" / "y.txt": "no"}
    )
    real = FsProbe()

    for pattern in ("**/*.md", "*.md", "*.txt", "a/*/x.md", "a/**/*.md", "a/*.txt"):
        assert fake.glob(tmp_path, pattern) == real.glob(tmp_path, pattern), pattern
    # An implied directory exists, as it does on a real filesystem.
    assert fake.exists(tmp_path / "a") == real.exists(tmp_path / "a") is True
    assert fake.exists(tmp_path / "zz") == real.exists(tmp_path / "zz") is False
    assert fake.glob(tmp_path / "zz", "**/*.md") == real.glob(
        tmp_path / "zz", "**/*.md"
    )


def test_layout_check_is_silent_on_a_scaffolded_repo() -> None:
    assert c.check_layout(LAYOUT, FakeProbe(_scaffolded())) == []


def test_layout_check_names_each_missing_required_file() -> None:
    files = _scaffolded()
    del files[LAYOUT.papers_registry]

    findings = c.check_layout(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert findings[0].file == "docs/research/papers.md"
    assert "defendable-science init" in findings[0].remedy


def test_layout_check_does_not_require_a_thesis_tree() -> None:
    """Thesis-ness is a fact on disk; a portfolio repo is complete without one."""
    files = _scaffolded()
    del files[LAYOUT.papers_registry]  # one real finding, so the test is not vacuous

    findings = c.check_layout(LAYOUT, FakeProbe(files))

    assert [f.file for f in findings] == ["docs/research/papers.md"]
    assert not any("thesis" in f.file for f in findings)


def test_layout_check_requires_aims_once_a_thesis_dir_exists() -> None:
    files = _scaffolded()
    files[LAYOUT.thesis_dir / "kappa" / "kappa.md"] = (
        "---\nstatus:\n  level: thesis\n---\n"
    )

    findings = c.check_layout(LAYOUT, FakeProbe(files))

    assert any(f.file == "docs/research/thesis/aims.md" for f in findings)
    assert any(f.file == "docs/research/thesis/milestones.yml" for f in findings)
    assert all("--thesis" in f.remedy for f in findings)


def test_tables_check_is_silent_on_a_scaffolded_repo() -> None:
    assert c.check_tables(LAYOUT, FakeProbe(_scaffolded())) == []


def test_tables_check_flags_the_header_that_broke_park() -> None:
    """The exact malformed header quoted in #120 and #121."""
    files = _scaffolded()
    files[LAYOUT.portfolio_backlog] = (
        "| id | status | idea | rationale | ranked | promoted-to |\n"
        "|---|---|---|---|---|---|\n"
    )

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "one-line" in findings[0].message
    assert "provenance" in findings[0].message
    assert findings[0].file == "docs/research/portfolio-backlog.md"
    assert "one-line" in findings[0].remedy


def test_tables_check_is_silent_about_an_extra_registry_column() -> None:
    """A column beyond the profile is the author's own extension point.

    ``append_papers_registry`` writes rows into a wider header and preserves the
    extra cells rather than dropping them, so flagging one would have `check`
    nag about documented behaviour.
    """
    files = _scaffolded()
    files[LAYOUT.papers_registry] = (
        "| paper-id | root | backend | notes |\n|---|---|---|---|\n"
        "| dc | docs/research/dc | bench | ours |\n"
    )
    files[LAYOUT.paper_dir("dc") / "backlog.md"] = r.render_paper_backlog()

    assert c.check_tables(LAYOUT, FakeProbe(files)) == []


def test_tables_check_flags_a_missing_registry_column() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = "| paper-id | root |\n|---|---|\n"

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert any("backend" in f.message and f.severity == "invalid" for f in findings)


def test_a_missing_backend_column_is_not_reported_once_per_row() -> None:
    """The header defect is the finding; the rows are not each a second one."""
    files = _scaffolded()
    files[LAYOUT.papers_registry] = (
        "| paper-id | root |\n|---|---|\n| dc | docs/research/dc |\n"
    )
    files[LAYOUT.paper_dir("dc") / "backlog.md"] = r.render_paper_backlog()

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "backend" in findings[0].message
    assert not any(f.severity == "gap" for f in findings)


def test_tables_check_flags_a_registry_root_outside_the_repository() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = _registry("| dc | ../outside/dc | bench |\n")

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "outside the repository" in findings[0].message
    assert "docs/research/dc" in findings[0].remedy


def test_tables_check_flags_an_absolute_registry_root() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = _registry("| dc | /etc | bench |\n")

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "outside the repository" in findings[0].message


def test_tables_check_flags_a_registry_row_whose_root_is_missing() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = _registry("| dc | docs/research/dc | bench |\n")

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert any(
        "docs/research/dc" in f.message and f.severity == "invalid" for f in findings
    )


def test_tables_check_flags_a_registry_row_with_an_empty_backend() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = _registry("| dc | docs/research/dc |  |\n")
    files[LAYOUT.paper_dir("dc") / "backlog.md"] = r.render_paper_backlog()

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert any("backend" in f.message and "dc" in f.message for f in findings)
    # An unbound backend is incomplete science, not a corrupt file.
    assert [f.severity for f in findings] == ["gap"]


def test_tables_check_flags_a_registry_row_with_no_root() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = _registry("| dc |  | bench |\n")

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "root" in findings[0].message
    assert "dc" in findings[0].message


def test_tables_check_flags_a_registry_row_with_no_paper_id() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = _registry("|  | docs/research/dc | bench |\n")

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "paper-id" in findings[0].message


def test_tables_check_reads_each_registered_papers_backlog() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = _registry("| dc | docs/research/dc | bench |\n")
    files[LAYOUT.paper_dir("dc") / "backlog.md"] = "| id | note |\n|---|---|\n"

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert any(f.file == "docs/research/dc/backlog.md" for f in findings)


def test_tables_check_flags_a_registered_paper_with_no_backlog() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = _registry("| dc | docs/research/dc | bench |\n")
    files[LAYOUT.paper_dir("dc") / "paper" / "pitch.md"] = "# Pitch\n"

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert [f.file for f in findings] == ["docs/research/dc/backlog.md"]
    assert findings[0].severity == "invalid"


def test_tables_check_reports_unreadable_separately_from_empty() -> None:
    files = _scaffolded()
    probe = FakeProbe(files, unreadable={LAYOUT.papers_registry})

    findings = c.check_tables(LAYOUT, probe)

    assert [f.severity for f in findings] == ["unreadable"]
    assert "could not read" in findings[0].message


def test_tables_check_reports_an_unreadable_paper_backlog() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = _registry("| dc | docs/research/dc | bench |\n")
    backlog = LAYOUT.paper_dir("dc") / "backlog.md"
    files[backlog] = r.render_paper_backlog()

    findings = c.check_tables(LAYOUT, FakeProbe(files, unreadable={backlog}))

    assert [f.severity for f in findings] == ["unreadable"]
    assert findings[0].file == "docs/research/dc/backlog.md"
    assert findings[0].remedy


def test_tables_check_flags_a_registry_that_holds_no_table() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = "# Papers registry\n\nNothing here yet.\n"

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "no markdown table" in findings[0].message
    assert "paper-id" in findings[0].remedy


def test_tables_check_surfaces_the_parsers_own_error_for_a_malformed_table() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = (
        "| paper-id | root | backend |\n| dc | docs/research/dc | bench |\n"
    )

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "separator" in findings[0].message


def test_tables_check_leaves_missing_files_to_the_layout_check() -> None:
    """A missing file is reported once, by the family that owns it."""
    files = _scaffolded()
    del files[LAYOUT.papers_registry]
    del files[LAYOUT.portfolio_backlog]

    assert c.check_tables(LAYOUT, FakeProbe(files)) == []
    assert len(c.check_layout(LAYOUT, FakeProbe(files))) == 2


def test_registry_rows_returns_every_registered_paper() -> None:
    files = _scaffolded()
    files[LAYOUT.papers_registry] = _registry(
        "| dc | docs/research/dc | bench |\n| mn | docs/research/mn | bench |\n"
    )

    rows, findings = c.registry_rows(LAYOUT, FakeProbe(files))

    assert [row["paper-id"] for row in rows] == ["dc", "mn"]
    assert findings == []


def test_tables_check_flags_a_backlog_that_holds_no_table() -> None:
    """A backlog with its table deleted is invalid, never a valid empty one."""
    files = _scaffolded()
    files[LAYOUT.portfolio_backlog] = "# Portfolio backlog\n\nNothing parked yet.\n"

    findings = c.check_tables(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "no markdown table" in findings[0].message
    assert "one-line" in findings[0].remedy


# --- frontmatter checks (#121) --------------------------------------------------


def _doc(level: str, **fields: str) -> str:
    return "---\n" + st.render(level, fields) + "---\n\n# Doc\n"


PITCH = LAYOUT.paper_docs_dir("dc") / "pitch.md"


def test_frontmatter_check_is_silent_on_a_valid_document() -> None:
    files = _scaffolded()
    files[PITCH] = _doc("paper", id="dc", **{"last-updated": "2026-03-04"})

    assert c.check_frontmatter(LAYOUT, FakeProbe(files)) == []


def test_frontmatter_check_flags_a_missing_status_block() -> None:
    files = _scaffolded()
    files[PITCH] = "# Pitch\n\nno frontmatter\n"

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "status:" in findings[0].message
    assert findings[0].file == "docs/research/dc/paper/pitch.md"


def test_frontmatter_check_flags_an_out_of_enum_verdict() -> None:
    files = _scaffolded()
    files[PITCH] = _doc("paper", id="dc", verdict="maybe")

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    # Exactly one finding for the invalid verdict value
    assert len(findings) == 1
    assert findings[0].severity == "invalid"
    assert "verdict" in findings[0].message
    assert "maybe" in findings[0].message


def test_frontmatter_check_flags_an_out_of_enum_readiness() -> None:
    files = _scaffolded()
    files[PITCH] = _doc("paper", id="dc", readiness="nearly")

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    # Exactly one finding for the invalid readiness value
    assert len(findings) == 1
    assert findings[0].severity == "invalid"
    assert "readiness" in findings[0].message
    assert "nearly" in findings[0].message


def test_frontmatter_check_flags_an_unreplaced_placeholder() -> None:
    """`readiness: <synthesis | defensible>` parses as a real value (#121).

    A placeholder in a field produces exactly one finding (the placeholder finding),
    not a second enum finding. This prevents duplicate remedies for a single defect.
    """
    files = _scaffolded()
    kappa = LAYOUT.kappa_dir / "kappa.md"
    files[kappa] = (
        "---\nstatus:\n  level: thesis\n  id: t\n"
        "  readiness: <synthesis | defensible>\n---\n\n# Kappa\n"
    )

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    # Exactly one finding: the placeholder finding, not a second readiness-enum finding
    assert len(findings) == 1
    assert findings[0].severity == "invalid"
    assert "placeholder" in findings[0].message
    assert "readiness" in findings[0].message
    assert "null" in findings[0].remedy


def test_frontmatter_check_flags_a_placeholder_in_verdict() -> None:
    """A placeholder in verdict yields one finding, not a second enum finding."""
    files = _scaffolded()
    findings_path = LAYOUT.hypothesis_dir("dc", "2026-03-04-h") / "findings.md"
    files[findings_path] = (
        "---\nstatus:\n  level: hypothesis\n  id: 2026-03-04-h\n"
        "  verdict: <confirmed | refuted>\n  readiness: resolved\n---\n\n# H\n"
    )

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    # Exactly one finding: the placeholder, not a second verdict-enum finding
    assert len(findings) == 1
    assert findings[0].severity == "invalid"
    assert "placeholder" in findings[0].message
    assert "verdict" in findings[0].message
    assert "null" in findings[0].remedy


def test_frontmatter_check_flags_a_placeholder_in_level() -> None:
    """A placeholder in level yields one finding, not a second level-mismatch finding."""
    files = _scaffolded()
    files[PITCH] = "---\nstatus:\n  level: <paper | hypothesis>\n  id: dc\n---\n\n# P\n"

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    # Exactly one finding: the placeholder, not a second level-mismatch finding
    assert len(findings) == 1
    assert findings[0].severity == "invalid"
    assert "placeholder" in findings[0].message
    assert "level" in findings[0].message
    assert "null" in findings[0].remedy


def test_frontmatter_check_flags_a_level_that_contradicts_the_filename() -> None:
    files = _scaffolded()
    files[PITCH] = _doc("hypothesis", id="dc", verdict="null", readiness="null")

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    # Exactly one finding for the level mismatch (not additional enum findings)
    assert len(findings) == 1
    assert findings[0].severity == "invalid"
    assert "level" in findings[0].message


def test_frontmatter_check_flags_an_unknown_status_field() -> None:
    files = _scaffolded()
    files[PITCH] = "---\nstatus:\n  level: paper\n  priority: high\n---\n"

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    # Exactly one finding for the unknown field
    assert len(findings) == 1
    assert findings[0].severity == "invalid"
    assert "priority" in findings[0].message


def test_frontmatter_check_reports_invalid_yaml_without_a_traceback() -> None:
    files = _scaffolded()
    files[PITCH] = "---\nstatus: [unclosed\n---\n"

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "invalid YAML" in findings[0].message


def test_frontmatter_check_reports_an_unreadable_document() -> None:
    files = _scaffolded()
    files[PITCH] = _doc("paper", id="dc")
    probe = FakeProbe(files, unreadable={PITCH})

    findings = c.check_frontmatter(LAYOUT, probe)

    assert [f.severity for f in findings] == ["unreadable"]


def test_frontmatter_check_ignores_a_file_that_is_not_a_staged_document() -> None:
    files = _scaffolded()
    files[LAYOUT.paper_dir("dc") / "notes.md"] = "# scratch notes, no frontmatter\n"

    assert c.check_frontmatter(LAYOUT, FakeProbe(files)) == []


def test_frontmatter_check_never_flags_a_refuted_hypothesis() -> None:
    """`refuted` is successful science, not a failure (meta-spec §2.1)."""
    files = _scaffolded()
    findings_path = LAYOUT.hypothesis_dir("dc", "2026-03-04-x") / "findings.md"
    files[findings_path] = _doc(
        "hypothesis",
        id="2026-03-04-x",
        verdict="refuted",
        readiness="resolved",
        **{"signed-off-by": "D. Runje", "signed-off-date": "2026-03-04"},
    )

    assert c.check_frontmatter(LAYOUT, FakeProbe(files)) == []


def test_frontmatter_check_accepts_a_freshly_rendered_document() -> None:
    """A document rendered fresh from status.render passes cleanly.

    This tests the critical behavior: VERDICTS and READINESS enums contain no
    member for the unset state, but the renderer emits `null`. A validator
    written as `value in VERDICTS[level]` would reject the renderer's own
    output. The validator must special-case `None` as a valid unset state.
    """
    files = _scaffolded()

    # Create a freshly rendered paper pitch (has no verdict, unset readiness)
    pitch_path = LAYOUT.paper_docs_dir("dc") / "pitch.md"
    files[pitch_path] = _doc("paper", id="dc")

    # Create a freshly rendered hypothesis (has pending verdict and readiness)
    hypothesis_path = LAYOUT.hypothesis_dir("dc", "2026-03-04-h") / "hypothesis.md"
    files[hypothesis_path] = _doc("hypothesis", id="2026-03-04-h")

    # Create a freshly rendered thesis (has n/a verdict, unset readiness)
    kappa_path = LAYOUT.kappa_dir / "kappa.md"
    files[kappa_path] = _doc("thesis")

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    # All three should pass cleanly; no findings about the unset/null fields
    assert findings == []


def test_staged_documents_globs_research_root() -> None:
    """staged_documents finds all markdown files in research_root with STAGED_DOCUMENTS names."""
    files = _scaffolded()
    pitch_path = LAYOUT.paper_docs_dir("dc") / "pitch.md"
    hypothesis_path = LAYOUT.hypothesis_dir("dc", "2026-03-04-h") / "hypothesis.md"
    files[pitch_path] = _doc("paper", id="dc")
    files[hypothesis_path] = _doc("hypothesis", id="2026-03-04-h")

    docs = c.staged_documents(LAYOUT, FakeProbe(files))

    assert pitch_path in docs
    assert hypothesis_path in docs
    # Should not include other markdown files
    notes_path = LAYOUT.paper_dir("dc") / "notes.md"
    files[notes_path] = "# Notes\n"
    docs = c.staged_documents(LAYOUT, FakeProbe(files))
    assert notes_path not in docs


def test_staged_documents_handles_external_thesis_dir() -> None:
    """If thesis_dir is outside research_root, it is also globbed."""
    from defendable_science.scaffold.layout import Layout

    external_thesis = Path("/other/thesis")
    layout_ext = Layout(
        repo_root=LAYOUT.repo_root,
        research_root=LAYOUT.research_root,
        literature_dir=LAYOUT.literature_dir,
        datasets_manifest=LAYOUT.datasets_manifest,
        thesis_dir=external_thesis,
    )

    files = {}
    files[LAYOUT.paper_docs_dir("dc") / "pitch.md"] = _doc("paper", id="dc")
    files[external_thesis / "kappa" / "kappa.md"] = _doc("thesis")
    # Multiple thesis documents to ensure loop iteration is tested
    files[external_thesis / "kappa" / "aims.md"] = _doc("thesis")

    docs = c.staged_documents(layout_ext, FakeProbe(files))

    assert LAYOUT.paper_docs_dir("dc") / "pitch.md" in docs
    assert external_thesis / "kappa" / "kappa.md" in docs
    assert external_thesis / "kappa" / "aims.md" in docs
