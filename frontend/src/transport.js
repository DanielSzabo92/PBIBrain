const API_ROOT = "/api";

function apiError(response, body) {
  const err = body?.error;
  const detail = typeof body === "string"
    ? body
    : body?.detail || body?.message || (typeof err === "string" ? err : err?.message) || (err ? JSON.stringify(err) : "");
  return new Error(detail || `${response.status} ${response.statusText}`);
}

async function jsonRequest(fetcher, url, options = {}) {
  const response = await fetcher(url, {
    ...options,
    headers: { Accept: "application/json", ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw apiError(response, body);
  return body;
}

/**
 * Local UI seam. The backend owns graph truth; the UI only reads it and sends
 * review commands. Tests and an embedded host can inject this transport.
 */
export function createBrainTransport({ baseUrl = API_ROOT, fetcher = globalThis.fetch } = {}) {
  const request = (path, options) => {
    if (typeof fetcher !== "function") throw new Error("No local Brain transport configured");
    return jsonRequest(fetcher, `${baseUrl}${path}`, options);
  };
  return {
    /**
     * One page of the review queue, counted and filtered on the server (finding 01): rows with the objects
     * they show, the filter choices, the totals and, with grouping=pattern, the patterns. ``target`` gives one
     * object's open suggestions and conflicts; ``tab: "reviewed"`` pages the decided ones.
     */
    getReviewPage(params = {}) {
      const query = new URLSearchParams();
      for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
      return request(`/review/page?${query}`);
    },
    // Decisions answer with a summary: the page asks for the rows it shows again instead of receiving the graph.
    async review(action, payload) {
      return request("/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...payload, reply: "summary" }),
      });
    },
    // One request, one write on the server, one undo token. ``items`` names the suggestions, or
    // ``{ view, except }`` lets the server choose what the queue shows for those filters.
    async reviewBulk(action, items, { view = null, except = null } = {}) {
      const body = view ? { action, view, ...(except?.length ? { except } : {}), reply: "summary" } : { action, items, reply: "summary" };
      return request("/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    },
    /** Puts back exactly the statuses that the bulk decision with this token replaced. */
    async reviewBulkUndo(token) {
      return request("/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "undo", token, reply: "summary" }),
      });
    },
    getOverview() {
      return request("/overview");
    },
    getModelSummary(modelId) {
      const params = new URLSearchParams({ model_id: modelId });
      return request(`/model-summary?${params}`);
    },
    /** PDF or Markdown documentation of the loaded scan, built by the running server (issue #15). */
    exportDocumentation({ format = "pdf", modelIds = null, reportIds = null, sections = null } = {}) {
      return request("/documentation-export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ format, model_ids: modelIds, report_ids: reportIds, sections }),
      });
    },
    /** Project files changed outside the app since the last scan, with Breaks and Needs (issue #17). */
    getPendingChanges() {
      return request("/pending-changes");
    },
    /** In-app chat (issue #7). Provider calls run in the backend; the page never sees the API key. */
    getChatSettings() {
      return request("/chat/settings");
    },
    saveChatSettings(settings) {
      return request("/chat/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(settings) });
    },
    testChatConnection() {
      return request("/chat/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    },
    /** The models and efforts of one provider: live where it can list them, else the built-in list. */
    getChatModels(provider, refresh = false) {
      return request(`/chat/models?provider=${encodeURIComponent(provider)}${refresh ? "&refresh=true" : ""}`);
    },
    startChat({ text, conversationId = null, context = {}, provider = null, model = null, effort = null }) {
      // The provider, model and effort of the chat's pickers; null keeps the default of Settings.
      const pick = Object.fromEntries(Object.entries({ provider, model, effort }).filter(([, value]) => value !== null && value !== undefined));
      return request("/chat/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, conversation_id: conversationId, context, ...pick }),
      });
    },
    chatEvents(runId, after = 0) {
      return request(`/chat/runs/${encodeURIComponent(runId)}?after=${Number(after) || 0}`);
    },
    stopChat(runId) {
      return request(`/chat/runs/${encodeURIComponent(runId)}/stop`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    },
    /**
     * The open Merge models session, or null when none is open (the context chip of the chat).
     * The session list always answers 200 and has a null revision when no session is open, so it is
     * read first: asking for the session itself with none open gives a 409 the browser logs as an error.
     */
    async getMergeSession() {
      try {
        const list = await request("/devcenter/sessions");
        if (!Number.isInteger(list?.revision)) return null;
        return await request("/devcenter/session");
      } catch {
        return null;
      }
    },
    getConfig() {
      return request("/config");
    },
    /** Adds the bundled sample source to the project and returns the saved configuration. */
    addSample() {
      return request("/sample", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    },
    /** Whether each configured source path exists on disk. */
    getSourceStatus() {
      return request("/config/sources");
    },
    saveConfig(config) {
      return request("/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
    },
    /** What the running scan is doing: { running, phase, done, total }. Answered while the scan request is open. */
    scanStatus() {
      return request("/scan/status");
    },
    /**
     * Scans the project. The server scans on a worker and this waits by polling its status, so every
     * other request is answered meanwhile and the scan can be cancelled. Resolves to
     * { overview, source_count }; rejects with error.cancelled === true when the scan was cancelled.
     */
    async scan() {
      const started = await request("/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ background: true }),
      });
      if (started?.overview) return started; // a server that scans inside the request
      for (;;) {
        await new Promise((resolve) => setTimeout(resolve, 400));
        const status = await request("/scan/status");
        const last = status?.last;
        if (status?.running || !last || (started?.scan && last.scan !== started.scan)) continue;
        if (last.state === "done") return { overview: await request("/overview"), source_count: last.source_count };
        const error = new Error(last.state === "cancelled" ? "Scan cancelled" : last.error || "Scan failed");
        error.cancelled = last.state === "cancelled";
        throw error;
      }
    },
    /** Stops the running scan before it publishes; the graph stays as it was. */
    cancelScan() {
      return request("/scan/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    },
    search({ query = "", modelId = "", reportId = "", objectType = "", limit = 50, offset = 0 } = {}) {
      const params = new URLSearchParams({ q: query, limit: String(limit), offset: String(offset) });
      if (modelId) params.set("model_id", modelId);
      if (reportId) params.set("report_id", reportId);
      if (objectType) params.set("object_type", objectType);
      // The search page lists project objects; alias and concept records repeat their names.
      else params.set("kind", "objects");
      return request(`/search?${params}`);
    },
    getGraph({ centerId = "", modelId = "", reportId = "", depth = 1, limit = 100, query = "", artifact = "", objectType = "", status = "", edgeType = "" } = {}) {
      const params = new URLSearchParams({ depth: String(depth), limit: String(limit) });
      if (centerId) params.set("center_id", centerId);
      if (modelId) params.set("model_id", modelId);
      if (reportId) params.set("report_id", reportId);
      for (const [key, value] of Object.entries({ query, artifact, object_type: objectType, status, edge_type: edgeType })) {
        if (value) params.set(key, value);
      }
      return request(`/graph?${params}`);
    },
    /** The whole factual structure of a scope, compact and without an object limit (lineage and matrix). */
    getLineage({ modelId = "", reportId = "" } = {}) {
      const params = new URLSearchParams();
      if (modelId) params.set("model_id", modelId);
      if (reportId) params.set("report_id", reportId);
      const search = String(params);
      // The payload leaves out edge ids and status (all factual, unique by type and ends) to stay small.
      return request(`/lineage${search ? `?${search}` : ""}`).then((result) => ({
        ...result,
        edges: (result?.edges || []).map((edge) => ({ id: `${edge.type}|${edge.from_id}|${edge.to_id}`, status: "factual", ...edge })),
      }));
    },
    /** Common / divergent / unique objects across the project's models and reports (issue #14). */
    getCommonality({ type = "", scope = "", bucket = "", groupId = "", limit = 50, offset = 0 } = {}) {
      const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
      for (const [key, value] of Object.entries({ type, scope, bucket, group_id: groupId })) {
        if (value) params.set(key, value);
      }
      return request(`/commonality?${params}`);
    },
    getObject(id) {
      return request(`/objects/${encodeURIComponent(id)}`);
    },
    getImpact(targetId, proposedChanges = []) {
      return request("/impact", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target_id: targetId, proposed_changes: proposedChanges, include_report_usage: true }) });
    },
    compareSnapshots(before, after) {
      return request("/compare", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ before, after }) });
    },
  };
}

export const brainTransport = createBrainTransport();
