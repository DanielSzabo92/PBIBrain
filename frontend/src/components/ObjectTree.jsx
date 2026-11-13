// The object tree of the Inspector: browse a project the way Power BI Desktop lists it,
// Model > Table > Measures and Columns, Report > Page > Visuals. Rows are drawn only while on screen.
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, Search } from "lucide-react";
import { Input } from "./ui/input";
import { TypeGlyph } from "./TypeGlyph";
import { objectForest } from "../graphLayout";
import { ownersOf, treeRows } from "../objectTree";
import { formatCount, objectName } from "../presentation";

const ROW = 26;
const OVERSCAN = 12;

export default function ObjectTree({ transport, colors, selectedId, onSelect, refreshKey }) {
  const [forest, setForest] = useState(null);
  const [failed, setFailed] = useState("");
  const [expanded, setExpanded] = useState(() => new Set());
  const [filter, setFilter] = useState("");
  const [activeId, setActiveId] = useState(selectedId || null);
  const [scrollTop, setScrollTop] = useState(0);
  const [height, setHeight] = useState(600);
  const scroller = useRef(null);

  useEffect(() => {
    let active = true;
    setFailed("");
    Promise.resolve(transport.getLineage?.({}) ?? { nodes: [], edges: [] })
      .then((data) => { if (active) setForest(objectForest(data.nodes || [], data.edges || [])); })
      .catch((cause) => { if (active) setFailed(cause?.message || "The object list could not be loaded"); });
    return () => { active = false; };
  }, [transport, refreshKey]);

  // The selected object is always reachable: its owners open and the row scrolls into view.
  useEffect(() => {
    if (!forest || !selectedId || !forest.byId.has(selectedId)) return;
    setActiveId(selectedId);
    const owners = ownersOf(forest, selectedId);
    setExpanded((current) => owners.every((id) => current.has(id)) ? current : new Set([...current, ...owners]));
  }, [forest, selectedId]);

  const rows = useMemo(() => treeRows(forest, expanded, filter), [forest, expanded, filter]);
  const indexOf = useMemo(() => new Map(rows.map((row, index) => [row.id, index])), [rows]);

  useLayoutEffect(() => {
    const element = scroller.current;
    if (!element) return undefined;
    const measure = () => setHeight(element.clientHeight || 600);
    measure();
    if (typeof ResizeObserver !== "function") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const reveal = useCallback((id) => {
    const index = indexOf.get(id);
    const element = scroller.current;
    if (index === undefined || !element) return;
    const top = index * ROW;
    if (top < element.scrollTop) element.scrollTop = top;
    else if (top + ROW > element.scrollTop + element.clientHeight) element.scrollTop = top + ROW - element.clientHeight;
  }, [indexOf]);
  const revealed = useRef(null);
  useLayoutEffect(() => {
    if (!selectedId || revealed.current === selectedId || !indexOf.has(selectedId)) return;
    revealed.current = selectedId;
    const element = scroller.current;
    if (element) element.scrollTop = Math.max(0, indexOf.get(selectedId) * ROW - element.clientHeight / 3);
  }, [selectedId, indexOf]);

  const toggle = (id, open) => setExpanded((current) => {
    const next = new Set(current);
    if (open ?? !next.has(id)) next.add(id); else next.delete(id);
    return next;
  });
  const move = (id) => { setActiveId(id); reveal(id); };
  const onKeyDown = (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey || !rows.length) return;
    const index = indexOf.get(activeId) ?? -1;
    const row = rows[index];
    const page = Math.max(1, Math.floor(height / ROW) - 1);
    const to = { ArrowDown: index + 1, ArrowUp: index - 1, Home: 0, End: rows.length - 1, PageDown: index + page, PageUp: index - page }[event.key];
    if (to !== undefined) { event.preventDefault(); move(rows[Math.max(0, Math.min(rows.length - 1, to))].id); return; }
    if (!row) return;
    if (event.key === "ArrowRight") {
      event.preventDefault();
      if (row.children && !row.open) toggle(row.id, true);
      else if (row.open && rows[index + 1]) move(rows[index + 1].id);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      if (row.open && !filter) toggle(row.id, false);
      else { const owner = forest.parentOf.get(row.id); if (owner) move(owner); }
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(row.id);
    }
  };

  const first = Math.max(0, Math.floor(scrollTop / ROW) - OVERSCAN);
  const last = Math.min(rows.length, Math.ceil((scrollTop + height) / ROW) + OVERSCAN);
  const total = forest ? forest.byId.size : 0;

  return <aside className="object-tree" aria-label="Objects">
    <div className="object-tree-filter">
      <Search aria-hidden="true" />
      <Input type="search" value={filter} onChange={(event) => { setFilter(event.target.value); if (scroller.current) scroller.current.scrollTop = 0; }} onKeyDown={(event) => { if (event.key === "ArrowDown" && rows.length) { event.preventDefault(); setActiveId(rows[0].id); scroller.current?.focus(); } else if (event.key === "Escape" && filter) { event.preventDefault(); setFilter(""); } }} placeholder={total ? `Filter ${formatCount(total)} objects` : "Filter objects"} aria-label="Filter the object tree" />
    </div>
    <div ref={scroller} className="object-tree-scroll" role="tree" aria-label="Project objects" tabIndex={0} aria-activedescendant={activeId && indexOf.has(activeId) ? `tree-${indexOf.get(activeId)}` : undefined} onKeyDown={onKeyDown} onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}>
      {failed ? <p className="object-tree-note" role="alert">{failed}</p>
        : !forest ? <p className="object-tree-note" role="status">Loading objects…</p>
        : !rows.length ? <p className="object-tree-note">{filter ? "No object has this name" : "No objects yet"}</p>
        : <div className="object-tree-rows" style={{ height: rows.length * ROW }}>
          {rows.slice(first, last).map((row, offset) => {
            const index = first + offset;
            return <div key={row.id} id={`tree-${index}`} role="treeitem" aria-level={row.depth + 1} aria-expanded={row.children ? row.open : undefined} aria-selected={row.id === selectedId}
              className={`object-tree-row ${row.id === selectedId ? "is-selected" : ""} ${row.id === activeId ? "is-active" : ""}`}
              style={{ top: index * ROW, paddingLeft: 6 + row.depth * 14 }}
              onClick={() => { setActiveId(row.id); onSelect(row.id); if (row.children && !row.open) toggle(row.id, true); }}>
              {row.children ? <button type="button" tabIndex={-1} className={`object-tree-twist ${row.open ? "is-open" : ""}`} aria-label={row.open ? "Collapse" : "Expand"} onClick={(event) => { event.stopPropagation(); setActiveId(row.id); toggle(row.id); }}><ChevronRight aria-hidden="true" /></button> : <span className="object-tree-twist" />}
              <TypeGlyph node={row.node} colors={colors} size="sm" />
              <span className="object-tree-name">{objectName(row.node)}</span>
              {row.children ? <span className="object-tree-count">{formatCount(row.children)}</span> : null}
            </div>;
          })}
        </div>}
    </div>
  </aside>;
}
