import { t } from "../copy.js";

// The pure part of the bulk edit dialog (issue #12, operation source "Edit target"):
// the request of POST edit-preview and target_edit_apply, and the rows of the preview.

export const EDIT_KINDS = ["rename", "set_property", "move_folder", "apply_naming_rules", "delete"];

// The properties that a bulk edit can set, with the value kind ("text", "bool", or a list of values).
export const EDIT_PROPERTIES = {
  format_string: "text",
  display_folder: "text",
  description: "text",
  data_category: "text",
  is_hidden: "bool",
  is_key: "bool",
  summarize_by: ["default", "none", "sum", "min", "max", "count", "average", "distinctcount"],
};

// The compare filters that select rows. Sort, page, and proposal filters are not part of a scope.
const SCOPE_FILTERS = ["q", "state", "type", "table", "folder", "source", "changed", "marks"];

export function editScope({ allMatching, queryParams = {}, selectedKeys = [] }) {
  if (allMatching) {
    const filter = {};
    for (const key of SCOPE_FILTERS) {
      if (queryParams[key] !== undefined && queryParams[key] !== null && queryParams[key] !== "") filter[key] = String(queryParams[key]);
    }
    return { filter };
  }
  return { row_keys: Array.from(selectedKeys) };
}

export function propertyValue(property, text) {
  const kind = EDIT_PROPERTIES[property];
  if (kind === "bool") return text === true || text === "true";
  if (Array.isArray(kind)) return text;
  const value = String(text ?? "").trim();
  return value === "" ? null : value;
}

// The operation of the form state, or null when the form is not complete.
export function editOperation(form) {
  switch (form.kind) {
    case "rename":
      if (!form.find) return null;
      return { kind: "rename", find: form.find, replace: form.replace ?? "", regex: Boolean(form.regex), match_case: form.matchCase !== false };
    case "set_property":
      if (!EDIT_PROPERTIES[form.property]) return null;
      return { kind: "set_property", property: form.property, value: propertyValue(form.property, form.value) };
    case "move_folder": {
      const folder = String(form.folder ?? "").trim();
      return { kind: "move_folder", folder: folder === "" ? null : folder };
    }
    case "apply_naming_rules":
      return { kind: "apply_naming_rules" };
    case "delete":
      return { kind: "delete", policy: form.policy === "cascade" ? "cascade" : "block" };
    default:
      return null;
  }
}

export function editRequest(form, scope) {
  const operation = editOperation(form);
  return operation ? { operation, scope } : null;
}

function show(value) {
  if (value === null || value === undefined || value === "") return t("edit.value.none");
  return String(value);
}

// One line for each changed row: the object and its old and new value.
export function changeRows(preview) {
  return (preview?.changes ?? []).map((item) => {
    const change = item.change || {};
    const object = item.table ? `${item.table}[${item.name}]` : item.name;
    if (change.kind === "rename" || change.kind === "apply_naming_rules") {
      const folder = change.new_folder !== undefined ? ` ${t("edit.value.folder", { folder: show(change.new_folder) })}` : "";
      return { key: item.row_key, object, type: item.object_type, before: change.old_name, after: `${change.new_name}${folder}` };
    }
    if (change.kind === "set_property") {
      return { key: item.row_key, object, type: item.object_type, before: show(change.old), after: show(change.new), property: change.property };
    }
    return { key: item.row_key, object, type: item.object_type, before: object, after: t("edit.value.removed") };
  });
}

// One line for each rewritten reference: DAX text or a report field binding.
export function referenceRows(preview) {
  return (preview?.references ?? []).map((item, index) => {
    const object = item.table ? `${item.table}[${item.name}]` : item.name;
    if (item.kind === "binding") {
      return {
        key: `${item.row_key}-${item.pointer}-${index}`, kind: "binding", domain: item.domain, object,
        before: `${item.old?.entity}[${item.old?.property}]`, after: `${item.new?.entity}[${item.new?.property}]`,
      };
    }
    return { key: `${item.row_key}-${item.property}-${index}`, kind: "expression", domain: item.domain, object, property: item.property,
             before: item.old_text, after: item.new_text };
  });
}

export function skippedCounts(preview) {
  const counts = {};
  for (const item of preview?.skipped ?? []) counts[item.reason] = (counts[item.reason] || 0) + 1;
  return counts;
}
