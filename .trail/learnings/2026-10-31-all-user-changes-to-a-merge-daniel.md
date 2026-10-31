---
title: "All user changes to a merge session go only through the app window, and cloud write waits for version 1.1"
author: Daniel
date: 2026-10-31
branch: docs/dev-center-spec
cost: { minutes: 7, tokens: 247586 }
id: l-e8b436e3
scope: repo
status: active
touches:
  - ".scratch/dev-center/issues/14-first-version.md"
  - ".scratch/dev-center/map.md"
  - docs/DEV_CENTER_TECHNICAL_DESIGN.md
  - docs/adr/0001-canonical-tmdl-proof.md
  - docs/adr/0002-deterministic-lineage-tags.md
  - docs/adr/0003-accepted-state-only-in-process.md
  - backend/desktop/host.py
  - backend/api/app.py
---

## Decided
- Not only accept and Apply: every change to accepted merge-session state (create or open a session, add sources, set the target, Merge Choices, alignment overrides, removal policies, mappings, rule confirms, undo) exists only in the in-process desktop JS API. The local HTTP API gives reads and agent proposal endpoints only. Reason: the HTTP API has no authentication, so an HTTP write of a Merge Choice would let an agent shell skip the proposal step.
- Version 1 is the full local merge plus cloud read. Cloud write (XMLA deploy, Fabric report update) is version 1.1, because nothing is tested against a real workspace yet. Its design is already fixed in the technical design.

## Watch out
- Browser dev mode (Vite) cannot change session state. It needs a mock of the JS API.
- trail check reports a "conflict" on each document that mentions the rejected secret header for the local API. These are false matches: the documents repeat the rejection.

In the code:
- docs/DEV_CENTER_TECHNICAL_DESIGN.md (sections 14.2, 15, 16), docs/adr/0003-accepted-state-only-in-process.md, backend/desktop/host.py (JS API), backend/api/app.py (HTTP routes)
