# 05 · The Overview tells the user things that are not true

**Severity:** P0 (trust) · **Criteria:** accomplishes its goals, self-explanatory UI

## Evidence

![Overview on the large project](evidence/overview-large.png)

On a project with 2,400 measures and 11,528 open suggestions, the first screen says:

| Widget | Shows | Truth |
|---|---|---|
| Most-used measures | "None · No measures defined in the loaded models." | 2,400 measures |
| Unreviewed on hot objects | "Clean · No pending suggestions or conflicts" | 11,528 pending |
| Recently changed | "Idle" | unknown |
| Validation summary | "No schema or dependency issues detected." under a "Graph validation not run" badge | not checked |
| Sources | "8 sources" in one row, "the 32 sources" two cards lower | 8 files; 32 = models + reports |
| Scan | "Last scan time unavailable" / "Last scan time unknown" | scanned seconds ago |
| Review count | sidebar "99+", status bar "11,528 to review" | one number, two forms |

Cause: the three widgets are computed in the browser from `snapshot` (`App.jsx:1109`), which is only loaded when the Review queue is opened. An unloaded snapshot is rendered as an empty one. `last_scan` is null for a freshly scanned project.

For a tool whose value is "authoritative understanding", a wrong "Clean" on the home screen is the most damaging defect in the product.

## Solution

1. **Server-computed widgets.** Add `top_measures` (by inbound DEPENDS_ON/USES count), `hot_unreviewed` and `recent_decisions` to the cached overview payload (03). The browser renders, it does not derive.
2. **Three states, never two.** Every widget has `loading` (skeleton), `unknown` (grey dash + reason: "Run validation") and `value`. "None", "Clean", "0" are only allowed when the server said so. Add a unit test: `OverviewView` with `snapshotLoaded=false` must not render the strings "None", "Clean", "No measures".
3. **Validation card:** before a run, show only "Not run" + the Run button. Remove "No schema or dependency issues detected."
4. **One vocabulary for counts.** "Source" = a file or cloud item in the project (8). The commonality card says "across 8 models and 24 reports". The review count is the same number everywhere; abbreviate as `11.5k` in the sidebar badge instead of "99+", full number in the tooltip.
5. **Scan time.** Persist `last_scan` (UTC) and duration in the repository at the end of every scan; show "Scanned 2 min ago · 21 s" with the absolute time in a tooltip. Never show the word "unknown" after a successful scan.
6. Remove the focus outline that draws a white box around the h1 on load (see 15).

## Acceptance

- On the large fixture, Most-used measures lists 5 measures with reference counts within 1.5 s of load.
- No widget shows a zero/empty claim while its data is not loaded.
