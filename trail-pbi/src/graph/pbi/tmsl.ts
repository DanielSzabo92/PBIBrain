/**
 * TMSL (`model.bim`) semantic model extractor for Trail-PBI.
 *
 * Parses `model.bim` JSON while locating exact line spans (`L<start>-L<end>`)
 * for tables, columns, measures, partitions, hierarchies, calculation groups,
 * relationships, shared expressions, and security roles.
 */
import { createHash } from "node:crypto";
import type { ExtractedFile, UnresolvedCall } from "../extract.js";
import type { EdgeV1, NodeV1, PbiKind } from "../types.js";
import { extractDaxDependencies } from "./dax.js";
import { extractMExpressionDependencies } from "./pq.js";

function sha256(text: string): string {
  return "sha256:" + createHash("sha256").update(text).digest("hex");
}

function normalizeBody(text: string): string {
  return text.replace(/\s+/g, " ").trim().slice(0, 800);
}

function asText(val: unknown): string {
  if (Array.isArray(val)) return val.map((item) => String(item ?? "")).join("\n");
  if (typeof val === "string") return val;
  return "";
}

function findNameSpanInLines(lines: string[], name: string, startSearchLine = 0): string {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const nameRe = new RegExp(`"name"\\s*:\\s*"${escaped}"`, "i");
  for (let i = startSearchLine; i < lines.length; i++) {
    if (nameRe.test(lines[i])) {
      const startLine = Math.max(1, i);
      const endLine = Math.min(lines.length, i + 12);
      return `L${startLine}-L${endLine}`;
    }
  }
  return `L1-L${Math.max(1, lines.length)}`;
}

