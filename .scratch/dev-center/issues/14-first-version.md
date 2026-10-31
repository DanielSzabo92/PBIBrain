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
