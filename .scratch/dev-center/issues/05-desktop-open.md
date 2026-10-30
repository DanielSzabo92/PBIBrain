# What happens when the app changes files while Power BI Desktop has the project open?

Type: research
Status: resolved
Blocked by: 

## Question

For TMDL and for PBIR: does Power BI Desktop detect external changes, ignore them, or overwrite them on the next save? Which changes does it reject? Can the app detect that Desktop has the project open? What must the app do before and after an apply?

## Answer

Findings: branch `research/desktop-open`, file `.scratch/dev-center/research/05-desktop-open.md` (not merged, not pushed).

- Desktop detects saved external changes. It shows an "Apply external changes" banner. It does not apply them by itself.
- "Apply" reloads the full report, the full model, or both. It discards unsaved Desktop changes. "Cancel" keeps them, and a later Desktop save can overwrite the external change (exact result not documented).
- Invalid PBIR or invalid TMDL blocks the load. The full list of TMDL changes that Desktop rejects is not documented.
- Some files must not change outside Desktop: report.json (PBIR-Legacy), mobileState.json, diagram layout files. The findings also list definition.pbir; confirm this before the design relies on it.
- There is no documented lock file. The existing Desktop bridge (named pipe and application state call) can tell which file is open and if it has unsaved changes.
- Before an apply: make sure that Desktop has no unsaved changes for the target (or that the target is not open). Write UTF-8 without BOM.
- After an apply: tell the user to select "Apply external changes", or reload through the bridge.
- Consequence for the design: the apply step needs a "target open in Desktop" check. Ticket "How does the Change Plan engine work?" and the first-version ticket must include it.
