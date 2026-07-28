# Engineering-delegation contract

`defendable-science` covers the **scientific** workflow (claims, evidence, decisions, papers)
but does **not** prescribe *how* engineering is done — designing and building the
code that produces evidence, and any implementation work. Skills that need
engineering **hand it off through this contract**; each consuming repo binds an
**engineering backend**. This mirrors the experiment-backend contract
(`experiment-backend.md`): `defendable-science` names no specific engineering tool, so the
backend is hot-swappable and the plugin stays domain- and tool-neutral.
(Decision: ADR-0023; supersedes the tool-specific framing of ADR-0002.)

## Binding

A project binds an engineering backend in `.defendable-science/config.yml`
(`engineering_backend: <name>`). A backend is anything that provides the three
capabilities below and writes its artifacts where the calling skill asks (e.g.
under a hypothesis folder). Pipeline skills contain no backend-specific logic.

## The three capabilities

| Capability | Purpose | Produces |
|---|---|---|
| `design` | given a scoped engineering task (framed by the science in `strategy.md`), explore and settle a design | a `design.md` artifact |
| `plan` | turn the design into a stepwise, reviewable implementation plan | a `plan.md` artifact |
| `implement` | carry out the plan — write/modify code + tests | code changes + a reference (e.g. commits/PR) |

- The calling skill hands off a **task** (what to build, framed by the science);
  the backend returns the artifacts, stored under the owning folder (e.g.
  `docs/research/<paper>/hypotheses/<slug>/{design,plan}.md`).
- The **experiment-backend** contract then *runs* what the engineering backend
  *built* — engineering builds the harness; the experiment backend executes it and
  returns evidence.

## Agency-principle interaction

Engineering is still human-driven: the backend produces design/plan/implementation
*artifacts*; the researcher directs and reviews them. `defendable-science` never fakes the
engineering, and the scientific decisions (what to test, what the result means)
remain the human's, per the agency principle (`docs/design/00-meta-spec.md` §2.1).

## Notes

- Most consumers will bind a general engineering-workflow tool they already use.
  `defendable-science` deliberately does not name one — pick whatever your team uses.
- A repo with no separate engineering backend can treat these capabilities as
  "the researcher (with their assistant) designs, plans, and implements directly,"
  storing the same `design.md`/`plan.md` artifacts.
