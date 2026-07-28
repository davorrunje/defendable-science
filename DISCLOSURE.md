# Disclosing AI use — and citing Defendable Science

`defendable-science` helps you use AI in research **honestly**: you (not the AI) make
and sign off every material decision, you can defend the work, and evidence is
provenance-tracked. This page is how you *tell your readers that* — a short,
truthful **AI-use disclosure** you can put in a paper, plus how to **cite** the
tool.

This is also, deliberately, how Defendable Science spreads: a disclosure that helps
you (venues increasingly require an AI-use statement) and, because it names the
protocol you followed, points other researchers to it. See ADR-0025.

## What it is *not*

- **Not a seal of honesty.** Defendable Science does not certify that your research is
  honest — it gives you a *structured, truthful way to disclose* what you and the
  AI each did, backed by your own recorded sign-offs. Readers judge; the statement
  just tells them what happened and links the record.
- **Not automatic or mandatory.** The disclosure is *proposed* to you (see
  [`paper-synthesis`](skills/paper-synthesis/SKILL.md)); you review, edit, and
  decide whether to include it. It is yours, in your words.

## The AI-use disclosure (template)

Put this in a *Use of AI* / Acknowledgments / methods statement. `paper-synthesis`
drafts it **from your actual provenance record** (who signed off which decisions,
which `run-ref`s back which results, what the AI drafted) — so it is evidence-based,
not boilerplate. Edit freely.

> **Use of AI.** This work was conducted with AI assistance under the
> *Defendable Science* protocol (github.com/davorrunje/defendable-science). Every material
> scientific decision — the hypotheses, whether results are real, what to publish,
> and all claims — was made and signed off by the named authors, who understand and
> can defend the work. AI tools were used for [literature search, bookkeeping and
> formatting, drafting] and **not** to generate conclusions or fabricate evidence;
> datasets and results are provenance-tracked. Decision record: [link / commit].

Keep it truthful: only claim what the record shows, and cut any line that isn't
true of your project.

## Citing Defendable Science

For now, cite the repository (a `CITATION.cff` is included, so GitHub's *"Cite this
repository"* works):

```bibtex
@software{defendable_science,
  title  = {defendable-science: a research-workflow plugin for honest, defensible AI-assisted research},
  author = {Runje, Davor},
  year   = {2026},
  url    = {https://github.com/davorrunje/defendable-science}
}
```

> **Transition:** a short report on Defendable Science will be posted to **arXiv** and
> then submitted to a venue. When the preprint exists, `CITATION.cff`'s
> `preferred-citation` will point at it, and this BibTeX will be replaced by the
> arXiv (then published) reference. (Tracking: the "arXiv report" issue.)

## Optional: a repo badge

If you keep your research in a public repo, you can add a discovery badge (this
describes the *disclosure*, it does not certify honesty):

```markdown
[![AI use: disclosed with defendable-science](https://img.shields.io/badge/AI%20use-disclosed%20with%20defendable--science-f9463c?style=flat-square&labelColor=2a1cc8)](https://github.com/davorrunje/defendable-science)
```

## How it reaches you (the automatic step)

You should not have to remember this. When `paper-synthesis` finalizes a paper —
after the publish `decision` is signed off — it **proactively proposes** the
disclosure (drafted from your record) and the citation, for you to adopt or
decline. That is the whole growth mechanism: useful to you, honest, and opt-in.
See ADR-0025 and [`paper-synthesis`](skills/paper-synthesis/SKILL.md).
