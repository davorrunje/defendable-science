"""The dashboard projection: collection and rendering (#130)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_check import FakeProbe, _doc  # the shared filesystem fake (#121)

from defendable_science.progress import collect as col
from defendable_science.progress import model as pm
from defendable_science.progress import render as pr
from defendable_science.scaffold import render as r
from defendable_science.scaffold.layout import Layout

ROOT = Path("/repo")
LAYOUT = Layout.default(ROOT)


def _artifact(**kwargs: object) -> pm.Artifact:
    base: dict[str, object] = {
        "level": "paper",
        "label": "dc",
        "link": "dc/paper/pitch.md",
    }
    base.update(kwargs)
    return pm.Artifact(**base)  # type: ignore[arg-type]


# --- the renderer -------------------------------------------------------------


def test_the_banner_names_the_command_that_writes_the_file() -> None:
    text = pr.render_dashboard(pm.Projection())

    assert text.splitlines()[0] == pr.BANNER
    assert "defendable-science progress dashboard" in pr.BANNER


def test_an_empty_projection_renders_every_section_and_no_totals() -> None:
    text = pr.render_dashboard(pm.Projection())

    assert "## Hypotheses" in text
    assert "## Papers" in text
    assert "## Thesis" in text
    # Absence is "not yet", never zero: no digit may stand in for an empty level.
    assert "0" not in text
    assert "%" not in text


def test_a_clean_artifact_is_one_row_and_no_detail_line() -> None:
    text = pr.render_dashboard(
        pm.Projection(
            artifacts=(
                _artifact(
                    artifact_id="dc",
                    verdict="publish",
                    readiness="published",
                    signed_off=True,
                    last_updated="2026-03-12",
                ),
            )
        )
    )

    assert "| [`dc`](dc/paper/pitch.md) | publish | published | 2026-03-12 |" in text
    assert "↳" not in text


def _row(text: str) -> str:
    """Return the one projected row in `text` — the header and rule excluded."""
    return next(line for line in text.splitlines() if line.startswith("| ["))


def test_a_refuted_verdict_renders_exactly_like_a_confirmed_one() -> None:
    """Refutation is successful science — no warning styling, no red mark."""
    common = {"signed_off": True, "readiness": "resolved", "last_updated": "2026-03-04"}

    def row(verdict: str) -> str:
        text = pr.render_dashboard(
            pm.Projection(
                artifacts=(
                    _artifact(
                        level="hypothesis", artifact_id="h", verdict=verdict, **common
                    ),
                )
            )
        )
        return _row(text).replace(verdict, "<verdict>")

    assert row("refuted") == row("confirmed")
    assert row("no-go") == row("publish")


def test_an_unsigned_verdict_is_not_rendered_as_decided() -> None:
    text = pr.render_dashboard(
        pm.Projection(
            artifacts=(
                _artifact(artifact_id="dc", verdict="publish", signed_off=False),
            )
        )
    )

    assert "publish (unsigned)" in text


@pytest.mark.parametrize("verdict", ["pending", "n/a"])
def test_a_verdict_that_decides_nothing_is_never_marked_unsigned(verdict: str) -> None:
    text = pr.render_dashboard(
        pm.Projection(artifacts=(_artifact(artifact_id="dc", verdict=verdict),))
    )

    assert "unsigned" not in _row(text)


def test_an_unset_field_renders_as_not_yet_set_never_zero() -> None:
    text = pr.render_dashboard(pm.Projection(artifacts=(_artifact(artifact_id="dc"),)))

    assert "| [`dc`](dc/paper/pitch.md) | — | — | — |" in text


def test_an_artifact_with_no_id_is_shown_and_is_not_claimed_as_an_id() -> None:
    text = pr.render_dashboard(pm.Projection(artifacts=(_artifact(),)))

    assert "[dc](dc/paper/pitch.md) (id not yet set)" in text
    assert pr.artifact_ids(text) == set()


def test_an_unreadable_artifact_is_reported_unknown_never_absent() -> None:
    text = pr.render_dashboard(
        pm.Projection(
            artifacts=(
                _artifact(
                    artifact_id="dc",
                    unreadable=True,
                    notes=("could not read dc/paper/decision.md",),
                ),
            )
        )
    )

    assert "| [`dc`](dc/paper/pitch.md) | unknown | unknown | — |" in text
    assert "could not read dc/paper/decision.md" in text


def test_the_detail_line_carries_coverage_blockers_and_understanding() -> None:
    text = pr.render_dashboard(
        pm.Projection(
            artifacts=(
                _artifact(
                    artifact_id="dc",
                    covers=("aim-2",),
                    blockers=("awaiting baseline rerun",),
                    understanding=("pitch.md: rival not addressed",),
                    blocked_by=("h1 (load-bearing, refuted)",),
                ),
            )
        )
    )
    detail = next(line for line in text.splitlines() if "↳" in line)

    assert detail == (
        "> ↳ `dc` — covers: aim-2 · blocked by: h1 (load-bearing, refuted) · "
        "blockers: awaiting baseline rerun · understanding: pitch.md: rival not "
        "addressed"
    )


def test_uncovered_aims_are_surfaced_as_a_named_gap_never_a_count() -> None:
    text = pr.render_dashboard(
        pm.Projection(
            artifacts=(
                _artifact(
                    level="thesis",
                    artifact_id="thesis",
                    label="thesis",
                    link="thesis/aims.md",
                    uncovered_aims=("aim-3",),
                ),
            )
        )
    )

    assert "uncovered aims: aim-3" in text


def test_the_hypothesis_table_names_the_paper_each_hypothesis_belongs_to() -> None:
    text = pr.render_dashboard(
        pm.Projection(
            artifacts=(
                _artifact(
                    level="hypothesis",
                    artifact_id="h1",
                    label="h1",
                    link="dc/hypotheses/h1/findings.md",
                    paper="dc",
                ),
            )
        )
    )

    assert "| id | paper | verdict | readiness | updated |" in text
    assert "| [`h1`](dc/hypotheses/h1/findings.md) | dc | — | — | — |" in text


def test_a_hypothesis_with_no_known_paper_renders_the_absent_marker() -> None:
    text = pr.render_dashboard(
        pm.Projection(
            artifacts=(_artifact(level="hypothesis", artifact_id="h1", paper=None),)
        )
    )

    assert "| [`h1`](dc/paper/pitch.md) | — | — | — | — |" in text


def test_rows_are_sorted_so_two_runs_are_byte_identical() -> None:
    first = _artifact(artifact_id="zeta", link="zeta/paper/pitch.md")
    second = _artifact(artifact_id="alpha", link="alpha/paper/pitch.md")

    forward = pr.render_dashboard(pm.Projection(artifacts=(first, second)))
    backward = pr.render_dashboard(pm.Projection(artifacts=(second, first)))

    assert forward == backward
    assert forward.index("alpha") < forward.index("zeta")


def test_rows_with_the_same_id_are_still_ordered_deterministically() -> None:
    first = _artifact(artifact_id="dc", link="a/paper/pitch.md")
    second = _artifact(artifact_id="dc", link="b/paper/pitch.md")

    forward = pr.render_dashboard(pm.Projection(artifacts=(first, second)))
    backward = pr.render_dashboard(pm.Projection(artifacts=(second, first)))

    assert forward == backward


def test_the_dashboard_carries_no_timestamp() -> None:
    """Idempotence: a date in the artifact would defeat the staleness check."""
    text = pr.render_dashboard(pm.Projection())

    assert "generated on" not in text.lower()


def test_a_pipe_in_a_field_cannot_break_the_table() -> None:
    text = pr.render_dashboard(
        pm.Projection(artifacts=(_artifact(artifact_id="dc", readiness="a|b"),))
    )

    assert r"a\|b" in text


# --- milestones ----------------------------------------------------------------


def test_no_milestones_file_renders_no_milestones_section() -> None:
    assert "## Milestones" not in pr.render_dashboard(pm.Projection())


def test_the_milestone_section_renders_whatever_the_file_holds() -> None:
    text = pr.render_dashboard(
        pm.Projection(
            milestones=pm.Milestones(
                entries=(
                    pm.Milestone(
                        name="viva", status="scheduled", next_deadline="2026-09-01"
                    ),
                )
            )
        )
    )

    assert "## Milestones" in text
    assert "| milestone | status | date | next deadline |" in text
    assert "| viva | scheduled | — | 2026-09-01 |" in text


def test_an_empty_milestone_list_is_not_yet_recorded_never_zero() -> None:
    text = pr.render_dashboard(pm.Projection(milestones=pm.Milestones()))

    assert "## Milestones" in text
    assert "not yet" in text


def test_an_unreadable_milestone_file_says_the_gates_are_unknown() -> None:
    text = pr.render_dashboard(pm.Projection(milestones=pm.Milestones(unknown=True)))

    assert "unknown, not absent" in text


def test_a_nameless_milestone_renders_the_absent_marker() -> None:
    text = pr.render_dashboard(
        pm.Projection(milestones=pm.Milestones(entries=(pm.Milestone(name=None),)))
    )

    assert "| — | — | — | — |" in text


# --- id extraction (what `check` compares against) -----------------------------


def test_artifact_ids_round_trips_what_the_renderer_wrote() -> None:
    projection = pm.Projection(
        artifacts=(
            _artifact(artifact_id="dc"),
            _artifact(level="hypothesis", artifact_id="h1", link="dc/h/findings.md"),
        )
    )

    assert pr.artifact_ids(pr.render_dashboard(projection)) == {"dc", "h1"}


def test_artifact_ids_ignores_prose_milestones_and_detail_lines() -> None:
    projection = pm.Projection(
        artifacts=(_artifact(artifact_id="dc", blockers=("waiting",)),),
        milestones=pm.Milestones(entries=(pm.Milestone(name="viva"),)),
    )

    assert pr.artifact_ids(pr.render_dashboard(projection)) == {"dc"}


# --- collection ----------------------------------------------------------------


def _scaffolded() -> dict[Path, str]:
    return {
        LAYOUT.papers_registry: r.render_papers_registry(),
        LAYOUT.portfolio_backlog: r.render_portfolio_backlog(),
        LAYOUT.dashboard: r.render_dashboard(),
        LAYOUT.references: r.render_references(),
        LAYOUT.triage: r.render_triage(),
        LAYOUT.datasets_manifest: r.render_datasets_manifest(),
        LAYOUT.config_file: r.render_config(),
    }


def test_an_empty_repo_projects_no_artifacts_and_no_findings() -> None:
    projection = col.collect(LAYOUT, FakeProbe(_scaffolded()))

    assert projection.artifacts == ()
    assert projection.findings == ()
    assert projection.milestones is None


def test_a_paper_is_one_artifact_however_many_staged_documents_it_has() -> None:
    files = _scaffolded()
    docs = LAYOUT.paper_docs_dir("dc")
    files[docs / "pitch.md"] = _doc("paper", id="dc")
    files[docs / "decision.md"] = _doc(
        "paper",
        id="dc",
        verdict="publish",
        readiness="published",
        **{"signed-off-by": "D. Runje", "last-updated": "2026-03-12"},
    )

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert len(projection.artifacts) == 1
    artifact = projection.artifacts[0]
    assert artifact.level == "paper"
    assert artifact.artifact_id == "dc"
    # The authoritative document, not the alphabetically-first one.
    assert artifact.link == "dc/paper/decision.md"
    assert artifact.verdict == "publish"
    assert artifact.signed_off is True
    assert artifact.last_updated == "2026-03-12"


def test_a_paper_with_no_decision_yet_projects_its_furthest_staged_document() -> None:
    files = _scaffolded()
    files[LAYOUT.paper_docs_dir("dc") / "pitch.md"] = _doc("paper", id="dc")
    files[LAYOUT.paper_docs_dir("dc") / "positioning.md"] = _doc("paper", id="dc")

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert [a.link for a in projection.artifacts] == ["dc/paper/positioning.md"]


def test_a_hypothesis_is_linked_to_the_paper_it_belongs_to() -> None:
    files = _scaffolded()
    files[LAYOUT.hypothesis_dir("dc", "h1") / "findings.md"] = _doc(
        "hypothesis", id="h1", verdict="refuted", readiness="resolved"
    )

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert [(a.level, a.artifact_id, a.paper) for a in projection.artifacts] == [
        ("hypothesis", "h1", "dc")
    ]


def test_a_signed_refuted_load_bearing_hypothesis_blocks_its_paper() -> None:
    files = _scaffolded()
    files[LAYOUT.paper_docs_dir("dc") / "pitch.md"] = _doc("paper", id="dc")
    files[LAYOUT.hypothesis_dir("dc", "h1") / "findings.md"] = _doc(
        "hypothesis",
        id="h1",
        verdict="refuted",
        readiness="resolved",
        **{"load-bearing": "true", "signed-off-by": "D. Runje"},
    )

    projection = col.collect(LAYOUT, FakeProbe(files))
    paper = next(a for a in projection.artifacts if a.level == "paper")

    assert paper.blocked_by == ("h1 (load-bearing, refuted)",)


def test_an_unsigned_refutation_does_not_yet_block_its_paper() -> None:
    """`signed-off-by: null` means not yet decided — it cannot block anything."""
    files = _scaffolded()
    files[LAYOUT.paper_docs_dir("dc") / "pitch.md"] = _doc("paper", id="dc")
    files[LAYOUT.hypothesis_dir("dc", "h1") / "findings.md"] = _doc(
        "hypothesis", id="h1", verdict="refuted", **{"load-bearing": "true"}
    )

    projection = col.collect(LAYOUT, FakeProbe(files))
    paper = next(a for a in projection.artifacts if a.level == "paper")

    assert paper.blocked_by == ()


def test_a_hypothesis_that_is_not_load_bearing_never_blocks_its_paper() -> None:
    files = _scaffolded()
    files[LAYOUT.paper_docs_dir("dc") / "pitch.md"] = _doc("paper", id="dc")
    files[LAYOUT.hypothesis_dir("dc", "h1") / "findings.md"] = _doc(
        "hypothesis",
        id="h1",
        verdict="refuted",
        **{"signed-off-by": "D. Runje", "load-bearing": "false"},
    )

    projection = col.collect(LAYOUT, FakeProbe(files))
    paper = next(a for a in projection.artifacts if a.level == "paper")

    assert paper.blocked_by == ()


def test_an_aim_no_paper_covers_is_reported_uncovered() -> None:
    files = _scaffolded()
    files[LAYOUT.aims] = _doc("thesis", id="t", readiness="framing") + (
        "\n## Aims\n\n- **aim-1** — one\n- **aim-2** — two\n"
    )
    files[LAYOUT.paper_docs_dir("dc") / "pitch.md"] = _doc(
        "paper", id="dc", covers="[aim-1]"
    )

    projection = col.collect(LAYOUT, FakeProbe(files))
    thesis = next(a for a in projection.artifacts if a.level == "thesis")

    assert thesis.uncovered_aims == ("aim-2",)
    assert next(a for a in projection.artifacts if a.level == "paper").covers == (
        "aim-1",
    )


def test_an_unreadable_aims_file_reports_no_coverage_rather_than_full_coverage() -> (
    None
):
    files = _scaffolded()
    files[LAYOUT.aims] = _doc("thesis", id="t", readiness="framing")

    projection = col.collect(LAYOUT, FakeProbe(files, unreadable={LAYOUT.aims}))
    thesis = next(a for a in projection.artifacts if a.level == "thesis")

    assert thesis.uncovered_aims == ()
    assert thesis.unreadable is True
    assert [f.severity for f in projection.findings] == ["unreadable"]


def test_a_thesis_groups_its_aims_and_kappa_into_one_artifact() -> None:
    files = _scaffolded()
    files[LAYOUT.aims] = _doc("thesis", id="t", readiness="framing")
    files[LAYOUT.kappa_dir / "kappa.md"] = _doc("thesis", id="t")

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert [(a.level, a.link) for a in projection.artifacts] == [
        ("thesis", "thesis/aims.md")
    ]


def test_a_document_that_cannot_be_read_is_one_finding_and_one_unknown_row() -> None:
    files = _scaffolded()
    path = LAYOUT.paper_docs_dir("dc") / "decision.md"
    files[path] = _doc("paper", id="dc")

    projection = col.collect(LAYOUT, FakeProbe(files, unreadable={path}))

    assert len(projection.findings) == 1
    assert projection.findings[0].severity == "unreadable"
    assert projection.findings[0].check == "progress"
    assert len(projection.artifacts) == 1
    artifact = projection.artifacts[0]
    assert artifact.unreadable is True
    assert artifact.artifact_id is None
    assert artifact.label == "dc"


def test_an_unreadable_sibling_leaves_the_authoritative_row_known() -> None:
    files = _scaffolded()
    docs = LAYOUT.paper_docs_dir("dc")
    files[docs / "pitch.md"] = _doc("paper", id="dc")
    files[docs / "decision.md"] = _doc(
        "paper", id="dc", verdict="no-go", **{"signed-off-by": "D. Runje"}
    )

    projection = col.collect(LAYOUT, FakeProbe(files, unreadable={docs / "pitch.md"}))
    artifact = projection.artifacts[0]

    assert artifact.unreadable is False
    assert artifact.verdict == "no-go"
    assert any("pitch.md" in note for note in artifact.notes)
    assert len(projection.findings) == 1


def test_unparsable_frontmatter_is_unknown_never_a_clean_empty_row() -> None:
    files = _scaffolded()
    files[LAYOUT.paper_docs_dir("dc") / "decision.md"] = "---\nstatus: [1, 2]\n---\n"

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert [f.severity for f in projection.findings] == ["invalid"]
    assert projection.artifacts[0].unreadable is True


def test_a_document_with_no_status_block_projects_an_empty_row() -> None:
    files = _scaffolded()
    files[LAYOUT.paper_docs_dir("dc") / "decision.md"] = "# Decision\n"

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.findings == ()
    assert projection.artifacts[0].verdict is None
    assert projection.artifacts[0].unreadable is False


def test_understanding_gaps_are_named_and_attributed_to_their_document() -> None:
    files = _scaffolded()
    docs = LAYOUT.paper_docs_dir("dc")
    files[docs / "pitch.md"] = _doc(
        "paper", id="dc", understanding="{status: gaps, unresolved: [rival A]}"
    )
    files[docs / "decision.md"] = _doc("paper", id="dc")

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.artifacts[0].understanding == ("pitch.md: rival A",)


def test_understanding_marked_ok_adds_no_noise() -> None:
    files = _scaffolded()
    files[LAYOUT.paper_docs_dir("dc") / "decision.md"] = _doc(
        "paper", id="dc", understanding="{status: ok, unresolved: []}"
    )

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.artifacts[0].understanding == ()


def test_understanding_flagged_as_gaps_with_nothing_named_is_still_surfaced() -> None:
    files = _scaffolded()
    files[LAYOUT.paper_docs_dir("dc") / "decision.md"] = _doc(
        "paper", id="dc", understanding="{status: gaps, unresolved: []}"
    )

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.artifacts[0].understanding == (
        "decision.md: gaps recorded, none named",
    )


def test_a_malformed_understanding_block_is_surfaced_rather_than_dropped() -> None:
    files = _scaffolded()
    files[LAYOUT.paper_docs_dir("dc") / "decision.md"] = _doc(
        "paper", id="dc", understanding="'ok'"
    )

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.artifacts[0].understanding == (
        "decision.md: understanding block is not a mapping",
    )


def test_blockers_and_covers_written_as_plain_text_are_still_read() -> None:
    files = _scaffolded()
    files[LAYOUT.paper_docs_dir("dc") / "decision.md"] = _doc(
        "paper", id="dc", blockers="awaiting rerun", covers="aim-1"
    )

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.artifacts[0].blockers == ("awaiting rerun",)
    assert projection.artifacts[0].covers == ("aim-1",)


def test_an_empty_collection_field_contributes_nothing() -> None:
    files = _scaffolded()
    files[LAYOUT.paper_docs_dir("dc") / "decision.md"] = _doc("paper", id="dc")

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.artifacts[0].blockers == ()
    assert projection.artifacts[0].covers == ()


# --- milestone collection -------------------------------------------------------


def test_the_configured_gate_list_is_read_verbatim_never_the_packaged_one() -> None:
    files = _scaffolded()
    files[LAYOUT.milestones] = (
        "milestones:\n"
        "  - name: transfer-report\n"
        "    status: passed\n"
        "    date: 2026-02-01\n"
        "    next-deadline: null\n"
    )

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.milestones is not None
    assert projection.milestones.entries == (
        pm.Milestone(name="transfer-report", status="passed", date="2026-02-01"),
    )
    # Nothing from `render.PROGRAM_GATES` leaks in.
    assert all(m.name != "candidacy" for m in projection.milestones.entries)


def test_the_packaged_milestone_template_parses_as_written() -> None:
    """A drift guard: one artifact must not have two shapes."""
    files = _scaffolded()
    files[LAYOUT.milestones] = r.render_milestones()

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.milestones is not None
    assert [m.name for m in projection.milestones.entries] == list(r.PROGRAM_GATES)


def test_an_unreadable_milestone_file_is_unknown_never_an_empty_gate_list() -> None:
    files = _scaffolded()
    files[LAYOUT.milestones] = r.render_milestones()

    projection = col.collect(LAYOUT, FakeProbe(files, unreadable={LAYOUT.milestones}))

    assert projection.milestones == pm.Milestones(unknown=True)
    assert [f.severity for f in projection.findings] == ["unreadable"]


def test_invalid_milestone_yaml_is_unknown_never_an_empty_gate_list() -> None:
    files = _scaffolded()
    files[LAYOUT.milestones] = "milestones: [\n"

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.milestones == pm.Milestones(unknown=True)
    assert [f.severity for f in projection.findings] == ["unreadable"]


@pytest.mark.parametrize(
    "text", ["gates: []\n", "- a\n- b\n", "milestones: 3\n"], ids=["key", "list", "int"]
)
def test_a_milestone_file_with_no_gate_list_is_unknown(text: str) -> None:
    files = _scaffolded()
    files[LAYOUT.milestones] = text

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.milestones == pm.Milestones(unknown=True)
    assert [f.severity for f in projection.findings] == ["invalid"]


def test_a_deliberately_emptied_gate_list_is_empty_not_unknown() -> None:
    files = _scaffolded()
    files[LAYOUT.milestones] = "milestones: []\n"

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.milestones == pm.Milestones()
    assert projection.findings == ()


def test_a_blank_milestone_file_is_empty_not_unknown() -> None:
    files = _scaffolded()
    files[LAYOUT.milestones] = "\n"

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.milestones == pm.Milestones()


def test_a_milestone_entry_that_is_not_a_mapping_is_shown_not_dropped() -> None:
    files = _scaffolded()
    files[LAYOUT.milestones] = "milestones:\n  - proposal\n"

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.milestones == pm.Milestones(
        entries=(pm.Milestone(name="proposal"),)
    )


def test_a_milestone_directory_where_the_file_belongs_is_not_read() -> None:
    projection = col.collect(LAYOUT, FakeProbe(_scaffolded(), dirs={LAYOUT.milestones}))

    assert projection.milestones is None


def test_a_paper_document_outside_any_paper_directory_still_gets_a_row() -> None:
    """It is misplaced, not absent — dropping it would be a projection that lies."""
    files = _scaffolded()
    files[LAYOUT.research_root / "pitch.md"] = _doc("paper", id="stray")

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert [(a.label, a.paper) for a in projection.artifacts] == [
        (LAYOUT.research_root.name, None)
    ]


def test_a_staged_document_in_the_thesis_tree_is_not_attributed_to_a_paper() -> None:
    """`thesis` is the thesis directory, never a paper called "thesis"."""
    files = _scaffolded()
    files[LAYOUT.thesis_dir / "findings.md"] = _doc("hypothesis", id="h1")

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert [(a.level, a.paper) for a in projection.artifacts] == [("hypothesis", None)]


def test_a_thesis_tree_outside_the_research_root_is_still_projected() -> None:
    """A relocated `thesis_dir` is a supported layout, so links need the `..` hop."""
    layout = Layout(
        repo_root=ROOT,
        research_root=ROOT / "papers",
        literature_dir=ROOT / "papers" / "literature",
        datasets_manifest=ROOT / "datasets.yml",
        thesis_dir=ROOT / "thesis",
    )
    files = {layout.thesis_dir / "findings.md": _doc("hypothesis", id="h1")}

    projection = col.collect(layout, FakeProbe(files))

    assert [(a.level, a.paper, a.link) for a in projection.artifacts] == [
        ("hypothesis", None, "../thesis/findings.md")
    ]


def test_a_milestone_key_with_no_value_is_empty_not_unknown() -> None:
    files = _scaffolded()
    files[LAYOUT.milestones] = "milestones:\n"

    projection = col.collect(LAYOUT, FakeProbe(files))

    assert projection.milestones == pm.Milestones()
    assert projection.findings == ()
