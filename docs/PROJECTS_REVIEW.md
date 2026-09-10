# Project configuration review

## Findings

- A scan currently replaces the whole repository. Scanning sources one at a
  time therefore loses earlier models and reports.
- `config/brain.json` is not a validated runtime contract. Relative paths and
  multiple inputs have no shared meaning across the CLI, API, and GUI.
- Canonical IDs are stable inside one combined build, but duplicate model or
  report source IDs can silently collapse objects.
- Parsing already completes before `Scanner` publishes, but a project service
  must stage every configured source together so one broken source cannot
  publish a partial project.

## Minimal v1 contract

```json
{
  "version": 1,
  "name": "PBIBrain",
  "sources": ["../reports/Finance.pbip"],
  "database": "../data/brain.lbug",
  "identity_map": "identity.json"
}
```

Paths are resolved from the configuration file directory. One project owns
one database and identity map. A project scan reads every source, rejects
duplicate paths and conflicting model/report identities, deduplicates an
identical model shared by reports, builds one staged graph, preserves matching
review decisions, and publishes once. Removed source
objects disappear on the next successful scan. Invalid configuration or any
source failure leaves the current graph unchanged.

Documentation export and structural diagrams should consume the same project
snapshot later. They do not need a second store or a second source manifest.
