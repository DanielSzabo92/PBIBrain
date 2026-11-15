// The address of what is on screen, kept in the URL hash so a reload, the Back button and a pasted
// link all land on the same view and object. No server route is involved: the hash never leaves the page.

const VIEW_PATHS = { overview: "", search: "search", graph: "graph", inspector: "inspector", review: "review", devcenter: "merge", config: "settings" };
const PATH_VIEWS = Object.fromEntries(Object.entries(VIEW_PATHS).map(([view, path]) => [path, view]));

/** @returns {string} the hash for a place in the app, e.g. "#/inspector/model%3Asales". */
export function routeHash({ view = "overview", selectedId = null, settingsTab = "", query = "", focus = "" } = {}) {
  const path = VIEW_PATHS[view] ?? "";
  if (view === "inspector") return selectedId ? `#/inspector/${encodeURIComponent(selectedId)}` : "#/inspector";
  if (view === "config") return settingsTab && settingsTab !== "project" ? `#/settings/${encodeURIComponent(settingsTab)}` : "#/settings";
  if (view === "search") return query ? `#/search?q=${encodeURIComponent(query)}` : "#/search";
  if (view === "graph") return focus ? `#/graph?focus=${encodeURIComponent(focus)}` : "#/graph";
  return `#/${path}`;
}

/** Reads a hash back. Anything unknown is the Overview, so an old or mistyped link still opens the app. */
export function parseRoute(hash) {
  const text = String(hash || "").replace(/^#\/?/, "");
  const [pathPart, queryPart = ""] = text.split("?");
  const [head = "", ...rest] = pathPart.split("/");
  const view = PATH_VIEWS[head] ?? "overview";
  const tail = safeDecode(rest.join("/"));
  const params = new URLSearchParams(queryPart);
  return {
    view,
    selectedId: view === "inspector" && tail ? tail : null,
    settingsTab: view === "config" ? tail || "project" : "",
    query: view === "search" ? params.get("q") || "" : "",
    focus: view === "graph" ? params.get("focus") || "" : "",
  };
}

function safeDecode(value) {
  try { return decodeURIComponent(value); } catch { return value; }
}
