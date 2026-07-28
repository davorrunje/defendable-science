# ADR-0029: Unified API-key handling — a CLI-managed JSON store, not `.env`

- Status: accepted · Date: 2026-07-19 · Deciders: Davor Runje

> **Refined by ADR-0032.** The default store location moves outside the
> consumer repo's work tree (XDG config, not `.defendable-science/keys.json`),
> closing a secret-leak gap the in-repo default left open
> (defendable-science#66). The in-repo path below remains available as an
> explicit opt-in and is still gitignored by `research-init`.

## Context

The skills reach external services that key-gate their useful rate limits —
Semantic Scholar (`S2_API_KEY`), OpenAlex (`OPENALEX_MAILTO`, polite pool),
private rclone mirror remotes — but keys are read ad hoc (`os.environ` inside
`_lit_client`) with no unified place to store, add, or check them, and no
guidance on obtaining them. Keyless Semantic Scholar throttling is the root cause
behind ADR-noted rate-limit work (#41); "get a key" is the easy ceiling-raiser,
but today it is undiscoverable and unmanaged. For a tool run across many repos,
that invites keys pasted into committed config or lost, and secrets leaking
through shell history, argv, or over-broad exposure to child processes.

This is an integrity tool, so the design must also be **honest about what it does
not do**: convenience storage is not encryption.

## Decision drivers

- One controlled, documented way to add/check keys — no rediscovery, no hand-edited files.
- **Never** leak a secret through shell history, `argv`, or a process list.
- **Least privilege**: a child process (rclone, the engineering backend) should
  see only the secrets its job needs, not the whole store.
- Prefer **no secret on disk** during an operation; when a file is unavoidable,
  make it short-lived and `0600`.
- **CI/interop**: an injected environment variable must always win over the store.
- Honest posture: disclose plaintext-at-rest; do not imply "secure".
- Light dependency footprint (ADR-0024) — avoid a heavy secrets dependency in v1.

## Considered options

1. **A globally-loaded `.env` file** (dotenv-style), read on every CLI start.
2. **A CLI-managed JSON store + a `keys` command group**, read in-process, with
   stdin-based writes and scoped in-memory env for child processes. *(chosen)*
3. **The OS secure store now** (Keychain / libsecret / Credential Manager).

## Decision

Option 2.

- **Store.** A CLI-owned JSON file `.defendable-science/keys.json` — gitignored,
  created `0600` — holding each key plus light metadata (service, how-to-obtain
  link). JSON (not `.env`) because the CLI is the only writer/reader, so a
  structured, metadata-carrying format beats line-parsing; and a global `.env`
  auto-loaded by unrelated tools is a foot-gun.
- **Command group.** `defendable-science keys set|list|check|unset|path`. `set` reads
  the value from **stdin / a hidden prompt** (never `argv`), and accepts a JSON
  blob on stdin to set many at once or to run a one-shot without persisting.
  `list`/`check` report **presence, never values**, and which source each key
  came from.
- **Read precedence.** `os.environ` **>** the JSON store **>** unset. A present
  env var always wins (CI/secrets injection), then the store, then the service
  degrades (per the rate-limit handling).
- **In-process use.** Our own CLI commands read the store into memory and use it
  directly — **no `.env`, no temp file** is written for our own work (the common
  path).
- **Child processes.** Secrets are handed to a child via a **scoped in-memory
  `env=` dict** containing only what that job needs — not a file. rclone in
  particular takes `RCLONE_CONFIG_<REMOTE>_<…>` env vars, so no config file is
  needed. A temporary `.env`/file is a **documented last resort** only for a tool
  that can *only* read a file, created under `TMPDIR`/tmpfs at `0600` and removed
  in a `finally`.
- **Honesty.** The store is **plaintext at rest**; docs say so explicitly —
  gitignore + `0600` limit exposure but are *not* encryption. `research-init`
  scaffolds guidance (not secrets); `doctor` reports key presence, never values.

## Consequences

- Adding/checking a key is one command; nothing lands in shell history or a
  committed file; env vars still override for CI.
- Child processes get least-privilege secret exposure with no disk artifact on
  the default path.
- The store gives **no at-rest encryption** — an accepted, disclosed limitation.
  Real at-rest protection (OS keychain) is deferred to **#49** as an optional
  backend behind the same `keys` interface.
- Implementation stays light-dep (stdlib JSON + a small loader); no Pydantic, no
  dotenv dependency.

## Rejected alternatives

- **Global `.env`** — auto-loaded by unrelated tools (surprising), no scoping to
  child processes, weaker metadata, and encourages a broad always-present secret
  file. The CLI-owned store with explicit env provisioning is more controlled.
- **OS secure store now** — the right at-rest answer, but heavy/platform-specific
  and needs a graceful headless/CI fallback; deferred to #49 as an optional extra.
- **Secret via `argv`** (`keys set NAME VALUE`) — leaks to the process list and
  shell history; rejected in favor of stdin/hidden-prompt.

## Links

`defendable-science/defendable_science/cli.py` (`_lit_client`, the `keys` group);
`resources/ensure-tooling.md`; #42 (implementation), #49 (OS-keychain backend
follow-up), #41 (rate-limit handling — the "get a key" complement); ADR-0024
(light-dependency / optional-extra posture).
