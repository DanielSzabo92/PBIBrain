# Guarded development: implementation and acceptance record

Status: implemented guarded core; **full user contract not accepted**.

The user-supplied 26-section implementation specification remains the authority. This document records the implemented mechanisms, bounded evidence, and outstanding work. Existing source edits were preserved. No project model was promoted, no repository commit was made, and nothing was pushed or deployed.

## Architecture and decisions

PBIBrain provides read-only analysis. `change_guard` is a separate trusted controller. Its CLI and loopback service have separate credentials and do not appear in the Brain MCP tool set. The coding process receives only an isolated candidate mount. Permission is enforced by semantic comparison and mandatory raw-source accounting, independently of any agent explanation.

| Decision | Mechanism |
|---|---|
| Reuse canonical graph | Existing scanner, stable IDs, schema, DAX analyzer, integrity validation, and graph serialization. Snapshot scans use independent ephemeral repositories; no second persistent dependency graph. |
| Authoritative metadata | .NET 8 bridge using Microsoft.AnalysisServices 19.114.12, locked NuGet dependencies, TOM JSON and TMDL deserialization and roundtrip checks. Failure closes the source gate. |
| Snapshot identity | Source path/hash/size manifest, project configuration, stable identity mappings, scanner/schema versions. Capture time and snapshot kind do not influence identity. |
| Scope | Strict schema plus exact stable object, type, operation, property, previous value, and proposed value checks. No wildcards or unlisted mutations. |
| Trust | Authorized contracts, evidence, approvals, state, and journals are controller-signed; audit records form a hash chain with a separately signed head. |
| Isolation | Digest-pinned Docker process, candidate-only mount, no network, read-only root, unprivileged UID, no capabilities, no controller state or production credentials. A manually edited candidate has no isolation receipt and cannot be accepted. |
| Impact | Conservative before/after relationship influence, implicit calculation context, transitive consumers and report usage. Possibilities never become factual graph edges. |
| Runtime | Capability declarations, independent loader/context/permission binding, equivalent frozen data, query AST target coverage, result comparison and required coverage. Mocks and unavailable backends cannot certify runtime behavior. |
| Promotion | Explicit candidate/evidence-bound approval, source/candidate hash rechecks, project lock, recoverable backups, signed multi-file journal, verified recovery and post-promotion scan. |
| Review | Impact Explorer in Inspector; separate `/guard` review served only by trusted guard service. Contract, behavior, high-risk, and promotion approvals remain separate from semantic Review Queue. |
| Cost | Hashing, scanning, graph traversal, diff, scope, policy, comparison and recovery use zero LLM calls. Derived impact cache is bounded and in memory. |

OPEN decisions: deployment-specific OS/container hardening and credentials; real isolated runtime loaders and read-only grant proof; supported PBIR schema versions; packaged bridge runtime distribution; Git promotion/recovery integration; retention/cleanup policy. The defaults block acceptance where the required proof is absent.

## Supported boundary

Guarded scanning currently requires one dedicated PBIP project root. Multiple local semantic models can be ingested when resolvable; missing and remote bindings block completeness. Standalone model-only TMSL/TMDL imports are not yet an accepted guarded workflow.

Recognized TOM metadata is retained in full. Canonical model/table/column/measure/relationship properties are compared. Full mapped PBIR JSON documents are compared without discarding unknown fields. Source coverage currently supports BIM property edits, mapped report/page/visual JSON property edits, and narrow existing-line TMDL relationship scalar replacements. Other TMDL edits, source creation/deletion, unmapped JSON changes, and protected/control-file changes fail closed. This prevents bypass; it does not claim all requested mutation operations are usable yet.

Normalization policy `exact-properties-v1` explicitly permits JSON object-key ordering, insignificant JSON whitespace, and a JSON UTF-8 BOM. Arrays, expression text, literal whitespace, DAX/M strings, TMDL comments, and TMDL newlines remain significant. TOM default expansion is explicitly implemented for selected typed properties. Unrecognized serialization loss fails; unsupported nested model semantics remain incomplete. Recognized report images/fonts in `StaticResources` are hash-pinned opaque assets; changing them is not authorized by metadata scope. Existing `.gitignore`/`.gitattributes` are protected text artifacts; edits fail coverage.

