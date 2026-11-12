# 18 · Settings: sources are bare path strings with no status

**Severity:** P2 · **Criteria:** easy and obvious, self-explanatory UI

## Evidence

![Settings](evidence/settings-project.png)

- Each source is a text input holding an absolute path, cut off on the right, so eight sources look identical (the file name — the only part that differs — is the part that is hidden).
- No per-source state: found or missing, last scanned, object count, changed on disk, scan error. The user learns a path is wrong only after a scan.
- "Use full Windows paths for PBIP projects or model JSON files." is shown on Linux and macOS.
- "Save configuration" is disabled with no hint why; "Scan saved sources" is a third scan button with a third name.
- The tab "Model summary / agent context" is two names for one thing; "Graph colors" and "Keyboard" are application preferences mixed with project configuration.
- Cloud sources and local sources are edited in different places.

## Solution

1. **Sources as a table, not inputs.**

   | | Name | Kind | Location | Objects | Scanned | |
   |---|---|---|---|---|---|---|
   | ● | Sales Analytics | PBIP | `…/Reports/Sales/` | 1,716 | 2 min ago | ⋯ |

   Status dot (ok / changed on disk / missing / error with tooltip), file name as the primary text, folder path middle-truncated in mono with the full path in a tooltip, row menu: Rescan this source, Reveal in file manager, Remove.
2. **Add sources** with one button → native file/folder picker in the desktop shell; drag-and-drop of a `.pbip`, folder or `.bim` anywhere on the table; paste a path as fallback. "Add from workspace…" opens the cloud picker in the same list.
3. **Save automatically** (debounced) with an inline "Saved ✓"; removing a source asks for confirmation with Undo. No disabled Save button.
4. **Scanning is the header's job** (15, item 2); the table shows per-source progress while it runs.
5. **Split preferences from project:** *Project* (name, sources, review rules, agent context, documentation export) and *Preferences* (appearance, graph colours, keyboard, AI provider). Left section list 200 px as the contract specifies, instead of a tab strip that will not fit a seventh entry.
6. Rename "Model summary / agent context" → "Agent context".
7. Platform-aware hint text, or none.

## Acceptance

- Eight sources are distinguishable at a glance at 1280 px.
- A missing path is flagged before any scan runs.
