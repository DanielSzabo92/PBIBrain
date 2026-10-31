# How does the user get into a merge session, and how is the work area laid out?

Type: grilling
Status: open
Blocked by: 01

## Question

Design the entry and the frame of the Development Center: the sidebar item, the "Merge sessions" list, the create-session flow, and the layout of the work area of an open session. Which sub-views does the work area have, how does the user move between them, and what does each session state look like?

## Context

- Charting decisions 2 and 5 (map): one sidebar item "Development Center" in `frontend/src/App.jsx` (`VIEWS`); session list as its landing; target 1440 x 900, minimum 1024 x 640; below 1280 wide, side panes become sheets.
- Session data: technical design section 11 and section 14.1 `GET session` (sources with kind, role, access type, status, fingerprint state; target; compare mode; plan status; counts; open questions; open proposals).
- JS API calls in scope: `session_create`, `session_open`, `session_close`, `source_add`, `source_remove`, `source_relink`, `target_set`, `compare_mode_set`, `sources_check`, `row_confirm`.
- Create flow: sources (local kinds of section 2.1; cloud sources are in ticket 07), target model and target report selection (spec section 5), target kinds "existing", "Empty", "Copy of <local source>" (section 2.2), the fixed refusal messages for TMSL, PBIR-Legacy, and PBIX targets.
- States to design: no sessions, session locked by another process (read-only), session with newer schema (refused), source changed marks and the confirm flow (section 11), source missing and relink, plan Invalid / Valid with warnings / Valid in the header.
- Existing parts to reuse: `PageHeading`, `EmptyState`, `Card`, `Tabs`, `Sheet`, toast in `App.jsx`.
- Skills: `design-doctrine`, `design-screen` (run its taste preflight and Brief Inference).

## Done when

The answer gives: the screen list with a wireframe (ASCII or prototype screenshot) for each, the sub-view list of the work area and the navigation between them, the create flow steps, each session state with its look and copy draft, and the responsive rule for each pane. All layout claims are measured (ticket 01) or marked UNMEASURED.
