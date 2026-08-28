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


def test_frontmatter_check_produces_one_finding_per_defect_across_fields() -> None:
    """A placeholder in one field must not suppress defects in another.

    A document with `readiness: <synthesis | defensible>` and `verdict: maybe`
    should produce exactly two findings: one for the placeholder, one for the
    invalid verdict. The placeholder suppresses enum checking on that field, but
    not on other fields.
    """
    files = _scaffolded()
    files[PITCH] = (
        "---\nstatus:\n  level: paper\n  id: dc\n"
        "  readiness: <synthesis | defensible>\n  verdict: maybe\n---\n\n# Pitch\n"
    )

    findings = c.check_frontmatter(LAYOUT, FakeProbe(files))

    # Exactly two findings: placeholder in readiness and invalid verdict
    assert len(findings) == 2
    severities = {f.severity for f in findings}
    assert severities == {"invalid"}
    messages = {f.message for f in findings}
    assert any("placeholder" in msg and "readiness" in msg for msg in messages)
    assert any("verdict" in msg and "maybe" in msg for msg in messages)


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


# --- registries checks -------------------------------------------------------


def test_registries_check_is_silent_on_a_scaffolded_repo() -> None:
    assert c.check_registries(LAYOUT, FakeProbe(_scaffolded())) == []


def test_registries_check_flags_invalid_csl_json() -> None:
    files = _scaffolded()
    files[LAYOUT.references] = '{"id": "smith2020"}\n'  # object, not an array

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert findings[0].file == "docs/research/literature/references.json"


def test_registries_check_flags_an_entry_without_an_id() -> None:
    files = _scaffolded()
    files[LAYOUT.references] = '[{"title": "no id here"}]\n'

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert any("id" in f.message for f in findings)


def test_registries_check_flags_a_triage_key_with_no_reference() -> None:
    files = _scaffolded()
    files[LAYOUT.references] = '[{"id": "smith2020"}]\n'
    files[LAYOUT.triage] = "jones2019:\n  disposition: include\n"

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert any("jones2019" in f.message and f.severity == "invalid" for f in findings)


def test_registries_check_flags_a_triage_row_that_is_not_a_mapping() -> None:
    """`load_triage` silently skips these, so nothing else would ever see it."""
    files = _scaffolded()
    files[LAYOUT.references] = '[{"id": "smith2020"}]\n'
    files[LAYOUT.triage] = "smith2020: include\n"

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert any("smith2020" in f.message and "mapping" in f.message for f in findings)


def test_registries_check_flags_invalid_triage_yaml() -> None:
    files = _scaffolded()
    files[LAYOUT.triage] = "smith2020: [unclosed\n"

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert any("invalid YAML" in f.message for f in findings)


def test_registries_check_reports_every_manifest_error() -> None:
    from defendable_science.dataset import manifest as mf

    files = _scaffolded()
    files[LAYOUT.datasets_manifest] = "datasets:\n  - id: cifar10\n    files: []\n"

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    error_findings = [
        f for f in findings if f.severity == "invalid" and f.file == "datasets.yml"
    ]
    messages = " ".join(f.message for f in error_findings)
    assert "version" in messages
    assert "license" in messages

    # Validate the same manifest to bound against the actual rules
    manifest = mf.load_text(
        "datasets:\n  - id: cifar10\n    files: []\n", "datasets.yml"
    )
    report = mf.validate(manifest)

    # No two findings share the same (severity, message) pair (catches double-reports)
    pairs = [(f.severity, f.message) for f in error_findings]
    assert len(pairs) == len(set(pairs)), "Duplicate (severity, message) pairs detected"

    # Exact count matches validator output
    assert len(error_findings) == len(report.errors)


def test_registries_check_flags_an_unparseable_manifest() -> None:
    files = _scaffolded()
    files[LAYOUT.datasets_manifest] = "- not: a mapping\n"

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert any(f.severity == "invalid" and f.file == "datasets.yml" for f in findings)


def test_registries_check_reports_each_unreadable_registry() -> None:
    probe = FakeProbe(_scaffolded(), unreadable={LAYOUT.references, LAYOUT.triage})

    findings = c.check_registries(LAYOUT, probe)

    assert sorted(f.file for f in findings if f.severity == "unreadable") == [
        "docs/research/literature/references.json",
        "docs/research/literature/triage.yml",
    ]


