// Impact wireframe view (UI design 4.5, 7.3, A4, A12): report trigger, page list, scaled canvas, "Drawing | Visual list".
// Each visual shows one status with pattern, icon, and word. Tab goes in reading order. Offer visuals of a donor report have a checkbox.
import React, { useMemo, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Notice } from "@/components/ui/notice";
import { EmptyState, Skeleton } from "@/components/ui/result-panel";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Select } from "@/components/ui/select";
import { t } from "../../copy.js";
import { useResource } from "../../useDevCenter.js";
import WireframeBox, { WireStatus } from "../../components/WireframeBox.jsx";
import { readingOrder, wireStatusWord, wireVisualLabel } from "./impactModel.js";

const CANVAS_WIDTH = 720;

export default function ImpactWireframe({ reports, report, onReport, pageId, onPage, mode, onMode, selectedVisualId, onOpenVisual, offers, onOffer, offerDisabled }) {
  const wireframe = useResource("wireframe", { report: report || "target" });
  const canvasRef = useRef(null);
  const data = wireframe.data;
  const pages = data?.pages ?? [];
  const page = pages.find((entry) => entry.id === pageId) ?? pages[0] ?? null;
  const visuals = useMemo(() => readingOrder(page?.visuals ?? []), [page]);
  const donor = report && report !== "target";
  const offerById = useMemo(() => new Map((offers ?? []).map((offer) => [offer.id, offer])), [offers]);
  const offerFor = (visual) => (donor ? offerById.get(visual.id) ?? null : null);
  const scale = page ? CANVAS_WIDTH / Math.max(1, page.width) : 1;

  return (
    <div className="dc-wire">
      <div className="dc-wire-bar">
        <Select label={t("impact.wireframe.report")} value={report || "target"} onValueChange={onReport} options={reports} className="dc-wire-report" />
        <SegmentedControl
          aria-label={t("impact.wireframe.mode")}
          value={mode}
          onValueChange={onMode}
          options={[{ value: "drawing", label: t("impact.wireframe.drawing") }, { value: "list", label: t("impact.wireframe.list") }]}
        />
      </div>
      <p className="dc-wire-priority">{t("impact.wireframe.priority")}</p>
      {wireframe.status === "loading" && !data ? <Skeleton lines={4} label={t("impact.wireframe.loading")} /> : null}
      {wireframe.status === "error" ? (
        <Notice tone="bad" actions={<Button variant="outline" size="sm" onClick={wireframe.reload}>{t("shared.try_again")}</Button>}>
          {t("impact.wireframe.fail")}
        </Notice>
      ) : null}
      {data && !pages.length ? <EmptyState headingLevel={2} title={t("impact.wireframe.empty")} /> : null}
      {page ? (
        <div className="dc-wire-body">
          <nav className="dc-wire-pages" aria-label={t("impact.wireframe.pages")}>
            <ul>
              {pages.map((entry) => (
                <li key={entry.id}>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="dc-wire-page"
                    aria-current={entry.id === page.id ? "page" : undefined}
                    onClick={() => onPage(entry.id)}>
                    {entry.name}
                  </Button>
                </li>
              ))}
            </ul>
          </nav>
          {mode === "list" ? (
            <ol className="dc-wire-list" aria-label={t("impact.wireframe.canvas", { name: page.name })}>
              {visuals.map((visual) => {
                const offer = offerFor(visual);
                return (
                  <li key={visual.id} className="dc-wire-list-item" data-status={visual.status}>
                    {offer ? (
                      <Checkbox
                        size="target"
                        checked={Boolean(offer.selected)}
                        disabled={offerDisabled}
                        aria-label={t("impact.wireframe.offer", { title: visual.title })}
                        onCheckedChange={(checked) => onOffer(offer, checked === true)}
                      />
                    ) : null}
                    <button type="button" className="dc-wire-list-open" aria-label={wireVisualLabel(visual)} onClick={() => onOpenVisual(visual)}>
                      {visual.title}
                    </button>
                    <span className="dc-wire-list-type">{visual.type}</span>
                    {visual.status === "unchanged" ? <span className="dc-wire-list-plain">{wireStatusWord("unchanged")}</span> : <WireStatus status={visual.status} />}
                  </li>
                );
              })}
            </ol>
          ) : (
            <div
              ref={canvasRef}
              className="dc-wire-canvas"
              role="group"
              aria-label={t("impact.wireframe.canvas", { name: page.name })}
              style={{ width: CANVAS_WIDTH, height: Math.round(page.height * scale) }}>
              {visuals.map((visual) => (
                <WireframeBox
                  key={visual.id}
                  visual={visual}
                  scale={scale}
                  selected={visual.id === selectedVisualId}
                  offer={offerFor(visual)}
                  offerDisabled={offerDisabled}
                  onOpen={onOpenVisual}
                  onOffer={onOffer}
                />
              ))}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
