// HTTP read client for /api/devcenter (technical design sections 14.1 and 14.4).
// Each read takes an optional {signal} from an AbortController. A non-2xx reply rejects with DevCenterError.
import { DevCenterError, normalizeError } from "./errors.js";

export const DEFAULT_PAGE_SIZE = 200;

function segment(value, name) {
  if (value === undefined || value === null || value === "") {
    throw new DevCenterError({ code: "invalid_payload", message: `The read needs a ${name}.`, details: { field: name }, source: "http" });
  }
  return encodeURIComponent(String(value));
}

function flag(value) {
  if (value === true) return "true";
  if (value === false) return "false";
  return value;
}

// Make a query string. Undefined, null, and empty values are not sent.
export function buildQuery(params = {}) {
  const query = new URLSearchParams();
  for (const [name, raw] of Object.entries(params)) {
    const values = Array.isArray(raw) ? raw : [raw];
    for (const value of values) {
      if (value === undefined || value === null || value === "") continue;
      query.append(name, String(flag(value)));
    }
  }
  const text = query.toString();
  return text ? `?${text}` : "";
}

// sort is a field ("state", "name", "type", "table") and direction is "asc" or "desc".
function sortParam(sort, direction) {
  if (!sort) return undefined;
  return direction ? `${sort}:${direction}` : sort;
}

function page({ limit, offset }, defaultLimit) {
  return { limit: limit ?? defaultLimit, offset: offset ?? 0 };
}

export function createDevCenterHttp({ baseUrl = "/api/devcenter", fetcher = globalThis.fetch?.bind(globalThis) } = {}) {
  const root = baseUrl.replace(/\/+$/, "");

  async function request(path, { method = "GET", body, signal } = {}) {
    const options = { method, headers: { Accept: "application/json" }, signal };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetcher(`${root}${path}`, options);
    } catch (error) {
      throw normalizeError(error, { source: "http" });
    }
    let value = null;
    try {
      value = await response.json();
    } catch {
      value = null;
    }
    if (!response.ok) {
      const error = normalizeError(value, { source: "http", status: response.status });
      if (!value || (error.code === "unknown" && !error.message)) {
        error.message = `The local API replied with HTTP ${response.status}.`;
      }
      throw error;
    }
    if (value === null || typeof value !== "object") {
      throw new DevCenterError({ code: "unknown", message: "The local API reply is not JSON.", source: "http", status: response.status });
    }
    return value;
  }

  const get = (path, signal) => request(path, { signal });
  const post = (path, body, signal) => request(path, { method: "POST", body, signal });

  return {
    getSessions: ({ signal } = {}) => get("/sessions", signal),
    getSession: ({ signal } = {}) => get("/session", signal),
    getCompareRows: (
      { type, table, folder, state, source, page: reportPage, changed, marks, q, sort, direction, limit, offset } = {},
      { signal } = {},
    ) =>
      get(
        `/compare-rows${buildQuery({
          type, table, folder, state, source, page: reportPage, changed, marks, q,
          sort: sortParam(sort, direction), ...page({ limit, offset }, DEFAULT_PAGE_SIZE),
        })}`,
        signal,
      ),
    getRowDiff: async (row, source, { signal } = {}) => get(`/compare-rows/${segment(row, "row")}/diff${buildQuery({ source })}`, signal),
    getDisplayFolders: ({ source, objectType } = {}, { signal } = {}) =>
      get(`/display-folders${buildQuery({ source, object_type: objectType })}`, signal),
    getPlan: ({ includeProposals } = {}, { signal } = {}) => get(`/plan${buildQuery({ include_proposals: includeProposals })}`, signal),
    getImpact: (
      { target = "plan", includeProposals, direction, blocking, severity, certainty, source, objectType, q, limit, offset } = {},
      { signal } = {},
    ) =>
      get(
        `/impact${buildQuery({
          target, include_proposals: includeProposals, direction, blocking, severity, certainty, source,
          object_type: objectType, q, ...page({ limit, offset }, DEFAULT_PAGE_SIZE),
        })}`,
        signal,
      ),
    getImpactPaths: async (item, { limit, offset } = {}, { signal } = {}) =>
      get(`/impact/${segment(item, "item")}/paths${buildQuery(page({ limit, offset }, DEFAULT_PAGE_SIZE))}`, signal),
    getRemoval: async (object, { signal } = {}) => get(`/impact/removal/${segment(object, "object")}`, signal),
    getWireframe: async (report, { signal } = {}) => get(`/wireframe/${segment(report, "report")}`, signal),
    getNamingRules: ({ signal } = {}) => get("/naming-rules", signal),
    proposeName: (body = {}, { signal } = {}) => post("/name-propose", body, signal),
    validatePlan: (mode = "quick", { signal } = {}) => post("/plan-validate", { mode }, signal),
    getApplyPreview: ({ signal } = {}) => get("/apply/preview", signal),
    getApplyProgress: ({ signal } = {}) => get("/apply/progress", signal),
    getApplyLast: ({ signal } = {}) => get("/apply/last", signal),
    getLog: ({ author, action, target, proposalId, limit, offset } = {}, { signal } = {}) =>
      get(`/log${buildQuery({ author, action, target, proposal_id: proposalId, ...page({ limit, offset }, DEFAULT_PAGE_SIZE) })}`, signal),
  };
}

// The cached reads of the store. Each resource key maps to one read with its params.
// The keys are the keys of invalidation.js.
export const RESOURCE_READS = Object.freeze({
  session: (http, _params, options) => http.getSession(options),
  sessions: (http, _params, options) => http.getSessions(options),
  compareRows: (http, params, options) => http.getCompareRows(params, options),
  rowDiff: (http, { row, source }, options) => http.getRowDiff(row, source, options),
  displayFolders: (http, params, options) => http.getDisplayFolders(params, options),
  plan: (http, params, options) => http.getPlan(params, options),
  impact: (http, params, options) => http.getImpact(params, options),
  impactPaths: (http, { item, ...params }, options) => http.getImpactPaths(item, params, options),
  removal: (http, { object }, options) => http.getRemoval(object, options),
  wireframe: (http, { report }, options) => http.getWireframe(report, options),
  namingRules: (http, _params, options) => http.getNamingRules(options),
  applyPreview: (http, _params, options) => http.getApplyPreview(options),
  applyLast: (http, _params, options) => http.getApplyLast(options),
  log: (http, params, options) => http.getLog(params, options),
});
