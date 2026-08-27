# The experiment backend: how a run becomes citable evidence

A task-oriented guide to the one part of `defendable-science` **you** have to
supply. The plugin defines a four-capability contract and ships no
implementation; this page is what to build, why each capability exists, and how
to bind it so the pipeline skills can find it.

If you have not met `defendable-science` yet, read the
[User Guide](../USER-GUIDE.md) first.

## 1. Why the plugin ships no backend

Every other capability here is domain-neutral by construction. Running an
experiment is not: it means your scheduler, your cluster or laptop, your config
format, your result layout. Bundling one would either be useless to most projects
or would smuggle a particular ML stack into a plugin that is supposed to work for
any empirical science.

So the plugin ships the **contract** and nothing else, and `backend:` in
`docs/research/papers.md` is a **required** field with no default (ADR-0013). A
paper with no backend binding is a paper whose numbers have no traceable origin,
which is precisely the state this tool exists to prevent — so it refuses to
pretend otherwise rather than silently defaulting to something.

There is no CLI here. The contract is implemented in your repo and invoked by the
pipeline skills, so everything on this page is either something you write or
something you ask the assistant for.

## 2. The four capabilities

| Capability | Purpose | Returns |
|---|---|---|
| **`run`** | execute (or resume) an experiment for a given config | a **run-ref** — an opaque, stable handle |
| **`evidence`** | fetch results for a run-ref | structured results + a **provenance stamp** |
| **`tables`** | render results into the doc-facing blocks a hypothesis or paper cites | rendered artifacts (managed blocks) |
| **`is-current`** | is this run-ref's evidence still valid given current code, config and data? | `current` \| `stale(reasons)` |

Nothing in that table mentions a scheduler, and that is deliberate: a shell script
that runs one model on a laptop and a GPU orchestrator fanning out a thousand
trials are equally valid implementations.

### The run-ref is the whole idea

A **run-ref is the citable unit of evidence.** `findings.md` at the hypothesis
level, and `ledger.md` / `decision.md` at the paper level, reference run-refs —
**never raw numbers copied by hand**. If a number cannot be traced to a run-ref,
it does not belong in a findings doc or a paper section.

This is not bookkeeping fussiness. Hand-copied numbers are the single most common
way an honest researcher publishes a wrong table: the run is re-done, the config
drifts, the number in the draft is from two weeks ago and nothing in the document
knows that. Citing a run-ref makes the staleness *detectable*, which is what
`is-current` is for.

### `tables` is the only writer of numbers

The `tables` capability writes result numbers into your documents as **managed,
regenerable blocks**. Nothing else does — not you, not the assistant. Regenerating
is therefore always safe, and a number in a paper section is always exactly what
the backend most recently rendered from a run-ref.

### The provenance stamp must carry the dataset fingerprint

`evidence` returns results *plus* a stamp: config hash, code/symbol provenance,
timestamps, hardware, and the dataset `id + version + sha256` from the
[`dataset`](dataset.md) manifest. That last one is what closes the loop — a
reported result resolves to exact bytes, so "which data was this?" has an answer
you can verify with `defendable-science dataset verify` rather than a
recollection.

### `is-current` makes selective re-execution honest

Without it, you have two bad options: re-run everything before every deadline, or
trust that nothing has drifted. `is-current` lets a hypothesis or paper ask "is my
evidence stale?" without knowing how the backend computes staleness — a
provenance or closure hash is the usual answer.

**It reports; it does not decide.** A `stale(reasons)` answer is information for
you. Whether to re-run is a research judgement — cost, deadline, whether the drift
could plausibly change the verdict — and the tool does not make it.

## 3. Binding a backend

One field, in the paper registry:

```
| paper-id | root | backend |
|---|---|---|
| aug-policy-robustness | docs/research/aug-policy-robustness | bench |
```

`promote` writes that row when you promote a candidate paper:

```bash
defendable-science backlog promote aug-policy-robustness \
    --backlog docs/research/portfolio-backlog.md --level paper --scaffold \
    --research-root docs/research --backend bench
```

`--backend` is required with `--scaffold` at the paper level, for the reason
above: a registry row with an empty binding is not a usable paper.

The repo-wide default lives in `.defendable-science/config.yml`; the per-paper row
in `papers.md` is what the pipeline skills actually resolve. Different papers in
one portfolio may bind different backends, and no pipeline skill changes as a
result — that is the payoff for the contract being abstract.

## 4. What a minimal implementation looks like

You do not need a platform. A typical mapping onto tooling a project already has:

| Capability | A plausible minimal implementation |
|---|---|
| `run` | the script you already use to train/evaluate, returning a directory name or hash as the run-ref |
| `evidence` | the committed results file plus a provenance sidecar you write alongside it |
| `tables` | a small renderer that replaces a marked block in a markdown file |
| `is-current` | hash of (config + code revision + dataset sha256s), compared against the stamp |

The discipline that matters is not sophistication, it is that **`evidence` stamps
the dataset fingerprint** and **`tables` is the only writer**. Those two make the
rest of the guarantees hold.

## 5. Where the boundary sits

The backend produces and stamps evidence. It **never adjudicates** it.

Whether the evidence confirms or refutes a hypothesis, and whether a body of work
supports publication, are material decisions recorded with a named human sign-off
and a date. A backend that returned a verdict would be making your call for you,
and the pipeline skills would have nowhere to put your signature.

The same line runs through `is-current`: it tells you the evidence is stale, and
stops.

## 6. Engineering is delegated, too

The backend contract is about *running* experiments. The adjacent question —
designing them and writing the code — is also not the plugin's job: `design.md`
and `plan.md` are produced by a bound **engineering backend** via the
engineering-delegation contract (ADR-0023). `defendable-science` stores the
results in the hypothesis folder and reasons about them, but does not design
experiments or write code itself.

So a fully wired repo binds two things: an engineering backend for design/plan,
and an experiment backend for run/evidence/tables/is-current.

> **Ask the assistant.** Walk me through what our experiment backend has to
> implement for `docs/research/aug-policy-robustness`, and check whether our
> current runner already covers `is-current` — I want to know what is missing
> before I bind it in `papers.md`.

## Where to go next

- [`docs/design/04-substrate-and-contract.md`](../design/04-substrate-and-contract.md)
  §3 — the contract in full, including the open question about run-ref format.
- [ADR-0013](../../decisions/0013-experiment-backend-contract.md) — why a
  contract with no bundled default, and the alternatives rejected.
- [ADR-0023](../../decisions/0023-engineering-delegation-contract.md) — the
  engineering-delegation contract, the other half of the delegation story.
- [`docs/guides/dataset.md`](dataset.md) — where the `id + version + sha256` in
  the provenance stamp comes from.
- [`skills/hypothesis-testing/SKILL.md`](../../skills/hypothesis-testing/SKILL.md)
  — the skill that consumes run-refs into a signed verdict.