PBIR schema coverage, calculation-group dependency extraction, calculated-table dependencies, RLS/OLS behavior, and complex active filter topology are not certified. They remain explicit blockers. TOM roundtrip success proves deserialization/serialization fidelity within the implemented adapter, **not processing or numerical correctness**.

## Commands

Build the bridge before using a development checkout:

```powershell
dotnet restore backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj --locked-mode
dotnet build backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj -c Release --no-restore
```

Install this project's entrypoints with the normal project installation. The module invocation also works without reinstalling entrypoints:

```powershell
python -m change_guard.cli --source C:\Models\Sales --state C:\GuardState\Sales --project-id sales snapshot
python -m change_guard.cli --source C:\Models\Sales --state C:\GuardState\Sales --project-id sales prepare contract.json
python -m change_guard.cli --source C:\Models\Sales --state C:\GuardState\Sales --project-id sales report OPERATION_ID
python -m change_guard.cli --source C:\Models\Sales --state C:\GuardState\Sales --project-id sales authorize OPERATION_ID --purpose CONTRACT
python -m change_guard.cli --source C:\Models\Sales --state C:\GuardState\Sales --project-id sales run-agent OPERATION_ID --image IMAGE@sha256:DIGEST -- COMMAND ARGUMENTS
python -m change_guard.cli --source C:\Models\Sales --state C:\GuardState\Sales --project-id sales verify OPERATION_ID
python -m change_guard.cli --source C:\Models\Sales --state C:\GuardState\Sales --project-id sales serve
```

The trusted runtime runner is an in-process API; the CLI does not yet load arbitrary regression scripts. This protects the evaluator from agent-authored privileged code. `authorize --purpose HIGH_RISK_PROMOTION`, `UNEXPECTED_BEHAVIOR`, and `PROMOTE` act only after mandatory gates succeed. `promote` then applies the approved local candidate; `recover` verifies the journal and backups. `retry` creates a fresh candidate under the unchanged contract with a configurable retry limit.

Use `--identity-file PATH` to seed from the existing authoritative PBIBrain identity store. Its canonical hash is pinned alongside the source baseline; subsequent identity edits make the baseline stale. Candidate mappings are staged independently and never written back by scanning. New-identity promotion remains unsupported while creation/deletion source coverage is incomplete.

Schema: [`contract-v1.schema.json`](../change_guard/contracts/contract-v1.schema.json). The deterministic validator also checks cross-field consistency, target resolution, uniqueness, and baseline property preconditions.

Exit codes: 0 success; 2 invalid input; 3 scope violation; 4 source/static failure; 5 runtime failure; 6 missing approval; 7 inconclusive; 8 stale baseline; 9 promotion/recovery failure. Results and invalid-argument errors use JSON. Help remains conventional CLI text.

Brain additions are read-only: `POST /api/impact`, `POST /api/compare`, `brain impact`, `brain compare`, `brain_impact`, `brain_compare`. Comparison accepts only trusted, previously prepared snapshot registrations. Existing endpoints and MCP tools remain in place. Context tasks add `impact`, `change_preflight`, `regression_planning`, and `post_change_review` without replacing existing lineage/usage/dependency behavior.

## Phase acceptance

