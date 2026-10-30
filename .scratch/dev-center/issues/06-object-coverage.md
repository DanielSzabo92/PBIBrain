# Which new object types must the graph learn first?

Type: grilling
Status: resolved
Blocked by: 

## Question

The graph does not know roles (RLS), OLS, hierarchies, perspectives, cultures and translations, partitions, bookmarks, themes, and report-level measures. Which of them are needed for the first version, and which can wait? Which properties of each object take part in compare and impact?

## Answer

Resolved with the user on 2026-10-31. Fact found first: the scanner reads none of these types now.

1. Scope split: this ticket decides the object types and the impact links. The ticket "What are the match and compare rules?" decides which properties count for "same" and "different".
2. First version:
   - Yes: hierarchies and levels; RLS roles with their table filters; OLS (table and column permissions) as part of a role; report-level measures; partitions (M text).
   - Read only (impact, no copy): bookmarks.
   - Later: perspectives; cultures and translations; themes; KPIs; detail rows expressions.
3. Unknown object types: the app never drops them. The write path loads the full model and changes only the planned objects, so unknown objects stay unchanged. The impact view shows a "not checked" note that lists the object types that the app could not examine.
4. Partitions and M: the app compares and copies M text exactly. It does not parse M, except to find references to shared expressions (parameters and shared queries). A copied table brings the shared expressions that it needs.
5. New impact links:

| From | To |
|---|---|
| Hierarchy level | Column |
| Visual | Hierarchy |
| Role filter (DAX) | Columns, measures, tables |
| OLS permission | Table or column |
| Report measure (DAX) | Model objects |
| Visual or filter | Report measure |
| Bookmark | Page, visuals, filter fields |
| Partition (M) | Shared expression |