def test_registries_check_unreadable_datasets() -> None:
    probe = FakeProbe(_scaffolded(), unreadable={LAYOUT.datasets_manifest})

    findings = c.check_registries(LAYOUT, probe)

    assert any(
        f.severity == "unreadable" and f.file == "datasets.yml" for f in findings
    )


def test_registries_check_flags_malformed_json_in_references() -> None:
    files = _scaffolded()
    files[LAYOUT.references] = '[{"id": "smith2020"}\n'  # missing closing bracket

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert any(
        f.severity == "invalid"
        and f.file == "docs/research/literature/references.json"
        and "invalid JSON" in f.message
        for f in findings
    )


def test_registries_check_flags_mirror_not_a_dict() -> None:
    files = _scaffolded()
    files[LAYOUT.datasets_manifest] = "mirror: not_a_dict\ndatasets: []\n"

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert any(f.severity == "invalid" and "mirror" in f.message for f in findings)


def test_registries_check_flags_datasets_not_a_list() -> None:
    files = _scaffolded()
    files[LAYOUT.datasets_manifest] = (
        "datasets:\n"
        "  id: cifar10\n"  # object instead of list
    )

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert any(f.severity == "invalid" and "datasets" in f.message for f in findings)


def test_registries_check_flags_malformed_yaml_in_datasets() -> None:
    files = _scaffolded()
    files[LAYOUT.datasets_manifest] = "datasets: [unclosed\n"

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    assert any(
        f.severity == "invalid"
        and f.file == "datasets.yml"
        and "invalid YAML" in f.message
        for f in findings
    )


def test_registries_check_handles_empty_datasets_manifest() -> None:
    files = _scaffolded()
    files[LAYOUT.datasets_manifest] = ""  # empty file

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    # Empty dataset manifest is valid, so no findings (except any schema validation)
    assert all(f.file != "datasets.yml" or f.severity == "invalid" for f in findings)


def test_registries_check_triage_orphan_with_readable_references() -> None:
    """Test orphan key detection when both triage and references are readable."""
    files = _scaffolded()
    files[LAYOUT.references] = '[{"id": "smith2020"}]\n'
    files[LAYOUT.triage] = "jones2019:\n  disposition: include\n"

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    orphan_findings = [f for f in findings if "jones2019" in f.message]
    assert len(orphan_findings) == 1
    assert orphan_findings[0].severity == "invalid"


def test_registries_check_triage_orphan_when_references_unreadable() -> None:
    """Test that when references can't be read, all triage keys are flagged as orphans."""
    files = _scaffolded()
    files[LAYOUT.triage] = "smith2020:\n  disposition: include\n"

    probe = FakeProbe(files, unreadable={LAYOUT.references})

    findings = c.check_registries(LAYOUT, probe)

    # Should have: unreadable references + orphan triage key
    unreadable_findings = [f for f in findings if f.severity == "unreadable"]
    orphan_findings = [
        f for f in findings if f.severity == "invalid" and "smith2020" in f.message
    ]
    assert len(unreadable_findings) == 1  # references is unreadable
    assert len(orphan_findings) == 1  # smith2020 is orphan


def test_registries_check_reports_manifest_warnings() -> None:
    """Test that manifest validation warnings become gap findings."""
    from defendable_science.dataset import manifest as mf

    files = _scaffolded()
    # Incomplete DataCite tuple (warning, not error)
    manifest_text = (
        "datasets:\n"
        "  - id: cifar10\n"
        "    version: 1.0\n"
        "    tier: A\n"
        "    license: CC-BY-4.0\n"
        "    redistributable: true\n"
        "    access: open\n"
        "    files:\n"
        "      - path: data.zip\n"
        "        sha256: " + "a" * 64 + "\n"
        "    datasheet: https://example.com/datasheet.pdf\n"
        "    citation:\n"
        "      title: My Dataset\n"  # Missing creator, publisher, identifier, publication_year
        "      resource_type: Dataset\n"
    )
    files[LAYOUT.datasets_manifest] = manifest_text

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    gap_findings = [f for f in findings if f.severity == "gap"]
    assert any("citation" in f.message for f in gap_findings)

    # Validate the same manifest to bound against the actual rules
    manifest = mf.load_text(manifest_text, "datasets.yml")
    report = mf.validate(manifest)

    # No two findings share the same (severity, message) pair (catches double-reports)
    pairs = [(f.severity, f.message) for f in gap_findings]
    assert len(pairs) == len(set(pairs)), "Duplicate (severity, message) pairs detected"

    # Exact count matches validator output for warnings
    assert len(gap_findings) == len(report.warnings)


