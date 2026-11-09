import React, { useEffect, useRef, useState } from "react";
import { Menubar as MenubarPrimitive } from "radix-ui";
import { Check, CircleCheck, Keyboard, Moon, Sun, TriangleAlert } from "lucide-react";
import BrandMark from "./BrandMark";
import { Dialog, DialogContent } from "./ui/dialog";
import { Tooltip } from "./ui/tooltip";
import { SHORTCUTS, displayKeys } from "../shortcuts";

// Desktop shell parts: the menu bar (title row), the status bar, and the shortcut sheet.
// Menus follow the Windows convention: Alt or F10 focuses the bar, Alt+letter opens a menu,
// arrows move between menus and items, Escape returns focus to the page.

const MNEMONICS = { f: "file", v: "view", g: "go", h: "help" };

function MenuItem({ item }) {
  if (item.separator) return <MenubarPrimitive.Separator className="ui-menu-separator" />;
  const keys = displayKeys(item.keys);
  if (item.checked !== undefined) {
    return (
      <MenubarPrimitive.CheckboxItem className="ui-menu-item app-menu-item" checked={item.checked} disabled={item.disabled} onSelect={item.onSelect}>
        <span className="ui-menu-check" aria-hidden="true"><MenubarPrimitive.ItemIndicator><Check /></MenubarPrimitive.ItemIndicator></span>
        <span className="app-menu-label">{item.label}</span>
        {keys ? <span className="app-menu-keys" aria-hidden="true">{keys}</span> : null}
      </MenubarPrimitive.CheckboxItem>
    );
  }
  return (
    <MenubarPrimitive.Item className="ui-menu-item app-menu-item" disabled={item.disabled} onSelect={item.onSelect} aria-keyshortcuts={item.keys ? item.keys.replace("Ctrl", "Control").replace("Left", "ArrowLeft") : undefined}>
      <span className="ui-menu-check" aria-hidden="true" />
      <span className="app-menu-label">{item.label}</span>
      {keys ? <span className="app-menu-keys" aria-hidden="true">{keys}</span> : null}
    </MenubarPrimitive.Item>
  );
}

export function AppMenuBar({ menus, projectName, children }) {
  const [value, setValue] = useState("");
  const bar = useRef(null);
  useEffect(() => {
    // Alt alone (pressed and released with no other key) or F10 focuses the first menu, as in Windows apps.
    let altAlone = false;
    const focusBar = () => bar.current?.querySelector("[role=menuitem]")?.focus();
    const down = (event) => {
      if (event.key === "Alt") { altAlone = !event.ctrlKey && !event.shiftKey && !event.metaKey; return; }
      altAlone = false;
      if (event.key === "F10" && !event.shiftKey) { event.preventDefault(); focusBar(); return; }
      if (event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
        const menu = MNEMONICS[(event.key || "").toLowerCase()];
        if (menu) { event.preventDefault(); setValue(menu); }
      }
    };
    const up = (event) => {
      if (event.key === "Alt" && altAlone) {
        altAlone = false;
        event.preventDefault();
        if (bar.current?.contains(document.activeElement)) document.querySelector("#main-content")?.focus();
        else focusBar();
      }
    };
    const blur = () => { altAlone = false; };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", blur);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); window.removeEventListener("blur", blur); };
  }, []);
  return (
    <header className="app-titlebar">
      <span className="app-titlebar-brand" aria-hidden="true"><BrandMark size={18} /></span>
      <MenubarPrimitive.Root ref={bar} value={value} onValueChange={setValue} className="app-menubar" aria-label="Application menu">
        {menus.map((menu) => (
          <MenubarPrimitive.Menu key={menu.id} value={menu.id}>
            <MenubarPrimitive.Trigger className="app-menubar-trigger">
              <span className="app-mnemonic">{menu.label[0]}</span>{menu.label.slice(1)}
            </MenubarPrimitive.Trigger>
            <MenubarPrimitive.Portal>
              <MenubarPrimitive.Content className="ui-menu app-menu" align="start" sideOffset={2} loop>
                {menu.items.filter(Boolean).map((item, index) => <MenuItem key={item.label || `sep-${index}`} item={item} />)}
              </MenubarPrimitive.Content>
            </MenubarPrimitive.Portal>
          </MenubarPrimitive.Menu>
        ))}
      </MenubarPrimitive.Root>
      <div className="app-titlebar-center">{children}</div>
      <Tooltip content={projectName}><span className="app-titlebar-project">{projectName}</span></Tooltip>
    </header>
  );
}

