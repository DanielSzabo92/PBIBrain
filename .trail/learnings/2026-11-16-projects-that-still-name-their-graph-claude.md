---
title: Projects that still name their graph brain.lbug no longer open; the owner chose no compatibility
author: Claude
date: 2026-11-16
branch: claude/practical-ramanujan-3xd2o3
cost: { minutes: 1, tokens: 1258 }
id: l-8e00e860
scope: repo
status: active
replaces: l-c3a3fb57
src: agent
touches:
  - backend/graph/sqlite_store.py
  - backend/desktop/host.py
---

## Decided
- The store no longer accepts a `.lbug` file name; the graph file is `brain.sqlite`. This reverses the earlier learning that kept `.lbug` readable, because the owner asked for every LadybugDB-era leftover to go with no backward compatibility.

## Watch out
- An existing project whose `.pbibrain/brain.json` says `"database": "brain.lbug"` fails to open, because the store treats an unknown suffix as a folder and the file already sits there. Fix by hand: set it to `brain.sqlite` and rescan, or delete `.pbibrain` and open the folder again (the settings API refuses database changes, so the app cannot do it). The README says this under "Project file".
- Do not add `.lbug` back to the accepted suffixes without asking the owner, otherwise the removed compatibility returns.

In the code: backend/graph/sqlite_store.py (SQLiteStore.__init__, accepted suffixes `.sqlite`, `.db`), backend/desktop/host.py (_open_project writes `brain.sqlite`).
