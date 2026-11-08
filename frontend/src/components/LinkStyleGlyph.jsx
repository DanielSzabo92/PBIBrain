import React from "react";

const DASHES = {
  factual: {},
  inferred: { strokeDasharray: "6 4" },
  observed: { x1: "1.5", strokeDasharray: "1.5 3", strokeLinecap: "round" },
  source: {},
  suggested: { strokeDasharray: "6 4" },
};

/** The short line sample for one graph link style in the legend. Decorative. */
export function LinkStyleGlyph({ kind = "factual" }) {
  const dash = DASHES[kind] || DASHES.factual;
  return <svg aria-hidden="true" viewBox="0 0 24 4"><line x1="1" y1="2" x2="23" y2="2" {...dash} /></svg>;
}

