# 13 · The Inspector opens on a manual instead of the model

**Severity:** P1 · **Criteria:** easy and obvious, information yield

## Evidence

![Inspector empty](evidence/inspector-empty.png)
![Inspector on a visual](evidence/inspector-visual.png)

- Clicking **Inspector** shows a three-step text tutorial ("Press Ctrl+K…", "Double-click…", "Use the Search page…") and three buttons that leave the view. The one useful element — the list of models — is a row of chips at the bottom.
- There is no way to browse: a Power BI developer expects Model ▸ Table ▸ Columns / Measures, as in Power BI Desktop, Tabular Editor and DAX Studio. The earlier desktop audit (`docs/ui-audit/desktop.md`) already recommended this; it is still missing.
- On an object: the Definition card of a visual is a label plus a large empty grey box; "Loading review evidence…" waits for the 163 MB payload (01); the breadcrumb says "Graph › Rank by Region" while the sidebar says Inspector; there is a second "Back to graph" link below it.
- Loading one column took 2.6 s and 153 kB (03).
- "Factual" here, "From source" in the visual contract, "Fact" in the legend — three words for one provenance state.

## Solution

1. **Dock an object tree on the left of the Inspector** (280 px, resizable, collapsible with Ctrl+B):
   - Roots: Models, Reports, Data sources. Model ▸ Tables ▸ (Columns, Measures, Hierarchies) · Relationships · Roles · Calculation groups. Report ▸ Pages ▸ Visuals.
   - Lazy children (`GET /api/tree?parent=`), virtualised, type chips, counts on folders, status glyph for review/validation issues, filter box on top (`/` focuses it).
   - Arrow keys, Home/End, type-to-select, Enter opens. Selection syncs with the route (10).
2. **Remove the tutorial card and the three buttons.** With no selection, the right side shows the selected model's summary (counts, top measures, unused objects) — content, not instructions. Shortcuts live in F1.
3. **Object page by type:**
   - Measure: DAX first (full width, copy button), then format string, display folder, description.
   - Column: data type, source column, sort-by, summarisation, relationships it takes part in.
   - Visual: a schematic of the field wells (Axis, Values, Legend, Filters) with the bound fields as chips — that fills the empty grey box with the most useful fact about a visual.
   - Never render an empty panel; omit it.
4. **Right rail:** "Depends on" and "Used by" as two collapsible lists with counts, each row navigable; "Show in graph" opens the trace view (08).
5. **One breadcrumb**, the real path: `Sales Analytics › Orders › Total Orders Amount`, every segment clickable. Delete "Back to graph" (history does it, see 10).
6. Evidence for this object only (`/api/objects/<id>/review`), collapsed to one line: "3 suggestions · highest 97 %".
7. Use "From source / Suggested / Observed" everywhere (contract §4).

## Acceptance

- From a cold start a user can reach any measure with the mouse alone in three clicks, without typing.
- No instructional paragraph is visible in the Inspector.
