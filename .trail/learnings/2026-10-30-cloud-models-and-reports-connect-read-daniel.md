---
title: "Cloud models and reports connect read-only by default, and merges happen in a local copy first"
author: Daniel
date: 2026-10-30
branch: docs/dev-center-spec
cost: { minutes: 7, tokens: 109201 }
id: l-0f9843d5
scope: repo
status: active
touches:
  - docs/DEV_CENTER_FUNCTIONAL_SPEC.md
---

## Decided
- The user must choose the access type when connecting to a cloud model (XMLA) or a cloud report (Fabric REST). The default is Read. Writing is optional and needs Read/Write.
- The default flow is: pull the cloud model to a local PBIP folder, merge there, then deploy. A direct XMLA write is an option, not the default.
- The agent can only propose choices. It never gets a tool that applies changes.

## Watch out
- After an XMLA write to a model that Power BI Desktop authored, the service can no longer download that model as a PBIX file (Microsoft documentation). Show this warning before the first XMLA write, and take a TMDL backup first.

In the code:
- Spec: docs/DEV_CENTER_FUNCTIONAL_SPEC.md, sections 4.2, 9.3, 10, 14 (Q4, Q5).
