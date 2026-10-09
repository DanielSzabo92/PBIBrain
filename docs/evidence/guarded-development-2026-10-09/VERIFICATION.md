# Verification record — 2026-10-09

Full contract acceptance: **NOT COMPLETE**. No authoritative Power BI project was promoted. All mutation/fault fixtures used temporary directories. No Git push or production deployment occurred.

| Check | Verified result | Scope |
|---|---|---|
| Python full suite | 283 tests, OK, 1 skipped; exit 0 | Existing 227 tests plus guarded tests; skipped pre-existing optional check remains unverified. |
| Guard focused suite | See `guard-tests.log` | Latest reference fixture and adversarial scope, evidence, recovery tests. |
| Frontend unit suite | 31 passed; exit 0 | Existing graph/session/presentation logic. |
| Existing browser acceptance | 47 passed; exit 0 | Actual Google Chrome, isolated native LadybugDB fixture, real local API. |
| Guard browser acceptance | 3 passed; exit 0 | Actual Google Chrome, real TOM fixture/API, independent guard review. Guard snapshot graph is ephemeral in-memory; this is not Power BI runtime execution. |
| Frontend build | Passed; exit 0 | Existing Vite bundle with guard/impact views. Existing dependency directive warnings are nonblocking. |
| TOM bridge build | Passed; exit 0, 0 warnings/errors | .NET 8 with locked Microsoft.AnalysisServices 19.114.12. |
| Diff whitespace | `git diff --check` passed | Includes existing uncommitted edits; they were preserved. |
| Graft | Refreshed, 211 indexed files | Local ignored context graph; deterministic build. |
| Visual inspection | `guard-review.png` inspected | Exact endpoint values visible; missing sandbox/runtime/coverage reasons visible; all unavailable approval/promotion actions disabled. |
| Synthetic benchmark | `benchmark.json` | 10/100/1000 added measures, real TOM PBIP extraction; not representative production acceptance. |
| Isolation runtime | NOT_RUN | `docker` unavailable on PATH. Digest-pinned launcher implemented; process/access proof unavailable. |
| Power BI numerical regression | NOT_RUN | No active PBIDesktop/msmdsrv process and no supplied equivalent frozen baseline/candidate endpoints. Query API/types and local AS/XMLA limitations remain explicit. |
| Full guarded promotion | NOT_RUN | Mandatory sandbox/runtime/coverage gates correctly block. Low-level signed local promotion/recovery was verified on temporary sources only. |

