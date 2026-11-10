---
title: "The first Trail-backed graph store and the trail-pbi fork do not work together yet, and the fork's name lookup crosses models"
author: Claude
date: 2026-11-10
branch: claude/kind-meitner-je8fhi
cost: { minutes: 9, tokens: 136406 }
id: l-6c8423cc
scope: repo
status: active
src: agent
touches:
  - backend/graph/repository.py
---

## Watch out
- The Python store on feat/trail-pbi-backend (backend/graph/trail_store.py) writes files that look like Trail's, but the trail CLI never reads them: pointed at that folder, `trail ask` rebuilds the graph and returns nothing. PBIBrain still reads only its own `.graph/brain-facts.json`. The TypeScript trail-pbi package is never called from the backend.
- trail-pbi looks up DAX, relationship and visual references by name across the whole repo (resolve.ts resolvePbiEdge / pickUniqueOrSameFile) and does not limit the search to one model. With several models open this gives two kinds of wrong result. A name defined only in another model links to that model: a SalesA measure `[Discount Rate]` linked to SalesB's measure. A name defined in more than one model links to nothing: SalesB `SUM(Sales[Cost])` got no edge.
- On merge_lab, trail-pbi found no edges for TMDL relationships, for `byPath` report→model bindings, for RLS filters, for field parameters, for calculation items or for some visuals. The project scan finds all of these.
- TrailStore.initialize deletes an existing `brain.lbug` *file* (an old LadybugDB database), with no warning, and creates an empty folder in its place. The default path is still data/brain.lbug.
- Every upsert rewrites every store file and every card. With 20k nodes, one upsert takes about 14 s.

In the code: backend/graph/trail_store.py (initialize, _node_path_and_span), backend/graph/repository.py (_TrailConnection), trail-pbi/src/graph/resolve.ts:813-942.
