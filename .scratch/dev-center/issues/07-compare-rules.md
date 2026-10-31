# What are the match and compare rules?

Type: grilling
Status: resolved
Blocked by: 06

## Question

For each object type: which properties count when the app says "same" or "different"? What does the default normalization ignore, and what does "strict" keep? How does the app show a property difference in plain words? How do the match steps (lineageTag, name, moved, possible rename, manual) rank, and what happens when two steps give different answers?

## Context

- From "Which new object types must the graph learn first?": this ticket owns the property list for each object type in the first version.
- From "How can the app write TMDL safely?": relationships, roles, perspectives, cultures, calculation items, and partitions have no lineageTag. They need a different match key.

## Answer

Resolved with the user on 2026-10-31. The user accepted all proposed defaults. Fact found first: the current `brain_compare` compares canonical JSON only (`backend/diff/snapshots.py`, `compare_properties`), and the DAX parser (`backend/dax/parser.py`) gives the tokens for DAX normalization.

### Alignment

1. Alignment keys for objects with no lineageTag:

| Object type | Alignment key |
|---|---|
| Relationship | The two columns at its ends, in any order |
| Calculation item | Calculation group + item name |
| RLS role | Role name |
| OLS permission | Role + table (+ column) |
| Partition | Table + partition name. If each side has only one partition, the table alone. |
| Report page | Page id, then page display name |
| Visual | Visual id only (works for copies of the same report). No approximate visual alignment in the first version. |
| Report measure | Home table + name |

2. Step order and conflicts: the app runs the alignment steps in the spec order. An object that aligns at a step leaves the pool. The lineageTag always wins. Example: the lineageTag aligns target `[Sales]` with donor `[Revenue]`, and the donor also has a different `[Sales]`. Result: one row "Renamed", and one more row for the donor `[Sales]` with a "name clash" warning. If one source has the same lineageTag two times, the app ignores the lineageTag for those objects and shows a warning.
3. One to one: each object aligns with at most one object in each source. A row starts from the target object. A donor object with no target object gets its own row (target = Missing).
4. Possible rename: "same expression" means equal after default normalization, same object type, and both objects are not aligned yet. The app shows a proposal only when there is exactly one candidate on each side. Otherwise it shows no proposal, and the user can align by hand. The user must always confirm.
5. "Moved" means only a different home table (measures and report measures). A different display folder is a property difference: "Different: display folder changed". This changes section 6.3 of the functional spec (the user agreed).
6. One state for each cell, plus a "changed" mark when properties are not equal. Precedence: Type conflict, Missing, Renamed, Moved, Different, Same. Example: "Renamed + changed".

### Compare

7. Properties that count. A table row is "Different" only for its own properties. Its columns, measures, hierarchies, and partitions are separate rows.

| Object type | Properties that count |
|---|---|
| Measure | expression, format string (or format string expression), display folder, description, hidden, data category |
| Data column | data type, source column, format string, display folder, description, hidden, summarize-by, sort-by column, data category, key |
| Calculated column | the data column list + expression |
| Table | description, hidden, data category; calculated table: + expression |
| Relationship | cardinality, cross-filter direction, active, security filter direction, assume referential integrity |
| Hierarchy | levels (order and columns), display folder, description, hidden |
| RLS role | model permission, filter expression for each table, OLS for each table and column |
| Partition | mode, M text |
| Calculation item | expression, order, format string expression |
| Shared expression | M text, kind |
| Report measure | expression, format string, display folder |

The app does not compare role members, because they change for each environment.

8. Default compare ignores: lineageTag, sourceLineageTag, annotations, `changedProperty` lines, line ending style (CRLF or LF), and JSON key order. Strict compare also compares annotations and the exact text. Strict ignores only line ending style and JSON key order, because these never change the model.
9. DAX normalization (default): ignore whitespace, comments, keyword and function name case, name case in references (`Sales[amount]` = `Sales[Amount]`), and quotes on table names (`'Sales'` = `Sales`). Do not ignore a table prefix on a measure reference (`[Total]` is not equal to `Sales[Total]`).
10. Compare through the alignment: the default compare reads references through the alignment. Example: the target renamed `[Sales]` to `[Revenue]`. A donor reference to `[Sales]` then equals a target reference to `[Revenue]`. The cell shows "Same" with the note "same after rename". Strict compare does not do this.
11. M text, descriptions, and format strings: exact text, but ignore line ending style and spaces at the end of lines. The app does not parse M (see "Which new object types must the graph learn first?").
12. Plain words: each property has one fixed phrase, for example "expression changed" or "format string changed". For short values, the app also shows old and new value (example: "hidden: No → Yes"). For long text (DAX, M), it shows only the phrase. The code diff opens on request.
13. Report pages and visuals: compare the full JSON without key order. The plain words name the area that changed: "position", "visual type", "fields", "filters", "formatting".
