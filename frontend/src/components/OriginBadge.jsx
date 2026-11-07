import React from "react";
import { Cloud, CircleDashed } from "lucide-react";
import { originNote } from "../presentation";

/** A small chip on a model or report: its cloud workspace, or "Not checked" when the scan could not read it. */
export function OriginBadge({ node }) {
  const note = originNote(node);
  if (!note) return null;
  const Icon = note.kind === "cloud" ? Cloud : CircleDashed;
  return <span className={`origin-badge is-${note.kind}`} title={note.title} aria-label={note.title} role="img">
    <Icon aria-hidden="true" /><span translate="no">{note.label}</span>
  </span>;
}
