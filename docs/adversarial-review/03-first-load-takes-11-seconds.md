# 03 · First load takes 11–14 s because the overview is recomputed on every request

**Severity:** P0 · **Criteria:** performance

## Evidence (measured)

On the 13.7k-object project, with a warm database:

| Request | Time | Size |
|---|---|---|
| `GET /api/overview` | **10.7–12.2 s** | 4 kB |
| `GET /api/config` | 11.4 s (queued behind overview, see 04) | 1 kB |
| `GET /api/commonality?limit=1` | 1.9–3.0 s | 9 kB |
| `GET /api/search?q=…` | 0.5–0.9 s | 6 kB |
| `GET /api/objects/<one column>` | 2.6 s | 153 kB |
| `GET /api/graph?depth=1&limit=80` | 1.9–2.1 s | 451 kB |

The window shows an empty shell for about 14 s before any number appears. The same 11 s is paid again after every scan, review decision and reload.

Cause: `backend/api/app.py:75` `get_overview()` reads **all nodes and all edges** from the store, builds the **entire review queue**, and then counts them — to return 4 kB. Nothing is cached. `/api/objects/<id>` and `/api/commonality` have the same shape: load everything, then filter.

## Solution

1. **Compute the summary once per graph revision.** Give `GraphRepository` a monotonically increasing `revision` (bumped by scan, review decision, override). Cache `get_overview`, review facets and commonality by `(revision, overrides_revision)`. Build the cache at the end of `project.scan()` so the first paint after a scan is instant.
2. **Count in the store, not in Python.** Object counts by type and status are `GROUP BY` queries in the Ladybug store; add `count_nodes_by_type()` / `count_edges_by_status()` to the repository instead of `all_nodes()`.
3. **Indexed point reads.** `get_object` should fetch the node plus its direct edges by id (already keyed), not scan. Target < 50 ms and < 20 kB for a column; move the AST and raw source behind `?include=ast`.
4. **Search index.** Build an in-memory name/description/expression index (lower-cased trigram or simple prefix map) at scan time; 13.7k names should answer in < 30 ms.
5. **HTTP validators.** Send `ETag: "<revision>"` and honour `If-None-Match` so reloads return 304. Today every response is `Cache-Control: no-store` (`app.py:801`).
6. **Perceived speed.** While the first overview loads, render the real layout with skeleton rows after 300 ms (the contract's rule), and show the project name immediately from `/api/config`.

## Acceptance

- `/api/overview` < 100 ms warm, < 1 s cold on the 13.7k-object fixture.
- Time to first meaningful paint < 1.5 s.
- A pytest benchmark on the large fixture (see 22) guards these budgets.
