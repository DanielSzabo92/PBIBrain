import React from "react";
import { Button } from "./ui/button";
import { objectName } from "../presentation";

const groups = { columns: "Columns", measures: "Measures", calculations: "Visual calculations", visual_filters: "Visual filters", page_filters: "Page filters · inherited", report_filters: "Report filters · inherited" };

export default function VisualBindings({ bindings, onSelect }) {
  if (!bindings) return null;
  return <div className="visual-bindings">{Object.entries(groups).map(([key, label]) => <section className="detail-section" key={key}>
    <h3>{label} <span>{bindings[key]?.length || 0}</span></h3>
    {bindings[key]?.length ? bindings[key].map((item) => <Button key={item.id} variant="ghost" className="detail-related" onClick={() => onSelect(item)}>{objectName(item)}</Button>) : <p className="muted-copy">None recorded.</p>}
  </section>)}</div>;
}
