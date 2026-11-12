# 16 · One 1.24 MB script, one 2,277-line component

**Severity:** P2 · **Criteria:** performance, production readiness

## Evidence

`vite build` on the current tree:

| Asset | Size | gzip |
|---|---|---|
| `index-*.js` (main chunk) | **1,244 kB** | 365 kB |
| `index-*.css` | 247 kB | 44 kB |
| `GraphView-*.js` | 82 kB | 27 kB |
| Fonts | 14 woff2 files (Inter + JetBrains Mono, incl. Cyrillic, Greek, Vietnamese subsets) | — |

Vite prints its own >500 kB warning. The Merge models code (`devcenter/`, 59 files) is inside the main chunk: `App.jsx:33-38` lazy-loads six components but not `DevCenter`. The build of 7 Nov still had a separate `DevCenter-*.js` (266 kB), so this is a regression. Users who never merge pay for it at start.

Structure:

- `frontend/src/App.jsx` is **2,277 lines / 72 symbols**: shell, router state, Overview, Search, Review queue, Settings and all data loading in one module. Any state change at the top re-renders every view's props.
- `frontend/src/app.css` is 1,858 lines of global selectors beside Tailwind; the palette bug (02) is the kind of drift this allows — CSS and JSX reference each other only by string.

## Solution

1. **Route-level code splitting.** `React.lazy` for `DevCenter` (restore), `ReviewQueue`, `SettingsView` and `CommandPalette`, next to the six that are already lazy. Target: entry chunk under 200 kB gzip together with step 2.
2. **Vendor chunks** via `build.rollupOptions.output.manualChunks`: `react`, `radix`, `xyflow+dagre`, `icons`. Check `radix-ui` umbrella imports tree-shake; if not, import the scoped packages actually used.
3. **Split `App.jsx`** into `views/Overview.jsx`, `views/Search.jsx`, `views/Review/*`, `views/Settings/*`, `shell/*`, and a `useProject()` data hook. Each view fetches its own data through a small cache (`useQuery`-style: key, stale time, abort) instead of `load()`/`loadSnapshot()` at the root.
4. **CSS ownership.** Move view styles next to their components (CSS modules or one file per view imported by that view) so unused rules fail the build or disappear with the component. Add `stylelint` + a script that reports class names used in JSX with no rule and rules with no user.
5. **Fonts.** The UI font is "Segoe UI Variable → Inter". Ship Inter latin + latin-ext only, load the rest by `unicode-range` (fontsource already splits them; make sure they are not preloaded). Preload only the two latin files.
6. **Budgets in CI:** fail the build when the entry chunk exceeds 200 kB gzip or total CSS exceeds 60 kB gzip (`rollup-plugin-visualizer` report as an artifact).

## Acceptance

- Entry JS ≤ 200 kB gzip; Merge models code loads only when the view opens.
- `App.jsx` ≤ 400 lines.
