/**
 * DAX formula and standalone `.dax` script extractor for Trail-PBI.
 *
 * Extracts:
 *  - Table-qualified column/measure references: `'Sales Order'[Net Amount]`, `Sales[Qty]`
 *  - Unqualified measure references: `[Total Sales]`
 *  - Local `VAR <Name> = ...` declarations (excluded from external unresolved references)
 *  - Filter-context modifiers (`CALCULATE`, `ALL`, `REMOVEFILTERS`, `ALLEXCEPT`, `ALLSELECTED`, `KEEPFILTERS`, `TREATAS`)
 *  - Relationship modifiers (`USERELATIONSHIP`, `CROSSFILTER`)
 *  - Standalone `.dax` `DEFINE MEASURE / COLUMN / TABLE / FUNCTION` blocks
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

/** Replace DAX comments (`//`, `--`, `/* ... *\/`) and string literals (`"..."`)
 * with spaces while preserving newlines so line offsets remain exact. */
export function stripDaxCommentsAndStrings(formula: string): string {
  let out = "";
  let i = 0;
  const n = formula.length;
  while (i < n) {
    const ch = formula[i];
    const next = i + 1 < n ? formula[i + 1] : "";
    // String literal "..." (with "" escape)
    if (ch === '"') {
      out += " ";
      i++;
      while (i < n) {
        if (formula[i] === '"') {
          if (i + 1 < n && formula[i + 1] === '"') {
            out += "  ";
            i += 2;
            continue;
          }
          out += " ";
          i++;
          break;
        }
        out += formula[i] === "\n" ? "\n" : " ";
        i++;
      }
      continue;
    }
    // Single-quoted table identifier '...' — keep intact!
    if (ch === "'") {
      out += ch;
      i++;
      while (i < n) {
        out += formula[i];
        if (formula[i] === "'") {
          if (i + 1 < n && formula[i + 1] === "'") {
            out += formula[i + 1];
            i += 2;
            continue;
          }
          i++;
          break;
        }
        i++;
      }
      continue;
    }
    // Line comment // or --
    if ((ch === "/" && next === "/") || (ch === "-" && next === "-")) {
      while (i < n && formula[i] !== "\n") {
        out += " ";
        i++;
      }
      continue;
    }
    // Block comment /* ... */
    if (ch === "/" && next === "*") {
      out += "  ";
      i += 2;
      while (i < n && !(formula[i] === "*" && i + 1 < n && formula[i + 1] === "/")) {
        out += formula[i] === "\n" ? "\n" : " ";
        i++;
      }
      if (i < n) {
        out += "  ";
        i += 2;
      }
      continue;
    }
    out += ch;
    i++;
  }
  return out;
}

export interface DaxDependencyResult {
  calls: UnresolvedCall[];
  nameofRefs: Array<{ table?: string; field: string }>;
}

const FILTER_MODIFIER_FUNCS = new Set([
  "ALL",
  "ALLEXCEPT",
  "ALLNOBLANKROW",
  "ALLSELECTED",
  "REMOVEFILTERS",
  "KEEPFILTERS",
  "TREATAS",
]);

/**
 * Extract DAX references from a formula expression owned by `callerId`.
 */
