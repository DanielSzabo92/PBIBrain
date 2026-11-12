# 04 · One slow request blocks every other request

**Severity:** P0 · **Criteria:** performance

## Evidence

- `backend/api/app.py:842-870` serves with `wsgiref.simple_server.make_server`, which handles one request at a time. There is also a global `request_lock` (`app.py:467`).
- Measured: while `/api/brain` ran (29 s), `/api/pending-changes` took **24 s** and `/api/devcenter/session` **23 s**. The Merge models view sat on "Loading the session" the whole time; Settings could not load.
- The same happens during a scan: status polling, search and the chat all queue behind it.
- Responses are uncompressed: `/api/lineage` is **7.5 MB**, `/api/graph` 451 kB for 80 objects.

## Solution

1. **Threaded server.** Replace `make_server` with a threading WSGI server (`socketserver.ThreadingMixIn` + `WSGIServer`, or `waitress` with 8 threads; waitress is pure Python and freezes cleanly with PyInstaller). Keep host/origin checks as they are.
2. **Reader–writer lock instead of one RLock.** Reads (overview, search, object, graph, lineage) share; scan, review decisions and config writes take the write lock. With the cached summaries from 03, most reads never touch the store.
3. **Long work off the request thread.** Scan already reports progress; make it a background job (`POST /api/scan` → `202 {job_id}`, `GET /api/jobs/<id>`), and do the same for documentation export. The UI then shows a determinate progress bar with object counts.
4. **Compression.** gzip any JSON response over 1 kB when the client sends `Accept-Encoding: gzip` (lineage 7.5 MB → roughly 400 kB).
5. **Budgets.** Reuse the per-tool character budgets that MCP already has: fail a test if any UI endpoint exceeds 1 MB uncompressed on the large fixture, except `/api/lineage`.
6. **Cancel stale work.** `transport.js` should pass an `AbortSignal` per view so leaving a view cancels its fetches.

## Acceptance

- With a 30 s scan running, `/api/overview`, `/api/search` and `/api/pending-changes` each answer in < 200 ms.
- `/api/lineage` transfers < 600 kB on the large fixture.
