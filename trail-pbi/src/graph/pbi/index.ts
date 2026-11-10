import type { ExtractResult, ExtractedFile, PbiLanguage, RawEdge } from "../extract.js";
import { extractDaxFile } from "./dax.js";
import { extractKqlFile } from "./kql.js";
import { extractPbirFile } from "./pbir.js";
import { extractPqFile } from "./pq.js";
import { extractSqlFile } from "./sql.js";
import { extractTmdlFile } from "./tmdl.js";
import { extractTmslFile } from "./tmsl.js";

export {
  extractDaxFile,
  extractKqlFile,
  extractPbirFile,
  extractPqFile,
  extractSqlFile,
  extractTmdlFile,
  extractTmslFile,
};

export function toExtractResult(extracted: ExtractedFile): ExtractResult {
  const rawEdges: RawEdge[] = [];
  for (const edge of extracted.edges) {
    rawEdges.push({
      source: edge.source,
      relation: edge.relation,
      targetId: edge.target,
      file: extracted.path,
    });
  }
  for (const call of extracted.unresolvedCalls) {
    rawEdges.push({
      source: call.caller,
      relation: call.kind,
      file: extracted.path,
      name: call.callee,
      ...(call.receiver ? { recvType: call.receiver, viaMember: true } : {}),
    });
  }
  return {
    nodes: extracted.nodes,
    rawEdges,
  };
}

export function extractPbiFile(relPath: string, source: string, lang: PbiLanguage): ExtractResult {
  switch (lang) {
    case "tmdl":
      return toExtractResult(extractTmdlFile(relPath, source));
    case "tmsl":
      return toExtractResult(extractTmslFile(relPath, source));
    case "dax":
      return toExtractResult(extractDaxFile(relPath, source));
    case "pq":
      return toExtractResult(extractPqFile(relPath, source));
    case "sql":
      return toExtractResult(extractSqlFile(relPath, source));
    case "kql":
      return toExtractResult(extractKqlFile(relPath, source));
    case "pbir":
      return toExtractResult(extractPbirFile(relPath, source));
  }
}
