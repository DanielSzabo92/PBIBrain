---
title: "Writing project files while Power BI Desktop has them open can lose work, and reading a cloud report needs write permission"
author: Daniel
date: 2026-10-30
branch: docs/dev-center-spec
cost: { minutes: 1, tokens: 9898 }
id: l-7db3a03c
scope: repo
status: active
touches:
  - ".scratch/dev-center/issues/05-desktop-open.md"
  - ".scratch/dev-center/map.md"
  - ".scratch/dev-center/issues/03-fabric-report-api.md"
  - docs/powerbi-desktop-bridge-cli.md
---

## Watch out
- Power BI Desktop does not apply external file changes by itself. It shows an "Apply external changes" banner. "Apply" reloads the full report or model and discards unsaved Desktop work. "Cancel" keeps Desktop's version, and a later Desktop save can overwrite the external change. Before the app writes, check that the target has no unsaved changes in Desktop (the Desktop bridge can tell this).
- The Fabric REST getDefinition call for a report needs read AND write permission on the report. A cloud report connection with access type "Read" can thus fail to load. Test with a real workspace before the design relies on it.
- A Fabric updateDefinition replaces the full report definition. Send all parts, not only the changed parts.

In the code:
- Findings: branches research/desktop-open and research/fabric-report-api (not merged).
- Tickets: .scratch/dev-center/issues/05-desktop-open.md, 03-fabric-report-api.md
- Desktop bridge notes: docs/powerbi-desktop-bridge-cli.md