| Phase | Delivered | Acceptance status / remaining work |
|---|---|---|
| 1 foundation | Manifests, isolated scans, real TOM bridge, property/raw comparison, strict contracts, scope, candidate-only sandbox launcher, policy | Extra mutations rejected in adversarial fixtures. **Live process separation not demonstrated on this host: Docker unavailable.** Full metadata operation coverage and packaged bridge pending. |
| 2 impact | Conservative relationship influence, unchanged SUM, dependent YTD, visual closure, provenance/completeness, required test categories, read-only MCP | Reference scenario static tests pass. Weighted/limited paths, broader advanced object extraction and full cross-model/report coverage pending. |
| 3 static gates | Independent candidate scans, raw coverage, graph changes, existing integrity checks, TOM roundtrip, endpoint/sort-reference checks, topology uncertainty | Authorized supported scope passes the scope gate; unsupported/invalid inputs block. **Full PBIR schemas and authoritative processing checks pending.** |
| 4 runtime | Adapter capability/binding contracts, query-only API adapter, independent runner, all comparison modes, invariants/coverage/retention | Comparator and fault tests pass. **Real numerical relationship regression NOT_RUN; local AS/XMLA adapters and isolated model loader pending.** |
| 5 promotion | Signed approvals, locked candidate, staleness checks, local journal/backups/recovery, post-promotion verification; separate Git review revision helper | Temporary-source promotion and recovery tests pass. **No accepted full guarded model promotion; Git controller integration pending.** |
| 6 Inspector | Impact graph/filter/evidence, semantic differences, results/coverage, independent approvals, audit/status | Actual Google Chrome tests and visual inspection pass for implemented views. Full report-context/runtime evidence drilldown pending. |
| 7 optimization | Indexed adjacency; bounded snapshot impact cache; synthetic PBIP measurement harness | Synthetic measurements recorded. Region-only recomputation, test-plan/baseline query cache, representative production/large-model benchmarks pending. |

## Definition of done: every criterion

PASS below means bounded automated evidence for the implemented scope, not complete acceptance of the full contract. PARTIAL and NOT_RUN remain unfinished.

| Contract criterion | Status | Evidence / limit |
|---|---|---|
| 25.1 exact stable targets | PASS | Exact IDs/types/current values validated; ambiguity cannot authorize. |
| 25.1 property changes | PARTIAL | Supported TOM/PBIR properties; narrow TMDL raw accounting. |
| 25.1 reject unauthorized mutation | PASS | Endpoint-only fixture rejects direction, measure, deletion/recreation, visual and hidden edits. |
| 25.1 relationship impact | PARTIAL | Conservative connected filter region; advanced semantics escalate. |
| 25.1 unchanged DAX impacted | PASS | Unchanged SUM fixture explicitly included. |
| 25.1 dependent measures/visuals | PASS | Transitive YTD and visual fixture. |
| 25.1 explicit uncertainty | PASS | Missing/unsupported/truncated scope represented. |
| 25.1 independent static integrity | PARTIAL | Existing graph validation and actual TOM roundtrip; PBIR/processing incomplete. |
| 25.1 required numerical tests | NOT_RUN | No equivalent frozen baseline/candidate runtime endpoints. |
| 25.1 unexpected behavior policy | PARTIAL | Comparator/coverage/approval mechanisms; live behavior not tested. |
| 25.1 failed/inconclusive never pass | PASS | Policy precedence, mock/data-drift/unavailable/error cases. |
| 25.2 original source protection | NOT_RUN | Candidate-only Docker launcher; no live Docker adversarial proof. Host-process use is unsupported. |
| 25.2 policy protected | PARTIAL | Outside candidate mount, policy hash checked; isolation proof pending. |
| 25.2 evidence protected | PARTIAL | Outside mount; HMAC/hash-chain/head tampering tests. OS proof pending. |
| 25.2 agent cannot promote | PARTIAL | No mutation MCP; separate service/key; process isolation proof pending. |
| 25.2 enforced read-only runtime | PARTIAL | Query-only HTTPS API surface; AS/XMLA connection grant proof pending. |
| 25.2 snapshot isolation | PASS | Independent ephemeral scans/identity staging; original ID file unchanged. |
| 25.2 unknown changes close gate | PASS | Unknown source/property/parse/raw coverage rejects. |
| 25.3 prior state recoverable | PASS | Backups and verified recovery in temporary fixtures. |
| 25.3 candidate hash lock | PASS | Signed evidence/approval and pre-write hashes. |
| 25.3 concurrent edits stale | PASS | Source/candidate/recovery concurrent-edit tests. |
| 25.3 multi-file failures recovery | PARTIAL | Fault after replacement and restart recovery; exhaustive OS interruption matrix pending. |
| 25.3 audit after failure | PASS | Durable signed records; incomplete/tampered history blocks. |
| 25.3 reproduce retained validation | PARTIAL | Canonical sources/manifests/evidence; real runtime reproducibility pending. |
| 25.4 graph compatibility | PASS | Existing schema unchanged; Python suite. |
| 25.4 existing MCP | PASS | Existing tools retained; suite compatibility. |
| 25.4 retrieval/context API | PASS | Existing tasks retained; integration tests. |
| 25.4 existing read-only boundary | PASS | Brain additions expose analysis only. |
| 25.4 stable identity compatibility | PARTIAL | Existing IDs reused; authoritative lineage rename test. Broader stale mappings pending. |
| 25.4 no duplicate persistent graph | PASS | Existing canonical graph with serialized immutable evidence. |
| 25.4 existing tests | PASS | See verified test counts in evidence record. |
| 25.5 analysis no LLM | PASS | Deterministic modules; measured zero calls. |
| 25.5 scope no LLM | PASS | Exact schema/property comparisons. |
| 25.5 regression compare no LLM | PASS | Deterministic comparator. |
| 25.5 relevant tests selected | PARTIAL | Conservative bounded categories/targets; executable planning incomplete. |
| 25.5 reuse graph/scanning | PASS | Existing scanner, DAX, schema, integrity, PowerBI hook. |
| 25.5 measurable performance | PARTIAL | Timing/counts and synthetic benchmark; production-scale task cost pending. |
| 25.5 AI cannot override blockers | PASS | No LLM approval input to policy. |

