import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

// Review 16: the script that every page waits for stays small; Merge models and the graph library load on demand.
const dist = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "dist");
const ENTRY_BUDGET = 420_000; // bytes before compression (347 kB when the budget was set)
const STYLE_BUDGET = 230_000;

test("the built entry script and stylesheet stay within budget", { skip: !existsSync(path.join(dist, "index.html")) && "no build in dist/" }, () => {
  const html = readFileSync(path.join(dist, "index.html"), "utf8");
  const entry = html.match(/<script[^>]+src="\/(assets\/index-[^"]+\.js)"/)?.[1];
  const style = html.match(/<link rel="stylesheet"[^>]+href="\/(assets\/index-[^"]+\.css)"/)?.[1];
  assert.ok(entry, "index.html names the entry script");
  assert.ok(statSync(path.join(dist, entry)).size < ENTRY_BUDGET, `${entry} is over ${ENTRY_BUDGET} bytes`);
  assert.ok(style && statSync(path.join(dist, style)).size < STYLE_BUDGET, `${style} is over ${STYLE_BUDGET} bytes`);
  // The graph library and Merge models are not preloaded with the first page.
  assert.ok(!/modulepreload[^>]+assets\/(graph|DevCenter)-/.test(html), "graph and Merge models load on demand");
});
