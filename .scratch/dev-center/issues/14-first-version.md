# What is in the first version, and what is the build order?

Type: grilling
Status: resolved
Blocked by: 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13

## Question

Which functions, object types, and source kinds are in the first version? In which order do the parts get built? Which acceptance tests prove each part? Write the result into the technical design document.

## Context

- From "What must change so that the change guard accepts create, delete, and rename?": the guard work is in its gates, not in the contract schema. Build items: canonical TMDL proof and full TOM tree compare, PBIR create and delete coverage, app write record in place of the sandbox receipt, identity-map rules for create and delete, linked rename pair, "merge" policy profile, one Apply dialog with all approvals, and a "format only" apply. Cloud deploys run only after the guard accepts a local copy.
- From "How does the Change Plan engine work?": build items: plan compiler (plan steps to operations), phase and dependency sort, removal policies, token-exact DAX rewrite, report rebind, deterministic lineageTags, prerequisite steps, a bridge write command for model operations, a Python PBIR writer, and an all-or-nothing local apply. ADR candidates: deterministic lineageTags and token-exact rewrite.
- From "Which impact data does the backend give to the UI?": build items: Impact item shape and phrase catalog, upstream Needs walk through the alignment, report-only graphs for other reports of the target model, blocking rules in validation, cascade preview, Offer record (pages, visuals, filters), wireframe data, and scanner support for PBIR positions and groups.
- From "How does the app find and store naming rules?": build items: name tokenizer, detector with support counts (limits 5 objects and 80%, as settings), rule file read and write, rule checker (warning only, only for new or changed names), built-in case-insensitive name clash check (blocking), deterministic name proposer with rule IDs, rules screen data, and copy of a rule set from a different model.
- From "What are the exact agent tools?": build items: eight MCP tools in the existing server, proposal HTTP endpoints, the server-side 0.9 and reason checks, accept, reject, accept-all, and Apply only in the pywebview JS API, the endpoint allowlist test, one error shape with fixed codes, `plan_validate` quick and full modes, and a stated limit plus a setup warning about agent shell access.
- From "How does the app store a merge session?": build items: session folder `.pbibrain/sessions/<session ID>/` with canonical `session.json` and append-only `log.jsonl`, atomic save, schema version and forward migration, Source Fingerprints (file manifest, `LastSchemaUpdate`, report definition hash), row hashes and the "source changed" marks with a blocking check before Apply, fingerprint update from the app write record, `.pbibrain/.gitignore` for runtime files, secret check before save, session lock, and the `session_id` to `connection_id` rename in `connection.json` (the app still reads the old key).

## Answer

Resolved on 2026-10-31. The user (through the orchestrator session) accepted all 16 proposed defaults. Addition from the user to decision 1: the technical design keeps the full cloud write design as version 1.1, so that its build tickets need no new map.

Result: [Technical design](../../../docs/DEV_CENTER_TECHNICAL_DESIGN.md) and ADRs 0001 to 0003 in `docs/adr/`.

### Decisions

1. **Release split.** Version 1 = full local merge plus cloud read (cloud model as donor, "Pull to local PBIP", cloud reports read for impact). Version 1.1 = cloud write (XMLA delta deploy, Fabric `updateDefinition`). The design of version 1.1 is in the technical design (section 10.4, build steps S12 and S13).
2. **Local source kinds.** Read: PBIP with TMDL or TMSL, standalone TMDL folder, `model.bim`, PBIR, PBIR-Legacy. Write target: TMDL and PBIR only. Other targets get a fixed message.
3. **Target kinds.** Existing local source, "Empty" (minimal PBIP skeleton), "Copy of <local source>".
4. **Merge Choices.** All six. "Take properties" for measures, columns, relationships. Report measures: promote, and copy into the target report. "Model measure into a `byConnection` report" is later.
5. **Report carry-over.** Pages (with fix-ups), visuals, page, visual, and report filters. Refused with a reason: bookmarks, sync slicer groups, custom visuals, static resources. No theme copy.
6. **Model types for create and copy.** Tables, columns, measures, relationships, hierarchies, calculation groups and items, UDFs (compatibility level 1702+), RLS with OLS, partitions and shared expressions. Field parameters: table copy and DAX rewrite only, shown as "not checked".
7. **Accepted-state writes.** All accepted-state changes and Apply go only through the pywebview JS API. HTTP has reads and proposal endpoints only. Browser dev mode uses a JS API mock.
8. **Code location.** New package `backend/devcenter/` (sources, session, alignment, compare, naming, plan, impact, apply, contracts). New bridge commands in the existing .NET project.
9. **Build order.** S0 foundations, S1 scanner, S2 session and sources, S3 alignment and compare, S4 naming, S5 plan, S6 impact, S7 writers, S8 guard, S9 local apply, S10 agent tools, S11 cloud read; S12 and S13 cloud write (1.1). Parallel lanes are in the design.
10. **Test rules.** Offline acceptance tests, no Desktop, no cloud. Bridge tests need the .NET 8 SDK. Cloud tests use recorded fakes. A manual real-tenant checklist before release.
11. **Real-tenant prerequisite.** Task T1 for the user: register the Entra app and run the checklist (also confirms "getDefinition needs write permission").
12. **Cloud reports of a cloud model.** "Reports In Group" in the workspace of the model only; other workspaces are "not checked". No admin scanner API.
13. **Large models.** No hard limit. Performance budgets as automated tests on a generated set (5 sources × 5,000 objects, 200 visuals): compare under 10 s, plan and impact under 5 s, quick validate under 5 s.
14. **Desktop open check.** Unsaved changes = blocking. Open and saved = warning. Bridge not reachable = warning.
15. **Later list.** Cloud write (1.1), value check, service principal, file watcher, perspectives, translations, themes, KPIs, detail rows, bookmark copy, sync slicer groups, custom visuals, mobile layout, approximate visual alignment, model measure to report measure.
16. **ADRs.** 0001 canonical TMDL proof, 0002 deterministic UUIDv5 lineageTags, 0003 accepted-state writes only in process. No ADR for token-exact rewrite.
