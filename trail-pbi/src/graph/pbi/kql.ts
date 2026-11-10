/**
 * KQL (`.kql` and embedded Kusto queries) extractor for Trail-PBI.
 *
 * Extracts:
 *  - `.create-or-alter function|table` and `let <Name> = ...` definitions
 *  - Tabular pipe sources (`TableName | where ...`, `join (OtherTable)`, `union OtherTable`)
 */
import { createHash } from "node:crypto";
import type { ExtractedFile, UnresolvedCall } from "../extract.js";
import type { EdgeV1, NodeV1 } from "../types.js";

function sha256(text: string): string {
  return "sha256:" + createHash("sha256").update(text).digest("hex");
}

function normalizeBody(text: string): string {
  return text.replace(/\s+/g, " ").trim().slice(0, 800);
}

const KQL_KEYWORDS = new Set([
  "let",
  "set",
  "alias",
  "declare",
  "pattern",
  "restrict",
  "access",
  "where",
  "project",
  "extend",
  "summarize",
  "join",
  "union",
  "sort",
  "order",
  "top",
  "take",
  "limit",
  "count",
  "distinct",
  "mv-expand",
  "evaluate",
  "parse",
  "render",
  "print",
  "datatable",
  "range",
  "externaldata",
  "find",
  "search",
]);

export function extractKqlDependencies(callerId: string, kql: string): UnresolvedCall[] {
  const cleaned = kql.replace(/\/\/[^\n]*/g, " ");
  const localLets = new Set<string>();
  const letRe = /\blet\s+([A-Za-z_][A-Za-z0-9_]*)\s*=/gi;
  let m: RegExpExecArray | null;
  while ((m = letRe.exec(cleaned)) !== null) {
    localLets.add(m[1].toLowerCase());
  }

  const calls: UnresolvedCall[] = [];
  const seen = new Set<string>();

  // Tabular pipeline starts: `TableName | ...`
  const pipeStartRe = /(?:^|[\n;])\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\r?\n\s*)?\|/g;
  while ((m = pipeStartRe.exec(cleaned)) !== null) {
    const name = m[1].trim();
    if (KQL_KEYWORDS.has(name.toLowerCase()) || localLets.has(name.toLowerCase())) continue;
    const key = `sources_from:${name.toLowerCase()}`;
    if (!seen.has(key)) {
      seen.add(key);
      calls.push({ caller: callerId, callee: name, kind: "sources_from" });
    }
  }

  // `join ... (TableName)` or `union TableName`
  const joinUnionRe = /\b(?:join(?:\s+kind\s*=\s*[A-Za-z]+)?\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)|union\s+([A-Za-z_][A-Za-z0-9_]*))/gi;
  while ((m = joinUnionRe.exec(cleaned)) !== null) {
    const name = (m[1] || m[2] || "").trim();
    if (!name || KQL_KEYWORDS.has(name.toLowerCase()) || localLets.has(name.toLowerCase())) continue;
    const key = `sources_from:${name.toLowerCase()}`;
    if (!seen.has(key)) {
      seen.add(key);
      calls.push({ caller: callerId, callee: name, kind: "sources_from" });
    }
  }

  return calls;
}

export function extractKqlFile(relPath: string, source: string): ExtractedFile {
  const lines = source.split(/\r?\n/);
  const fileNode: NodeV1 = {
    id: relPath,
    name: relPath.split("/").pop() || relPath,
    kind: "file",
    path: relPath,
    span: `L1-L${Math.max(1, lines.length)}`,
    signature: null,
    exported: true,
    origin: "ast",
    body_hash: sha256(source),
    chars: Buffer.byteLength(source, "utf8"),
    summary_state: "pending",
    summary: null,
    crux: null,
  };

  const nodes: NodeV1[] = [fileNode];
  const edges: EdgeV1[] = [];
  const unresolvedCalls: UnresolvedCall[] = [];

  const createRe = /^\s*\.create(?:-or-alter)?\s+(function|table)\s+(?:with\s*\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)/i;
  const defs: Array<{ lineIdx: number; kind: "table" | "function"; name: string }> = [];

  for (let i = 0; i < lines.length; i++) {
    const m = createRe.exec(lines[i]);
    if (!m) continue;
    defs.push({
      lineIdx: i,
      kind: m[1].toLowerCase() === "table" ? "table" : "function",
      name: m[2].trim(),
    });
  }

  if (defs.length === 0) {
    const queryName = (relPath.split("/").pop() || "kql_query").replace(/\.kql$/i, "");
    const queryId = `${relPath}#${queryName}`;
    nodes.push({
      id: queryId,
      name: queryName,
      kind: "function",
      path: relPath,
      span: `L1-L${Math.max(1, lines.length)}`,
      signature: `kql ${queryName}`,
      exported: true,
      origin: "ast",
      body_hash: sha256(source),
      body_text: normalizeBody(source),
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: relPath, target: queryId, relation: "contains", confidence: "extracted" });
    unresolvedCalls.push(...extractKqlDependencies(queryId, source));
    return { path: relPath, language: "kql", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  for (let idx = 0; idx < defs.length; idx++) {
    const cur = defs[idx];
    const endLineIdx = idx + 1 < defs.length ? defs[idx + 1].lineIdx - 1 : lines.length - 1;
    const body = lines.slice(cur.lineIdx, endLineIdx + 1).join("\n");
    const nodeId = `${relPath}#${cur.name}`;
    nodes.push({
      id: nodeId,
      name: cur.name,
      kind: cur.kind,
      path: relPath,
      span: `L${cur.lineIdx + 1}-L${endLineIdx + 1}`,
      signature: lines[cur.lineIdx].trim().slice(0, 140),
      exported: true,
      origin: "ast",
      body_hash: sha256(body),
      body_text: normalizeBody(body),
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: relPath, target: nodeId, relation: "contains", confidence: "extracted" });
    unresolvedCalls.push(...extractKqlDependencies(nodeId, body));
  }

  return { path: relPath, language: "kql", nodes, edges, unresolvedCalls, unresolvedImports: [] };
}