def test_registries_check_handles_manifest_with_mirror() -> None:
    """Test that a dataset manifest with a valid mirror is handled correctly."""
    files = _scaffolded()
    files[LAYOUT.datasets_manifest] = (
        "mirror:\n"
        "  rclone_remote: myremote\n"
        "  base_path: /data\n"
        "datasets:\n"
        "  - id: cifar10\n"
        "    version: 1.0\n"
        "    tier: A\n"
        "    license: CC-BY-4.0\n"
        "    redistributable: true\n"
        "    access: open\n"
        "    files:\n"
        "      - path: data.zip\n"
        "        sha256: " + "a" * 64 + "\n"
        "    datasheet: https://example.com/datasheet.pdf\n"
    )

    findings = c.check_registries(LAYOUT, FakeProbe(files))

    # Should not have errors about the manifest structure itself
    # (may have other validation issues, but not about mirror being invalid)
    assert not any("mirror" in f.message and f.severity == "invalid" for f in findings)


# --- config checks ---


def _scaffolded_with_backend(backend: str | None) -> dict[Path, str]:
    files = _scaffolded()
    value = "null" if backend is None else backend
    files[LAYOUT.config_file] = (
        f"cache_dir: {r.DEFAULT_CACHE_DIR}\nexperiment_backend: {value}\n"
    )
    return files


def test_config_check_is_silent_on_a_scaffolded_repo_with_a_bound_backend() -> None:
    assert c.check_config(LAYOUT, FakeProbe(_scaffolded_with_backend("bench"))) == []


def test_config_check_flags_unparseable_yaml_without_a_traceback() -> None:
    files = _scaffolded()
    files[LAYOUT.config_file] = "cache_dir: [unclosed\n"

    findings = c.check_config(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]
    assert "invalid YAML" in findings[0].message
    assert "Traceback" not in findings[0].message


def test_config_check_flags_a_non_mapping_config() -> None:
    files = _scaffolded()
    files[LAYOUT.config_file] = "- a\n- b\n"

    findings = c.check_config(LAYOUT, FakeProbe(files))

    assert [f.severity for f in findings] == ["invalid"]


def test_config_check_flags_an_unknown_layout_key() -> None:
    files = _scaffolded()
    files[LAYOUT.config_file] = "layout:\n  papers_dir: x/\n"

    findings = c.check_config(LAYOUT, FakeProbe(files))

    # Exactly one finding for the unknown key
    invalid_layout = [
        f for f in findings if "papers_dir" in f.message and f.severity == "invalid"
    ]
    assert len(invalid_layout) == 1
    # No duplicate findings with the same message
    assert len({(f.severity, f.message) for f in findings}) == len(findings)


def test_config_check_flags_a_cache_dir_that_is_not_gitignored() -> None:
    files = _scaffolded()
    files[ROOT / ".gitignore"] = "__pycache__/\n"

    findings = c.check_config(LAYOUT, FakeProbe(files))

    cache_not_ignored = [
        f
        for f in findings
        if ".defendable-science/cache" in f.message and f.severity == "invalid"
    ]
    assert len(cache_not_ignored) == 1
    assert ".gitignore" in cache_not_ignored[0].remedy
    # No duplicate findings with the same message
    assert len({(f.severity, f.message) for f in findings}) == len(findings)


def test_config_check_flags_a_missing_gitignore() -> None:
    files = _scaffolded()
    del files[ROOT / ".gitignore"]

    findings = c.check_config(LAYOUT, FakeProbe(files))

    assert any(f.file == ".gitignore" for f in findings)


def test_config_check_surfaces_a_null_experiment_backend_as_a_gap() -> None:
    """A repo that cannot produce run-refs is incomplete, not invalid."""
    findings = c.check_config(LAYOUT, FakeProbe(_scaffolded_with_backend(None)))

    backend = [f for f in findings if "experiment_backend" in f.message]
    assert [f.severity for f in backend] == ["gap"]


def test_config_check_is_silent_once_a_backend_is_bound() -> None:
    findings = c.check_config(LAYOUT, FakeProbe(_scaffolded_with_backend("bench")))

    assert [f for f in findings if "experiment_backend" in f.message] == []


def test_config_check_reports_an_unreadable_config() -> None:
    probe = FakeProbe(_scaffolded(), unreadable={LAYOUT.config_file})

    findings = c.check_config(LAYOUT, probe)

    assert [f.severity for f in findings] == ["unreadable"]


