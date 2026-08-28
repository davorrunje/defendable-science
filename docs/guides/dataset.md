# Datasets: a manifest you can cite, and bytes you can prove

A task-oriented guide to the whole `dataset` capability — registering data, giving
every file a fingerprint, materializing it through the resolution chain, and
keeping a private mirror so link rot cannot quietly break your reproducibility.

If you have not met `defendable-science` yet, read the
[User Guide](../USER-GUIDE.md) first — this page assumes you know what a skill is
and what the agency principle asks of you.

## 1. Two kinds of instruction, and how to tell them apart

Like `literature`, the `dataset` capability is half assistant and half
command-line tool, and mixing the two up is the fastest way to get stuck.

- **`init` and `register` are skill *modes*.** You *ask the assistant* for them,
  in prose. They involve judgement — proposing a storage tier, reading a license,
  writing a datasheet — and end in a decision that is yours to confirm. There is
  no `defendable-science dataset register` command.
- **`defendable-science dataset …` is a CLI.** Seven commands, each printing
  JSON: `validate | ingest | emit` over the manifest, and
  `fetch | verify | mirror | audit` over the bytes. These run in a terminal, and
  the skill shells out to them.

So this page can never be misread, it uses exactly two conventions:

> **Ask the assistant.** Anything you say to the agent appears in a quote block
> like this one, in plain language. You are not meant to type it into a shell.

```bash
# Anything in a shell block is a real command, verbatim.
defendable-science dataset verify
```

Note the asymmetry with the skill's verb table in
[`skills/dataset/SKILL.md`](../../skills/dataset/SKILL.md): the skill's `export`
verb is the CLI's `dataset emit`, and the skill's `register` is what *produces*
manifest entries that `dataset validate` then gates. The verb names are the
methodology's; the command names are the tool's.

## 2. The manifest: one file, checked into git

`datasets.yml` is the registry and the source of truth. It is committed, public,
and holds **no secrets and no blobs above Tier A** — metadata, checksums, tiers,
licenses, retrieval recipes, and datasheet links.

Every command that reads the manifest finds it for you: the path comes from the
repo layout (`layout.datasets_manifest` in `.defendable-science/config.yml`,
defaulting to `datasets.yml` at the repo root), so no command in this guide
passes `--manifest`. The flag still exists and still wins when you pass it — use
it to point at a manifest that is not this repo's. The one command with no
`--manifest` at all is `dataset ingest`: it reads a Croissant document you name
and never opens the manifest.

> **Ask the assistant.** Scaffold the dataset registry for this repo
> (`dataset` in `init` mode) — I want `datasets.yml`, the gitignored cache dir,
> and the committed `rclone.conf.example` template.

Then, per dataset:

> **Ask the assistant.** Register `imagenet-c` in the dataset manifest — ingest
> its published Croissant metadata if there is one, propose a storage tier and
> read me the license, and draft the datasheet. I will confirm the tier and the
> license.

Two things in that request are load-bearing. **The tier and the license are
yours to confirm**, never the skill's to decide — they determine whether bytes may
be committed or redistributed, which is a legal question about your project, not
a technical one. And the **datasheet** is not paperwork: it is a `defend`
methodology target, so expect to be asked "what are this dataset's known
collection limits?" before you sign a finding that rests on it.

If the dataset publishes Croissant JSON-LD, bootstrap from it rather than
hand-typing:

```bash
defendable-science dataset ingest path/to/croissant.json
```

and validate the manifest whenever you have hand-edited it:

```bash
defendable-science dataset validate
```

`validate` is the gate `register` and `audit` both run behind. A manifest that
does not validate is a manifest whose checksums you cannot trust.

## 3. Tiers: a license question, not a size question

The tier is `f(redistribution license × access automation)`, and **redistribution
dominates**. Size only decides Tier A once redistribution is already permitted.

| Tier | Condition | What you get |
|---|---|---|
| **A — committed** | small **and** the license permits redistribution | bytes in git/LFS; zero-setup reproducibility. A mirror is redundant. |
| **B — auto-retrievable** | public and fetchable from a stable URL/API, but large or non-redistributable | a `retrieval` recipe plus a `sha256` in the manifest; bytes land in the gitignored cache. **The mirror is link-rot insurance**, populated on first fetch. |
| **C — manual / gated** | login, EULA, registration, or no stable source | metadata, datasheet, acquisition instructions and `sha256` only. The tooling **verifies presence and integrity but never fetches**. Mirror only if the DUA permits a private copy. |

