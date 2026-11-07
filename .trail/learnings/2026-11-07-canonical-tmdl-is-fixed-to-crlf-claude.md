---
title: "Canonical TMDL is fixed to CRLF in the TOM bridge, because Microsoft's serializer uses the OS line ending"
author: Claude
date: 2026-11-07
branch: claude/wonderful-johnson-24vmnu
cost: { minutes: 16, tokens: 93496 }
id: l-a2766856
scope: repo
status: active
src: agent
touches:
  - tests/guarded_fixture.py
---

## Decided
Canonical TMDL means Microsoft's TMDL serializer output with CRLF line endings, on every OS. The serializer writes Environment.NewLine, so on Linux/macOS it wrote LF and every baseline file was flagged non-canonical, which blocked all merge plans in CI and cloud sessions. All bridge commands now serialize through one helper that rewrites lone LF to CRLF after serialization.

## Watch out
- Any new bridge code that serializes TMDL must call the helper, not TmdlSerializer.SerializeDatabaseToFolder directly, or the canonical check becomes OS-dependent again.
- Python test fixtures that hash file bytes (the guard reference snapshot IDs) were recorded on Windows, where write_text turns "\n" into CRLF. Write such fixtures with newline="\r\n", or the recorded IDs will not match on Linux.
- The apply end-to-end test once chose SalesB's "Total Sales", which is a known rename (it becomes "Sales Amount") and is correctly blocked for its dependents. That is plan behavior, not a line-ending bug.

In the code: backend/adapters/tabular_metadata/dotnet/CanonicalTmdl.cs (CanonicalTmdl.SerializeToFolder), tests/guarded_fixture.py, .gitattributes (*.tmdl text eol=crlf; byte-exact folders keep -text and come later), CI job tom-bridge-linux.
