# PBIBrain product review — 2026-09-08

## Product boundary

Windows-local, provider-independent metadata retrieval for agents. One Brain
project groups multiple semantic models and reports. Source artifacts stay
read-only. Stable object IDs, exact expressions, provenance, explicit uncertainty,
and bounded responses are the product. No hosted account, built-in chatbot,
embedding service, or Power BI model editor is needed.

## Findings and implementation scope

| Priority | Evidence | Problem | Change |
| --- | --- | --- | --- |
| P0 | `scanner/pipeline.py` scans replace repository contents | Scanning another model can remove the first | Explicit project manifest; stage all sources, detect conflicting identities, publish together |
| P0 | `graph/repository.py::_sync_native` deletes before independent inserts | Failed writes can leave partial persistent data | Transactional replacement and memory rollback |
| P1 | `api/objects.py`, CLI search | Unbounded substring search, weak disambiguation | Add deterministic ranked, paginated retrieval with model/report scope and match evidence |
| P1 | `api/app.py::__call__` | Wildcard CORS and unchecked request size on local mutation endpoints | Local origin/host checks, JSON writes, bounded bodies, actionable errors |
| P1 | `frontend/src/transport.js` | Full snapshot is the only UI read transport | Scoped graph/search and configuration workflow |
| P1 | CLI and unused `config/brain.json` | No coherent project setup or simple shared entrypoint | Project config, project scan, serve, agent context commands |
| P2 | Existing graph limits | Truncation loses the focus object and hides omitted counts | Preserve focus; scope before traversal; disclose total/truncation |
| P2 | `_last_scan` | File modification or current time pretends to be scan time | Report only known scan metadata; unknown is null |

Baseline: 146 unittest tests, 1 pre-existing README heading failure, 4 native
skips in this shell. Existing README edits and untracked user files are preserved.

## Later, deliberately separate

1. Documentation export: deterministic Markdown from the same project snapshot,
   with model/report inventories, exact DAX, relationships, lineage, source
   evidence, unresolved bindings, and scan identity. Optional PDF rendering later.
   Never turn inferred business meaning into asserted fact.
2. Structural understanding: reuse scoped graph payloads for table relationships,
   report-to-model usage, and impact paths. No second graph store or 3D renderer.
3. Release gate: representative multi-model PBIP corpus, retrieval precision and
   ambiguity evaluations, scan memory/time measurements, native fault/reopen tests,
   Windows clean-machine install, and Power BI Desktop external-tool acceptance.
4. Distribution: signed Windows package and optional External Tools registration
   after the local workflow is proven. Keep CLI/HTTP contracts provider-neutral.

Global adoption is a long-term objective, not a readiness claim. Parser coverage,
remote model resolution, large-model scale, and installer support must be measured
and documented before a stable release.

## Implemented and checked

The project service, ranked retrieval, optional read-only MCP adapter, bounded
graph API, loopback transport checks, transaction rollback, and Configuration /
Search / Graph workflow are implemented. Existing single-source APIs remain
compatible. Technical documentation generation remains a later feature.

Acceptance uses the real Finance Aevum PBIP together with a second model fixture:
2 models, 1 report, 186 nodes and 318 edges in native LadybugDB. The combined graph
survives close/reopen. Browser checks exercise configuration save, native scan,
search, object inspection, and a centered 13-node graph. All 145 source files
retain their SHA-256 hashes across the GUI scan. A native failure injected after
actual graph deletion proves transaction rollback and close/reopen recovery.

Remaining release gates: clean-machine Windows installation, Power BI Desktop
External Tools integration, large-project performance, and a wider corpus of
real reports. The identity file and native database are separate persistence
units: ordinary write failures roll back, but crash-atomic publication across
both files is not claimed. Native scan time and validation state are runtime
metadata and become unknown after reopening the database.

Final checks (2026-09-09): 178 Python tests passed with native Ladybug enabled;
Python compilation passed; frontend build and 5 transport tests passed. Actual
MCP stdio initialization, tool discovery, and all five tools passed against the
native project server. Inspector at 1265 px has no horizontal overflow and puts
the expression first. Scoped graph refits after asynchronous loading.

**Resolved regression — exit after completed writes:** interrupting the test
server through the execution harness left its disposable database with an
invalid WAL record on reopen. This is not resolved by normal transaction
rollback tests. A fresh real-PBIP scan, orderly close/reopen, and stable-ID rescan
passed afterward. Source files and the user's normal database were not involved.
The same failure reproduced after two real-PBIP scans followed by `os._exit(0)`.
Checkpointing after each committed replacement fixed that reproduction: all
186 nodes and 318 edges reopened successfully. Regression coverage also checks
that checkpoint failure cannot roll back an already committed in-memory index;
that condition logs a warning requiring orderly shutdown. Termination during
an active write/checkpoint and power-loss recovery still need release testing.

## Current phase — Markdown export

The documentation export implementation is complete. `brain --config
<brain.json> export-markdown` emits deterministic Markdown from the canonical
project snapshot to stdout or to a new `--output` file; existing files and
protected project paths are rejected. The export carries model/report
inventories, exact stored expressions, fact versus inference and observation
classes, source evidence, unresolved bindings, unknown scan metadata, and a
deterministic snapshot identity without inventing a scan ID. It is
canonical-snapshot only; review overrides are excluded. Stop `brain serve`
before direct database CLI use.

Native-enabled validation passed: 183 Python tests with no skips, Python
compilation, and a combined native two-model/one-report export with all 25
canonical expressions present, deterministic output, 132 source hashes
unchanged, and the graph unchanged after close/reopen. The final artifact
rerun also passed at 316224 bytes: repeated exports were identical, and UTF-8
stdout matched the output file exactly. This validates the export phase;
separate release gates above remain.
