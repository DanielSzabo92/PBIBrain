/**
 * TMDL (`.tmdl` — Tabular Model Definition Language) extractor for Trail-PBI.
 *
 * Extracts:
 *  - `model.tmdl` / `database.tmdl` -> `semantic_model`
 *  - `tables/*.tmdl` -> `table`, `column`, `measure`, `hierarchy`, `level`,
 *    `partition`, `calculation_group`, `calculation_item`, `field_parameter`
 *  - `relationships.tmdl` -> `relationship` + `relates_to` edges
 *  - `expressions.tmdl` -> `shared_expression` + M data source lineage
 *  - `roles/*.tmdl` -> `security_role`, `role_filter`, `ols_permission`
 *  - `functions.tmdl` -> `user_defined_function`
 *
 * Delegates embedded DAX formulas to `extractDaxDependencies` and embedded M
 * partition/shared expressions to `extractMExpressionDependencies` while
 * preserving exact container line spans (`L<start>-L<end>`).
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

function unquote(raw: string): string {
  const text = raw.trim();
  if (text.length >= 2 && text.startsWith("'") && text.endsWith("'")) {
    return text.slice(1, -1).replace(/''/g, "'");
  }
  if (text.length >= 2 && text.startsWith('"') && text.endsWith('"')) {
    return text.slice(1, -1).replace(/""/g, '"');
  }
  return text;
}

function indentOf(line: string): number {
  let count = 0;
  for (let i = 0; i < line.length; i++) {
    if (line[i] === "\t") count += 4;
    else if (line[i] === " ") count += 1;
    else break;
  }
  return count;
}

function trimmedEndLine(lines: string[], startIdx: number, endExclusive: number): number {
  let cursor = endExclusive;
  while (cursor > startIdx + 1 && !lines[cursor - 1].trim()) {
    cursor--;
  }
  return cursor;
}

function readAttr(blockLines: string[], attrName: string): string | undefined {
  const wanted = attrName.toLowerCase();
  const attrRe = /^\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$/;
  for (const line of blockLines) {
    const m = attrRe.exec(line);
    if (m && m[1].toLowerCase() === wanted) {
      return m[2].trim();
    }
  }
  return undefined;
}

function hasMarker(blockLines: string[], marker: string): boolean {
  const wanted = marker.toLowerCase();
  return blockLines.some((line) => line.trim().toLowerCase() === wanted);
}

function readDocComment(lines: string[], headerIdx: number): string | null {
  const comments: string[] = [];
  for (let i = headerIdx - 1; i >= 0; i--) {
    const trimmed = lines[i].trim();
    if (!trimmed) continue;
    if (trimmed.startsWith("///")) {
      comments.unshift(trimmed.replace(/^\/\/\/\s?/, ""));
    } else {
      break;
    }
  }
  return comments.length > 0 ? comments.join("\n") : null;
}

function extractFormulaFromBlock(rhs: string, blockLines: string[], baseIndent: number): string {
  const trimmedRhs = rhs.trim();
  if (trimmedRhs.startsWith("```")) {
    const parts: string[] = [];
    const rem = trimmedRhs.slice(3);
    if (rem) {
      if (rem.includes("```")) {
        return rem.split("```")[0].trim();
      }
      parts.push(rem);
    }
    for (let i = 1; i < blockLines.length; i++) {
      if (blockLines[i].includes("```")) {
        parts.push(blockLines[i].split("```")[0]);
        break;
      }
      parts.push(blockLines[i]);
    }
    return parts.join("\n").trim();
  }

  const exprParts: string[] = [];
  if (trimmedRhs) exprParts.push(trimmedRhs);
  const metadataPrefixes = [
    "lineagetag:",
    "formatstring:",
    "formatstringexpression:",
    "displayfolder:",
    "datatype:",
    "summarizeby:",
    "sourcecolumn:",
    "sortbycolumn:",
    "ishidden",
    "isnameinferred",
    "isdatatypedinferred",
    "annotation ",
    "changedproperty ",
    "kpi",
    "mode:",
    "querygroup:",
    "mattributes:",
    "ordinal:",
  ];
  for (let i = 1; i < blockLines.length; i++) {
    const line = blockLines[i];
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (indentOf(line) <= baseIndent) break;
    const lower = trimmed.toLowerCase();
    if (metadataPrefixes.some((p) => lower.startsWith(p))) {
      break;
    }
    exprParts.push(trimmed);
  }
  return exprParts.join("\n").trim();
}

function splitEndpoint(raw: string): { table?: string; column: string } {
  const cleaned = unquote(raw);
  const dotIdx = cleaned.lastIndexOf(".");
  if (dotIdx === -1) return { column: cleaned };
  return {
    table: unquote(cleaned.slice(0, dotIdx)),
    column: unquote(cleaned.slice(dotIdx + 1)),
  };
}

export function extractTmdlFile(relPath: string, source: string): ExtractedFile {
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

  const modelHeaderRe = /^\s*model\s+(.+?)\s*$/i;
  const tableHeaderRe = /^\s*table\s+(.+?)\s*$/i;
  const relHeaderRe = /^\s*relationship\s+(.+?)\s*$/i;
  const exprHeaderRe = /^\s*expression\s+(.+?)\s*=\s*(.*?)\s*$/i;
  const roleHeaderRe = /^\s*role\s+(.+?)\s*$/i;
  const funcHeaderRe = /^\s*function\s+(.+?)\s*=\s*(.*?)\s*$/i;

  // 1. Check if this is `table <Name>`
  const tableLineIdx = lines.findIndex((l) => tableHeaderRe.test(l));
  if (tableLineIdx !== -1) {
    const tm = tableHeaderRe.exec(lines[tableLineIdx])!;
    const tableName = unquote(tm[1]);
    const tableIndent = indentOf(lines[tableLineIdx]);
    const tableEndLine = trimmedEndLine(lines, tableLineIdx, lines.length);
    const tableBlock = lines.slice(tableLineIdx, tableEndLine);
    const tableId = `${relPath}#${tableName}`;
    const isCalcGroup = tableBlock.some((l) => /^\s*calculationGroup\b/i.test(l));
    const tableKind: PbiKind = isCalcGroup ? "calculation_group" : "table";
    const tableDoc = readDocComment(lines, tableLineIdx);

    const tableNode: NodeV1 = {
      id: tableId,
      name: tableName,
      kind: tableKind,
      path: relPath,
      span: `L${tableLineIdx + 1}-L${tableEndLine}`,
      signature: `${tableKind} ${tableName}`,
      exported: !hasMarker(tableBlock, "isHidden"),
      origin: "ast",
      body_hash: sha256(tableBlock.join("\n")),
      body_text: normalizeBody(tableBlock.join("\n")),
      pbi_meta: {
        lineage_tag: readAttr(tableBlock, "lineageTag"),
        hidden: hasMarker(tableBlock, "isHidden"),
      },
      summary_state: tableDoc ? "ready" : "pending",
      summary: tableDoc,
      crux: null,
    };
    nodes.push(tableNode);
    edges.push({ source: relPath, target: tableId, relation: "contains", confidence: "extracted" });

    // Scan child objects inside the table (`column`, `measure`, `partition`, `hierarchy`, `calculationItem`)
    const childRe = /^(\s+)(column|measure|hierarchy|partition|calculationItem)\s+(.+?)\s*$/i;
    const childStarts: Array<{ lineIdx: number; indent: number; kind: string; rest: string }> = [];
    for (let i = tableLineIdx + 1; i < lines.length; i++) {
      const cm = childRe.exec(lines[i]);
      if (!cm) continue;
      const ind = indentOf(lines[i]);
      if (ind <= tableIndent) continue;
      childStarts.push({ lineIdx: i, indent: ind, kind: cm[2].toLowerCase(), rest: cm[3] });
    }

    for (let idx = 0; idx < childStarts.length; idx++) {
      const cur = childStarts[idx];
      let nextLineIdx = lines.length;
      for (let j = idx + 1; j < childStarts.length; j++) {
        if (childStarts[j].indent <= cur.indent) {
          nextLineIdx = childStarts[j].lineIdx;
          break;
        }
      }
      const endLine = trimmedEndLine(lines, cur.lineIdx, nextLineIdx);
      const block = lines.slice(cur.lineIdx, endLine);
      const span = `L${cur.lineIdx + 1}-L${endLine}`;
      const doc = readDocComment(lines, cur.lineIdx);

      if (cur.kind === "partition") {
        const [rawPartName, rawType] = cur.rest.split("=").map((s) => s?.trim() ?? "");
        const partName = unquote(rawPartName);
        const partId = `${relPath}#${tableName}.${partName}`;
        const sourceLineRelIdx = block.findIndex((l, bi) => bi > 0 && /^\s*source\b/i.test(l));
        let exprText = "";
        if (sourceLineRelIdx !== -1) {
          const srcMatch = /^\s*source\s*(?:=\s*(.*))?$/i.exec(block[sourceLineRelIdx]);
          const srcRhs = srcMatch?.[1] ?? "";
          exprText = extractFormulaFromBlock(srcRhs, block.slice(sourceLineRelIdx), indentOf(block[sourceLineRelIdx]));
        }
        nodes.push({
          id: partId,
          name: partName,
          kind: "partition",
          owner: tableName,
          path: relPath,
          span,
          signature: `partition ${tableName}.${partName} = ${rawType || "m"}`,
          exported: true,
          origin: "ast",
          body_hash: sha256(block.join("\n")),
          body_text: normalizeBody(exprText || block.join("\n")),
          pbi_meta: {
            table: tableName,
            partition_type: rawType || "m",
            mode: readAttr(block, "mode"),
          },
          summary_state: doc ? "ready" : "pending",
          summary: doc,
          crux: null,
        });
        edges.push({ source: tableId, target: partId, relation: "contains", confidence: "extracted" });

        if (rawType.toLowerCase().startsWith("calculated")) {
          const daxDeps = extractDaxDependencies(partId, exprText, tableName);
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
        } else if (exprText) {
          const mDeps = extractMExpressionDependencies(partId, relPath, span, exprText);
          for (const ds of mDeps.dataSourceNodes) {
            if (!nodes.some((n) => n.id === ds.id)) {
              nodes.push(ds);
              edges.push({ source: relPath, target: ds.id, relation: "contains", confidence: "extracted" });
            }
          }
          edges.push(...mDeps.dataSourceEdges);
          unresolvedCalls.push(...mDeps.calls);
        }
        continue;
      }

      if (cur.kind === "hierarchy") {
        const hierName = unquote(cur.rest);
        const hierId = `${relPath}#${tableName}.${hierName}`;
        nodes.push({
          id: hierId,
          name: hierName,
          kind: "hierarchy",
          owner: tableName,
          path: relPath,
          span,
          signature: `hierarchy ${tableName}.${hierName}`,
          exported: !hasMarker(block, "isHidden"),
          origin: "ast",
          body_hash: sha256(block.join("\n")),
          pbi_meta: { table: tableName, lineage_tag: readAttr(block, "lineageTag") },
          summary_state: doc ? "ready" : "pending",
          summary: doc,
          crux: null,
        });
        edges.push({ source: tableId, target: hierId, relation: "contains", confidence: "extracted" });

        // Extract levels inside the hierarchy
        const levelRe = /^\s+level\s+(.+?)\s*$/i;
        for (let li = 1; li < block.length; li++) {
          const lm = levelRe.exec(block[li]);
          if (!lm) continue;
          const levelName = unquote(lm[1]);
          const levelId = `${hierId}.${levelName}`;
          const levelSlice = block.slice(li, Math.min(block.length, li + 5));
          const colRef = readAttr(levelSlice, "column");
          const levelLine = cur.lineIdx + li + 1;
          nodes.push({
            id: levelId,
            name: levelName,
            kind: "level",
            owner: tableName,
            path: relPath,
            span: `L${levelLine}-L${Math.min(endLine, levelLine + 2)}`,
            signature: `level ${levelName} -> ${colRef || levelName}`,
            exported: true,
            origin: "ast",
            body_hash: sha256(levelSlice.join("\n")),
            summary_state: "pending",
            summary: null,
            crux: null,
          });
          edges.push({ source: hierId, target: levelId, relation: "contains", confidence: "extracted" });
          if (colRef) {
            unresolvedCalls.push({
              caller: levelId,
              callee: unquote(colRef),
              receiver: tableName,
              kind: "depends_on",
            });
          }
        }
        continue;
      }

      // `measure`, `column`, or `calculationItem`
      const eqIdx = cur.rest.indexOf("=");
      const objName = unquote(eqIdx === -1 ? cur.rest : cur.rest.slice(0, eqIdx));
      const rhs = eqIdx === -1 ? "" : cur.rest.slice(eqIdx + 1);
      const formula = eqIdx !== -1 ? extractFormulaFromBlock(rhs, block, cur.indent) : "";
      const nodeKind: PbiKind =
        cur.kind === "measure"
          ? "measure"
          : cur.kind === "calculationitem"
            ? "calculation_item"
            : "column";
      const objId = `${relPath}#${tableName}.${objName}`;
      const datatype = readAttr(block, "dataType");
      const formatString = readAttr(block, "formatString");
      const formatStringExpr = readAttr(block, "formatStringExpression");
      const sortByColumn = readAttr(block, "sortByColumn");

      nodes.push({
        id: objId,
        name: objName,
        kind: nodeKind,
        owner: tableName,
        path: relPath,
        span,
        signature: formula
          ? `${nodeKind} ${tableName}[${objName}] = ${normalizeBody(formula).slice(0, 120)}`
          : `${nodeKind} ${tableName}[${objName}]${datatype ? ` : ${datatype}` : ""}`,
        exported: !hasMarker(block, "isHidden"),
        origin: "ast",
        body_hash: sha256(block.join("\n")),
        body_text: normalizeBody(formula || block.join("\n")),
        pbi_meta: {
          table: tableName,
          lineage_tag: readAttr(block, "lineageTag"),
          datatype,
          format_string: formatString,
          sort_by_column: sortByColumn,
          source_column: readAttr(block, "sourceColumn"),
          expression: formula || undefined,
          expression_language: formula ? "DAX" : undefined,
        },
        summary_state: doc ? "ready" : "pending",
        summary: doc,
        crux: null,
      });
      edges.push({ source: tableId, target: objId, relation: "contains", confidence: "extracted" });

      if (formula) {
        const daxDeps = extractDaxDependencies(objId, formula, tableName);
        unresolvedCalls.push(...daxDeps.calls);
      }
      if (formatStringExpr) {
        const fmtDeps = extractDaxDependencies(objId, formatStringExpr, tableName);
        for (const call of fmtDeps.calls) {
          unresolvedCalls.push({ ...call, kind: "formats_by" });
        }
      }
      if (sortByColumn) {
        unresolvedCalls.push({
          caller: objId,
          callee: unquote(sortByColumn),
          receiver: tableName,
          kind: "depends_on",
        });
      }
    }

    return { path: relPath, language: "tmdl", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  // 2. Check if this is `relationships.tmdl`
  const relStarts: number[] = [];
  for (let i = 0; i < lines.length; i++) {
    if (relHeaderRe.test(lines[i])) relStarts.push(i);
  }
  if (relStarts.length > 0) {
    for (let idx = 0; idx < relStarts.length; idx++) {
      const startIdx = relStarts[idx];
      const nextIdx = idx + 1 < relStarts.length ? relStarts[idx + 1] : lines.length;
      const endLine = trimmedEndLine(lines, startIdx, nextIdx);
      const block = lines.slice(startIdx, endLine);
      const relIdRaw = unquote(relHeaderRe.exec(lines[startIdx])![1]);
      const fromColRaw = readAttr(block, "fromColumn");
      const toColRaw = readAttr(block, "toColumn");
      const fromEp = fromColRaw ? splitEndpoint(fromColRaw) : undefined;
      const toEp = toColRaw ? splitEndpoint(toColRaw) : undefined;
      const relDisplayName =
        fromEp && toEp
          ? `${fromEp.table ?? ""}.${fromEp.column} -> ${toEp.table ?? ""}.${toEp.column}`
          : relIdRaw;
      const nodeId = `${relPath}#${relIdRaw}`;
      nodes.push({
        id: nodeId,
        name: relDisplayName,
        kind: "relationship",
        path: relPath,
        span: `L${startIdx + 1}-L${endLine}`,
        signature: `relationship ${relDisplayName}`,
        exported: true,
        origin: "ast",
        body_hash: sha256(block.join("\n")),
        body_text: normalizeBody(block.join("\n")),
        pbi_meta: {
          relationship_id: relIdRaw,
          from_table: fromEp?.table,
          from_column: fromEp?.column,
          to_table: toEp?.table,
          to_column: toEp?.column,
          cross_filtering_behavior: readAttr(block, "crossFilteringBehavior"),
          is_active: readAttr(block, "isActive") !== "false",
        },
        summary_state: "pending",
        summary: null,
        crux: null,
      });
      edges.push({ source: relPath, target: nodeId, relation: "contains", confidence: "extracted" });
      if (fromEp) {
        unresolvedCalls.push({
          caller: nodeId,
          callee: fromEp.column,
          receiver: fromEp.table,
          kind: "relates_to",
        });
      }
      if (toEp) {
        unresolvedCalls.push({
          caller: nodeId,
          callee: toEp.column,
          receiver: toEp.table,
          kind: "relates_to",
        });
      }
    }
    return { path: relPath, language: "tmdl", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  // 3. Check if this is `expressions.tmdl`
  const exprStarts: number[] = [];
  for (let i = 0; i < lines.length; i++) {
    if (exprHeaderRe.test(lines[i])) exprStarts.push(i);
  }
  if (exprStarts.length > 0) {
    for (let idx = 0; idx < exprStarts.length; idx++) {
      const startIdx = exprStarts[idx];
      const nextIdx = idx + 1 < exprStarts.length ? exprStarts[idx + 1] : lines.length;
      const endLine = trimmedEndLine(lines, startIdx, nextIdx);
      const block = lines.slice(startIdx, endLine);
      const m = exprHeaderRe.exec(lines[startIdx])!;
      const exprName = unquote(m[1]);
      const exprBody = extractFormulaFromBlock(m[2], block, indentOf(lines[startIdx]));
      const span = `L${startIdx + 1}-L${endLine}`;
      const nodeId = `${relPath}#${exprName}`;
      nodes.push({
        id: nodeId,
        name: exprName,
        kind: "shared_expression",
        path: relPath,
        span,
        signature: `expression ${exprName} = ${normalizeBody(exprBody).slice(0, 100)}`,
        exported: true,
        origin: "ast",
        body_hash: sha256(block.join("\n")),
        body_text: normalizeBody(exprBody),
        pbi_meta: {
          lineage_tag: readAttr(block, "lineageTag"),
          expression: exprBody,
          expression_language: "M",
        },
        summary_state: "pending",
        summary: null,
        crux: null,
      });
      edges.push({ source: relPath, target: nodeId, relation: "contains", confidence: "extracted" });
      const mDeps = extractMExpressionDependencies(nodeId, relPath, span, exprBody);
      for (const ds of mDeps.dataSourceNodes) {
        if (!nodes.some((n) => n.id === ds.id)) {
          nodes.push(ds);
          edges.push({ source: relPath, target: ds.id, relation: "contains", confidence: "extracted" });
        }
      }
      edges.push(...mDeps.dataSourceEdges);
      unresolvedCalls.push(...mDeps.calls);
    }
    return { path: relPath, language: "tmdl", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  // 4. Check if this is `roles/*.tmdl`
  const roleLineIdx = lines.findIndex((l) => roleHeaderRe.test(l));
  if (roleLineIdx !== -1) {
    const roleName = unquote(roleHeaderRe.exec(lines[roleLineIdx])![1]);
    const endLine = trimmedEndLine(lines, roleLineIdx, lines.length);
    const block = lines.slice(roleLineIdx, endLine);
    const roleId = `${relPath}#${roleName}`;
    nodes.push({
      id: roleId,
      name: roleName,
      kind: "security_role",
      path: relPath,
      span: `L${roleLineIdx + 1}-L${endLine}`,
      signature: `role ${roleName}`,
      exported: true,
      origin: "ast",
      body_hash: sha256(block.join("\n")),
      pbi_meta: { model_permission: readAttr(block, "modelPermission") },
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: relPath, target: roleId, relation: "contains", confidence: "extracted" });

    const tpRe = /^\s+tablePermission\s+(.+?)\s*(?:=\s*(.*))?$/i;
    for (let i = roleLineIdx + 1; i < lines.length; i++) {
      const tpm = tpRe.exec(lines[i]);
      if (!tpm) continue;
      const targetTable = unquote(tpm[1]);
      const filterFormula = tpm[2]?.trim() || "";
      const rfId = `${roleId}.${targetTable}`;
      nodes.push({
        id: rfId,
        name: `${roleName}:${targetTable}`,
        kind: "role_filter",
        owner: roleName,
        path: relPath,
        span: `L${i + 1}-L${i + 1}`,
        signature: `tablePermission ${targetTable} = ${filterFormula}`,
        exported: true,
        origin: "ast",
        body_hash: sha256(lines[i]),
        body_text: normalizeBody(filterFormula),
        summary_state: "pending",
        summary: null,
        crux: null,
      });
      edges.push({ source: roleId, target: rfId, relation: "contains", confidence: "extracted" });
      unresolvedCalls.push({ caller: rfId, callee: targetTable, kind: "filters" });
      if (filterFormula) {
        const daxDeps = extractDaxDependencies(rfId, filterFormula, targetTable);
        unresolvedCalls.push(...daxDeps.calls);
      }
    }
    return { path: relPath, language: "tmdl", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  // 5. Check if this is `functions.tmdl`
  const funcStarts: number[] = [];
  for (let i = 0; i < lines.length; i++) {
    if (funcHeaderRe.test(lines[i])) funcStarts.push(i);
  }
  if (funcStarts.length > 0) {
    for (let idx = 0; idx < funcStarts.length; idx++) {
      const startIdx = funcStarts[idx];
      const nextIdx = idx + 1 < funcStarts.length ? funcStarts[idx + 1] : lines.length;
      const endLine = trimmedEndLine(lines, startIdx, nextIdx);
      const block = lines.slice(startIdx, endLine);
      const fm = funcHeaderRe.exec(lines[startIdx])!;
      const fnName = unquote(fm[1]);
      const fnBody = extractFormulaFromBlock(fm[2], block, indentOf(lines[startIdx]));
      const fnId = `${relPath}#${fnName}`;
      nodes.push({
        id: fnId,
        name: fnName,
        kind: "user_defined_function",
        path: relPath,
        span: `L${startIdx + 1}-L${endLine}`,
        signature: `function ${fnName} = ${normalizeBody(fnBody).slice(0, 100)}`,
        exported: true,
        origin: "ast",
        body_hash: sha256(block.join("\n")),
        body_text: normalizeBody(fnBody),
        summary_state: "pending",
        summary: null,
        crux: null,
      });
      edges.push({ source: relPath, target: fnId, relation: "contains", confidence: "extracted" });
      unresolvedCalls.push(...extractDaxDependencies(fnId, fnBody).calls);
    }
    return { path: relPath, language: "tmdl", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  // 6. Default: `model.tmdl` or `database.tmdl` -> `semantic_model`
  const modelLineIdx = lines.findIndex((l) => modelHeaderRe.test(l));
  const modelName =
    modelLineIdx !== -1
      ? unquote(modelHeaderRe.exec(lines[modelLineIdx])![1])
      : (relPath.split("/").slice(-3, -2)[0] || "Model").replace(/\.(?:SemanticModel|Dataset)$/i, "");
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
      culture: readAttr(lines, "culture"),
      compatibility_level: readAttr(lines, "compatibilityLevel"),
    },
    summary_state: "pending",
    summary: null,
    crux: null,
  });
  edges.push({ source: relPath, target: modelId, relation: "contains", confidence: "extracted" });

  return { path: relPath, language: "tmdl", nodes, edges, unresolvedCalls, unresolvedImports: [] };
}
