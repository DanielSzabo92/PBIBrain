# Product

<!-- impeccable:product-schema 1 -->

> Written by `/impeccable init` without a live interview: the audit brief asked
> for answers to be inferred from the repository (README.md, CONTEXT.md,
> frontend/README.md, docs/, the e2e fixtures). Every line below is sourced from
> those files. Lines marked _(inferred)_ are reasonable readings of them that
> the owner has not confirmed.

## Platform

web (rendered inside a Windows desktop shell: `PBIBrain.exe` hosts the same
React UI in a pywebview/WebView2 window; developers also open it in a browser
at `http://127.0.0.1:8000/`).

## Users

Power BI developers and BI engineers who own one or more PBIP projects
(semantic models in TMDL/TMSL, reports in PBIR). They open Brain Inspector next
to Power BI Desktop and a code editor to answer "what is this object, what uses
it, what does it depend on, and can I trust its meaning?" and, in the
Development Center, to merge objects from donor models into one target.
_(inferred)_ They are expert, keyboard-capable, and work on large desktop
monitors for long sessions.

## Product Purpose

PBIBrain turns model metadata, report bindings, DAX, descriptions and review
decisions into one canonical, provenance-aware graph. Brain Inspector is the
local window onto that graph: search, graph exploration, single-object
inspection, a review queue for inferred meanings, model summaries for agents,
and the Development Center for guarded merges. Success is a developer finding
the exact object and its lineage in seconds, and trusting what they see
because fact, inference and observation are always distinguished.

## Positioning

The Brain is infrastructure, not an assistant: it does not generate queries,
compile DAX, or edit Power BI files outside a guarded, reviewed change plan.
Its distinguishing mechanism is provenance: every edge is factual, inferred or
observed, and inferred meaning only becomes trusted through explicit review.

## Operating Context

- Runs locally; no AI provider, API key or cloud service is required.
- Generated files live under `.pbibrain` in the user's project folder; Power
  BI sources stay untouched.
- Used beside Power BI Desktop, Tabular Editor / DAX Studio and VS Code
  _(inferred from the audience)_.
- Desktop window minimum is about 1024 px wide (see `app.css` breakpoint
  comment); narrow layouts exist for resilience, not as a primary target.

## Capabilities and Constraints

- Views: Overview, Search, Graph, Inspector, Review queue, Development Center,
  Settings (project sources, graph colours, model summary, keyboard).
- Graph colours are user-editable and persisted in `brain.json`; nodes,
  legend, search results and Inspector share that palette, so the UI chrome
  must never compete with artifact colours.
- Status is always labelled in text; solid / dashed / dotted lines encode
  factual / inferred / observed evidence.
- Terminology is fixed by CONTEXT.md (PBIP Project, Semantic Model Artifact,
  Report Artifact, Merge Session, Target, Donor, Alignment, Change Plan).

## Brand Commitments

Name: PBIBrain / "Brain Inspector". Existing mark in `branding/` and
`src/components/BrandMark.jsx`. No other binding visual commitments were
found.

## Evidence on Hand

Fixture projects in `tests/graph_ui_server.py` and
`tests/fixtures/devcenter_ui/`. No customer quotes, metrics or testimonials
exist; none may be invented.

## Product Principles

1. Exactness over summary: show the real name, the real formula, the real path.
2. Provenance is always visible: fact, inference and observation never look alike.
3. The tool recedes; the user's model is the content.
4. Nothing changes the user's Power BI files without an explicit, reviewable step.

## Accessibility & Inclusion

The repo ships an axe-based a11y sweep (`frontend/e2e/axe.js`,
`devcenter-a11y.spec.js`) and WCAG 2.4.11 focus-not-obscured handling. Target
WCAG 2.2 AA in both themes.
