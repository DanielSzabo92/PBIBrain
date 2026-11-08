// Tests for ProvenanceLegend canonical trio (PRODUCT.md principle 2).
import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const LEGEND_JSX = fileURLToPath(new URL("../src/components/ProvenanceLegend.jsx", import.meta.url));
const GLYPH_JSX = fileURLToPath(new URL("../src/components/LinkStyleGlyph.jsx", import.meta.url));

test("ProvenanceLegend defines the canonical provenance trio: Factual, Inferred, Observed", async () => {
  const source = await readFile(LEGEND_JSX, "utf8");
  assert.match(source, /export function ProvenanceLegend/);
  assert.match(source, /export default ProvenanceLegend/);
  assert.match(source, /kind="factual"/);
  assert.match(source, /kind="inferred"/);
  assert.match(source, /kind="observed"/);
  assert.match(source, />Factual</);
  assert.match(source, />Inferred</);
  assert.match(source, />Observed</);
  // Ensure legacy / divergent terms are NOT present
  assert.doesNotMatch(source, /From source/);
  assert.doesNotMatch(source, />Suggested</);
  assert.doesNotMatch(source, /Known reference/);
  assert.doesNotMatch(source, /Possible/);
});

test("LinkStyleGlyph supports factual, inferred, and observed dashes", async () => {
  const source = await readFile(GLYPH_JSX, "utf8");
  assert.match(source, /factual:/);
  assert.match(source, /inferred:/);
  assert.match(source, /observed:/);
  assert.match(source, /kind = "factual"/);
});
