---
title: The graph file brain.lbug is a SQLite database; the name is left over from LadybugDB
author: Claude
date: 2026-11-16
branch: claude/lucid-maxwell-d0z6x3
cost: { minutes: 1, tokens: 1483 }
id: l-c3a3fb57
scope: repo
status: active
src: agent
touches:
  - backend/desktop/host.py
  - backend/api/app.py
  - backend/graph/sqlite_store.py
  - backend/projects.py
---

## Decided
The SQLite store accepts a `.lbug` file name because projects created in the LadybugDB era name their graph `brain.lbug` in brain.json; otherwise those projects would fail to open.

## Watch out
- A `brain.lbug` file is SQLite, because the store writes SQLite to whatever path the config names: open it with sqlite3, not LadybugDB tools.
- Renaming the default graph file must keep `.lbug` paths readable, otherwise existing projects lose their graph.

In the code: backend/desktop/host.py:378 (default written into new brain.json), backend/api/app.py:1414 and :1471 (`data/brain.lbug` defaults), backend/graph/sqlite_store.py:144 (accepts `.lbug`, `.sqlite`, `.db`), backend/projects.py:127 (`database` is required). LadybugDB was replaced in commit 8206c89 (#56).
