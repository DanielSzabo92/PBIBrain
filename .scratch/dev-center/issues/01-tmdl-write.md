# How can the app write TMDL safely?

Type: research
Status: resolved
Blocked by: 

## Question

How can the app create, delete, rename, and replace model objects (tables, columns, measures, relationships, hierarchies, calculation groups, field parameters, functions, roles, perspectives, translations) and save them as TMDL with Microsoft's own library (TOM / Microsoft.AnalysisServices), through the existing .NET bridge? How stable is the output format (file layout, ordering, lineageTag, whitespace), so that a diff shows only the real changes? What does the library not support?

## Answer

Findings: branch `research/tmdl-write`, file `.scratch/dev-center/research/01-tmdl-write.md`, with a local experiment against TOM 19.114.12 in `.scratch/dev-center/research/01-tmdl-write-experiment/` (not merged, not pushed).

- Write path: read the model, change the TOM object tree, serialize TMDL to a temporary folder, read it again to verify, then copy only the changed files to the target. TOM wrote every object type in the question.
- The bridge is read-only now. Write needs a new bridge command: input is a list of operations, output is the changed TMDL files. No server connection is necessary.
- Rename: `RequestRename` changes only the name. It does not change DAX text. The app must rewrite DAX references itself. Relationships, perspectives, and translations follow the new name automatically.
- lineageTag: TOM gives a new object no tag. `Clone()` copies the tag. TOM rejects a duplicate tag only inside one collection, so the app must check the full model.
- Relationships, roles, perspectives, cultures, calculation items, and partitions have no lineageTag. Alignment by tag cannot work for them. (Input for the compare-rules ticket.)
- Output is deterministic: the same model gives the same bytes (tabs, CRLF, no BOM).
- WARNING: do not serialize directly into the user's `definition` folder. The folder write rewrites every file and deletes each `.tmdl` file that it did not write.
- TOM blocks a user-defined function below compatibility level 1702.
- TOM does not check DAX and does not stop broken references on delete. The app must validate before it writes.
- Not documented: the field-parameter metadata format, rename fixup on a server, and whether Power BI Desktop writes the same bytes as TOM.
