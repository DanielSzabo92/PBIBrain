/**
 * Power Query / M (`.pq`, `.m`, and embedded partition/shared M expressions) extractor for Trail-PBI.
 *
 * Extracts:
 *  - `section ...; shared <Name> = ...` definitions in `.pq`/`.m` files
 *  - Data source connector calls (`Sql.Database`, `Lakehouse.Contents`, `Fabric.Warehouse`,
 *    `Kusto.Contents`, `AzureStorage.DataLake`, `OneLake.Contents`, `SharePoint.Files`,
 *    `Excel.Workbook`, `Csv.Document`, `Web.Contents`, `OData.Feed`, `Snowflake.Databases`,
 *    `Databricks.Contents`, `PostgreSQL.Database`, `Oracle.Database`) -> `data_source` nodes + `sources_from` edges
 *  - `Value.NativeQuery(source, "SELECT ...")` -> delegates embedded SQL/KQL to `extractSqlDependencies` / `extractKqlDependencies`
 *  - Shared expression / query references (`#"Other Query"`, `OtherQuery`) -> `depends_on` / `sources_from` unresolved calls
 */
import { createHash } from "node:crypto";
import type { ExtractedFile, UnresolvedCall } from "../extract.js";
import type { EdgeV1, NodeV1 } from "../types.js";
import { extractKqlDependencies } from "./kql.js";
import { extractSqlDependencies } from "./sql.js";

function sha256(text: string): string {
  return "sha256:" + createHash("sha256").update(text).digest("hex");
}

function normalizeBody(text: string): string {
  return text.replace(/\s+/g, " ").trim().slice(0, 800);
}

const M_CONNECTORS = new Map<string, string>([
  ["sql.database", "SQL Server"],
  ["sql.databases", "SQL Server"],
  ["azurestorage.datalake", "Azure Data Lake"],
  ["azurestorage.blobs", "Azure Blob Storage"],
  ["onelake.contents", "Fabric OneLake"],
  ["lakehouse.contents", "Fabric Lakehouse"],
  ["fabric.warehouse", "Fabric Warehouse"],
  ["powerplatform.dataflows", "Power Platform Dataflows"],
  ["powerbi.dataflows", "Power BI Dataflows"],
  ["kusto.contents", "Azure Data Explorer (Kusto)"],
  ["sharepoint.files", "SharePoint"],
  ["sharepoint.tables", "SharePoint"],
  ["sharepoint.contents", "SharePoint"],
  ["excel.workbook", "Excel"],
  ["csv.document", "CSV"],
  ["json.document", "JSON"],
  ["parquet.document", "Parquet"],
  ["web.contents", "Web"],
  ["odata.feed", "OData"],
  ["snowflake.databases", "Snowflake"],
  ["databricks.contents", "Databricks"],
  ["databricks.catalogs", "Databricks"],
  ["postgresql.database", "PostgreSQL"],
  ["oracle.database", "Oracle"],
  ["analysisservices.database", "Analysis Services"],
  [" analysisservices.databases", "Analysis Services"],
]);

const M_BUILTIN_IGNORED = new Set([
  "let",
  "in",
  "each",
  "true",
  "false",
  "null",
  "if",
  "then",
  "else",
  "try",
  "otherwise",
  "error",
  "section",
  "shared",
  "type",
  "table",
  "record",
  "list",
  "value",
  "text",
  "number",
  "date",
  "datetime",
  "datetimezone",
  "duration",
  "logical",
  "binary",
  "splitter",
  "comparer",
  "replacer",
  "uri",
  "lines",
  "file",
  "folder",
]);

export interface MExtractionResult {
  dataSourceNodes: NodeV1[];
  dataSourceEdges: EdgeV1[];
  calls: UnresolvedCall[];
}

/**
 * Extract M data-source nodes, `sources_from` edges, `Value.NativeQuery` SQL/KQL dependencies,
 * and shared-expression references from an M expression.
 */
