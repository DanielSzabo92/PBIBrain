import { formatObjectRef } from "../presentation.js";

export const GUARD_PHRASES = {
  PBIR_SCHEMA_UNSUPPORTED: "Unsupported report schema",
  PBIR_REQUIRED_ARTIFACT_MISSING: "Required report file missing",
  PBIR_PAGE_COVERAGE_MISMATCH: "Report page mismatch",
  PBIR_ACTIVE_PAGE_UNRESOLVED: "Active page not found",
  PBIR_PAGE_ID_PATH_MISMATCH: "Page ID path mismatch",
  PBIR_UNSUPPORTED_ARTIFACT: "Unsupported report item",
  PBIR_DYNAMIC_CONTEXT_UNSUPPORTED: "Dynamic report feature not supported",
  SCANNER_COVERAGE_UNKNOWN: "Scanner coverage unknown: metadata incomplete for this source",
  APPROVAL_REQUIRED: "Ready for your decision",
  ELIGIBLE_FOR_PROMOTION: "Eligible for promotion",
  POST_PROMOTION_VERIFIED: "Changes applied and verified",
  PREFLIGHT: "Proposal awaiting your decision",
  REQUIRED_RUNTIME_NOT_VERIFIED: "Required model tests incomplete",
  MANDATORY_IMPACT_INCOMPLETE: "Impact coverage incomplete",
  SECURITY_VIOLATION: "Security violation",
  REFERENCE_CHANGED: "Reference changed",
  PASSED: "Passed",
  FAILED: "Failed",
  NOT_RUN: "Not run",
  CONTRACT: "Contract",
  ALLOW: "Allowed",
  BLOCK: "Blocked",
  HIGH_RISK_PROMOTION: "High risk promotion",
  UNEXPECTED_BEHAVIOR: "Behavior differences disclosed",
  BREAKS_DEPENDENTS: "Breaks dependent objects",
  PROMOTE: "Promotion",
  REJECTED: "Rejected",
  ACCEPTED: "Accepted",
  CANCELLED: "Cancelled",
  PROMOTING: "Promoting",
  PROMOTED: "Promoted",
  PROMOTION_RECOVERY_REQUIRED: "Promotion recovery required",
  CANDIDATE_READY: "candidate ready",
};

export const explain = (value) => {
  if (!value) return "Not run";
  const str = String(value).trim();
  const upper = str.toUpperCase();
  if (GUARD_PHRASES[upper]) return GUARD_PHRASES[upper];

  const pbirMatch = str.match(/^pbir[ _]schema[ _]unsupported(?::\s*(.*))?$/i);
  if (pbirMatch) {
    const reportPath = pbirMatch[1];
    if (reportPath) {
      const reportName = reportPath.replace(/^[/\\]+|[/\\]+$/g, "").split(/[/\\]/)[0] || reportPath;
      return `Unsupported report schema in ${reportName}`;
    }
    return "Unsupported report schema";
  }

  if (str.startsWith("relationship-")) {
    const clean = str.slice("relationship-".length).replaceAll(/[-_]/g, " ");
    return `Relationship (${clean.charAt(0).toUpperCase() + clean.slice(1).toLowerCase()})`;
  }

  const cleaned = str.replaceAll("_", " ");
  const isAllCaps = str === upper && /[A-Z]/.test(str);
  if (isAllCaps) {
    return cleaned.charAt(0).toUpperCase() + cleaned.slice(1).toLowerCase();
  }
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
};

export const formatGuardObjectName = (id, names) => {
  if (!id) return "Resolved target";
  const raw = names?.get(id) || id;
  if (typeof raw === "string") {
    if (raw.startsWith("relationship-")) {
      return formatObjectRef(raw);
    }
    return formatObjectRef(raw);
  }
  return String(raw);
};

export const valueText = (value, names) => {
  if (value == null) return "Blank";
  if (typeof value === "string") {
    return names?.get(value) || formatGuardObjectName(value, names);
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
};

export const blockerLabel = (item) => {
  if (item?.code === "SECURITY_VIOLATION" && item?.status === "NOT_RUN") {
    return "Sandbox verification missing";
  }
  return (
    {
      REQUIRED_RUNTIME_NOT_VERIFIED: "Required model tests incomplete",
      MANDATORY_IMPACT_INCOMPLETE: "Impact coverage incomplete",
      SECURITY_VIOLATION: "Security violation detected",
    }[item?.code] || explain(item?.code)
  );
};

export const propertyLabel = (value) =>
  ({
    from_column_id: "Source column",
    to_column_id: "Target column",
    active: "Active relationship",
    cross_filter_direction: "Filter direction",
    from_cardinality: "Source cardinality",
    to_cardinality: "Target cardinality",
    security_filter_behavior: "Security filter direction",
  }[value] || explain(value));

export const getVerdictMeta = ({ operation = {}, canApprove = false }) => {
  const rejected = operation.user_decision === "REJECTED" || operation.state === "REJECTED";
  if (rejected) {
    return {
      heading: "Changes rejected",
      tone: "bad",
      label: "Rejected",
      rejected: true,
    };
  }
  if (operation.state === "POST_PROMOTION_VERIFIED") {
    return {
      heading: "Changes applied and verified",
      tone: "ok",
      label: "Verified and applied",
      rejected: false,
    };
  }
  if (canApprove) {
    return {
      heading: "Ready for your decision",
      tone: "ok",
      label: "Ready to accept",
      rejected: false,
    };
  }
  if (operation.state === "PREFLIGHT") {
    return {
      heading: "Proposal awaiting your decision",
      tone: "proposal",
      label: "Proposal awaiting decision",
      rejected: false,
    };
  }
  return {
    heading: "Checks incomplete",
    tone: "warn",
    label: "Checks incomplete",
    rejected: false,
  };
};

export const getInitialOperationId = () => {
  try {
    const search = new URLSearchParams(globalThis.location?.search || "");
    const fromSearch = search.get("op") || search.get("operation") || search.get("id");
    if (fromSearch) return fromSearch;
    const hash = new URLSearchParams(globalThis.location?.hash?.slice(1) || "");
    return hash.get("op") || hash.get("operation") || "";
  } catch {
    return "";
  }
};