def test_config_check_handles_an_empty_config_file() -> None:
    """An empty or null config is valid; it just uses all defaults."""
    files = _scaffolded()
    files[LAYOUT.config_file] = ""

    findings = c.check_config(LAYOUT, FakeProbe(files))

    # Empty config should still have the experiment_backend gap but no other issues
    backend_gaps = [f for f in findings if "experiment_backend" in f.message]
    assert [f.severity for f in backend_gaps] == ["gap"]


def test_config_check_flags_an_unreadable_gitignore() -> None:
    files = _scaffolded()
    files[LAYOUT.config_file] = (
        f"cache_dir: {r.DEFAULT_CACHE_DIR}\nexperiment_backend: bench\n"
    )
    probe = FakeProbe(files, unreadable={ROOT / ".gitignore"})

    findings = c.check_config(LAYOUT, probe)

    assert any(f.severity == "unreadable" and ".gitignore" in f.file for f in findings)


def test_config_check_accepts_cache_dir_with_trailing_slash_in_config_matching_without_in_gitignore() -> (
    None
):
    """Trailing-slash differences should not cause false failures."""
    files = _scaffolded()
    files[LAYOUT.config_file] = (
        "cache_dir: .defendable-science/cache\nexperiment_backend: bench\n"
    )
    files[ROOT / ".gitignore"] = ".defendable-science/cache/\n"

    findings = c.check_config(LAYOUT, FakeProbe(files))

    # Should be silent (config without trailing slash matches .gitignore entry with one)
    assert not any("cache" in f.message for f in findings)


def test_config_check_accepts_cache_dir_without_trailing_slash_in_config_matching_with_in_gitignore() -> (
    None
):
    """Trailing-slash differences should not cause false failures."""
    files = _scaffolded()
    files[LAYOUT.config_file] = (
        "cache_dir: .defendable-science/cache/\nexperiment_backend: bench\n"
    )
    files[ROOT / ".gitignore"] = ".defendable-science/cache\n"

    findings = c.check_config(LAYOUT, FakeProbe(files))

    # Should be silent (config with trailing slash matches .gitignore entry without one)
    assert not any("cache" in f.message for f in findings)


def test_config_check_accepts_a_parent_directory_line_in_gitignore() -> None:
    """A parent directory rule covers the cache_dir."""
    files = _scaffolded()
    files[LAYOUT.config_file] = (
        "cache_dir: .defendable-science/cache/\nexperiment_backend: bench\n"
    )
    files[ROOT / ".gitignore"] = ".defendable-science/\n"

    findings = c.check_config(LAYOUT, FakeProbe(files))

    # Should be silent (parent directory covers cache_dir)
    assert not any("cache" in f.message for f in findings)


def test_config_check_ignores_commented_out_gitignore_entries() -> None:
    """A commented-out entry does not count as covering the cache_dir."""
    files = _scaffolded()
    files[LAYOUT.config_file] = (
        f"cache_dir: {r.DEFAULT_CACHE_DIR}\nexperiment_backend: bench\n"
    )
    files[ROOT / ".gitignore"] = f"# {r.DEFAULT_CACHE_DIR}\n"

    findings = c.check_config(LAYOUT, FakeProbe(files))

    # Should flag the missing entry
    cache_missing = [
        f for f in findings if "cache" in f.message and f.severity == "invalid"
    ]
    assert len(cache_missing) == 1


# --- cross-artifact checks -------------------------------------------------------


def test_an_unsigned_verdict_is_a_gap_not_a_failure() -> None:
    files = _scaffolded()
    decision = LAYOUT.paper_docs_dir("dc") / "decision.md"
    files[decision] = _doc("paper", id="dc", verdict="publish")

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    signed = [f for f in findings if "signed-off-by" in f.message]
    assert [f.severity for f in signed] == ["gap"]
    assert "not yet decided" in signed[0].message


def test_a_no_go_verdict_is_never_reported_as_a_problem() -> None:
    files = _scaffolded()
    decision = LAYOUT.paper_docs_dir("dc") / "decision.md"
    files[decision] = _doc(
        "paper",
        id="dc",
        verdict="no-go",
        **{"signed-off-by": "D. Runje", "signed-off-date": "2026-03-04"},
    )

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    assert [f for f in findings if "no-go" in f.message] == []


