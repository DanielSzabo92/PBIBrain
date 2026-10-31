// Smoke test of the React seam of the Development Center data layer (UI design step U2).
// The design has no React render tests; this test only proves that the module loads and exports its API.
import assert from "node:assert/strict";
import test from "node:test";
import * as seam from "../src/devcenter/useDevCenter.js";

test("useDevCenter.js exports the provider and the hooks", () => {
  for (const name of ["DevCenterProvider", "useDevCenterStore", "useDevCenterState", "useResource", "useAction"]) {
    assert.equal(typeof seam[name], "function", name);
  }
});
