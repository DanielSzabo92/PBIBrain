# How does the app read and write cloud reports through the Fabric REST API?

Type: research
Status: resolved
Blocked by: 

## Question

Which endpoints read and update a report definition (PBIR parts)? Which permissions and sign-in scopes do they need? Are the calls long-running? Which formats and limits apply (PBIR versus PBIR-Legacy, byConnection references, size)? How does the app find the reports that use a given semantic model?

## Answer

Findings: branch `research/fabric-report-api`, file `.scratch/dev-center/research/03-fabric-report-api.md` (not merged, not pushed).

- Read with `POST /v1/workspaces/{workspaceId}/reports/{reportId}/getDefinition`. Write with `POST .../updateDefinition`.
- Both calls need the scope `Report.ReadWrite.All` or `Item.ReadWrite.All`, and read and write permission on the report.
- Both calls can return 202 (long-running). Poll `GET /v1/operations/{id}`, then get the result.
- A definition is PBIR or PBIR-Legacy, never both. An update replaces the full definition: send all parts as InlineBase64.
- A deployed `definition.pbir` must use a `byConnection` reference.
- The Fabric report list has no dataset ID. To find the reports of a model, use the Power BI "Reports In Group" API or the scanner API.
- Limits: 1,000 pages, 1,000 visuals for each page, 300 MB report files. The request size limit is not documented.
- IMPORTANT: getDefinition needs write permission. Thus a cloud report with access type `Read` can fail to load. A test with a real workspace must confirm this. If it is true, a read-only user can only read reports through a different path (for example, a local PBIP export).