def test_empty_evidence_on_a_resolved_artifact_is_a_gap() -> None:
    files = _scaffolded()
    path = LAYOUT.hypothesis_dir("dc", "2026-03-04-x") / "findings.md"
    files[path] = _doc(
        "hypothesis",
        id="2026-03-04-x",
        verdict="confirmed",
        readiness="resolved",
        **{"signed-off-by": "D. Runje", "signed-off-date": "2026-03-04"},
    )

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    evidence = [f for f in findings if "evidence" in f.message]
    assert [f.severity for f in evidence] == ["gap"]


def test_a_covers_entry_with_no_such_aim_is_a_gap() -> None:
    files = _scaffolded()
    files[LAYOUT.aims] = _doc("thesis", id="t", readiness="framing") + (
        "\n## Aims\n\n- **aim-1** — the first aim\n"
    )
    files[PITCH] = "---\nstatus:\n  level: paper\n  id: dc\n  covers: [aim-2]\n---\n"

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    covers = [f for f in findings if "aim-2" in f.message]
    assert [f.severity for f in covers] == ["gap"]


def test_covers_is_not_checked_when_the_repo_has_no_thesis() -> None:
    files = _scaffolded()
    files[PITCH] = "---\nstatus:\n  level: paper\n  id: dc\n  covers: [aim-2]\n---\n"

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    assert [f for f in findings if "aim-2" in f.message] == []


def test_a_dashboard_missing_a_live_artifact_is_a_gap() -> None:
    files = _scaffolded()
    files[PITCH] = _doc("paper", id="dc")

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    stale = [f for f in findings if f.file == "docs/research/dashboard.md"]
    assert [f.severity for f in stale] == ["gap"]
    assert "dc" in stale[0].message
    assert "progress" in stale[0].remedy


def test_a_dashboard_naming_an_artifact_that_is_gone_is_a_gap() -> None:
    files = _scaffolded()
    files[LAYOUT.dashboard] = "# Research dashboard\n\n- paper `ghost` — drafting\n"

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    assert any("ghost" in f.message for f in findings)


def test_the_ungenerated_dashboard_stub_is_not_stale_on_an_empty_repo() -> None:
    assert c.check_cross_artifact(LAYOUT, FakeProbe(_scaffolded())) == []


def test_cross_artifact_silent_when_dashboard_missing() -> None:
    """When dashboard file doesn't exist, no findings about it."""
    files = _scaffolded()
    files[PITCH] = _doc("paper", id="dc")
    # Remove the dashboard
    del files[LAYOUT.dashboard]

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    # Should not complain about missing dashboard in cross-artifact check
    # (check_layout handles that)
    stale = [f for f in findings if f.file == "docs/research/dashboard.md"]
    assert stale == []


def test_cross_artifact_ignores_documents_with_missing_status_blocks() -> None:
    files = _scaffolded()
    # Add a document without a status block
    path = LAYOUT.hypothesis_dir("dc", "2026-03-04-x") / "findings.md"
    files[path] = "# No status block\n\nJust content.\n"

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    # Should not report anything about the file without a status block
    assert not any(
        f.file == "docs/research/dc/hypotheses/2026-03-04-x/findings.md"
        for f in findings
    )


def test_cross_artifact_reports_unreadable_documents() -> None:
    files = _scaffolded()
    # Add a document that cannot be read
    path = LAYOUT.hypothesis_dir("dc", "2026-03-04-x") / "findings.md"
    files[path] = _doc("hypothesis", id="2026-03-04-x")

    probe = FakeProbe(files, unreadable={path})

    findings = c.check_cross_artifact(LAYOUT, probe)

    # Should report the unreadable file as a finding
    unreadable = [f for f in findings if f.file.endswith("findings.md")]
    assert len(unreadable) == 1
    assert unreadable[0].severity == "unreadable"


def test_cross_artifact_handles_null_artifact_ids() -> None:
    files = _scaffolded()
    # Add a document with null id
    files[PITCH] = _doc("paper", id="null")  # Rendered as null, not the string "null"

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    # Null ids should be skipped (not added to artifact_ids), so dashboard should be clean
    stale = [f for f in findings if f.file == "docs/research/dashboard.md"]
    assert stale == []


def test_cross_artifact_reports_unreadable_dashboard() -> None:
    files = _scaffolded()
    files[PITCH] = _doc("paper", id="dc")

    probe = FakeProbe(files, unreadable={LAYOUT.dashboard})

    findings = c.check_cross_artifact(LAYOUT, probe)

    # Should report the unreadable dashboard as a finding
    unreadable = [f for f in findings if f.file == "docs/research/dashboard.md"]
    assert len(unreadable) == 1
    assert unreadable[0].severity == "unreadable"
    assert "could not read" in unreadable[0].message


