# 10 · No deep links, no Back, state is lost on reload

**Severity:** P1 · **Criteria:** easy and obvious, navigation

## Evidence

- Loading `/#/graph`, `/#/review`, `/#/settings` always shows Overview. The view is React state only (`App.jsx`, `view`), there is no `hashchange` handling.
- The visual contract §8 specifies hash routes (`#/search?q=`, `#/graph?view=&focus=`, `#/inspector/<id>`, `#/merge`, `#/settings/<section>`) and Alt+← back. They were not built.
- Consequences: F5 or a crash returns to Overview and drops the search, the selected object and the graph focus; the browser Back button leaves the app; an object cannot be linked from a ticket, a PR, the chat answer, or an MCP agent's reply; the Inspector needs its own "Back to graph" button to fake history.

For a tool whose second audience is AI agents, "open this exact object" is a core integration point.

## Solution

1. **A small router over the hash** (no dependency needed): `parseRoute(location.hash) → {view, params}` and `navigate(route, {replace})`. `view`, `selectedId`, search query + filters, graph `view`/`focus`, review `issue`/`type`/`tab`, settings section all derive from the route; local UI state (scroll, expanded rows) stays in session storage keyed by route.
2. `pushState` on navigation between views and object selections; `replaceState` for typing in search and for filter changes.
3. **Back/Forward:** Alt+←/→ and mouse buttons 4/5 work for free; add ‹ › buttons in the title bar next to the menus (as in VS Code and Explorer). Remove the special "Back to graph" button.
4. **Copy link** in the object header and pane (`Link` glyph). In the desktop shell use a `pbibrain://object/<id>` protocol handler that focuses the running window.
5. Chat answers and MCP tool replies render object references as these links.
6. Restore the last route on start (stored per project).

## Acceptance

- Reload on any view returns to the same view, object, filters and graph focus.
- e2e: `page.goto("/#/inspector/<id>")` shows that object; `page.goBack()` returns to the previous view.
