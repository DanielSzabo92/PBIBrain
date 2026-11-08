import React, { useEffect, useId, useRef, useState } from "react";
import {
  ArrowRight,
  Bot,
  Command,
  Compass,
  FileCode,
  FileDown,
  FileText,
  FolderGit2,
  Inbox,
  Keyboard,
  Layers,
  LoaderCircle,
  Moon,
  PanelLeft,
  RefreshCw,
  ScanLine,
  ScanSearch,
  Search,
  SlidersHorizontal,
  Sun,
  Waypoints,
  X,
} from "lucide-react";
import { Dialog, DialogContent } from "./ui/dialog";
import { displayKeys, shortcutKeys } from "../shortcuts";
import { artifactColor } from "../graphPresentation";
import { objectName } from "../presentation";
import { TypeGlyph } from "./TypeGlyph";

const labelFor = (node) => objectName(node);

export default function CommandPalette({
  open,
  onOpenChange,
  onNavigate,
  onSelectObject,
  overview,
  colors,
  transport,
  recentObjects = [],
  onScan,
  onReload,
  onTheme,
  theme,
  onChat,
  onShortcuts,
  onExportDocumentation,
  onExportSummary,
  onMergeAction,
  activeSession,
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef(null);
  const listRef = useRef(null);
  const searchTimer = useRef(null);
  const searchReq = useRef(0);
  const listId = useId();

  // Reset query and selection when dialog opens
  useEffect(() => {
    if (open) {
      setQuery("");
      setResults([]);
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Debounced search for objects when query changes
  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed || !transport?.search) {
      setResults([]);
      setLoading(false);
      return;
    }
    const reqId = ++searchReq.current;
    setLoading(true);
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(async () => {
      try {
        const resp = await transport.search({ query: trimmed, limit: 8 });
        if (reqId === searchReq.current) {
          setResults(resp?.items || resp?.objects || []);
        }
      } catch {
        if (reqId === searchReq.current) setResults([]);
      } finally {
        if (reqId === searchReq.current) setLoading(false);
      }
    }, 180);
    return () => clearTimeout(searchTimer.current);
  }, [query, transport]);

  // Build the list of static commands
  const allCommands = [
    // Navigation
    { id: "nav:overview", group: "Navigation", label: "Overview", icon: Compass, keys: "Ctrl+1", action: () => onNavigate?.("overview") },
    { id: "nav:search", group: "Navigation", label: "Search objects", icon: Search, keys: "Ctrl+2", action: () => onNavigate?.("search") },
    { id: "nav:graph", group: "Navigation", label: "Graph explorer", icon: Waypoints, keys: "Ctrl+3", action: () => onNavigate?.("graph") },
    { id: "nav:inspector", group: "Navigation", label: "Inspector", icon: Layers, keys: "Ctrl+4", action: () => onNavigate?.("inspector") },
    { id: "nav:review", group: "Navigation", label: "Review queue", icon: Inbox, keys: "Ctrl+5", action: () => onNavigate?.("review") },
    { id: "nav:devcenter", group: "Navigation", label: "Merge models", icon: FolderGit2, keys: "Ctrl+6", action: () => onNavigate?.("devcenter") },
    { id: "nav:config", group: "Navigation", label: "Settings", icon: SlidersHorizontal, keys: "Ctrl+,", action: () => onNavigate?.("config") },

    // Actions & Tools
    { id: "act:scan", group: "Commands", label: "Scan sources", icon: ScanLine, keys: "Ctrl+F5", action: onScan },
    { id: "act:reload", group: "Commands", label: "Reload data", icon: RefreshCw, keys: "F5", action: onReload },
    { id: "act:theme", group: "Commands", label: theme === "dark" ? "Switch to light theme" : "Switch to dark theme", icon: theme === "dark" ? Sun : Moon, keys: "Ctrl+Shift+L", action: onTheme },
    { id: "act:chat", group: "Commands", label: "Toggle chat panel", icon: Bot, keys: "Ctrl+J", action: onChat },
    { id: "act:shortcuts", group: "Commands", label: "Keyboard shortcuts", icon: Keyboard, keys: "F1", action: onShortcuts },
    { id: "act:export-doc", group: "Commands", label: "Export documentation…", icon: FileDown, action: onExportDocumentation },
    { id: "act:export-summary", group: "Commands", label: "Export model summary / agent context…", icon: FileCode, action: onExportSummary },

    // Merge Actions
    { id: "merge:list", group: "Merge models", label: "Merge sessions list", icon: FolderGit2, action: () => { onNavigate?.("devcenter"); onMergeAction?.("list"); } },
    { id: "merge:new", group: "Merge models", label: "New merge session…", icon: FolderGit2, action: () => { onNavigate?.("devcenter"); onMergeAction?.("create"); } },
    ...(activeSession ? [
      { id: "merge:check", group: "Merge models", label: "Check sources for changes", icon: RefreshCw, action: () => onMergeAction?.("check_sources") },
      { id: "merge:compare", group: "Merge models", label: `Merge: Compare (${activeSession.display_name})`, icon: FolderGit2, action: () => onMergeAction?.("tab:compare") },
      { id: "merge:plan", group: "Merge models", label: `Merge: Plan (${activeSession.display_name})`, icon: FolderGit2, action: () => onMergeAction?.("tab:plan") },
      { id: "merge:impact", group: "Merge models", label: `Merge: Impact (${activeSession.display_name})`, icon: FolderGit2, action: () => onMergeAction?.("tab:impact") },
    ] : []),
  ];

  // Filter commands by query
  const trimmed = query.trim().toLowerCase();
  const matchingCommands = trimmed
    ? allCommands.filter((cmd) => cmd.label.toLowerCase().includes(trimmed) || cmd.group.toLowerCase().includes(trimmed))
    : allCommands;

  // Flatten items for keyboard navigation index
  const items = [];

  // 1. Search results (when query is typed)
  if (results.length > 0) {
    for (const item of results) {
      const obj = item?.object || item;
      items.push({
        id: `obj:${obj.id}`,
        type: "object",
        group: "Matching objects",
        label: labelFor(obj),
        detail: obj.model_id || obj.report_id || obj.type,
        object: obj,
        action: () => onSelectObject?.(obj.id),
      });
    }
  }

  // 2. Fallback "show all results in Search page"
  if (trimmed) {
    items.push({
      id: "search:all",
      type: "search-fallback",
      group: "Search",
      label: `Search all objects for "${query.trim()}"`,
      icon: Search,
      action: () => {
        onNavigate?.("search", { query: query.trim() });
      },
    });
  }

  // 3. Recent objects (when query is empty)
  if (!trimmed && recentObjects.length > 0) {
    for (const obj of recentObjects.slice(0, 5)) {
      items.push({
        id: `recent:${obj.id}`,
        type: "recent",
        group: "Recent objects",
        label: obj.name || obj.id,
        detail: obj.type || "Object",
        object: obj,
        action: () => onSelectObject?.(obj.id),
      });
    }
  }

  // 4. Commands
  for (const cmd of matchingCommands) {
    items.push({
      id: cmd.id,
      type: "command",
      group: cmd.group,
      label: cmd.label,
      icon: cmd.icon,
      keys: cmd.keys,
      action: cmd.action,
    });
  }

  // Keep selected index within bounds
  useEffect(() => {
    if (selectedIndex >= items.length) {
      setSelectedIndex(Math.max(0, items.length - 1));
    }
  }, [items.length, selectedIndex]);

  // Execute selected item
  const executeItem = (item) => {
    if (!item) return;
    onOpenChange(false);
    item.action?.();
  };

  const handleKeyDown = (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelectedIndex((idx) => (idx + 1) % Math.max(1, items.length));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelectedIndex((idx) => (idx - 1 + items.length) % Math.max(1, items.length));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (items[selectedIndex]) executeItem(items[selectedIndex]);
    } else if (event.key === "Escape") {
      onOpenChange(false);
    }
  };

  // Group items by group name for rendering
  const groups = [];
  let currentGroup = null;
  items.forEach((item, index) => {
    if (!currentGroup || currentGroup.name !== item.group) {
      currentGroup = { name: item.group, items: [] };
      groups.push(currentGroup);
    }
    currentGroup.items.push({ ...item, globalIndex: index });
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Command palette"
        className="command-palette-dialog"
        aria-describedby={undefined}
      >
        <div className="command-palette">
          <div className="command-palette-header">
            <Search className="command-palette-search-icon" aria-hidden="true" />
            <input
              ref={inputRef}
              type="search"
              className="command-palette-input"
              placeholder="Type a command or search objects…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              role="combobox"
              aria-expanded="true"
              aria-autocomplete="list"
              aria-controls={listId}
              aria-activedescendant={items[selectedIndex] ? items[selectedIndex].id : undefined}
              spellCheck={false}
              autoComplete="off"
            />
            {loading ? <LoaderCircle className="command-palette-spinner spin" aria-hidden="true" /> : null}
            <kbd className="command-palette-esc-badge" aria-hidden="true">Esc</kbd>
          </div>

          <div
            id={listId}
            ref={listRef}
            role="listbox"
            className="command-palette-body"
            tabIndex={-1}
          >
            {items.length === 0 ? (
              <div className="command-palette-empty" role="status">
                No matching commands or objects found.
              </div>
            ) : (
              groups.map((group) => (
                <div key={group.name} className="command-palette-group" role="group" aria-label={group.name}>
                  <div className="command-palette-group-title">{group.name}</div>
                  {group.items.map((item) => {
                    const isSelected = item.globalIndex === selectedIndex;
                    const Icon = item.icon;
                    return (
                      <div
                        key={item.id}
                        id={item.id}
                        role="option"
                        aria-selected={isSelected}
                        className={`command-palette-row ${isSelected ? "is-selected" : ""}`}
                        onClick={() => executeItem(item)}
                        onMouseEnter={() => setSelectedIndex(item.globalIndex)}
                      >
                        {item.object ? (
                          <span className="command-palette-glyph">
                            <TypeGlyph node={item.object} colors={colors} size="sm" />
                          </span>
                        ) : Icon ? (
                          <span className="command-palette-icon"><Icon aria-hidden="true" /></span>
                        ) : null}
                        <div className="command-palette-label-group">
                          <span className="command-palette-label">{item.label}</span>
                          {item.detail ? <span className="command-palette-detail">{item.detail}</span> : null}
                        </div>
                        {item.keys ? (
                          <kbd className="command-palette-shortcut" aria-hidden="true">
                            {displayKeys(item.keys)}
                          </kbd>
                        ) : (
                          <ArrowRight className="command-palette-arrow" aria-hidden="true" />
                        )}
                      </div>
                    );
                  })}
                </div>
              ))
            )}
          </div>

          <div className="command-palette-footer">
            <span><kbd>↑</kbd> <kbd>↓</kbd> Navigate</span>
            <span><kbd>↵</kbd> Select</span>
            <span><kbd>Esc</kbd> Close</span>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
