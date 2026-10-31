import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";
import { DEVCENTER_SHIM_PATH, devcenterFakeEnabled, devcenterFakePlugin, devcenterFakeProxy } from "../vite-plugins/devcenterFake.js";

const frontend = fileURLToPath(new URL("..", import.meta.url));
const shimTag = `src="${DEVCENTER_SHIM_PATH}"`;

async function buildIndex(fake) {
  const outDir = await mkdtemp(path.join(tmpdir(), "pbibrain-shim-build-"));
  const previous = process.env.DEVCENTER_FAKE;
  if (fake) process.env.DEVCENTER_FAKE = "1";
  else delete process.env.DEVCENTER_FAKE;
  try {
    await build({ root: frontend, configFile: path.join(frontend, "vite.config.js"), logLevel: "silent", build: { outDir, emptyOutDir: true } });
    return await readFile(path.join(outDir, "index.html"), "utf8");
  } finally {
    if (previous === undefined) delete process.env.DEVCENTER_FAKE;
    else process.env.DEVCENTER_FAKE = previous;
    await rm(outDir, { recursive: true, force: true });
  }
}

test("only DEVCENTER_FAKE=1 turns the fake mode on", () => {
  assert.equal(devcenterFakeEnabled({ DEVCENTER_FAKE: "1" }), true);
  for (const value of [undefined, "", "0", "true"]) assert.equal(devcenterFakeEnabled({ DEVCENTER_FAKE: value }), false);
});

test("the plugin adds the shim tag only when it is enabled", () => {
  assert.equal(devcenterFakePlugin({ enabled: false }).transformIndexHtml(), undefined);
  const tags = devcenterFakePlugin({ enabled: true }).transformIndexHtml();
  assert.deepEqual(tags, [{ tag: "script", attrs: { src: DEVCENTER_SHIM_PATH }, injectTo: "head-prepend" }]);
});

test("the fake proxy sends /api and /__test__ to the fake server on port 8766", () => {
  const proxy = devcenterFakeProxy({});
  assert.deepEqual(Object.keys(proxy).sort(), ["/__test__", "/api"]);
  for (const entry of Object.values(proxy)) assert.equal(entry.target, "http://127.0.0.1:8766");
  assert.equal(devcenterFakeProxy({ DEVCENTER_FAKE_URL: "http://127.0.0.1:9000" })["/api"].target, "http://127.0.0.1:9000");
});

test("the production build has no shim tag, and the DEVCENTER_FAKE=1 build has it", { timeout: 180000 }, async () => {
  const production = await buildIndex(false);
  assert.ok(production.includes('id="root"'), "the production build must write index.html");
  assert.equal(production.includes(shimTag), false, "the production build must not load the shim");
  assert.equal(production.includes("pywebviewShim"), false);
  const fake = await buildIndex(true);
  assert.equal(fake.includes(shimTag), true, "the DEVCENTER_FAKE=1 build must load the shim");
  assert.ok(fake.indexOf(shimTag) < fake.indexOf('type="module"'), "the shim must load before the app module");
});
