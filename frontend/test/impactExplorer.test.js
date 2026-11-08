import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("Collapsible and Disclosure components file is present and exports correctly", () => {
  const file = path.join(__dirname, "../src/components/ui/collapsible.jsx");
  assert.ok(fs.existsSync(file), "collapsible.jsx must exist");
  const src = fs.readFileSync(file, "utf-8");
  assert.match(src, /export\s*\{\s*Collapsible/);
  assert.match(src, /CollapsibleTrigger/);
  assert.match(src, /CollapsibleContent/);
  assert.match(src, /Disclosure/);
});

test("ImpactExplorer component file is present and exports correctly with auto-analysis and proOptions", () => {
  const file = path.join(__dirname, "../src/components/ImpactExplorer.jsx");
  assert.ok(fs.existsSync(file), "ImpactExplorer.jsx must exist");
  const src = fs.readFileSync(file, "utf-8");
  assert.match(src, /export default function ImpactExplorer/);
  assert.match(src, /hideAttribution:\s*true/);
  assert.match(src, /Disclosure/);
  assert.match(src, /Dialog/);
});
