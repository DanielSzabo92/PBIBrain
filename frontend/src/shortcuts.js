// One keyboard map for the whole app shell. The menu bar, the shortcut sheet, the
// sidebar tooltips and the global key handler all read it, so a shortcut is shown
// exactly where it works. Conventions follow Windows desktop apps (Power BI Desktop,
// VS Code, Tabular Editor): Ctrl+number switches views, F5 refreshes, Ctrl+, opens
// settings, Ctrl+B toggles the side bar, Alt+Left goes back, F1 lists the keys.

export const VIEW_ORDER = ["overview", "search", "graph", "inspector", "review", "devcenter", "config"];

export const SHORTCUTS = [
  { id: "view:overview", keys: "Ctrl+1", label: "Overview", group: "Go" },
  { id: "view:search", keys: "Ctrl+2", label: "Search", group: "Go" },
  { id: "view:graph", keys: "Ctrl+3", label: "Graph", group: "Go" },
  { id: "view:inspector", keys: "Ctrl+4", label: "Inspector", group: "Go" },
  { id: "view:review", keys: "Ctrl+5", label: "Review queue", group: "Go" },
  { id: "view:devcenter", keys: "Ctrl+6", label: "Development Center", group: "Go" },
  { id: "find", keys: "Ctrl+K", label: "Find object", group: "Go" },
  { id: "back", keys: "Alt+Left", label: "Back", group: "Go" },
  { id: "view:config", keys: "Ctrl+,", label: "Settings", group: "File" },
  { id: "scan", keys: "Ctrl+F5", label: "Scan sources", group: "File" },
  { id: "reload", keys: "F5", label: "Reload data", group: "View" },
  { id: "sidebar", keys: "Ctrl+B", label: "Toggle side bar", group: "View" },
  { id: "theme", keys: "Ctrl+Shift+L", label: "Toggle light/dark theme", group: "View" },
  { id: "shortcuts", keys: "F1", label: "Keyboard shortcuts", group: "Help" },
  { id: "menu", keys: "Alt", label: "Focus the menu bar (or F10)", group: "Help", display: true },
];

const BY_ID = Object.fromEntries(SHORTCUTS.map((item) => [item.id, item]));

export function shortcutKeys(id) {
  return BY_ID[id]?.keys || "";
}

const KEY_ALIASES = { ArrowLeft: "Left", ArrowRight: "Right", ArrowUp: "Up", ArrowDown: "Down", " ": "Space" };

/** Normalise a KeyboardEvent to the "Ctrl+Shift+K" form used in SHORTCUTS. Cmd counts as Ctrl. */
export function eventKeys(event) {
  const raw = event.key || "";
  if (["Control", "Shift", "Alt", "Meta"].includes(raw)) return raw === "Control" || raw === "Meta" ? "Ctrl" : raw;
  // Ctrl+Shift+L reports "L"; Ctrl+1 can report "!" on Shift layouts, so prefer the physical digit.
  let key = KEY_ALIASES[raw] || raw;
  if (/^Digit[0-9]$/.test(event.code || "")) key = event.code.slice(5);
  if (key.length === 1) key = key.toUpperCase();
  const parts = [];
  if (event.ctrlKey || event.metaKey) parts.push("Ctrl");
  if (event.altKey) parts.push("Alt");
  if (event.shiftKey) parts.push("Shift");
  parts.push(key);
  return parts.join("+");
}

const TEXT_TYPES = /^(text|search|email|url|tel|password|number)$/i;

export function isTextEntry(target) {
  if (!target || typeof target !== "object") return false;
  if (target.isContentEditable) return true;
  const tag = String(target.tagName || "").toUpperCase();
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  return tag === "INPUT" && TEXT_TYPES.test(target.type || "text");
}

/**
 * The shell command for a key event, or null. Back (Alt+Left) is left to text fields,
 * where it is a caret movement on some platforms; every other shell key works anywhere,
 * because each one carries a modifier or is a function key.
 */
export function commandFor(event) {
  const keys = eventKeys(event);
  const hit = SHORTCUTS.find((item) => !item.display && item.keys.toUpperCase() === keys.toUpperCase());
  if (!hit) return null;
  if (hit.id === "back" && isTextEntry(event.target)) return null;
  return hit.id;
}

/** Display form for a shortcut on the current platform ("Ctrl+K" or "⌘K"). */
export function displayKeys(keys, platform = globalThis.navigator?.platform || "") {
  if (!keys) return "";
  if (!/Mac|iPhone|iPad/i.test(platform)) return keys;
  return keys.replace(/Ctrl\+/g, "⌘").replace(/Alt\+/g, "⌥").replace(/Shift\+/g, "⇧").replace("Left", "←");
}
