import React, { useMemo, useState } from "react";
import { Layers, Unlink } from "lucide-react";
import { Button } from "./ui/button";
import { Dialog, DialogContent } from "./ui/dialog";
import { NativeSelect } from "./ui/native-select";
import { TypeGlyph } from "./TypeGlyph";
import { objectName } from "../presentation";
import { typeLabel } from "../graphPresentation";
import { versionFamilies, versionTitle, withVersionLink } from "../versions";

const ROOT_TYPES = ["MODEL", "REPORT"];

/**
 * The user's say on version folding: which models (or reports) are versions of one another.
 * Folding is guessed from names and structure; here a wrong guess is corrected in both directions,
 * and the correction is stored with the project (`version_links`).
 */
export default function VersionGroups({ open, onOpenChange, nodes, links, colors, onChange, saving = false, error = "" }) {
  const [joinWith, setJoinWith] = useState({});
  const roots = useMemo(() => nodes.filter((node) => ROOT_TYPES.includes(node.type)), [nodes]);
  const families = useMemo(() => [...versionFamilies(nodes, links).families.values()], [nodes, links]);
  const groups = families.filter((members) => members.length > 1);
  const singles = families.filter((members) => members.length === 1).map((members) => members[0]);
  const corrected = (links?.same?.length || 0) + (links?.different?.length || 0);

  // Taking one version out of a group: it is different from every other member.
  const split = (member, members) => {
    let next = links;
    members.filter((other) => other.id !== member.id).forEach((other) => { next = withVersionLink(next, "different", member.id, other.id); });
    onChange(next);
  };
  const join = (node) => {
    const other = joinWith[node.id];
    if (!other) return;
    setJoinWith((current) => ({ ...current, [node.id]: "" }));
    onChange(withVersionLink(links, "same", node.id, other));
  };

  return <Dialog open={open} onOpenChange={onOpenChange}>
    {open ? <DialogContent className="version-groups" title="Versions" description="Models and reports that are copies of one another are shown once when versions are folded."
      footer={<>
        {corrected ? <Button variant="ghost" disabled={saving} onClick={() => onChange({ same: [], different: [] })}>Forget my {corrected === 1 ? "correction" : `${corrected} corrections`}</Button> : null}
        <Button variant="outline" onClick={() => onOpenChange(false)}>Done</Button>
      </>}>
      {error ? <p className="error-copy" role="alert">{error}</p> : null}
      <section aria-label="Folded as versions">
        <h3>Folded as versions</h3>
        {groups.length ? <ul className="version-group-list">{groups.map((members) => <li key={members[0].id} className="version-group">
          <strong className="version-group-title"><Layers aria-hidden="true" />{versionTitle(members.map((member) => objectName(member)))} · {members.length} versions</strong>
          <ul>{members.map((member) => <li key={member.id}>
            <TypeGlyph node={member} colors={colors} size="xs" />
            <span className="version-member-name">{objectName(member)}</span>
            <Button variant="ghost" size="sm" disabled={saving} aria-label={`${objectName(member)} is not a version of this group`} onClick={() => split(member, members)}><Unlink aria-hidden="true" />Not a version</Button>
          </li>)}</ul>
        </li>)}</ul> : <p className="muted-copy">No two models or reports are folded.</p>}
      </section>
      {singles.length > 1 || (singles.length && groups.length) ? <section aria-label="Shown separately">
        <h3>Shown separately</h3>
        <ul className="version-single-list">{singles.map((node) => {
          const others = roots.filter((other) => other.type === node.type && other.id !== node.id);
          if (!others.length) return null;
          return <li key={node.id}>
            <TypeGlyph node={node} colors={colors} size="xs" />
            <span className="version-member-name">{objectName(node)}</span>
            <NativeSelect aria-label={`${objectName(node)} is a version of`} value={joinWith[node.id] || ""} disabled={saving} onChange={(event) => setJoinWith((current) => ({ ...current, [node.id]: event.target.value }))}>
              <option value="">Is a version of…</option>
              {others.map((other) => <option key={other.id} value={other.id}>{objectName(other)}</option>)}
            </NativeSelect>
            <Button variant="outline" size="sm" disabled={saving || !joinWith[node.id]} aria-label={`Fold ${objectName(node)} with the chosen ${typeLabel(node.type).toLowerCase()}`} onClick={() => join(node)}>Fold</Button>
          </li>;
        })}</ul>
      </section> : null}
    </DialogContent> : null}
  </Dialog>;
}