export function extractDaxDependencies(
  callerId: string,
  formula: string,
  defaultTableName?: string,
): DaxDependencyResult {
  const cleaned = stripDaxCommentsAndStrings(formula);
  const calls: UnresolvedCall[] = [];
  const nameofRefs: Array<{ table?: string; field: string }> = [];
  const seen = new Set<string>();

  // 1. Collect local VAR declarations so we don't emit them as external refs
  const localVars = new Set<string>();
  const varRe = /\bVAR\s+([A-Za-z_][A-Za-z0-9_]*)\s*=/gi;
  let m: RegExpExecArray | null;
  while ((m = varRe.exec(cleaned)) !== null) {
    localVars.add(m[1].toLowerCase());
  }

  // 2. Detect NAMEOF('Table'[Field]) for Field Parameters
  const nameofRe = /\bNAMEOF\s*\(\s*(?:'((?:[^']|'')+)'|([A-Za-z_][A-Za-z0-9_.]*))?\s*\[([^\[\]]+)\]\s*\)/gi;
  while ((m = nameofRe.exec(cleaned)) !== null) {
    const rawTable = m[1] ? m[1].replace(/''/g, "'") : m[2];
    const field = m[3].trim();
    nameofRefs.push({ table: rawTable || defaultTableName, field });
  }

  // 3. Detect USERELATIONSHIP(col1, col2) and CROSSFILTER(col1, col2, ...)
  const relModRe = /\b(USERELATIONSHIP|CROSSFILTER)\s*\(\s*(?:'((?:[^']|'')+)'|([A-Za-z_][A-Za-z0-9_.]*))\s*\[([^\[\]]+)\]\s*,\s*(?:'((?:[^']|'')+)'|([A-Za-z_][A-Za-z0-9_.]*))\s*\[([^\[\]]+)\]/gi;
  while ((m = relModRe.exec(cleaned)) !== null) {
    const fn = m[1].toUpperCase();
    const relType = fn === "USERELATIONSHIP" ? "activates_relationship" : "modifies_relationship";
    const t1 = (m[2] ? m[2].replace(/''/g, "'") : m[3]).trim();
    const c1 = m[4].trim();
    const t2 = (m[5] ? m[5].replace(/''/g, "'") : m[6]).trim();
    const c2 = m[7].trim();
    for (const [tbl, col] of [
      [t1, c1],
      [t2, c2],
    ]) {
      const key = `${relType}:${tbl}:${col}`;
      if (!seen.has(key)) {
        seen.add(key);
        calls.push({
          caller: callerId,
          callee: col,
          receiver: tbl,
          kind: relType,
        });
      }
    }
  }

  // 4. Detect filter-modifier functions: ALL('Table'[Col]), REMOVEFILTERS('Table'), etc.
  const filterFnRe = /\b(ALL|ALLEXCEPT|ALLNOBLANKROW|ALLSELECTED|REMOVEFILTERS|KEEPFILTERS|TREATAS)\s*\(\s*(?:'((?:[^']|'')+)'|([A-Za-z_][A-Za-z0-9_.]*))(?:\s*\[([^\[\]]+)\])?/gi;
  while ((m = filterFnRe.exec(cleaned)) !== null) {
    const tbl = (m[2] ? m[2].replace(/''/g, "'") : m[3] || "").trim();
    const col = m[4]?.trim();
    if (!tbl || localVars.has(tbl.toLowerCase()) || FILTER_MODIFIER_FUNCS.has(tbl.toUpperCase())) {
      continue;
    }
    const targetName = col || tbl;
    const receiver = col ? tbl : undefined;
    const key = `modifies_filter:${receiver ?? ""}:${targetName}`;
    if (!seen.has(key)) {
      seen.add(key);
      calls.push({
        caller: callerId,
        callee: targetName,
        receiver,
        kind: "modifies_filter",
      });
    }
  }

  // 5. General 'Table'[Field], Table[Field], and unqualified [Measure] references
  const refRe = /(?:'((?:[^']|'')+)'|([A-Za-z_][A-Za-z0-9_.]*))?\s*\[([^\[\]]+)\]/g;
  while ((m = refRe.exec(cleaned)) !== null) {
    const rawQuotedTable = m[1] ? m[1].replace(/''/g, "'").trim() : undefined;
    const rawUnquotedTable = m[2] ? m[2].trim() : undefined;
    const tableRef = rawQuotedTable || rawUnquotedTable;
    const fieldName = m[3].trim();
    if (!fieldName) continue;
    if (!tableRef && localVars.has(fieldName.toLowerCase())) continue;

    // Qualified 'Table'[Field] or Table[Field]
    if (tableRef) {
      if (localVars.has(tableRef.toLowerCase())) continue;
      const key = `depends_on:${tableRef}:${fieldName}`;
      if (!seen.has(key)) {
        seen.add(key);
        calls.push({
          caller: callerId,
          callee: fieldName,
          receiver: tableRef,
          kind: "depends_on",
        });
      }
    } else {
      // Unqualified [Measure] (or column on defaultTableName if calculated column)
      const key = `depends_on::${fieldName}`;
      if (!seen.has(key)) {
        seen.add(key);
        calls.push({
          caller: callerId,
          callee: fieldName,
          receiver: undefined,
          kind: "depends_on",
        });
      }
    }
  }

  return { calls, nameofRefs };
}

