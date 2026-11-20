---
title: "A source checkout must rebuild the web UI after git pull, or the app keeps serving the old UI against new backend code"
author: Claude
date: 2026-11-20
branch: claude/gallant-cerf-0prgd3
cost: { minutes: 5, tokens: 116802 }
id: l-93043a23
scope: repo
status: active
src: agent
touches:
  - backend/ui_build.py
  - start.bat
  - start.sh
  - frontend/src/devcenter/copy.js
  - backend/desktop/host.py
  - frontend/src/devcenter/screens/TargetChoice.jsx
---

## Decided
start.bat, start.sh, the desktop launcher and `serve` check whether frontend/dist is older than the frontend sources, not only whether it exists. The start scripts and the desktop launcher (source checkout only) run npm to rebuild; `serve` prints a warning.

## Tried and ruled out
Reading a user report as "the fix for #74 did not work": the screenshot showed copy that #74 had removed ("Load the row again", "The session exists, but N sources were not added"). The fix was in the code; the user's frontend/dist was from before it, because start.bat only built when dist/index.html was missing.

## Watch out
When a user screenshot shows copy that is no longer in frontend/src/devcenter/copy.js, the UI build is stale; check that before debugging. A target folder left full by an earlier run gives "Select an empty folder" at Create; choose_folder now returns `empty` so the Target step refuses it first.

In the code: backend/ui_build.py (stale_reason, ensure_current), start.bat / start.sh step 4, backend/desktop/host.py run() and choose_folder, frontend/src/devcenter/screens/TargetChoice.jsx.
