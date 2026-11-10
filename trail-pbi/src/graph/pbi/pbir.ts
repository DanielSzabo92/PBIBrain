/**
 * PBIP / PBIR Report & Fabric Workspace extractor for Trail-PBI.
 *
 * Handles:
 *  - `.pbip` project files
 *  - `definition.pbir` report -> semantic model binding (`uses_model`)
 *  - `report.json` report root + report-level filters (`report_filter`)
 *  - `page.json` report pages + drillthrough/tooltip bindings + page filters (`page_filter`)
 *  - `visual.json` visuals + field projections (`uses`), visual calculations (`visual_calculation`),
 *    visual filters (`visual_filter`), drillthrough (`drills_through_to`), tooltip (`tooltip_page`),
 *    and slicer sync (`synced_with`)
 *  - `reportExtensions.json` report-level measures (`report_measure` -> `extractDaxDependencies`)
 *  - `*.bookmark.json` bookmarks (`bookmark`)
 *  - `.platform` Fabric workspace item metadata (`workspace`)
 */
import { createHash } from "node:crypto";
import type { ExtractedFile, UnresolvedCall } from "../extract.js";
import type { EdgeV1, NodeV1 } from "../types.js";
import { extractDaxDependencies } from "./dax.js";

function sha256(text: string): string {
  return "sha256:" + createHash("sha256").update(text).digest("hex");
}

function normalizeBody(text: string): string {
  return text.replace(/\s+/g, " ").trim().slice(0, 800);
}

interface SemanticFieldRef {
  table?: string;
  field: string;
  kind: "column" | "measure" | "hierarchy";
}

/** Recursively walk a PBIR JSON structure (`query`, `filterConfig`, `singleVisual`, `pageBinding`)
 * to collect all semantic model field bindings (`Column`, `Measure`, `HierarchyLevel`) and
 * `NativeVisualCalculation` formulas. */
function collectPbirBindings(rootObj: any): {
  refs: SemanticFieldRef[];
  visualCalculations: Array<{ name: string; expression: string }>;
} {
  const refs: SemanticFieldRef[] = [];
  const visualCalculations: Array<{ name: string; expression: string }> = [];
  const seen = new Set<string>();

  function walk(node: any, aliases: Map<string, string>): void {
    if (!node || typeof node !== "object") return;
    if (Array.isArray(node)) {
      for (const item of node) walk(item, aliases);
      return;
    }

    const localAliases = new Map(aliases);
    const fromArr = node.From || node.from;
    if (Array.isArray(fromArr)) {
      for (const entry of fromArr) {
        const alias = entry?.Name ?? entry?.name;
        const entity = entry?.Entity ?? entry?.entity;
        if (typeof alias === "string" && typeof entity === "string") {
          localAliases.set(alias, entity);
        }
      }
    }

    const resolveSource = (exprObj: any): string | undefined => {
      if (!exprObj || typeof exprObj !== "object") return undefined;
      const srcRef = exprObj.SourceRef ?? exprObj.sourceRef;
      if (!srcRef || typeof srcRef !== "object") return undefined;
      const entity = srcRef.Entity ?? srcRef.entity;
      if (typeof entity === "string") return entity;
      const src = srcRef.Source ?? srcRef.source;
      if (typeof src === "string") return localAliases.get(src) || src;
      return undefined;
    };

    const colObj = node.Column ?? node.column;
    if (colObj && typeof colObj === "object") {
      const prop = colObj.Property ?? colObj.property;
      const tbl = resolveSource(colObj.Expression ?? colObj.expression);
      if (typeof prop === "string") {
        const key = `col:${tbl ?? ""}:${prop}`;
        if (!seen.has(key)) {
          seen.add(key);
          refs.push({ table: tbl, field: prop, kind: "column" });
        }
      }
    }

    const msrObj = node.Measure ?? node.measure;
    if (msrObj && typeof msrObj === "object") {
      const prop = msrObj.Property ?? msrObj.property;
      const tbl = resolveSource(msrObj.Expression ?? msrObj.expression);
      if (typeof prop === "string") {
        const key = `msr:${tbl ?? ""}:${prop}`;
        if (!seen.has(key)) {
          seen.add(key);
          refs.push({ table: tbl, field: prop, kind: "measure" });
        }
      }
    }

    const hlObj = node.HierarchyLevel ?? node.hierarchyLevel;
    if (hlObj && typeof hlObj === "object") {
      const hierExpr = hlObj.Expression ?? hlObj.expression;
      const hier = hierExpr?.Hierarchy ?? hierExpr?.hierarchy;
      const hierName = hier?.Hierarchy ?? hier?.hierarchy;
      const lvlName = hlObj.Level ?? hlObj.level;
      const prop =
        typeof hierName === "string" && typeof lvlName === "string"
          ? `${hierName}.${lvlName}`
          : (hierName ?? lvlName);
      const tbl = resolveSource(hier?.Expression ?? hier?.expression);
      if (typeof prop === "string") {
        const key = `hier:${tbl ?? ""}:${prop}`;
        if (!seen.has(key)) {
          seen.add(key);
          refs.push({ table: tbl, field: prop, kind: "hierarchy" });
        }
      }
    }

    const nvc = node.NativeVisualCalculation ?? node.nativeVisualCalculation;
    if (nvc && typeof nvc === "object") {
      const expr = nvc.Expression ?? nvc.expression;
      const name = nvc.Name ?? nvc.name ?? node.displayName ?? "VisualCalc";
      if (typeof expr === "string" && expr.trim()) {
        visualCalculations.push({ name: String(name), expression: expr });
      }
    }

    for (const val of Object.values(node)) {
      walk(val, localAliases);
    }
  }

  walk(rootObj, new Map());
  return { refs, visualCalculations };
}

