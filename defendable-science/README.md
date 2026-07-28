# Defendable Science

*Research you can defend.*

**Defendable Science** helps you keep research honest — especially now that AI is in
the loop. You (not the AI) make and sign off every material decision, and you must
be able to explain and defend the work; the tool keeps the accounts, advises, and
probes. It **supports** honest, disclosable AI-assisted research — it does **not**
certify that any work is honest.

This package is the **CLI / tooling** behind the
[`defendable-science` Claude Code plugin](https://github.com/davorrunje/defendable-science).
The plugin (skills + methodology) stays pure-markdown; this package provides the
`defendable-science` command it calls — `literature`, `dataset`, `defend`, `backlog`,
and `doctor` — installed **isolated**, so it never touches your project's ML
environment.

## Install

```bash
uv tool install defendable-science     # recommended (isolated tool env)
# or: pipx install defendable-science
# or: pip install defendable-science

defendable-science --version
defendable-science doctor              # reports python / uv / rclone
```

**Documentation:** <https://defendable.science/>

## CLI

```
defendable-science --version
defendable-science doctor                                           # environment report
defendable-science literature resolve|cites|refs|enrich|neighbors   # citation graph (OpenAlex + S2)
defendable-science dataset    validate|ingest|emit                  # manifest + Croissant
defendable-science dataset    fetch|verify|mirror|audit             # SHA-256 retrieval + rclone mirror
defendable-science defend     record                                # understanding-status record
defendable-science backlog    park|add|list|rank|promote|drop       # exploration backlog
defendable-science keys       set|list|check|unset|path             # API-key & credential store
```

Every command is implemented and emits JSON (the skills parse it). **Failures are
surfaced honestly:** a rate-limit or transient network error is retried with
backoff (honoring `Retry-After`) and, if it persists, reported as a distinct,
actionable message — never a silent "not found" and never a traceback. A missing
API key or `rclone` binary is reported cleanly, and an optional key (e.g.
`S2_API_KEY`) simply lifts the rate ceiling — see
[API keys & credentials](#api-keys--credentials).

## API keys & credentials

Some services throttle hard without a key. Providing one is optional (the tooling
degrades gracefully) but lifts the ceiling:

| Key | Service | What it buys | How to obtain |
|---|---|---|---|
| `S2_API_KEY` | Semantic Scholar | Rate limit well above the shared keyless pool. | <https://www.semanticscholar.org/product/api#api-key> |
| `OPENALEX_MAILTO` | OpenAlex | The "polite pool" (a contact email) — faster, more reliable. | <https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication> |
| `RCLONE_CONFIG_<REMOTE>_*` | Private dataset mirror | rclone remote credentials passed as scoped env vars (no config file). | Per your rclone remote. |

Keys live in a **CLI-managed JSON store** at `.defendable-science/keys.json`
(gitignored, created `0600`), read with **`os.environ` > store > unset**
precedence, so an environment variable always wins. Manage it with `keys`:

```bash
defendable-science keys set S2_API_KEY        # hidden prompt, or reads piped stdin
echo "$MY_KEY" | defendable-science keys set S2_API_KEY
defendable-science keys set < keys.json       # a JSON object sets many at once
defendable-science keys list                  # presence + source (never the value)
defendable-science keys check | unset | path
```

The value is read only from stdin or a hidden prompt — never `argv` — so it never
hits your shell history or the process list, and `list`/`check`/`doctor` report
presence only.

> **Plaintext at rest.** The store is **not encrypted**; gitignore + `0600` limit
> exposure but are not a vault. OS-keychain backing is a planned follow-up (#49).

## Learn more

- **Documentation:** <https://defendable.science/>
- **User guide:** <https://defendable.science/get-started/user-guide>
- **Plugin, source & full design record:** <https://github.com/davorrunje/defendable-science>
- **Disclose your AI use & cite Defendable Science:** <https://github.com/davorrunje/defendable-science/blob/main/DISCLOSURE.md>

## Changelog

<https://github.com/davorrunje/defendable-science/blob/main/CHANGELOG.md>

## License

[Apache-2.0](https://github.com/davorrunje/defendable-science/blob/main/LICENSE).
