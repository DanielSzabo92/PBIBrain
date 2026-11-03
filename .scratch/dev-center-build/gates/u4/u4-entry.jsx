// Gate build entry (step U4): renders the Compare grid screen from fixture data,
// with no backend server, so that the kit gates can open one static HTML file.
import React from "../../../../frontend/node_modules/react/index.js";
import { createRoot } from "../../../../frontend/node_modules/react-dom/client.js";
import { ToastProvider } from "../../../../frontend/src/components/ui/toast.jsx";
import { createDevCenterHttp } from "../../../../frontend/src/devcenter/httpClient.js";
import { createDevCenterStore } from "../../../../frontend/src/devcenter/store.js";
import { DevCenterProvider } from "../../../../frontend/src/devcenter/useDevCenter.js";
import WorkArea from "../../../../frontend/src/devcenter/screens/WorkArea.jsx";
import SESSION from "../../../../tests/fixtures/devcenter_ui/default/session.json";
import SESSIONS from "../../../../tests/fixtures/devcenter_ui/default/sessions.json";
import PLAN from "../../../../tests/fixtures/devcenter_ui/default/plan.json";
import COMPARE_ROWS from "../../../../tests/fixtures/devcenter_ui/default/compare-rows.json";
import DISPLAY_FOLDERS from "../../../../tests/fixtures/devcenter_ui/default/display-folders.json";
import "../../../../frontend/src/theme.css";
import "../../../../frontend/src/app.css";
import "../../../../frontend/src/devcenter/devcenter.css";
import "../../../../frontend/src/devcenter/components/compare.css";

const revision = SESSION.revision;

const json = (status, body) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

window.fetch = async (url) => {
  const path = String(url);
  if (path.endsWith("/api/devcenter/sessions")) {
    return json(200, { ...SESSIONS, revision: null });
  }
  if (path.endsWith("/api/devcenter/session")) {
    return json(200, { ...SESSION, revision });
  }
  if (path.includes("/api/devcenter/plan")) {
    return json(200, { ...PLAN, revision });
  }
  if (path.includes("/api/devcenter/display-folders")) {
    return json(200, { ...DISPLAY_FOLDERS, revision });
  }
  if (path.includes("/api/devcenter/compare-rows")) {
    return json(200, {
      revision,
      rows: COMPARE_ROWS.rows,
      total: COMPARE_ROWS.rows.length,
      state_counts: {
        different: 1,
        conflict: 1,
        missing: 1,
        renamed: 1,
        same: 2,
      },
      compare_mode: "default",
    });
  }
  return json(404, {
    error: { code: "not_found", message: "Not in gate build.", details: {} },
  });
};

const api = new Proxy(
  {},
  {
    get: (_target, method) => async () => {
      if (method === "sources_check") {
        return { revision, sources: [], mark_count: SESSION.counts.marks };
      }
      return { revision };
    },
  }
);
window.pywebview = { api };

function Screen() {
  const store = React.useMemo(
    () => createDevCenterStore({ http: createDevCenterHttp(), api }),
    []
  );
  return (
    <DevCenterProvider store={store}>
      <ToastProvider>
        <div className="dc-root">
          <WorkArea
            session={SESSION}
            tabState={{ tab: "compare", marks: false }}
            onTabs={() => {}}
            onRetryLock={() => {}}
            onClose={() => {}}
          />
        </div>
      </ToastProvider>
    </DevCenterProvider>
  );
}

createRoot(document.getElementById("root")).render(
  <main className="content">
    <Screen />
  </main>
);
