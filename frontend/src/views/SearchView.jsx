// Search: every project object by name or formula text, with model, report and type filters.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight, RefreshCw, TriangleAlert, X } from "lucide-react";
import NavIcon from "../NavIcon";
import { TypeGlyph } from "../components/TypeGlyph";
import { foldSearchResults, formatCount, matchSnippet, readableText, scopeChoices } from "../presentation";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { NativeSelect } from "../components/ui/native-select";
import { Card } from "../components/ui/card";
import { Label } from "../components/ui/label";
import { artifactColor, typeLabel } from "../graphPresentation";
import { EmptyState, PageHeading, contentScroller, labelFor } from "./shared";
import { listKeys, moveInList } from "../listNavigation";

export function searchObject(item) {
  return item?.object && typeof item.object === "object" ? item.object : item;
}

/** Why a row matched when its name does not show it: the matching line of the formula or description. */
export function searchSnippet(item, query) {
  const evidence = (item?.match?.evidence || []).find((entry) => /expression|description/i.test(entry.field || ""));
  const first = item?.match?.evidence?.[0]?.field || "";
  if (!evidence || first === "name") return null;
  const parts = matchSnippet(evidence.value, query);
  return parts ? { parts, formula: /expression/i.test(evidence.field) } : null;
}

/** A name with the typed query marked in it. */
export function Marked({ text, query }) {
  const parts = matchSnippet(text, query, 400);
  return parts ? <>{parts[0]}<mark>{parts[1]}</mark>{parts[2]}</> : text;
}

export function searchMatch(item) {
  const match = item?.match || {};
  const field = match.evidence?.[0]?.field || match.field || item?.match_field || "";
  return /expression/i.test(field) ? "In formula" : /description/i.test(field) ? "In description" : "";
}

