// One list behaviour for every list of objects (search results, relationships, the review queue, the object tree):
// ↓/↑ move one row, Home/End go to the ends, PageDown/PageUp move a page where the list knows its page size.
export const LIST_MOVES = { ArrowDown: "next", ArrowUp: "previous", Home: "first", End: "last", PageDown: "page-down", PageUp: "page-up" };

export function listMove(event) {
  if (event.altKey || event.ctrlKey || event.metaKey) return null;
  return LIST_MOVES[event.key] || null;
}

// The row a move lands on, or -1 when it would leave the list (a page move stops at the ends instead).
export function listStep(where, index, count, page = 1) {
  if (!count) return -1;
  if (where === "first") return 0;
  if (where === "last") return count - 1;
  if (where === "page-down") return Math.min(count - 1, Math.max(0, index) + page);
  if (where === "page-up") return Math.max(0, index - page);
  const next = index + (where === "next" ? 1 : -1);
  return next >= 0 && next < count ? next : -1;
}

// Moves focus through the rows of a list in the DOM, as in a desktop list box.
export function moveInList(container, where, from, selector = ":scope > button:not(:disabled)") {
  const rows = [...(container?.querySelectorAll(selector) || [])];
  const next = listStep(where, rows.indexOf(from), rows.length);
  if (next < 0) return false;
  rows[next].focus();
  rows[next].scrollIntoView({ block: "nearest" });
  return true;
}

// Key handler for a list of buttons. Up from the first row returns to the field above (onTop),
// so search -> results -> search works without the mouse.
export function listKeys(event, onTop) {
  const where = listMove(event);
  if (!where || where.startsWith("page")) return;
  const from = event.target.closest?.("button");
  if (!from || from.parentElement !== event.currentTarget) return;
  event.preventDefault();
  if (!moveInList(event.currentTarget, where, from) && where === "previous") onTop?.();
}
