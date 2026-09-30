# PBIBrain desktop production audit

Audit dates: 29–30 September 2026, Europe/Budapest. Audit only; no fixes.

## 1. Executive audit summary

The installed application completed project creation, native scanning, graph/Inspector use, semantic editing, review decisions, reopen, and project switching. A normal Windows folder containing `á` cannot open its native database. Standard PBIP scans also publish a containment relation that their own validator rejects.

Four independently verified defects: 0 CRITICAL, 1 HIGH, 3 MEDIUM, 0 LOW. This is a bounded production audit with explicit coverage gaps, not universal or clean-machine acceptance. Release readiness is not established. Repeated controlled startup passed. The user subsequently restricted display testing to 100%; higher-scale observations are excluded from defect and release judgments.

Evidence root: [desktop-audit-2026-09-29](evidence/desktop-audit-2026-09-29/). Independent verification: [runtime-verification.md](evidence/desktop-audit-2026-09-29/verification/runtime-verification.md).

Environment: Windows 11 Pro `10.0.26200`, Hungarian OS, 1920×1080 internal display. Before the user's scope correction, actual Windows scales 100%, 125%, 150%, 175% were exercised. Final setting is 100%, visibly verified; all further testing is restricted to 100%. WebView2 Evergreen `154.0.4258.37` was already installed. This machine also has development tools.

Installed executable: `C:\Users\Daniel\AppData\Local\Programs\PBIBrain\PBIBrain.exe`, SHA-256 `9817EA71CBD3489B5DE0C9214DE8ADC09359F3C0644C2EC5136C12B328A44AFF`; byte-identical to the audited distribution executable. Installed frontend JS/CSS match `frontend/dist`; hashes are saved in `frontend-hashes.json`. EXE file/product version fields are empty; installer source declares `0.1.0`. Source references explain the observed build and do not substitute for packaged evidence.

## 2. Critical and high-priority findings

**DESKTOP-001 — HIGH, CONFIRMED: a non-ASCII database path prevents project opening/scanning.** Independently reproduced with an ASCII control and a Unicode source root using an ASCII database path. This prevents ordinary use for affected Windows folders, including potential non-ASCII user-profile paths.

No confirmed catastrophic source corruption, cross-project decision leak, or externally exposed listener was detected in the tested cases.

## 3. Complete verified findings

### DESKTOP-001 — Unicode project database cannot open

