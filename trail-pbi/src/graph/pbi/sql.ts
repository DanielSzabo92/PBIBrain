/**
 * SQL (`.sql` and embedded `Value.NativeQuery` SQL) extractor for Trail-PBI.
 *
 * Extracts:
 *  - `CREATE [OR ALTER] VIEW|TABLE|PROCEDURE|FUNCTION [schema.]name` definitions
 *  - `FROM [db.][schema.]table` and `JOIN [db.][schema.]table` source dependencies
 *    (filtering out local `WITH cte AS (...)` names)
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

function cleanSqlIdentifier(raw: string): string {
  return raw
    .split(".")
    .map((part) => part.trim().replace(/^\[|\]$|^"|"$|^`|`$/g, ""))
    .filter(Boolean)
    .pop() || raw.trim();
}

function cleanSqlQualifiedName(raw: string): string {
  return raw
    .split(".")
    .map((part) => part.trim().replace(/^\[|\]$|^"|"$|^`|`$/g, ""))
    .filter(Boolean)
    .join(".");
}

export function extractSqlDependencies(callerId: string, sql: string): UnresolvedCall[] {
  const cleaned = sql
    .replace(/--[^\n]*/g, " ")
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/'(?:''|[^'])*'/g, "''");

  const ctes = new Set<string>();
  const cteRe = /\b(?:WITH|,)\s*([A-Za-z_\[][A-Za-z0-9_\]]*)\s+AS\s*\(/gi;
  let m: RegExpExecArray | null;
  while ((m = cteRe.exec(cleaned)) !== null) {
    ctes.add(cleanSqlIdentifier(m[1]).toLowerCase());
  }

  const calls: UnresolvedCall[] = [];
  const seen = new Set<string>();
  const fromJoinRe = /\b(?:FROM|JOIN|EXEC|EXECUTE)\s+((?:\[[^\]]+\]|"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*)(?:\s*\.\s*(?:\[[^\]]+\]|"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*)){0,2})/gi;
  const sqlKeywords = new Set(["select", "where", "group", "order", "having", "values", "set", " lateral", "unnest", "openjson"]);

  while ((m = fromJoinRe.exec(cleaned)) !== null) {
    const rawTarget = m[1].trim();
    const tableName = cleanSqlIdentifier(rawTarget);
    if (!tableName || sqlKeywords.has(tableName.toLowerCase()) || ctes.has(tableName.toLowerCase())) {
      continue;
    }
    const key = `sources_from:${tableName.toLowerCase()}`;
    if (!seen.has(key)) {
      seen.add(key);
      calls.push({
        caller: callerId,
        callee: tableName,
        kind: "sources_from",
      });
    }
  }
  return calls;
}

export function extractSqlFile(relPath: string, source: string): ExtractedFile {
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

  const createRe = /^\s*CREATE\s+(?:OR\s+ALTER\s+|OR\s+REPLACE\s+)?(VIEW|TABLE|PROC|PROCEDURE|FUNCTION)\s+((?:\[[^\]]+\]|"[^"]+"|[A-Za-z_][A-Za-z0-9_]*)(?:\s*\.\s*(?:\[[^\]]+\]|"[^"]+"|[A-Za-z_][A-Za-z0-9_]*))*)/i;

  interface SqlDef {
    lineIdx: number;
    objKind: "table" | "function";
    rawName: string;
    qualName: string;
  }

  const defs: SqlDef[] = [];
  for (let i = 0; i < lines.length; i++) {
    const m = createRe.exec(lines[i]);
    if (!m) continue;
    const kw = m[1].toUpperCase();
    const objKind = kw === "VIEW" || kw === "TABLE" ? "table" : "function";
    const rawName = m[2].trim();
    const qualName = cleanSqlQualifiedName(rawName);
    defs.push({ lineIdx: i, objKind, rawName, qualName });
  }

  if (defs.length === 0) {
    const scriptName = (relPath.split("/").pop() || "query").replace(/\.sql$/i, "");
    const scriptId = `${relPath}#${scriptName}`;
    nodes.push({
      id: scriptId,
      name: scriptName,
      kind: "table",
      path: relPath,
      span: `L1-L${Math.max(1, lines.length)}`,
      signature: `sql ${scriptName}`,
      exported: true,
      origin: "ast",
      body_hash: sha256(source),
      body_text: normalizeBody(source),
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: relPath, target: scriptId, relation: "contains", confidence: "extracted" });
    unresolvedCalls.push(...extractSqlDependencies(scriptId, source));
    return { path: relPath, language: "sql", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  for (let idx = 0; idx < defs.length; idx++) {
    const cur = defs[idx];
    const endLineIdx = idx + 1 < defs.length ? defs[idx + 1].lineIdx - 1 : lines.length - 1;
    let trimmedEnd = endLineIdx;
    while (trimmedEnd > cur.lineIdx && !lines[trimmedEnd].trim()) {
      trimmedEnd--;
    }
    const body = lines.slice(cur.lineIdx, trimmedEnd + 1).join("\n");
    const nodeId = `${relPath}#${cur.qualName}`;
    nodes.push({
      id: nodeId,
      name: cur.qualName,
      kind: cur.objKind,
      path: relPath,
      span: `L${cur.lineIdx + 1}-L${trimmedEnd + 1}`,
      signature: lines[cur.lineIdx].trim().slice(0, 140),
      exported: true,
      origin: "ast",
      body_hash: sha256(body),
      body_text: normalizeBody(body),
      pbi_meta: { qualified_sql_name: cur.rawName },
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: relPath, target: nodeId, relation: "contains", confidence: "extracted" });
    unresolvedCalls.push(...extractSqlDependencies(nodeId, body));
  }

  return { path: relPath, language: "sql", nodes, edges, unresolvedCalls, unresolvedImports: [] };
}
