import React from "react";
import { artifactStyle, typeLabel } from "../graphPresentation";
import { typeIcon } from "../objectIcons";
import { cn } from "@/lib/utils";

/**
 * Square object-type chip: the type glyph in the type colour on a 14% tint (visual contract §3).
 * Decorative by default; pass `label` when the chip is the only place the type is named.
 */
export function TypeGlyph({ node, type, colors, size = "md", label = false, className }) {
  const kind = type || node?.type;
  const Icon = typeIcon(kind);
  const style = artifactStyle(node || { type: kind }, colors);
  return (
    <span className={cn("type-glyph", `type-glyph-${size}`, className)} style={style} data-type={kind} {...(label ? { role: "img", "aria-label": typeLabel(kind) } : { "aria-hidden": "true" })}>
      <Icon />
    </span>
  );
}

/** The bare type icon, for places that already carry the type colour (e.g. a labelled `.type-chip`). */
export function TypeIcon({ type }) {
  const Icon = typeIcon(type);
  return <Icon aria-hidden="true" />;
}
