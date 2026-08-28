"""End-to-end CLI coverage for the dataset commands + error paths (#16 sweep)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from defendable_science.cli import app
from defendable_science.dataset import manifest as manifest_mod
from defendable_science.dataset import retrieval as retrieval_mod

runner = CliRunner()


def _tier_a_project(tmp_path: Path) -> Path:
    """Create a cwd with a Tier-A datasets.yml + its in-repo file; return cwd."""
    (tmp_path / "data").mkdir()
    payload = b"tier-a bytes"
    (tmp_path / "data" / "f.bin").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    (tmp_path / "datasets.yml").write_text(
        f"""
datasets:
  - id: ds-a
    version: "1.0.0"
    tier: A
    license: CC0-1.0
    redistributable: true
    access: open
    files:
      - path: data/f.bin
        sha256: {digest}
    datasheet: datasheets/ds-a.md
""",
        encoding="utf-8",
    )
    return tmp_path


def test_validate_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    result = runner.invoke(app, ["dataset", "validate"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["ok"] is True


def test_validate_malformed_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "datasets.yml").write_text("datasets: [oops\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["dataset", "validate"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_ingest_bad_file_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["dataset", "ingest", "nope.json"]).exit_code == 1


def test_emit_all_and_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    all_ = runner.invoke(app, ["dataset", "emit", "--all"])
    assert all_.exit_code == 0
    assert isinstance(json.loads(all_.stdout), list)
    assert runner.invoke(app, ["dataset", "emit", "ghost"]).exit_code == 1


def test_fetch_and_verify_tier_a(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    fetch = runner.invoke(app, ["dataset", "fetch", "ds-a"])
    assert fetch.exit_code == 0
    # Fetch returns the absolute path to the Tier-A file
    assert json.loads(fetch.stdout) == [str(tmp_path / "data/f.bin")]
    verify = runner.invoke(app, ["dataset", "verify", "ds-a"])
    assert verify.exit_code == 0
    assert json.loads(verify.stdout)["ok"] is True


def test_fetch_verify_audit_use_configured_cache_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dataset fetch/verify/audit resolve the cache dir from config.yml (#65).

    The cache directory the CLI actually passes to :mod:`retrieval` must be
    exactly the one ``research-init`` gitignores — sourced from
    ``cache_dir:`` instead of a hardcoded literal, so the two cannot drift.
    """
    monkeypatch.chdir(_tier_a_project(tmp_path))
    cfg = tmp_path / ".defendable-science"
    cfg.mkdir()
    (cfg / "config.yml").write_text("cache_dir: .custom-cache\n", encoding="utf-8")

    seen: list[Path] = []
    original_fetch = retrieval_mod.fetch
    original_verify = retrieval_mod.verify
    original_audit = retrieval_mod.audit

    def _fetch_spy(entry, *, cache_dir, mirror=None, repo_root=None, **kw):  # type: ignore[no-untyped-def]
        seen.append(Path(cache_dir))
        return original_fetch(
            entry, cache_dir=cache_dir, mirror=mirror, repo_root=repo_root, **kw
        )

    def _verify_spy(entry, *, cache_dir, repo_root=None):  # type: ignore[no-untyped-def]
        seen.append(Path(cache_dir))
        return original_verify(entry, cache_dir=cache_dir, repo_root=repo_root)

    def _audit_spy(manifest, *, cache_dir, mirror=None, repo_root=None):  # type: ignore[no-untyped-def]
        seen.append(Path(cache_dir))
        return original_audit(
            manifest, cache_dir=cache_dir, mirror=mirror, repo_root=repo_root
        )

    monkeypatch.setattr(retrieval_mod, "fetch", _fetch_spy)
    monkeypatch.setattr(retrieval_mod, "verify", _verify_spy)
    monkeypatch.setattr(retrieval_mod, "audit", _audit_spy)

    assert runner.invoke(app, ["dataset", "fetch", "ds-a"]).exit_code == 0
    assert runner.invoke(app, ["dataset", "verify", "ds-a"]).exit_code == 0
    assert runner.invoke(app, ["dataset", "audit"]).exit_code == 0

    # `audit` internally re-runs `verify`, so more than 3 calls may land here —
    # what matters is that every one of them got the *configured* root, never
    # the old hardcoded ``.defendable-science/cache/datasets`` literal.
    expected = tmp_path / ".custom-cache/datasets"
    assert len(seen) >= 3
    assert all(path == expected for path in seen)


def test_fetch_exits_1_on_invalid_cache_dir_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    cfg = tmp_path / ".defendable-science"
    cfg.mkdir()
    (cfg / "config.yml").write_text("cache_dir:\n  - nope\n", encoding="utf-8")
    result = runner.invoke(app, ["dataset", "fetch", "ds-a"])
    assert result.exit_code == 1
    assert "cache_dir" in result.stderr


