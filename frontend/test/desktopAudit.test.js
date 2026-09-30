import assert from "node:assert/strict";
import test from "node:test";
import { objectScope } from "../src/presentation.js";

test("same-name review targets retain table and model/report scope", () => {
  const nodes = [
    { id: "model:1", name: "Finance" }, { id: "report:1", name: "Sales report" },
    { id: "table:sales", name: "Sales" }, { id: "table:date", name: "Date" },
    { id: "page:1", name: "Overview", properties: { parent_id: "report:1" } },
  ];
  assert.equal(objectScope({ id: "column:1", name: "DateKey", model_id: "model:1", properties: { table_id: "table:sales" } }, nodes), "Finance / Sales");
  assert.equal(objectScope({ id: "column:2", name: "DateKey", model_id: "model:1", properties: { table_id: "table:date" } }, nodes), "Finance / Date");
  assert.equal(objectScope({ id: "visual:1", report_id: "report:1", properties: { parent_id: "page:1" } }, nodes), "Sales report / Overview");
  assert.equal(objectScope({ id: "missing", properties: { parent_id: "missing" } }, nodes), "Scope unavailable");
});
