import React from "react";
import { ChevronRight } from "lucide-react";
import { Button } from "./ui/button";
import { objectName } from "../presentation";

const groups = { columns: "Columns", measures: "Measures", calculations: "Visual calculations", visual_filters: "Visual filters", page_filters: "Page filters · inherited", report_filters: "Report filters · inherited" };

export default function VisualBindings({ bindings, onSelect }) {
  if (!bindings) return null;
  return <div className="visual-bindings">{Object.entries(groups).map(([key, label]) => <section className={`detail-section ${bindings[key]?.length ? "" : "is-empty"}`} key={key}>
    <h3>{label} <span className="count-pill">{bindings[key]?.length || 0}</span></h3>
    {bindings[key]?.length ? bindings[key].map((item) => <Button key={item.id} variant="ghost" className="detail-related binding-row" onClick={() => onSelect(item)}><span>{objectName(item)}</span><ChevronRight className="row-chevron" aria-hidden="true" /></Button>) : <p className="muted-copy compact">None recorded.</p>}
  </section>)}</div>;
}
