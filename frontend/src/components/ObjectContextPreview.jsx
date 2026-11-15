import * as React from "react";
import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { HoverCard, HoverCardTrigger, HoverCardContent } from "./ui/hover-card";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "./ui/sheet";
import { Button } from "./ui/button";
import { TypeGlyph } from "./TypeGlyph";
import { typeLabel } from "../graphPresentation";
import { byId } from "../presentation";
import { highlightDax } from "../dax";
import { objectName, readableText } from "../presentation";

const labelFor = (node) => objectName(node);

export default function ObjectContextPreview({
  node,
  nodes = [],
  links = null,
  colors,
  onSelect,
  children,
}) {
  const [sheetOpen, setSheetOpen] = useState(false);

  if (!node) return children || null;

  const properties = node.properties || {};
  const expression = node.expression ?? properties.expression;
  const description = readableText(node.description || properties.description);

  // ``links`` counts the objects that use this one and that it uses, and names the first few each way (the server's review rows).
  const resolveNode = (id) => byId(nodes, id);
  const incomingCount = links?.incoming || 0;
  const outgoingCount = links?.outgoing || 0;
  const incomingNames = (links?.used_by || []).map(resolveNode).filter(Boolean).slice(0, 3);
  const outgoingNames = (links?.depends_on || []).map(resolveNode).filter(Boolean).slice(0, 3);

  const previewContent = (
    <div className="object-context-preview">
      <div className="context-preview-header">
        <TypeGlyph node={node} colors={colors} size="sm" />
        <div className="context-preview-title">
          <strong>{labelFor(node)}</strong>
          <small className="context-preview-type">{typeLabel(node.type)}</small>
        </div>
      </div>

      {description ? (
        <p className="context-preview-description">{description}</p>
      ) : null}

      {expression ? (
        <div className="context-preview-expression">
          <div className="context-preview-code-header">
            <span className="code-lang">DAX</span>
            <span>Formula</span>
          </div>
          <pre className="context-preview-code" tabIndex={0}>
            <code>{highlightDax(expression)}</code>
          </pre>
        </div>
      ) : null}

      <div className="context-preview-usage">
        {incomingCount > 0 ? (
          <div className="usage-stat">
            <span className="stat-label">Used by {incomingCount} {incomingCount === 1 ? "object" : "objects"}:</span>
            <ul className="stat-list">
              {incomingNames.map((n) => (
                <li key={n.id}>
                  <span>{labelFor(n)}</span>
                  <small className="stat-type">({typeLabel(n.type)})</small>
                </li>
              ))}
              {incomingCount > 3 ? <li className="stat-more">+{incomingCount - 3} more</li> : null}
            </ul>
          </div>
        ) : (
          <p className="muted-copy compact">No direct dependents found.</p>
        )}

        {outgoingCount > 0 ? (
          <div className="usage-stat">
            <span className="stat-label">Depends on {outgoingCount} {outgoingCount === 1 ? "object" : "objects"}:</span>
            <ul className="stat-list">
              {outgoingNames.map((n) => (
                <li key={n.id}>
                  <span>{labelFor(n)}</span>
                  <small className="stat-type">({typeLabel(n.type)})</small>
                </li>
              ))}
              {outgoingCount > 3 ? <li className="stat-more">+{outgoingCount - 3} more</li> : null}
            </ul>
          </div>
        ) : null}
      </div>

      <div className="context-preview-footer">
        {onSelect ? (
          <Button
            variant="link"
            size="sm"
            className="context-preview-inspect"
            onClick={() => {
              setSheetOpen(false);
              onSelect(node.id, "inspector");
            }}
          >
            Open in Inspector <ArrowRight className="size-3.5" aria-hidden="true" />
          </Button>
        ) : null}
      </div>
    </div>
  );

  return (
    <>
      <HoverCard>
        <HoverCardTrigger asChild>
          {children}
        </HoverCardTrigger>
        <HoverCardContent className="object-preview-hover-content" align="start" sideOffset={8}>
          {previewContent}
        </HoverCardContent>
      </HoverCard>

      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent side="right" className="object-context-sheet">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <TypeGlyph node={node} colors={colors} size="sm" />
              <span>{labelFor(node)}</span>
            </SheetTitle>
            <SheetDescription>{typeLabel(node.type)} context, formula, and usage</SheetDescription>
          </SheetHeader>
          <div className="sheet-body p-4">
            {previewContent}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
