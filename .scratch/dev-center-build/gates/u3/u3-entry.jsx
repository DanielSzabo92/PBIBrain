// Gate build entry (step U3): renders one Development Center screen from fixture data, with no app,
// no server, and no shim, so that the kit gates can open one static file from file://.
// The page sets window.__U3_SCREEN__ to "list", "create", or "work" before this script.
import React from "../../../../frontend/node_modules/react/index.js";
import { createRoot } from "../../../../frontend/node_modules/react-dom/client.js";
import { ToastProvider } from "../../../../frontend/src/components/ui/toast.jsx";
import { createDevCenterHttp } from "../../../../frontend/src/devcenter/httpClient.js";
import { createDevCenterStore } from "../../../../frontend/src/devcenter/store.js";
import { DevCenterProvider } from "../../../../frontend/src/devcenter/useDevCenter.js";
import DevCenter from "../../../../frontend/src/devcenter/screens/DevCenter.jsx";
import CreateSession from "../../../../frontend/src/devcenter/screens/CreateSession.jsx";
import WorkArea from "../../../../frontend/src/devcenter/screens/WorkArea.jsx";
import SESSION from "../../../../tests/fixtures/devcenter_ui/sources-changed/session.json";
import SESSIONS from "../../../../tests/fixtures/devcenter_ui/locked/sessions.json";
import PLAN from "../../../../tests/fixtures/devcenter_ui/default/plan.json";
import "../../../../frontend/src/theme.css";
import "../../../../frontend/src/app.css";
import "../../../../frontend/src/devcenter/devcenter.css";

const screen = window.__U3_SCREEN__ || "list";
let revision = SESSION.revision;

const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
window.fetch = async (url) => {
  const path = String(url);
  if (path.endsWith("/api/devcenter/sessions")) return json(200, { ...SESSIONS, revision: null });
  if (path.endsWith("/api/devcenter/session")) {
    if (screen === "list") return json(409, { error: { code: "session_not_open", message: "No session is open.", details: {} } });
    return json(200, { ...SESSION, revision });
  }
  if (path.includes("/api/devcenter/plan")) return json(200, { ...PLAN, revision });
  return json(404, { error: { code: "not_found", message: "Not in the gate build.", details: {} } });
};
const api = new Proxy({}, {
  get: (_target, method) => async () => {
    if (method === "sources_check") return { revision, sources: [], mark_count: SESSION.counts.marks };
    if (method === "choose_folder") return { ok: true, folder: "merge-lab" };
    if (method === "choose_sources") return { ok: true, sources: ["sources/Sales.SemanticModel"] };
    return { revision };
  },
});
window.pywebview = { api };

function Screen() {
  if (screen === "list") return <DevCenter onOpenProject={() => {}} />;
  const store = React.useMemo(() => createDevCenterStore({ http: createDevCenterHttp(), api }), []);
  return (
    <DevCenterProvider store={store}>
      <ToastProvider>
        <div className="dc-root">
          {screen === "create" ? <CreateSession onCancel={() => {}} onDone={() => {}} onOpenPartial={() => {}} /> : null}
          {screen === "work" ? <WorkArea session={SESSION} tabState={{ tab: "sources", marks: false }} onTabs={() => {}} onRetryLock={() => {}} onClose={() => {}} /> : null}
        </div>
      </ToastProvider>
    </DevCenterProvider>
  );
}

createRoot(document.getElementById("root")).render(<main className="content"><Screen /></main>);
