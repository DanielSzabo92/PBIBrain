---
title: The graph is stored only in SQLite; LadybugDB and its .lbug file name were removed with no migration
author: Claude
date: 2026-11-16
branch: claude/practical-ramanujan-3xd2o3
cost: { minutes: 25, tokens: 164566 }
id: l-161fedec
scope: repo
status: active
src: agent
touches:
  - backend/graph/repository.py
  - backend/graph/sqlite_store.py
  - backend/desktop/host.py
  - tests/test_product_api.py
---

## Decided
- The owner asked to remove all LadybugDB-era code and not keep backward compatibility. The graph database file is `brain.sqlite`; new projects write `"database": "brain.sqlite"`. A `.lbug` path is no longer recognised as a database file.
- Removed: the native DLL loader, the Cypher translation wrapper and `query_graph`, `LadybugRepository`, `ladybug_schema`, the JSON schema migration (a JSON graph file must carry the current `schema_version`), the repository's alias method names, and the LadybugDB/OpenSSL bundling in CI and the desktop build. The build script only downloads the WebView2 bootstrapper now (`scripts/prepare-webview2.ps1`).
- `GraphRepository(path, use_sqlite=False)` (was `use_native=False`) is the in-memory or JSON-file graph that scans stage into and tests use.
- The UTF-8 active code page in the Windows manifest stays: removing it would change Python's default encodings in the packaged app.

## Watch out
- A project created before this change has `"database": "brain.lbug"` in `.pbibrain/brain.json` and fails to open. Change it to `brain.sqlite` (and rescan), or delete `.pbibrain` and open the folder again. The settings API refuses database changes, so it is a hand edit.
- `SQLiteStore.replace_all` now owns the write transaction: `BEGIN IMMEDIATE`, write, Trail export, commit, then a passive WAL checkpoint whose failure only logs a warning. A failed write rolls back and raises `RuntimeError("Graph replacement failed: ...")`.

In the code: backend/graph/repository.py, backend/graph/sqlite_store.py (replace_all, path suffixes), backend/desktop/host.py (_open_project), tests/test_product_api.py (rollback and checkpoint tests).
