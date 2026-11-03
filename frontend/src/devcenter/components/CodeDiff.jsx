// Modal dialog for code differences between target and donor (UI design 4.3).
// All text follows ASD-STE100 rules.
import React, { useEffect, useRef, useState } from "react";
import { LoaderCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { t } from "../copy.js";

// Basic line-by-line diff.
export function computeDiff(leftText = "", rightText = "") {
  const leftLines = String(leftText || "").split("\n");
  const rightLines = String(rightText || "").split("\n");
  const max = Math.max(leftLines.length, rightLines.length);

  const left = [];
  const right = [];
  const unified = [];

  for (let i = 0; i < max; i++) {
    const l = leftLines[i];
    const r = rightLines[i];

    if (l !== undefined && r !== undefined) {
      if (l === r) {
        left.push({ line: i + 1, mark: " ", text: l, type: "same" });
        right.push({ line: i + 1, mark: " ", text: r, type: "same" });
        unified.push({ line: i + 1, mark: " ", text: l, type: "same" });
      } else {
        left.push({ line: i + 1, mark: "-", text: l, type: "del" });
        right.push({ line: i + 1, mark: "+", text: r, type: "add" });
        unified.push({ line: i + 1, mark: "-", text: l, type: "del" });
        unified.push({ line: i + 1, mark: "+", text: r, type: "add" });
      }
    } else if (l !== undefined) {
      left.push({ line: i + 1, mark: "-", text: l, type: "del" });
      unified.push({ line: i + 1, mark: "-", text: l, type: "del" });
    } else if (r !== undefined) {
      right.push({ line: i + 1, mark: "+", text: r, type: "add" });
      unified.push({ line: i + 1, mark: "+", text: r, type: "add" });
    }
  }

  return { left, right, unified };
}

export default function CodeDiff({
  row,
  initialDonor,
  donors = [],
  targetName = "Target",
  compareMode = "default",
  onClose,
  http,
  triggerElement,
}) {
  const [selectedDonor, setSelectedDonor] = useState(() => initialDonor || donors[0] || null);
  const [diff, setDiff] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const closeButtonRef = useRef(null);

  // Focus close button on mount.
  useEffect(() => {
    closeButtonRef.current?.focus();
  }, []);

  // Return focus to trigger element on unmount.
  useEffect(() => {
    return () => {
      triggerElement?.focus?.();
    };
  }, [triggerElement]);

  // Fetch diff for row and donor.
  useEffect(() => {
    if (!row || !selectedDonor || !http) return;
    let active = true;
    setLoading(true);
    setError(null);

    http
      .getRowDiff(row.row_key, selectedDonor.source_id)
      .then((data) => {
        if (!active) return;
        setDiff(data);
        setLoading(false);
      })
      .catch((err) => {
        if (!active) return;
        setError(err);
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [row, selectedDonor, http]);

  // Handle Escape key.
  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown, { capture: true });
    return () => window.removeEventListener("keydown", onKeyDown, { capture: true });
  }, [onClose]);

  const targetCode = diff?.target ?? diff?.reference_text ?? "";
  const sourceCode = diff?.source ?? diff?.source_text ?? "";
  const { left, right, unified } = computeDiff(targetCode, sourceCode);

  const isWide = typeof window !== "undefined" ? window.innerWidth >= 1280 : true;

  const donorSegments = donors.map((d) => ({
    value: d.source_id,
    label: d.display_name || d.name,
  }));

  const modeText = compareMode === "strict" ? t("compare.footer.strict") : t("compare.footer.default");

  return (
    <div className="ui-scrim" onClick={onClose} role="presentation">
      <div
        className="ui-dialog dc-diff-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dc-diff-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="dc-diff-head">
          <div>
            <h2 id="dc-diff-title" className="dc-diff-title">
              {t("compare.diff.title", { name: row.name })}
            </h2>
            <span className="dc-diff-sub">{modeText}, DAX and TMDL</span>
          </div>

          <span className="dc-spacer" />

          {donorSegments.length > 1 ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--text-2)]">{t("compare.diff.with")}</span>
              <SegmentedControl
                options={donorSegments}
                value={selectedDonor?.source_id}
                onValueChange={(val) => {
                  const found = donors.find((d) => d.source_id === val);
                  if (found) setSelectedDonor(found);
                }}
              />
            </div>
          ) : null}

          <Button
            ref={closeButtonRef}
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label="Close code diff"
          >
            <X className="w-4 h-4" />
          </Button>
        </header>

        {loading ? (
          <div className="flex-1 flex items-center justify-center p-8 text-[var(--text-2)] gap-2">
            <LoaderCircle className="spin w-5 h-5" aria-hidden="true" />
            <span>Loading code differences</span>
          </div>
        ) : error ? (
          <div className="flex-1 flex flex-col items-center justify-center p-8 gap-2 text-[var(--bad)]">
            <p>{error.message || "Could not load code difference."}</p>
          </div>
        ) : (
          <div className={`dc-diff-body ${isWide ? "split" : ""}`}>
            {isWide ? (
              <>
                <div className="dc-diff-col">
                  <h3 className="dc-diff-col-head">{targetName} (target)</h3>
                  {left.map((item, idx) => (
                    <div key={`l-${idx}`} className={`dc-diff-line ${item.type}`}>
                      <span className="dc-diff-ln">{item.line}</span>
                      <span className="dc-diff-mk" aria-hidden="true">
                        {item.mark}
                      </span>
                      <span>
                        {item.type === "del" ? (
                          <span className="sr-only">{t("compare.diff.removed")}</span>
                        ) : null}
                        {item.text}
                      </span>
                    </div>
                  ))}
                </div>

                <div className="dc-diff-col">
                  <h3 className="dc-diff-col-head">{selectedDonor?.display_name || selectedDonor?.name}</h3>
                  {right.map((item, idx) => (
                    <div key={`r-${idx}`} className={`dc-diff-line ${item.type}`}>
                      <span className="dc-diff-ln">{item.line}</span>
                      <span className="dc-diff-mk" aria-hidden="true">
                        {item.mark}
                      </span>
                      <span>
                        {item.type === "add" ? (
                          <span className="sr-only">{t("compare.diff.added")}</span>
                        ) : null}
                        {item.text}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="dc-diff-col">
                <h3 className="dc-diff-col-head">
                  {targetName} to {selectedDonor?.display_name || selectedDonor?.name}
                </h3>
                {unified.map((item, idx) => (
                  <div key={`u-${idx}`} className={`dc-diff-line ${item.type}`}>
                    <span className="dc-diff-ln">{item.line}</span>
                    <span className="dc-diff-mk" aria-hidden="true">
                      {item.mark}
                    </span>
                    <span>
                      {item.type === "del" ? (
                        <span className="sr-only">{t("compare.diff.removed")}</span>
                      ) : item.type === "add" ? (
                        <span className="sr-only">{t("compare.diff.added")}</span>
                      ) : null}
                      {item.text}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
