import React, { useEffect, useRef, useState } from "react";
import { RefreshCw, TriangleAlert, X } from "lucide-react";
import { Button } from "./ui/button";
import { PENDING_POLL_MS, pendingHeadline, pendingKey, pendingLines, pendingTone, showsPending } from "../pendingChanges";

/**
 * Warning for project files changed outside the app (issue #17). It polls the pending-changes
 * route; the backend hashes the files (unchanged files are not read again) and only rescans
 * a graph preview when something changed. Nothing here writes anything.
 */
export default function PendingChanges({ transport, scanning, onScan }) {
  const [reply, setReply] = useState(null);
  const [dismissed, setDismissed] = useState("");
  const active = useRef(true);

  useEffect(() => {
    active.current = true;
    if (typeof transport?.getPendingChanges !== "function") return undefined;
    let timer = null;
    const poll = async () => {
      try {
        const value = await transport.getPendingChanges();
        if (active.current) setReply(value);
      } catch {
        // An app without a project, or a closed server, has no pending changes to show.
      }
      if (active.current) timer = setTimeout(poll, PENDING_POLL_MS);
    };
    poll();
    return () => {
      active.current = false;
      clearTimeout(timer);
    };
  }, [transport]);

  if (scanning || !showsPending(reply) || dismissed === pendingKey(reply)) return null;
  const { lines, more } = pendingLines(reply);
  return (
    <section className="pending-banner" data-tone={pendingTone(reply)} role="status" aria-live="polite" aria-label="Files changed outside PBIBrain">
      <TriangleAlert aria-hidden="true" />
      <div className="pending-body">
        <p>{pendingHeadline(reply)}</p>
        {lines.length ? <ul>{lines.map((line) => <li key={line}>{line}</li>)}{more ? <li>{`and ${more} more`}</li> : null}</ul> : null}
      </div>
      {onScan ? <Button variant="outline" size="sm" onClick={onScan}><RefreshCw aria-hidden="true" />Rescan</Button> : null}
      <Button variant="ghost" size="icon-sm" onClick={() => setDismissed(pendingKey(reply))} aria-label="Dismiss until the files change again"><X aria-hidden="true" /></Button>
    </section>
  );
}