export function SearchView({ transport, overview, onSelect, colors, session, onSession, browse = false }) {
  const { query, modelId, reportId, objectType = "" } = session;
  const active = Boolean(browse || query.trim() || modelId || reportId || objectType);
  const inputId = browse ? "browse-object-query" : "brain-search-query";
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState(null);
  const request = useRef(0);
  const inFlight = useRef(null);
  const panel = useRef(null);
  const latest = useRef(session);
  latest.current = session;
  const revision = session.revision || 0;
  const key = JSON.stringify([query.trim(), modelId, reportId, objectType, revision]);
  const requestedKey = useRef(key);
  requestedKey.current = key;
  const result = session.result?.key === key ? session.result.data : null;
  const error = failure?.key === key ? failure : null;
  const loading = pending || Boolean(active && !result && !error);
  const change = (values) => onSession((current) => ({ ...current, ...values, selectedId: null, scrollY: 0 }));
  const runSearch = useCallback(async (offset = 0) => {
    if (!active || inFlight.current?.key === key) return;
    const requestId = ++request.current;
    inFlight.current = { key, requestId };
    setPending(true); setFailure(null);
    try {
      const next = await transport.search({ query: query.trim(), modelId, reportId, objectType, offset });
      if (requestId !== request.current || requestedKey.current !== key) return;
      onSession((current) => {
        if (JSON.stringify([current.query.trim(), current.modelId, current.reportId, current.objectType || "", current.revision || 0]) !== key) return current;
        const previous = offset && current.result?.key === key ? current.result.data.items : [];
        const items = [...new Map([...previous, ...(next.items || [])].map((item) => [searchObject(item).id, item])).values()];
        return { ...current, result: { key, data: { ...next, items } } };
      });
    } catch (cause) {
      if (requestId === request.current && requestedKey.current === key) setFailure({ key, offset, message: cause.message || "Search failed" });
    } finally {
      if (requestId === request.current) { setPending(false); inFlight.current = null; }
    }
  }, [key, modelId, query, reportId, objectType, transport, onSession, active]);
  useEffect(() => {
    setPending(false);
    if (!active || latest.current.result?.key === key) return undefined;
    const timer = setTimeout(() => runSearch(), 220);
    return () => { clearTimeout(timer); request.current += 1; inFlight.current = null; };
  }, [key, runSearch, active]);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const current = latest.current;
      const selected = [...(panel.current?.querySelectorAll("[data-result-id]") || [])].find((element) => element.dataset.resultId === current.selectedId);
      if (selected) { selected.focus({ preventScroll: true }); contentScroller().scrollTop = current.scrollY || 0; }
      else panel.current?.querySelector("input")?.focus({ preventScroll: true });
    });
    return () => { cancelAnimationFrame(frame); request.current += 1; };
  }, []);
  const models = scopeChoices(overview, "model");
  const reports = scopeChoices(overview, "report");
  const scopeName = (object) => [...models, ...reports].find((item) => item.id === (object.report_id || object.model_id))?.name;
  const [unfolded, setUnfolded] = useState(() => new Set());
  const folded = useMemo(() => foldSearchResults(result?.items || [], searchObject), [result]);
  return <div ref={panel}>
    <PageHeading quiet title={browse ? "Browse objects" : "Search"} />
    <Card className="panel search-panel" aria-busy={loading}>
      <div className="search-toolbar" data-ui-actions="">
        <Label htmlFor={inputId} className="sr-only">{browse ? "Filter by name or formula" : "Name or formula"}</Label>
        <div className="search-field"><NavIcon name="search" size={18} /><Input id={inputId} type="search" value={query} onChange={(event) => change({ query: event.target.value })} onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); if (query) change({ query: "" }); else event.target.blur(); } else if (event.key === "Enter") runSearch(); else if (event.key === "ArrowDown" && moveInList(panel.current?.querySelector(".search-results"), "first")) event.preventDefault(); }} placeholder={browse ? "Filter objects by name…" : "Measure, table, column, or visual…"} aria-label="Search objects" />{loading && active ? <RefreshCw className="search-spinner spin" aria-hidden="true" /> : null}</div>
        <div className="search-filters">
          <Label className="select-field"><span className="sr-only">Model</span><NativeSelect aria-label="Model" value={modelId} onChange={(event) => change({ modelId: event.target.value, reportId: "" })}><option value="">All models</option>{models.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</NativeSelect></Label>
          <Label className="select-field"><span className="sr-only">Report</span><NativeSelect aria-label="Report" value={reportId} onChange={(event) => change({ reportId: event.target.value, modelId: "" })}><option value="">All reports</option>{reports.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</NativeSelect></Label>
          <Label className="select-field"><span className="sr-only">Type</span><NativeSelect aria-label="Search object type" value={objectType} onChange={(event) => change({ objectType: event.target.value })}><option value="">All types</option>{Object.keys(overview.object_counts || {}).filter((type) => !new Set(["ALIAS", "BUSINESS_CONCEPT", "ROLE", "BEHAVIOR", "CONFLICT", "SELECTOR", "SELECTOR_OPTION", "SEMANTIC_ASSERTION"]).has(type)).sort().map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</NativeSelect></Label>
          {modelId || reportId || objectType ? <Button variant="ghost" size="sm" className="clear-filters" onClick={() => change({ modelId: "", reportId: "", objectType: "" })}><X />Clear filters</Button> : null}
        </div>
        <div className="search-status" role="status" aria-live="polite">
          {active ? loading ? "Searching…" : result ? (
            (result.total === 0 || result.items.length === 0)
              ? (!query.trim() ? "No objects" : "No matches")
              : `${result.items.length} of ${formatCount(result.total)} ${!query.trim() ? (result.total === 1 ? "object" : "objects") : (result.total === 1 ? "match" : "matches")}`
          ) : "" : ""}
        </div>
      </div>
      {error ? <div className="search-error" role="alert"><TriangleAlert aria-hidden="true" /><span>{readableText(error.message)}</span><Button variant="outline" size="sm" onClick={() => runSearch(error.offset)}>Retry search</Button></div> : null}
      {!active ? <EmptyState icon={<NavIcon name="search" size={20} />} title="What are you looking for?" detail="Find a measure to inspect its formula and dependencies." action={<p className="empty-hint"><kbd>Ctrl</kbd><kbd>K</kbd> jumps here from anywhere</p>} /> : null}
      {active && !loading && !result?.items?.length && !error ? <EmptyState icon={<NavIcon name="search" size={20} />} title="No matches" detail="Try a shorter name or clear the filters." /> : null}
      {active && result?.items?.length ? <div className="search-results" onKeyDown={(event) => listKeys(event, () => panel.current?.querySelector(".search-field input")?.focus())}>{folded.map(({ item, copies }) => {
        const first = searchObject(item);
        const open = copies.length > 1 && unfolded.has(first.id);
        const shown = copies.length > 1 && !open ? [item] : copies;
        return shown.map((entry, index) => {
          const object = searchObject(entry);
          const color = artifactColor(object, colors);
          const snippet = browse && !query.trim() ? null : searchSnippet(entry, query);
          const lead = copies.length > 1 && index === 0;
          const where = lead && !open ? `${copies.length} ${first.report_id ? "reports" : "models"}` : scopeName(object) || readableText(object.description) || "";
          return <Button variant="ghost" key={object.id} data-result-id={object.id} className={`search-result ${copies.length > 1 && index ? "is-copy" : ""}`} style={{ "--artifact-color": color }} onClick={() => { onSession((current) => ({ ...current, selectedId: object.id, scrollY: contentScroller().scrollTop })); onSelect(object.id, "inspector"); }}>
            <TypeGlyph node={object} colors={colors} size="sm" />
            <span className="result-type sr-only">{typeLabel(object.type)}</span>
            <span className="result-copy"><strong><Marked text={labelFor(object)} query={query.trim()} /></strong>{where ? <small>{where}</small> : null}{snippet ? <code className={`result-snippet ${snippet.formula ? "is-formula" : ""}`}>{snippet.parts[0]}<mark>{snippet.parts[1]}</mark>{snippet.parts[2]}</code> : null}</span>
            {lead ? <span role="button" tabIndex={-1} className="result-fold" aria-label={open ? "Show one row" : `Show all ${copies.length}`} title={open ? "Show one row" : `Show all ${copies.length}`} onClick={(event) => { event.stopPropagation(); setUnfolded((current) => { const next = new Set(current); if (next.has(first.id)) next.delete(first.id); else next.add(first.id); return next; }); }}>×{copies.length}<ChevronDown className={open ? "is-open" : ""} aria-hidden="true" /></span> : <span />}
            <ChevronRight className="result-chevron" aria-hidden="true" />
          </Button>;
        });
      })}</div> : null}
      {active && result?.has_more ? <div className="search-footer"><Button variant="outline" size="sm" disabled={loading} onClick={() => runSearch(Number(result.offset || 0) + Number(result.limit || 50))}>{pending ? "Loading…" : "More results"}</Button></div> : null}
    </Card>
  </div>;
}
