import React from "react";
import { ArrowRight, Clock, Layers, ScanSearch, Search, Waypoints } from "lucide-react";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { TypeGlyph } from "./TypeGlyph";
import { displayKeys } from "../shortcuts";

export default function InspectorEmpty({
  overview,
  colors,
  recentObjects = [],
  onSelect,
  onOpenSearch,
  onOpenPalette,
  onOpenGraph,
}) {
  const models = overview?.model_objects || [];
  const totalObjects = overview?.counts?.nodes ?? overview?.objects ?? 0;

  return (
    <div className="inspector-empty-state" data-ui-stack="">
      <div className="page-heading">
        <div className="page-heading-copy">
          <p className="eyebrow">Inspector</p>
          <h1>Object Inspector</h1>
          <p className="page-description">
            Inspect DAX formulas, dependencies, visual bindings, and semantic suggestions for any model or report object.
          </p>
        </div>
        <div className="page-heading-action" data-ui-actions="">
          <Button onClick={onOpenPalette}>
            <ScanSearch aria-hidden="true" />
            Find object ({displayKeys("Ctrl+K")})
          </Button>
          <Button variant="outline" onClick={onOpenSearch}>
            <Search aria-hidden="true" />
            Search all ({displayKeys("Ctrl+2")})
          </Button>
          <Button variant="outline" onClick={onOpenGraph}>
            <Waypoints aria-hidden="true" />
            Graph ({displayKeys("Ctrl+3")})
          </Button>
        </div>
      </div>

      {recentObjects && recentObjects.length > 0 ? (
        <Card className="panel inspector-empty-section">
          <div className="inspector-section-header">
            <Clock aria-hidden="true" className="size-4" />
            <h2>Recently inspected objects</h2>
          </div>
          <div className="inspector-recent-grid">
            {recentObjects.slice(0, 8).map((obj) => (
              <Button
                key={obj.id}
                variant="ghost"
                className="inspector-recent-card"
                onClick={() => onSelect(obj.id)}
              >
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

      <Card className="panel inspector-empty-section">
        <div className="inspector-section-header">
          <Layers aria-hidden="true" className="size-4" />
          <h2>How to inspect an object</h2>
        </div>
        <div className="inspector-guide-grid">
          <div className="inspector-guide-card">
            <span className="inspector-guide-num">1</span>
            <strong>Quick jump with Command Palette</strong>
            <p>Press <kbd>{displayKeys("Ctrl+K")}</kbd> from anywhere to type the name of any measure, column, table, or visual.</p>
          </div>
          <div className="inspector-guide-card">
            <span className="inspector-guide-num">2</span>
            <strong>Explore from the Graph</strong>
            <p>Double-click or press <kbd>Enter</kbd> on any node in the graph view to open it directly in the Inspector.</p>
          </div>
          <div className="inspector-guide-card">
            <span className="inspector-guide-num">3</span>
            <strong>Parametric search</strong>
            <p>Use the Search page (<kbd>{displayKeys("Ctrl+2")}</kbd>) to filter by model, report, or specific object type.</p>
          </div>
        </div>
      </Card>

      {models.length > 0 ? (
        <Card className="panel inspector-empty-section">
          <div className="inspector-section-header">
            <Layers aria-hidden="true" className="size-4" />
            <h2>Semantic models ({models.length})</h2>
          </div>
          <div className="inspector-models-list">
            {models.map((model) => (
              <Button
                key={model.id}
                variant="outline"
                size="sm"
                className="inspector-model-pill"
                onClick={() => onSelect(model.id)}
              >
                <TypeGlyph node={{ type: "MODEL" }} colors={colors} size="sm" />
                <span>{model.name || model.id}</span>
              </Button>
            ))}
          </div>
        </Card>
      ) : null}
    </div>
  );
}
