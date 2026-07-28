# Experiment-backend contract

The pipeline skills never run experiments directly — they depend on this
contract, and each consuming repo binds a concrete implementation. This keeps the
runner hot-swappable and keeps `defendable-science` domain-neutral. (Design: `docs/design/04-substrate-and-contract.md` §3; ADR-0013.)

## Binding

A project binds a backend in `docs/research/papers.md` via a **required**
`backend:` field — the plugin bundles **no default**, shipping only this contract.
A backend is any implementation exposing the four capabilities below. Pipeline
skills resolve the backend from the binding and contain **no** backend-specific
logic.

## The four capabilities

| Capability | Purpose | Returns |
|---|---|---|
| `run` | execute (or resume) an experiment for a given config | a **run-ref** — an opaque, stable handle |
| `evidence` | fetch results for a run-ref | structured results + a **provenance stamp** |
| `tables` | render results into the doc-facing artifacts a hypothesis/paper cites | rendered result blocks (managed, regenerable) |
| `is-current` | check whether a run-ref's evidence is still valid given current code/config/data | `current` \| `stale(reasons)` |

### run-ref

The **citable unit of evidence**. `findings.md` (hypothesis) and the paper
`ledger`/`decision` reference run-refs — **never** hand-copied numbers. Format is
opaque; the backend resolves it.

### provenance stamp

Accompanies `evidence`. Must carry, at minimum:

- the config hash / identity of the run,
- code provenance (e.g. a symbol-closure hash or commit),
- **for every dataset consumed: `id + version + sha256`** (from the `dataset`
  skill — so a result resolves to exact bytes),
- timestamps and hardware/context as available.

### tables

The **only** writer of result numbers into documents — as managed, regenerable
blocks. This is what keeps quoted results in sync with the evidence.

### is-current

What makes selective re-execution honest: a hypothesis or paper asks "is my
evidence stale?" without knowing how the backend computes staleness. It **reports**
staleness; it does **not** decide to re-run — the researcher does.

## Agency-principle interaction

The backend **produces and stamps** evidence; it **never adjudicates** it. Whether
the evidence confirms/refutes a hypothesis, or supports publication, is a human
decision recorded with a sign-off (agency principle, `docs/design/00-meta-spec.md` §2.1).

## Implementing a backend

A backend implementation lives in the **consuming repo**, not here. It must:

1. accept a config and return a stable run-ref (`run`);
2. return results + a provenance stamp for a run-ref (`evidence`);
3. render managed result blocks (`tables`);
4. answer `current | stale(reasons)` for a run-ref (`is-current`).

How it runs experiments (local, GPU fan-out, cluster, cached) is entirely up to
the implementation; nothing above prescribes a scheduler. One implementation might
use a `doit` + GPU-pool executor with committed-JSON results, `.provenance.json`
sidecars, a managed-block writer, and a closure-based provenance hash; a
lightweight local runner is equally valid. The plugin ships no backend — each repo
supplies its own.
