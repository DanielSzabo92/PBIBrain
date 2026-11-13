// Rows of the Inspector's object tree: Model > Table > Measures and Columns, Report > Page > Visuals.
import { objectName } from "./presentation.js";

// Inside one owner the kinds a developer looks for first come first, as in Power BI Desktop's Data pane.
const TYPE_ORDER = ["MODEL", "REPORT", "TABLE", "MEASURE", "COLUMN", "HIERARCHY", "RELATIONSHIP", "ROLE", "PAGE", "VISUAL"];
const rank = (type) => { const index = TYPE_ORDER.indexOf(type); return index < 0 ? TYPE_ORDER.length : index; };

function byKind(ids, byId) {
  // The ids arrive in name order; a stable sort by kind keeps that order inside each kind.
  return [...ids].sort((left, right) => rank(byId.get(left)?.type) - rank(byId.get(right)?.type));
}

/**
 * The visible rows, top to bottom.
 * With a filter, only the objects whose name holds it and their owners are listed, all opened.
 * @returns {{ id: string, node: object, depth: number, children: number, open: boolean }[]}
 */
export function treeRows(forest, expanded = new Set(), filter = "") {
  if (!forest) return [];
  const { byId, roots, childrenById, parentOf } = forest;
  const needle = String(filter || "").trim().toLowerCase();
  let keep = null;
  if (needle) {
    keep = new Set();
    for (const [id, node] of byId) {
      if (!objectName(node).toLowerCase().includes(needle)) continue;
      for (let current = id; current && !keep.has(current); current = parentOf.get(current)) keep.add(current);
    }
  }
  const rows = [];
  const visit = (id, depth) => {
    if (keep && !keep.has(id)) return;
    const node = byId.get(id);
    if (!node) return;
    const all = childrenById.get(id) || [];
    const children = keep ? all.filter((child) => keep.has(child)) : all;
    const open = children.length > 0 && (Boolean(keep) || expanded.has(id));
    rows.push({ id, node, depth, children: all.length, open });
    if (open) for (const child of byKind(children, byId)) visit(child, depth + 1);
  };
  for (const id of byKind(roots, byId)) visit(id, 0);
  return rows;
}

/** The owners of an object, outermost first: what has to be open for the object to be on screen. */
export function ownersOf(forest, id) {
  const path = [];
  for (let current = forest?.parentOf.get(id); current; current = forest.parentOf.get(current)) path.unshift(current);
  return path;
}