## Invariants and failure behavior

I-001/I-003/I-012/I-016: enforced at the configured candidate-only container boundary and separate controller API, pending live isolation proof. I-002/I-004/I-010/I-018: immutable exact contracts, compatible IDs, no automatic scope expansion/repair. I-005/I-006/I-007/I-019: conservative impact, preserved edge provenance, explicit unknowns, full coverage accounting. I-008/I-009/I-011: static scope does not authorize behavioral changes; real equivalent-data runtime evidence required. I-013/I-014/I-015/I-017/I-020: bound hashes, attributable approvals, deterministic blocking policy, signed journals and verified prior-state recovery.

None of these claims establishes a security boundary for an arbitrary already-running host process with the user's full filesystem access. Supported agent execution must enter the isolated runtime. Do not mount source roots, credentials, controller state, a Docker socket, or the user's profile into it.

Evidence: [`guarded-development`](evidence/guarded-development-2026-10-09/). Protocol details: [impact](IMPACT_ANALYSIS.md), [regression](REGRESSION_PROTOCOL.md), [security](SECURITY_BOUNDARIES.md), [recovery](RECOVERY_PROTOCOL.md).

## 2026-10-09 proof and coverage continuation

The earlier acceptance table above is retained as history. The following evidence supersedes its sandbox, runtime, PBIR and Git integration blockers for the supported scope. This is not unrestricted acceptance of every source format or execution context in the full specification.