The common mistake is filing a large public dataset as Tier C because it is
awkward to download. If there is a stable URL and a checksum, it is Tier B, and
the difference matters: Tier B is reproducible by anyone who clones your repo,
Tier C needs a human with credentials.

## 4. Getting the bytes: the resolution chain

`fetch` never just downloads. It walks a chain, verifying SHA-256 at every hop,
and **a file that fails verification is treated as absent** so the chain
continues rather than handing you bad bytes:

```
1  LOCAL CACHE     exists and sha256 == manifest → return; else discard if corrupt
2  PRIVATE MIRROR  rclone copy mirror:base/sha256/<hash> → re-hash → return; else fall through
3  PUBLIC SOURCE   Tier A: git/LFS · Tier B: pooch (http/ftp/sftp/doi:)
                   → assert sha256 == manifest (HARD FAIL) → populate mirror → return
4  GATED / MANUAL  print acquisition instructions → wait for your drop → verify → populate mirror
```

```bash
defendable-science dataset fetch imagenet-c
```

Three properties of that chain are worth understanding, because they are what
make a cited number defensible:

- **The manifest's SHA-256 is authoritative.** Integrity *is* identity *is*
  citation-verifiability. A mismatch at step 3 is a hard failure, not a warning —
  the tool will not bind unverified bytes to a dataset id you are citing.
- **rclone's own hash is only a transport check.** Backends often report MD5
  (Drive, S3). Local bytes are always **re-hashed against the manifest** after any
  transfer, so verification does not depend on which backend you mirror to.
- **The cache is content-addressed on the wire** (`sha256/<hash>` keys) and
  name-addressed for use. That gives deduplication for free and makes integrity
  and identity the same fact.

To check what you already have, offline and without touching the network:

```bash
defendable-science dataset verify
```

`verify` never downloads. That is the point: it answers "do the bytes on this
machine still match what I published?" — the question you want answered before a
paper deadline, not during one.

## 5. The mirror: link-rot insurance

A Tier B dataset is only reproducible for as long as its URL resolves. The
private mirror is the answer, populated automatically on first successful
acquisition and refreshable on demand:

```bash
defendable-science dataset mirror imagenet-c
```

**Credentials never enter the repo.** `rclone.conf` is gitignored; you point at it
with `RCLONE_CONFIG=$PWD/.defendable-science/rclone.conf`, and commit only
`rclone.conf.example` (remote name and type, nothing else). CI uses env-var
remotes from secrets. And `rclone obscure` is **not** encryption — never commit
its output and never treat it as a secret store.

rclone itself is an optional external binary the wrappers shell out to, not a
Python dependency. If it is absent, mirror steps degrade with an explicit signal
rather than silently reporting "not mirrored".

## 6. `audit`: the one command to run before you publish

```bash
defendable-science dataset audit
```

`audit` is the whole-manifest sweep, and it checks more than fixity:

- **fixity** — every on-disk file against its manifest checksum;
- **presence** — is each entry actually retrievable, including from the mirror;
- **completeness** — is there a license and a datasheet for every entry;
- **tier ↔ (access, redistributable) consistency** — this is the one people miss.
  A Tier A entry whose license forbids redistribution is a licensing problem
  sitting in your git history. A Tier C entry with a perfectly good public URL is
  a reproducibility problem you have imposed on your readers.

It reports gaps; it does not fix them. Closing a gap is a decision (relicense,
re-tier, write the datasheet), and decisions are yours.

## 7. Quick reference

| You want to… | How |
|---|---|
| scaffold the registry | ask the assistant (`init` mode) |
| add a dataset | ask the assistant (`register` mode) — you confirm tier + license |
| bootstrap from published Croissant | `dataset ingest <file>` |
| check a hand-edited manifest | `dataset validate` |
| materialize a dataset | `dataset fetch <id>` |
| check on-disk bytes, offline | `dataset verify` |
| refresh the private mirror | `dataset mirror <id>` |
| pre-publication sweep | `dataset audit` |
| emit Croissant for a venue | `dataset emit <id>` (or `--all`) |

## Where to go next

- [`skills/dataset/SKILL.md`](../../skills/dataset/SKILL.md) — the capability in
  the plugin's own words, including the full manifest schema and the guardrails.
- [`docs/guides/literature.md`](literature.md) — the other front-end over the same
  substrate; the same cache → mirror → source chain, for PDFs.
- [`docs/design/03-dataset.md`](../design/03-dataset.md) — the design, and
  [`docs/design/04-substrate-and-contract.md`](../design/04-substrate-and-contract.md)
  §2.4 for the shared resolution chain.
- [ADR-0010](../../decisions/0010-storage-tiers.md) — why tiers are a license
  question first and a size question second.
