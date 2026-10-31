// Unit tests of the Development Center copy catalog (UI design section 8, step U2).
import assert from "node:assert/strict";
import test from "node:test";
import { COPY, errorCopy, errorKey, longCallText, t, tn } from "../src/devcenter/copy.js";
import { CLIENT_ERROR_CODES, DevCenterError, SERVER_ERROR_CODES } from "../src/devcenter/errors.js";
import { JSAPI_METHODS } from "../src/devcenter/jsapiClient.js";

const entries = Object.entries(COPY);

test("each copy key has text", () => {
  assert.ok(entries.length > 500, "the catalog has the full key list");
  for (const [key, text] of entries) {
    assert.match(key, /^[a-z]+(\.[a-z0-9_]+)+$/, `bad key ${key}`);
    assert.equal(typeof text, "string", key);
    assert.ok(text.trim().length > 0, `${key} has no text`);
    assert.doesNotMatch(text, /^\s|\s{2}/, `${key} has extra spaces`);
  }
});

test("no copy text has an em dash, an en dash, an emoji, an ellipsis character, or (s)", () => {
  const rules = [
    ["em or en dash", /[–—]/u],
    ["emoji", /[\p{Extended_Pictographic}\u{1F1E6}-\u{1F1FF}\u{FE0F}]/u],
    ["ellipsis character", /…/u],
    ["three dots", /\.\.\./u],
    ["(s) plural", /\(s\)/iu],
    ["arrow character", /[←-⇿]/u],
  ];
  const found = [];
  for (const [key, text] of entries) {
    for (const [name, pattern] of rules) if (pattern.test(text)) found.push(`${key}: ${name}`);
  }
  assert.deepEqual(found, []);
});

test("each placeholder is a whole value in braces, and no angle bracket placeholder stays", () => {
  for (const [key, text] of entries) {
    assert.doesNotMatch(text, /<[a-z][^>]*>/i, `${key} uses an angle bracket placeholder`);
    const open = (text.match(/\{/g) ?? []).length;
    const close = (text.match(/\}/g) ?? []).length;
    assert.equal(open, close, `${key} has a broken placeholder`);
    for (const match of text.matchAll(/\{([^}]*)\}/g)) assert.match(match[1], /^[a-z_]+$/, `${key}: {${match[1]}}`);
  }
});

test("each count key has its one and other forms", () => {
  for (const key of Object.keys(COPY)) {
    if (key.endsWith(".one")) assert.ok(COPY[`${key.slice(0, -4)}.other`], `${key} has no .other form`);
  }
});

test("each error code of section 12 plus network and unknown has a text", () => {
  for (const code of [...SERVER_ERROR_CODES, "network", "unknown"]) {
    const key = errorKey(code);
    assert.ok(COPY[key], code);
    if (code !== "unknown") assert.notEqual(key, "error.unknown.body", `${code} falls back to unknown`);
  }
  assert.equal(COPY["error.stale_revision"], COPY["shared.stale"]);
  assert.equal(COPY["error.session_not_open"], COPY["shared.session_not_open"]);
  assert.ok(CLIENT_ERROR_CODES.includes("network"));
});

test("errorCopy gives the fixed text of a code and uses the backend message only where the catalog says so", () => {
  const copy = (code, message = "", details = {}) => errorCopy(new DevCenterError({ code, message, details }));
  assert.deepEqual(copy("network", "socket closed"), { title: "Cannot reach PBIBrain", body: COPY["shared.network.body"] });
  assert.deepEqual(copy("unknown", "The bridge stopped."), {
    title: "Something stopped this action",
    body: "The bridge stopped. Try again. If it fails again, open the Log tab and copy the details.",
  });
  assert.equal(copy("unknown").body, "Try again. If it fails again, open the Log tab and copy the details.");
  assert.equal(copy("action_not_allowed", "the plan is not valid").body, "This action is not possible now: the plan is not valid");
  assert.equal(copy("action_not_allowed", "", { existing_rule_id: "rule-4" }).body, "A rule with this scope and check kind exists: rule-4. Edit that rule.");
  assert.equal(copy("not_found", "", { kind: "row" }).body, "PBIBrain cannot find this row. It was removed or renamed in another place. Load the view again.");
  assert.equal(copy("user_choice_exists", "backend text").body, COPY["error.user_choice_exists"]);
});

