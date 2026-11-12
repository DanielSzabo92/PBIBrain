# 14 · The interface explains itself in sentences instead of showing

**Severity:** P1 · **Criteria:** self-explanatory UI, information yield, looks high-end

## Evidence (text visible by default)

| Where | Text | Problem |
|---|---|---|
| Every view | h1 repeated directly under a view header that already shows the same icon + name ("Overview" / "Overview") | 70 px of duplicated chrome per view |
| Search | "Find objects by name, description, or part of a DAX formula." | belongs in the placeholder |
| Review queue | "Confirm suggested meanings with the evidence behind each one." + "Approval saves a trusted label for search and context; rejection excludes it. Power BI files stay unchanged." + inline `J K move A approve R reject` | two sentences and a key legend above every session |
| Review rows | "Approve" / "Reject" words on every row; a full sentence of reasoning per row | see 09 |
| Inspector | "Inspect DAX formulas, dependencies, visual bindings, and semantic suggestions for any model or report object." + 3-step how-to | see 13 |
| Settings | "Manage project sources, graph appearance, model context, documentation, and the AI provider of the chat." + per-section helper paragraphs + "Use full Windows paths…" (shown on Linux and macOS too) | restates the tab names |
| Overview | "Check suggested meanings and resolve uncertain matches.", "What is identical, what has drifted, what was renamed and what is unique in the 32 sources." | restates the headings |
| Merge row detail | six radio options, each with a helper sentence, including disabled ones with the reason spelled out | see 20 |
| Status bar | "Connected", "Last scan time unknown · Scan now" | a green dot already says connected |
| Type chips | "8 Model", "240 Table", "4,320 Column" | singular nouns after plurals; the glyph already identifies the type |

Expensive tools are quiet. Each sentence here is something the layout failed to communicate.

## Rules to apply

1. **One title per view.** Keep the 44 px view header; delete `PageHeading` descriptions (8 uses in `App.jsx`). The h1 lives in the header.
2. **A sentence is allowed in three places only:** empty states, confirmation dialogs, error messages.
3. **Explain on demand:** tooltip (300 ms) on every icon button with name + shortcut; F1 opens the shortcut sheet; a `CircleHelp` icon opens a popover where a concept needs it (provenance, merge choices).
4. **Encode state, do not describe it:**
   - provenance = border style + glyph (already defined in contract §4);
   - status = colour + glyph;
   - counts = number next to a type glyph, label only in tooltip (`Σ 2,400`);
   - confidence = number + meter;
   - connection = dot (green/amber/red), text only when not connected;
   - freshness = relative time ("2 min ago"), amber when sources changed on disk.
5. **Actions as icons where the icon is conventional** (approve ✓, reject ✕, copy, expand, close, fit, scan), text + icon for primary and destructive actions.
6. **Platform-aware copy:** path hints from `navigator.platform`; never mention Windows paths elsewhere.
7. Add a lint to `ui-policy.json` / `lint-ui-states.mjs`: fail when a view renders more than 2 text nodes longer than 60 characters outside `[data-empty-state]`, dialogs and alerts.

## Acceptance

- Word count of default-visible static copy per view drops by ≥ 60 % (Overview, Search, Review, Inspector, Settings).
- Every icon-only control has a tooltip and an `aria-label`.
