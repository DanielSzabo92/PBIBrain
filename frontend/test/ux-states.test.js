import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { isBackendUnreachableError } from "../src/presentation.js";
import { t as devCopy } from "../src/devcenter/copy.js";
import { banners } from "../src/devcenter/screens/sessionModel.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("isBackendUnreachableError identifies network, offline, and gateway errors", () => {
  assert.equal(isBackendUnreachableError(new Error("Failed to fetch")), true);
  assert.equal(isBackendUnreachableError(new TypeError("fetch failed")), true);
  assert.equal(isBackendUnreachableError(new Error("NetworkError when attempting to fetch resource")), true);
  assert.equal(isBackendUnreachableError(new Error("connect ECONNREFUSED 127.0.0.1:8000")), true);
  assert.equal(isBackendUnreachableError(new Error("Connection refused")), true);
  assert.equal(isBackendUnreachableError("Load failed"), true);
  assert.equal(isBackendUnreachableError({ status: 502 }), true);
  assert.equal(isBackendUnreachableError({ status: 503 }), true);
  assert.equal(isBackendUnreachableError({ status: 504 }), true);

  assert.equal(isBackendUnreachableError(new Error("Validation failed: field required")), false);
  assert.equal(isBackendUnreachableError(new Error("SyntaxError: Unexpected token")), false);
  assert.equal(isBackendUnreachableError(null), false);
  assert.equal(isBackendUnreachableError(undefined), false);
});

test("StateCell displays Not checked placeholder instead of permanent skeleton when idle", () => {
  const stateCellSource = fs.readFileSync(path.join(__dirname, "../src/devcenter/components/StateCell.jsx"), "utf-8");
  // Skeletons only render when loading is true
  assert.match(stateCellSource, /loading/);
  assert.match(stateCellSource, /dc-st-not-checked/);
  assert.match(stateCellSource, /Not checked/);
  assert.equal(devCopy("compare.state.not_checked"), "Not checked");
});

test("CompareGrid renders missing source column as greyed out with Not found", () => {
  const compareGridSource = fs.readFileSync(path.join(__dirname, "../src/devcenter/components/CompareGrid.jsx"), "utf-8");
  assert.match(compareGridSource, /isMissing/);
  assert.match(compareGridSource, /status === "missing"/);
  assert.match(compareGridSource, /dc-cell-missing/);
  assert.match(compareGridSource, /dc-hcell-missing/);
  assert.match(compareGridSource, /Not found/);
});

test("SessionModel and SessionList provide recovery actions for broken sessions", () => {
  // Locked banner provides owner, time, and read-only indication
  const lockedBanner = banners({
    lock_state: "locked",
    locked: true,
    lock_owner: "Alice",
    lock_time: "2026-11-08T12:00:00Z",
    read_only: false,
  });
  assert.ok(lockedBanner.some((b) => b.id === "locked" && b.text.includes("Alice")));

  const sessionListSource = fs.readFileSync(path.join(__dirname, "../src/devcenter/screens/SessionList.jsx"), "utf-8");
  // Damaged session file path and recovery actions
  assert.match(sessionListSource, /schema_state !== "ok"/);
  assert.match(sessionListSource, /Copy session path/);
  assert.match(sessionListSource, /Delete session/);
  assert.match(sessionListSource, /Open read-only/);

  const workAreaSource = fs.readFileSync(path.join(__dirname, "../src/devcenter/screens/WorkArea.jsx"), "utf-8");
  assert.match(workAreaSource, /Copy path/);
  assert.match(workAreaSource, /Delete session/);
});

test("StatusBar shows honest loading and unreachable states and inline Scan now", () => {
  const appShellSource = fs.readFileSync(path.join(__dirname, "../src/components/AppShell.jsx"), "utf-8");
  assert.match(appShellSource, /connection === "loading"\s*\?\s*"Loading project…"/);
  assert.match(appShellSource, /connection === "error"\s*\?\s*"Service unreachable"/);
  assert.match(appShellSource, /statusbar-scan-now/);
  assert.match(appShellSource, /Scan now/);
});

test("Overview in App.jsx provides unreachable backend state, honest loading, and inline actions", () => {
  const appSource = fs.readFileSync(path.join(__dirname, "../src/App.jsx"), "utf-8");
  // Offline / unreachable dedicated screen
  assert.match(appSource, /Can't reach the PBIBrain service/);
  assert.match(appSource, /Retry connection/);

  // Honest loading: do not display onboarding copy while loading
  assert.match(appSource, /loading \? \(/);
  assert.match(appSource, /Loading project…/);

  // Inline "Run validation" and "Scan now"
  assert.match(appSource, /Run validation/);
  assert.match(appSource, /Scan now/);

  // Disabled button tooltips
  assert.match(appSource, /Project settings unavailable\. Connect to the PBIBrain service first\./);
  assert.match(appSource, /No configuration changes to save/);
});

test("Button component supports tooltips on disabled buttons", () => {
  const buttonSource = fs.readFileSync(path.join(__dirname, "../src/components/ui/button.jsx"), "utf-8");
  assert.match(buttonSource, /cursor-not-allowed/);
  assert.match(buttonSource, /tabIndex=\{0\}/);
});
