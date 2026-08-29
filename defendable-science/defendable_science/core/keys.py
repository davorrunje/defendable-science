"""CLI-owned API-key store (ADR-0029, ADR-0032).

A single, controlled place to store, read and check the service keys the tooling
uses — Semantic Scholar (``S2_API_KEY``), the OpenAlex polite pool
(``OPENALEX_MAILTO``) and private rclone-mirror credentials — without leaking a
secret through shell history, ``argv`` or an over-broad always-present file.

Design (ADR-0029, ADR-0032):

- **Store location.** A JSON object ``{name: value}`` at an **XDG config
  location outside the repo** — ``$XDG_CONFIG_HOME/defendable-science/keys.json``,
  falling back to ``~/.config/defendable-science/keys.json`` — created ``0600``, so a
  stored secret can never be committed to a consumer repo's work tree
  (ADR-0032). :envvar:`STORE_PATH_ENV` (``DEFENDABLE_SCIENCE_KEYS_PATH``) is an
  explicit opt-in override, e.g. to restore the legacy in-repo location at
  :data:`IN_REPO_STORE_PATH` (``.defendable-science/keys.json``, which
  ``research-init`` still gitignores for anyone who opts in). JSON (not
  ``.env``) because the CLI is the sole reader/writer. Per-key *metadata*
  (service, how-to-obtain link, rate-limit benefit) lives in the
  :data:`KNOWN_KEYS` registry — the single source of truth — rather than being
  duplicated into every stored record.
- **Precedence.** :func:`get` resolves ``os.environ`` **>** the store **>**
  ``None``, so an injected environment variable always wins (CI / secrets
  injection) and the service degrades gracefully when a key is unset.
- **Least privilege.** :func:`scoped_env` / :func:`rclone_scoped_env` build an
  in-memory ``env`` dict holding *only* the secrets a given child process needs —
  never the whole store, never a file on the default path.
- **Guardrail.** :func:`store_at_risk` flags a resolved store path that sits
  inside a git work tree and is not confirmed gitignored — the CLI's ``keys
  set`` warns (never silently) when that is the case, defense-in-depth for
  anyone who opts into an in-repo store without gitignoring it.
- **Honesty.** The store is **plaintext at rest**. Living outside the repo (or
  being gitignored + ``0600`` when opted in) limits exposure but is *not*
  encryption; OS-keychain backing is the follow-up (#49). Nothing in this
  module logs or echoes a value.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 - used only for `git check-ignore`, fixed args
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from pydantic import ConfigDict, RootModel

from defendable_science.core.models import parse_json

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

#: Explicit override for the resolved store path (defendable-science#66) — set this
#: to opt out of the XDG default, e.g. to the legacy in-repo
#: :data:`IN_REPO_STORE_PATH`.
STORE_PATH_ENV = "DEFENDABLE_SCIENCE_KEYS_PATH"

#: The legacy in-repo store location. No longer the default (ADR-0032), but
#: still supported via :data:`STORE_PATH_ENV` and still gitignored by
#: ``research-init`` for anyone who opts in.
IN_REPO_STORE_PATH = Path(".defendable-science/keys.json")

#: Prefix for rclone remote-config credentials handed to the rclone subprocess as
#: ``RCLONE_CONFIG_<REMOTE>_<PARAM>`` environment variables (no config file).
RCLONE_ENV_PREFIX = "RCLONE_CONFIG_"


class _KeyStore(RootModel[dict[str, str]]):
    """The on-disk key store: a flat JSON object of string values."""

    # Not `OwnedModel`: a `RootModel[...]` cannot also inherit a `BaseModel`
    # subclass that supplies `model_config` — the generic root and the
    # config-carrying base collide in the MRO — so `strict=True` is repeated
    # here by hand instead of coming from `OwnedModel`. Currently harmless:
    # verified that lax mode would not have coerced e.g. an int value to
    # `str` here anyway, so `strict=True` isn't load-bearing *yet* — but a
    # future edit to `OwnedModel` (e.g. tightening `extra=...`) will not
    # automatically apply to this store.
    model_config = ConfigDict(strict=True)


@dataclass(frozen=True)
class KnownKey:
    """A documented, recognised key the tooling knows how to use.

    :param name: The environment-variable / store name (e.g. ``S2_API_KEY``).
    :param service: The service the key authenticates or identifies to.
    :param benefit: What providing it buys (a rate-limit / politeness benefit).
    :param how_to_obtain: A URL describing how to obtain the key.
    """

    name: str
    service: str
    benefit: str
    how_to_obtain: str


#: The recognised-keys registry — the single source of truth for key metadata.
KNOWN_KEYS: dict[str, KnownKey] = {
    "S2_API_KEY": KnownKey(
        name="S2_API_KEY",
        service="Semantic Scholar",
        benefit=(
            "Raises the Semantic Scholar rate limit well above the shared keyless "
            "pool, which throttles hard and stalls citation-graph lookups."
        ),
        how_to_obtain="https://www.semanticscholar.org/product/api#api-key",
    ),
    "OPENALEX_MAILTO": KnownKey(
        name="OPENALEX_MAILTO",
        service="OpenAlex",
        benefit=(
            "Joins the OpenAlex 'polite pool' (a contact email), giving faster, "
            "more reliable responses than the anonymous pool."
        ),
        how_to_obtain="https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication",
    ),
}


def is_known(name: str) -> bool:
    """Return whether `name` is a recognised key.

    Recognised means either a registry entry or an rclone remote-config variable
    (``RCLONE_CONFIG_<REMOTE>_<PARAM>``), which are accepted by convention.

    :param name: The candidate key name.
    :returns: ``True`` if the name is documented or an rclone-config variable.
    """
    return name in KNOWN_KEYS or name.startswith(RCLONE_ENV_PREFIX)


def xdg_config_home() -> Path:
    """Return the XDG config-home directory (``$XDG_CONFIG_HOME`` or ``~/.config``).

    :returns: The resolved XDG config-home directory (per the XDG Base
        Directory spec — not created; callers create it as needed).
    """
    override = os.environ.get("XDG_CONFIG_HOME")
    if override:
        return Path(override)
    return Path.home() / ".config"


def default_store_path() -> Path:
    """Return the default, out-of-the-repo store path (ADR-0032).

    :returns: ``$XDG_CONFIG_HOME/defendable-science/keys.json`` (or the
        ``~/.config`` fallback) — outside any consumer repo's work tree, so a
        stored key is never committable by default (defendable-science#66).
    """
    return xdg_config_home() / "defendable-science" / "keys.json"


def store_path(path: str | Path | None = None) -> Path:
    """Resolve the store path.

    Resolution order: an explicit `path` argument, then
    :data:`STORE_PATH_ENV` (an explicit opt-in override, e.g. to
    :data:`IN_REPO_STORE_PATH`), then the out-of-repo :func:`default_store_path`
    (ADR-0032).

    :param path: An explicit override; ``None`` consults the environment/default.
    :returns: The path the store is read from / written to.
    """
    if path is not None:
        return Path(path)
    env_override = os.environ.get(STORE_PATH_ENV)
    if env_override:
        return Path(env_override)
    return default_store_path()


def load_store(path: str | Path | None = None) -> dict[str, str]:
    """Load the key store as a ``{name: value}`` mapping.

    A missing store yields an empty mapping rather than an error, so callers can
    treat an unconfigured project as "no stored keys".

    :param path: Store path override; defaults to the resolved :func:`store_path`.
    :returns: The stored ``{name: value}`` pairs (empty if the file is absent).
    :raises ValueError: If the file exists but is not a JSON object of strings.
    """
    resolved = store_path(path)
    if not resolved.is_file():
        return {}
    return dict(
        parse_json(
            _KeyStore,
            resolved.read_text(encoding="utf-8"),
            source=str(resolved),
            error=ValueError,
        ).root
    )


def write_store(mapping: Mapping[str, str], path: str | Path | None = None) -> None:
    """Write `mapping` to the store, creating it ``0600``.

    The parent directory is created if needed; the file mode is tightened to
    owner-read/write only. Values are written verbatim (plaintext at rest — this
    is not encryption; see the module docstring).

    :param mapping: The ``{name: value}`` pairs to persist.
    :param path: Store path override; defaults to the resolved :func:`store_path`.
    """
    resolved = store_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dict(sorted(mapping.items())), indent=2) + "\n"
    resolved.write_text(payload, encoding="utf-8")
    resolved.chmod(0o600)


def set_key(name: str, value: str, path: str | Path | None = None) -> None:
    """Add or update a single key in the store.

    :param name: The key name.
    :param value: The secret value (never logged or echoed).
    :param path: Store path override; defaults to the resolved :func:`store_path`.
    """
    store = load_store(path)
    store[name] = value
    write_store(store, path)


def unset_key(name: str, path: str | Path | None = None) -> bool:
    """Remove a key from the store.

    :param name: The key name to remove.
    :param path: Store path override; defaults to the resolved :func:`store_path`.
    :returns: ``True`` if the key was present and removed, ``False`` if absent.
    """
    store = load_store(path)
    if name not in store:
        return False
    del store[name]
    write_store(store, path)
    return True


def _environ(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    """Return the environment mapping to consult (`os.environ` by default)."""
    return os.environ if environ is None else environ


def get(
    name: str,
    *,
    path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve a key value with ``os.environ`` > store > ``None`` precedence.

    :param name: The key name.
    :param path: Store path override; defaults to the resolved :func:`store_path`.
    :param environ: Environment mapping override (for tests); defaults to
        :data:`os.environ`.
    :returns: The resolved value, or ``None`` if unset in both sources.
    """
    env = _environ(environ)
    if name in env:
        return env[name]
    return load_store(path).get(name)


def source_of(
    name: str,
    *,
    path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Report *where* a key would resolve from — without exposing its value.

    :param name: The key name.
    :param path: Store path override; defaults to the resolved :func:`store_path`.
    :param environ: Environment mapping override; defaults to :data:`os.environ`.
    :returns: ``"env"`` if an environment variable would win, ``"store"`` if the
        store would supply it, or ``None`` if it is unset everywhere.
    """
    env = _environ(environ)
    if name in env:
        return "env"
    if name in load_store(path):
        return "store"
    return None


def scoped_env(
    names: Iterable[str],
    *,
    path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build a least-privilege ``env`` dict of only the requested, present keys.

    Intended for handing to a child process: it contains *only* the named
    secrets that actually resolve (via :func:`get` precedence), and nothing else
    from the store.

    :param names: The key names the job is allowed to see.
    :param path: Store path override; defaults to the resolved :func:`store_path`.
    :param environ: Environment mapping override; defaults to :data:`os.environ`.
    :returns: A ``{name: value}`` dict of the present requested secrets.
    """
    result: dict[str, str] = {}
    for name in names:
        value = get(name, path=path, environ=environ)
        if value is not None:
            result[name] = value
    return result


def rclone_config_env(remote: str, params: Mapping[str, str]) -> dict[str, str]:
    """Translate rclone remote parameters to ``RCLONE_CONFIG_<REMOTE>_<KEY>`` vars.

    rclone reads a remote's configuration from environment variables of this
    shape, so a mirror can run with no config file on disk.

    :param remote: The rclone remote name (upper-cased in the variable names).
    :param params: The remote's config parameters (e.g. ``type``, ``token``).
    :returns: The corresponding ``RCLONE_CONFIG_*`` environment mapping.
    """
    prefix = f"{RCLONE_ENV_PREFIX}{remote.upper()}_"
    return {f"{prefix}{key.upper()}": value for key, value in params.items()}


def rclone_scoped_env(
    remote: str,
    *,
    path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Collect the stored/env ``RCLONE_CONFIG_<REMOTE>_*`` credentials for `remote`.

    Only the variables scoped to this one remote are returned (least privilege),
    each resolved with :func:`get` precedence. An empty result means no
    credentials are stored for the remote (a ``rclone.conf`` may still cover it).

    :param remote: The rclone remote name.
    :param path: Store path override; defaults to the resolved :func:`store_path`.
    :param environ: Environment mapping override; defaults to :data:`os.environ`.
    :returns: A ``{RCLONE_CONFIG_<REMOTE>_<PARAM>: value}`` dict.
    """
    prefix = f"{RCLONE_ENV_PREFIX}{remote.upper()}_"
    candidates = {
        name
        for name in (*load_store(path), *_environ(environ))
        if name.startswith(prefix)
    }
    return scoped_env(sorted(candidates), path=path, environ=environ)


# --- guardrail: warn on a committable in-repo store (defendable-science#66) -----


class _GitProc(Protocol):
    """The minimal completed-process shape a git runner must return."""

    returncode: int


#: A ``git`` subprocess runner with the ``subprocess.run`` shape (injectable
#: for tests, mirroring :data:`defendable_science.core.mirror.Runner`).
GitRunner = Callable[..., _GitProc]


def _git_root_for(path: Path) -> Path | None:
    """Walk upward from `path`'s parent looking for a ``.git`` entry.

    :param path: The (needn't exist) path to check; only its ancestry matters.
    :returns: The git work-tree root directory, or ``None`` if none is found.
    """
    start = path.resolve().parent
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def is_gitignored(
    path: str | Path,
    *,
    cwd: str | Path | None = None,
    run: GitRunner = subprocess.run,
) -> bool | None:
    """Return whether `path` is covered by a gitignore rule.

    Delegates to ``git check-ignore``, the same mechanism the issue's own
    reproduction used, rather than reimplementing gitignore-pattern matching.

    :param path: The path to check.
    :param cwd: The directory to run ``git`` in — pass the target repo's root
        so the check uses *that* repository regardless of the caller's actual
        working directory; ``None`` inherits the current process's cwd.
    :param run: The subprocess runner (defaults to :func:`subprocess.run`;
        injectable so tests never need a real ``git`` binary).
    :returns: ``True``/``False`` if git could answer conclusively, or ``None``
        if git is unavailable or the answer is inconclusive (e.g. not inside a
        git repository at all).
    """
    try:
        proc = run(  # nosec B603 - fixed git args, no shell
            ["git", "check-ignore", "-q", str(path)],
            capture_output=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode in (0, 1):
        return proc.returncode == 0
    return None


def store_at_risk(path: str | Path, *, run: GitRunner = subprocess.run) -> bool:
    """Return whether `path` is a committable secret store (defendable-science#66).

    A resolved store path is "at risk" when it sits inside a git work tree and
    is not *confirmed* gitignored — including when git cannot confirm either
    way (no news is not good news for a secret). Used as the ``keys set``
    guardrail: a warning, not a refusal, since the out-of-repo default already
    keeps a fresh setup safe (ADR-0032) and this only fires for an explicit
    opt-in.

    :param path: The resolved store path to check.
    :param run: Injectable subprocess runner for ``git check-ignore``.
    :returns: ``True`` if `path` is inside a git work tree and not confirmed
        ignored; ``False`` if it is outside any work tree, or inside one and
        confirmed ignored.
    """
    resolved = Path(path)
    root = _git_root_for(resolved)
    if root is None:
        return False
    return is_gitignored(resolved, cwd=root, run=run) is not True
