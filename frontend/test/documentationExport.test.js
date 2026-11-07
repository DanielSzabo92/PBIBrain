import test from "node:test";
import assert from "node:assert/strict";
import { DOC_SECTIONS, exportBlocker, exportRequest, formatSize, replyBytes } from "../src/documentationExport.js";
import { createBrainTransport } from "../src/transport.js";

const overview = { model_objects: [{ id: "m1" }, { id: "m2" }], report_objects: [{ id: "r1" }] };
const everySection = new Set(DOC_SECTIONS.map(([key]) => key));

test("everything chosen is sent as null, so a later scan's new objects are included", () => {
  const request = exportRequest({ format: "pdf", models: new Set(["m1", "m2"]), reports: new Set(["r1"]), sections: everySection }, overview);
  assert.deepEqual(request, { format: "pdf", modelIds: null, reportIds: null, sections: null });
});

test("a partial scope sends the exact ids and sections in a stable order", () => {
  const request = exportRequest({ format: "markdown", models: new Set(["m2"]), reports: new Set(), sections: new Set(["lineage", "overview"]) }, overview);
  assert.deepEqual(request, { format: "markdown", modelIds: ["m2"], reportIds: [], sections: ["overview", "lineage"] });
});

test("the export is blocked with a reason when nothing is chosen", () => {
  assert.equal(exportBlocker({ models: new Set(), reports: new Set(), sections: everySection }), "Choose at least one model or report.");
  assert.equal(exportBlocker({ models: new Set(["m1"]), reports: new Set(), sections: new Set() }), "Choose at least one section.");
  assert.equal(exportBlocker({ models: new Set(), reports: new Set(["r1"]), sections: everySection }), "");
});

test("reply bytes decode from base64 exactly", () => {
  const bytes = replyBytes({ content_base64: Buffer.from([37, 80, 68, 70, 0, 255]).toString("base64") });
  assert.deepEqual([...bytes], [37, 80, 68, 70, 0, 255]);
  assert.equal(formatSize(512), "512 B");
  assert.equal(formatSize(2048), "2.0 KB");
});

test("transport posts the documentation scope as JSON", async () => {
  const calls = [];
  const fetcher = async (url, options) => { calls.push({ url, options }); return { ok: true, json: async () => ({ filename: "x.pdf" }) }; };
  const reply = await createBrainTransport({ baseUrl: "/api", fetcher }).exportDocumentation({ format: "markdown", modelIds: ["m1"], reportIds: null, sections: ["overview"] });
  assert.equal(reply.filename, "x.pdf");
  assert.equal(calls[0].url, "/api/documentation-export");
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].options.body), { format: "markdown", model_ids: ["m1"], report_ids: null, sections: ["overview"] });
});
