import React from "react";
import { LinkStyleGlyph } from "./LinkStyleGlyph";
import { cn } from "@/lib/utils";

/**
 * Canonical provenance legend (PRODUCT.md principle 2).
 * Shows the single provenance trio: Factual, Inferred, and Observed.
 */
export function ProvenanceLegend({ className = "", ariaLabel = "Link styles" }) {
  return (
    <ul className={cn("graph-evidence-key", className)} aria-label={ariaLabel}>
      <li><LinkStyleGlyph kind="factual" />Factual</li>
      <li><LinkStyleGlyph kind="inferred" />Inferred</li>
      <li><LinkStyleGlyph kind="observed" />Observed</li>
    </ul>
  );
}

export default ProvenanceLegend;