export function isPbirJsonFile(relPath: string): boolean {
  const lower = relPath.toLowerCase();
  const base = lower.split("/").pop() || "";
  if (
    lower.endsWith(".pbip") ||
    lower.endsWith(".pbir") ||
    lower.endsWith(".bookmark.json") ||
    base === ".platform" ||
    base === "report.json" ||
    base === "page.json" ||
    base === "visual.json" ||
    base === "reportextensions.json"
  ) {
    return true;
  }
  return false;
}

export function extractPbirFile(relPath: string, source: string): ExtractedFile {
  const lines = source.split(/\r?\n/);
  const span = `L1-L${Math.max(1, lines.length)}`;
  const baseName = relPath.split("/").pop() || relPath;
  const lowerBase = baseName.toLowerCase();

  const fileNode: NodeV1 = {
    id: relPath,
    name: baseName,
    kind: "file",
    path: relPath,
    span,
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

  let data: Record<string, any>;
  try {
    data = JSON.parse(source.replace(/^\uFEFF/, ""));
  } catch {
    return { path: relPath, language: "pbir", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  // 1. `.platform` Fabric item marker
  if (lowerBase === ".platform") {
    const displayName = String(data?.metadata?.displayName || relPath.split("/").slice(-2, -1)[0] || "FabricItem");
    const itemType = String(data?.metadata?.type || "Item");
    const logicalId = String(data?.config?.logicalId || displayName);
    const nodeId = `${relPath}#${displayName}`;
    nodes.push({
      id: nodeId,
      name: displayName,
      kind: "workspace",
      path: relPath,
      span,
      signature: `fabric ${itemType}: ${displayName}`,
      exported: true,
      origin: "ast",
      body_hash: sha256(source),
      pbi_meta: { logical_id: logicalId, fabric_type: itemType },
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: relPath, target: nodeId, relation: "contains", confidence: "extracted" });
    return { path: relPath, language: "pbir", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  // 2. `definition.pbir` or `.pbip`
  if (lowerBase.endsWith(".pbir") || lowerBase.endsWith(".pbip")) {
    const reportDir = relPath.split("/").slice(-2, -1)[0] || baseName.replace(/\.(?:pbir|pbip)$/i, "");
    const reportName = reportDir.replace(/\.Report$/i, "");
    const nodeId = `${relPath}#${reportName}`;
    nodes.push({
      id: nodeId,
      name: reportName,
      kind: "report",
      path: relPath,
      span,
      signature: `report ${reportName}`,
      exported: true,
      origin: "ast",
      body_hash: sha256(source),
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: relPath, target: nodeId, relation: "contains", confidence: "extracted" });

    const byPath = data?.datasetReference?.byPath?.path;
    if (typeof byPath === "string") {
      const targetModelName = byPath
        .split("/")
        .filter(Boolean)
        .pop()
        ?.replace(/\.(?:SemanticModel|Dataset)$/i, "");
      if (targetModelName) {
        unresolvedCalls.push({
          caller: nodeId,
          callee: targetModelName,
          kind: "uses_model",
        });
      }
    }
    return { path: relPath, language: "pbir", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  // 3. `reportExtensions.json` -> `report_measure` nodes with DAX formulas
  if (lowerBase === "reportextensions.json") {
    const entities: any[] = Array.isArray(data.entities) ? data.entities : [];
    for (const ent of entities) {
      const tableName = String(ent?.name || "");
      const measures: any[] = Array.isArray(ent?.measures) ? ent.measures : [];
      for (const msr of measures) {
        if (!msr || typeof msr.name !== "string") continue;
        const msrName = msr.name;
        const expr = String(msr.expression || "");
        const msrId = `${relPath}#${tableName ? `${tableName}.` : ""}${msrName}`;
        nodes.push({
          id: msrId,
          name: msrName,
          kind: "report_measure",
          owner: tableName || undefined,
          path: relPath,
          span,
          signature: `report_measure ${tableName}[${msrName}] = ${normalizeBody(expr).slice(0, 120)}`,
          exported: true,
          origin: "ast",
          body_hash: sha256(JSON.stringify(msr)),
          body_text: normalizeBody(expr),
          pbi_meta: {
            table: tableName,
            expression: expr,
            expression_language: "DAX",
            datatype: msr.dataType,
            format_string: msr.formatString,
          },
          summary_state: "pending",
          summary: null,
          crux: null,
        });
        edges.push({ source: relPath, target: msrId, relation: "contains", confidence: "extracted" });
        if (expr) {
          unresolvedCalls.push(...extractDaxDependencies(msrId, expr, tableName).calls);
        }
      }
    }
    return { path: relPath, language: "pbir", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  // 4. `*.bookmark.json`
  if (lowerBase.endsWith(".bookmark.json")) {
    const bmName = String(data.displayName || data.name || baseName.replace(/\.bookmark\.json$/i, ""));
    const bmId = `${relPath}#${bmName}`;
    const activePage = data?.explorationState?.activeSection;
    nodes.push({
      id: bmId,
      name: bmName,
      kind: "bookmark",
      path: relPath,
      span,
      signature: `bookmark ${bmName}`,
      exported: true,
      origin: "ast",
      body_hash: sha256(source),
      pbi_meta: { bookmark_id: data.name, active_page: activePage },
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: relPath, target: bmId, relation: "contains", confidence: "extracted" });
    if (typeof activePage === "string" && activePage) {
      unresolvedCalls.push({ caller: bmId, callee: activePage, kind: "interacts_with" });
    }
    return { path: relPath, language: "pbir", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  // 5. `visual.json`
  if (lowerBase === "visual.json") {
    const visualIdRaw = String(data.name || relPath.split("/").slice(-2, -1)[0] || "visual");
    const visualType = String(data?.visual?.visualType || data?.visualType || "visual");
    const titleText =
      data?.visual?.visualContainerObjects?.title?.[0]?.properties?.text?.expr?.Literal?.Value?.replace(/^'|'$/g, "") ||
      visualIdRaw;
    const nodeId = `${relPath}#${visualIdRaw}`;
    nodes.push({
      id: nodeId,
      name: titleText,
      kind: "visual",
      path: relPath,
      span,
      signature: `visual ${titleText} (${visualType})`,
      exported: !data.isHidden,
      origin: "ast",
      body_hash: sha256(source),
      body_text: normalizeBody(`${titleText} ${visualType}`),
      pbi_meta: {
        visual_id: visualIdRaw,
        visual_type: visualType,
        position: data.position,
      },
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: relPath, target: nodeId, relation: "contains", confidence: "extracted" });

    const { refs, visualCalculations } = collectPbirBindings(data);
    for (const ref of refs) {
      unresolvedCalls.push({
        caller: nodeId,
        callee: ref.field,
        receiver: ref.table,
        kind: "uses",
      });
    }

    for (const vc of visualCalculations) {
      const vcId = `${nodeId}.${vc.name}`;
      nodes.push({
        id: vcId,
        name: vc.name,
        kind: "visual_calculation",
        owner: titleText,
        path: relPath,
        span,
        signature: `visual_calculation ${vc.name} = ${normalizeBody(vc.expression).slice(0, 100)}`,
        exported: true,
        origin: "ast",
        body_hash: sha256(vc.expression),
        body_text: normalizeBody(vc.expression),
        summary_state: "pending",
        summary: null,
        crux: null,
      });
      edges.push({ source: nodeId, target: vcId, relation: "contains", confidence: "extracted" });
      unresolvedCalls.push(...extractDaxDependencies(vcId, vc.expression).calls);
    }

    // Visual filters
    const vFilters: any[] = Array.isArray(data?.filterConfig?.filters) ? data.filterConfig.filters : [];
    for (let i = 0; i < vFilters.length; i++) {
      const vf = vFilters[i];
      const vfName = String(vf?.name || `Filter_${i + 1}`);
      const vfId = `${nodeId}.filter.${vfName}`;
      const vfBindings = collectPbirBindings(vf.field ?? vf);
      nodes.push({
        id: vfId,
        name: vfName,
        kind: "visual_filter",
        owner: titleText,
        path: relPath,
        span,
        signature: `visual_filter ${vfName}`,
        exported: true,
        origin: "ast",
        body_hash: sha256(JSON.stringify(vf)),
        summary_state: "pending",
        summary: null,
        crux: null,
      });
      edges.push({ source: nodeId, target: vfId, relation: "contains", confidence: "extracted" });
      for (const ref of vfBindings.refs) {
        unresolvedCalls.push({ caller: vfId, callee: ref.field, receiver: ref.table, kind: "filters" });
      }
    }

    return { path: relPath, language: "pbir", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  // 6. `page.json`
  if (lowerBase === "page.json") {
    const pageIdRaw = String(data.name || relPath.split("/").slice(-2, -1)[0] || "Page");
    const displayName = String(data.displayName || pageIdRaw);
    const nodeId = `${relPath}#${pageIdRaw}`;
    nodes.push({
      id: nodeId,
      name: displayName,
      kind: "page",
      path: relPath,
      span,
      signature: `page ${displayName}`,
      exported: data.visibility !== "HiddenInViewMode",
      origin: "ast",
      body_hash: sha256(source),
      pbi_meta: { page_id: pageIdRaw, display_name: displayName, page_type: data.pageBinding?.type },
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: relPath, target: nodeId, relation: "contains", confidence: "extracted" });

    const { refs } = collectPbirBindings(data.pageBinding);
    for (const ref of refs) {
      unresolvedCalls.push({ caller: nodeId, callee: ref.field, receiver: ref.table, kind: "uses" });
    }

    const pFilters: any[] = Array.isArray(data?.filterConfig?.filters) ? data.filterConfig.filters : [];
    for (let i = 0; i < pFilters.length; i++) {
      const pf = pFilters[i];
      const pfName = String(pf?.name || `PageFilter_${i + 1}`);
      const pfId = `${nodeId}.filter.${pfName}`;
      const pfBindings = collectPbirBindings(pf.field ?? pf);
      nodes.push({
        id: pfId,
        name: pfName,
        kind: "page_filter",
        owner: displayName,
        path: relPath,
        span,
        signature: `page_filter ${pfName}`,
        exported: true,
        origin: "ast",
        body_hash: sha256(JSON.stringify(pf)),
        summary_state: "pending",
        summary: null,
        crux: null,
      });
      edges.push({ source: nodeId, target: pfId, relation: "contains", confidence: "extracted" });
      for (const ref of pfBindings.refs) {
        unresolvedCalls.push({ caller: pfId, callee: ref.field, receiver: ref.table, kind: "filters" });
      }
    }

    return { path: relPath, language: "pbir", nodes, edges, unresolvedCalls, unresolvedImports: [] };
  }

  // 7. `report.json`
  const reportDir = relPath.split("/").find((p) => p.toLowerCase().endsWith(".report")) || "Report";
  const reportName = reportDir.replace(/\.Report$/i, "");
  const reportNodeId = `${relPath}#${reportName}`;
  nodes.push({
    id: reportNodeId,
    name: reportName,
    kind: "report",
    path: relPath,
    span,
    signature: `report ${reportName}`,
    exported: true,
    origin: "ast",
    body_hash: sha256(source),
    summary_state: "pending",
    summary: null,
    crux: null,
  });
  edges.push({ source: relPath, target: reportNodeId, relation: "contains", confidence: "extracted" });

  const rFilters: any[] = Array.isArray(data?.filterConfig?.filters) ? data.filterConfig.filters : [];
  for (let i = 0; i < rFilters.length; i++) {
    const rf = rFilters[i];
    const rfName = String(rf?.name || `ReportFilter_${i + 1}`);
    const rfId = `${reportNodeId}.filter.${rfName}`;
    const rfBindings = collectPbirBindings(rf.field ?? rf);
    nodes.push({
      id: rfId,
      name: rfName,
      kind: "report_filter",
      owner: reportName,
      path: relPath,
      span,
      signature: `report_filter ${rfName}`,
      exported: true,
      origin: "ast",
      body_hash: sha256(JSON.stringify(rf)),
      summary_state: "pending",
      summary: null,
      crux: null,
    });
    edges.push({ source: reportNodeId, target: rfId, relation: "contains", confidence: "extracted" });
    for (const ref of rfBindings.refs) {
      unresolvedCalls.push({ caller: rfId, callee: ref.field, receiver: ref.table, kind: "filters" });
    }
  }

  return { path: relPath, language: "pbir", nodes, edges, unresolvedCalls, unresolvedImports: [] };
}