* **Actual Windows boundary:** a unique AppContainer, no capability SIDs or inherited handles, read-only trusted runtime grants, candidate-only artifact writes, private disposable profile, and a kill-on-close job. The controller checks the OS token and waits for every descendant to exit before hashing candidate output. The real adversarial proof denied protected-source/baseline/policy/audit/unrelated file access, hardlinks, runtime writes, controller process write access and child-process protected writes. A reachable loopback listener was blocked. Files remained unchanged; temporary ACL grants/profile were removed. See `windows-isolation.json`.
* **Actual execution:** the installed Desktop Analysis Services engine 17.0.74.22 ran a separately owned native tabular instance. No existing Desktop model was loaded or modified. TOM loaded and processed baseline/candidate databases; partition errors and nonready states block validation. A valid refresh command succeeded through the trusted administrator control and failed through the mandatory reader role. The role's actual model read permission and successful model-data read were independently checked. Regex query checks remain secondary guardrails.
* **Equivalent data:** three constant DATATABLE partitions, two date dimensions and four sales rows. Full AST validation rejects references, unknown functions and dynamic expressions. Literal definitions and every processed physical table were independently hashed on both models; the results were rechecked after queries. External/M sources, RLS, parameters and unsupported locale/context configurations cannot receive this frozen-data attestation.
* **Numerical regression:** all nine mandatory relationship categories plus three field invariants passed: 12 real before/after tests, 41 impact paths. Order-date January sales of 30 became BLANK; February sales changed from 30 to 60; the unmatched-key bucket remained 5 and the unfiltered total remained 65. The explicit inactive relationship override and YTD were tested. Report coverage certifies the selected bound data, not rendering or untested interactions. Structural endpoint/relationship paths are reported separately from runtime observations. `live-regression.json` records full query/result/context evidence and independent audit-head/tail hashes.
* **Broader metadata:** offline pinned Microsoft PBIR schemas validate report, page, visual, page inventory and model binding documents. Invalid or unsupported schema contexts fail the static gate even for low-risk contracts. Exact TMDL scalar/inline-expression accounting now covers supported table, column and measure properties as well as relationships; comments, extra lines, unknown properties and mismatched object scopes still fail closed. TOM integration tests exercise format strings, display folders and expressions. Scanner identity is versioned as `guarded-2`.
* **Git promotion:** the trusted controller now creates a verified review revision, journals source/index/ref transitions, checks the pinned branch and index, applies verified files, updates the branch by compare-and-swap and verifies a clean resulting revision. All mandatory gates and purpose-specific approvals precede this operation. Recovery tests interrupt after source, index and ref writes, restart the controller and verify original contents/HEAD/index. Foreign staged edits block recovery. A real isolated implementation, runtime verification, explicit high-risk approval, Git promotion and post-promotion scan completed in the disposable acceptance project.
* **Audit:** `verify_integrity` checks every record signature and chain link plus the separately signed head under the audit lock, retaining the compared tail hash. Corrupt head evidence is rejected. An initial weak proof-output patch was rejected by automatic review; the final evidence uses the actual cryptographic checks.

Additional development commands:

```powershell
dotnet restore change_guard/regression/dotnet/RuntimeEvaluator.csproj --locked-mode
dotnet build change_guard/regression/dotnet/RuntimeEvaluator.csproj -c Release --no-restore
python -m change_guard.cli --source PROJECT --state TRUSTED_STATE --project-id PROJECT_ID run-agent OPERATION_ID --backend windows --runtime-root TRUSTED_RUNTIME -- EXECUTABLE ARGS
python -m change_guard.cli --source PROJECT --state TRUSTED_STATE --project-id PROJECT_ID promote OPERATION_ID --mode git
python -m tests.proof_native_guard windows-isolation.json
python -m tests.proof_live_regression live-regression.json
```

Remaining unsupported boundaries stay explicit: arbitrary calculated-table dependencies, calculation-group/field-parameter contexts, RLS/OLS, remote/multimodel runtime binding, bookmarks/interactions, generic frozen external data, standalone model workflows and source create/delete operations. These cannot be automatically promoted. Bridge/runtime distribution and production-scale optimization remain deployment work. No production Power BI/Fabric workspace is deployed by this implementation.

### Source-release verification

Guard-only changes are staged independently of the user's existing UI edits. The isolated release exposed a genuine Windows checkout defect: Git newline conversion changed the pinned Microsoft schema bytes. Scoped `.gitattributes` entries preserve vendor/evidence bytes exactly; a regression test stages and checks out the real catalog with `core.autocrlf=true` and verifies every pinned hash. The integrity gate was retained throughout; no expected hash was weakened or rewritten to accommodate corruption.

The final release keeps the same checked implementation while adding verification records. `evidence/guarded-development-2026-10-09/continuation-manifest.json` binds the tested source tree, final suite results and retained evidence hashes. Source-code publication is separate from the disposable Power BI model promotion acceptance test and does not establish acceptance of the remaining unsupported specification scope.
