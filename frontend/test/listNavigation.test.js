import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { listMove, listStep } from "../src/listNavigation.js";

test("every list moves with the same keys", () => {
  assert.equal(listMove({ key: "ArrowDown" }), "next");
  assert.equal(listMove({ key: "ArrowUp" }), "previous");
  assert.equal(listMove({ key: "Home" }), "first");
  assert.equal(listMove({ key: "End" }), "last");
  assert.equal(listMove({ key: "PageDown" }), "page-down");
  assert.equal(listMove({ key: "ArrowDown", ctrlKey: true }), null);
  assert.equal(listMove({ key: "a" }), null);
});

test("a move stops at the ends of the list; a page move clamps", () => {
  assert.equal(listStep("next", 0, 3), 1);
  assert.equal(listStep("next", 2, 3), -1);
  assert.equal(listStep("previous", 0, 3), -1);
  assert.equal(listStep("first", 2, 3), 0);
  assert.equal(listStep("last", 0, 3), 2);
  assert.equal(listStep("page-down", 1, 10, 4), 5);
  assert.equal(listStep("page-down", 8, 10, 4), 9);
  assert.equal(listStep("page-up", 2, 10, 4), 0);
  assert.equal(listStep("next", -1, 3), 0);
  assert.equal(listStep("next", 0, 0), -1);
});

test("search results, relationships, the review queue and the object tree share the list keys", () => {
  for (const file of ["src/views/SearchView.jsx", "src/views/Inspector.jsx", "src/views/ReviewQueue.jsx", "src/components/ObjectTree.jsx"]) {
    const source = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
    assert.match(source, /from "\.\.\/listNavigation"/, file);
    assert.doesNotMatch(source, /ArrowDown: index \+ 1|event\.key === "ArrowDown" \? 1/, file);
  }
});
