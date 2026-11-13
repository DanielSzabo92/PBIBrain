import test from "node:test";
import assert from "node:assert/strict";
import { parseRoute, routeHash } from "../src/routes.js";

test("every place in the app round-trips through its hash", () => {
  const places = [
    { view: "overview" },
    { view: "search", query: "total orders" },
    { view: "graph", focus: "model:m/table:t" },
    { view: "inspector", selectedId: "model:m/table:t/measure:Sales %" },
    { view: "review" },
    { view: "devcenter" },
    { view: "config", settingsTab: "colors" },
  ];
  for (const place of places) {
    const parsed = parseRoute(routeHash(place));
    for (const [key, value] of Object.entries(place)) assert.equal(parsed[key], value, `${place.view}.${key}`);
  }
  assert.equal(routeHash({ view: "overview" }), "#/");
  assert.equal(routeHash({ view: "config", settingsTab: "project" }), "#/settings");
});

test("an unknown or broken hash opens the Overview", () => {
  assert.equal(parseRoute("").view, "overview");
  assert.equal(parseRoute("#/nowhere/else").view, "overview");
  assert.equal(parseRoute("#/inspector/%E0%A4%A").selectedId, "%E0%A4%A");
});