- **Severity / confidence:** HIGH / CONFIRMED.
- **Location:** installed desktop onboarding, project folder `Audit B á # (test)`; packaged agent scan; `.pbibrain\brain.lbug`.
- **Preconditions:** existing valid PBIP project under a path containing a real non-ASCII character; native database stored beside that project.
- **Reproduction:** copy the disposable TMSL/legacy-report fixture to `Audit B á # (test)`; enter its name/path in the installed GUI; click Open project. Independently run packaged `project-scan` with its database beneath `Audit á (test)`. Repeat with precreated `.pbibrain`. Run identical ASCII control `Audit B # (test)`. Finally retain the Unicode sources but configure only the database under an ASCII sibling.
- **Expected:** valid Windows Unicode folders open and scan.
- **Actual:** Unicode database path fails with LadybugDB `IO exception: Cannot open file ... Error 3: The system cannot find the path specified`; GUI remains on onboarding and creates configuration without a usable database. ASCII control opens/scans 20 nodes/31 edges. Unicode sources scan when the database path is ASCII.
- **Evidence:** `unicode-open-error.jpg`, `b-control-snapshot.json`, independent V-003 in `verification/runtime-verification.md` and its saved fixture/run outputs.
- **User impact:** affected projects cannot use the core desktop workflow. The displayed advice to pass `use_native=False` is an internal test instruction and is unusable for a desktop user.
- **Likely cause:** native Windows database filename encoding/opening boundary. Path isolation supports this mechanism; the precise native-library implementation was not inspected.
- **Recommended fix:** correct the native Unicode filename boundary/runtime. If runtime repair is unavailable, design a stable supported storage location with proper project identity and migration; do not silently fall back to a test double. Present actionable desktop errors.
- **Regression scope:** GUI open, packaged agent scan, absent/precreated directory, ASCII spaces/`#`/parentheses control, Unicode sources with ASCII database, extended-path-prefix attempt. A `\\?\` prefix did not repair the failure.

### DESKTOP-002 — standard scan publishes invalid report containment

- **Severity / confidence:** MEDIUM / CONFIRMED.
- **Location:** packaged scan graph construction and graph-integrity validation.
- **Preconditions:** valid standard PBIP fixture with report `byPath` reference to its semantic model.
- **Reproduction:** scan the disposable TMDL/PBIR fixture A in the installed GUI; read `/api/brain` validation. Independently scan TMSL/legacy-report fixtures with the packaged agent and read `/api/overview` and `/api/brain`. Rescan and reopen.
- **Expected:** the standard model/report association produces a valid graph.
- **Actual:** the graph contains both `USES_MODEL(report, model)` and `CONTAINS(model, report)`. Validation reports `invalid_containment`, `MODEL cannot contain REPORT`, error count 1, blocking count 0. Scan itself succeeds.
- **Evidence:** `a-initial-snapshot.json`, `a-rescanned.json`, `b-control-snapshot.json`, independent V-001. Edge `edge:cfabf21d9c94f00e772af6ebfe0db9c8` connects model `11111111-1111-1111-1111-111111111111` to `report:Finance.Report`. Source: `backend/graph/loader.py:201-203`, `backend/validation/graph.py:314-323`.
- **User impact:** ordinary project graphs are internally invalid; ownership/layout consumers can receive an unsupported factual relation. This finding does not establish source-data corruption.
- **Likely cause:** loader and canonical containment contract disagree; the loader adds ownership for a model reference.
- **Recommended fix:** retain the factual `USES_MODEL` association and remove unsupported ownership, or deliberately reconcile the canonical contract if another relationship is intended.
- **Regression scope:** both source formats, repeated scans, server restart, folder move, stable-lineage table rename.

### DESKTOP-003 — scan validation errors are absent from Overview

- **Severity / confidence:** MEDIUM / CONFIRMED; independently verified as V-005.
- **Location:** installed Overview after successful scan.
- **Preconditions:** scan result containing the validation error in DESKTOP-002.
- **Reproduction:** scan A or ASCII B; inspect Overview and read the same running server's validation payload.
- **Expected:** an invalid result has a visible validation state and a route to its actionable error details.
- **Actual:** Overview shows counts, connected state, and “Ready for review” without the error or invalid state. The API simultaneously reports validation invalid.
- **Evidence:** native observations/journal; A/B snapshots; `frontend/src/App.jsx:522-557` contains no validation-state/error presentation.
- **User impact:** successful extraction appears ready while graph-integrity errors remain undisclosed. Users cannot assess graph trust from the main result screen.
- **Likely cause:** Overview renders object counts/review state without consuming validation state.
- **Recommended fix:** display validation state and concise error summary with a details route; preserve separate extraction success and graph-validation result.
- **Regression scope:** fresh TMDL/PBIR and TMSL/legacy scans. Reopen additionally loses runtime validation; that persistence question is separately unverified below.

### DESKTOP-004 — same-name review targets lack table context

- **Severity / confidence:** MEDIUM / CONFIRMED; independently verified as V-004.
- **Location:** installed Review queue, two `DateKey` columns.
- **Preconditions:** model contains both `Sales.DateKey` and `Date.DateKey`, each with name-only semantic suggestions.
- **Reproduction:** open Review queue after a fresh A/B scan; compare the first two rows and their Approve/Reject buttons.
- **Expected:** each decision row identifies which source object its action affects.
- **Actual:** both rows show `DateKey`, `Meaning: DateKey`, `Column`, identical name-only reason/evidence and 30% confidence. Table scope is absent. Opening Inspector provides further context but the decision row itself is indistinguishable.
- **Evidence:** `review-ambiguous.png`, `review-ambiguous.txt`, fresh B native accessibility tree; `frontend/src/App.jsx:787-799` renders label/type without owning table/model scope.
- **User impact:** users can approve or reject the wrong same-name object without knowing which row they chose.
- **Likely cause:** decision-card target label omits ownership context already available in the graph.
- **Recommended fix:** show table-qualified column/measure labels and relevant model/report scope beside each action.
- **Regression scope:** reproduced in TMDL and TMSL fixtures. Underlying decision targeting passed on fresh B; this is a presentation issue, not a confirmed bulk-approval bug.

## 4. Systemic/root-cause findings

The native filesystem boundary differs from Python source parsing: Unicode sources/identity writes work while the native database filename fails. Treat this as packaged runtime behavior, not a malformed project.

Graph publication, validation, and user-facing scan state need a shared contract. The loader creates an edge the validator rejects, and Overview does not present the rejection. These are distinct defects with a shared trust consequence.

Review actions use stable candidate identity correctly in repeated fresh-project checks. The UI's missing table scope creates ambiguity even when backend targeting is correct.

The desktop server uses a serialized `wsgiref` server (`backend/desktop/host.py:478-502`). A hung client or blocked handler is a possible mechanism for startup hangs, but no causal trace yet confirms it. Do not prescribe a server rewrite solely from the blank-window observation.

## 5. Project-data integrity assessment

Fifteen original fixture source files have identical final SHA-256 and modification timestamps to `source-baseline.json`; see `source-final-check.json`. The intentional malformed-A-source test restored its exact bytes and original timestamp. PBIBrain state was written beneath `.pbibrain`, including config, native graph, identity data, and semantic override. No production Power BI source was modified.

New A scanned to 17 nodes/24 edges; unchanged rescans preserved graph counts and manual meaning `Verified net revenue`. That override and project palette survived normal process close/relaunch and A→B→A switching. B used the same fixed source IDs but showed its own unmodified meanings and independently approved/rejected DateKey candidates; A retained its own state.

Independent packaged-agent checks retained an approval across restart, complete project-folder move, and table rename with unchanged lineage tag. Missing/malformed PBIP scans returned failures while preserving the previous 20-node/31-edge graph; restoration allowed retry. Parent GUI malformed-source scan likewise preserved the 17-node/24-edge graph and override.

No tested source corruption or project-state leak was detected. Crash/power-loss atomicity, concurrent same-database writers, orphan decisions after deletion, disk-full behavior, and unsupported partial source formats remain untested.

## 6. Desktop-runtime assessment

The installed GUI runs its loopback server and bundled native graph, with WebView2 child processes. Bundled Python/native files and packaged frontend exist; ordinary launch and shutdown were exercised. One normal close removed the app PID, loopback listener, WebView child root, and project `connection.json`.

The independently tested packaged agent scanned and served with PATH limited to Windows directories and with Python/Ladybug development environment variables removed or poisoned. This supports agent runtime bundling. It does not establish GUI clean-machine acceptance.

Two parent GUI launches with a stripped child environment remained blank beyond 60 seconds and their loopback HTTP requests timed out. This did not reproduce in independent ordinary/sanitized runs with continuously drained stdout/stderr: root, session and bootstrap returned HTTP200 after10 seconds; both exited cleanly. A final parent stripped-environment launch with regular-file stdout/stderr rendered native onboarding, opened an empty project with a native database, and displayed correct missing-source guidance. Earlier blank results remain a launch-harness/timing suspicion, not a confirmed dependency defect. Evidence: `sanitized-file-ready.jpg`, `sanitized-file-launch.json`, independent `startup-*.json` and logs. A clean Windows VM remains untested.

Windows scaling was changed through actual Settings, not browser zoom. At 100% the graph details footer was visible and Full inspector opened successfully. The user then restricted work to 100%; that setting is now applied and verified. Earlier higher-scale observations remain historical evidence only and are excluded from issue counts and release blockers.

Installer file and installed integration were inspected, but installer install/repair/upgrade/uninstall and WebView2 bootstrap were not executed in a disposable Windows environment. Internet-free/missing-WebView behavior therefore remains unverified.

## 7. Coverage report

“Partial” names a real test plus remaining gaps; it is not a pass for the whole area. Native tests used the installed EXE. Independent CLI/API tests used the installed packaged agent. Source review explains behavior. No development-browser test is presented as native acceptance.

| Requested area | Evidence-backed coverage and limits |
|---|---|
| 1 Desktop surface | Native onboarding, Overview, Search, Graph, Inspector, Review queue, Settings; install/build/frontend identities recorded. |
| 2 Clean machine | Agent stripped/poisoned environment passed; controlled GUI stripped startup and native DB creation passed; no clean VM. |
| 3 Startup | Ordinary relaunch ready; controlled sanitized/ordinary HTTP startup passed; parent rendered sanitized GUI. Earlier undrained-handle launches blank twice, unconfirmed. No boot/login or missing-WebView run. |
| 4 First run | Blank fields rejected; name/path entry, first-source/scan guidance seen. No novice usability study. |
| 5 Project selection | Native folder picker cancel; direct valid paths; empty folder routes to source setup, zero-source scan errors clearly; Unicode failure; reopen and switch. Nonexistent/permission-denied folders not exercised. |
| 6 Project name | Required name, spaces and Unicode display; existing persisted name honored on reopen. No extreme-length/RTL matrix. |
| 7 Scan | Native first scan, duplicate click guard/loading, repeated rescan, malformed failure and retry; resulting graph/state inspected. No very large scan/cancel test. |
| 8 Source immutability | 15 fixture files SHA-256+mtime unchanged; independent agent source manifest unchanged. |
| 9 .pbibrain lifecycle | New config/native DB, overrides/palette persistence, connection cleanup; Unicode open leaves config without usable DB. No forced crash/storage-corruption matrix. |
| 10 Persistence | Normal reopen, unchanged rescan, manual meaning and palette retained. Runtime last-scan/validation disappear on reopen; contract disposition below. |
| 11 Isolation | A→ASCII B→A, identical source IDs, separate graph counts/meaning/review states; stale request/concurrent switch races not exercised. |
| 12 Inspector | Measure browse/select, DAX, direct dependency/consumer, observed usage, disclosure, edit/save manual meaning. Clipboard, all types and huge evidence not covered. |
| 13 Trust | Fact/Inferred/Observed labels and line styles; name-only 30% reasoning; observed co-occurrence disclaimer. Validation visibility defective. |
| 14 Stable identity | Independent lineage-preserving table rename and moved project retained IDs/approval. Object deletion/recreation and missing-lineage ambiguity not covered. |
| 15 Incremental/rescan | Repeated unchanged scans and renamed-table scan; graph/override retained. No full add/remove/conflict corpus. |
| 16 Recovery | Missing/malformed source preserve prior graph; GUI retry passes; Unicode control succeeds. Disk full, permissions, corrupt DB not covered. |
| 17 Window lifecycle | Normal close/relaunch; maximize; dialog and sheet Escape. Minimize/sleep/monitor transfer not fully covered. |
| 18 DPI | Final authorized scope100%; graph footer and Full inspector passed at100%. Historical higher-scale tests excluded from assessment at user's request. |
| 19 Size matrix | 1920×1080, restored/maximized, one-column Inspector at175%; no other physical-resolution matrix. |
| 20 Keyboard | Native picker/sheet Escape and Alt+F4. Full Tab order, focus traps, Enter forms and screen-reader flow not covered. |
| 21 Pointer | Navigation, graph node selection/zoom, reviews, edit/save, palette; footer clipping observation. Full pan/drag/multi-select not covered. |
| 22 Text | Duplicate names, Unicode path/name and source error; no long formula/description, RTL or malicious markup matrix. |
| 23 Dialogs | Native folder/file pickers; cancel preserves state; file filter PBIP/JSON/BIM. Actual multi-file add/remove cycle not completed. |
| 24 Visual | Native screenshots of onboarding/review/error/Inspector/graph across DPI. Full view-by-view contrast/spacing audit incomplete. |
| 25 States | Empty input, first scan, loading, connected, pending review, disabled save, scan error/retry; stale async races not covered. |
| 26 Accessibility | Accessibility labels/tree observed; keyboard checks limited. No screen reader/high contrast/complete contrast measurements. |
| 27 Performance | Small 17/20-object projects responded interactively; no large-project latency/resource benchmark. |
| 28 Resources | Process/listener/WebView cleanup on normal close; no quantified long-term memory/handle growth. |
| 29 Package integrity | EXE/frontend hashes, native/Python files, frozen agent stripped/poisoned runtime, controlled ordinary/sanitized GUI startup and native empty-project DB creation. |
| 30 Paths | Spaces, Unicode, #, parentheses, nested paths; Unicode native DB failure confirmed. UNC, OneDrive sync, >260 characters and read-only paths not covered. |
| 31 Multi-instance | Not exercised; same-project locking and competing writers remain open. |
| 32 Critical termination | Normal close only; no mid-scan/review forced kill, power loss or restart atomicity test. |
| 33 Reviews | Fresh GUI single approval/rejection inspected per edge; manual edit persisted; independent restart/move/rename persistence. Conflict/stale/remove/all actions not covered. |
| 34 Search | Packaged API case variants/no-result; native SALES8/8 and NETSALES0/0 for B's spaced Net Sales name; input/results/filter labels. Pagination/back/focus/error matrix not covered. |
| 35 Factual graph | Counts, measure formula/dependencies/report usage, artifact/type/edge/empty API scopes; invalid containment confirmed. Full real-project truth corpus not covered. |
| 36 Errors | Missing/malformed source paths/parser details; Unicode exposes internal test advice. Full error-quality catalogue incomplete. |
| 37 Diagnostics | Process/network/file/UI/API evidence saved; EXE version fields blank. Crash/event-log and support-export flows not exercised. |
| 38 Security | Loopback binding; foreign Origin rejected403; local session routing source reviewed. Full hostile local-site/native-bridge/fuzz audit not performed. |
| 39 Power BI boundary | Source hashes/timestamps unchanged; UI review changes affect brain state only. No Power BI Desktop live-open integration. |
| 40 Installer | Package/installer/source/dependency bootstrap inspected; no isolated install/upgrade/repair/uninstall test. |
| 41 Windows integration | Native task/window identity and dialogs; installed entry/version inspection. Shortcut/pinning/file association/update matrix incomplete. |
| 42 Regressions | Fresh A/B controls; Unicode ASCII-db isolation; repeated scan/reopen and independent review targeting. No broad existing-suite execution attributed to package. |
| 43 Code review | Graft-guided host/server/project scan/review/Overview/Inspector/sheet/runtime/storage spans; evidence-linked only, not a whole-repo static audit. |
| 44 Repetition | Multiple native scans/reopens, two stripped GUI launches, independent fixture scan/move/rename repetitions. No high-iteration automation soak. |
| 45 Long session | Extended interactive audit session across views/projects/scales; no controlled fixed-duration resource soak or idle/resume test. |

## 8. Unverified risks

1. **Earlier blank GUI startup:** two parent observations did not reproduce with independently drained handles or parent file-backed logs. Controlled stripped GUI startup passed. Treat earlier failures as a harness/timing suspicion; exact closed-handle reproduction or a clean VM is required to attribute a production defect.
2. **Initial A double-approval observation:** initial saved API state showed both DateKey edges approved after one recorded click. Independent packaged API and fresh parent B GUI both changed only the selected candidate. Treat as SUSPECTED; requires GUI request trace and fresh repeated A reproduction. Do not count as a confirmed defect.
3. **Higher-scale layout observations excluded:** user restricted work to100%. No 100% graph-footer defect was detected; earlier clipping observations are not counted as findings or release gates.
4. **Scan timestamp/validation persistence:** graph and overrides reopen, but overview shows `Last scan time unavailable` and runtime validation returns `not_run`. Runtime-only validation is explicit in repository comments; decide the product contract before calling this a defect. A persisted scan summary or revalidation could improve trust.
5. **Unexecuted high-risk environments:** clean Windows/WebView bootstrap, installer upgrade/uninstall, same-project multi-instance locking, mid-write termination, permissions/disk-full/corrupt database, large real projects, UNC/synchronized folders, full accessibility and multi-monitor matrix require separate evidence. These gaps are acceptance risks, not invented defects.

## 9. Clean areas

Within the tested fixtures: ordinary installed workflow, native bundled graph extraction, manual meaning/palette persistence, stable-ID approval persistence, moved project, lineage-preserving rename, A/B state isolation, source immutability, malformed/missing-source graph preservation and retry, native picker cancellation, loopback-only listener, foreign-Origin rejection, normal process/listener/WebView cleanup, and fresh single-candidate approval/rejection produced no detected defect in their checked behavior. This statement is intentionally limited to the recorded cases.

## 10. Release blockers

DESKTOP-001 blocks normal project operation for non-ASCII project/database paths and should be resolved before a general Windows release. No evidence establishes source corruption or a catastrophic security failure.

Actual clean-machine startup and installer lifecycle acceptance remain open release gates, rather than assumed passes; controlled sanitized startup has passed. The invalid standard containment and undisclosed validation should be corrected before presenting graph output as validated. Do not characterize this audit as proof that all requested environments are bug-free.
