import test from "node:test";
import assert from "node:assert/strict";
import { sourceState, sourceStatusMap } from "../src/sourceStatus.js";

test("a source row says whether it was found and what the last scan did with it", () => {
  assert.equal(sourceState(undefined).tone, "unknown");
  assert.deepEqual(sourceState({ exists: false }), { tone: "bad", label: "Not found at this path", text: "Not found" });
  assert.equal(sourceState({ exists: true }).text, "Found");
  assert.equal(sourceState({ exists: true, scan: { state: "scanned", models: 1, reports: 3 } }).text, "Scanned · 1 model, 3 reports");
  assert.equal(sourceState({ exists: true, scan: { state: "scanned" } }).text, "Scanned");
  const failed = sourceState({ exists: true, scan: { state: "failed", detail: "Invalid JSON" } });
  assert.deepEqual([failed.tone, failed.text, failed.label], ["bad", "Failed", "Could not be read: Invalid JSON"]);
  assert.equal(sourceState({ exists: true, scan: { state: "reading" } }).tone, "busy");
  assert.equal(sourceState({ exists: true, scan: { state: "not_scanned", detail: "The scan was cancelled" } }).label, "Not scanned. The scan was cancelled.");
  assert.deepEqual(Object.keys(sourceStatusMap({ sources: [{ path: "a.json", exists: true }] })), ["a.json"]);
});