test("t replaces placeholders and tn picks the count form", () => {
  assert.equal(t("work.target_model", { name: "Sales Master" }), "Target model: Sales Master");
  assert.equal(t("work.target_model"), "Target model: {name}");
  assert.equal(t("no.such.key"), "no.such.key");
  assert.equal(tn("row.blocking", 1), "1 blocking item for this row.");
  assert.equal(tn("row.blocking", 3), "3 blocking items for this row.");
  assert.equal(tn("sources.remove.body", 0, { source: "Sales A" }), "No Merge Choice takes from Sales A.");
  assert.equal(tn("sources.remove.body", 2, { source: "Sales A" }), "2 Merge Choices take from Sales A. They stay, but the plan is not valid until you change them.");
});

test("each long method has a status line, and each changing method has a log label", () => {
  for (const { name, kind } of JSAPI_METHODS) {
    if (kind === "long") assert.match(longCallText(name), /\. Changes wait until this ends\.$/, name);
  }
  assert.equal(longCallText("sources_check"), "Checking sources. Changes wait until this ends.");
  assert.equal(longCallText("merge_choice_set"), null);
  const notLogged = new Set(["cloud_sign_in", "cloud_items_list", "impact_action_apply"]);
  for (const { name } of JSAPI_METHODS) {
    if (notLogged.has(name)) continue;
    const labels = Object.keys(COPY).filter((key) => key === `log.action.${name}` || key.startsWith(`log.action.${name}.`));
    assert.ok(labels.length > 0, `no log label for ${name}`);
  }
});

test("each apply step and each guard check has one sentence", () => {
  const steps = ["source_check", "plan_status", "desktop_check", "canonical_check", "full_validation", "approval",
    "candidate_write", "guard", "promotion", "rescan", "fingerprints"];
  for (const step of steps) {
    assert.ok(COPY[`details.step.${step}`], `details.step.${step}`);
    assert.ok(COPY[`apply.step.${step}`], `apply.step.${step}`);
  }
  for (const check of ["scope", "canonical", "tree_compare", "pbir", "policy", "approval", "write", "rescan"]) {
    assert.ok(COPY[`details.check.${check}`], `details.check.${check}`);
  }
});

test("the shared texts of section 8.3 are the design texts", () => {
  assert.equal(COPY["shared.stale"], "This session changed in another place. The view shows the latest state. Do the action again.");
  assert.equal(COPY["shared.network.title"], "Cannot reach PBIBrain");
  assert.equal(COPY["shared.network.body"], "The local API did not answer. Make sure PBIBrain is running, then try again.");
  assert.equal(COPY["shared.unknown.title"], "Something stopped this action");
  assert.equal(COPY["shared.locked.banner"], "Another PBIBrain window has this session open. You can read it, but you cannot change it.");
  assert.equal(COPY["shared.not_current"], "This data is not current. Try again to load it.");
  assert.equal(COPY["shared.session_not_open"], "This session is not open now. Open it again from the list.");
});

test("the confirm buttons of section 8.4 restate the action and the object", () => {
  const confirms = {
    "sources.remove.confirm": "Remove source",
    "compare.bulk.dialog.set.confirm": "Set Merge Choice",
    "compare.bulk.dialog.remove.confirm": "Remove from target",
    "row.split.confirm": "Split row",
    "row.policy.block.confirm": "Use Block",
    "row.policy.cascade.confirm": "Use Cascade (remove {n} objects)",
    "row.policy.repoint.confirm": "Use Repoint",
    "agent.accept_all.confirm.other": "Accept {n} proposals",
    "rules.delete.confirm": "Delete rule",
    "pull.confirm": "Pull model",
    "apply.confirm": "Apply plan",
    "format.confirm": "Format files",
    "undo.confirm": "Undo apply",
  };
  for (const [key, text] of Object.entries(confirms)) assert.equal(COPY[key], text, key);
  assert.equal(COPY["shared.cancel"], "Cancel");
});
