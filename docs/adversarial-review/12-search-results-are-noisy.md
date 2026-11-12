# 12 · Search: duplicates first, no match context, filters eat the top of the page

**Severity:** P1 · **Criteria:** accomplishes its goals, information yield

## Evidence

Query "total orders" on the large project (first screen of results):

- Rows 1–8 are **Alias** objects named "Total Orders Amount"; rows 9–16 are the real measures with the same name. The user wants the measure.
- 16 rows show the same name; the only difference is the model name in grey. Version copies are not folded (the graph folds them as ×8).
- The type is written out in a 110 px text column ("Alias", "Measure") next to an icon that already says it.
- No snippet: a hit inside a DAX formula or description looks identical to a name hit, so the user cannot tell why a row matched.
- Header block: h1 "Search" + a sentence + a labelled input + a second row of three labelled selects + "50 of 61 matches". Results start at 310 px; 13 rows fit on a 900 px screen.
- No preview: every candidate has to be opened in the Inspector and backed out of (and there is no Back, see 10).
- Search (sidebar), "Find an object…" (graph) and Ctrl+K are three different search boxes with three behaviours.

## Solution

1. **Rank real objects first.** Order: exact name › prefix › word match › description › formula; model objects before semantic ones. Aliases never appear as rows — a measure matched through its alias shows `aka "…"` in its snippet.
2. **Fold versions:** one row "Total Orders Amount · Orders · ×8 models" with an expander.
3. **Row = chip · name (match highlighted) · scope path in mono · snippet.** For formula hits show the matching line of DAX with the term highlighted. Drop the type text column.
4. **One filter bar, one line:** `[🔍 query…………] [Type ▾] [Model ▾] [Report ▾]`, labels inside the controls, active filters as removable chips. Remove the h1 sentence; the result count goes on the right of the bar. Results then start at ~120 px.
5. **Split view 44/56** (already in the visual contract, not built): arrow keys move the selection and the right side shows the live Inspector preview; Enter opens it.
6. **Empty query state:** recent objects and type chips with counts, instead of a blank panel.
7. **One search engine:** the palette, the graph finder and this page call the same endpoint with the same ranking; the palette's "See all results" lands here with the query in the route.
8. Type-ahead: debounce 120 ms, cancel the previous request (`AbortController`), keep old results dimmed while loading.

## Acceptance

- For "total orders" the first row is the measure, shown once with ×8.
- ≥ 20 result rows visible at 1440×900.
- A formula-only match shows the matching DAX line.
