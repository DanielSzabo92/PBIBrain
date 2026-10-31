# Which impact data does the backend give to the UI?

Type: grilling
Status: open
Blocked by: 06

## Question

Define the Breaks and Needs records: fields, severity levels, certain versus possible, the path, and the plain-words reason. Define the wireframe data for a page (visual boxes, filters, status colors). How does the existing impact analyzer extend to the Needs direction and to cross-model sessions?

## Context

- From "Which new object types must the graph learn first?": include the new impact links and the "not checked" note for object types that the app does not know.
- From "How does the Change Plan engine work?": the impact data must give, for each removed object, the dependents that the removal policy (Block, Cascade, Repoint) acts on. A cascade in a visual removes the field and its filters, and removes the visual only when no field stays.
- From the same ticket: an unselected dependent of a renamed target object is a blocking "Breaks" item with an "include in rewrite" action. Other reports that use the target model show as "not changed by this plan". A bookmark that refers to a renamed or removed object is "not checked".
