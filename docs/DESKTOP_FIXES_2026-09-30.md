# Desktop audit fixes — implementation and verification

30 September 2026, Europe/Budapest. Implements only the four confirmed findings in [the historical audit](DESKTOP_PRODUCTION_AUDIT_2026-09-30.md). The original audit and its evidence remain unchanged.

## Changes

| Finding | Implementation | Verified outcome |
|---|---|---|
| DESKTOP-001 HIGH | Both frozen executables embed `packaging/windows.manifest` with process `activeCodePage=UTF-8`. Native initialization errors retain the native cause and give desktop recovery steps. | Real LadybugDB creates, scans and reopens databases under accented, Chinese and emoji directories. Database, config and identity remain project-local; no alternate store or test double. |
| DESKTOP-002 MEDIUM | Remove generated `MODEL CONTAINS REPORT`; retain `REPORT USES_MODEL MODEL`. Graph display traversal follows the reverse model reference solely for branch ordering. | Standard PBIP scan validates successfully, including repeated packaged API scans. Limited graph views still include report visuals and their bindings. |
| DESKTOP-003 MEDIUM | Overview displays graph validation separately from extraction and review. Exact issues expand in place; affected-object buttons open Inspector. Invalid graphs say “Resolve graph issues before review.” | A deliberately broken fixture extracts successfully but displays “Graph validation failed”; its missing relationship endpoint is visible and navigates to the affected relationship. |
| DESKTOP-004 MEDIUM | Review target buttons show model/report and table/ancestor names, preserving scoped accessible names. | Adjacent DateKey rows show `FinanceModel / Sales` and `FinanceModel / Date`; opening Sales.DateKey retains FinanceModel and Sales in Inspector. |

The Unicode cause is now confirmed from [Ladybug 0.20.0 native source](https://github.com/LadybugDB/ladybug/blob/v0.20.0/src/common/file_system/local_file_system.cpp): `openFile` passes UTF-8 bytes to `CreateFileA`. The C API Python wrapper encodes filenames as UTF-8. [Microsoft documents process UTF-8 manifests](https://learn.microsoft.com/en-us/windows/apps/design/globalizing/use-utf8-code-page) as the supported boundary fix on Windows 10 version 1903 onward. This sets the application's code page; it does not change Windows locale or relocate project data. Arbitrary developer Python executables without that manifest may still fail with Unicode database paths; the error directs users to the packaged runtime.

Existing report hierarchy tests were reconciled with canonical `USES_MODEL` semantics. One existing frontend contract's function-boundary search was made independent of Windows CRLF; its assertions remain intact. Pre-existing checkout edits were retained. No reset, stash, clean, commit, installation or release publication was performed.

## Validation

Evidence: [desktop-fixes-2026-09-30](evidence/desktop-fixes-2026-09-30/).

- **Source backend:** `.venv-build/Scripts/python.exe -m unittest discover -s tests` — 219 passed, no skips. Includes standard PBIP/rescan containment, validation detail transport, native desktop lifecycle and report-scope/limited-graph regressions.
- **Frontend:** `npm test` — 25 passed. `npm run build` passed. Existing Vite dependency directive/chunk-size warnings remain nonfatal.
- **Browser:** `npx playwright test desktopAudit.spec.js product.spec.js graph.spec.js` — 16 passed in Chromium. The two new tests deliberately inject UI payloads for invalid validation and duplicate review labels; they are presentation regressions, not standalone production proof. Other cases use the isolated native API fixture. Browser zoom remained 100%; narrow viewports do not change Windows scaling.
- **Frozen package:** `scripts/build-desktop.ps1 -SkipInstaller` completed, rebuilding GUI, agent and portable ZIP. The strengthened frozen gate scans/reopens `Finance project`, `Audit á (test)`, `Audit á # (precreated)` and `审计 🧠`; each persisted 17 nodes/23 edges with original PBIP source hashes unchanged. All gate configs precreate `.pbibrain`; native desktop opening separately exercised an absent `.pbibrain` in the Unicode fixture.
- **Packaged CLI/API:** [verify-packaged.py](evidence/desktop-fixes-2026-09-30/verify-packaged.py) uses the rebuilt agent under a sanitized Windows PATH with Python/Ladybug overrides removed. Valid and invalid Unicode fixtures each passed initial CLI scan and two HTTP rescans. The standard fixture has 20 nodes/30 edges and `validation_state=valid`; the broken fixture has 20 nodes/29 edges and `validation_state=invalid`, with exact issues matching `/api/brain`. See [packaged-api-results.json](evidence/desktop-fixes-2026-09-30/packaged-api-results.json).
- **Native desktop:** rebuilt portable `dist/PBIBrain/PBIBrain.exe`, not the earlier installed executable. File-backed stdout/stderr launch; real WebView2 window, 100% Windows scale (observed) and explicit Ctrl+0 UI zoom. Native opening/scan of the Unicode project succeeded; final build showed the invalid status, expanded exact issue, Inspector navigation and distinguishable DateKey rows. [Invalid status screenshot](evidence/desktop-fixes-2026-09-30/native-invalid.jpg), [final review screenshot](evidence/desktop-fixes-2026-09-30/final-native-review.jpg), and saved accessibility captures record the proof.
- **Immutability:** both valid and deliberately invalid fixture source manifests match their respective baseline hashes after CLI/API and desktop scans. The invalid fixture was deliberately changed before its baseline, never during scans. See [source-immutability.json](evidence/desktop-fixes-2026-09-30/source-immutability.json).
- **Package integrity:** embedded UTF-8 manifests verified in both EXEs; packaged frontend byte matches `frontend/dist`. EXE/ZIP hashes: [package-hashes.json](evidence/desktop-fixes-2026-09-30/package-hashes.json). `git diff --check` passed. `graft build` refreshed the context graph.

## Remaining gates and limits

The previously installed application was not upgraded; this proof covers the newly rebuilt portable runtime/native GUI. Clean Windows VM, installer, upgrade and uninstall acceptance remain unverified. Nothing here establishes universal release readiness.

Validation remains runtime-only: reopening shows “Graph validation not run” until a scan checks it again. Persisting validation/timestamps was a suspected contract gap, outside these four confirmed fixes. No bulk-approval behavior was changed. Higher Windows scales were neither tested nor used for acceptance. No production Power BI project was mutated.