export function StatusBar({ connection, projectName, counts, pending, onReview, scanning, lastScan, notice, noticeFailed, theme, onTheme, onShortcuts, onScan }) {
  const label = connection === "loading" ? "Loading" : connection === "error" ? "Offline" : "Connected";
  const countsText = connection === "loading"
    ? "Loading project…"
    : connection === "error"
      ? "Service unreachable"
      : `${counts.models} ${counts.models === 1 ? "model" : "models"} · ${counts.reports} ${counts.reports === 1 ? "report" : "reports"} · ${counts.objects.toLocaleString()} objects · ${counts.edges.toLocaleString()} relationships`;
  const isScanUnknown = lastScan === "Last scan time unknown" || lastScan === "Not scanned";
  return (
    <footer className="app-statusbar" aria-label="Status bar">
      <Tooltip content={label}><span className={`statusbar-item connection connection-${connection}`}><i />{label}</span></Tooltip>
      {scanning ? <span className="statusbar-item topbar-scanning"><span className="statusbar-progress" aria-hidden="true" />Scanning sources…</span> : null}
      <span className={`statusbar-item statusbar-counts ${connection === "loading" ? "statusbar-loading" : ""}`}>{countsText}</span>
      {pending > 0 ? <Tooltip content="Open the review queue (Ctrl+5)"><button type="button" className="statusbar-item statusbar-button statusbar-review" onClick={onReview}>{pending.toLocaleString()} to review</button></Tooltip> : null}
      {isScanUnknown && onScan ? (
        <Tooltip content="Scan sources now">
          <button type="button" className="statusbar-item statusbar-button statusbar-scan-now" onClick={onScan} disabled={scanning}>
            {lastScan} · <strong>Scan now</strong>
          </button>
        </Tooltip>
      ) : (
        <span className="statusbar-item statusbar-scan">{lastScan}</span>
      )}
      <span className="statusbar-spacer" />
      {notice ? <span className={`statusbar-item toast ${noticeFailed ? "toast-error" : ""}`} role="status">{noticeFailed ? <TriangleAlert aria-hidden="true" /> : <CircleCheck aria-hidden="true" />}{notice}</span> : null}
      <Tooltip content="Keyboard shortcuts (F1)"><button type="button" className="statusbar-item statusbar-button" onClick={onShortcuts} aria-label="Keyboard shortcuts"><Keyboard aria-hidden="true" /></button></Tooltip>
      <Tooltip content={`${theme === "dark" ? "Light" : "Dark"} theme (Ctrl+Shift+L)`}><button type="button" className="statusbar-item statusbar-button theme-toggle" onClick={onTheme} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}>{theme === "dark" ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}</button></Tooltip>
    </footer>
  );
}

export function ShortcutsDialog({ open, onOpenChange }) {
  const groups = ["Go", "File", "View", "Review", "Help"].map((group) => [group, SHORTCUTS.filter((item) => item.group === group)]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Keyboard shortcuts" description="Every command in the menu bar has a key. In lists, arrow keys move between rows and Enter opens one." className="shortcuts-dialog">
        <div className="shortcuts-grid">
          {groups.map(([group, items]) => (
            <section key={group} aria-label={group}>
              <h3>{group}</h3>
              <dl>{items.map((item) => <div key={item.id} className="shortcuts-row"><dt>{item.label}</dt><dd><kbd>{displayKeys(item.keys)}</kbd></dd></div>)}</dl>
            </section>
          ))}
          <section aria-label="Lists">
            <h3>Lists and search</h3>
            <dl>
              <div className="shortcuts-row"><dt>Search from anywhere</dt><dd><kbd>/</kbd></dd></div>
              <div className="shortcuts-row"><dt>Move into results</dt><dd><kbd>↓</kbd></dd></div>
              <div className="shortcuts-row"><dt>First / last result</dt><dd><kbd>Home</kbd> <kbd>End</kbd></dd></div>
              <div className="shortcuts-row"><dt>Close panel or dialog</dt><dd><kbd>Esc</kbd></dd></div>
            </dl>
          </section>
          <section aria-label="Graph">
            <h3>Graph</h3>
            <dl>
              <div className="shortcuts-row"><dt>Move to a connected object</dt><dd><kbd>←</kbd> <kbd>↑</kbd> <kbd>→</kbd> <kbd>↓</kbd></dd></div>
              <div className="shortcuts-row"><dt>Select, then open in Inspector</dt><dd><kbd>Enter</kbd></dd></div>
              <div className="shortcuts-row"><dt>Expand or collapse a group</dt><dd><kbd>Space</kbd></dd></div>
              <div className="shortcuts-row"><dt>Zoom in / out / 100%</dt><dd><kbd>+</kbd> <kbd>−</kbd> <kbd>0</kbd></dd></div>
              <div className="shortcuts-row"><dt>Fit the graph</dt><dd><kbd>F</kbd></dd></div>
              <div className="shortcuts-row"><dt>Clear the selection</dt><dd><kbd>Esc</kbd></dd></div>
              <div className="shortcuts-row"><dt>Show an object’s connections</dt><dd>Double-click</dd></div>
              <div className="shortcuts-row"><dt>Pan / zoom</dt><dd>Drag / scroll</dd></div>
            </dl>
          </section>
          <section aria-label="Compare grid">
            <h3>Compare grid</h3>
            <dl>
              <div className="shortcuts-row"><dt>Move between cells</dt><dd><kbd>←</kbd> <kbd>↑</kbd> <kbd>→</kbd> <kbd>↓</kbd></dd></div>
              <div className="shortcuts-row"><dt>Open row details</dt><dd><kbd>Enter</kbd></dd></div>
              <div className="shortcuts-row"><dt>Select row (toggle)</dt><dd><kbd>Space</kbd></dd></div>
              <div className="shortcuts-row"><dt>Open code diff</dt><dd><kbd>D</kbd> or double-click</dd></div>
              <div className="shortcuts-row"><dt>Bulk merge choices</dt><dd><kbd>M</kbd></dd></div>
              <div className="shortcuts-row"><dt>Search names</dt><dd><kbd>/</kbd></dd></div>
              <div className="shortcuts-row"><dt>Clear selection or close</dt><dd><kbd>Esc</kbd></dd></div>
              <div className="shortcuts-row"><dt>Reload project data</dt><dd><kbd>F5</kbd></dd></div>
            </dl>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
