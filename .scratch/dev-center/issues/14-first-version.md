# What is in the first version, and what is the build order?

Type: grilling
Status: open
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
