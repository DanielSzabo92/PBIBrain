# Brain Inspector

Run the UI:

```powershell
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`. Set `$env:BRAIN_API_URL` to use another local API address.

The local API exposes the legacy snapshot/review endpoints plus targeted routes used by the main workflow:

- `GET /api/config`, `POST /api/config`, `POST /api/scan`
- `GET /api/overview`, `GET /api/search`, `GET /api/graph`, `GET /api/objects/:id`

The graph page requests a bounded server-side neighborhood. Search is server-side and can be scoped to one model or report. The configuration page edits the project name and sources; database and identity-map paths remain server-owned and require a restart after manual changes.

Run `npm test` for the transport contract checks. The backend WSGI app is created with `backend.api.app.create_app`.

## Graph and appearance

The graph uses React Flow with separate report, model, and other artifact regions. Cross-region arrows keep their canonical direction. Model/report scope, text, object type, status, and relationship filters run on the API before the node limit; the count and **Show more** control make truncation visible. **Center graph here** enables the distance selector. Object-type filtering retains an explicit center for context.

Click a node (or focus it and press Enter) to open its right-side details sheet. Properties, lineage, and evidence load from the object endpoint. Escape closes the sheet. The full Inspector and its review actions remain available.

**Settings → Graph colors** edits the group palette and optional type overrides. **Save colors** persists `graph_colors` in the project's `brain.json`; colors survive restarts and travel with the project. Group defaults apply to types without an override. **Restore defaults** updates the draft; save to apply it. Nodes, group outlines, the minimap, legend, search results, and Inspector use the same palette. Status stays labeled; solid, dashed, and dotted arrows identify factual, inferred, and observed evidence.

UI primitives are the basic [shadcn/ui components](https://ui.shadcn.com/docs/installation/vite), generated into `src/components/ui`. `components.json`, `jsconfig.json`, and the Vite alias support adding components. Tailwind theme variables live in `src/theme.css`; existing page layout rules remain in `src/styles.css`.

## Browser acceptance

Run `npx playwright install chromium` once, then `npm run test:e2e`. Python dependencies (including the native Ladybug runtime) must be installed. The suite scans an isolated temporary model/report project, closes and reopens its native database, and serves the production frontend through the real API. It covers grouping, filters, node details, persisted colors, keyboard/mobile use, failure recovery, stale responses, and the shared GUI. It never uses the current project's sources or database.

Set `PLAYWRIGHT_CHANNEL=msedge` to use an installed Edge browser instead. Screenshots and failure traces go to `frontend/test-results/`.
