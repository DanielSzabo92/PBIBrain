import test from "node:test";
import assert from "node:assert/strict";
import { SHORTCUTS, VIEW_ORDER, commandFor, displayKeys, eventKeys, isTextEntry } from "../src/shortcuts.js";

const key = (key, extra = {}) => ({ key, code: /^[0-9]$/.test(key) ? `Digit${key}` : "", ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, target: null, ...extra });

test("view shortcuts follow the sidebar order", () => {
  VIEW_ORDER.slice(0, 6).forEach((view, index) => {
    assert.equal(commandFor(key(String(index + 1), { ctrlKey: true })), `view:${view}`);
  });
  assert.equal(commandFor(key(",", { ctrlKey: true })), "view:config");
});

test("function keys and modifiers map to shell commands", () => {
  assert.equal(commandFor(key("F5")), "reload");
  assert.equal(commandFor(key("F5", { ctrlKey: true })), "scan");
  assert.equal(commandFor(key("k", { metaKey: true })), "find");
  assert.equal(commandFor(key("L", { ctrlKey: true, shiftKey: true })), "theme");
  assert.equal(commandFor(key("b", { ctrlKey: true })), "sidebar");
  assert.equal(commandFor(key("F1")), "shortcuts");
  assert.equal(commandFor(key("x")), null);
  assert.equal(commandFor(key("Alt")), null, "Alt alone is handled by the menu bar, not as a command");
});

test("shifted digits still match by physical key", () => {
  assert.equal(eventKeys({ key: "!", code: "Digit1", ctrlKey: true, shiftKey: true }), "Ctrl+Shift+1");
});

test("Back leaves text fields alone", () => {
  const input = { tagName: "INPUT", type: "search" };
  assert.equal(isTextEntry(input), true);
  assert.equal(isTextEntry({ tagName: "BUTTON" }), false);
  assert.equal(commandFor(key("ArrowLeft", { altKey: true, target: input })), null);
  assert.equal(commandFor(key("ArrowLeft", { altKey: true, target: { tagName: "DIV" } })), "back");
});

test("shortcut ids are unique and keys do not collide", () => {
  const ids = SHORTCUTS.map((item) => item.id);
  const keys = SHORTCUTS.map((item) => item.keys.toUpperCase());
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(new Set(keys).size, keys.length);
});

test("mac display uses symbols", () => {
  assert.equal(displayKeys("Ctrl+Shift+L", "MacIntel"), "⌘⇧L");
  assert.equal(displayKeys("Ctrl+K", "Win32"), "Ctrl+K");
});
