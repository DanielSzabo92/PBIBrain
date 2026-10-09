# Independent regression protocol

The trusted runner reuses `PowerBIValidationHook`, `ValidationQuery` and existing read-only adapter seams. Agent-written scripts and claimed summaries are not accepted evidence. A runtime adapter is trusted evaluator code, never imported from the candidate workspace.

Before certification, the evaluator must independently bind each loaded model to the exact baseline/candidate snapshot, an actual model identity, execution-context hash, loader evidence and read-permission evidence. It must prove matching frozen source data and processed state, culture, role, parameters, filters, calculation configuration and relevant evaluation time. The runner checks this binding as well as capabilities; a caller's two matching context strings are insufficient.

The current query-only Power BI ExecuteQueries adapter can collect observations against an explicitly configured isolated dataset. It uses a fixed HTTPS query endpoint, denies redirects, does not persist its credential supplier, and declares that authoritative result types and role context are unsupported. Consequently it cannot certify full required regression. Local AS/XMLA and model-loading/processing adapters remain unavailable; capability absence returns NOT_RUN. Test doubles are always non-live and cannot certify.

Read-only grants and server command capability are the security boundary. Existing query-text rejection remains defense in depth, not proof that a connection cannot mutate a model.

Each test has an exact ID, object targets, DAX, required flag, comparison policy, category, invariant identities and coverage paths. Expected changes require an explicit expected dataset or delta bounds. All nine modes are implemented: EXACT, NUMERIC_TOLERANCE, EXPECTED_CHANGE, PRESERVE_AGGREGATE, EXPECTED_VALUE, EXPECTED_DELTA, SET_EQUIVALENCE, SCHEMA_ONLY and MONITOR. MONITOR stays inconclusive; it does not approve changed behavior. SCHEMA_ONLY does not certify invariants or numerical impact paths.

Comparison preserves typed column schema, BLANK/null, decimal precision, finite numeric values, row shape/count, duplicate multiplicity, explicit row-order rules, dates/times, errors and configured collation. Tolerance is explicit and versioned; unknown expected-result modes and non-finite delta bounds are rejected. Failed/timeout queries fail required tests. Missing or drifting data cannot certify equivalence.

Coverage parses supported single EVALUATE expression queries using PBIBrain's DAX AST and object resolver. Labels alone do not prove object evaluation. Explicit references and factual calculation dependencies establish query targets; unsupported query statements, unresolved models and missing target references prevent certification. Coverage includes impacted/tested/untested objects, covered/uncovered paths, required/completed/failed/inconclusive tests and invariant results. All required contexts and paths must be accounted for.

Evidence records query/hash, snapshot identities, backend, context/data identity, actual result hashes, assertions, error class, timestamps, duration and certification status. Retained result values are canonical typed JSON. Default result retention is off; configure a trusted retention policy before storing sensitive data. The current implementation does not yet provide automated retention cleanup or a complete frozen-time/volatile-query execution backend.

Real relationship numerical acceptance remains NOT_RUN on this host. Synthetic changed monthly rows and preserved total fixtures validate the comparator only; they do not replace Power BI execution.
