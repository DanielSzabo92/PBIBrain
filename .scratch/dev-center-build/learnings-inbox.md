## Ticket 10
- Learning: a Radix dialog that the app opens from its own state needs DialogTrigger, because without it focus does not go back to the button when the dialog closes, and verify_focustrap fails.
- Learning: give the gate runner a long time limit, because one verify_states run on a dark snapshot can take more than 3 minutes on Windows and then stops with no result.
- Learning: Toast animations must not animate opacity from zero because axe accessibility contrast checks sample elements during the transition.
- Learning: The test web server serves `frontend/dist` directly because it checks production bundle behavior, which requires a rebuild when CSS changes.

## Ticket 13
- Learning: Align mock server fixtures strictly with S4 schemas (rule_id and support count/total) before implementing UI components to prevent contract validation mismatches.

## Ticket 12
- Learning: In virtualized grids, filter or query changes must reset the scroll position to zero; otherwise, row range calculations based on a previously scrolled offset produce zero or negative render slices when fewer rows match.
- Learning: Fast scroll performance rules must render light placeholder cells for non-essential columns to maintain frame budgets while retaining ARIA grid attributes.
- Learning: In-flight state updates in rapid keyboard navigation must be synchronized via immediate refs to avoid stale closures over focused cell coordinates.

## Ticket 11
- Learning: Plan compiler result must include `"sources": list(self.data.sources.keys())` so `plan_hash()` can compute SHA-256 over all plan facets without KeyError.
- Learning: Token-exact DAX rewriting must use ANTLR4 lexer character spans (`token.start`, `token.stop + 1`) to preserve whitespace, comments, and casing outside rewritten identifier tokens.
- Learning: Under UC3, `GET session` (`session_summary()`) must return cached plan status or `plan_state: "computing"` lazily without invoking plan compilation or compare computation.

## Ticket 15
- Learning: In large scale impact analysis with 5000 objects, canonical JSON hashing for unused fields like `impact_paths` causes high CPU overhead (2.7 seconds for 75000 records). Making path serialization optional and pre-caching node metadata tables in Python reduces impact derivation time by more than 70 percent (from 5.1 seconds to 1.6 seconds).

## Ticket 16
- Learning: In TMDL model serialization, candidate paths must strictly validate against the input model definition folder to prevent destructive in-place rewrites.
- Learning: TOM canonical check detects format-only differences (LF line endings, quoted identifiers, blank lines) without altering semantic tree equivalence, enabling safe format-only promotion.
- Learning: TOM tree compare must walk unmodeled collections like Perspectives and Cultures to detect and guard changes outside the PBIBrain graph schema.
- Learning: TOM 19.118.3 rejects lineageTag on root model nodes; lineage tags must strictly attach to child objects (tables, columns, measures, hierarchies).


## Ticket 17
- Learning: When `compile_plan` emits `COPY_PAGE` followed by `COPY_VISUAL` and `REBIND_FIELD` for child visuals of the copied page, the PBIR writer must map donor row keys (`page:<id>`, `visual:<page>/<id>`) to the clash-resolved candidate IDs so subsequent `COPY_VISUAL` and `REBIND_FIELD` operations target the renamed page and visual folders without duplicating visuals.
- Learning: `validate_report_documents` requires document keys to start with a `<name>.Report/` root prefix to trigger `PBIR_PAGE_COVERAGE_MISMATCH`, `PBIR_ACTIVE_PAGE_UNRESOLVED`, and `PBIR_PAGE_ID_PATH_MISMATCH` checks even when the candidate output directory name does not end with `.Report`.
- Learning: Semantic filters in `filterConfig.filters[].filter` bind `Where` column/measure expressions through `From` table aliases (`SourceRef.Source`), so `REBIND_FIELD` on a filter must update both the top-level `filter.field` and any matching `From` entity and `Where` property.
