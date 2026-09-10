const API_ROOT = "/api";

function apiError(response, body) {
  const detail = typeof body === "string" ? body : body?.detail || body?.message || body?.error;
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

function bootstrapSnapshot() {
  return globalThis.__POWER_BI_BRAIN__ || null;
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
    async getSnapshot() {
      const bootstrapped = bootstrapSnapshot();
      if (bootstrapped) return bootstrapped;
      return request("/brain");
    },
    async review(action, payload) {
      return request("/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...payload }),
      });
    },
    getOverview() {
      return request("/overview");
    },
    getConfig() {
      return request("/config");
    },
    saveConfig(config) {
      return request("/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
    },
    scan() {
      return request("/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
    },
    search({ query = "", modelId = "", reportId = "", limit = 50, offset = 0 } = {}) {
      const params = new URLSearchParams({ q: query, limit: String(limit), offset: String(offset) });
      if (modelId) params.set("model_id", modelId);
      if (reportId) params.set("report_id", reportId);
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
    getObject(id) {
      return request(`/objects/${encodeURIComponent(id)}`);
    },
  };
}

export const brainTransport = createBrainTransport();

export function normalizeSnapshot(value) {
  const source = value || {};
  const review = source.review && typeof source.review === "object" ? source.review : {};
  const candidates = source.semantic_candidates || source.semanticCandidates || [];
  return {
    nodes: Array.isArray(source.nodes) ? source.nodes : [],
    edges: Array.isArray(source.edges) ? source.edges : [],
    semantic_candidates: Array.isArray(candidates) ? candidates : [],
    conflicts: Array.isArray(source.conflicts) ? source.conflicts : [],
    observations: Array.isArray(source.observations) ? source.observations : [],
    diagnostics: Array.isArray(source.diagnostics) ? source.diagnostics : [],
    scan: source.scan || source.status || {},
    validation: source.validation || {},
    overrides: Array.isArray(source.overrides) ? source.overrides : [],
    stale_overrides: Array.isArray(source.stale_overrides) ? source.stale_overrides : Array.isArray(source.staleOverrides) ? source.staleOverrides : Array.isArray(review.stale_overrides) ? review.stale_overrides : Array.isArray(review.staleOverrides) ? review.staleOverrides : [],
    review_items: Array.isArray(source.review_items) ? source.review_items : Array.isArray(source.reviewItems) ? source.reviewItems : Array.isArray(source.review_queue) ? source.review_queue : Array.isArray(source.reviewQueue) ? source.reviewQueue : Array.isArray(review.items) ? review.items : Array.isArray(review.review_items) ? review.review_items : [],
    graph: source.graph || source.scoped_graph || source.scopedGraph || null,
  };
}
