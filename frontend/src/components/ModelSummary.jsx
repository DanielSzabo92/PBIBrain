import React, { useEffect, useRef, useState } from "react";
import { Copy, Download, RefreshCw, Sparkles, TriangleAlert } from "lucide-react";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Label } from "./ui/label";
import { NativeSelect } from "./ui/native-select";

export default function ModelSummary({ overview, transport, scanning }) {
  const models = overview?.model_objects || [];
  const [selectedId, setSelectedId] = useState("");
  const modelId = models.some((item) => item.id === selectedId) ? selectedId : models[0]?.id || "";
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const preview = useRef(null);

  useEffect(() => {
    let disposed = false;
    setResult(null); setError(""); setNotice("");
    if (!modelId || scanning) { setLoading(false); return undefined; }
    setLoading(true);
    transport.getModelSummary(modelId).then((value) => {
      if (!disposed) setResult(value);
    }).catch((cause) => {
      if (!disposed) setError(cause.message || "Summary could not be loaded. Try again.");
    }).finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [modelId, overview, transport, scanning, revision]);

  const ready = !loading && !scanning && result?.model_id === modelId;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(result.markdown);
      setNotice("Context copied.");
    } catch {
      preview.current?.focus(); preview.current?.select();
      setNotice("Copy unavailable. Preview selected; press Ctrl+C, or save the file.");
    }
  };
  const save = () => {
    const url = URL.createObjectURL(new Blob([result.markdown], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "model-context.md";
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice("Context file prepared.");
  };
  const lines = ready ? result.markdown.split("\n").length : 0;

  return <Card className="panel model-summary-panel">
    <div className="settings-panel-head"><span className="icon-tile" aria-hidden="true"><Sparkles /></span><div><p className="eyebrow">Agent context</p><h2>Model summary</h2><p className="muted-copy">Model overview, exact formulas, relationships, and reviewed meanings in one Markdown file.</p></div></div>
    {models.length ? <>
      <div className="model-summary-toolbar">
        <div className="model-summary-choice"><Label htmlFor="summary-model">Semantic model</Label><NativeSelect id="summary-model" value={modelId} onChange={(event) => setSelectedId(event.target.value)} disabled={scanning}>
          {models.map((item) => <option key={item.id} value={item.id}>{item.name || item.id}</option>)}
        </NativeSelect></div>
        <div className="model-summary-actions">
          <Button variant="ghost" size="sm" onClick={() => setRevision((value) => value + 1)} disabled={loading || scanning}><RefreshCw className={loading ? "spin" : ""} />Refresh</Button>
          <Button variant="outline" size="sm" onClick={copy} disabled={!ready}><Copy />Copy context</Button>
          <Button size="sm" onClick={save} disabled={!ready}><Download />Save Markdown</Button>
        </div>
      </div>
      <p className="muted-copy compact">Uses the last scan. Rescan after editing source files. Unknowns and inferred meanings stay labelled.</p>
      {loading || scanning ? <p role="status" className="loading-label">{scanning ? "Waiting for scan…" : "Loading summary…"}</p> : null}
      {error ? <div role="alert" className="inline-error"><TriangleAlert aria-hidden="true" /><p>{error}</p><Button variant="outline" size="sm" onClick={() => setRevision((value) => value + 1)}>Retry summary</Button></div> : null}
      {ready ? <div className="code-window"><div className="code-window-bar"><Label htmlFor="model-summary-preview">Markdown preview</Label><span className="code-window-meta">model-context.md · {lines.toLocaleString()} lines</span></div><textarea ref={preview} id="model-summary-preview" className="model-summary-preview" value={result.markdown} readOnly spellCheck={false} /></div> : null}
      {notice ? <p role="status" className="success-text">{notice}</p> : null}
    </> : <p className="muted-copy">Scan a semantic model to create its context file.</p>}
  </Card>;
}
