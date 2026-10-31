// StatusBadge refuses a tone with no label (UI design A4: no color-only status).
import test from "node:test";
import assert from "node:assert/strict";
import { STATUS_TONES, statusBadgeProps } from "../src/components/ui/status-badge-rules.js";

test("StatusBadge refuses a tone with no label", () => {
  for (const tone of STATUS_TONES) {
    for (const label of [undefined, null, "", "   "]) {
      assert.throws(() => statusBadgeProps({ tone, label }), /has no label/, `${tone} with ${JSON.stringify(label)}`);
    }
  }
  assert.throws(() => statusBadgeProps(), /has no label/);
  assert.throws(() => statusBadgeProps({ tone: "ok", label: 3 }), /has no label/);
});

test("StatusBadge refuses a tone that is not known", () => {
  assert.throws(() => statusBadgeProps({ tone: "danger", label: "Critical" }), /not known/);
});

test("StatusBadge accepts each tone with a word", () => {
  assert.deepEqual(STATUS_TONES, ["ok", "warn", "bad", "info", "plain", "proposal"]);
  for (const tone of STATUS_TONES) {
    assert.deepEqual(statusBadgeProps({ tone, label: " Valid " }), { tone, label: "Valid" });
  }
});
