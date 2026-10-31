# How does the user see and resolve impact in the table, graph, and wireframe views?

Type: prototype
Status: open
Blocked by: 02

## Question

Design the three impact views (table as default, graph, page wireframe) for Breaks and Needs, for one row and for the full plan. How does the user act on an item, see the completeness, and select carry-over Offers?

## Context

- Data: technical design section 7 and 14.1 `GET impact` (Impact items, completeness block, Offer records; paging), `GET wireframe/{report}`.
- Impact item: direction (breaks or needs), cause, impacted object, severity (Breaks: breaks, changes value, needs review; Needs: will be added, mapped, missing, name clash), certainty (certain or possible; possible never blocks), reason (phrase ID + text), shortest path (+ count of other paths), blocking flag, allowed actions.
- Actions: `include_in_rewrite`, `set_policy_block`, `set_policy_cascade`, `set_policy_repoint`, `add_from_donor`, `map_to_target`, `drop_added_object`, `remove_field`. JS API `impact_action_apply`, `need_mapping_set`, `offer_select`.
- Graph: reuse the existing xyflow + dagre code (`frontend/src/components/GraphView.jsx`, `frontend/src/graphLayout.js`, `frontend/src/graphPresentation.js`). Decide what to reuse and what is new.
- Wireframe: pages with visual boxes from PBIR positions; status in priority order removed, breaks, changes, new, not checked, unchanged; wireframes for the target report after apply, donor reports now, and other reports of the target model. Status needs icon or pattern + text, not color only.
- Completeness (spec 8.5): not-checked types, unresolved bindings, unreadable remote reports, bookmarks, possible-only areas. The backend never truncates the list.
- Existing screen to compare with: `frontend/src/components/ImpactExplorer.jsx`.
- Skills: `design-doctrine`, `design-screen`, `data-dashboard`, "prototype". Prototype in `.scratch/dev-center-ui/prototypes/05/`.

## Done when

The answer gives: the layout of each view and the switch between them, the item row and its actions, the graph node and edge look and its keyboard and screen reader alternative, the wireframe drawing rules and its text alternative, the completeness block, the Offer selection flow, and the empty, loading, error, and large-list states. Prototype screenshots in both themes are linked. Contrast and layout claims are measured or marked UNMEASURED.
