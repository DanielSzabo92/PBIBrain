import React, { useCallback, useEffect, useState } from "react";
import { GitMerge, Layers, RefreshCw, TriangleAlert } from "lucide-react";
import { BUCKETS, BUCKET_LABELS, countRows, groupMembers, groupSummary, mergeCandidates, sourceName } from "../commonality";
import { typeLabel } from "../graphPresentation";
import { TypeGlyph } from "./TypeGlyph";
import { Button } from "./ui/button";
import { Card } from "./ui/card";

const PAGE_SIZE = 50;

/**
 * Overview panel (issue #14): across every model and report of the project, how many objects are
 * identical, differ, are renamed copies or are unique, by type. A count opens its groups; a group
 * opens its members side by side (Compare) and, for models, offers a merge session.
 */
export default function CommonObjects({ transport, colors, onSelect, onMerge, refreshKey }) {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState(null);
  const [page, setPage] = useState(null);
  const [loadingPage, setLoadingPage] = useState(false);
  const [open, setOpen] = useState(null);

  const load = useCallback(async () => {
    setError("");
    try {
      setSummary(await transport.getCommonality({ limit: 1 }));
    } catch (cause) {
      setError(cause?.message || "The comparison across models could not be loaded");
    }
  }, [transport]);
  useEffect(() => { load(); }, [load, refreshKey]);

  const show = useCallback(async (next, offset = 0) => {
    setFilter(next);
    setOpen(null);
    setLoadingPage(true);
    try {
      const result = await transport.getCommonality({ ...next, limit: PAGE_SIZE, offset });
      setPage((current) => offset && current ? { ...result, groups: [...current.groups, ...result.groups] } : result);
    } catch (cause) {
      setError(cause?.message || "The groups could not be loaded");
    } finally {
      setLoadingPage(false);
    }
  }, [transport]);

  if (error && !summary) {
    return <Card className="panel common-objects" role="region" aria-label="Across models and reports">
      <div className="status-row tone-bad" role="alert"><TriangleAlert className="status-icon" aria-hidden="true" /><div className="status-copy"><h2>Across models and reports</h2><p>{error}</p></div><div className="status-actions"><Button variant="outline" size="sm" onClick={load}>Retry</Button></div></div>
    </Card>;
  }
  if (!summary) return <Card className="panel common-objects" role="region" aria-label="Across models and reports"><p className="muted" role="status"><RefreshCw className="spin" aria-hidden="true" /> Comparing models and reports…</p></Card>;

  const rows = countRows(summary.counts);
  const sources = summary.sources || [];
  const duplicates = summary.duplicate_logic_total || 0;
  return <Card className="panel common-objects" role="region" aria-labelledby="common-objects-title">
    <header className="common-objects-head">
      <Layers className="status-icon" aria-hidden="true" />
      <div className="status-copy">
        <h2 id="common-objects-title">Across models and reports</h2>
        <p>What is identical, what has drifted, what was renamed and what is unique in the {sources.length} sources.{summary.incomplete ? " Some sources were not checked, so this is incomplete." : ""}</p>
      </div>
    </header>
    {rows.length ? <table className="common-objects-table">
      <thead><tr><th scope="col">Type</th>{BUCKETS.map((bucket) => <th scope="col" key={bucket}>{BUCKET_LABELS[bucket]}</th>)}</tr></thead>
      <tbody>{rows.map((row) => <tr key={row.type}>
        <th scope="row"><TypeGlyph type={row.type} colors={colors} size="sm" /> {typeLabel(row.type)}</th>
        {BUCKETS.map((bucket) => <td key={bucket} data-ui-number="">{row[bucket] ? <Button variant="link" size="sm" aria-pressed={filter?.type === row.type && filter?.bucket === bucket} aria-label={`${row[bucket]} ${BUCKET_LABELS[bucket].toLowerCase()} ${typeLabel(row.type).toLowerCase()} objects`} onClick={() => show({ type: row.type, bucket })}>{row[bucket].toLocaleString()}</Button> : <span className="muted">0</span>}</td>)}
      </tr>)}</tbody>
    </table> : <p className="muted">No objects to compare yet.</p>}
    {duplicates ? <p className="common-objects-dup"><Button variant="link" size="sm" onClick={() => show({ type: "", bucket: "", duplicates: true })}>{duplicates.toLocaleString()} {duplicates === 1 ? "group" : "groups"} of duplicate logic</Button> <span className="muted">— the same DAX under different names</span></p> : null}
    {filter ? <section className="common-objects-groups" aria-live="polite" aria-busy={loadingPage}>
      {filter.duplicates ? <>
        <h3>Duplicate logic</h3>
        <ul>{(page?.duplicate_logic || []).map((item) => <li key={item.id}>
          <code className="common-objects-expression">{item.expression}</code>
          <ul className="common-objects-members">{item.members.map((member) => <li key={member.object_id}><Button variant="link" size="sm" onClick={() => onSelect(member.object_id, "inspector")}>{member.name}</Button> <span className="muted">in {sourceName(member.in, sources)}{member.table ? ` · ${member.table} table` : ""}</span></li>)}</ul>
        </li>)}</ul>
      </> : <>
        <h3>{BUCKET_LABELS[filter.bucket]} · {typeLabel(filter.type)}</h3>
        <ul>{(page?.groups || []).map((group) => {
          const expanded = open === group.id;
          const merge = mergeCandidates(group, sources);
          return <li key={group.id} className="common-objects-group">
            <div className="common-objects-row">
              <span className="common-objects-name">{group.table ? <span className="muted">{group.table} / </span> : null}{group.name}</span>
              <span className="muted">{groupSummary(group, sources)}</span>
              <span className="common-objects-actions">
                {group.in.length > 1 ? <Button variant="ghost" size="sm" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : group.id)}>Compare</Button> : <Button variant="ghost" size="sm" onClick={() => onSelect(group.objects?.[group.in[0]], "inspector")}>Inspect</Button>}
                {merge.length && group.bucket !== "identical" ? <Button variant="ghost" size="sm" onClick={() => onMerge(merge, group)}><GitMerge aria-hidden="true" />Merge</Button> : null}
              </span>
            </div>
            {expanded ? <ul className="common-objects-members">{groupMembers(group, sources).map((member) => <li key={member.ref}>
              <span className="muted">{member.source}:</span> <Button variant="link" size="sm" onClick={() => onSelect(member.objectId, "inspector")}>{member.name}</Button>
            </li>)}</ul> : null}
          </li>;
        })}</ul>
        {page?.has_more ? <Button variant="outline" size="sm" disabled={loadingPage} onClick={() => show(filter, page.groups.length)}>Show more</Button> : null}
      </>}
    </section> : null}
  </Card>;
}