/**
 * Extract a standalone `.dax` file (`DEFINE MEASURE`, `DEFINE COLUMN`, `DEFINE TABLE`, `DEFINE FUNCTION`, or query).
 */
export function extractDaxFile(relPath: string, source: string): ExtractedFile {
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
  const defineHeaderRe = /^\s*(?:DEFINE\s+)?(MEASURE|COLUMN|TABLE|FUNCTION)\s+(?:'((?:[^']|'')+)'|([A-Za-z_][A-Za-z0-9_.]*))?\s*(?:\[([^\[\]]+)\]|([A-Za-z_][A-Za-z0-9_.]*))\s*=\s*(.*)$/i;

  interface BlockStart {
    lineIdx: number;
    kind: "measure" | "column" | "table" | "user_defined_function";
    table?: string;
    name: string;
    rhs: string;
  }

  const starts: BlockStart[] = [];
  for (let i = 0; i < lines.length; i++) {
    const m = defineHeaderRe.exec(lines[i]);
    if (!m) continue;
    const kw = m[1].toUpperCase();
    const kind =
      kw === "MEASURE"
        ? "measure"
        : kw === "COLUMN"
          ? "column"
          : kw === "TABLE"
            ? "table"
            : "user_defined_function";
    const table = (m[2] ? m[2].replace(/''/g, "'") : m[3])?.trim();
    const name = (m[4] || m[5] || "").trim();
    if (!name) continue;
    starts.push({ lineIdx: i, kind, table, name, rhs: m[6] || "" });
  }

  if (starts.length === 0) {
    // Treat the whole .dax file as a DAX query block
    const queryId = `${relPath}#Query`;
    const queryNode: NodeV1 = {
      id: queryId,
      name: (relPath.split("/").pop() || "Query").replace(/\.dax$/i, ""),
      kind: "measure",
      path: relPath,
      span: `L1-L${Math.max(1, lines.length)}`,
      signature: normalizeBody(source).slice(0, 140),
      exported: true,
      origin: "ast",
      body_hash: sha256(source),
      body_text: normalizeBody(source),
      summary_state: "pending",
      summary: null,
      crux: null,
    };
    nodes.push(queryNode);
    edges.push({ source: relPath, target: queryId, relation: "contains", confidence: "extracted" });
    const deps = extractDaxDependencies(queryId, source);
    unresolvedCalls.push(...deps.calls);
    return { path: relPath, language: "dax", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  for (let idx = 0; idx < starts.length; idx++) {
    const cur = starts[idx];
    const endLineIdx = idx + 1 < starts.length ? starts[idx + 1].lineIdx - 1 : lines.length - 1;
    let trimmedEnd = endLineIdx;
    while (trimmedEnd > cur.lineIdx && !lines[trimmedEnd].trim()) {
      trimmedEnd--;
    }
    const blockText = lines.slice(cur.lineIdx, trimmedEnd + 1).join("\n");
    const exprText = [cur.rhs, ...lines.slice(cur.lineIdx + 1, trimmedEnd + 1)].join("\n").trim();
    const qualName = cur.table ? `${cur.table}.${cur.name}` : cur.name;
    const nodeId = `${relPath}#${qualName}`;
    const node: NodeV1 = {
      id: nodeId,
      name: cur.name,
      kind: cur.kind,
      owner: cur.table,
      path: relPath,
      span: `L${cur.lineIdx + 1}-L${trimmedEnd + 1}`,
      signature: `${cur.kind} ${qualName} = ${normalizeBody(exprText).slice(0, 120)}`,
      exported: true,
      origin: "ast",
      body_hash: sha256(blockText),
      body_text: normalizeBody(exprText),
      pbi_meta: {
        table: cur.table,
        expression: exprText,
        expression_language: "DAX",
      },
      summary_state: "pending",
      summary: null,
      crux: null,
    };
    nodes.push(node);
    edges.push({ source: relPath, target: nodeId, relation: "contains", confidence: "extracted" });
    const deps = extractDaxDependencies(nodeId, exprText, cur.table);
    unresolvedCalls.push(...deps.calls);
  }

  return { path: relPath, language: "dax", nodes, edges, unresolvedCalls, unresolvedImports: [] };
}