Commands:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -q
.venv\Scripts\python.exe -m unittest tests.test_guarded_development -q
.venv\Scripts\python.exe -m tests.benchmark_guarded_development
dotnet build backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj -c Release --no-restore
```

From `frontend`:

```powershell
node node_modules/vite/bin/vite.js build
node --test
node node_modules/@playwright/test/cli.js test --config=playwright.guard-compat.config.js
node node_modules/@playwright/test/cli.js test --config=playwright.guard.config.js
```

The compatibility server uses port 8774 to avoid an existing unrelated listener on 8765; it never reuses a live user server. The guard fixture uses 8773. Initial readiness/port attempts did not execute browser cases; the final isolated runs completed successfully.

Reference evidence `reference-static.json` pins a one-property OrderDateKey → ShipDateKey change with unchanged SUM/YTD definitions and a date-bound monthly visual. It records incomplete PBIR coverage and NOT_RUN runtime/isolation; no golden record claims successful numerical verification or promotion.

Remaining implementation and per-criterion acceptance are recorded in [CHANGE_GUARD_CONTRACT.md](../../CHANGE_GUARD_CONTRACT.md). Required next acceptance inputs are a trusted sandbox execution environment, isolated baseline/candidate runtime models with identical frozen data, authoritative load/read-grant evidence and full required regression contexts. Broader metadata/PBIR, Git promotion integration and remaining optimization are still unfinished.

## Continuation: real isolation, numerical execution and recovery

The preceding record is retained history. The continuation supersedes its NOT_RUN entries only for the bounded scopes below. Full contract acceptance remains **NOT COMPLETE**; unsupported scopes still block automatic Power BI promotion.

| Check | Observed result | Scope |
|---|---|---|
| Final Python suite | 293 tests, OK, 1 skipped; exit 0 | Existing compatibility, metadata, adversarial guard and recovery cases. |
| Windows isolation | 20 real OS access attempts; PASSED | Capability-free AppContainer, protected-file and controller access denied, network denied, candidate write allowed, delayed descendant killed and cleanup verified. See `windows-isolation.json`. |
| Desktop engine numerical execution | 12 required tests; 41 impact paths covered; certified | Separately owned native engine 17.0.74.22; sealed literal-data reference model. Actual read role and denied mutation verified. January 30 becomes BLANK, February 30 becomes 60, unmatched 5 and grand total 65 preserved. See `live-regression.json`. |
| Runtime data identity | Frozen definitions and independently read processed rows match | Literal DATATABLE partitions only. Arbitrary external data, source credentials, source roles and unsupported evaluation contexts are rejected before loading. |
| Report test scope | BOUND_DATA_ONLY | Schema-valid simple monthly visual field bindings; no rendering, bookmark or interactive-context acceptance claim. |
| Guarded Git promotion | POST_PROMOTION_VERIFIED | Disposable acceptance project only; exact approved relationship endpoint mutation, unchanged measures and report sources. Signed audit head, tail and chain independently verified. |
| Crash recovery | Actual process exit 99 at source, index and reference stages; recovered | Exclusive Git index lock, persisted signed journal, restart recovery and clean original revision verified. Foreign staged edits block recovery. |
| Broader metadata | Pinned offline Microsoft PBIR schemas; real TOM scalar/expression accounting | Report/page/visual schemas, structured field bindings and filters; exact measure expression/format/folder and column format diffs. Unknown source changes and unsupported report contexts fail closed. |
| Frontend | 31 unit tests, 47 compatibility Chrome cases, 3 guard Chrome cases; builds passed | Actual installed Google Chrome. Separate Playwright output directories resolve an initial concurrent trace-cleanup collision. |

The user's existing Finance Desktop model was not modified. The native engine ran in a separately owned temporary directory and was terminated after proof. No production deployment occurred. Source-code release verification is recorded separately from Power BI project promotion.

The first proposed audit summary was rejected by automatic review because record count alone did not verify integrity. The accepted implementation computes and verifies every signed chain link and the signed head against the actual tail; the evidence contains those results.

Unsupported calculation groups/field parameter contexts, RLS/OLS, remote or multiple-model runtime bindings, bookmarks/interactions, arbitrary calculated-table dependencies and generic external-data freeze remain blocking. Native bridge distribution and production-scale performance acceptance remain unfinished. See [CHANGE_GUARD_CONTRACT.md](../../CHANGE_GUARD_CONTRACT.md).

## Isolated source release

Tested Git tree: `25a019eea19b5eb2dbd416336799eb1a28e46f67`, parent `22f86dd0a196759d7fc78bbf71c81516ff0d89bd`. This tree contains only guarded-development changes. Existing uncommitted UI work is excluded and preserved.

* Python: **293 tests, OK, 1 skipped**, exit 0 (`release-final-python.log`).
* Frontend units: **26 passed**, exit 0. Chrome: **32 existing cases plus 3 guard cases passed**, exit 0. The larger earlier 31/47 counts include existing user UI changes and are not used as acceptance of this isolated release. Frontend source trees for the unit/compatibility run and corrected release are identical.
* Both .NET bridges build with locked dependencies and **0 warnings/errors**. Frontend release build passes. The initial `--locked-mode` build invocation was corrected to `-p:RestoreLockedMode=true`; initial diagnostics are retained.
* Real isolated release runtime: **12 tests, 41 covered paths**, certified, `POST_PROMOTION_VERIFIED`, audit integrity independently verified (`release-final-live-regression.json`).
* Real release OS proof: **20 access attempts**, passed (`release-windows-isolation.json`). The tested Windows launcher and proof source are unchanged in the corrected release.
* The first isolated tree failed the pinned-schema integrity gate after Git converted line endings. `.gitattributes` now preserves the exact schema/evidence bytes; an actual Git staging/checkout regression with `core.autocrlf=true` passes. Initial failing logs are retained. No integrity check was relaxed.
* Authored-source whitespace check passes. Pinned vendor documents and raw evidence retain their original bytes. Graft refresh completes: 226 files, 2506 nodes and 6806 edges.

The release adds documentation/evidence after execution; source identity is rechecked against the tested tree before publication. `continuation-manifest.json` contains evidence hashes and supported-scope limits. Publication targets the existing `ui-redesign` branch, using a fast-forward revision and preserving all working-file contents.
