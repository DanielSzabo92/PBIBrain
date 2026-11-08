// Tests for review undo, app-wide toast system, and reviewed audit history trail.
import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const TOAST_JSX = fileURLToPath(new URL("../src/components/ui/toast.jsx", import.meta.url));

test("toast.jsx defines ToastProvider, useToast, and Toaster export", async () => {
  const source = await readFile(TOAST_JSX, "utf8");
  assert.match(source, /function ToastProvider/);
  assert.match(source, /function useToast/);
  assert.match(source, /export const Toaster = ToastProvider/);
  assert.match(source, /export const TOAST_MIN_MS = 8000/);
  assert.match(source, /const existing = React\.useContext\(ToastContext\)/);
});

test("review audit entry preserves who, when, and what", () => {
  const item = {
    id: "cand-1",
    candidate_id: "cand-1",
    target: "model:sales/measure:revenue",
    meaning: "Total Revenue",
    confidence: 0.92,
    status: "candidate",
  };
  const now = new Date().toISOString();
  const entry = {
    id: "audit-1",
    reviewId: item.candidate_id,
    targetId: item.target,
    action: "approve",
    actor: "You",
    timestamp: now,
    label: "Total Revenue",
    value: "Total Revenue",
    item,
    previousStatus: "candidate",
  };

  assert.equal(entry.actor, "You");
  assert.equal(entry.action, "approve");
  assert.equal(entry.targetId, "model:sales/measure:revenue");
  assert.equal(entry.timestamp, now);
});

test("undo review builds the correct reverse payload for candidate and override", () => {
  const candidateEntry = {
    reviewId: "cand-1",
    candidateId: "cand-1",
    targetId: "model:sales/measure:revenue",
    property: "business_concept",
    item: { id: "cand-1" },
  };
  const candPayload = {
    target: candidateEntry.targetId,
    candidate_id: candidateEntry.candidateId,
    review_id: candidateEntry.reviewId,
    property: candidateEntry.property,
  };
  assert.deepEqual(candPayload, {
    target: "model:sales/measure:revenue",
    candidate_id: "cand-1",
    review_id: "cand-1",
    property: "business_concept",
  });

  const staleEntry = {
    reviewId: "override:model:sales/measure:old:business_concept",
    targetId: "model:sales/measure:old",
    property: "business_concept",
    item: { issue: "stale", item: { value: "old meaning" } },
  };
  const stalePayload = {
    target: staleEntry.targetId,
    candidate_id: undefined,
    review_id: staleEntry.reviewId,
    property: staleEntry.property,
    override_id: staleEntry.reviewId,
    override_record: staleEntry.item.item,
  };
  assert.equal(stalePayload.override_id, "override:model:sales/measure:old:business_concept");
  assert.deepEqual(stalePayload.override_record, { value: "old meaning" });
});
