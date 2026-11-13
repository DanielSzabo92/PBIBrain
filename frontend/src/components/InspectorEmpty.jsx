import React from "react";
import { ArrowRight, Clock } from "lucide-react";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { TypeGlyph } from "./TypeGlyph";
import { displayKeys } from "../shortcuts";

// Nothing is selected yet: the tree on the left is the way in, so this side shows content only —
// what was inspected last and the models with the reports built on them.
export default function InspectorEmpty({ overview, colors, recentObjects = [], onSelect }) {
  const models = overview?.model_objects || [];
  const reports = overview?.report_objects || [];
  const reportsOf = (modelId) => reports.filter((report) => report.model_id === modelId);
  const loose = reports.filter((report) => !models.some((model) => model.id === report.model_id));

  return (
    <div className="inspector-empty-state" data-ui-stack="">
      <h1 className="sr-only" tabIndex={-1}>Inspector</h1>
      {recentObjects && recentObjects.length > 0 ? (
        <Card className="panel inspector-empty-section">
          <div className="inspector-section-header">
            <Clock aria-hidden="true" className="size-4" />
            <h2>Recently inspected</h2>
          </div>
          <div className="inspector-recent-grid">
            {recentObjects.slice(0, 8).map((obj) => (
              <Button key={obj.id} variant="ghost" className="inspector-recent-card" onClick={() => onSelect(obj.id)}>
                <TypeGlyph node={obj} colors={colors} size="sm" />
                <div className="inspector-recent-copy">
                  <strong>{obj.name || obj.id}</strong>
                  <small>{obj.type || "Object"}</small>
                </div>
                <ArrowRight aria-hidden="true" className="inspector-recent-arrow" />
              </Button>
            ))}
          </div>
        </Card>
      ) : null}

      {models.length > 0 || loose.length > 0 ? (
        <Card className="panel inspector-empty-section">
          <table className="inspector-home-table">
            <thead><tr><th scope="col">Model</th><th scope="col">Reports</th></tr></thead>
            <tbody>
              {models.map((model) => {
                const built = reportsOf(model.id);
                return <tr key={model.id} onClick={() => onSelect(model.id)}>
                  <td><TypeGlyph node={{ type: "MODEL" }} colors={colors} size="sm" /><Button variant="link" size="sm" onClick={(event) => { event.stopPropagation(); onSelect(model.id); }}>{model.name || model.id}</Button></td>
                  <td title={built.map((report) => report.name).join("\n") || undefined}>{built.length || ""}</td>
                </tr>;
              })}
              {loose.map((report) => <tr key={report.id} onClick={() => onSelect(report.id)}>
                <td><TypeGlyph node={{ type: "REPORT" }} colors={colors} size="sm" /><Button variant="link" size="sm" onClick={(event) => { event.stopPropagation(); onSelect(report.id); }}>{report.name || report.id}</Button></td>
                <td />
              </tr>)}
            </tbody>
          </table>
        </Card>
      ) : null}
      <p className="muted inspector-home-hint">Pick an object in the tree, or press <kbd>{displayKeys("Ctrl+K")}</kbd> to find one by name.</p>
    </div>
  );
}
