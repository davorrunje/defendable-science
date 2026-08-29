"""Tests for the CLI-owned API-key store and the ``keys`` command group (#42, #66).

Deterministic throughout: the store path is a ``tmp_path`` (module tests) or the
CLI's cwd via ``monkeypatch.chdir``; the environment is driven with
``monkeypatch``; stdin is fed via ``CliRunner(input=...)``. No test ever asserts a
secret *value* appears in output — only presence/absence and source. The
``tests/conftest.py`` autouse fixture points ``HOME``/``XDG_CONFIG_HOME`` at a
throwaway directory for every test, so the new out-of-repo default store path
(ADR-0032) never touches a real developer's home directory.
"""

from __future__ import annotations

import json
import re
import stat
import subprocess
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from defendable_science import cli
from defendable_science.cli import app
from defendable_science.core import keys as keys_mod

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


# --- registry ---------------------------------------------------------------


def test_is_known_registry_rclone_and_unknown() -> None:
    assert keys_mod.is_known("S2_API_KEY") is True
    assert keys_mod.is_known("RCLONE_CONFIG_STORE_TYPE") is True
    assert keys_mod.is_known("MYSTERY") is False


# --- store round-trip + permissions -----------------------------------------


def test_store_path_default_and_override(tmp_path: Path) -> None:
    assert keys_mod.store_path() == keys_mod.default_store_path()
    override = tmp_path / "k.json"
    assert keys_mod.store_path(override) == override


# --- default store location: XDG, outside the repo (defendable-science#66) ------


def test_xdg_config_home_uses_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    xdg = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    assert keys_mod.xdg_config_home() == xdg


def test_xdg_config_home_falls_back_to_dot_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert keys_mod.xdg_config_home() == tmp_path / ".config"


def test_default_store_path_is_xdg_defendable_science_keys_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    xdg = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    assert keys_mod.default_store_path() == xdg / "defendable-science" / "keys.json"


def test_store_path_env_override_wins_over_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    in_repo = tmp_path / ".defendable-science" / "keys.json"
    monkeypatch.setenv(keys_mod.STORE_PATH_ENV, str(in_repo))
    assert keys_mod.store_path() == in_repo


def test_store_path_explicit_arg_wins_over_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(keys_mod.STORE_PATH_ENV, str(tmp_path / "env.json"))
    explicit = tmp_path / "explicit.json"
    assert keys_mod.store_path(explicit) == explicit


def test_missing_store_is_empty(tmp_path: Path) -> None:
    assert keys_mod.load_store(tmp_path / "absent.json") == {}


def test_set_creates_parent_and_0600(tmp_path: Path) -> None:
    store = tmp_path / "nested" / "keys.json"
    keys_mod.set_key("S2_API_KEY", "fake-s2-key", store)
    assert keys_mod.load_store(store) == {
        "S2_API_KEY": "fake-s2-key"  # pragma: allowlist secret
    }
    assert stat.S_IMODE(store.stat().st_mode) == 0o600


def test_load_store_rejects_bad_json(tmp_path: Path) -> None:
    store = tmp_path / "keys.json"
    store.write_text("{not json", encoding="utf-8")
    pattern = rf"{re.escape(str(store))}: invalid JSON"
    with pytest.raises(ValueError, match=pattern):
        keys_mod.load_store(store)


def test_load_store_rejects_non_object(tmp_path: Path) -> None:
    store = tmp_path / "keys.json"
    store.write_text("[1, 2, 3]", encoding="utf-8")
    pattern = rf"{re.escape(str(store))}: <root>: Input should be an object"
    with pytest.raises(ValueError, match=pattern):
        keys_mod.load_store(store)


def test_load_store_rejects_non_string_value(tmp_path: Path) -> None:
    store = tmp_path / "keys.json"
    store.write_text('{"S2_API_KEY": 5}', encoding="utf-8")
    pattern = rf"{re.escape(str(store))}: S2_API_KEY: Input should be a valid string"
    with pytest.raises(ValueError, match=pattern):
        keys_mod.load_store(store)


def test_unset_present_and_absent(tmp_path: Path) -> None:
    store = tmp_path / "keys.json"
    keys_mod.set_key("S2_API_KEY", "secret", store)
    assert keys_mod.unset_key("S2_API_KEY", store) is True
    assert keys_mod.load_store(store) == {}
    assert keys_mod.unset_key("S2_API_KEY", store) is False


# --- precedence: os.environ > store > None ----------------------------------