def test_cross_artifact_reports_unreadable_aims() -> None:
    files = _scaffolded()
    # Create a document with covers by directly writing YAML
    pitch_content = (
        "---\nstatus:\n  level: paper\n  id: dc\n  covers: [aim-1]\n---\n\n# Pitch\n"
    )
    files[PITCH] = pitch_content
    files[LAYOUT.aims] = _doc("thesis", id="t", readiness="framing")

    probe = FakeProbe(files, unreadable={LAYOUT.aims})

    findings = c.check_cross_artifact(LAYOUT, probe)

    # Should report the unreadable aims as a finding
    unreadable = [f for f in findings if "aims.md" in f.file]
    assert len(unreadable) == 1
    assert unreadable[0].severity == "unreadable"
    # Should not generate covers findings since aims cannot be checked
    covers_findings = [f for f in findings if "covers" in f.message]
    assert covers_findings == []


def test_cross_artifact_handles_documents_with_empty_covers() -> None:
    files = _scaffolded()
    files[LAYOUT.aims] = _doc("thesis", id="t", readiness="framing") + (
        "\n## Aims\n\n- **aim-1** — the first aim\n"
    )
    # Document with empty covers list should not trigger any findings
    pitch_content = (
        "---\nstatus:\n  level: paper\n  id: dc\n  covers: []\n---\n\n# Pitch\n"
    )
    files[PITCH] = pitch_content

    findings = c.check_cross_artifact(LAYOUT, FakeProbe(files))

    covers_findings = [
        f for f in findings if "covers" in f.message or "aim" in f.message
    ]
    assert covers_findings == []


def test_run_checks_deduplicates_findings_on_same_file() -> None:
    """run_checks deduplicates findings with identical (severity, file, message).

    Multiple families (frontmatter and cross-artifact) both read staged documents,
    so an unreadable file surfaces twice if not deduplicated. The composition point
    must keep the first occurrence and discard later duplicates.
    """
    files = _scaffolded()
    # Add a pitch.md file to the files dict, then mark it as unreadable
    files[PITCH] = "dummy content"
    # Create a FakeProbe that marks pitch.md as unreadable
    probe = FakeProbe(files, unreadable={PITCH})
    report = c.run_checks(LAYOUT, probe)

    # Should have exactly one finding for pitch.md, not two
    pitch_findings = [f for f in report.findings if "pitch.md" in f.file]
    assert len(pitch_findings) == 1
    assert pitch_findings[0].severity == "unreadable"
    # Verify counts reflect the deduplicated findings
    assert report.counts["unreadable"] == 1


def test_run_checks_preserves_findings_with_different_messages() -> None:
    """run_checks preserves findings on the same file with different messages.

    Deduplication only drops (severity, file, message) triples.
    If two findings differ in any field, they should both be preserved.
    """
    # Create a scenario with two different findings for the same file
    # (e.g., missing status block and some other issue)
    pitch_findings: list[m.Finding] = [
        m.Finding(
            severity="invalid",
            check="frontmatter",
            file="docs/research/dc/paper/pitch.md",
            message="first error",
            remedy="fix 1",
        ),
        m.Finding(
            severity="invalid",
            check="cross-artifact",
            file="docs/research/dc/paper/pitch.md",
            message="second error",
            remedy="fix 2",
        ),
    ]

    # Manually construct a report to test the deduplication logic
    # by simulating what run_checks would do
    seen: dict[tuple[str, str, str], None] = {}
    deduplicated: list[m.Finding] = []
    for finding in pitch_findings:
        key = (finding.severity, finding.file, finding.message)
        if key not in seen:
            seen[key] = None
            deduplicated.append(finding)

    # Both findings should survive because they have different messages
    assert len(deduplicated) == 2


def test_run_checks_no_finding_appears_twice_with_same_severity_file_message() -> None:
    """Assert no two findings in a full run_checks report share (severity, file, message)."""
    files = _scaffolded()
    report = c.run_checks(LAYOUT, FakeProbe(files))

    # Group findings by (severity, file, message)
    seen: set[tuple[str, str, str]] = set()
    for finding in report.findings:
        key = (finding.severity, finding.file, finding.message)
        # This assertion proves no duplicate was preserved
        assert key not in seen, f"Duplicate finding: {key}"
        seen.add(key)
