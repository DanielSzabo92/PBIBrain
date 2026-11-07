import assert from "node:assert/strict";
import test from "node:test";
import { pendingHeadline, pendingKey, pendingLines, pendingTone, showsPending } from "../src/pendingChanges.js";
import { createBrainTransport } from "../src/transport.js";

const breaks = {
  status: "BREAKS",
  scanned_at: "2026-11-07T10:00:00Z",
  file_count: 1,
  files: [{ file: "Sales.SemanticModel/definition/tables/FactSales.tmdl", change: "changed" }],
  safety: {
    summary: { changes: 1, deleted: 1, breaks: 2, needs: 1 },
    breaks: [
      { object_type: "MEASURE", name: "Sales YTD", table: "FactSales", reason: "uses_deleted", uses: { object_type: "MEASURE", name: "Sales Amount", table: "FactSales" } },
      { object_type: "VISUAL", name: "card", reason: "uses_old_name", uses: { object_type: "MEASURE", name: "Total", table: "Fact", new_name: "Revenue" } },
    ],
    needs: [{ object_type: "MEASURE", name: "Margin", table: "Fact", missing: [{ kind: "measure_or_column", name: "Cost" }, { kind: "table", name: "Budget" }] }],
  },
};

test("pending changes show only for changed files and say what breaks", () => {
  assert.equal(showsPending({ status: "UNCHANGED" }), false);
  assert.equal(showsPending({ status: "CHECKING" }), false);
  assert.equal(showsPending({ status: "NO_SCAN" }), false);
  assert.equal(showsPending(breaks), true);
  assert.equal(pendingTone(breaks), "bad");
  assert.equal(pendingTone({ ...breaks, status: "CHANGED" }), "warn");
  assert.equal(pendingHeadline(breaks), "1 file changed outside PBIBrain since the last scan: 1 object changed, breaks 2 objects, needs 1 missing object.");
  assert.deepEqual(pendingLines(breaks), {
    lines: [
      "FactSales[Sales YTD] uses FactSales[Sales Amount], which was deleted",
      "card still uses the old name of Fact[Total] (now Revenue)",
      "Fact[Margin] needs [Cost], 'Budget', which the model does not have",
    ],
    more: 0,
  });
  assert.match(pendingHeadline({ status: "UNREADABLE", file_count: 2 }), /2 files changed outside PBIBrain and cannot be read yet/);
});

test("a dismissed warning comes back only when the files change again", () => {
  const key = pendingKey(breaks);
  assert.equal(pendingKey({ ...breaks, checked_at: "later" }), key);
  assert.notEqual(pendingKey({ ...breaks, files: [...breaks.files, { file: "x.tmdl", change: "created" }] }), key);
  assert.equal(pendingKey({ status: "UNCHANGED" }), "");
});

test("the transport reads the pending-changes route", async () => {
  const calls = [];
  const transport = createBrainTransport({ fetcher: async (url) => { calls.push(url); return { ok: true, json: async () => ({ status: "UNCHANGED" }) }; } });
  assert.deepEqual(await transport.getPendingChanges(), { status: "UNCHANGED" });
  assert.deepEqual(calls, ["/api/pending-changes"]);
});