export function extractMExpressionDependencies(
  callerId: string,
  relPath: string,
  span: string,
  mExpression: string,
): MExtractionResult {
  const dataSourceNodes: NodeV1[] = [];
  const dataSourceEdges: EdgeV1[] = [];
  const calls: UnresolvedCall[] = [];
  const seenSources = new Set<string>();
  const seenCalls = new Set<string>();

  // 1. Collect local step names in `let Step = ... in ...` so we don't emit them as external shared expressions
  const localSteps = new Set<string>();
  const stepRe = /(?:^|[,;\n])\s*(?:#"([^"]+)"|([A-Za-z_][A-Za-z0-9_.]*))\s*=/g;
  let m: RegExpExecArray | null;
  while ((m = stepRe.exec(mExpression)) !== null) {
    const stepName = (m[1] || m[2] || "").trim();
    if (stepName) localSteps.add(stepName.toLowerCase());
  }

  // 2. Detect connector invocations: `Sql.Database("server", "db")`, `Lakehouse.Contents(...)`, etc.
  const connectorRe = /\b([A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*)\s*\(([^()]*)\)/g;
  while ((m = connectorRe.exec(mExpression)) !== null) {
    const fnName = m[1].trim();
    const connectorKind = M_CONNECTORS.get(fnName.toLowerCase());
    if (!connectorKind) continue;
    const argsRaw = m[2].trim();
    const stringArgs: string[] = [];
    const strArgRe = /"((?:[^"]|"")*)"/g;
    let sm: RegExpExecArray | null;
    while ((sm = strArgRe.exec(argsRaw)) !== null) {
      stringArgs.push(sm[1].replace(/""/g, '"'));
    }
    const targetLabel = stringArgs.length > 0 ? `${fnName}(${stringArgs.slice(0, 2).join(", ")})` : fnName;
    const dsId = `${relPath}#datasource:${targetLabel}`;
    if (!seenSources.has(dsId)) {
      seenSources.add(dsId);
      dataSourceNodes.push({
        id: dsId,
        name: targetLabel,
        kind: "data_source",
        path: relPath,
        span,
        signature: `${connectorKind}: ${targetLabel}`,
        exported: true,
        origin: "ast",
        body_hash: sha256(targetLabel),
        pbi_meta: {
          connector: fnName,
          connector_kind: connectorKind,
          endpoints: stringArgs,
        },
        summary_state: "pending",
        summary: null,
        crux: null,
      });
    }
    dataSourceEdges.push({
      source: callerId,
      target: dsId,
      relation: "sources_from",
      confidence: "extracted",
    });
  }

  // 3. Detect `Value.NativeQuery(target, "SELECT ...")` and delegate embedded SQL / KQL
  const nativeQueryRe = /\bValue\.NativeQuery\s*\(\s*[^,]+,\s*"((?:[^"]|"")*)"/gi;
  while ((m = nativeQueryRe.exec(mExpression)) !== null) {
    const rawQuery = m[1].replace(/""/g, '"').replace(/#(lf)/gi, "\n").replace(/#(cr)/gi, "\r").replace(/#(tab)/gi, "\t");
    for (const sqlCall of extractSqlDependencies(callerId, rawQuery)) {
      const key = `${sqlCall.kind}:${sqlCall.callee.toLowerCase()}`;
      if (!seenCalls.has(key)) {
        seenCalls.add(key);
        calls.push(sqlCall);
      }
    }
    for (const kqlCall of extractKqlDependencies(callerId, rawQuery)) {
      const key = `${kqlCall.kind}:${kqlCall.callee.toLowerCase()}`;
      if (!seenCalls.has(key)) {
        seenCalls.add(key);
        calls.push(kqlCall);
      }
    }
  }

  // 4. Detect `[Schema="...", Item="..."]` or `[Name="..."]` navigation steps
  const navItemRe = /\[\s*(?:Schema\s*=\s*"([^"]+)"\s*,\s*)?(?:Item|Name)\s*=\s*"([^"]+)"\s*\]/gi;
  while ((m = navItemRe.exec(mExpression)) !== null) {
    const itemName = m[2].trim();
    if (!itemName || localSteps.has(itemName.toLowerCase())) continue;
    const key = `sources_from:${itemName.toLowerCase()}`;
    if (!seenCalls.has(key)) {
      seenCalls.add(key);
      calls.push({
        caller: callerId,
        callee: itemName,
        receiver: m[1]?.trim(),
        kind: "sources_from",
      });
    }
  }

  // 5. Detect quoted identifier references `#"Shared Query"` and bare identifier references to shared expressions
  const quotedRefRe = /#"([^"]+)"/g;
  while ((m = quotedRefRe.exec(mExpression)) !== null) {
    const refName = m[1].trim();
    if (!refName || localSteps.has(refName.toLowerCase())) continue;
    const key = `depends_on:${refName.toLowerCase()}`;
    if (!seenCalls.has(key)) {
      seenCalls.add(key);
      calls.push({
        caller: callerId,
        callee: refName,
        kind: "depends_on",
      });
    }
  }

  // Strip strings and comments before scanning bare identifiers
  const stripped = mExpression
    .replace(/#"[^"]*"/g, " ")
    .replace(/"(?:[^"]|"")*"/g, " ")
    .replace(/\/\/[^\n]*/g, " ")
    .replace(/\/\*[\s\S]*?\*\//g, " ");
  const bareIdRe = /\b([A-Za-z_][A-Za-z0-9_]*)\b/g;
  while ((m = bareIdRe.exec(stripped)) !== null) {
    const token = m[1];
    const lower = token.toLowerCase();
    if (localSteps.has(lower) || M_BUILTIN_IGNORED.has(lower)) continue;
    // Skip namespace prefixes of `Namespace.Function`
    const after = stripped.slice(m.index + token.length);
    const before = m.index > 0 ? stripped[m.index - 1] : " ";
    if (after.startsWith(".") || before === ".") continue;
    const key = `depends_on:${lower}`;
    if (!seenCalls.has(key)) {
      seenCalls.add(key);
      calls.push({
        caller: callerId,
        callee: token,
        kind: "depends_on",
      });
    }
  }

  return { dataSourceNodes, dataSourceEdges, calls };
}

/**
 * Extract a standalone `.pq` or `.m` Power Query file.
 */
export function extractPqFile(relPath: string, source: string): ExtractedFile {
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

  const sharedRe = /^\s*shared\s+(?:#"([^"]+)"|([A-Za-z_][A-Za-z0-9_.]*))\s*=\s*(.*)$/i;
  const starts: Array<{ lineIdx: number; name: string }> = [];
  for (let i = 0; i < lines.length; i++) {
    const m = sharedRe.exec(lines[i]);
    if (!m) continue;
    starts.push({ lineIdx: i, name: (m[1] || m[2]).trim() });
  }

  if (starts.length === 0) {
    const exprName = (relPath.split("/").pop() || "Query").replace(/\.(?:pq|m)$/i, "");
    const exprId = `${relPath}#${exprName}`;
    const span = `L1-L${Math.max(1, lines.length)}`;
    nodes.push({
      id: exprId,
      name: exprName,
      kind: "shared_expression",
      path: relPath,
      span,
      signature: `shared_expression ${exprName}`,
      exported: true,
      origin: "ast",
      body_hash: sha256(source),
      body_text: normalizeBody(source),
      pbi_meta: { expression_language: "M" },
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: relPath, target: exprId, relation: "contains", confidence: "extracted" });
    const res = extractMExpressionDependencies(exprId, relPath, span, source);
    for (const ds of res.dataSourceNodes) {
      nodes.push(ds);
      edges.push({ source: relPath, target: ds.id, relation: "contains", confidence: "extracted" });
    }
    edges.push(...res.dataSourceEdges);
    unresolvedCalls.push(...res.calls);
    return { path: relPath, language: "pq", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  for (let idx = 0; idx < starts.length; idx++) {
    const cur = starts[idx];
    const endLineIdx = idx + 1 < starts.length ? starts[idx + 1].lineIdx - 1 : lines.length - 1;
    let trimmedEnd = endLineIdx;
    while (trimmedEnd > cur.lineIdx && !lines[trimmedEnd].trim()) {
      trimmedEnd--;
    }
    const body = lines.slice(cur.lineIdx, trimmedEnd + 1).join("\n");
    const span = `L${cur.lineIdx + 1}-L${trimmedEnd + 1}`;
    const nodeId = `${relPath}#${cur.name}`;
    nodes.push({
      id: nodeId,
      name: cur.name,
      kind: "shared_expression",
      path: relPath,
      span,
      signature: `shared ${cur.name}`,
      exported: true,
      origin: "ast",
      body_hash: sha256(body),
      body_text: normalizeBody(body),
      pbi_meta: { expression_language: "M" },
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: relPath, target: nodeId, relation: "contains", confidence: "extracted" });
    const res = extractMExpressionDependencies(nodeId, relPath, span, body);
    for (const ds of res.dataSourceNodes) {
      if (!nodes.some((n) => n.id === ds.id)) {
        nodes.push(ds);
        edges.push({ source: relPath, target: ds.id, relation: "contains", confidence: "extracted" });
      }
    }
    edges.push(...res.dataSourceEdges);
    unresolvedCalls.push(...res.calls);
  }

  return { path: relPath, language: "pq", nodes, edges, unresolvedCalls, unresolvedImports: [] };
}
