import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SHORTCUTS, VIEW_ORDER, commandFor } from "../src/shortcuts.js";
import { t as devCopy } from "../src/devcenter/copy.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("Ctrl+K is command palette shortcut and does not duplicate search shortcut", () => {
  const findShortcut = SHORTCUTS.find((s) => s.id === "find");
  assert.ok(findShortcut);
  assert.equal(findShortcut.keys, "Ctrl+K");
  assert.equal(findShortcut.label, "Command palette");

  const searchShortcut = SHORTCUTS.find((s) => s.id === "view:search");
  assert.ok(searchShortcut);
  assert.equal(searchShortcut.keys, "Ctrl+2");

  assert.notEqual(findShortcut.keys, searchShortcut.keys);
});

test("graph tabs are renamed to avoid collision with Overview and Inspector", () => {
  const graphViewSource = fs.readFileSync(path.join(__dirname, "../src/components/GraphView.jsx"), "utf-8");
  assert.match(graphViewSource, /Containers/);
  assert.match(graphViewSource, /Neighbourhood/);
  assert.match(graphViewSource, /Lineage flow/);
  assert.match(graphViewSource, /Field usage/);

  // Tab values preserved for internal logic
  assert.match(graphViewSource, /value="overview"/);
  assert.match(graphViewSource, /value="connections"/);
  assert.match(graphViewSource, /value="full"/);
  assert.match(graphViewSource, /value="matrix"/);
});

test("graph details tab is renamed from Lineage to Dependencies", () => {
  const graphDetailsSource = fs.readFileSync(path.join(__dirname, "../src/components/GraphDetails.jsx"), "utf-8");
  assert.match(graphDetailsSource, /<TabsTrigger value="lineage">Dependencies<\/TabsTrigger>/);
});

test("Inspector lineage card is renamed to avoid collision with graph tabs", () => {
  const appSource = fs.readFileSync(path.join(__dirname, "../src/App.jsx"), "utf-8");
  assert.match(appSource, /<h2 className="panel-title">Lineage &amp; usage<\/h2>/);
});

test("Settings tabs include Keyboard and have consolidated export naming", () => {
  const appSource = fs.readFileSync(path.join(__dirname, "../src/App.jsx"), "utf-8");
  assert.match(appSource, /<TabsTrigger value="summary">Model summary \/ agent context<\/TabsTrigger>/);
  assert.match(appSource, /<TabsTrigger value="documentation">Documentation export<\/TabsTrigger>/);
  assert.match(appSource, /<TabsTrigger value="keyboard">Keyboard<\/TabsTrigger>/);
  assert.match(appSource, /<TabsContent value="keyboard"><KeyboardSettings \/><\/TabsContent>/);
});

test("DevCenter session management copy strings exist", () => {
  assert.equal(devCopy("work.more.sessions"), "All merge sessions");
  assert.equal(devCopy("work.more.rename"), "Rename session");
  assert.equal(devCopy("work.more.duplicate"), "Duplicate session");
  assert.equal(devCopy("work.more.delete"), "Delete session");
  assert.equal(devCopy("list.row.open"), "Open session");
  assert.equal(devCopy("list.row.rename"), "Rename session");
  assert.equal(devCopy("list.row.duplicate"), "Duplicate session");
  assert.equal(devCopy("list.row.delete"), "Delete session");
});

test("CommandPalette component file is present and exports correctly", () => {
  const file = path.join(__dirname, "../src/components/CommandPalette.jsx");
  assert.ok(fs.existsSync(file));
  const src = fs.readFileSync(file, "utf-8");
  assert.match(src, /export default function CommandPalette/);
  assert.match(src, /allCommands/);
});

test("InspectorEmpty component file is present and exports correctly", () => {
  const file = path.join(__dirname, "../src/components/InspectorEmpty.jsx");
  assert.ok(fs.existsSync(file));
  const src = fs.readFileSync(file, "utf-8");
  assert.match(src, /export default function InspectorEmpty/);
});

test("ExportDialog component file is present and exports correctly", () => {
  const file = path.join(__dirname, "../src/components/ExportDialog.jsx");
  assert.ok(fs.existsSync(file));
  const src = fs.readFileSync(file, "utf-8");
  assert.match(src, /export default function ExportDialog/);
});
