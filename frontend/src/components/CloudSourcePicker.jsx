import React, { useEffect, useState } from "react";
import { Cloud, LogIn, Plus, X } from "lucide-react";
import { Button } from "./ui/button";
import { Label } from "./ui/label";
import { NativeSelect } from "./ui/native-select";

// The cloud calls are pywebview JS API methods only (no HTTP route gives tenant data). They reply with an
// object, or with { error: { message } }.
async function cloudCall(api, method, request) {
  if (!api || typeof api[method] !== "function") throw new Error("Cloud sources need the PBIBrain app");
  const reply = await api[method](request);
  if (reply?.error) throw new Error(reply.error.message || "The cloud request failed");
  return reply;
}

/**
 * Pick one cloud model or cloud report and add it to the project (issue #9). The scan reads it with the
 * app's cloud sign-in; the project file keeps only workspace and item IDs, names and the access type.
 */
export function CloudSourcePicker({ api, onAdded, onClose }) {
  const [signedIn, setSignedIn] = useState(null);
  const [workspaces, setWorkspaces] = useState([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [kind, setKind] = useState("cloud_model");
  const [items, setItems] = useState([]);
  const [itemId, setItemId] = useState("");
  const [access, setAccess] = useState("Read");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  const run = async (action) => {
    setWorking(true); setError("");
    try { await action(); } catch (cause) { setError(cause.message || "The cloud request failed"); } finally { setWorking(false); }
  };
  const signIn = (prompt) => run(async () => {
    const reply = await cloudCall(api, "cloud_sign_in", prompt ? { prompt } : {});
    setSignedIn(Boolean(reply.signed_in));
    if (reply.signed_in) setWorkspaces((await cloudCall(api, "cloud_items_list", { kind: "workspaces" })).items || []);
  });
  useEffect(() => { signIn("none"); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    setItems([]); setItemId("");
    if (!workspaceId) return;
    run(async () => {
      const reply = await cloudCall(api, "cloud_items_list", { kind: kind === "cloud_model" ? "models" : "reports", workspace_id: workspaceId });
      setItems(reply.items || []);
    });
  }, [workspaceId, kind]); // eslint-disable-line react-hooks/exhaustive-deps

  const workspace = workspaces.find((item) => item.id === workspaceId);
  const item = items.find((row) => row.id === itemId);
  const add = () => run(async () => {
    const entry = { kind, workspace_id: workspace.id, workspace_name: workspace.name, item_id: item.id, name: item.name, access_type: access };
    if (kind === "cloud_report" && item.dataset_id) entry.dataset_id = item.dataset_id;
    const reply = await api.add_cloud_source(entry);
    if (!reply?.ok) throw new Error(reply?.error || "The cloud item could not be added");
    await onAdded(reply);
  });

  return <div className="cloud-picker" role="group" aria-label="Add a cloud model or report">
    <div className="panel-heading"><div><h3><Cloud aria-hidden="true" />Add from the Power BI service</h3><p className="muted">The scan reads the item again each time and keeps a copy in the project folder. Only a merge with Read/Write access writes it, after a backup.</p></div><Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close cloud picker"><X /></Button></div>
    {signedIn === false ? <Button onClick={() => signIn()} disabled={working}><LogIn />Sign in with Microsoft</Button> : null}
    {signedIn ? <div className="cloud-picker-fields">
      <div><Label htmlFor="cloud-kind">Item type</Label><NativeSelect id="cloud-kind" value={kind} onChange={(event) => setKind(event.target.value)} disabled={working}>
        <option value="cloud_model">Semantic model</option><option value="cloud_report">Report</option>
      </NativeSelect></div>
      <div><Label htmlFor="cloud-workspace">Workspace</Label><NativeSelect id="cloud-workspace" value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)} disabled={working}>
        <option value="">Select a workspace</option>{workspaces.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
      </NativeSelect></div>
      <div><Label htmlFor="cloud-item">{kind === "cloud_model" ? "Semantic model" : "Report"}</Label><NativeSelect id="cloud-item" value={itemId} onChange={(event) => setItemId(event.target.value)} disabled={working || !workspaceId}>
        <option value="">{workspaceId ? "Select an item" : "Select a workspace first"}</option>
        {items.map((row) => <option key={row.id} value={row.id} disabled={kind === "cloud_model" && row.xmla_readable === false}>{row.name}{kind === "cloud_model" && row.xmla_readable === false ? " (XMLA read not available)" : ""}</option>)}
      </NativeSelect></div>
      <div><Label htmlFor="cloud-access">Access</Label><NativeSelect id="cloud-access" value={access} onChange={(event) => setAccess(event.target.value)} disabled={working}>
        <option value="Read">Read only</option><option value="Read/Write">Read/Write (a merge can write it)</option>
      </NativeSelect></div>
      <Button onClick={add} disabled={working || !item}><Plus />Add to project</Button>
    </div> : null}
    {signedIn === null && working ? <p className="muted">Checking the sign-in…</p> : null}
    {error ? <p className="onboarding-error" role="alert">{error}</p> : null}
  </div>;
}
