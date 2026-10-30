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

- [How does the app read and write cloud reports through the Fabric REST API?](issues/03-fabric-report-api.md): getDefinition / updateDefinition (long-running, full replace, PBIR only for write); read also needs write permission, so "Read" access can fail.

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
