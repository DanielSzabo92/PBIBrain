---
title: "Report usage roles live on USES edge properties, report links are FACT edges, and the usage summary is computed on read"
author: Claude
date: 2026-11-07
branch: claude/usage-roles-11
cost: { minutes: 9, tokens: 188969 }
id: l-cb37b895
scope: repo
status: active
src: agent
touches:
  - backend/graph/usage_links.py
  - backend/inference/usage_roles.py
  - tests/test_usage_roles.py
  - backend/scanner/normalization.py
  - backend/context/builder.py
---

## Decided
- The field-well role of a visual binding is stored on its `USES` edge (`properties.role` is the stable kind such as value, category, legend, tooltip, slicer_field, sort, conditional_formatting; `projection` keeps the PBIR well name such as Y; `roles` lists every use when one field sits in several wells). One edge per visual and field stays, because the edge ID is keyed on type, from, to and source.
- Drillthrough, tooltip page, visual interactions, slicer sync and conditional formatting are FACT edges (`DRILLS_THROUGH_TO`, `TOOLTIP_PAGE`, `INTERACTS_WITH`, `SYNCED_WITH`, `FORMATS_BY`). A `DRILLS_THROUGH_TO` with `via: field` repeats Power BI's own rule (the visual uses a drillthrough field of the page); `via: button` is an explicit drillthrough button.
- A drillthrough or tooltip page's binding fields are `USES` edges from the PAGE (role drillthrough_field or tooltip_page_field), so a field's impact reaches the page.
- The derived summary ("KPI value on 3 cards", "only as tooltip", "only on hidden pages", "unused in any report") is INFERRED and computed on request by the usage profile; it goes into brain_context (`usage_roles`) and the Inspector, and is never stored.

## Tried and ruled out
- Storing the derived facts or the drillthrough reachability as INFERRED edges: the review queue lists every INFERRED edge with status candidate, so each would show up as a semantic suggestion to approve.

## Watch out
- The lineage payload carries `role` on USES edges only; the new link edge types are not in the lineage edge set, so Lineage and Matrix drawings are unchanged.
- Visual interactions name visuals by their PBIR `name`; they are resolved per page while the page's visuals are normalized.

In the code: backend/scanner/normalization.py (_usage_bindings, _visual_links, _page_binding, Normalizer._normalize_page_usage), backend/graph/usage_links.py, backend/inference/usage_roles.py, backend/context/builder.py (usage_roles), tests/test_usage_roles.py.
