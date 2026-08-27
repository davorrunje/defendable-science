"""Tests for the ``literature fetch|confirm|verify|mirror`` CLI wiring (Task 14).

Follows ``tests/test_literature.py``'s pattern: a ``CliRunner`` invoking the real
Typer app, with ``cli._lit_client`` (and, here, ``cli._lit_mirror``) monkeypatched
to inject fakes rather than touching the network or shelling out to rclone.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import typer
import yaml
from typer.testing import CliRunner

from defendable_science import cli
from defendable_science.cli import app
from defendable_science.core import http
from defendable_science.core.download import DownloadError
from defendable_science.core.mirror import Mirror
from defendable_science.literature import acquire as a
from defendable_science.scaffold.layout import Layout

runner = CliRunner()

PDF = b"%PDF-1.4 body"
PDF_SHA = hashlib.sha256(PDF).hexdigest()


# --- fakes --------------------------------------------------------------------


class FakeResponse:
    def __init__(
        self, status_code: int, payload: Any, headers: dict[str, str] | None = None
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers: dict[str, str] = headers or {}

    def json(self) -> Any:
        return self._payload

    @property
    def text(self) -> str:
        return json.dumps(self._payload)


class FakeSession:
    """A routing fake: maps a URL to a queue of responses (or one response)."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes

    def get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> FakeResponse:
        payload = self.routes.get(url)
        if isinstance(payload, list):
            payload = payload.pop(0)
        if isinstance(payload, FakeResponse):
            return payload
        if payload is None:
            return FakeResponse(404, {})
        return FakeResponse(200, payload)


def _fake_client(routes: dict[str, Any] | None = None, **kw: Any) -> http.HttpClient:
    return http.HttpClient(
        session=FakeSession(routes or {}), sleep=lambda _s: None, cache_dir=None, **kw
    )


class _Proc:
    def __init__(self, returncode: int = 0, stderr: bytes | None = None) -> None:
        self.returncode = returncode
        self.stderr = stderr


#: rclone's "file not found" — the only kind of non-zero exit that means the key
#: is genuinely absent rather than unaskable (``core.mirror.ABSENT_EXIT_CODES``).
ABSENT = 4


def _run_ok(_args: list[str], **_kw: Any) -> _Proc:
    return _Proc(0)


def _run_absent(_args: list[str], **_kw: Any) -> _Proc:
    """Rclone answered: the key is not there."""
    return _Proc(ABSENT)


def _run_unreachable(_args: list[str], **_kw: Any) -> _Proc:
    """Rclone could not ask — an expired credential, say (exit 7, fatal)."""
    return _Proc(7, b"SignatureDoesNotMatch: the token has expired")


def _run_missing_rclone(_args: list[str], **_kw: Any) -> _Proc:
    raise FileNotFoundError


# --- config / registry fixtures ------------------------------------------------


def _write_config(
    tmp_path: Path, lit: Any = None, cache_dir: str | None = None
) -> None:
    cfg = tmp_path / ".defendable-science"
    cfg.mkdir(exist_ok=True)
    data: dict[str, Any] = {}
    if cache_dir is not None:
        data["cache_dir"] = cache_dir
    if lit is not None:
        data["literature"] = lit
    (cfg / "config.yml").write_text(yaml.safe_dump(data), encoding="utf-8")


def _item(
    citekey: str,
    *,
    title: str = "A Title",
    year: int = 2020,
    family: str = "Smith",
    doi: str | None = "10.1234/x",
    spine: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": citekey,
        "type": "article",
        "title": title,
        "issued": {"date-parts": [[year]]},
        "author": [{"family": family, "given": "A"}],
    }
    if doi is not None:
        out["DOI"] = doi
    if spine is not None:
        out["custom"] = {"defendable-science": spine}
    return out


def _spine(sha: str = PDF_SHA, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema": 1,
        "pid": None,
        "files": [{"path": f"sha256/{sha}", "sha256": f"sha256:{sha}"}],
        "license": {"id": None, "observed": None, "source": None},
        "redistributable": False,
    }
    base.update(kw)
    return base


