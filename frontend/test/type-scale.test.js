// Repo lint: every font size comes from the type scale in theme.css (--fs-* tokens),
// and that scale matches ui-policy.json, which lintapple checks in the rendered app.
// Before this, the CSS used 17 different sizes (10px to 30px, with half pixels).
import test from "node:test";
import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const POLICY = fileURLToPath(new URL("../ui-policy.json", import.meta.url));

async function files(dir) {
  const found = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...await files(full));
    else if (/\.(css|jsx?)$/.test(entry.name)) found.push(full);
  }
  return found;
}

async function scale() {
  const theme = await readFile(path.join(SRC, "theme.css"), "utf8");
  return Object.fromEntries([...theme.matchAll(/--fs-([a-z]+):\s*(\d+)px/g)].map((match) => [match[1], Number(match[2])]));
}

test("the type scale in theme.css is the font size list in ui-policy.json", async () => {
  const policy = JSON.parse(await readFile(POLICY, "utf8"));
  const sizes = Object.values(await scale()).sort((a, b) => a - b);
  assert.ok(sizes.length >= 5, "theme.css defines the --fs-* scale");
  assert.deepEqual(sizes, [...policy.fontSizes].sort((a, b) => a - b));
});

test("CSS and JSX use type scale tokens, not literal font sizes", async () => {
  const offenders = [];
  const allowed = new Set(Object.values(await scale()));
  for (const file of await files(SRC)) {
    if (file.endsWith("theme.css")) continue;
    const source = await readFile(file, "utf8");
    for (const match of source.matchAll(/font-size:\s*([^;}\n]+)/g)) {
      const value = match[1].trim();
      if (/^var\(--fs-[a-z]+\)$/.test(value) || value === "0" || value === "inherit") continue;
      offenders.push(`${path.relative(SRC, file)}: font-size: ${value}`);
    }
    for (const match of source.matchAll(/\btext-\[(\d+(?:\.\d+)?)px\]/g)) offenders.push(`${path.relative(SRC, file)}: ${match[0]}`);
    // Inline SVG styles (React Flow edge labels) take a number; it must still be a scale step.
    for (const match of source.matchAll(/fontSize:\s*(\d+(?:\.\d+)?)/g)) if (!allowed.has(Number(match[1]))) offenders.push(`${path.relative(SRC, file)}: ${match[0]}`);
  }
  assert.deepEqual(offenders, [], "Use var(--fs-*) in CSS or text-2xs/xs/sm/base/lg/xl/2xl utilities in JSX.");
});
