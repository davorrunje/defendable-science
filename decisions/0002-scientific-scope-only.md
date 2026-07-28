# ADR-0002: Scientific scope only; engineering delegated via a contract

- Status: accepted · Date: 2026-07-17 · Deciders: Davor Runje

> **Refined by ADR-0023.** Engineering is delegated *via the
> engineering-delegation contract* to a bound engineering backend, naming no
> specific tool. The original decision named one; that framing is superseded.

## Context

The full research lifecycle includes both scientific work (claims, evidence,
decisions, papers) and engineering (designing/building the code that produces
evidence). Mature engineering workflows already handle the latter well
(design → plan → implement).

## Decision drivers

- Don't reinvent engineering workflows; keep `defendable-science`'s identity sharp.
- The scientific parts (rigor, positioning, decisions) are what's missing.

## Considered options

1. **Scientific scope only; delegate engineering via a contract to a bound
   engineering backend.**
2. One plugin covering both science and engineering.

## Decision

Option 1. `hypothesis-testing` hands design/plan/implementation to the bound
engineering backend via the engineering-delegation contract
(`resources/contracts/engineering.md`) and stores the artifacts under the
hypothesis folder.

## Consequences

- Clean separation; `defendable-science` composes with an engineering backend rather than
  competing with one.
- A dependency on some engineering backend for the engineering leg (acceptable;
  the consumer binds whatever it uses in `.defendable-science/config.yml`).

## Rejected alternatives

- **All-in-one plugin** — duplicates mature engineering tools, bloats scope,
  blurs identity.

## Links

meta-spec §1 (non-goals), §2; sub-spec 1 §2.2; ADR-0023 (the
engineering-delegation contract that refines this).