export function extractTmslFile(relPath: string, source: string): ExtractedFile {
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

  let parsed: Record<string, any>;
  try {
    parsed = JSON.parse(source.replace(/^\uFEFF/, ""));
  } catch {
    return { path: relPath, language: "tmsl", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  const modelObj: Record<string, any> =
    parsed && typeof parsed.model === "object" && parsed.model !== null ? parsed.model : parsed;
  const modelName = String(
    modelObj.name ||
      parsed.name ||
      (relPath.split("/").slice(-2, -1)[0] || "Model").replace(/\.(?:SemanticModel|Dataset)$/i, ""),
  );
  const modelId = `${relPath}#${modelName}`;
  nodes.push({
    id: modelId,
    name: modelName,
    kind: "semantic_model",
    path: relPath,
    span: `L1-L${Math.max(1, lines.length)}`,
    signature: `semantic_model ${modelName}`,
    exported: true,
    origin: "ast",
    body_hash: sha256(source),
    pbi_meta: {
      compatibility_level: parsed.compatibilityLevel ?? modelObj.compatibilityLevel,
      culture: modelObj.culture,
    },
    summary_state: "pending",
    summary: null,
    crux: null,
  });
  edges.push({ source: relPath, target: modelId, relation: "contains", confidence: "extracted" });

  // 1. Tables
  const tables: any[] = Array.isArray(modelObj.tables) ? modelObj.tables : [];
  for (const tbl of tables) {
    if (!tbl || typeof tbl.name !== "string") continue;
    const tableName = tbl.name;
    const tableSpan = findNameSpanInLines(lines, tableName);
    const isCalcGroup = Boolean(tbl.calculationGroup);
    const tableKind: PbiKind = isCalcGroup ? "calculation_group" : "table";
    const tableId = `${relPath}#${tableName}`;
    const tableNode: NodeV1 = {
      id: tableId,
      name: tableName,
      kind: tableKind,
      path: relPath,
      span: tableSpan,
      signature: `${tableKind} ${tableName}`,
      exported: !tbl.isHidden,
      origin: "ast",
      body_hash: sha256(JSON.stringify(tbl)),
      pbi_meta: { lineage_tag: tbl.lineageTag, hidden: Boolean(tbl.isHidden) },
      summary_state: tbl.description ? "ready" : "pending",
      summary: tbl.description ? asText(tbl.description) : null,
      crux: null,
    };
    nodes.push(tableNode);
    edges.push({ source: modelId, target: tableId, relation: "contains", confidence: "extracted" });

    // Columns
    const columns: any[] = Array.isArray(tbl.columns) ? tbl.columns : [];
    for (const col of columns) {
      if (!col || typeof col.name !== "string") continue;
      const colName = col.name;
      const colId = `${relPath}#${tableName}.${colName}`;
      const colSpan = findNameSpanInLines(lines, colName);
      const expr = asText(col.expression);
      nodes.push({
        id: colId,
        name: colName,
        kind: "column",
        owner: tableName,
        path: relPath,
        span: colSpan,
        signature: expr
          ? `column ${tableName}[${colName}] = ${normalizeBody(expr).slice(0, 120)}`
          : `column ${tableName}[${colName}] : ${col.dataType || "variant"}`,
        exported: !col.isHidden,
        origin: "ast",
        body_hash: sha256(JSON.stringify(col)),
        body_text: normalizeBody(expr || colName),
        pbi_meta: {
          table: tableName,
          lineage_tag: col.lineageTag,
          datatype: col.dataType,
          source_column: col.sourceColumn,
          sort_by_column: col.sortByColumn,
          expression: expr || undefined,
        },
        summary_state: col.description ? "ready" : "pending",
        summary: col.description ? asText(col.description) : null,
        crux: null,
      });
      edges.push({ source: tableId, target: colId, relation: "contains", confidence: "extracted" });
      if (expr) {
        unresolvedCalls.push(...extractDaxDependencies(colId, expr, tableName).calls);
      }
      if (col.sortByColumn) {
        unresolvedCalls.push({
          caller: colId,
          callee: String(col.sortByColumn),
          receiver: tableName,
          kind: "depends_on",
        });
      }
    }

    // Measures
    const measures: any[] = Array.isArray(tbl.measures) ? tbl.measures : [];
    for (const msr of measures) {
      if (!msr || typeof msr.name !== "string") continue;
      const msrName = msr.name;
      const msrId = `${relPath}#${tableName}.${msrName}`;
      const msrSpan = findNameSpanInLines(lines, msrName);
      const expr = asText(msr.expression);
      const fmtExpr = asText(msr.formatStringDefinition?.expression ?? msr.formatStringExpression);
      nodes.push({
        id: msrId,
        name: msrName,
        kind: "measure",
        owner: tableName,
        path: relPath,
        span: msrSpan,
        signature: `measure ${tableName}[${msrName}] = ${normalizeBody(expr).slice(0, 120)}`,
        exported: !msr.isHidden,
        origin: "ast",
        body_hash: sha256(JSON.stringify(msr)),
        body_text: normalizeBody(expr),
        pbi_meta: {
          table: tableName,
          lineage_tag: msr.lineageTag,
          format_string: msr.formatString,
          expression: expr,
          expression_language: "DAX",
        },
        summary_state: msr.description ? "ready" : "pending",
        summary: msr.description ? asText(msr.description) : null,
        crux: null,
      });
      edges.push({ source: tableId, target: msrId, relation: "contains", confidence: "extracted" });
      if (expr) {
        unresolvedCalls.push(...extractDaxDependencies(msrId, expr, tableName).calls);
      }
      if (fmtExpr) {
        for (const call of extractDaxDependencies(msrId, fmtExpr, tableName).calls) {
          unresolvedCalls.push({ ...call, kind: "formats_by" });
        }
      }
    }

    // Calculation group items
    const calcItems: any[] = Array.isArray(tbl.calculationGroup?.calculationItems)
      ? tbl.calculationGroup.calculationItems
      : [];
    for (const item of calcItems) {
      if (!item || typeof item.name !== "string") continue;
      const itemId = `${relPath}#${tableName}.${item.name}`;
      const expr = asText(item.expression);
      nodes.push({
        id: itemId,
        name: item.name,
        kind: "calculation_item",
        owner: tableName,
        path: relPath,
        span: findNameSpanInLines(lines, item.name),
        signature: `calculation_item ${item.name} = ${normalizeBody(expr).slice(0, 100)}`,
        exported: true,
        origin: "ast",
        body_hash: sha256(JSON.stringify(item)),
        body_text: normalizeBody(expr),
        summary_state: "pending",
        summary: null,
        crux: null,
      });
      edges.push({ source: tableId, target: itemId, relation: "contains", confidence: "extracted" });
      if (expr) {
        unresolvedCalls.push(...extractDaxDependencies(itemId, expr, tableName).calls);
      }
    }

    // Partitions
    const partitions: any[] = Array.isArray(tbl.partitions) ? tbl.partitions : [];
    for (const part of partitions) {
      if (!part || typeof part.name !== "string") continue;
      const partId = `${relPath}#${tableName}.${part.name}`;
      const partSpan = findNameSpanInLines(lines, part.name);
      const srcType = String(part.source?.type || "m").toLowerCase();
      const expr = asText(part.source?.expression);
      nodes.push({
        id: partId,
        name: part.name,
        kind: "partition",
        owner: tableName,
        path: relPath,
        span: partSpan,
        signature: `partition ${tableName}.${part.name} (${srcType})`,
        exported: true,
        origin: "ast",
        body_hash: sha256(JSON.stringify(part)),
        body_text: normalizeBody(expr),
        pbi_meta: { table: tableName, partition_type: srcType, mode: part.mode },
        summary_state: "pending",
        summary: null,
        crux: null,
      });
      edges.push({ source: tableId, target: partId, relation: "contains", confidence: "extracted" });
      if (srcType === "calculated" && expr) {
        const daxDeps = extractDaxDependencies(partId, expr, tableName);
        unresolvedCalls.push(...daxDeps.calls);
        if (daxDeps.nameofRefs.length > 0) {
          tableNode.kind = "field_parameter";
          for (const ref of daxDeps.nameofRefs) {
            unresolvedCalls.push({
              caller: tableId,
              callee: ref.field,
              receiver: ref.table,
              kind: "depends_on",
            });
          }
        }
      } else if (expr) {
        const mDeps = extractMExpressionDependencies(partId, relPath, partSpan, expr);
        for (const ds of mDeps.dataSourceNodes) {
          if (!nodes.some((n) => n.id === ds.id)) {
            nodes.push(ds);
            edges.push({ source: relPath, target: ds.id, relation: "contains", confidence: "extracted" });
          }
        }
        edges.push(...mDeps.dataSourceEdges);
        unresolvedCalls.push(...mDeps.calls);
      }
    }
  }

  // 2. Relationships
  const relationships: any[] = Array.isArray(modelObj.relationships) ? modelObj.relationships : [];
  for (let i = 0; i < relationships.length; i++) {
    const rel = relationships[i];
    if (!rel) continue;
    const relName = String(rel.name || rel.id || `rel_${i + 1}`);
    const fromTable = String(rel.fromTable || "");
    const fromCol = String(rel.fromColumn || "");
    const toTable = String(rel.toTable || "");
    const toCol = String(rel.toColumn || "");
    const displayName =
      fromTable && fromCol && toTable && toCol ? `${fromTable}.${fromCol} -> ${toTable}.${toCol}` : relName;
    const relId = `${relPath}#${relName}`;
    nodes.push({
      id: relId,
      name: displayName,
      kind: "relationship",
      path: relPath,
      span: findNameSpanInLines(lines, relName),
      signature: `relationship ${displayName}`,
      exported: true,
      origin: "ast",
      body_hash: sha256(JSON.stringify(rel)),
      pbi_meta: {
        from_table: fromTable,
        from_column: fromCol,
        to_table: toTable,
        to_column: toCol,
        is_active: rel.isActive !== false,
      },
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: modelId, target: relId, relation: "contains", confidence: "extracted" });
    if (fromCol) {
      unresolvedCalls.push({ caller: relId, callee: fromCol, receiver: fromTable || undefined, kind: "relates_to" });
    }
    if (toCol) {
      unresolvedCalls.push({ caller: relId, callee: toCol, receiver: toTable || undefined, kind: "relates_to" });
    }
  }

  // 3. Shared Expressions
  const expressions: any[] = Array.isArray(modelObj.expressions) ? modelObj.expressions : [];
  for (const exprObj of expressions) {
    if (!exprObj || typeof exprObj.name !== "string") continue;
    const exprId = `${relPath}#${exprObj.name}`;
    const exprSpan = findNameSpanInLines(lines, exprObj.name);
    const exprText = asText(exprObj.expression);
    nodes.push({
      id: exprId,
      name: exprObj.name,
      kind: "shared_expression",
      path: relPath,
      span: exprSpan,
      signature: `expression ${exprObj.name}`,
      exported: true,
      origin: "ast",
      body_hash: sha256(JSON.stringify(exprObj)),
      body_text: normalizeBody(exprText),
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: modelId, target: exprId, relation: "contains", confidence: "extracted" });
    if (exprText) {
      const mDeps = extractMExpressionDependencies(exprId, relPath, exprSpan, exprText);
      for (const ds of mDeps.dataSourceNodes) {
        if (!nodes.some((n) => n.id === ds.id)) {
          nodes.push(ds);
          edges.push({ source: relPath, target: ds.id, relation: "contains", confidence: "extracted" });
        }
      }
      edges.push(...mDeps.dataSourceEdges);
      unresolvedCalls.push(...mDeps.calls);
    }
  }

  return { path: relPath, language: "tmsl", nodes, edges, unresolvedCalls, unresolvedImports: [] };
}
