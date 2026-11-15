---
title: "A full scan spends its time in name normalising and one quadratic de-duplication, and Cancel reaches inside formula analysis through a context variable"
author: Claude
date: 2026-11-15
branch: claude/vibrant-franklin-h8aafq
cost: { minutes: 12, tokens: 209631 }
id: l-9044f058
scope: repo
status: active
src: agent
touches:
  - HANDOFF.md
  - backend/dax/analyzer.py
  - backend/graph/loader.py
  - backend/dax/visitors.py
  - backend/text_keys.py
  - backend/inference/engine.py
  - backend/projects.py
---

## Decided
Formula analysis and the graph builder call a cancellation checkpoint per expression and between stages. The project scan sets it through a context variable, so no scanner signature changed, and outside a project scan the checkpoint costs one lookup. Because the formula step was one call (15 of 18 s), a cancel used to wait for the whole step; now it lands within one expression.
The AST key and name normalisers are memoised per text and the meta-key set is built once, because the same few keys were normalised millions of times on the 13,731-object project. Observation edges are de-duplicated with a set of ids, because the old list scan compared every edge with every kept edge (88 million comparisons).
Per-source scan state is kept in a side file beside the project file, so Settings shows the last result after a restart.

## Watch out
Measured on the generated large project: full scan 23.0 s to 11.7 s; a cancel during formula analysis took 18.9 s and now takes under 0.1 s. Profile with cProfile on `ProjectService.scan` before guessing: the costs were not in parsing.

In the code: backend/scanner/checkpoint.py (CHECKPOINT, checkpoint(), checkpoints()); backend/dax/analyzer.py DaxAnalyzer.analyze; backend/graph/loader.py FactGraphBuilder.build; backend/dax/visitors.py _norm/_META_NORMS; backend/text_keys.py alnum_key; backend/inference/engine.py observation de-dup; backend/projects.py source-states.json.