def _write_registry(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _lit_cache_dir(tmp_path: Path) -> Path:
    return tmp_path / ".defendable-science" / "cache" / "literature"


def _seed_blob(tmp_path: Path, body: bytes = PDF) -> str:
    sha = hashlib.sha256(body).hexdigest()
    blob = _lit_cache_dir(tmp_path) / "sha256" / sha
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(body)
    return sha


# --- 1/2: exactly one of CITEKEY or --all (fetch / verify / mirror) -----------


@pytest.mark.parametrize("command", ["fetch", "verify", "mirror"])
def test_neither_citekey_nor_all_exits_2(
    command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["literature", command])
    assert result.exit_code == 2
    assert "CITEKEY or --all" in result.stderr


@pytest.mark.parametrize("command", ["fetch", "verify", "mirror"])
def test_both_citekey_and_all_exits_2(
    command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["literature", command, "somekey", "--all"])
    assert result.exit_code == 2
    assert "CITEKEY or --all" in result.stderr


# --- 3: exactly one of --sha256 or --file (confirm) ----------------------------


def test_confirm_neither_sha_nor_file_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["literature", "confirm", "k1"])
    assert result.exit_code == 2
    assert "--sha256 or --file" in result.stderr


def test_confirm_both_sha_and_file_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app, ["literature", "confirm", "k1", "--sha256", "ab", "--file", "x.pdf"]
    )
    assert result.exit_code == 2
    assert "--sha256 or --file" in result.stderr


# --- 4: fetch --all clean sweep -------------------------------------------------


def test_fetch_all_clean_sweep_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    sha = _seed_blob(tmp_path)
    _write_registry(tmp_path / "references.json", [_item("k1", spine=_spine(sha))])
    _write_config(tmp_path, {"registry": "references.json", "triage": "triage.yml"})
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())

    result = runner.invoke(app, ["literature", "fetch", "--all"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert set(report) == {
        "complete",
        "not_attempted",
        "fetched",
        "cached",
        "quarantined",
        "manual",
        "committable",
        "errors",
    }
    assert report["complete"] is True
    assert report["errors"] == []
    assert report["cached"][0]["citekey"] == "k1"


# --- 5: fetch --all with an errors[] row exits 1 --------------------------------


def test_fetch_all_with_error_row_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    # No DOI/pid on the entry -- `_resolve_work` errors without any network call.
    _write_registry(tmp_path / "references.json", [_item("nodoi", doi=None)])
    _write_config(tmp_path, {"registry": "references.json", "triage": "triage.yml"})
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())

    result = runner.invoke(app, ["literature", "fetch", "--all"])

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["errors"]
    assert report["errors"][0]["citekey"] == "nodoi"
    assert "error" in report["errors"][0]


# --- 6: fetch --all aborted by a rate limit -------------------------------------


def test_fetch_all_rate_limited_aborts_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_registry(tmp_path / "references.json", [_item("k1")])
    _write_config(tmp_path, {"registry": "references.json", "triage": "triage.yml"})
    routes = {
        "https://api.openalex.org/works/doi:10.1234/x": FakeResponse(429, {}),
    }
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client(routes, max_retries=1))

    result = runner.invoke(app, ["literature", "fetch", "--all"])

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["complete"] is False
    assert report["errors"]


# --- 7: RegistryError -> exit 1, no traceback -----------------------------------


def test_fetch_registry_error_exits_1_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, {"registry": "does-not-exist.json", "triage": "triage.yml"})
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())

    result = runner.invoke(app, ["literature", "fetch", "--all"])

    assert result.exit_code == 1
    assert "Traceback" not in (result.stdout + result.stderr)
    assert "registry not found" in result.stderr


def test_verify_registry_error_exits_1_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, {"registry": "does-not-exist.json"})

    result = runner.invoke(app, ["literature", "verify", "--all"])

    assert result.exit_code == 1
    assert "Traceback" not in (result.stdout + result.stderr)
    assert "registry not found" in result.stderr


def test_confirm_registry_error_exits_1_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, {"registry": "does-not-exist.json"})
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())

    result = runner.invoke(app, ["literature", "confirm", "k1", "--sha256", "ab" * 32])

    assert result.exit_code == 1
    assert "Traceback" not in (result.stdout + result.stderr)


# --- 8: verify --------------------------------------------------------------


def test_verify_corrupt_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    blob = _lit_cache_dir(tmp_path) / "sha256" / PDF_SHA
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"not the recorded bytes")
    _write_registry(tmp_path / "references.json", [_item("k1", spine=_spine(PDF_SHA))])
    _write_config(tmp_path, {"registry": "references.json"})

    result = runner.invoke(app, ["literature", "verify", "k1"])

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["corrupt"]
    assert report["ok"] is False


