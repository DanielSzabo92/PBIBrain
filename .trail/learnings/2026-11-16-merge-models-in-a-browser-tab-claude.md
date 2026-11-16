---
title: "Merge models in a browser tab shows a desktop-only notice, and the chat asks for the session list before the session"
author: Claude
date: 2026-11-16
branch: claude/nice-pasteur-ppkrv8
cost: { minutes: 16, tokens: 233135 }
id: l-75ce440f
scope: repo
status: active
src: agent
touches:
  - start.sh
  - start.bat
  - frontend/src/devcenter/screens/SessionList.jsx
  - frontend/src/desktop.js
  - frontend/src/transport.js
  - frontend/src/devcenter/screens/DevCenter.jsx
  - README.md
---

## Decided
- Merge sessions are created and changed only through the desktop JS API (an earlier learning: no web endpoint applies merges). In a browser tab (start.sh / start.bat) "Add source" threw "Desktop service is unavailable" (issue #69). The session list now shows a notice and disables "New merge session" when `pywebview.api` is absent; desktopRequest's error says to use the desktop app.
- GET /api/devcenter/session answers 409 when no session is open, which the browser logs (issue #70). The chat chip and the Merge view's first load read GET /api/devcenter/sessions first (always 200; `revision` is null when no session is open) and only then GET session. The 409 contract stays.

## Watch out
- e2e specs inject a pywebview shim before the app module, so the notice does not show there; a spec without the shim sees disabled create buttons.

In the code: frontend/src/devcenter/screens/SessionList.jsx, frontend/src/desktop.js (hasDesktopApi, DESKTOP_ONLY_MESSAGE), frontend/src/transport.js getMergeSession, frontend/src/devcenter/screens/DevCenter.jsx first-view effect.
