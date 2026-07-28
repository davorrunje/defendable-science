# ADR-0023: Delegate engineering via a contract, not a named tool

- Status: accepted · Date: 2026-07-18 · Deciders: Davor Runje

## Context

ADR-0002 kept `defendable-science` scientific-only and delegated engineering to **a specific
named tool**. But naming a specific engineering tool couples the plugin to it and
specifies *how* engineering is performed — exactly what we avoided for experiments
(ADR-0013, the experiment-backend contract). `defendable-science` should be agnostic to the
engineering workflow the same way it is agnostic to the experiment runner, and
should not advertise or depend on any particular product.

## Decision drivers

- Symmetry with the experiment-backend contract; hot-swappable backends.
- Domain- and tool-neutrality: the plugin should not depend on or advertise a
  particular engineering tool.
- Consumers already have their own engineering workflows.

## Considered options

1. **Define an engineering-delegation contract (`design` / `plan` / `implement`),
   bound per project; name no specific tool.**
2. Keep naming a specific tool as the engineering backend (ADR-0002 as written).
3. Bring engineering in-scope for `defendable-science`.

## Decision

Option 1. Add `resources/contracts/engineering.md` (three capabilities, bound via
`.defendable-science/config.yml` `engineering_backend:`). Remove every explicit
engineering-tool mention from the plugin; a consumer binds whatever engineering
backend it uses (bound in *its own* `.claude/settings.json` / config — the
consumer's choice, not the plugin's concern). ADR-0002 is refined accordingly
(engineering delegated *via the contract*, tool unnamed).

## Consequences

- The plugin is fully tool-neutral; skills reference "the bound engineering
  backend," not a product.
- One more contract to keep coherent with the experiment-backend contract.
- Sweep: `hypothesis-testing` / `paper-synthesis` / `research-init` / templates /
  README / user guide / specs reworded to the contract.

## Rejected alternatives

- **Name a specific tool** — couples the plugin, specifies how engineering is
  done, and advertises one product.
- **Engineering in-scope** — duplicates mature engineering tools; bloats scope;
  breaks the science-only identity (ADR-0002).

## Links

`resources/contracts/engineering.md`; ADR-0002 (refined), ADR-0013 (the parallel
experiment-backend contract).
