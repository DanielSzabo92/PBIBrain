---
title: "Never let the model library write straight into a project's model folder"
author: Daniel
date: 2026-10-30
branch: docs/dev-center-spec
cost: { minutes: 1, tokens: 3068 }
id: l-20745fb8
scope: repo
status: active
touches:
  - ".scratch/dev-center/issues/04-pbir-copy.md"
  - ".scratch/dev-center/map.md"
  - ".scratch/dev-center/issues/02-xmla-access.md"
  - backend/adapters/tabular_metadata/dotnet/Program.cs
---

## Watch out
- The TOM TMDL folder write rewrites every file and deletes each .tmdl file that it did not write itself. Serialize to a temporary folder, read it back to verify, then copy only the changed files into the user's project.
- RequestRename changes only the object name. DAX text that refers to the old name stays unchanged. The app must rewrite the DAX references itself.
- TOM gives a new object no lineageTag, Clone() copies the tag, and TOM checks duplicate tags only inside one collection. Check tag uniqueness over the full model.
- Relationships, roles, perspectives, cultures, calculation items, and partitions have no lineageTag. Do not rely on the tag to match them across models.
- TOM does not check DAX and does not stop broken references on delete. Validate before writing.

In the code:
- Bridge: backend/adapters/tabular_metadata/dotnet/Program.cs (read-only now), bridge.py
- Findings and experiment (TOM 19.114.12): branch research/tmdl-write, .scratch/dev-center/research/01-tmdl-write.md
