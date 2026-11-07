import assert from "node:assert/strict";
import test from "node:test";
import { countRows, groupMembers, groupSummary, hasComparableSources, mergeCandidates, propertyLabel } from "../src/commonality.js";
import { createBrainTransport } from "../src/transport.js";

const sources = [
  { ref: "m1", id: "model:a", name: "Alpha", domain: "model" },
  { ref: "m2", id: "model:b", name: "Beta", domain: "model" },
  { ref: "m3", id: "model:c", name: "Gamma", domain: "model" },
  { ref: "r1", id: "report:x", name: "Sales report", domain: "report" },
];

test("count rows keep model types first and drop empty types", () => {
  const rows = countRows({ VISUAL: { unique: 2 }, MEASURE: { identical: 1, differs: 2, renamed: 1, unique: 3 }, ROLE: {} });
  assert.deepEqual(rows.map((row) => row.type), ["MEASURE", "VISUAL"]);
  assert.equal(rows[0].total, 7);
  assert.equal(rows[1].identical, 0);
});

test("summaries name the sources and the properties that differ", () => {
  assert.equal(groupSummary({ bucket: "identical", in: ["m1", "m2", "m3"], of: 3 }, sources), "Identical in 3 of 3: Alpha, Beta, Gamma");
  assert.equal(groupSummary({ bucket: "differs", in: ["m1", "m2", "m3"], of: 3, differs: ["expression", "format_string"], variants: 3 }, sources),
    "Differs in 3 of 3: expression, format (3 variants)");
  assert.equal(groupSummary({ bucket: "unique", in: ["m1"], of: 3 }, sources), "Only in Alpha");
  assert.equal(groupSummary({ bucket: "renamed", name: "Order Count", in: ["m1", "m2", "m3"], names: { m1: "Order Count", m2: "Order Count", m3: "Number of Orders" } }, sources),
    "Same logic under 2 names: Order Count (Alpha, Beta) · Number of Orders (Gamma)");
  assert.equal(propertyLabel("summarize_by"), "summarize by");
});

test("members and merge candidates", () => {
  const group = { domain: "model", name: "Margin", in: ["m1", "m3"], objects: { m1: "model:a/m", m3: "model:c/m" } };
  assert.deepEqual(groupMembers(group, sources), [
    { ref: "m1", source: "Alpha", name: "Margin", objectId: "model:a/m" },
    { ref: "m3", source: "Gamma", name: "Margin", objectId: "model:c/m" },
  ]);
  assert.deepEqual(mergeCandidates(group, sources), ["model:a", "model:c"]);
  assert.deepEqual(mergeCandidates({ ...group, in: ["m1"] }, sources), []);
  assert.deepEqual(mergeCandidates({ domain: "report", in: ["r1", "r1"] }, sources), []);
});

test("the panel shows with two models or two reports", () => {
  assert.equal(hasComparableSources({ models: 1, reports: 1 }), false);
  assert.equal(hasComparableSources({ models: 2 }), true);
  assert.equal(hasComparableSources({ reports: 2 }), true);
});

test("transport sends the commonality filters", async () => {
  const calls = [];
  const transport = createBrainTransport({ baseUrl: "/api", fetcher: async (url) => { calls.push(url); return { ok: true, json: async () => ({}) }; } });
  await transport.getCommonality({ type: "MEASURE", bucket: "differs", scope: "m1,m2", limit: 20, offset: 40 });
  assert.equal(calls[0], "/api/commonality?limit=20&offset=40&type=MEASURE&scope=m1%2Cm2&bucket=differs");
  await transport.getCommonality({ groupId: "measure:abc" });
  assert.equal(calls[1], "/api/commonality?limit=50&offset=0&group_id=measure%3Aabc");
});
