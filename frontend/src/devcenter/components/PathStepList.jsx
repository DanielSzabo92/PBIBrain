// PathStepList (UI design 4.5, 6.1): the steps of one impact path, with the edge phrase of each step.
import React from "react";
import { ArrowRight } from "lucide-react";

export default function PathStepList({ steps = [], label }) {
  if (!steps.length) return null;
  return (
    <ol className="dc-path-steps" aria-label={label}>
      {steps.map((step, index) => (
        <li key={`${step.object_id}-${index}`} className="dc-path-step">
          {index > 0 ? (
            <span className="dc-path-edge">
              <ArrowRight aria-hidden="true" />
              {step.edge_phrase}
            </span>
          ) : null}
          <span className="dc-path-object">
            <span className="dc-path-type">{step.type}</span>
            <span className="dc-path-name">{step.name}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}
