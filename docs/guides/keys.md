# API keys: what they buy, and where they are kept

A task-oriented guide to credentials. Every key here is **optional** —
`defendable-science` degrades gracefully without any of them — but the citation
graph in particular is much less painful with one, and knowing which key does what
saves you from setting up things you do not need.

If you have not met `defendable-science` yet, read the
[User Guide](../USER-GUIDE.md) first.

## 1. This one is nearly all CLI

Unlike most capabilities here, key handling is a real command group with no skill
mode: `defendable-science keys set | list | check | unset | path`. Everything on
this page is a command you type.

## 2. What each key buys

| Key | Service | What it buys | Where to get it |
|---|---|---|---|
| `S2_API_KEY` | Semantic Scholar | Raises the rate limit far above the shared keyless pool, which throttles hard. | <https://www.semanticscholar.org/product/api#api-key> |
| `OPENALEX_MAILTO` | OpenAlex | Joins the "polite pool" — it is just a contact email — for faster, more reliable responses. | <https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication> |
| `RCLONE_CONFIG_<REMOTE>_*` | private dataset/PDF mirror | rclone remote credentials, handed to rclone as scoped env vars so no config file is needed. | per your remote (`rclone config`) |

`OPENALEX_MAILTO` is the cheapest win in the list: it is an email address, not a
credential, and it moves you out of the throttled anonymous pool. Set it first.

Without `S2_API_KEY`, snowballing a survey to saturation will stall on rate
limits — and it will *say* it stalled rather than reporting a short result as
complete. A throttle is an error, never a legitimately empty answer.

## 3. Where keys live: a JSON store outside your repo

`defendable-science` keeps keys in a **CLI-managed JSON store — never a `.env`** —
at an XDG config path **outside any repo's work tree**:

```
$XDG_CONFIG_HOME/defendable-science/keys.json
# falling back to
~/.config/defendable-science/keys.json
```

That location is the point (ADR-0032): a stored key cannot be committed by
accident, because it is not in the repo at all.

```bash
defendable-science keys path      # print the resolved store path
```

## 4. Setting and inspecting keys

```bash
defendable-science keys set S2_API_KEY          # hidden prompt
echo "$MY_KEY" | defendable-science keys set S2_API_KEY
defendable-science keys set < keys.json         # a JSON object sets many at once
defendable-science keys list                    # metadata + presence + source
defendable-science keys check                   # compact presence/source report
defendable-science keys unset S2_API_KEY
```

**The value is never taken from the command line** — only from a hidden prompt or
stdin. So a secret never lands in your shell history or in the process list where
any other user on the machine could read it. There is deliberately no
`keys set S2_API_KEY <value>` form.

`keys list`, `keys check` and `doctor` report **presence and source only, never a
value**. If you need to see a key, read the store file yourself; the tool will not
print it for you.

## 5. Precedence: the environment always wins

Keys resolve as **`os.environ` > store > unset**.

- An environment variable always wins, so CI and secret-injection setups work
  untouched — you do not need the store in CI.
- The store is the convenience layer for your laptop.
- An unset key does not fail; it degrades the service, visibly.

```bash
defendable-science keys check     # tells you which source each key came from
```

That `source` column is the one to read when something behaves unexpectedly: a
stale environment variable shadowing a freshly-set store entry looks exactly like
"the store did not save", and `check` distinguishes them.

## 6. Opting into a different location

Set `DEFENDABLE_SCIENCE_KEYS_PATH` to move the store — for example to the legacy
in-repo `.defendable-science/keys.json`, which `research-init` still gitignores
for anyone who wants it there.

If you do, the store **warns — never silently** — when the resolved path sits
inside a git work tree and is not confirmed gitignored. That warning is the
guardrail for the one configuration that can leak a key into a commit.

## 7. Honesty caveat: plaintext at rest

**The store is not encrypted.**

Living outside the repo limits exposure, and an opted-in in-repo store is
gitignored with `0600` permissions — but anyone who can read the file reads the
keys. Treat it as convenience storage, not a secret vault. If your threat model
includes other users on the machine, or a stolen laptop, use your OS keychain or
an env-var injection setup instead.

OS-keychain backing behind this same `keys` interface is a planned follow-up
(issue [#49](https://github.com/davorrunje/defendable-science/issues/49)).

## Where to go next

- [`docs/guides/literature.md`](literature.md) — what `S2_API_KEY` and
  `OPENALEX_MAILTO` are actually for.
- [`docs/guides/dataset.md`](dataset.md) §5 — the rclone side, and why
  `rclone obscure` is not encryption.
- [ADR-0029](../../decisions/0029-api-key-handling.md) — a CLI-managed store
  rather than `.env`, and the alternatives rejected.
- [ADR-0032](../../decisions/0032-keys-store-outside-repo-by-default.md) — why the
  default lives outside the repo.
