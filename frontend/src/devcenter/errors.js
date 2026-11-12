// One error type for the Development Center data layer (UI design section 10).
// Plain JS with no React import, so that node --test can test it.

// The codes of the error shape {error: {code, message, details}} (technical design section 12).
export const SERVER_ERROR_CODES = Object.freeze([
  "not_found",
  "session_not_open",
  "stale_revision",
  "confidence_below_threshold",
  "reason_required",
  "user_choice_exists",
  "naming_rule_violation",
  "invalid_payload",
  "action_not_allowed",
  "source_changed",
]);

// Codes that only the client makes. "aborted" and "dropped" never show to the user.
export const CLIENT_ERROR_CODES = Object.freeze(["network", "unknown", "aborted", "dropped"]);


// The UI reaction for each code (UI design section 10, "Other codes").
// toast: shared.stale toast after a refetch. list: session list with a banner.
// compare_marks: Compare with the marks filter. inline: error at the control.
// region: region banner with "Try again". agent: Agent tab and Log only. none: show nothing.
const REACTIONS = Object.freeze({
  stale_revision: "toast",
  session_not_open: "list",
  source_changed: "compare_marks",
  action_not_allowed: "inline",
  invalid_payload: "inline",
  not_found: "inline",
  user_choice_exists: "inline",
  confidence_below_threshold: "agent",
  reason_required: "agent",
  naming_rule_violation: "agent",
  network: "region",
  unknown: "region",
  aborted: "none",
  dropped: "none",
});

// An accept of a proposal shows source_changed as an inline alert, not as a move to Compare.
const INLINE_SOURCE_CHANGED = new Set(["proposal_accept", "proposal_accept_all"]);

const KNOWN_CODES = new Set([...SERVER_ERROR_CODES, ...CLIENT_ERROR_CODES]);

export class DevCenterError extends Error {
  constructor({ code = "unknown", message = "", details = {}, source = "jsapi", status = null } = {}) {
    super(message);
    this.name = "DevCenterError";
    this.code = code;
    this.details = details && typeof details === "object" ? details : {};
    this.source = source;
    this.status = status;
  }
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isAbort(value) {
  return isObject(value) && (value.name === "AbortError" || value.code === 20) && !(value instanceof DevCenterError);
}

// True when the value has the new error shape {error: {code, message, details}}.
export function isErrorShape(value) {
  return isObject(value) && isObject(value.error) && typeof value.error.code === "string";
}

// True when the value has the old desktop shape {ok: false, error: "<text>"}.
export function isOldErrorShape(value) {
  return isObject(value) && value.ok === false;
}

function fromShape(shape, source, status) {
  const code = KNOWN_CODES.has(shape.code) ? shape.code : "unknown";
  const details = isObject(shape.details) ? { ...shape.details } : {};
  if (code !== shape.code) details.original_code = shape.code;
  return new DevCenterError({ code, message: String(shape.message ?? ""), details, source, status });
}

// Make one DevCenterError from each kind of failure value:
// - a DevCenterError (returned as it is),
// - the new shape {error: {code, message, details}},
// - the old shape {ok: false, error: "<text>"} (code "unknown"),
// - a thrown Error: "network" for an HTTP read (fetch failed), "unknown" for a JS API call,
// - an Error from the test shim that carries the reply (the code of the reply),
// - an AbortError (code "aborted").
// An HTTP status of 500 or more with no error shape gives "unknown".
export function normalizeError(value, { source = "jsapi", status = null } = {}) {
  if (value instanceof DevCenterError) return value;
  if (isErrorShape(value)) return fromShape(value.error, source, status);
  if (isOldErrorShape(value)) {
    const text = typeof value.error === "string" ? value.error : value.error?.message ?? "";
    return new DevCenterError({ code: "unknown", message: String(text), details: { shape: "old" }, source, status });
  }
  if (isAbort(value)) {
    return new DevCenterError({ code: "aborted", message: value.message || "The read was stopped.", source, status });
  }
  if (value instanceof Error) {
    // The test shim throws an Error for a non-2xx reply and puts the body in error.reply.
    if (isErrorShape(value.reply)) return fromShape(value.reply.error, source, status);
    if (isOldErrorShape(value.reply)) return normalizeError(value.reply, { source, status });
    // A failed fetch means that the local API did not answer. A JS API call has no network: a thrown
    // error there is a fault in the host or the bridge, so it is unknown.
    if (source === "http") return new DevCenterError({ code: "network", message: value.message, source: "network", status });
    return new DevCenterError({ code: "unknown", message: value.message, details: { thrown: value.name || "Error" }, source, status });
  }
  if (typeof value === "string") return new DevCenterError({ code: "unknown", message: value, source, status });
  return new DevCenterError({ code: "unknown", message: "", details: {}, source, status });
}

// The UI reaction for an error. method is the JS API method that failed, if any.
export function errorReaction(error, method = null) {
  const code = error?.code ?? "unknown";
  if (code === "source_changed" && INLINE_SOURCE_CHANGED.has(method)) return "inline";
  if (error?.source === "http" && Number(error?.status) >= 500 && REACTIONS[code] === "inline") return "region";
  return REACTIONS[code] ?? "region";
}
