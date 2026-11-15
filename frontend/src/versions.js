// Versions: the same logical object in two copies of a model or report ("Sales" and "Sales v2").
//
// Two models (or two reports) are versions of each other when their names agree apart from a version
// marker ("v2", "copy", "DEV", a date) and most of their objects match. Objects match
// with the rules of Merge models: model objects by type, table and name; report objects by their page and
// visual IDs, which survive a copied report folder. "Group versions" folds every set of matching objects into
// one node, so the picture shows each logical object once:
//
//   versions        every copy of the object, first version first
//   versionCount    how many versions have it            (×2: in both)
//   familySize      how many versions the family has     (1 of 2: only in one)
//   differs         the copies are not identical (their definitions, else source hashes, differ)
//
// Pure functions over graph payloads (getLineage or getGraph).

import { objectName } from "./presentation.js";

const ROOTS = new Set(["MODEL", "REPORT"]);
// Two roots are versions when this share of the smaller one's objects is also in the other.
const FAMILY_OVERLAP = 0.5;
const fold = (value) => String(value ?? "").trim().toLowerCase();

// Words that mark a copy of the same thing: "Sales v2", "Sales (copy)", "Sales - DEV", "Sales 2024-05-01".
const VERSION_WORDS = /\b(v(?:er(?:sion)?)?\.?\s*\d+(?:\.\d+)*|copy(?:\s+of)?|kopie|backup|bak|old|new|final|draft|wip|dev|test|uat|qa|stag(?:e|ing)|prod(?:uction)?|\d{4}[-_.]?\d{2}[-_.]?\d{2}|\(\d+\))\b/gi;

/**
 * A model or report name without its version marker. Two models stamped from one template
 * ("Sales Analytics", "HR Analytics") share their structure but not this stem, and they are not versions.
 */
export function versionStem(name) {
  const stem = fold(name).replace(/\(\d+\)/g, " ").replace(VERSION_WORDS, " ").replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  return stem || fold(name);
}
// One shared collator: localeCompare with options builds a new one on every call.
const NAME_ORDER = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

/**
 * The name of a folded model or report: the name its versions share, in the spelling of the first one
 * ("Sales Analytics v2" and "Sales Analytics (copy)" are "Sales Analytics").
 */
export function versionTitle(names) {
  const first = String(names?.[0] ?? "");
  const title = first.replace(/\(\d+\)/g, " ").replace(VERSION_WORDS, " ").replace(/\(\s*\)|\[\s*\]/g, " ").replace(/\s+/g, " ").replace(/^[\s\-_.,·:]+|[\s\-_.,·:]+$/g, "");
  return title || first;
}