def test_verify_all_clean_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    sha = _seed_blob(tmp_path)
    _write_registry(tmp_path / "references.json", [_item("k1", spine=_spine(sha))])
    _write_config(tmp_path, {"registry": "references.json"})

    result = runner.invoke(app, ["literature", "verify", "--all"])

    assert result.exit_code == 0
    reports = json.loads(result.stdout)
    assert reports[0]["ok"] is True
    assert reports[0]["verified"]


def test_verify_unknown_citekey_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_registry(tmp_path / "references.json", [_item("k1")])
    _write_config(tmp_path, {"registry": "references.json"})

    result = runner.invoke(app, ["literature", "verify", "nope"])

    assert result.exit_code == 1
    assert "nope" in result.stderr


# --- 9/10/forward-item-3: mirror -----------------------------------------------


def test_mirror_missing_config_exits_1_naming_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, {"registry": "references.json"})

    result = runner.invoke(app, ["literature", "mirror", "--all"])

    assert result.exit_code == 1
    assert "literature.mirror" in result.stderr


def test_mirror_check_absent_key_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_registry(tmp_path / "references.json", [_item("k1", spine=_spine(PDF_SHA))])
    _write_config(
        tmp_path, {"registry": "references.json", "mirror": {"remote": "papers"}}
    )
    monkeypatch.setattr(
        cli, "_lit_mirror", lambda _lit: Mirror(remote="papers", run=_run_absent)
    )

    result = runner.invoke(app, ["literature", "mirror", "k1", "--check"])

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["missing"]
    assert report["corrupt"] == []


def test_mirror_distinguishes_corrupt_from_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Forward item #3: a bit-rotted local blob is `corrupt`, not `missing`."""
    monkeypatch.chdir(tmp_path)
    blob = _lit_cache_dir(tmp_path) / "sha256" / PDF_SHA
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"bit rot, not the recorded bytes")
    _write_registry(tmp_path / "references.json", [_item("k1", spine=_spine(PDF_SHA))])
    _write_config(
        tmp_path, {"registry": "references.json", "mirror": {"remote": "papers"}}
    )
    monkeypatch.setattr(
        cli, "_lit_mirror", lambda _lit: Mirror(remote="papers", run=_run_absent)
    )

    result = runner.invoke(app, ["literature", "mirror", "k1"])

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["corrupt"] == [PDF_SHA]
    assert report["missing"] == []


