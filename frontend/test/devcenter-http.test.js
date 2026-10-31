// Unit tests of the Development Center HTTP read client and the error normalization (UI design step U2).
import assert from "node:assert/strict";
import test from "node:test";
import { DevCenterError, errorReaction, normalizeError } from "../src/devcenter/errors.js";
import { buildQuery, createDevCenterHttp, RESOURCE_READS } from "../src/devcenter/httpClient.js";
import { RESOURCE_KEYS } from "../src/devcenter/invalidation.js";

function fakeFetch(reply = { status: 200, body: { revision: 1 } }) {
  const calls = [];
  const fetcher = async (url, options = {}) => {
    calls.push({ url, options });
    if (reply instanceof Error) throw reply;
    const { status = 200, body } = typeof reply === "function" ? reply(url, options) : reply;
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => {
        if (body === undefined) throw new SyntaxError("No JSON");
        return body;
      },
    };
  };
  return { calls, fetcher };
}

const urls = (fake) => fake.calls.map((call) => call.url);

test("the compare rows read sends each filter, the sort, and the page", async () => {
  const fake = fakeFetch();
  const http = createDevCenterHttp({ fetcher: fake.fetcher });
  await http.getCompareRows({
    type: "measure", table: "Sales Fact", folder: "KPI/Margin", state: "different", source: "src-a", page: "Overview",
    changed: true, marks: false, q: "net margin", sort: "name", direction: "desc", limit: 50, offset: 100,
  });
  assert.equal(
    fake.calls[0].url,
    "/api/devcenter/compare-rows?type=measure&table=Sales+Fact&folder=KPI%2FMargin&state=different&source=src-a&page=Overview"
      + "&changed=true&marks=false&q=net+margin&sort=name%3Adesc&limit=50&offset=100",
  );
  assert.equal(fake.calls[0].options.method, "GET");
});

test("empty filters are not sent and the default page is 200 rows from offset 0", async () => {
  const fake = fakeFetch();
  const http = createDevCenterHttp({ baseUrl: "/api/devcenter/", fetcher: fake.fetcher });
  await http.getCompareRows({ type: "", table: null, folder: undefined });
  await http.getCompareRows();
  await http.getImpact();
  await http.getLog({ author: "agent", proposalId: "p-1" });
  assert.deepEqual(urls(fake), [
    "/api/devcenter/compare-rows?limit=200&offset=0",
    "/api/devcenter/compare-rows?limit=200&offset=0",
    "/api/devcenter/impact?target=plan&limit=200&offset=0",
    "/api/devcenter/log?author=agent&proposal_id=p-1&limit=200&offset=0",
  ]);
});

test("paging moves the offset and keeps the filters", async () => {
  const fake = fakeFetch();
  const http = createDevCenterHttp({ fetcher: fake.fetcher });
  for (const offset of [0, 200, 400]) await http.getCompareRows({ state: "missing", offset });
  assert.deepEqual(urls(fake), [
    "/api/devcenter/compare-rows?state=missing&limit=200&offset=0",
    "/api/devcenter/compare-rows?state=missing&limit=200&offset=200",
    "/api/devcenter/compare-rows?state=missing&limit=200&offset=400",
  ]);
});

test("each read has its path, and path parts are encoded", async () => {
  const fake = fakeFetch();
  const http = createDevCenterHttp({ fetcher: fake.fetcher });
  await http.getSessions();
  await http.getSession();
  await http.getRowDiff("measure/Net Margin", "src-a");
  await http.getDisplayFolders({ source: "src-a", objectType: "measure" });
  await http.getPlan({ includeProposals: "ready" });
  await http.getImpact({ target: "row-1", includeProposals: false, blocking: true, objectType: "measure", q: "margin", limit: 500 });
  await http.getImpactPaths("item/1", { offset: 20 });
  await http.getRemoval("measure/Gross Profit");
  await http.getWireframe("Sales report");
  await http.getNamingRules();
  await http.getApplyPreview();
  await http.getApplyProgress();
  await http.getApplyLast();
  assert.deepEqual(urls(fake), [
    "/api/devcenter/sessions",
    "/api/devcenter/session",
    "/api/devcenter/compare-rows/measure%2FNet%20Margin/diff?source=src-a",
    "/api/devcenter/display-folders?source=src-a&object_type=measure",
    "/api/devcenter/plan?include_proposals=ready",
    "/api/devcenter/impact?target=row-1&include_proposals=false&blocking=true&object_type=measure&q=margin&limit=500&offset=0",
    "/api/devcenter/impact/item%2F1/paths?limit=200&offset=20",
    "/api/devcenter/impact/removal/measure%2FGross%20Profit",
    "/api/devcenter/wireframe/Sales%20report",
    "/api/devcenter/naming-rules",
    "/api/devcenter/apply/preview",
    "/api/devcenter/apply/progress",
    "/api/devcenter/apply/last",
  ]);
});

test("the calculation reads post a JSON body", async () => {
  const fake = fakeFetch();
  const http = createDevCenterHttp({ fetcher: fake.fetcher });
  await http.proposeName({ row_key: "r1", candidate: "Total Sales" });
  await http.validatePlan("full");
  assert.deepEqual(urls(fake), ["/api/devcenter/name-propose", "/api/devcenter/plan-validate"]);
  assert.equal(fake.calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(fake.calls[0].options.body), { row_key: "r1", candidate: "Total Sales" });
  assert.deepEqual(JSON.parse(fake.calls[1].options.body), { mode: "full" });
  assert.equal(fake.calls[1].options.headers["Content-Type"], "application/json");
});

