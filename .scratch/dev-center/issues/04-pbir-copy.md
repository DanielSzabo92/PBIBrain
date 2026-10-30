# Which PBIR versions must the app support, and how does it copy report objects safely?

Type: research
Status: resolved
Blocked by: 

## Question

Which PBIR schema versions exist now, and which must the app read and write? What are the rules to copy a page, a visual, a bookmark, a filter, and a report-level measure (reportExtensions.json) from one report to another: names and IDs, references to fields, references between files (pages.json, bookmarks, visual groups, drillthrough, tooltips), static resources, themes? How does the app rebind a field reference to a different model object?

## Answer

Findings: branch `research/pbir-copy`, file `.scratch/dev-center/research/04-pbir-copy.md` (not merged, not pushed).

- Current upstream schemas: report 3.3.0, page 2.1.0, visualContainer 2.13.0, pagesMetadata 1.1.0, bookmark 2.1.0, bookmarksMetadata 1.0.0, reportExtension 1.0.0, versionMetadata 1.0.0.
- The repo vendors only old versions (report, page, visualContainer 2.0.0; pagesMetadata 1.0.0) and has no bookmark, reportExtension, or version schema. Confirmed in `backend/adapters/pbir/schemas/`.
- The validator fails closed on an unknown `$schema`. Thus files from a current Power BI Desktop get `PBIR_SCHEMA_UNSUPPORTED`. The vendored set must be updated before any PBIR write work.
- Version policy: read all versions; write a changed file in its own version. Mixed versions in one report are normal.
- The repo has no PBIR write or copy path now.
- Names: letters, digits, underscore, hyphen. A visual name is unique in its page. Bookmark and report-measure names are unique in the report. On a clash, rename and keep an old-to-new map.
- References to fix after a copy or rename: page order, visual group parent, drillthrough page binding, visual interactions, bookmark sections and target visuals, bookmarks.json.
- Rebind a field: replace Entity and Property in every field location (query state, sort, filters, page binding, bookmarks, report-measure DAX). Rebind a report: `datasetReference` in definition.pbir.
- A report-level measure goes into reportExtensions.json. Its name must be unique, and its entity must exist in the target model.
- Not documented: sync slicer groups, theme and resource copy rules, which Desktop build reads which schema version, behavior with a broken reference.
- Recommendation for the first version: refuse to copy bookmarks, sync slicer groups, and custom visuals. (Input for the first-version ticket.)
