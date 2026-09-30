import React, { useEffect, useMemo, useState } from "react";
import { ResetIcon as RotateCcw } from "@radix-ui/react-icons";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { ARTIFACT_GROUPS, PALETTES, normalizeColors, typeLabel } from "../graphPresentation";

const sameColors = (a, b) => ["groups", "types"].every((section) => Object.keys(a[section]).length === Object.keys(b[section]).length && Object.entries(a[section]).every(([key, color]) => b[section][key] === color));

function ColorInput({ label, color, onChange }) {
  const [text, setText] = useState(color);
  useEffect(() => setText(color), [color]);
  const valid = /^#[0-9a-f]{6}$/i.test(text);
  return <div className="color-inputs">
    <Input type="color" aria-label={`${label} color picker`} value={color} onChange={(event) => { setText(event.target.value); onChange(event.target.value); }} className="color-picker" />
    <Input aria-label={`${label} hex color`} value={text} maxLength={7} spellCheck={false} aria-invalid={!valid} onChange={(event) => {
      setText(event.target.value);
      if (/^#[0-9a-f]{6}$/i.test(event.target.value)) onChange(event.target.value.toLowerCase());
    }} onBlur={() => { if (!valid) setText(color); }} className="color-hex" />
  </div>;
}

export default function GraphColors({ config, transport, overview, onSaved }) {
  const saved = useMemo(() => normalizeColors(config?.graph_colors), [config?.graph_colors]);
  const [draft, setDraft] = useState(saved);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  useEffect(() => { setDraft(saved); }, [saved]);
  const dirty = !sameColors(draft, saved);
  const extraTypes = Object.keys(overview?.object_counts || {}).filter((type) => !Object.values(ARTIFACT_GROUPS).some((group) => group.types.includes(type)));
  const change = (section, key, color) => {
    setDraft((current) => ({ ...current, [section]: { ...current[section], [key]: color } }));
    setMessage("");
  };
  const resetType = (type) => setDraft((current) => {
    const types = { ...current.types }; delete types[type];
    return { ...current, types };
  });
  const save = async () => {
    setSaving(true); setMessage(""); setFailed(false);
    try {
      // Fetch the current contract so appearance edits preserve source changes.
      const current = await transport.getConfig();
      const next = await transport.saveConfig({ ...current, graph_colors: draft });
      onSaved(next);
      setMessage("Colors saved");
    } catch (error) { setFailed(true); setMessage(error.message || "Could not save colors"); }
    finally { setSaving(false); }
  };

  return <Card className="graph-colors">
    <CardHeader>
      <CardTitle>Color palette</CardTitle>
      <CardDescription>Soft colors distinguish objects. Saved with this project.</CardDescription>
    </CardHeader>
    <CardContent>
      <fieldset disabled={saving}>
        <div className="palette-grid" role="group" aria-label="Color palettes">{PALETTES.map((palette) => <Button key={palette.name} variant="ghost" className="palette-option" aria-pressed={sameColors(draft, palette)} onClick={() => { setDraft({ groups: { ...palette.groups }, types: { ...palette.types } }); setMessage(""); }}><span className="palette-swatches" aria-hidden="true">{Object.values(palette.types).map((color, index) => <i key={index} style={{ background: color }} />)}</span><strong>{palette.name}</strong><small>{palette.description}</small></Button>)}</div>
        <details className="customize-colors"><summary>Customize colors</summary>
        <Tabs defaultValue="report">
          <TabsList aria-label="Artifact color groups" className="color-tabs">
            {Object.entries(ARTIFACT_GROUPS).map(([key, group]) => <TabsTrigger key={key} value={key}><span className="artifact-dot" style={{ backgroundColor: draft.groups[key] }} />{group.label.replace(" artifacts", "")}</TabsTrigger>)}
          </TabsList>
          {Object.entries(ARTIFACT_GROUPS).map(([key, group]) => <TabsContent key={key} value={key}>
            <div className="group-color-row">
              <div><Label>{group.label}</Label><p className="text-sm text-muted-foreground">Default for this group</p></div>
              <ColorInput label={group.label} color={draft.groups[key]} onChange={(color) => change("groups", key, color)} />
            </div>
            <div className="color-type-list">
              {[...group.types, ...(key === "other" ? extraTypes : [])].map((type) => <div className="type-color-row" key={type}>
                <div><Label>{typeLabel(type)}</Label><span className="color-inheritance">{draft.types[type] ? "Custom color" : "Group color"}</span></div>
                <ColorInput label={typeLabel(type)} color={draft.types[type] || draft.groups[key]} onChange={(color) => change("types", type, color)} />
                <Button variant="ghost" size="icon" aria-label={`Reset ${typeLabel(type)} color`} title="Use group color" disabled={!draft.types[type]} onClick={() => resetType(type)}><RotateCcw /></Button>
              </div>)}
            </div>
          </TabsContent>)}
        </Tabs>
        </details>
        <div className="color-preview" aria-label="Graph color preview">
          {["TABLE", "COLUMN", "MEASURE", "REPORT", "PAGE", "VISUAL"].map((type) => <div className="color-preview-node" key={type} style={{ "--artifact-color": draft.types[type] || draft.groups[Object.keys(ARTIFACT_GROUPS).find((key) => ARTIFACT_GROUPS[key].types.includes(type))] }}><span className="artifact-dot" /><span>{typeLabel(type)}</span></div>)}
        </div>
        <div className="settings-actions">
          <Button onClick={save} disabled={!dirty || saving || !config}>{saving ? "Saving…" : "Save colors"}</Button>
          <Button variant="outline" onClick={() => { setDraft(normalizeColors()); setMessage(""); }}>Restore defaults</Button>
          {dirty ? <Button variant="ghost" onClick={() => { setDraft(saved); setMessage(""); }}>Discard changes</Button> : null}
          {message ? <span role={failed ? "alert" : "status"} className={failed ? "error-copy" : "success-text"}>{message}</span> : null}
        </div>
      </fieldset>
    </CardContent>
  </Card>;
}
