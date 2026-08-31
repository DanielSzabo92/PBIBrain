const API_ROOT = "/api";

function apiError(response, body) {
  const detail = typeof body === "string" ? body : body?.detail || body?.message;
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
  return {
    async getSnapshot() {
      const bootstrapped = bootstrapSnapshot();
      if (bootstrapped) return bootstrapped;
      if (typeof fetcher !== "function") {
        throw new Error("No local Brain transport configured");
      }
      return jsonRequest(fetcher, `${baseUrl}/brain`);
    },
    async review(action, payload) {
      if (typeof fetcher !== "function") throw new Error("No local Brain transport configured");
      return jsonRequest(fetcher, `${baseUrl}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...payload }),
      });
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
