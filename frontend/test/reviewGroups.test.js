import test from "node:test";
import assert from "node:assert/strict";
import { groupReviewItems } from "../src/reviewGroups.js";

const nodes = { m1: { type: "MEASURE", name: "Sales" }, m2: { type: "MEASURE", name: "Sales" }, c1: { type: "COLUMN", name: "Key" } };
const targetOf = (item) => nodes[item.target_id];

test("suggestions group by rule, basis and object type, largest first", () => {
  const items = [
    { target_id: "c1", assertion_type: "BUSINESS_CONCEPT", confidence: 0.3, item: { properties: { candidate_source: "object_name" } } },
    { target_id: "m1", assertion_type: "ALIAS", source: "description", confidence: 0.97 },
    { target_id: "m2", assertion_type: "ALIAS", source: "description", confidence: 0.9 },
  ];
  const groups = groupReviewItems(items, targetOf);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].title, "Other name from the description");
  assert.equal(groups[0].scope, "measures");
  assert.equal(groups[0].items.length, 2);
  assert.equal(groups[0].names, 1);
  assert.equal(groups[0].low, 0.9);
  assert.equal(groups[0].high, 0.97);
  assert.equal(groups[1].title, "Meaning from the name");
});

test("conflicts come first and cannot be decided in bulk", () => {
  const groups = groupReviewItems([
    { target_id: "m1", assertion_type: "ALIAS", source: "description", issue: "candidate" },
    { target_id: "m1", issue: "conflict" },
  ], targetOf);
  assert.equal(groups[0].title, "Conflicts");
  assert.equal(groups[0].bulk, false);
  assert.equal(groups[1].bulk, true);
});
