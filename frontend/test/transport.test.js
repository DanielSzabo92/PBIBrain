import assert from "node:assert/strict";
import test from "node:test";
import { createBrainTransport } from "../src/transport.js";

function fakeFetch(body = {}) {
  const calls = [];
  return {
    calls,
    fetch: async (url, options = {}) => {
      calls.push({ url, options });
      return { ok: true, json: async () => body };
    },
  };
}

test("search scopes and paginates through the local API", async () => {
  const fake = fakeFetch({ items: [], total: 0 });
  await createBrainTransport({ baseUrl: "/api", fetcher: fake.fetch }).search({ query: "Revenue", modelId: "m/1", reportId: "r/1", limit: 25, offset: 25 });
  assert.equal(fake.calls[0].url, "/api/search?q=Revenue&limit=25&offset=25&model_id=m%2F1&report_id=r%2F1&kind=objects");
});

test("graph encodes a center and carries an explicit bounded scope", async () => {
  const fake = fakeFetch({ nodes: [], edges: [] });
  await createBrainTransport({ baseUrl: "/api", fetcher: fake.fetch }).getGraph({ centerId: "measure/Net Sales", depth: 2, limit: 100 });
  assert.equal(fake.calls[0].url, "/api/graph?depth=2&limit=100&center_id=measure%2FNet+Sales");
});

test("graph filters are sent before the server truncates the result", async () => {
  const fake = fakeFetch({ nodes: [], edges: [] });
  await createBrainTransport({ fetcher: fake.fetch }).getGraph({ query: "Net Sales", artifact: "model", objectType: "MEASURE", status: "approved", edgeType: "DEPENDS_ON", modelId: "m/1", limit: 200 });
  const params = new URL(fake.calls[0].url, "http://localhost").searchParams;
  for (const [key, value] of Object.entries({ query: "Net Sales", artifact: "model", object_type: "MEASURE", status: "approved", edge_type: "DEPENDS_ON", model_id: "m/1", limit: "200" })) assert.equal(params.get(key), value);
});

test("config save preserves the complete server contract", async () => {
  const fake = fakeFetch({ version: 1 });
  const payload = { version: 1, name: "Finance", sources: ["C:\\Finance.pbip"], database: "../data/brain.lbug", identity_map: "identity.json" };
  await createBrainTransport({ baseUrl: "/api", fetcher: fake.fetch }).saveConfig(payload);
  assert.equal(fake.calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(fake.calls[0].options.body), payload);
});

test("scan posts an explicit JSON payload for the local WSGI API", async () => {
  const fake = fakeFetch({ overview: {} });
  await createBrainTransport({ baseUrl: "/api", fetcher: fake.fetch }).scan();
  assert.equal(fake.calls[0].options.method, "POST");
  assert.equal(fake.calls[0].options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(fake.calls[0].options.body), { background: true });
});

test("scan waits for the background scan by polling its status, and reports a cancelled scan as such", async () => {
  const sequence = (answers) => {
    const calls = [];
    return { calls, fetch: async (url, options = {}) => { calls.push({ url, method: options.method || "GET" }); const body = answers.shift(); return { ok: true, status: 200, json: async () => body }; } };
  };
  const done = sequence([
    { running: true, scan: 2 },
    { running: true, phase: "Reading formulas and dependencies", last: { scan: 1, state: "done" } },
    { running: false, last: { scan: 1, state: "done" } }, // the outcome of an earlier scan is not this one's
    { running: false, last: { scan: 2, state: "done", source_count: 3 } },
    { counts: { nodes: 20 } },
  ]);
  const result = await createBrainTransport({ baseUrl: "/api", fetcher: done.fetch }).scan();
  assert.deepEqual(result, { overview: { counts: { nodes: 20 } }, source_count: 3 });
  assert.deepEqual(done.calls.map((call) => `${call.method} ${call.url}`), ["POST /api/scan", "GET /api/scan/status", "GET /api/scan/status", "GET /api/scan/status", "GET /api/overview"]);

  const cancelled = sequence([{ running: true, scan: 1 }, { running: false, last: { scan: 1, state: "cancelled" } }]);
  await assert.rejects(createBrainTransport({ baseUrl: "/api", fetcher: cancelled.fetch }).scan(), (error) => error.cancelled === true);
  const failed = sequence([{ running: true, scan: 1 }, { running: false, last: { scan: 1, state: "failed", error: "Source file is not valid JSON" } }]);
  await assert.rejects(createBrainTransport({ baseUrl: "/api", fetcher: failed.fetch }).scan(), (error) => !error.cancelled && /not valid JSON/.test(error.message));
});

test("API errors expose the backend error field", async () => {
  const transport = createBrainTransport({ baseUrl: "/api", fetcher: async () => ({ ok: false, status: 422, statusText: "Unprocessable", json: async () => ({ error: "Source path is invalid" }) }) });
  await assert.rejects(transport.scan(), /Source path is invalid/);
});

test("model summary requires an explicit encoded model scope", async () => {
  const fake = fakeFetch({ model_id: "model/Finance á", markdown: "# Model" });
  const result = await createBrainTransport({ baseUrl: "/api", fetcher: fake.fetch }).getModelSummary("model/Finance á");
  assert.equal(fake.calls[0].url, "/api/model-summary?model_id=model%2FFinance+%C3%A1");
  assert.equal(result.markdown, "# Model");
});