def test_fetch_unknown_id_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    assert runner.invoke(app, ["dataset", "fetch", "ghost"]).exit_code == 1


def test_verify_corrupt_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    (tmp_path / "data" / "f.bin").write_bytes(b"tampered")
    assert runner.invoke(app, ["dataset", "verify", "ds-a"]).exit_code == 1


def test_mirror_without_config_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    result = runner.invoke(app, ["dataset", "mirror", "ds-a"])
    assert result.exit_code == 1
    assert "no mirror configured" in result.stderr


def test_audit_whole_and_by_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    whole = runner.invoke(app, ["dataset", "audit"])
    assert whole.exit_code == 0
    assert json.loads(whole.stdout)["ok"] is True
    by_id = runner.invoke(app, ["dataset", "audit", "ds-a"])
    assert by_id.exit_code == 0


def test_audit_fails_on_missing_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    (tmp_path / "data" / "f.bin").unlink()
    result = runner.invoke(app, ["dataset", "audit"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_emit_no_arg_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(_tier_a_project(tmp_path))
    result = runner.invoke(app, ["dataset", "emit"])
    assert result.exit_code == 1
    assert "give a dataset id or --all" in result.stderr


def test_fetch_tier_c_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "datasets.yml").write_text(
        f"""
datasets:
  - id: ds-c
    version: "1.0.0"
    tier: C
    license: proprietary
    redistributable: false
    access: gated
    files:
      - path: data/c.bin
        sha256: {"d" * 64}
    datasheet: datasheets/ds-c.md
    instructions: email the authors
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["dataset", "fetch", "ds-c"])
    assert result.exit_code == 1
    assert "gated" in result.stderr


def test_mirror_success_with_fake_rclone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from defendable_science import cli
    from defendable_science.dataset import retrieval as retrieval_mod

    monkeypatch.chdir(_tier_a_project(tmp_path))

    class _Proc:
        returncode = 0
        stderr = b""

    def _ok(args: list[str], **_kw: object) -> _Proc:
        return _Proc()

    monkeypatch.setattr(
        cli, "_mirror_from", lambda _m: retrieval_mod.Mirror(remote="store", run=_ok)
    )
    result = runner.invoke(app, ["dataset", "mirror", "ds-a"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["mirrored"] == "ds-a"


def test_emit_malformed_manifest_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "bad.yml").write_text("datasets: [oops\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["dataset", "emit", "x", "--manifest", "bad.yml"])
    assert result.exit_code == 1


def test_fetch_malformed_manifest_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "datasets.yml").write_text("datasets: [oops\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["dataset", "fetch", "x"])
    assert result.exit_code == 1
    assert "manifest error" in result.stderr


def test_mirror_retrieval_error_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "datasets.yml").write_text(
        f"""
mirror:
  rclone_remote: store
  base_path: base
datasets:
  - id: ds-c
    version: "1.0.0"
    tier: C
    license: proprietary
    redistributable: false
    access: gated
    files:
      - path: data/c.bin
        sha256: {"d" * 64}
    datasheet: datasheets/ds-c.md
    instructions: email the authors
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["dataset", "mirror", "ds-c"])
    assert result.exit_code == 1
    assert "mirror failed" in result.stderr


def test_verify_from_a_subdirectory_uses_the_repo_root_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The content-addressed cache is anchored to the repo root, not the cwd.

    ``research-init`` gitignores exactly one cache directory, at the repo root.
    Resolving ``cache_dir`` against the cwd instead makes a command run from
    inside a paper read (and, on ``fetch``, write) a *different*, un-gitignored
    directory — a silent wrong-location write (#122).
    """
    payload = b"tier-b bytes"
    digest = hashlib.sha256(payload).hexdigest()
    (tmp_path / ".defendable-science").mkdir()
    manifest = tmp_path / "datasets.yml"
    manifest.write_text(
        f"""
datasets:
  - id: ds-b
    version: "1.0.0"
    tier: B
    license: CC-BY-4.0
    redistributable: true
    access: open
    files:
      - path: data/f.bin
        sha256: {digest}
    retrieval:
      kind: http
      url: https://example.org/f.bin
    datasheet: datasheets/ds-b.md
""",
        encoding="utf-8",
    )
    blob = tmp_path / ".defendable-science" / "cache" / "datasets" / "sha256" / digest
    blob.parent.mkdir(parents=True)
    blob.write_bytes(payload)
    paper = tmp_path / "docs" / "research" / "dc"
    paper.mkdir(parents=True)
    monkeypatch.chdir(paper)

    result = runner.invoke(
        app, ["dataset", "verify", "ds-b", "--manifest", str(manifest)]
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["ok"] is True


# --- layout.datasets_manifest routing (#124) ------------------------------------------

#: The recorded, deliberately non-default manifest location used below.
_RECORDED = Path("data/datasets.yml")


def _recorded_manifest_project(tmp_path: Path) -> Path:
    """Build a repo whose ``config.yml`` records a non-default manifest path.

    The Tier-A manifest is moved to ``data/datasets.yml`` and nothing is left at
    the default ``datasets.yml``, so any command that still hardcodes the
    default fails loudly instead of half-passing.

    :param tmp_path: The temporary repository root.
    :returns: The repository root.
    """
    root = _tier_a_project(tmp_path)
    (root / "datasets.yml").rename(root / _RECORDED)
    config_dir = root / ".defendable-science"
    config_dir.mkdir()
    (config_dir / "config.yml").write_text(
        f"layout:\n  datasets_manifest: {_RECORDED.as_posix()}\n", encoding="utf-8"
    )
    return root


@pytest.mark.parametrize(
    "argv",
    [
        ["dataset", "validate"],
        ["dataset", "emit", "--all"],
        ["dataset", "fetch", "ds-a"],
        ["dataset", "verify", "ds-a"],
        ["dataset", "mirror", "ds-a"],
        ["dataset", "audit"],
    ],
    ids=lambda argv: argv[1],
)
def test_dataset_commands_resolve_the_recorded_manifest(
    argv: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every dataset command reads ``layout.datasets_manifest`` (#124).

    ``resolve_layout`` treats an unknown ``layout:`` key as an error precisely
    so nothing is silently dropped; a *known* key that no command consumes is
    the same silent ignore by another route.
    """
    root = _recorded_manifest_project(tmp_path)
    monkeypatch.chdir(root)
    seen: list[Path] = []
    original_load = manifest_mod.load

    def _load_spy(path: str | Path) -> manifest_mod.Manifest:
        seen.append(Path(path))
        return original_load(path)

    monkeypatch.setattr(manifest_mod, "load", _load_spy)

    result = runner.invoke(app, argv)

    assert seen, f"{argv} never loaded a manifest: {result.stdout + result.stderr}"
    assert all(path == root.resolve() / _RECORDED for path in seen), seen


def test_manifest_resolves_from_the_layout_in_a_subdirectory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An omitted ``--manifest`` is anchored to the repo root, not the cwd.

    A recorded path describes a location in the *repository*. Resolving it
    against the cwd makes a command run from inside a paper report "no such
    file" for a manifest that is right there at the top of the repo.
    """
    root = _recorded_manifest_project(tmp_path)
    paper = root / "docs" / "research" / "dc"
    paper.mkdir(parents=True)
    monkeypatch.chdir(paper)

    result = runner.invoke(app, ["dataset", "emit", "ds-a"])

    assert result.exit_code == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["name"] == "ds-a"


def test_explicit_manifest_wins_and_stays_cwd_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit ``--manifest`` overrides the layout and keeps the cwd frame.

    Two frames meet here and they are not the same decision. A path recorded in
    ``config.yml`` describes a location in the repository, so it anchors to the
    repo root. A path the author *types* is relative to the directory they
    typed it in — re-anchoring that would quietly read a different file than
    the one they named.
    """
    root = _recorded_manifest_project(tmp_path)
    here = root / "elsewhere"
    here.mkdir()
    (here / "local.yml").write_text(
        f"""
datasets:
  - id: ds-z
    version: "1.0.0"
    tier: A
    license: CC0-1.0
    redistributable: true
    access: open
    files:
      - path: data/f.bin
        sha256: {"e" * 64}
    datasheet: datasheets/ds-z.md
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(here)
    # The typed path exists *only* under the cwd, so anchoring it to the repo
    # root instead would find nothing and the assertions below would not hold.
    assert not (root / "local.yml").exists()

    result = runner.invoke(app, ["dataset", "emit", "ds-z", "--manifest", "local.yml"])

    assert result.exit_code == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["name"] == "ds-z"


def test_missing_recorded_manifest_names_the_path_it_looked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manifest that is not there fails loudly, naming the resolved path.

    Never an empty-but-valid manifest, and never a bare ``datasets.yml`` that
    hides *which* location was actually consulted.
    """
    (tmp_path / ".defendable-science").mkdir()
    (tmp_path / ".defendable-science" / "config.yml").write_text(
        f"layout:\n  datasets_manifest: {_RECORDED.as_posix()}\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    expected = str(tmp_path.resolve() / _RECORDED)

    fetch = runner.invoke(app, ["dataset", "fetch", "ds-a"])
    assert fetch.exit_code == 1
    assert expected in fetch.stderr
    assert "no such file" in fetch.stderr

    validate = runner.invoke(app, ["dataset", "validate"])
    assert validate.exit_code == 1
    report = json.loads(validate.stdout)
    assert report["ok"] is False
    assert expected in report["errors"][0]


# --- init (#123) ---------------------------------------------------------------------
#
# Every scaffold here lands in a `repo` subdirectory of `tmp_path`, never in
# `tmp_path` itself: the autouse fake-HOME fixture already populates `tmp_path`,
# and the dry-run assertion ("nothing was written") is only worth making if it
# can be exact. It also keeps the writer's `.gitignore` merge a long way from
# this repository's own.


def _fresh_repo(tmp_path: Path) -> Path:
    """Return an empty, un-onboarded repo root under `tmp_path`."""
    root = tmp_path / "repo"
    root.mkdir()
    return root


def test_init_scaffolds_and_reports_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _fresh_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["counts"]["created"] > 0
    assert payload["thesis"] is False
    assert payload["dry_run"] is False
    assert payload["root"] == str(repo.resolve())
    paths = {action["path"] for action in payload["actions"]}
    assert "docs/research/papers.md" in paths  # repo-relative in the report
    assert (repo / "docs" / "research" / "papers.md").is_file()


def test_init_counts_every_action_it_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The counts are a tally of the actions, not a separate claim about them."""
    repo = _fresh_repo(tmp_path)
    monkeypatch.chdir(repo)

    payload = json.loads(runner.invoke(app, ["init"]).stdout)

    counts = payload["counts"]
    assert set(counts) == {"created", "exists", "merged"}
    assert sum(counts.values()) == len(payload["actions"])
    for status in ("created", "exists", "merged"):
        tallied = [a for a in payload["actions"] if a["status"] == status]
        assert counts[status] == len(tallied)
    # `.gitignore` is *merged*, never *created*: the writer appends the missing
    # entries whether or not the file was already there.
    assert counts["merged"] == 1


def test_init_is_idempotent_at_the_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _fresh_repo(tmp_path)
    monkeypatch.chdir(repo)
    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["counts"]["created"] == 0
    assert payload["counts"]["exists"] == len(payload["actions"])


def test_init_dry_run_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _fresh_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["init", "--dry-run"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["counts"]["created"] > 0
    assert list(repo.iterdir()) == []


def test_init_thesis_scaffolds_the_thesis_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _fresh_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["init", "--thesis"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["thesis"] is True
    assert (repo / "docs" / "research" / "thesis" / "aims.md").is_file()


def test_init_honours_root_and_a_recorded_layout(tmp_path: Path) -> None:
    """``--root`` is authoritative for the *whole* resolution chain.

    Not just for where files land: the config that is read, and the cache path
    written into ``.gitignore``, must come from that root too. This test never
    chdirs, so a resolution that quietly fell back to the cwd would reach for
    this checkout instead of the scaffolded repo.
    """
    repo = _fresh_repo(tmp_path)
    (repo / ".defendable-science").mkdir()
    (repo / ".defendable-science" / "config.yml").write_text(
        "layout:\n  research_root: writing/\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["init", "--root", str(repo)])

    assert result.exit_code == 0, result.output
    assert (repo / "writing" / "papers.md").is_file()
    payload = json.loads(result.stdout)
    assert payload["root"] == str(repo.resolve())
    assert "writing/papers.md" in {a["path"] for a in payload["actions"]}
    ignored = (repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".defendable-science/cache/" in ignored
    assert not any(line.startswith("/") for line in ignored)


def test_init_gitignores_the_configured_cache_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repo that moved its cache gets *that* path ignored, not the default."""
    repo = _fresh_repo(tmp_path)
    (repo / ".defendable-science").mkdir()
    (repo / ".defendable-science" / "config.yml").write_text(
        "cache_dir: var/cache/ds\n", encoding="utf-8"
    )
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0, result.output
    assert "var/cache/ds/" in (repo / ".gitignore").read_text(encoding="utf-8")


def test_init_exits_1_on_an_invalid_layout_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _fresh_repo(tmp_path)
    (repo / ".defendable-science").mkdir()
    (repo / ".defendable-science" / "config.yml").write_text(
        "layout:\n  papers_dir: x/\n", encoding="utf-8"
    )
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 1
    assert "unknown layout key" in result.output
    assert "research_root" in result.output
    assert "Traceback" not in result.output
    assert result.stdout.strip() == ""
    assert not (repo / "docs").exists()


def test_init_reports_a_write_failure_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unwritable path is an actionable message, never a raw traceback.

    And never a report either: the scaffold got part-way (``papers.md`` is on
    disk) and saying so with a JSON report would present a half-finished repo
    as a finished one.
    """
    repo = _fresh_repo(tmp_path)
    (repo / ".gitignore").mkdir()  # the writer's last step cannot write here
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 1
    assert not isinstance(result.exception, OSError)
    assert "Traceback" not in result.output
    assert ".gitignore" in result.output
    assert "incomplete" in result.output
    assert result.stdout.strip() == ""
    assert (repo / "docs" / "research" / "papers.md").is_file()
