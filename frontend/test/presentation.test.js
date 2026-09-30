import assert from "node:assert/strict";
import test from "node:test";
import { readableText, publicProperties, scopeChoices, objectName } from "../src/presentation.js";
import { PALETTES, normalizeColors } from "../src/graphPresentation.js";

test("source visual identifiers use the visual type while explicit titles survive", () => {
  const visual = { type: "VISUAL", name: "g7h8i9j0k1l2m3n4o5p6", source_id: "g7h8i9j0k1l2m3n4o5p6", properties: { visual_type: "pivotTable" } };
  assert.equal(objectName(visual), "Pivot Table");
  assert.equal(objectName({ ...visual, properties: { ...visual.properties, title: "Account breakdown" } }), "Account breakdown");
  assert.equal(objectName({ ...visual, name: "Revenue breakdown" }), "Revenue breakdown");
});

test("nested and serialized evidence becomes readable without exposing internal references", () => {
  const evidence = { evidence: ["Description: Total invoiced sales.", { reason: "Uses model:finance/table:sales/measure:net" }], target: "model:finance", extractor: "name_interpretation" };
  assert.equal(readableText(JSON.stringify(evidence)), "Description: Total invoiced sales. · Uses Referenced object");
  assert.equal(readableText({ target_id: "model:finance", source_hash: "abc", ast: {} }), "");
  assert.equal(readableText("[Net Sales] * 2"), "[Net Sales] * 2");
  assert.equal(readableText(0), "0");
  assert.equal(objectName({ id: "model:finance" }), "Unnamed object");
  assert.deepEqual(publicProperties({ properties: { table_id: "table:1", data_type: "Double", is_hidden: false, raw_source: { id: "secret" } } }), [["Data type", "Double"], ["Hidden", "No"]]);
  assert.deepEqual(scopeChoices({ model_ids: ["model:finance"] }, "model"), [{ id: "model:finance", name: "Model 1" }]);
});

test("palettes are diverse defaults while explicit custom colors and group inheritance survive", () => {
  assert.deepEqual(normalizeColors().types, PALETTES[0].types);
  for (const palette of PALETTES) {
    assert.equal(new Set(Object.values(palette.types)).size, 6);
    assert.deepEqual(normalizeColors(palette), { groups: palette.groups, types: palette.types });
  }
  assert.deepEqual(normalizeColors({ groups: { model: "#123456" }, types: {} }).types, {});
});