def test_mirror_pushes_a_clean_local_blob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_blob(tmp_path)
    _write_registry(tmp_path / "references.json", [_item("k1", spine=_spine(PDF_SHA))])
    _write_config(
        tmp_path, {"registry": "references.json", "mirror": {"remote": "papers"}}
    )
    monkeypatch.setattr(
        cli,
        "_lit_mirror",
        lambda _lit: Mirror(remote="papers", run=_run_fail_then_ok()),
    )

    result = runner.invoke(app, ["literature", "mirror", "k1"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["pushed"] == [PDF_SHA]


def _run_fail_then_ok() -> Any:
    """``lsf`` (check) fails, so the entry isn't already present; ``copyto`` succeeds."""

    def _run(args: list[str], **_kw: Any) -> _Proc:
        return _Proc(ABSENT if "lsf" in args else 0)

    return _run


def test_mirror_all_reports_already_present_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_registry(tmp_path / "references.json", [_item("k1", spine=_spine(PDF_SHA))])
    _write_config(
        tmp_path, {"registry": "references.json", "mirror": {"remote": "papers"}}
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli, "_lit_mirror", lambda _lit: Mirror(remote="papers", run=_run_ok)
    )

    result = runner.invoke(app, ["literature", "mirror", "--all"])

    assert result.exit_code == 0
    reports = json.loads(result.stdout)
    assert reports[0]["already_present"] == [PDF_SHA]


def test_mirror_unknown_citekey_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_registry(tmp_path / "references.json", [_item("k1")])
    _write_config(
        tmp_path, {"registry": "references.json", "mirror": {"remote": "papers"}}
    )
    monkeypatch.setattr(
        cli, "_lit_mirror", lambda _lit: Mirror(remote="papers", run=_run_ok)
    )

    result = runner.invoke(app, ["literature", "mirror", "nope"])

    assert result.exit_code == 1
    assert "nope" in result.stderr


# --- forward item #1: a missing rclone escapes uncaught, needs a CLI guard ----


def test_fetch_all_missing_rclone_exits_1_with_actionable_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify a missing rclone binary produces a clean exit, not a traceback.

    A recorded-but-uncached entry falls through to `Mirror.get`, which raises
    `RetrievalError` uncaught out of `acquire_one`/`fetch_all` when rclone is
    missing (Task 10's forward note). The CLI must not let that surface as a
    traceback.
    """
    monkeypatch.chdir(tmp_path)
    # Recorded checksum, but no local blob -- forces a mirror resolution attempt.
    _write_registry(tmp_path / "references.json", [_item("k1", spine=_spine(PDF_SHA))])
    _write_config(
        tmp_path, {"registry": "references.json", "mirror": {"remote": "papers"}}
    )
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())
    monkeypatch.setattr(
        cli,
        "_lit_mirror",
        lambda _lit: Mirror(remote="papers", run=_run_missing_rclone),
    )

    result = runner.invoke(app, ["literature", "fetch", "k1"])

    assert result.exit_code == 1
    assert "rclone not found on PATH" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)


def test_fetch_an_unreachable_mirror_is_an_error_row_and_a_non_zero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: a failing rclone cannot produce a `manual` worklist row.

    The whole point of the fix, asserted where a researcher would see it: an
    expired credential must not come back as ``complete: true``, exit 0, and a
    line telling them to go and download the paper by hand.
    """
    monkeypatch.chdir(tmp_path)
    # Recorded checksum, no local blob — the mirror is the only place to look.
    _write_registry(tmp_path / "references.json", [_item("k1", spine=_spine(PDF_SHA))])
    _write_config(
        tmp_path, {"registry": "references.json", "mirror": {"remote": "papers"}}
    )
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())
    monkeypatch.setattr(
        cli,
        "_lit_mirror",
        lambda _lit: Mirror(remote="papers", run=_run_unreachable),
    )

    result = runner.invoke(app, ["literature", "fetch", "k1"])

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["manual"] == []
    assert len(report["errors"]) == 1
    error = report["errors"][0]["error"]
    assert "could not be reached" in error
    assert "the token has expired" in error
    assert "Traceback" not in (result.stdout + result.stderr)


def test_mirror_check_does_not_report_missing_for_an_unreachable_mirror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``literature mirror --check`` reports nothing rather than "not present"."""
    monkeypatch.chdir(tmp_path)
    _write_registry(tmp_path / "references.json", [_item("k1", spine=_spine(PDF_SHA))])
    _write_config(
        tmp_path, {"registry": "references.json", "mirror": {"remote": "papers"}}
    )
    monkeypatch.setattr(
        cli, "_lit_mirror", lambda _lit: Mirror(remote="papers", run=_run_unreachable)
    )

    result = runner.invoke(app, ["literature", "mirror", "k1", "--check"])

    assert result.exit_code == 1
    assert "could not be reached" in result.stderr
    assert result.stdout.strip() == ""
    assert "Traceback" not in (result.stdout + result.stderr)


def test_mirror_missing_rclone_exits_1_with_actionable_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_registry(tmp_path / "references.json", [_item("k1", spine=_spine(PDF_SHA))])
    _write_config(
        tmp_path, {"registry": "references.json", "mirror": {"remote": "papers"}}
    )
    monkeypatch.setattr(
        cli,
        "_lit_mirror",
        lambda _lit: Mirror(remote="papers", run=_run_missing_rclone),
    )

    result = runner.invoke(app, ["literature", "mirror", "--all"])

    assert result.exit_code == 1
    assert "rclone not found on PATH" in result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)


# --- forward item #2: fetch_all's own errors[] row for an excluded citekey ---


def test_fetch_explicit_citekey_excluded_by_disposition_is_an_error_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    sha = _seed_blob(tmp_path)
    _write_registry(tmp_path / "references.json", [_item("k1", spine=_spine(sha))])
    (tmp_path / "triage.yml").write_text(
        "k1:\n  disposition: inbox\n", encoding="utf-8"
    )
    _write_config(tmp_path, {"registry": "references.json", "triage": "triage.yml"})
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())

    result = runner.invoke(
        app, ["literature", "fetch", "k1", "--disposition", "acted-on"]
    )

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["errors"][0]["citekey"] == "k1"
    assert "excluded by disposition" in report["errors"][0]["error"]


# --- confirm: promotion and adoption -------------------------------------------


def _quarantine(tmp_path: Path, citekey: str, body: bytes = PDF) -> str:
    sha = hashlib.sha256(body).hexdigest()
    directory = _lit_cache_dir(tmp_path) / "quarantine" / citekey
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{sha}.pdf").write_bytes(body)
    (directory / f"{sha}.json").write_text(
        json.dumps(
            {
                "candidate": {
                    "url": "http://x/p.pdf",
                    "rung": "sibling-version",
                    "title": "A Title",
                    "year": 2020,
                    "first_author_family": "Smith",
                    "openalex": None,
                    "license": None,
                },
                "match": {
                    "verdict": "quarantine",
                    "title": "exact",
                    "author": "exact",
                    "year": "within-5",
                    "reason": "plausibly a preprint",
                },
                "url": "http://x/p.pdf",
                "rung": "sibling-version",
            }
        ),
        encoding="utf-8",
    )
    return sha


def test_confirm_sha256_promotes_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    sha = _quarantine(tmp_path, "k1")
    _write_registry(tmp_path / "references.json", [_item("k1")])
    _write_config(tmp_path, {"registry": "references.json", "triage": "triage.yml"})
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())

    result = runner.invoke(app, ["literature", "confirm", "k1", "--sha256", sha])

    assert result.exit_code == 0
    outcome = json.loads(result.stdout)
    assert outcome["bucket"] == a.BUCKET_FETCHED
    assert outcome["sha256"] == sha


def test_confirm_sha256_unknown_checksum_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_registry(tmp_path / "references.json", [_item("k1")])
    _write_config(tmp_path, {"registry": "references.json"})
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())

    result = runner.invoke(app, ["literature", "confirm", "k1", "--sha256", "ab" * 32])

    assert result.exit_code == 1
    assert "Traceback" not in (result.stdout + result.stderr)


def test_confirm_sha256_tampered_quarantine_is_a_bucket_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    sha = _quarantine(tmp_path, "k1")
    pdf_path = _lit_cache_dir(tmp_path) / "quarantine" / "k1" / f"{sha}.pdf"
    pdf_path.write_bytes(b"tampered bytes")
    _write_registry(tmp_path / "references.json", [_item("k1")])
    _write_config(tmp_path, {"registry": "references.json"})
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())

    result = runner.invoke(app, ["literature", "confirm", "k1", "--sha256", sha])

    assert result.exit_code == 1
    outcome = json.loads(result.stdout)
    assert outcome["bucket"] == a.BUCKET_ERROR


def test_confirm_file_adopts_a_manual_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    downloaded = tmp_path / "downloads" / "paper.pdf"
    downloaded.parent.mkdir(parents=True)
    downloaded.write_bytes(PDF)
    _write_registry(tmp_path / "references.json", [_item("k1")])
    _write_config(tmp_path, {"registry": "references.json"})
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())

    result = runner.invoke(
        app, ["literature", "confirm", "k1", "--file", str(downloaded)]
    )

    assert result.exit_code == 0
    outcome = json.loads(result.stdout)
    assert outcome["bucket"] == a.BUCKET_FETCHED
    assert outcome["rung"] == a.RUNG_MANUAL
    # `--file` copies; the researcher's own file must still be there.
    assert downloaded.is_file()


def test_confirm_file_missing_path_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_registry(tmp_path / "references.json", [_item("k1")])
    _write_config(tmp_path, {"registry": "references.json"})
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())

    result = runner.invoke(
        app, ["literature", "confirm", "k1", "--file", "no-such-file.pdf"]
    )

    assert result.exit_code == 1
    assert "Traceback" not in (result.stdout + result.stderr)


def test_confirm_file_non_pdf_is_a_bucket_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    junk = tmp_path / "not-a-pdf.pdf"
    junk.write_bytes(b"just text")
    _write_registry(tmp_path / "references.json", [_item("k1")])
    _write_config(tmp_path, {"registry": "references.json"})
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())

    result = runner.invoke(app, ["literature", "confirm", "k1", "--file", str(junk)])

    assert result.exit_code == 1
    outcome = json.loads(result.stdout)
    assert outcome["bucket"] == a.BUCKET_ERROR


def test_confirm_unknown_citekey_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_registry(tmp_path / "references.json", [_item("k1")])
    _write_config(tmp_path, {"registry": "references.json"})
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())

    result = runner.invoke(
        app, ["literature", "confirm", "nope", "--sha256", "ab" * 32]
    )

    assert result.exit_code == 1
    assert "nope" in result.stderr


# --- 11: config plumbing --------------------------------------------------------


def test_lit_context_defaults_with_no_literature_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())

    ctx = cli._lit_context()

    # The default bibliography paths come from the layout, not a second copy of
    # "docs/research/literature/..." held in the CLI (#122).
    layout = Layout.default(tmp_path.resolve())
    assert ctx.registry_path == layout.references
    assert ctx.triage_path == layout.triage
    assert ctx.max_bytes == cli._DEFAULT_MAX_BYTES
    assert ctx.resolvers == []
    assert ctx.mirror is None


def test_lit_context_reads_configured_paths_and_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())
    resolvers = [{"match": "Neural", "url_template": "http://v/{doi}.pdf"}]
    _write_config(
        tmp_path,
        {
            "registry": "mylit/refs.json",
            "triage": "mylit/triage.yml",
            "acquisition": {"max_bytes": 1234, "venue_resolvers": resolvers},
        },
    )

    ctx = cli._lit_context()

    assert ctx.registry_path == Path("mylit/refs.json")
    assert ctx.triage_path == Path("mylit/triage.yml")
    assert ctx.max_bytes == 1234
    assert ctx.resolvers == resolvers


def test_lit_context_reads_configured_mirror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client())
    _write_config(tmp_path, {"mirror": {"remote": "papers", "base_path": "lit"}})

    ctx = cli._lit_context()

    assert ctx.mirror is not None
    assert ctx.mirror.remote == "papers"
    assert ctx.mirror.base_path == "lit"


def test_literature_block_rejects_non_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, "just-a-string")

    with pytest.raises(typer.Exit) as exc:
        cli._lit_context()
    assert exc.value.exit_code == 1


@pytest.mark.parametrize("value", [123, ["nope"]])
def test_lit_registry_path_must_be_a_string(
    value: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, {"registry": value})

    with pytest.raises(typer.Exit) as exc:
        cli._lit_context()
    assert exc.value.exit_code == 1


@pytest.mark.parametrize(
    "acquisition",
    [
        "not-a-mapping",
        {"max_bytes": "big"},
        {"max_bytes": True},
        {"venue_resolvers": "not-a-list"},
    ],
)
def test_lit_acquisition_rejects_bad_shapes(
    acquisition: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, {"acquisition": acquisition})

    with pytest.raises(typer.Exit) as exc:
        cli._lit_context()
    assert exc.value.exit_code == 1


@pytest.mark.parametrize(
    "mirror_cfg",
    ["not-a-mapping", {}, {"remote": ""}, {"remote": "papers", "base_path": 5}],
)
def test_lit_mirror_rejects_bad_shapes(
    mirror_cfg: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, {"mirror": mirror_cfg})

    with pytest.raises(typer.Exit) as exc:
        cli._lit_context()
    assert exc.value.exit_code == 1


# --- 8: a PDF host throttle aborts the sweep, end to end ------------------------
#
# The metadata-layer version of this is test 6 above. This is the byte-layer
# twin: the ladder found a URL, the *PDF host* said 429, and the command must not
# print a `manual` worklist with exit 0.


def test_fetch_all_byte_layer_throttle_exits_1_and_buckets_nothing_manual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_registry(tmp_path / "references.json", [_item("k1")])
    _write_config(tmp_path, {"registry": "references.json", "triage": "triage.yml"})
    work = {
        "id": "https://openalex.org/W1",
        "display_name": "A Title",
        "publication_year": 2020,
        "authorships": [{"author": {"display_name": "A Smith"}}],
        "open_access": {"is_oa": True},
        "best_oa_location": {"pdf_url": "http://arxiv.org/pdf/1234", "license": None},
        "locations": [
            {
                "landing_page_url": None,
                "pdf_url": "http://arxiv.org/pdf/1234",
                "license": None,
            }
        ],
        "primary_location": {"source": None},
        "ids": {},
        "doi": None,
    }
    routes = {
        "https://api.openalex.org/works/doi:10.1234/x": work,
        "https://api.openalex.org/works/W1": work,
    }
    monkeypatch.setattr(cli, "_lit_client", lambda: _fake_client(routes))

    def throttled(url: str, dest: Path, max_bytes: int) -> Any:
        raise DownloadError(f"{url}: HTTP 429", status=429, retry_after=60)

    monkeypatch.setattr(cli, "stream_to_file", throttled)

    result = runner.invoke(app, ["literature", "fetch", "--all"])

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["complete"] is False
    assert report["manual"] == []
    assert "HTTP 429" in report["errors"][0]["error"]
    assert "Traceback" not in (result.stdout + result.stderr)
