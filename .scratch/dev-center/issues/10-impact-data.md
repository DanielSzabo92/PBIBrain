# Which impact data does the backend give to the UI?

Type: grilling
Status: resolved
Blocked by: 06

## Question

Define the Breaks and Needs records: fields, severity levels, certain versus possible, the path, and the plain-words reason. Define the wireframe data for a page (visual boxes, filters, status colors). How does the existing impact analyzer extend to the Needs direction and to cross-model sessions?

## Context

- From "Which new object types must the graph learn first?": include the new impact links and the "not checked" note for object types that the app does not know.
- From "How does the Change Plan engine work?": the impact data must give, for each removed object, the dependents that the removal policy (Block, Cascade, Repoint) acts on. A cascade in a visual removes the field and its filters, and removes the visual only when no field stays.
- From the same ticket: an unselected dependent of a renamed target object is a blocking "Breaks" item with an "include in rewrite" action. Other reports that use the target model show as "not changed by this plan". A bookmark that refers to a renamed or removed object is "not checked".

## Answer

Resolved with the user on 2026-10-31. The user accepted all proposed defaults, with one change to decision 16 (no bookmark offers).

### Facts found first

- `backend/impact/analyzer.py` (`analyze_impact`) walks one graph only (one model and its reports), and only downstream. It gives the categories DIRECT, STRUCTURAL, POTENTIAL_BEHAVIORAL, CONDITIONAL, and UNKNOWN, an evidence class (FACT or INFERRED), one shortest path for each rule, a completeness block, and a `required_tests` list. It has no upstream (Needs) walk and no cross-model walk.
- The scanner does not read visual positions now. PBIR `visual.json` has `position` (x, y, z, width, height) and `parentGroupName`. `page.json` has the page size and `filterConfig` (branch `research/pbir-copy`).

### Decisions

1. One record shape, the "Impact item", for Breaks and Needs. Fields: stable item ID (hash), direction (breaks or needs), link to the plan step or Merge Choice row that causes it, impacted object (source, object ID, type, name, model or report), severity, certainty, reason, path, blocking flag, allowed actions.
2. Severity. Breaks: "breaks" (the reference fails), "changes value" (same reference, different result), "needs review" (the app cannot decide). Needs: "will be added" (default prerequisite), "mapped" (to an existing target object), "missing" (no donor has it), "name clash".
3. Certain or possible. Certain: analyzer category DIRECT or STRUCTURAL, and only FACT edges on the path. Possible: POTENTIAL_BEHAVIORAL, CONDITIONAL, or any INFERRED step (for example relationship direction effects). Possible items never block apply. They show as "needs review" warnings.
4. Blocking rules. An item blocks apply when:
   - it is a certain "breaks" item, the removal policy is Block, and no Merge Choice resolves it; or
   - it is an unselected dependent of a renamed target object (action "include in rewrite"); or
   - it is a Need with "missing" or "name clash".

   All other items are warnings or information.
5. Path: one shortest path for each item. Each path step has the object name, type, and a fixed edge phrase ("used by", "filters", "in visual", "on page", "in hierarchy"). When more paths exist, the item gives only their count. The full list comes on request.
6. Reason: one fixed phrase ID for each rule, plus its text. Examples: "uses a removed measure", "uses a renamed column (not rewritten)", "filter context can change". The UI and the agent get the ID and the text.
7. Actions: each item lists its allowed actions as fixed IDs: `include_in_rewrite`, `set_policy_block`, `set_policy_cascade`, `set_policy_repoint`, `add_from_donor`, `map_to_target`, `drop_added_object`, `remove_field`. An action changes only the session state (Merge Choices, removal policies, mappings). The engine then derives the plan and the impact again.
8. Breaks walk: the existing analyzer on the current target graph. Seeds: each object that a plan step deletes, renames, replaces, or changes. Extend it with the new impact links from "Which new object types must the graph learn first?" (hierarchies, roles, OLS, report measures, bookmarks, partitions).
9. Needs walk (new): walk upstream (outgoing "uses" edges) in the donor graph from each added object. Translate each reached object through the alignment. An object with an aligned target object is satisfied. An object with no aligned target object is a Need. The walk is transitive: a Need that the plan adds has its own Needs.
10. Cross-model sessions: no graph edge crosses two models. The alignment is the only link between sources. Breaks runs only on the target graph. Needs runs only on donor graphs. Other reports that use the target model join the Breaks walk as report-only graphs. Their items carry the mark "not changed by this plan".
11. Removal policy data: for each removed object, give its certain dependents (transitive) and, for each one, what Cascade does: "remove object", "remove field from visual", "remove filter", or "remove visual". For Repoint, give the candidate objects of the same kind, each with a data type warning flag.
12. Completeness block, one for each impact result: status (complete or incomplete), "not checked" object types, unresolved bindings, remote reports that the app could not read, bookmarks that refer to a changed object, and possible-only areas. The backend never truncates the item list. The UI pages it.
13. Wireframe data:
    - Page: page ID, display name, width, height, hidden flag, page filters.
    - Visual: visual ID, visual type, title, x, y, z, width, height, group (`parentGroupName`), hidden flag, status, the item IDs that cause the status, visual filters.
    - Report-level filters.

    The scanner must learn to read positions. No mobile layout in the first version.
14. Statuses: removed, breaks, changes, new, not checked, unchanged. A visual or filter with more than one status shows the first one in this order.
15. Wireframes: the target report as it will be after apply (copied pages and visuals show as "new"); donor reports in their current state, to pick carry-over items; other reports that use the target model, with the same data shape.
16. Carry-over offers are a separate "Offer" record, not impact items. Offers include donor pages, visuals, and filters that use an added model object (spec 8.2). Bookmarks are read only in the first version: a donor bookmark that uses an added object shows as information, with no copy action. A field that a copied visual needs and the target does not have is a Need, with the actions `add_from_donor`, `map_to_target`, `remove_field`.
17. Derived, not stored: the engine computes the impact result again from the session state each time, like the plan. The result carries the plan hash and the source snapshot IDs. The session file does not store it.
18. The analyzer `required_tests` list (`QUERY_REQUIRED`) does not go to the UI in the first version. It stays for the later optional value check.
19. Word list: "Impact item" and "Not checked" are in `CONTEXT.md`.

### Consequences

- Build items: Impact item shape and phrase catalog, upstream Needs walk through the alignment, report-only graphs for other reports, blocking rules in plan validation, cascade preview, Offer record, wireframe data, and scanner support for PBIR positions and groups.
- No ADR: each decision is easy to change and follows the spec.
