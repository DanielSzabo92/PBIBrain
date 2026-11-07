import React from "react";

/**
 * How many versions of a model or report have this object: "×2" when every version has it (a stack of
 * identical-in-meaning copies), "1/2" when only some do. A dot marks copies whose definitions differ.
 */
export function VersionBadge({ node, note }) {
  if (!node || !(node.familySize > 1)) return null;
  const partial = node.versionCount < node.familySize;
  if (!partial && node.versionCount < 2) return null;
  return <span className={`version-badge ${partial ? "is-partial" : ""} ${node.differs ? "differs" : ""}`} data-ui-number="" role="img" aria-label={note} title={note}>
    {partial ? `${node.versionCount}/${node.familySize}` : `×${node.versionCount}`}
  </span>;
}
