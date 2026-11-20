---
title: "The UI mock server accepts payloads the real desktop backend refuses, so merge UI tests pass while the real app fails"
author: Daniel
date: 2026-11-19
branch: test/desktop-merge-e2e
id: l-9b8b859b
scope: repo
status: active
touches:
  - backend/adapters/tabular_metadata/bridge.py
  - backend/devcenter/apply/pipeline.py
  - frontend/src/devcenter/components/CompareGrid.jsx
---

## Decided
Test merge UI flows against the real desktop backend (pywebview JS API with the real TOM bridge), not only against the mock server. A frontend payload must pass the JSON schemas in backend/devcenter/contracts/jsapi/*.request.json.

## Tried and ruled out
- Trusting the frontend tests that use tests/devcenter_ui_server.py. The mock accepts the grid choice shape {choice, source}, but the real contract requires {kind, source_id} with additionalProperties false. The mock also knows filter state not_same; the backend filter_rows does not.

## Watch out
- In the code: CompareGrid.jsx sends {choice, source}; jsapi.py call() validates against contracts/jsapi. No error toast shows when the contract refuses the call.
- The plan property names (hidden, m_text, active, cross_filter_direction) do not match ModelWriter.cs (is_hidden, expression/partition_expression, is_active, cross_filtering_behavior).
- compare/extract.py _relationship sorts the ends by name and flips the cardinality text; ModelWriter.cs uses ends[0] as fromColumn and ignores cardinality, so relationships come out reversed.
- apply/pipeline.py write() swallows the real exception as write_failed. Reproduce outside the app to see it.
- Evidence: docs/evidence/desktop-merge-e2e-2026-11-19/REPORT.md
