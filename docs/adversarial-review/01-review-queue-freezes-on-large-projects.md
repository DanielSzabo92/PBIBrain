# 01 · Review queue downloads the whole graph and freezes the app

**Severity:** P0 (blocks use) · **Criteria:** performance, accomplishes its goals

## Evidence (measured)

Large test project: 8 models, 24 reports, 13,731 objects, 41,942 relationships, 11,528 review items.

| Step | Result |
|---|---|
| Click **Review queue** | `GET /api/brain` returns **163 MB** of JSON in 29 s |
| Parse + render | one main-thread task of **99 s**; the window is dead for ~2 min 17 s in total |
| DOM after render | **377,813 elements** (every one of the 11,528 rows is mounted) |
| Scroll | 18 long tasks, worst 525 ms |
| Meanwhile | every other request waits (see 04); `/api/pending-changes` took 24 s |

The Inspector has the same dependency: "Loading review evidence…" waits for the same 163 MB payload.

Cause, in code:

- `frontend/src/App.jsx:288` `loadSnapshot()` calls `transport.getSnapshot()` → `/api/brain` (`transport.js:38`), which is every node and edge with full properties.
- `ReviewQueue` (`App.jsx:1699`) filters, sorts and renders the whole list in the browser. The visual contract asked for `content-visibility: auto` beyond 50 rows; that only skips paint, not React mount cost.

## Solution

1. **A dedicated, paged review endpoint.** `GET /api/review?tab=queue&issue=&type=&model=&report=&sort=&offset=&limit=100` returns only row data: `id, target {id, name, type, scope}, suggestion, reason, confidence, issue`. Plus `total` and `facets` (counts per issue, type, model) so the filters and the tab labels never need the full list. Evidence detail for one row loads on expand: `GET /api/review/<id>`.
2. **Never call `/api/brain` from the UI.** Remove `snapshot` from `ReviewQueue`, the Inspector evidence block and the Overview widgets (see 05). Keep `/api/brain` only for export.
3. **Virtualise the list.** Fixed 44 px rows make this simple: a windowed list (`@tanstack/react-virtual`, 4 kB) with 10 rows of overscan, fetching the next page when the window passes 70 % of loaded rows. J/K navigation moves a logical index and scrolls it into view.
4. **Bulk actions on the server.** "Approve all" sends the current filter (`POST /api/review/bulk {filter, decision}`), not 11,528 ids, and returns one undo token.
5. **Inspector evidence** reads `GET /api/objects/<id>/review` for that one object.

## Acceptance

- Opening Review queue on the 13.7k-object project: first rows visible in < 500 ms, no long task over 100 ms, DOM under 3,000 elements.
- Response for one page under 100 kB.
- Scrolling 11,528 rows holds 60 fps.
