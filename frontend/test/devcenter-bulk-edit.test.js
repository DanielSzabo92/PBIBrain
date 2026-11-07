// Unit tests of the bulk edit model (issue #12, operation source "Edit target").
import assert from "node:assert/strict";
import test from "node:test";
import { changeRows, editOperation, editRequest, editScope, propertyValue, referenceRows, skippedCounts } from "../src/devcenter/components/bulkEditModel.js";
import { INVALIDATES } from "../src/devcenter/invalidation.js";
import { createDevCenterHttp } from "../src/devcenter/httpClient.js";

test("the scope is the selected row keys, or the compare filters without sort and page", () => {
  assert.deepEqual(editScope({ selectedKeys: new Set(["measure:Sales/A", "measure:Sales/B"]) }), { row_keys: ["measure:Sales/A", "measure:Sales/B"] });
  assert.deepEqual(editScope({ allMatching: true, queryParams: { type: "measure", q: "", state: "not_same", sort: "name:asc", proposal: "true" } }),
                   { filter: { type: "measure", state: "not_same" } });
});

test("each operation of the form, and an incomplete form gives no request", () => {
  assert.equal(editOperation({ kind: "rename", find: "" }), null);
  assert.deepEqual(editOperation({ kind: "rename", find: "^Total (.*)$", replace: "$1 Total", regex: true }),
                   { kind: "rename", find: "^Total (.*)$", replace: "$1 Total", regex: true, match_case: true });
  assert.deepEqual(editOperation({ kind: "set_property", property: "is_hidden", value: "true" }), { kind: "set_property", property: "is_hidden", value: true });
  assert.deepEqual(editOperation({ kind: "set_property", property: "description", value: "  " }), { kind: "set_property", property: "description", value: null });
  assert.equal(editOperation({ kind: "set_property", property: "expression" }), null);
  assert.deepEqual(editOperation({ kind: "move_folder", folder: " KPI " }), { kind: "move_folder", folder: "KPI" });
  assert.deepEqual(editOperation({ kind: "delete", policy: "cascade" }), { kind: "delete", policy: "cascade" });
  assert.deepEqual(editRequest({ kind: "apply_naming_rules" }, { row_keys: ["x"] }), { operation: { kind: "apply_naming_rules" }, scope: { row_keys: ["x"] } });
  assert.equal(propertyValue("summarize_by", "sum"), "sum");
});

test("the preview rows show each change and each rewritten reference", () => {
  const preview = {
    changes: [
      { row_key: "measure:Sales/Total Sales", object_type: "measure", table: "Sales", name: "Total Sales", change: { kind: "rename", old_name: "Total Sales", new_name: "Sales Total" } },
      { row_key: "column:Sales/Key", object_type: "column", table: "Sales", name: "Key", change: { kind: "set_property", property: "is_hidden", old: false, new: true } },
    ],
    skipped: [{ row_key: "a", reason: "no_match" }, { row_key: "b", reason: "no_match" }],
    references: [
      { kind: "expression", domain: "model", row_key: "measure:Sales/Margin", table: "Sales", name: "Margin", property: "expression",
        old_text: "[Total Sales]", new_text: "[Sales Total]" },
      { kind: "binding", domain: "report", row_key: "visual:p/v", table: null, name: "v", pointer: "/x",
        old: { entity: "Sales", property: "Total Sales" }, new: { entity: "Sales", property: "Sales Total" } },
    ],
  };
  assert.deepEqual(changeRows(preview).map((row) => [row.object, row.before, row.after]),
                   [["Sales[Total Sales]", "Total Sales", "Sales Total"], ["Sales[Key]", "false", "true"]]);
  assert.deepEqual(referenceRows(preview).map((row) => [row.kind, row.before, row.after]),
                   [["expression", "[Total Sales]", "[Sales Total]"], ["binding", "Sales[Total Sales]", "Sales[Sales Total]"]]);
  assert.deepEqual(skippedCounts(preview), { no_match: 2 });
});

test("the preview is a POST read and the apply invalidates the choice reads", async () => {
  const calls = [];
  const http = createDevCenterHttp({ fetcher: async (url, options) => { calls.push({ url, options }); return { ok: true, status: 200, json: async () => ({}) }; } });
  await http.previewEdit({ operation: { kind: "apply_naming_rules" }, scope: { filter: {} } });
  assert.equal(calls[0].url, "/api/devcenter/edit-preview");
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(INVALIDATES.target_edit_apply, INVALIDATES.merge_choice_bulk_set);
});
