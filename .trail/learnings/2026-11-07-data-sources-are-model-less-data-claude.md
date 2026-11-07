---
title: "Data sources are model-less DATA_SOURCE nodes read statically from M, the text TMDL reader now reads partitions, and Lineage puts Sources after Models"
author: Claude
date: 2026-11-07
branch: claude/data-source-lineage-10
cost: { minutes: 12, tokens: 227985 }
id: l-40fe711a
scope: repo
status: active
src: agent
touches:
  - backend/graph/m_sources.py
  - backend/graph/data_sources.py
  - backend/impact/sources.py
  - tests/test_data_source_lineage.py
  - README.md
  - backend/graph/loader.py
  - backend/scanner/pbip.py
  - backend/impact/analyzer.py
  - backend/api/graph.py
  - backend/api/app.py
---

## Decided
- One DATA_SOURCE node per source object (SQL table, lakehouse table, dataflow entity, file, URL). Its id is a hash of connector kind + location (case-folded), and it has no model_id, so two models that read the same object share the node (`model_ids` lists them). That is the "common object" for the overview ticket (#14).
- SOURCES_FROM goes from the PARTITION or SHARED_EXPRESSION to the DATA_SOURCE. Query → shared expression/parameter stays the existing REFERENCES edge; a second edge type for the same link was not added.
- M is tokenised, never evaluated. Known connectors only; text literals, `let` steps holding a literal and model parameters (an expression that is a text literal with optional `meta`) are substituted. Any other `X.Y(` call outside the M standard library families, or a connector argument that is not readable, marks the query `check_status: not_checked`, `not_checked_reason: m_not_read`, `not_checked_detail`. That reuses the #9 not-checked fields, so Overview, Lineage badges and the Inspector show it with no new UI.
- A DATA_SOURCE impact target makes the impact INCOMPLETE when any query in the graph is not checked (that query might read the same source).
- `upstream_sources` is added to the impact report only when non-empty, so guard snapshot impact ids (which hash the report) stay unchanged; DATA_SOURCE is not in the snapshot FACT_TYPES either.

## Tried and ruled out
- Lineage lanes Sources › Queries › Models: MODEL CONTAINS SHARED_EXPRESSION then flowed expression → model → every table, so each visual's upstream showed the sources of all shared expressions. Lanes are Models › Sources › Queries › Tables instead.

## Watch out
- The text TMDL reader (project scan) skipped partitions until now; it reads `partition X = m` / `= entity` blocks and the `source` body up to the first dedent. Direct Lake entity partitions resolve through `expressionSource`.
- `_M_COMMENT` in the loader strips `//` inside strings; the new tokenizer does not, so URLs survive.
- A model slice of the graph (`get_graph(model_id=...)`) adds the DATA_SOURCE nodes its queries read, since they have no model_id.

In the code: backend/graph/m_sources.py, backend/graph/data_sources.py, backend/graph/loader.py (_build_edges), backend/scanner/pbip.py (_parse_partition), backend/impact/sources.py, backend/impact/analyzer.py, backend/api/graph.py, backend/api/app.py (get_overview), frontend/src/lineage.js (LANES), tests/test_data_source_lineage.py.
