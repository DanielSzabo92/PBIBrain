// App preferences that the Development Center uses (UI design 9.3, A24).
// The "/" key switch is stored in localStorage, as the theme is. Storage can be unavailable: then the default is on.
const SLASH_KEY = "pbibrain-slash-search";

export function slashSearchEnabled(storage = globalThis.localStorage) {
  try {
    return storage?.getItem(SLASH_KEY) !== "off";
  } catch {
    return true;
  }
}

export function setSlashSearchEnabled(enabled, storage = globalThis.localStorage) {
  try {
    storage?.setItem(SLASH_KEY, enabled ? "on" : "off");
  } catch {
    // Storage can be unavailable. The switch then works only until the page reloads.
  }
}

// True when a "/" key event must go to search: the switch is on, focus is not in a text field, and no dialog is open.
export function slashGoesToSearch(event, { enabled = slashSearchEnabled(), doc = globalThis.document } = {}) {
  if (!enabled || event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return false;
  const target = event.target;
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(target?.tagName ?? "") || Boolean(target?.isContentEditable);
  if (typing) return false;
  return !doc?.querySelector?.('[role="dialog"][aria-modal="true"], [role="alertdialog"][aria-modal="true"]');
}
