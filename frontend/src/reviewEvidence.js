import { byId } from "./presentation.js";
import { readableText } from "./presentation.js";

function cleanToken(str) {
  return String(str || "")
    .trim()
    .replace(/^['"\[]+|['"\]]+$/g, "")
    .toLowerCase()
    .replace(/[\s_\-]+/g, "");
}

/**
 * Determine whether a review suggestion is low-evidence or a name-only tautology.
 * E.g. "Meaning: Sales" for table "Sales" at 30%, or an alias identical to object name.
 */
export function isLowEvidence(item, nodes = []) {
  if (!item) return false;
  const issue = String(item.issue || item.issue_type || "").toLowerCase();
  if (issue === "conflict" || issue === "stale") return false;

  const targetId = item.target_id || item.target || item.object_id || item.item?.target || item.item?.target_id;
  const targetNode = byId(nodes, targetId) || null;
  const targetName = targetNode?.name || item.name || item.target_name || "";
  const value = String(item.value ?? item.meaning ?? item.properties?.value ?? item.properties?.meaning ?? item.item?.value ?? "").trim();

  const normName = cleanToken(targetName);
  const normVal = cleanToken(value);
  const isTautology = Boolean(normName && normVal && normName === normVal);

  const source = String(item.source || item.properties?.candidate_source || item.item?.source || "").toLowerCase();
  const isNameSource = source === "object_name" || source === "name";

  const evidence = item.evidence || item.item?.evidence || [];
  const onlyNameEvidence = Array.isArray(evidence) && evidence.length > 0 && evidence.every((entry) => {
    const s = typeof entry === "string" ? entry.toLowerCase() : String(entry?.source || entry?.origin || "").toLowerCase();
    return s === "object_name" || s === "name";
  });

  const rawConfidence = item.confidence ?? item.properties?.confidence ?? item.item?.confidence;
  const score = rawConfidence !== undefined && rawConfidence !== null ? Math.round(Number(rawConfidence) <= 1 ? Number(rawConfidence) * 100 : Number(rawConfidence)) : null;

  if (isTautology) return true;
  if (isNameSource && (evidence.length <= 1 || onlyNameEvidence)) return true;
  if (onlyNameEvidence) return true;
  if (score !== null && score <= 35 && (!evidence.length || onlyNameEvidence)) return true;

  return false;
}

/**
 * Format an honest, inspectable explanation of the confidence score.
 */
export function explainConfidence(item, node = null) {
  if (!item) return "No confidence data.";
  const rawConfidence = item.confidence ?? item.properties?.confidence ?? item.item?.confidence;
  const score = rawConfidence !== undefined && rawConfidence !== null ? Math.round(Number(rawConfidence) <= 1 ? Number(rawConfidence) * 100 : Number(rawConfidence)) : null;
  const scoreText = score !== null ? `${score}%` : "Unrated";

  const targetName = node?.name || item.name || item.target_name || "object";
  const value = String(item.value ?? item.meaning ?? item.properties?.value ?? item.item?.value ?? "").trim();
  const normName = cleanToken(targetName);
  const normVal = cleanToken(value);
  const isTautology = Boolean(normName && normVal && normName === normVal);

  const source = String(item.source || item.properties?.candidate_source || item.item?.source || "").toLowerCase();
  const evidence = item.evidence || item.item?.evidence || [];

  if (isTautology) {
    return `Confidence: ${scoreText} · Low evidence. The suggested label matches the object's own name (${targetName}) with no corroborating documentation or formula.`;
  }

  const sources = new Set();
  if (source) sources.add(source);
  if (Array.isArray(evidence)) {
    evidence.forEach((e) => {
      const s = typeof e === "string" ? e.toLowerCase() : String(e?.source || e?.origin || "").toLowerCase();
      if (s) sources.add(s);
    });
  }

  const contributions = [];
  if (sources.has("description")) contributions.push("source description (+96%)");
  if (sources.has("dax_ast") || sources.has("dax_analysis")) contributions.push("DAX formula analysis (+86%)");
  if (sources.has("model_metadata") || sources.has("structural")) contributions.push("model metadata (+82%)");
  if (sources.has("report_usage")) contributions.push("report usage (+48%)");
  if (sources.has("object_name") || sources.has("name")) contributions.push("object name (+30%)");
  if (sources.has("llm")) contributions.push("semantic assistant (+20%)");

  if (contributions.length > 0) {
    return `Confidence: ${scoreText} · Based on ${contributions.join(", ")}.`;
  }

  if (score !== null && score >= 80) {
    return `Confidence: ${scoreText} · High evidence from model documentation and structural analysis.`;
  }
  if (score !== null && score >= 50) {
    return `Confidence: ${scoreText} · Moderate evidence from inferred usage patterns.`;
  }
  return `Confidence: ${scoreText} · Low evidence proposal. Verify context before approving.`;
}
