import React, { useEffect, useState } from "react";
import { FileDown } from "lucide-react";
import { toast } from "./ui/toast";

// Finding 20: files dropped on the desktop window become project sources. A browser never sees a dropped
// file's path, so the window's own drop event adds them (backend/desktop/host.py) and reports here.
export const DROP_EVENT = "pbibrain-sources-dropped";

/** What a drop did, in one line. */
export function dropMessage(result) {
  if (!result?.ok) return { tone: "error", text: result?.error || "The dropped files could not be added." };
  const added = result.added?.length || 0;
  const skipped = result.skipped ? ` ${result.skipped} other ${result.skipped === 1 ? "file was" : "files were"} left out.` : "";
  if (!added) return { tone: "info", text: `The dropped sources are already in this project.${skipped}` };
  return { tone: "success", text: `Added ${added} ${added === 1 ? "source" : "sources"}. Scan to read ${added === 1 ? "it" : "them"}.${skipped}` };
}

const carriesFiles = (event) => [...(event.dataTransfer?.types || [])].includes("Files");

/** The drop target over the whole window while files are dragged in, and the result of a drop. */
export function SourceDrop({ onAdded }) {
  const [over, setOver] = useState(false);
  useEffect(() => {
    let depth = 0;
    const enter = (event) => { if (!carriesFiles(event)) return; depth += 1; setOver(true); };
    const leave = (event) => { if (!carriesFiles(event)) return; depth = Math.max(0, depth - 1); if (!depth) setOver(false); };
    const drop = () => { depth = 0; setOver(false); };
    const done = (event) => {
      const message = dropMessage(event.detail);
      (toast[message.tone] || toast)(message.text);
      if (event.detail?.ok && event.detail.added?.length) onAdded?.();
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    window.addEventListener(DROP_EVENT, done);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
      window.removeEventListener(DROP_EVENT, done);
    };
  }, [onAdded]);
  if (!over) return null;
  return <div className="source-drop" role="status" aria-live="polite">
    <div className="source-drop-target"><FileDown aria-hidden="true" /><strong>Drop to add sources</strong><span>.pbip, .bim or model .json</span></div>
  </div>;
}