def test_get_precedence(tmp_path: Path) -> None:
    store = tmp_path / "keys.json"
    keys_mod.set_key("S2_API_KEY", "from-store", store)
    # store wins over unset environment
    assert keys_mod.get("S2_API_KEY", path=store, environ={}) == "from-store"
    # a present env var always wins
    assert (
        keys_mod.get(
            "S2_API_KEY",
            path=store,
            environ={"S2_API_KEY": "from-env"},  # pragma: allowlist secret
        )
        == "from-env"
    )
    # unset everywhere
    assert keys_mod.get("OPENALEX_MAILTO", path=store, environ={}) is None


def test_get_defaults_to_os_environ(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # default store path is absent under a fresh cwd
    monkeypatch.setenv("S2_API_KEY", "env-default")
    assert keys_mod.get("S2_API_KEY") == "env-default"


def test_source_of(tmp_path: Path) -> None:
    store = tmp_path / "keys.json"
    keys_mod.set_key("S2_API_KEY", "s", store)
    assert keys_mod.source_of("S2_API_KEY", path=store, environ={}) == "store"
    assert (
        keys_mod.source_of("S2_API_KEY", path=store, environ={"S2_API_KEY": "e"})
        == "env"
    )
    assert keys_mod.source_of("OPENALEX_MAILTO", path=store, environ={}) is None


# --- scoped env (least privilege) -------------------------------------------


def test_scoped_env_only_present_requested(tmp_path: Path) -> None:
    store = tmp_path / "keys.json"
    keys_mod.set_key("S2_API_KEY", "s", store)
    keys_mod.set_key("OPENALEX_MAILTO", "m", store)
    scoped = keys_mod.scoped_env(
        ["S2_API_KEY", "OPENALEX_MAILTO", "MISSING"], path=store, environ={}
    )
    assert scoped == {"S2_API_KEY": "s", "OPENALEX_MAILTO": "m"}
    assert "MISSING" not in scoped


def test_rclone_config_env_translation() -> None:
    env = keys_mod.rclone_config_env("myremote", {"type": "s3", "access_key_id": "AK"})
    assert env == {
        "RCLONE_CONFIG_MYREMOTE_TYPE": "s3",
        "RCLONE_CONFIG_MYREMOTE_ACCESS_KEY_ID": "AK",
    }


def test_rclone_scoped_env_is_per_remote(tmp_path: Path) -> None:
    store = tmp_path / "keys.json"
    keys_mod.set_key("RCLONE_CONFIG_STORE_TYPE", "s3", store)
    keys_mod.set_key(
        "RCLONE_CONFIG_STORE_SECRET_ACCESS_KEY",  # pragma: allowlist secret
        "fake-mirror-secret",
        store,
    )
    keys_mod.set_key("RCLONE_CONFIG_OTHER_TYPE", "sftp", store)
    scoped = keys_mod.rclone_scoped_env("store", path=store, environ={})
    assert scoped == {
        "RCLONE_CONFIG_STORE_TYPE": "s3",
        "RCLONE_CONFIG_STORE_SECRET_ACCESS_KEY": (  # pragma: allowlist secret
            "fake-mirror-secret"
        ),
    }
    # a var supplied only via the environment is picked up too
    scoped_env_only = keys_mod.rclone_scoped_env(
        "store",
        path=store,
        environ={"RCLONE_CONFIG_STORE_TOKEN": "fake-token"},  # pragma: allowlist secret
    )
    assert scoped_env_only["RCLONE_CONFIG_STORE_TOKEN"] == "fake-token"


# --- guardrail: committable in-repo store (defendable-science#66) ---------------


def _fake_run(returncode: int) -> keys_mod.GitRunner:
    """Build a fake ``git`` runner that always returns `returncode`."""

    def _run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=returncode)

    return _run


def _raising_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
    raise FileNotFoundError("git not found")