test("each read passes the abort signal to fetch", async () => {
  const fake = fakeFetch();
  const http = createDevCenterHttp({ fetcher: fake.fetcher });
  const controller = new AbortController();
  await http.getCompareRows({}, { signal: controller.signal });
  await http.getSession({ signal: controller.signal });
  await http.getRowDiff("r1", "s1", { signal: controller.signal });
  assert.ok(fake.calls.every((call) => call.options.signal === controller.signal));
});

test("a read with no path value refuses before fetch", async () => {
  const fake = fakeFetch();
  const http = createDevCenterHttp({ fetcher: fake.fetcher });
  await assert.rejects(http.getRowDiff("", "s1"), (error) => error instanceof DevCenterError && error.code === "invalid_payload");
  assert.equal(fake.calls.length, 0);
});

test("buildQuery repeats array values and writes booleans as text", () => {
  assert.equal(buildQuery({ state: ["same", "different"], marks: true, empty: [] }), "?state=same&state=different&marks=true");
  assert.equal(buildQuery({}), "");
});

test("an error reply in the new shape rejects with its code, message, details, and status", async () => {
  const body = { error: { code: "not_found", message: "The row r9 does not exist.", details: { row_key: "r9" } } };
  const http = createDevCenterHttp({ fetcher: fakeFetch({ status: 404, body }).fetcher });
  await assert.rejects(http.getRowDiff("r9", "s1"), (error) => {
    assert.ok(error instanceof DevCenterError);
    assert.equal(error.code, "not_found");
    assert.equal(error.message, "The row r9 does not exist.");
    assert.deepEqual(error.details, { row_key: "r9" });
    assert.equal(error.source, "http");
    assert.equal(error.status, 404);
    return true;
  });
});

test("an HTTP 5xx reply with no error shape is unknown and a fetch failure is network", async () => {
  const http = createDevCenterHttp({ fetcher: fakeFetch({ status: 502, body: undefined }).fetcher });
  await assert.rejects(http.getSession(), (error) => error.code === "unknown" && error.status === 502 && /HTTP 502/.test(error.message));
  const down = createDevCenterHttp({ fetcher: fakeFetch(new TypeError("Failed to fetch")).fetcher });
  await assert.rejects(down.getSession(), (error) => error.code === "network" && error.source === "network");
});

test("an aborted read rejects with the code aborted", async () => {
  const abort = new Error("The operation was aborted.");
  abort.name = "AbortError";
  const http = createDevCenterHttp({ fetcher: fakeFetch(abort).fetcher });
  await assert.rejects(http.getSession(), (error) => error.code === "aborted");
});

test("normalizeError reads the new shape, the old shape, and a thrown error", () => {
  const fresh = normalizeError({ error: { code: "stale_revision", message: "Changed.", details: { revision: 9 } } });
  assert.deepEqual([fresh.code, fresh.message, fresh.details, fresh.source], ["stale_revision", "Changed.", { revision: 9 }, "jsapi"]);

  const old = normalizeError({ ok: false, error: "The folder does not exist." });
  assert.deepEqual([old.code, old.message, old.details.shape], ["unknown", "The folder does not exist.", "old"]);

  const thrown = normalizeError(new Error("socket closed"));
  assert.deepEqual([thrown.code, thrown.message, thrown.source], ["network", "socket closed", "network"]);

  const shim = new Error("The fake server replied with HTTP 409.");
  shim.reply = { error: { code: "source_changed", message: "A source changed.", details: {} } };
  assert.equal(normalizeError(shim).code, "source_changed");

  const same = new DevCenterError({ code: "not_found" });
  assert.equal(normalizeError(same), same);

  const strange = normalizeError({ error: { code: "disk_full", message: "No space." } });
  assert.deepEqual([strange.code, strange.details.original_code], ["unknown", "disk_full"]);
  assert.equal(normalizeError(null).code, "unknown");
  assert.equal(normalizeError("text").code, "unknown");
});

test("errorReaction gives the UI reaction of each code", () => {
  const reaction = (code, method, extra = {}) => errorReaction(new DevCenterError({ code, ...extra }), method);
  assert.equal(reaction("stale_revision"), "toast");
  assert.equal(reaction("session_not_open"), "list");
  assert.equal(reaction("source_changed", "merge_choice_set"), "compare_marks");
  assert.equal(reaction("source_changed", "proposal_accept"), "inline");
  assert.equal(reaction("source_changed", "proposal_accept_all"), "inline");
  for (const code of ["action_not_allowed", "invalid_payload", "not_found", "user_choice_exists"]) assert.equal(reaction(code), "inline");
  for (const code of ["confidence_below_threshold", "reason_required", "naming_rule_violation"]) assert.equal(reaction(code), "agent");
  assert.equal(reaction("network"), "region");
  assert.equal(reaction("unknown"), "region");
  assert.equal(reaction("not_found", null, { source: "http", status: 503 }), "region");
  assert.equal(reaction("dropped"), "none");
});

test("each resource key of invalidation.js has a read", () => {
  assert.deepEqual(Object.keys(RESOURCE_READS).sort(), [...RESOURCE_KEYS].sort());
});
