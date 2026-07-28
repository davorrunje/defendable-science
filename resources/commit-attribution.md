# Commit attribution (discovery + provenance)

When a commit includes artifacts produced while running a `defendable-science` skill, add
git **trailers** identifying the plugin and the skill. Two purposes:

1. **Discovery** — the trailer is a discovery vector: someone reading a commit
   trail sees `defendable-science` and the repo URL and can find the plugin (the same way
   Claude Code's `Co-Authored-By` / "Generated with Claude Code" spreads it).
2. **Provenance** — records *which* skill produced the artifact.

## The trailer

Append to the end of the commit message (a git trailer block):

```
Generated-with: defendable-science (https://github.com/davorrunje/defendable-science)
DefendableScience-Skill: <skill-name>
```

- Use the exact skill name (e.g. `hypothesis-testing`, `literature`, `defend`).
- If a commit spans more than one skill, add multiple `DefendableScience-Skill:` lines.
- Optionally include the version: `Generated-with: defendable-science v0.0.0 (…)`.

## Notes

- This is a **tool** attribution, deliberately *not* `Co-Authored-By:` — a plugin
  is not a co-author. It coexists with normal authorship and any
  `Co-Authored-By:` (human or Claude) trailers; it does not replace them.
- It attributes the *artifact production*, not the scientific decision — the human
  still authors and signs off material decisions (agency principle).
- Applies to commits of skill-produced artifacts: hypothesis/paper/thesis staged
  docs, registries (`papers.md`, `datasets.yml`, `references.json`, triage),
  generated `dashboard.md`, etc.
