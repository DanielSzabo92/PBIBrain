# Conservative impact analysis

`backend/impact/analyzer.py` reads the existing canonical graph and never inserts speculative edges. `backend/impact/cache.py` caches derived immutable-snapshot reports in memory, bounded by entry count. Cache identity includes source snapshot, graph content, completeness, targets, proposal and report-usage flag; returned data is copied.

The pipeline seeds exact modified objects/properties, records original and proposed relationship endpoint columns, walks a conservative before/after table region, includes calculations whose filter context may change without expression changes, follows explicit calculation consumers, and reaches report objects and containing pages/reports. Model/table/column/calculation-group/security changes conservatively seed relevant model calculations. Indexed adjacency avoids repeated full-edge scans for each calculation.

Relationship influence retains both possible directions, including inactive paths, because expanded tables, USERELATIONSHIP, CROSSFILTER and security may alter effective behavior. This is a conservative superset, not an authoritative direction/cardinality/weight simulation. Runtime tests decide what actually changed. Complex active cycles, unknown types and unsupported extraction remain incomplete. Microsoft's [relationship documentation](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-relationships-understand) describes filter priority/weight and cases requiring engine evaluation.

Every record carries root target, trigger, stable impacted ID, category, shortest retained path per rule/root/property, original edge class/direction/evidence, inclusion reason, conditions and verification requirement. Distinct rules retain distinct explanations. Analytical influence is `INFERRED`; observed runtime effects cannot be produced by static analysis. Existing FACT/INFERRED/OBSERVED graph contracts remain intact.

Completeness reports exact examined nodes/edges, relevant model/report scope, unsupported/unresolved metadata, analysis and output truncation separately, and missing execution proof. Output pruning preserves full impacted IDs/path identities and never certifies reduced scope. Live graph endpoints use UNKNOWN scanner completeness unless a trusted snapshot has supplied coverage.

Relationship plans select mandatory categories: unfiltered and grouped totals, affected/dependent measures, alternate relationships, unmatched keys/BLANK, slicer contexts, time intelligence, representative report calculations, and security where applicable. Entries are explicitly `QUERY_REQUIRED`: a category list is not executed validation. No invariant or expected numeric result is invented.

Reference fixtures retain SUM unchanged, use a real TOTALYTD expression, discover consuming visuals, and exercise explicit USERELATIONSHIP/CROSSFILTER. Static discovery does not prove data/time-intelligence processing succeeds. Unsupported report contexts remain blockers.
