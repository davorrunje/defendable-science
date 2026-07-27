# ADR-0032: Key store defaults outside the repo (XDG); in-repo store is an explicit, gitignored opt-in

- Status: accepted · Date: 2026-07-22 · Deciders: Davor Runje

## Context

ADR-0029 put the CLI-owned key store at `.honest-scholar/keys.json` — **inside
the consumer repo's work tree** — relying on `research-init` to gitignore it.
Onboarding `davorrunje/mononet` surfaced that `research-init` never actually
added that entry: `honest-scholar keys path` resolved to
`.honest-scholar/keys.json`, and `git check-ignore -v` on it produced no
output — not ignored, therefore committable. `keys set` correctly takes values
from stdin/a hidden prompt (never `argv`), so a secret never lands in shell
history, but the **at-rest store itself** was one missed scaffolding step away
from landing in a commit (honest-scholar#66). That is exactly the failure mode
ADR-0029 set out to avoid, and it contradicts the secret-hygiene stance applied
elsewhere in this repo (`rclone.conf` is gitignored and only
`rclone.conf.example` is tracked).

A gitignore entry is a **single point of failure**: it protects a fresh,
correctly-scaffolded repo, but a missing line, a hand-edited `.gitignore`, or a
consumer repo onboarded before the fix all leave the secret exposed with no
second line of defense.

## Decision drivers

- A stored key must **never be committable by default** — not "committable
  unless `.gitignore` happens to be right."
- Defense-in-depth: even a correct gitignore entry is one mistake away from a
  leak; prefer removing the repo from the equation entirely.
- Preserve ADR-0029's other properties unchanged: `os.environ` > store >
  unset precedence, stdin/hidden-prompt-only writes, scoped in-memory `env`
  for child processes, plaintext-at-rest honesty.
- Stay light-dependency (ADR-0024) — no new package for this.
- Don't break an existing in-repo store outright; give it an explicit,
  documented path back for anyone who wants it (e.g. a shared dev container
  where `$HOME` isn't durable).

## Considered options

1. **Minimal: just add the gitignore line.** `research-init` gitignores
   `.honest-scholar/keys.json`, store location unchanged.
2. **Move the default store outside the repo (XDG config), keep the in-repo
   path as an explicit opt-in** + a runtime guardrail that warns if a
   resolved store is ever inside a non-gitignored work tree. *(chosen)*
3. **OS secure store (Keychain / libsecret / Credential Manager) now.**

## Decision

Option 2.

- **Default store location.** `honest_scholar.core.keys.default_store_path()`
  resolves to `$XDG_CONFIG_HOME/honest-scholar/keys.json`, falling back to
  `~/.config/honest-scholar/keys.json` per the XDG Base Directory spec —
  never inside the consumer repo's work tree. No dependency added
  (`platformdirs` was considered and rejected as unnecessary weight for two
  environment variables); implemented with stdlib `os.environ` + `Path.home()`.
- **Opt-in override.** `HONEST_SCHOLAR_KEYS_PATH` is an explicit override —
  set to any path, including the legacy in-repo `.honest-scholar/keys.json`
  (kept as `keys.IN_REPO_STORE_PATH`) — for anyone who wants the store to
  travel with the repo instead of `$HOME`. `research-init` continues to
  gitignore `.honest-scholar/keys.json`, so that opt-in still lands safely.
- **Runtime guardrail.** `keys.store_at_risk(path)` reports whether the
  *resolved* store sits inside a git work tree (walking up for a `.git` entry)
  and is not *confirmed* ignored (`git check-ignore`, run in that work tree's
  root regardless of the CLI's actual cwd). `keys set` calls this before
  writing and **warns** — never refuses — when it is true; an inconclusive
  answer (no `git` binary, not a git repo at all... i.e. any non-"definitely
  ignored" result) is treated as at-risk, matching the "no news is not good
  news for a secret" posture. Warn, not refuse, because: (a) the default path
  already keeps a fresh setup safe, so this only fires for an explicit
  opt-in a user made deliberately; (b) it matches the existing convention in
  this module (`keys set` on an unrecognised name warns but still stores) —
  CLAUDE.md's failure-honesty stance asks for an explicit, actionable signal,
  not a silent success *or* a hard stop on a deliberate choice.
- **Everything else from ADR-0029 is unchanged**: precedence, stdin-only
  writes, scoped child-process env, plaintext-at-rest disclosure.

## Consequences

- A fresh `research-init` + `keys set` sequence can never produce a
  committable secret file — `git status` shows nothing, because the store
  never entered the work tree.
- An existing consumer repo that already has an in-repo store is unaffected by
  the code change alone (nothing migrates automatically) but gets a warning
  the next time it writes if it opts into `HONEST_SCHOLAR_KEYS_PATH` pointed
  at an un-ignored location; `research-init` re-runs will still add the
  gitignore line as a backstop.
- One more environment variable to document (`HONEST_SCHOLAR_KEYS_PATH`,
  alongside the existing `HONEST_SCHOLAR_LIVE`).
- The guardrail shells out to `git check-ignore` (a fixed, argument-list
  subprocess call, no shell) — the same trust boundary already accepted for
  `rclone` (ADR-0011) and the `--version` probes in `doctor`.
- Tests that exercise the default path must isolate `HOME`/`XDG_CONFIG_HOME`
  (a `tests/conftest.py` autouse fixture does this for the whole suite) so the
  suite never touches a real developer's `~/.config`.

## Rejected alternatives

- **Just add the gitignore line (option 1)** — the minimal fix the issue
  proposed, but it is exactly the single point of failure that caused #66 in
  the first place: it protects only a freshly, correctly scaffolded repo.
  Implemented anyway as defense-in-depth (`research-init` still gitignores
  the in-repo path), just not relied on as the primary control.
- **OS secure store now (option 3)** — the right at-rest answer eventually,
  but heavy/platform-specific with a headless/CI fallback to design; already
  deferred to issue #49 by ADR-0029 and still the better place for it.

## Links

`honest-scholar/honest_scholar/core/keys.py` (`store_path`, `default_store_path`,
`store_at_risk`, `is_gitignored`); `honest-scholar/honest_scholar/cli.py` (`keys
set`'s `_warn_if_store_committable`); `skills/research-init/SKILL.md`;
ADR-0029 (the store this refines); ADR-0024 (light-dependency posture);
honest-scholar#66 (this decision); honest-scholar#49 (OS-keychain follow-up,
unaffected); honest-scholar#65 (a related but distinct scaffolding-vs-runtime
mismatch for the dataset cache path, fixed separately — not in scope here).
