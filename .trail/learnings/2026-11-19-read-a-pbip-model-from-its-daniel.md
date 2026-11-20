---
title: "Read a PBIP model from its definition folder, or a TMDL view script breaks the read"
author: Daniel
date: 2026-11-19
branch: test/desktop-merge-e2e
id: l-12c3e0c7
scope: repo
status: active
touches:
  - backend/adapters/tabular_metadata/bridge.py
  - backend/devcenter/apply/pipeline.py
  - frontend/src/devcenter/components/CompareGrid.jsx
---

## Decided
The compare read must give the model's definition folder to the TOM bridge, not the .SemanticModel folder. The write step already does this.

## Tried and ruled out
Moving the TMDLScripts folder out of the source is a workaround only. Power BI Desktop opens the source correctly, so the source is not at fault.

## Watch out
TOM reads every .tmdl file under the folder it gets. A TMDL view script (createOrReplace) in TMDLScripts then fails the read. The compare grid drops that source with no message.

In the code: backend/devcenter/compare/extract.py _read_model passes source.model_dir. bridge.py write_model already selects model_dir/definition. Checked 2026-11-20: read of Finance.SemanticModel fails, read of Finance.SemanticModel/definition passes.
