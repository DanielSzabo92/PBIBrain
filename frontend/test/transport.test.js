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
  assert.equal(fake.calls[0].url, "/api/search?q=Revenue&limit=25&offset=25&model_id=m%2F1&report_id=r%2F1");
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
  assert.equal(fake.calls[0].options.body, "{}");
});

test("API errors expose the backend error field", async () => {
  const transport = createBrainTransport({ baseUrl: "/api", fetcher: async () => ({ ok: false, status: 422, statusText: "Unprocessable", json: async () => ({ error: "Source path is invalid" }) }) });
  await assert.rejects(transport.scan(), /Source path is invalid/);
});