const pairKey = (a, b) => (a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`);

const byName = (left, right) => NAME_ORDER.compare(objectName(left), objectName(right)) || left.id.localeCompare(right.id);

/** The model or report an object belongs to: its report for report objects, else its model. */
export function rootOf(node) {
  if (ROOTS.has(node?.type)) return node.id;
  return node?.report_id || node?.model_id || "";
}

/**
 * Key of an object inside its model or report, the same in every version of it, or "" when there is none.
 * Model objects: type + table + name. Report objects: type + source ID (else name), under their parent's key.
 */
function relativeKey(node, byId, seen = new Set()) {
  if (!node || ROOTS.has(node.type) || seen.has(node.id)) return "";
  seen.add(node.id);
  const own = `${node.type}:${fold(node.report_id ? node.source_id || node.name : node.name)}`;
  if (node.report_id) {
    const parent = byId.get(node.parent_id || node.page_id);
    const parentKey = parent && !ROOTS.has(parent.type) ? relativeKey(parent, byId, seen) : "";
    return parentKey ? `${parentKey}/${own}` : own;
  }
  const table = byId.get(node.table_id);
  if (table && table.id !== node.id) return `${fold(table.type)}:${fold(table.name)}/${own}`;
  return own;
}

/**
 * Families of versions and a version key for every object.
 * `links` are the user's corrections (project setting `version_links`): `same` pairs are versions whatever
 * their names say, `different` pairs never end up in one family.
 * @returns {{ keyOf: Map<id,string>, familyOf: Map<rootId,string>, families: Map<string, node[]> }}
 */
export function versionFamilies(nodes, links = null) {
  const same = new Set((links?.same || []).map(([a, b]) => pairKey(a, b)));
  const different = (links?.different || []).filter((pair) => pair?.length === 2);
  const apart = new Set(different.map(([a, b]) => pairKey(a, b)));
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const relative = new Map();
  const keysByRoot = new Map();
  nodes.forEach((node) => {
    if (ROOTS.has(node.type)) { if (!keysByRoot.has(node.id)) keysByRoot.set(node.id, new Set()); return; }
    const key = relativeKey(node, byId);
    if (!key) return;
    relative.set(node.id, key);
    const root = rootOf(node);
    if (!root || !byId.has(root)) return;
    if (!keysByRoot.has(root)) keysByRoot.set(root, new Set());
    keysByRoot.get(root).add(key);
  });

  // Union roots of one type whose objects mostly match.
  const parent = new Map([...keysByRoot.keys()].map((id) => [id, id]));
  const find = (id) => { while (parent.get(id) !== id) { parent.set(id, parent.get(parent.get(id))); id = parent.get(id); } return id; };
  const roots = [...keysByRoot.keys()].filter((id) => byId.has(id)).sort((a, b) => byName(byId.get(a), byId.get(b)));
  // Joining two families is refused when it would put a pair the user called different into one family.
  const join = (a, b) => {
    const ra = find(a), rb = find(b);
    if (ra === rb) return;
    if (different.some(([x, y]) => parent.has(x) && parent.has(y) && ((find(x) === ra && find(y) === rb) || (find(x) === rb && find(y) === ra)))) return;
    parent.set(rb, ra);
  };
  // The user's "same" pairs first, so a later automatic match cannot block them.
  roots.forEach((a, index) => roots.slice(index + 1).forEach((b) => {
    if (same.has(pairKey(a, b)) && byId.get(a).type === byId.get(b).type) join(a, b);
  }));
  roots.forEach((a, index) => roots.slice(index + 1).forEach((b) => {
    if (byId.get(a).type !== byId.get(b).type || apart.has(pairKey(a, b)) || same.has(pairKey(a, b))) return;
    // Matching structure alone is not enough: the names must agree apart from a version marker.
    if (versionStem(objectName(byId.get(a))) !== versionStem(objectName(byId.get(b)))) return;
    const left = keysByRoot.get(a), right = keysByRoot.get(b);
    const smaller = Math.min(left.size, right.size);
    if (!smaller) return;
    let shared = 0;
    const [few, many] = left.size <= right.size ? [left, right] : [right, left];
    few.forEach((key) => { if (many.has(key)) shared += 1; });
    if (shared / smaller >= FAMILY_OVERLAP) join(a, b);
  }));

  const families = new Map();
  roots.forEach((id) => { const family = find(id); if (!families.has(family)) families.set(family, []); families.get(family).push(byId.get(id)); });
  const familyOf = new Map();
  families.forEach((members, family) => members.forEach((member) => familyOf.set(member.id, `family:${family}`)));

  const keyOf = new Map();
  nodes.forEach((node) => {
    if (ROOTS.has(node.type)) { keyOf.set(node.id, familyOf.get(node.id) || node.id); return; }
    const family = familyOf.get(rootOf(node));
    const key = relative.get(node.id);
    keyOf.set(node.id, family && key ? `${family}|${key}` : node.id);
  });
  return { keyOf, familyOf, families };
}

/**
 * Fold the versions of each object into one node. Links are re-pointed to the folded nodes and de-duplicated.
 * The folded node keeps the id of its first version, so selecting it opens that version's details.
 * @returns {{ nodes, edges, membersOf: Map<id, node[]>, grouped: boolean }}
 */
export function groupVersions(nodes, edges, links = null) {
  const { keyOf, familyOf, families } = versionFamilies(nodes, links);
  if (![...families.values()].some((members) => members.length > 1)) {
    return { nodes, edges, membersOf: new Map(nodes.map((node) => [node.id, [node]])), grouped: false };
  }
  const familyRank = new Map();
  families.forEach((members) => members.forEach((member, index) => familyRank.set(member.id, index)));
  const familySize = (node) => { const family = familyOf.get(rootOf(node)); return family ? families.get(family.slice("family:".length))?.length || 1 : 1; };
  const rank = (node) => familyRank.get(rootOf(node)) ?? 0;

  const buckets = new Map();
  nodes.forEach((node) => { const key = keyOf.get(node.id); if (!buckets.has(key)) buckets.set(key, []); buckets.get(key).push(node); });
  const representative = new Map();
  const membersOf = new Map();
  const merged = [];
  buckets.forEach((members) => {
    members.sort((a, b) => rank(a) - rank(b) || byName(a, b));
    const first = members[0];
    const size = familySize(first);
    members.forEach((member) => representative.set(member.id, first.id));
    membersOf.set(first.id, members);
    if (size < 2) { merged.push(first); return; }
    const hashes = new Set(members.map((member) => member.definition_hash || member.source_hash).filter(Boolean));
    const versions = ROOTS.has(first.type) ? members : members.map((member) => ({ ...member, versionOf: rootOf(member) }));
    const folded = { ...first, versions, versionCount: members.length, familySize: size, differs: hashes.size > 1 };
    // A folded model or report is not its first version: it carries the shared name and says how many it stands for.
    if (ROOTS.has(first.type) && members.length > 1) {
      folded.versionTitle = versionTitle(members.map((member) => objectName(member)));
      folded.name = `${folded.versionTitle} · ${members.length} versions`;
      delete folded.display_name;
    }
    merged.push(folded);
  });

  // Owner fields point at folded owners too, so an object only in v2 sits under the folded model.
  const OWNER_FIELDS = ["model_id", "report_id", "table_id", "page_id", "parent_id"];
  const repointed = merged.map((node) => {
    const changes = {};
    OWNER_FIELDS.forEach((field) => { const target = node[field] && representative.get(node[field]); if (target && target !== node[field]) changes[field] = target; });
    return Object.keys(changes).length ? { ...node, ...changes } : node;
  });

  const seen = new Set();
  const groupedEdges = [];
  edges.forEach((edge) => {
    const from = representative.get(edge.from_id) || edge.from_id, to = representative.get(edge.to_id) || edge.to_id;
    if (from === to) return;
    const key = `${edge.type}\u0000${from}\u0000${to}`;
    if (seen.has(key)) return;
    seen.add(key);
    groupedEdges.push(from === edge.from_id && to === edge.to_id ? edge : { ...edge, id: `${edge.id}~v`, from_id: from, to_id: to });
  });
  return { nodes: repointed, edges: groupedEdges, membersOf, grouped: true };
}

/** One line on an object's versions for titles and labels, or "" when it has no versions. */
export function versionNote(node, byId) {
  if (!node?.familySize || node.familySize < 2) return "";
  const names = (node.versions || []).map((member) => objectName(byId?.get(member.versionOf) || { name: member.versionOf || objectName(member) }));
  if (node.versionCount >= node.familySize) return `In all ${node.familySize} versions${node.differs ? ", with differences" : ", identical"}`;
  return `In ${node.versionCount} of ${node.familySize} versions${names.length ? `: ${names.join(", ")}` : ""}`;
}

/** `links` with one more statement about a pair; the opposite statement about that pair is dropped. */
export function withVersionLink(links, kind, a, b) {
  const drop = (pairs) => (pairs || []).filter(([x, y]) => pairKey(x, y) !== pairKey(a, b));
  const next = { same: drop(links?.same), different: drop(links?.different) };
  if (kind === "same" || kind === "different") next[kind] = [...next[kind], [a, b].sort()];
  return next;
}
