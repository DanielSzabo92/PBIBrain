import React, { useEffect, useState } from "react";
import { Download, TriangleAlert } from "lucide-react";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Checkbox } from "./ui/checkbox";
import { Label } from "./ui/label";
import { SegmentedControl } from "./ui/segmented-control";
import { DOC_SECTIONS, exportBlocker, exportRequest, formatSize, replyBytes } from "../documentationExport";

function CheckList({ legend, idPrefix, items, chosen, onChange, disabled }) {
  const all = items.length > 0 && items.every((item) => chosen.has(item.id));
  const toggle = (id, on) => {
    const next = new Set(chosen);
    if (on) next.add(id); else next.delete(id);
    onChange(next);
  };
  return <fieldset className="doc-export-group" disabled={disabled}>
    <legend>{legend}</legend>
    {items.length > 1 ? <Button type="button" variant="ghost" size="sm" className="doc-export-all" onClick={() => onChange(all ? new Set() : new Set(items.map((item) => item.id)))}>{all ? "Clear all" : "Select all"}</Button> : null}
    {items.length ? items.map((item) => <div key={item.id} className="doc-export-check">
      <Checkbox id={`${idPrefix}-${item.id}`} checked={chosen.has(item.id)} onCheckedChange={(value) => toggle(item.id, value === true)} />
      <Label htmlFor={`${idPrefix}-${item.id}`}>{item.name || item.id}</Label>
    </div>) : <p className="muted-copy compact">None in this project.</p>}
  </fieldset>;
}

/** File › Export documentation…: PDF or Markdown of the last scan, built by the running server (issue #15). */
export default function DocumentationExport({ overview, transport, scanning }) {
  const models = overview?.model_objects || [];
  const reports = overview?.report_objects || [];
  const [format, setFormat] = useState("pdf");
  const [chosenModels, setChosenModels] = useState(() => new Set(models.map((item) => item.id)));
  const [chosenReports, setChosenReports] = useState(() => new Set(reports.map((item) => item.id)));
  const [sections, setSections] = useState(() => new Set(DOC_SECTIONS.map(([key]) => key)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const modelKey = models.map((item) => item.id).join("\n");
  const reportKey = reports.map((item) => item.id).join("\n");
  // A rescan can add or remove models and reports: start again from everything.
  useEffect(() => { setChosenModels(new Set(models.map((item) => item.id))); }, [modelKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setChosenReports(new Set(reports.map((item) => item.id))); }, [reportKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const scope = { format, models: chosenModels, reports: chosenReports, sections };
  const blocker = exportBlocker(scope);
  const run = async () => {
    setBusy(true); setError(""); setNotice("");
    try {
      const reply = await transport.exportDocumentation(exportRequest(scope, overview));
      const url = URL.createObjectURL(new Blob([replyBytes(reply)], { type: reply.content_type }));
      const link = document.createElement("a");
      link.href = url;
      link.download = reply.filename;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice(`${reply.filename} prepared (${formatSize(reply.bytes)}).`);
    } catch (cause) {
      setError(cause.message || "Documentation could not be exported. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return <Card className="panel doc-export-panel">
    <div className="settings-panel-head"><div><h2>Export documentation</h2><p className="muted-copy">A document of the last scan: model diagram, measures with DAX, report pages and fields, lineage, and what was not checked. The app can stay open.</p></div></div>
    {models.length || reports.length ? <>
      <div className="doc-export-format">
        <Label id="doc-export-format-label">Format</Label>
        <SegmentedControl mode="radio" aria-label="Format" value={format} onValueChange={setFormat} disabled={busy}
          options={[{ value: "pdf", label: "PDF" }, { value: "markdown", label: "Markdown" }]} />
      </div>
      <div className="doc-export-scope">
        <CheckList legend="Models" idPrefix="doc-model" items={models} chosen={chosenModels} onChange={setChosenModels} disabled={busy} />
        <CheckList legend="Reports" idPrefix="doc-report" items={reports} chosen={chosenReports} onChange={setChosenReports} disabled={busy} />
        <CheckList legend="Sections" idPrefix="doc-section" items={DOC_SECTIONS.map(([id, name]) => ({ id, name }))} chosen={sections} onChange={setSections} disabled={busy} />
      </div>
      <p className="muted-copy compact">Uses the last scan. Rescan after editing source files. Exporting the same scan again gives the same file except the generation time.</p>
      <div className="doc-export-actions" data-ui-actions="">
        <Button onClick={run} disabled={busy || scanning || Boolean(blocker)} aria-describedby={blocker ? "doc-export-blocker" : undefined}><Download />{busy ? "Exporting…" : format === "pdf" ? "Export PDF" : "Export Markdown"}</Button>
        {blocker ? <p id="doc-export-blocker" className="muted-copy compact">{blocker}</p> : null}
      </div>
      {scanning ? <p role="status" className="loading-label">Waiting for scan…</p> : null}
      {error ? <div role="alert" className="inline-error"><TriangleAlert aria-hidden="true" /><p>{error}</p></div> : null}
      {notice ? <p role="status" className="success-text">{notice}</p> : null}
    </> : <p className="muted-copy">Scan a model or report to export its documentation.</p>}
  </Card>;
}
