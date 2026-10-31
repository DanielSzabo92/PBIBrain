# Map: Power BI Development Center

Label: wayfinder:map

## Destination

A technical design document (`docs/DEV_CENTER_TECHNICAL_DESIGN.md`) plus short decision records (ADRs). The design answers every "how" question of the functional spec, fixes the first version and the build order, and is complete enough to split into build tasks.

## Notes

- Baseline: [Functional specification](../../docs/DEV_CENTER_FUNCTIONAL_SPEC.md) (accepted). Do not reopen its decisions without the user.
- Domain: Power BI semantic models (TMDL, TMSL, XMLA) and reports (PBIR). Use the Microsoft Learn MCP server for facts.
- Conversation tickets: call the "grilling" and "domain-modeling" skills. Research tickets: call the "research" skill.
- Word list: `CONTEXT.md`. Use "Merge Choice" for the choice on one row (not "Decision").
- Language: ASD-STE100 for all text.
- Standing decisions from charting (2026-10-31):
  - The change guard is reused for its safety checks only: scope check, file coverage check, backups, undo. No Docker isolation, because the app writes and the agent only proposes.
  - Cloud sign-in in the first version: interactive Microsoft account sign-in only.
  - One user on one Windows PC. Sessions are local files. Sharing goes through git.
  - Research subagents: Haiku or Sonnet for light tickets, Opus for hard tickets.

## Decisions so far

<!-- one line per closed ticket -->

- [How can the app write TMDL safely?](issues/01-tmdl-write.md): change the TOM tree, serialize to a temp folder, verify, copy only changed files; app must rewrite DAX on rename and check lineageTags itself; many object types have no lineageTag.
- [How does the app read and write cloud reports through the Fabric REST API?](issues/03-fabric-report-api.md): getDefinition / updateDefinition (long-running, full replace, PBIR only for write); read also needs write permission, so "Read" access can fail.
- [What happens when the app changes files while Power BI Desktop has the project open?](issues/05-desktop-open.md): Desktop shows an "Apply external changes" banner and reloads all; unsaved Desktop work can be lost, so apply needs an "open in Desktop" check.
- [How does the app read and write cloud models through XMLA?](issues/02-xmla-access.md): TOM + MSAL (WAM) in the .NET bridge; `SaveChanges()` sends only changes, but the app must apply the plan to TOM itself; write conditions are found only from the write error.
- [Which PBIR versions must the app support, and how does it copy report objects safely?](issues/04-pbir-copy.md): read all versions, write each file in its own version; vendored schemas are outdated and must be updated first; copy needs an old-to-new name map and a fixed list of reference rewrites.
- [Which new object types must the graph learn first?](issues/06-object-coverage.md): add hierarchies, RLS roles with OLS, report measures, partitions; bookmarks read only; perspectives, translations, themes later; unknown objects stay unchanged and show as "not checked".
- [What are the match and compare rules?](issues/07-compare-rules.md): lineageTag wins, then the spec steps, one to one; keys for objects with no lineageTag; fixed property list for each type; default compare ignores tags, annotations, DAX format and reads through renames; "Moved" is a table change only.
- [What must change so that the change guard accepts create, delete, and rename?](issues/08-guard-reuse.md): canonical TMDL proof plus a full TOM tree compare against the plan; an app write record replaces the sandbox receipt; "merge" policy profile with no value test and one explicit Apply approval; the plan sets new lineageTags; a no-tag rename is a linked pair; each reference rewrite is its own exact operation.

## Not yet specified

- Optional value check: run the same measure in a donor and in the target through a live connection, and compare a sample of results. Depends on the XMLA research and the first-version scope.
- Service principal sign-in (a later step after the first version).
- How the app finds the cloud reports that use a cloud target model (workspace scan, permissions, cost).
- Limits for very large models and reports (time, memory), and what the app does above them.
- What the app does when a source changes on disk during an open merge session, beyond "mark the affected rows".

## Out of scope

- The later features in section 13 of the spec: merge templates, golden measure library, duplicate finder, unused object finder, three-way Git merge. Ruled out at charting: the user excluded them from this destination.
- UI look and layout. Ruled out at charting: a separate round. This map defines only the data that the backend gives to the UI.
- Writing PBIX or PBIR-Legacy files, data refresh, and Power Query logic edits. Ruled out by the spec.
