import React from "react";
import { ChevronRight } from "lucide-react";
import { Button } from "./ui/button";
import { objectName } from "../presentation";

const groups = { columns: "Columns", measures: "Measures", calculations: "Visual calculations", visual_filters: "Visual filters", page_filters: "Page filters · inherited", report_filters: "Report filters · inherited" };

const FIELD_GROUPS = new Set(["columns", "measures"]);

/** One field row; in a well it also says how the visual aggregates or renames the field. */
function Field({ item, onSelect }) {
  const note = [item.aggregation, item.shown_as && item.shown_as !== objectName(item) ? `shown as “${item.shown_as}”` : ""].filter(Boolean).join(" · ");
  return <Button variant="ghost" className="detail-related binding-row" onClick={() => onSelect(item)}><span>{objectName(item)}{note ? <small className="binding-note"> {note}</small> : null}</span><ChevronRight className="row-chevron" aria-hidden="true" /></Button>;
}

export default function VisualBindings({ bindings, wells, onSelect }) {
  if (!bindings) return null;
  // With wells recorded, fields are listed by where they sit in the visual instead of by type.
  const byWell = Array.isArray(wells) && wells.length > 0;
  return <div className="visual-bindings">{byWell ? wells.map((well) => <section className="detail-section field-well" key={well.role}>
    <h3>{well.label} <span className="count-pill">{well.fields.length}</span></h3>
    {well.fields.map((item) => <Field key={item.id} item={item} onSelect={onSelect} />)}
  </section>) : null}{Object.entries(groups).filter(([key]) => !(byWell && FIELD_GROUPS.has(key))).map(([key, label]) => <section className={`detail-section ${bindings[key]?.length ? "" : "is-empty"}`} key={key}>
    <h3>{label} <span className="count-pill">{bindings[key]?.length || 0}</span></h3>
    {bindings[key]?.length ? bindings[key].map((item) => <Button key={item.id} variant="ghost" className="detail-related binding-row" onClick={() => onSelect(item)}><span>{objectName(item)}</span><ChevronRight className="row-chevron" aria-hidden="true" /></Button>) : <p className="muted-copy compact">None recorded.</p>}
  </section>)}</div>;
}
