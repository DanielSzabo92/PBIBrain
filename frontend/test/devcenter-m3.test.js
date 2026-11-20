import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createDevCenterHttp } from "../src/devcenter/httpClient.js";
import { t } from "../src/devcenter/copy.js";
import { formatCheckTime, planStripState } from "../src/devcenter/screens/plan/planModel.js";
import { deriveReadiness } from "../src/devcenter/screens/sessionModel.js";
import { failureReason } from "../src/devcenter/screens/plan/applyModel.js";

test("Issue #78: httpClient.getCompareRows forwards proposal and multi-value type/source", async () => {
  const seen = [];
  const http = createDevCenterHttp({
    fetcher: async (url) => {
      seen.push(url);
      return {
        ok: true,
        status: 200,
        json: async () => ({ rows: [], total: 0, state_counts: {} }),
      };
    },
  });
  await http.getCompareRows({
    state: "not_same",
    type: ["measure", "column"],
    source: ["s1", "s2"],
    proposal: "true",
  });
  assert.equal(seen.length, 1);
  assert.match(seen[0], /state=not_same/);
  assert.match(seen[0], /type=measure/);
  assert.match(seen[0], /type=column/);
  assert.match(seen[0], /source=s1/);
  assert.match(seen[0], /source=s2/);
  assert.match(seen[0], /proposal=true/);
});

test("Issue #76 & #77: CompareGrid and BulkBar use canonical {kind, source_id}, no policy in choice, and handle previous_choices", async () => {
  const gridSrc = await readFile(new URL("../src/devcenter/components/CompareGrid.jsx", import.meta.url), "utf-8");
  const bulkSrc = await readFile(new URL("../src/devcenter/components/BulkBar.jsx", import.meta.url), "utf-8");
  assert.doesNotMatch(gridSrc, /choicePayload\s*=\s*\{\s*choice:/);
  assert.doesNotMatch(gridSrc, /choicePayload\.policy\s*=/);
  assert.match(gridSrc, /kind:\s*"take",\s*source_id:/);
  assert.match(gridSrc, /reply\.previous_choices/);
  assert.match(gridSrc, /generationRef\.current/);
  assert.doesNotMatch(bulkSrc, /kind:\s*"take_from"/);
});

test("Issue #90: no hardcoded 14:22 or 09:30, plan_state computing, and work.change_target copy key", async () => {
  assert.equal(t("work.change_target"), "Change target");
  assert.equal(formatCheckTime(null), "");
  const strip = planStripState({ plan: { steps: [{ id: "1" }], operations: [{ id: "op1" }] }, checkTime: "" });
  assert.equal(strip.body, "1 plan step · 1 operation.");
  const readiness = deriveReadiness({ session: { plan_state: "computing" } });
  assert.equal(readiness.checking, true);

  const planTabSrc = await readFile(new URL("../src/devcenter/screens/plan/PlanTab.jsx", import.meta.url), "utf-8");
  assert.doesNotMatch(planTabSrc, /"14:22"/);
  assert.doesNotMatch(planTabSrc, /planResource\.loading/);
  assert.doesNotMatch(planTabSrc, /plan_state === "checking"/);
});

test("Issue #91 & #86: DevCenter uses real session lifecycle JS APIs and App resets sharedStore and wires onProjectChanged", async () => {
  const dcSrc = await readFile(new URL("../src/devcenter/screens/DevCenter.jsx", import.meta.url), "utf-8");
  const appSrc = await readFile(new URL("../src/App.jsx", import.meta.url), "utf-8");
  assert.match(dcSrc, /useAction\("session_rename"\)/);
  assert.match(dcSrc, /useAction\("session_delete"\)/);
  assert.match(dcSrc, /useAction\("session_duplicate"\)/);
  assert.doesNotMatch(dcSrc, /pbibrain_session_overrides/);
  assert.doesNotMatch(dcSrc, /pbibrain_deleted_sessions/);
  assert.match(appSrc, /devCenterShared\.store\s*=\s*null/);
  assert.match(appSrc, /onProjectChanged=\{reloadBrain\}/);
});

test("Issue #92: failureReason preserves real error message, CompareRowDetail uses mark.source_id, DesktopStart updated, no --brand-text", async () => {
  const reason = failureReason({ message: "TOM write exploded: duplicate key", details: { step: "write" } });
  assert.match(reason, /TOM write exploded: duplicate key/);

  const detailSrc = await readFile(new URL("../src/devcenter/components/CompareRowDetail.jsx", import.meta.url), "utf-8");
  assert.match(detailSrc, /row\.marks\?\.\[0\]\?\.source_id/);

  const cssSrc = await readFile(new URL("../src/devcenter/components/compare.css", import.meta.url), "utf-8");
  assert.doesNotMatch(cssSrc, /--brand-text/);

  const startSrc = await readFile(new URL("../src/views/DesktopStart.jsx", import.meta.url), "utf-8");
  assert.doesNotMatch(startSrc, /only read, never changed/);
});