def test_git_root_for_finds_ancestor_dot_git(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "a" / "b" / "keys.json"
    assert keys_mod._git_root_for(nested) == tmp_path.resolve()


def test_git_root_for_none_outside_a_work_tree(tmp_path: Path) -> None:
    assert keys_mod._git_root_for(tmp_path / "keys.json") is None


def test_is_gitignored_true_false_and_inconclusive() -> None:
    assert keys_mod.is_gitignored("x", run=_fake_run(0)) is True
    assert keys_mod.is_gitignored("x", run=_fake_run(1)) is False
    assert keys_mod.is_gitignored("x", run=_fake_run(128)) is None


def test_is_gitignored_none_when_git_binary_missing() -> None:
    assert keys_mod.is_gitignored("x", run=_raising_run) is None


def test_store_at_risk_false_outside_a_work_tree(tmp_path: Path) -> None:
    assert keys_mod.store_at_risk(tmp_path / "keys.json", run=_fake_run(0)) is False


def test_store_at_risk_false_when_confirmed_ignored(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    path = tmp_path / ".defendable-science" / "keys.json"
    assert keys_mod.store_at_risk(path, run=_fake_run(0)) is False


def test_store_at_risk_true_when_not_ignored(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    path = tmp_path / ".defendable-science" / "keys.json"
    assert keys_mod.store_at_risk(path, run=_fake_run(1)) is True


def test_store_at_risk_true_when_inconclusive(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    path = tmp_path / ".defendable-science" / "keys.json"
    assert keys_mod.store_at_risk(path, run=_fake_run(128)) is True


def test_store_at_risk_runs_git_in_the_repo_root(tmp_path: Path) -> None:
    # Regression guard: `git check-ignore` must run in the *target* repo's
    # root, not the caller's actual cwd, or the check silently uses the wrong
    # repository when `keys set` is invoked from elsewhere.
    (tmp_path / ".git").mkdir()
    path = tmp_path / "nested" / ".defendable-science" / "keys.json"
    seen: dict[str, object] = {}

    def _run(*args: object, **kwargs: object) -> SimpleNamespace:
        seen["cwd"] = kwargs.get("cwd")
        return SimpleNamespace(returncode=0)

    keys_mod.store_at_risk(path, run=_run)
    assert seen["cwd"] == str(tmp_path.resolve())


def test_store_at_risk_real_git_matches_check_ignore(tmp_path: Path) -> None:
    """End-to-end with the real ``git`` binary — the issue's own reproduction."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # nosec B603 B607
    path = tmp_path / ".defendable-science" / "keys.json"
    # not yet gitignored -> committable
    assert keys_mod.store_at_risk(path) is True
    (tmp_path / ".gitignore").write_text(
        ".defendable-science/keys.json\n", encoding="utf-8"
    )
    # gitignored -> no longer at risk
    assert keys_mod.store_at_risk(path) is False


# --- keys CLI group ---------------------------------------------------------


def test_set_single_via_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["keys", "set", "S2_API_KEY"], input="fake-s2-key\n")
    assert result.exit_code == 0
    assert "fake-s2-key" not in result.stdout  # never echoes the value
    assert keys_mod.load_store() == {
        "S2_API_KEY": "fake-s2-key"  # pragma: allowlist secret
    }
    # the default (out-of-repo) store never triggers the committable warning
    assert "committable" not in result.stderr


def test_set_warns_when_resolved_store_is_committable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(keys_mod, "store_at_risk", lambda *_a, **_k: True)
    result = runner.invoke(app, ["keys", "set", "S2_API_KEY"], input="v\n")
    assert result.exit_code == 0
    assert "committable" in result.stderr
    assert keys_mod.STORE_PATH_ENV in result.stderr
    # still stores the value — this is a warning, never a refusal
    assert keys_mod.load_store() == {"S2_API_KEY": "v"}


def test_set_many_warns_when_resolved_store_is_committable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(keys_mod, "store_at_risk", lambda *_a, **_k: True)
    blob = json.dumps({"S2_API_KEY": "a"})
    result = runner.invoke(app, ["keys", "set"], input=blob)
    assert result.exit_code == 0
    assert "committable" in result.stderr
    assert keys_mod.load_store() == {"S2_API_KEY": "a"}


def test_set_numeric_value_is_not_treated_as_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # "12345" is valid JSON but not an object → stored as a single value.
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["keys", "set", "S2_API_KEY"], input="12345")
    assert result.exit_code == 0
    assert keys_mod.load_store() == {"S2_API_KEY": "12345"}


def test_set_json_blob_sets_many(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    blob = json.dumps({"S2_API_KEY": "a", "OPENALEX_MAILTO": "me@x.org"})
    result = runner.invoke(app, ["keys", "set"], input=blob)
    assert result.exit_code == 0
    assert "a" not in result.stdout.split()  # no value echoed
    assert keys_mod.load_store() == {"S2_API_KEY": "a", "OPENALEX_MAILTO": "me@x.org"}


def test_set_json_blob_empty_object_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["keys", "set"], input="{}")
    assert result.exit_code == 2
    assert "empty" in result.stderr


def test_set_json_blob_non_string_value_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["keys", "set"], input='{"S2_API_KEY": 5}')
    assert result.exit_code == 2
    assert "must be a string" in result.stderr


def test_set_unknown_name_warns_but_stores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["keys", "set", "MYSTERY_KEY"], input="v\n")
    assert result.exit_code == 0
    assert "not a known key" in result.stderr
    assert keys_mod.load_store() == {"MYSTERY_KEY": "v"}


def test_set_missing_name_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    # A bare token (not a JSON object) piped with no NAME argument.
    result = runner.invoke(app, ["keys", "set"], input="loose-token\n")
    assert result.exit_code == 2
    assert "provide NAME" in result.stderr


def test_set_empty_value_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["keys", "set", "S2_API_KEY"], input="   \n")
    assert result.exit_code == 2
    assert "empty value" in result.stderr


def test_set_interactive_uses_hidden_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_stdin_is_piped", lambda: False)
    monkeypatch.setattr(
        "defendable_science.cli.getpass.getpass", lambda prompt: "fake-typed-value"
    )
    result = runner.invoke(app, ["keys", "set", "S2_API_KEY"])
    assert result.exit_code == 0
    assert "fake-typed-value" not in result.stdout
    assert keys_mod.load_store() == {
        "S2_API_KEY": "fake-typed-value"  # pragma: allowlist secret
    }


def test_set_interactive_missing_name_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_stdin_is_piped", lambda: False)

    def _never(prompt: str) -> str:  # pragma: no cover - must not be called
        raise AssertionError("getpass must not run without a name")

    monkeypatch.setattr("defendable_science.cli.getpass.getpass", _never)
    result = runner.invoke(app, ["keys", "set"])
    assert result.exit_code == 2
    assert "provide NAME" in result.stderr


def test_list_reports_presence_and_source_not_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    keys_mod.set_key("S2_API_KEY", "topsecret")
    keys_mod.set_key("RCLONE_CONFIG_STORE_TOKEN", "mirror-cred")
    result = runner.invoke(app, ["keys", "list"])
    assert result.exit_code == 0
    assert "topsecret" not in result.stdout
    assert "mirror-cred" not in result.stdout
    rows = {row["name"]: row for row in json.loads(result.stdout)}
    assert rows["S2_API_KEY"]["present"] is True
    assert rows["S2_API_KEY"]["source"] == "store"
    assert "how_to_obtain" in rows["S2_API_KEY"]
    # an unset known key is reported absent
    assert rows["OPENALEX_MAILTO"]["present"] is False
    assert rows["OPENALEX_MAILTO"]["source"] is None
    # the stored rclone credential shows up as an extra, metadata-less row
    assert rows["RCLONE_CONFIG_STORE_TOKEN"]["present"] is True
    assert rows["RCLONE_CONFIG_STORE_TOKEN"]["service"] is None


def test_check_env_source_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    keys_mod.set_key("S2_API_KEY", "from-store")
    monkeypatch.setenv("S2_API_KEY", "from-env")
    result = runner.invoke(app, ["keys", "check"])
    assert result.exit_code == 0
    assert "from-store" not in result.stdout
    assert "from-env" not in result.stdout
    rows = {row["name"]: row for row in json.loads(result.stdout)}
    assert rows["S2_API_KEY"] == {
        "name": "S2_API_KEY",
        "present": True,
        "source": "env",
    }


def test_unset_present_then_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    keys_mod.set_key("S2_API_KEY", "s")
    ok = runner.invoke(app, ["keys", "unset", "S2_API_KEY"])
    assert ok.exit_code == 0
    assert "unset S2_API_KEY" in ok.stdout
    again = runner.invoke(app, ["keys", "unset", "S2_API_KEY"])
    assert again.exit_code == 0
    assert "was not in the store" in again.stderr


def test_path_prints_store_path() -> None:
    result = runner.invoke(app, ["keys", "path"])
    assert result.exit_code == 0
    assert result.stdout.strip() == str(keys_mod.default_store_path())


def test_path_prints_in_repo_override_when_opted_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    in_repo = tmp_path / ".defendable-science" / "keys.json"
    monkeypatch.setenv(keys_mod.STORE_PATH_ENV, str(in_repo))
    result = runner.invoke(app, ["keys", "path"])
    assert result.exit_code == 0
    assert result.stdout.strip() == str(in_repo)


# --- integration: doctor + _lit_client --------------------------------------


def test_doctor_reports_key_presence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    keys_mod.set_key("S2_API_KEY", "s")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "S2_API_KEY: set (source: store)" in result.stdout
    assert "OPENALEX_MAILTO: not set" in result.stdout


def test_lit_client_sources_s2_key_from_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("S2_API_KEY", raising=False)
    keys_mod.set_key("S2_API_KEY", "store-key")
    client = cli._lit_client()
    assert client.s2_key == "store-key"
