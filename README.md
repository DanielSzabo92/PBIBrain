# Power BI Brain

Repository: [PBIBrain](https://github.com/DanielSzabo92/PBIBrain)

Power BI Brain is a reusable semantic-understanding layer for Power BI models
and reports. It turns model metadata, report bindings, DAX, descriptions, and
review decisions into a canonical, provenance-aware graph.

The Brain is infrastructure. It does not generate natural-language queries,
compile DAX, or edit Power BI models and reports.

## Setup guide

This guide is for running Power BI Brain on a Windows PC. The PBIBrain folder
and the Power BI project are separate. A Power BI project can be anywhere on
your computer; it does not need to be inside the PBIBrain folder.

### 1. Install the prerequisites

Install:

- Python 3.11 or newer.
- Node.js and npm for the Inspector web interface.
- The LadybugDB Python package and its matching native library. Installing
  PBIBrain installs the Python package, but Windows also needs
  `lbug_shared.dll`.
- Optional: Power BI Desktop if you want to use the Desktop Bridge.

The Desktop Bridge CLI requires Node.js 20 or newer. It is optional for
scanning PBIP files.

### 2. Open PowerShell in the PBIBrain folder

Use the folder where this repository is installed:

```powershell
cd C:\path\to\PBIBrain
```

Run the commands below from this folder. The default database is
`data/brain.lbug`, and the default identity file is
`config/identity.json`.

### 3. Install the Python backend

```powershell
python -m pip install -e .
```

Editable install means Python runs the code from this folder. Changes to the
repository are immediately available without reinstalling.

Check that the command is available:

```powershell
brain --help
```

If `brain` is not found, use the module form instead:

```powershell
python -m backend.cli.main --help
```

### 4. Configure the LadybugDB Windows library

Find `lbug_shared.dll` on a PC where LadybugDB is already configured:

```powershell
where.exe /R C:\ lbug_shared.dll
```

If it is not available, download the matching Windows shared library from the
[LadybugDB releases](https://github.com/LadybugDB/ladybug/releases). Use the
version that matches the installed Python package.

Set the DLL path in the current PowerShell window:

```powershell
$env:LBUG_C_API_LIB_PATH = 'C:\path\to\lbug_shared.dll'
$env:PATH = "$(Split-Path $env:LBUG_C_API_LIB_PATH);$env:PATH"
```

These environment variables apply only to the current PowerShell window. Set
them again in every new window, or add them to your Windows user environment.

Verify the backend and native library:

```powershell
brain status --json
```

If this reports that `lbug_shared.dll` is missing, the DLL path is wrong or
the DLL does not match the installed LadybugDB package.

### 5. Put the PBIP project anywhere

The normal Power BI project layout is:

```text
C:\models\Finance\
├── Finance.pbip
├── Finance.SemanticModel\
└── Finance.Report\
```

The `.pbip` file, `.SemanticModel` folder, and `.Report` folder normally sit
beside each other. They do not need to be beside or inside PBIBrain.

When Brain receives the path to `Finance.pbip`, it reads that project file and
follows its declared artifact paths. If no paths are declared, it looks for
`.SemanticModel` and `.Report` folders directly beside the `.pbip` file.

### 6. Scan the PBIP project

From the PBIBrain folder, provide the full path to the `.pbip` file:

```powershell
brain scan 'C:\models\Finance\Finance.pbip'
```

Do not use `model.json` for a PBIP project. That is a separate input mode for
standalone JSON metadata files.

After scanning, inspect the graph:

```powershell
brain status --json
brain search "net sales"
```

### 7. Start the Inspector web interface

Keep the first PowerShell window running and open a second one.

In the first window, start the API from the PBIBrain folder:

```powershell
cd C:\path\to\PBIBrain
python -m backend.api --db data/brain.lbug --overrides config/overrides.json
```

In the second window, install and start the frontend:

```powershell
cd C:\path\to\PBIBrain\frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173/` in your browser. The frontend proxies API
requests to `http://127.0.0.1:8000`.

### 8. Preserve project data when moving to another PC

Copy these files if you want to keep the existing graph and stable object
identities:

- `data/brain.lbug`
- `config/identity.json`
- `config/overrides.json`, if you have made review decisions

Keep the Power BI project files together. PBIX files are not parsed directly;
use the companion PBIP project and its `.SemanticModel` and `.Report` folders.

## What is implemented

The V1 pipeline is:

```text
Power BI metadata / PBIP files
        -> adapters and normalization
        -> canonical nodes and factual edges
        -> ANTLR DAX AST and deterministic analysis
        -> semantic candidates and report observations
        -> separate human overrides and validation
        -> Brain API, scoped context, and Inspector UI
```

Implemented capabilities include:

- Native LadybugDB persistence through a graph repository abstraction.
- Direct `.pbip` ingestion: TMDL semantic-model artifacts and PBIR report
  artifacts are read at the scanner boundary.
- JSON/mapping-based model and report adapters for API or test fixtures.
- Stable IDs based on native source IDs, persisted identity mappings, or
  persisted generated IDs. Display names are never identity.
- ANTLR4 DAX parsing into a source-located AST, followed by reference,
  dependency, filter, relationship, variable, function, and behavior analysis.
- Description-first semantic inference, selector discovery, selector options,
  defaults, business concepts, aliases, roles, confidence, and conflicts.
- Report usage observations (`OBSERVED_WITH`) kept separate from compatibility
  claims.
- Incremental scan classification: `UNCHANGED`, `CHANGED`, `NEW`, `DELETED`.
- Separate override storage, stale-override detection, and deterministic
  structural/reference/semantic validation.
- A stable in-process API, HTTP Inspector transport, task-scoped context
  packages, and a React Flow graph Inspector.

## Trust model

The graph keeps evidence classes distinct:

| Class | Meaning |
| --- | --- |
| `FACT` | Mechanically extracted structure or DAX/report fact. |
| `INFERRED` | Semantic interpretation proposed from evidence. |
| `OBSERVED` | Report co-occurrence or other observed usage; not proof of compatibility. |
| Human decision | Approval, rejection, edit, or override. Stored as lifecycle status or in the separate override file. |

Generated facts are never replaced by human overrides. Effective API payloads
apply overrides over generated records while the generated graph remains
inspectable.

## Technical requirements

- Python 3.11 or newer.
- LadybugDB Python package (`ladybug >= 0.20`) and its native shared library.
- Node.js and npm for the Inspector frontend. The Microsoft Desktop Bridge CLI
  requires Node.js 20 or newer.
- Optional: Power BI Desktop with the secure external-tool preview option
  enabled when using the Desktop Bridge for local open/status/reload/screenshot
  verification.

Install the Python package in editable mode:

```powershell
python -m pip install -e .
```

On Windows, LadybugDB also needs the matching `lbug_shared.dll`. Put the DLL
on `PATH`, or point directly to it:

```powershell
$env:LBUG_C_API_LIB_PATH = 'C:\path\to\lbug_shared.dll'
$env:PATH = "$(Split-Path $env:LBUG_C_API_LIB_PATH);$env:PATH"
```

The native graph store is the production path. The JSON repository is only an
explicit test double: `GraphRepository(..., use_native=False)`.

## Command reference

Run from the repository root. The defaults are `data/brain.lbug` and
`config/identity.json`.

### Optional: scan standalone JSON metadata

This mode is for standalone JSON metadata files or test fixtures. The files
must already exist at the paths provided. These are not the files inside a
PBIP project.

```powershell
brain scan .\model.json --report .\report.json
brain status --json
brain search "net sales"
brain object "model:abc/measure:123"
```

The module form works without the installed console script:

```powershell
python -m backend.cli.main scan .\model.json --report .\report.json
```

`build` is an alias for `scan`. Use `--db` and `--identity` before the command
to choose other paths:

```powershell
brain --db .\data\finance.lbug --identity .\config\finance-identity.json scan .\model.json
```

### Scan a PBIP project directly

The scanner detects an existing `.pbip` path, follows its declared semantic
model and report artifacts, and discovers the report when `--report` is not
provided:

```powershell
brain scan 'C:\models\Finance\Finance.pbip'
```

The project should retain its companion `*.SemanticModel` and `*.Report`
directories. PBIX files are not parsed by the Brain. The Desktop Bridge can
open a PBIX for Desktop control, but it is not a metadata extraction API.

### Run the local API and Inspector

Start the standard-library WSGI API:

```powershell
python -m backend.api --db data/brain.lbug --overrides config/overrides.json
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173/`. Vite proxies `/api` to
`http://127.0.0.1:8000`. Set `BRAIN_API_URL` when the API uses another local
address. The default bind is loopback; do not expose the unauthenticated local
API directly to a network.

## Canonical graph

Every node has this envelope:

```json
{
  "id": "model:abc/measure:123",
  "type": "MEASURE",
  "name": "Net Sales",
  "description": "Net invoiced sales after discounts.",
  "model_id": "model:abc",
  "report_id": null,
  "source_id": "123",
  "status": "factual",
  "source": "model_metadata",
  "properties": {}
}
```

Every edge has `id`, `type`, `from_id`, `to_id`, `source`, `confidence`,
`status`, `evidence`, `evidence_class`, and `properties`.

The ontology supports model and report objects including `MODEL`, `TABLE`,
`COLUMN`, `MEASURE`, `RELATIONSHIP`, `FIELD_PARAMETER`,
`SHARED_EXPRESSION`, `USER_DEFINED_FUNCTION`, `CALCULATION_GROUP`,
`CALCULATION_ITEM`, `REPORT`, `PAGE`, `VISUAL`, and the filter scopes. It also
supports semantic objects such as `BUSINESS_CONCEPT`, `SELECTOR`,
`SELECTOR_OPTION`, `CONFLICT`, and `SEMANTIC_ASSERTION`. Unknown future object
types are preserved rather than rejected.

Structural edges include `CONTAINS`, `BELONGS_TO`, `USES_MODEL`, `USES`,
`REFERENCES`, `DEPENDS_ON`, `RELATES_TO`, and `FILTERS`. DAX behavior adds
`MODIFIES_FILTER`, `ACTIVATES_RELATIONSHIP`, and
`MODIFIES_RELATIONSHIP`. Semantic edges include `CONTROLLED_BY`, `HAS_OPTION`,
`DEFAULTS_TO`, `SEMANTICALLY_MAPS_TO`, `SIMILAR_TO`, `ALIAS_OF`, `HAS_ROLE`,
and `HAS_BEHAVIOR`. Observed usage uses `OBSERVED_WITH`; conflicts use
`CONFLICTS_WITH`.

## Stable identity and overrides

Preferred identity order:

1. Native Power BI stable ID or lineage tag.
2. A persisted source mapping.
3. A persisted generated ID.

For example, renaming a measure does not change
`model:abc/measure:123` when the source supplies a stable ID. Generated
identity mappings are stored in `config/identity.json` and are ignored by
Git.

Human review records live separately in `config/overrides.json`:

```json
{
  "version": 1,
  "overrides": [
    {
      "target": "model:abc/measure:123",
      "property": "business_concept",
      "value": "net revenue",
      "status": "approved"
    }
  ]
}
```

The review API supports approve, reject, edit, override, remove, and stale
override resolution. A rescan reapplies records by stable ID and reports
missing targets instead of silently moving an override.

## DAX analysis

DAX is parsed once through the ANTLR4 lexer/parser in `backend/dax/`. The AST
preserves nested structure and source spans. The analyzer then resolves
qualified columns, tables, measures, UDFs, shared expressions, and supported
relationship/filter constructs against canonical nodes.

Analysis is stored on source nodes and produces deterministic factual edges
with evidence such as AST locations, extractor names, and source expression
fragments. Syntax failures become diagnostics; parsing does not invent business
meaning.

## Incremental sync and validation

`Scanner.scan()` performs the initial build. Later calls to
`scan_incremental()`, `rescan()`, or `sync()` compare stable IDs and source
fingerprints. Changed expressions and dependent consumers are re-analyzed;
unchanged analysis is reused where safe.

Validation runs after scanning and review reconciliation. It checks graph
integrity, references, DAX dependencies, semantic contradictions, selector
semantics, report bindings, source disappearance, orphan objects, and override
integrity. Issues use `INFO`, `WARNING`, `ERROR`, or `BLOCKING` severity.

Read-only Power BI validation hooks are available through
`backend.validation.PowerBIValidationHook`,
`ReadOnlyValidationAdapter`, and `run_validation_query`. Query results are
traceable evidence; the Brain does not mutate Power BI.

## Brain API

`backend.api.app.BrainAPI` provides:

```text
search_objects(query)
get_object(id)
get_neighbors(id, edge_types=None)
get_dependencies(id)
get_dependents(id)
get_usage(id)
get_semantics(id)
get_context(target, task=None)
find_path(from_id, to_id)
validate_selection(object_ids)
```

Inspector-specific helpers include `inspect_object()`, `get_graph()`,
`get_review_queue()`, and `apply_review()`.

The WSGI transport exposes the same operations through routes such as:

```text
GET  /api/overview
GET  /api/brain
GET  /api/objects
GET  /api/objects/{id}
GET  /api/objects/{id}/neighbors
GET  /api/objects/{id}/dependencies
GET  /api/objects/{id}/dependents
GET  /api/objects/{id}/usage
GET  /api/objects/{id}/semantics
GET  /api/graph
GET  /api/path?from_id=...&to_id=...
GET  /api/context/{id}
GET  /api/review
POST /api/review
GET|POST /api/validate-selection
```

`GraphRepository.query_graph()` exists for trusted internal diagnostics. It is
not exposed as an unrestricted downstream-agent API.

## Context compiler

`get_context(target, task)` returns a relevant subgraph instead of dumping the
database. The stable package contains:

```json
{
  "target": {},
  "scope": {"model_ids": [], "report_ids": []},
  "semantics": [],
  "relationships": [],
  "dependencies": [],
  "controls": [],
  "usage": [],
  "constraints": [],
  "evidence": [],
  "confidence": {},
  "warnings": []
}
```

Task hints such as `lineage`, `usage`, and `semantics` control traversal. Facts,
observations, candidates, approvals, confidence, and evidence remain visible
in the returned records. Relevance is selected before deterministic pruning;
required facts are not removed merely to make the response shorter.

## Brain Inspector

The local React Inspector has four views:

- **Overview:** scan state, models, reports, object counts, candidates,
  warnings, review items, and validation state.
- **Graph:** scoped React Flow (`@xyflow/react`) rendering with search, object
  and edge filters, connected navigation, node selection, controls, and
  fact/inferred/approved/warning styling.
- **Object Inspector:** identity, metadata, descriptions, lineage,
  relationships, usage, semantics, evidence, confidence, and warnings.
- **Review Queue:** candidates, conflicts, stale overrides, confidence and
  impact sorting, model/report/type/issue filters, and review actions.

React Flow is only a view. Node positions and UI state are not graph facts.

## Desktop Bridge companion

Install Microsoft’s local Desktop Bridge CLI when Desktop verification is
needed:

```powershell
npm install -g @microsoft/powerbi-desktop-bridge-cli@latest
powerbi-desktop --version
powerbi-desktop open 'C:\models\Finance\Finance.pbip'
powerbi-desktop status
powerbi-desktop reload --pid <pid>
powerbi-desktop screenshot <pbir-page-id> --pid <pid> --output .\page.png
```

The bridge controls a local Power BI Desktop process and can report its current
file, connection state, PBIR pages, reload result, and screenshots. It does not
return semantic metadata. Use the PBIP file adapter or a metadata/MCP source
for ingestion. Report reload is suitable for PBIR/report edits; model changes
may require reopening the PBIP project.

See the researched command and safety notes in
[`docs/powerbi-desktop-bridge-cli.md`](docs/powerbi-desktop-bridge-cli.md).

## Project layout

```text
backend/
  scanner/       model/report/PBIP adapters, normalization, scan pipeline
  dax/           ANTLR grammar, AST, parser, analyzer, evidence
  graph/         canonical schema, Ladybug repository, loader, queries
  inference/     semantics, selectors, confidence, report usage
  sync/          source fingerprints, change classification, reconciliation
  validation/    graph, semantic, override, integrity, Power BI hooks
  context/       scoped context builder, schema, deterministic pruning
  api/           in-process API and standard-library WSGI transport
  cli/           `brain` command
frontend/        Vite + React + React Flow Inspector
config/          brain settings and separate human overrides
data/            default native Ladybug database location
docs/            research and integration notes
tests/           reusable unit, parser, graph, inference, sync, API, and PBIP tests
```

## Verification

Run the Python suite:

```powershell
python -m unittest discover -s tests -v
```

Run compilation and the frontend production build:

```powershell
python -m compileall -q backend tests
cd frontend
npm run build
```

Native persistence and CLI tests need a working Ladybug shared library. Tests
that use `GraphRepository(..., use_native=False)` are explicit test-double
coverage and do not replace native verification.

## Security and limits

- Power BI access is read-only in V1. Validation queries must be targeted,
  traceable, and read-only.
- Credentials are not passed to semantic inference, and an LLM is never an
  authority for object existence, source identity, relationships, DAX
  dependencies, or graph integrity.
- Keep the local API on loopback or put authentication in front of it before
  network exposure. The Inspector is a local development UI, not a hosted
  multi-user service.
- The Brain does not provide natural-language-to-DAX, a query compiler, chat,
  automatic report creation/editing, or automatic semantic-model mutation.
- Automatic cross-model ontology reconciliation is not a V1 feature.
- Native writes currently replace the graph snapshot per repository write;
  finer-grained persistence is future work.
- Raw source retention is intentionally compacted but still has known
  duplication in some paths. This is non-blocking cleanup debt.

## Contributing

Keep source-specific parsing inside scanner adapters. Downstream layers should
consume canonical nodes and edges. Preserve stable IDs, evidence class,
provenance, lifecycle status, and separate override storage. Add a focused
regression test for every parser, resolver, inference, sync, validation, or
context behavior change, then run the full verification commands above.

## License

MIT. See [`LICENSE`](LICENSE).
