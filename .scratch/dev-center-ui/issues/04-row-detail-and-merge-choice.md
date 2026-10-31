# How does the user set a Merge Choice on one row, with a new name, a display folder, and a removal policy?

Type: grilling
Status: resolved
Blocked by: 02

## Question

Design the row detail and the Merge Choice editor. How does the user pick one of the six Merge Choices, pick properties for "Take properties", set a new name and a display folder, see naming rule marks and a proposed name, change the alignment of the row, and set a removal policy with a Cascade preview or a Repoint target?

## Context

- Merge Choices (spec 7.1): Keep target, Take from <source>, Take properties from <source> (measures, columns, relationships only), Add as new name, Remove from target, Skip. JS API `merge_choice_set`.
- New name and display folder (spec 7.2): the folder field lists the folders of the target and the selected source; the user can type a new one. This is a Combobox (charting decision 4).
- Naming rules (technical design section 5): a rule break is a warning; a name clash is blocking. `POST name-propose` returns a name and rule IDs.
- Alignment override (section 4.1): confirm a possible rename, break a match, reject a rename. JS API `alignment_override`.
- Removal policy (section 6.4, `GET impact/removal/{object}`): Block (default), Cascade (list of dependents with the effect for each), Repoint (same-kind candidates with a data type warning flag). JS API `removal_policy_set`.
- Source marks: a row with "source changed" needs `row_confirm` (section 11).
- Agent proposal on the row: show it here; the full proposal flow is ticket 06.
- Report measures: "promote" and "copy into target report" (spec 7.4, section 15.1).
- Skills: `design-doctrine`, `design-component` (spec level, 8 states for each new part).

## Done when

The answer gives: the row detail layout (pane or sheet, from ticket 02), the Merge Choice control and its states, the property picker, the name and folder fields with rule marks and the proposer action, the alignment override actions, the removal policy dialog with Cascade and Repoint, each blocking and warning state with a copy draft, and the component specs with the 8 states.

## Answer

Resolved on 2026-10-31. The orchestrator accepted all 18 recommendations of round 1 (one round), with one note on Q15: the proposal card uses the ticket 06 card spec. Prototype: `.scratch/dev-center-ui/prototypes/04/` (`index.html`, `tokens.css`, `measure.mjs`, screenshots in `shots/`, static snapshots in `shots/snap/`). The prototype is never shipped. To make the screenshots again, run `node measure.mjs shots` in `prototypes/04/`. Set `SNAP_ALL=1` to save a static snapshot of each screen.

### Brief Inference

- Domain: dev-tool (Power BI model merge). Audience: expert BI developer. Tone: calm, utilitarian.
- Mood: precise. Motion depth: subtle feedback only (chevron turn on collapsible sections, spinner on save; both stop with reduced motion).
- Layout family: one narrow vertical inspector. One thing leads: the Merge Choice group. Notices and the agent card go above it, because they ask for an action first.
- Reference anchor: the ticket 02 shell and the existing PBIBrain Inspector, without its one-sided color bars.

### Decisions of round 1

1. The pane opens when the user clicks a row or presses Enter on a row. It follows the selected row. It closes with the close button or Escape. With no open row, the side column is not shown and the grid uses the full width. The header has "Previous row" and "Next row".
2. Section order: header, row notices, agent proposal card, Merge Choice (with the fields of the selected choice), Match (collapsible), Sources (collapsible), "Show impact of this row".
3. Merge Choice: one vertical radio group with the 6 choices. With 2 or more donors that have the object, "Take from source" and "Take properties from source" show a source Select below the radio. With one donor, the label names it ("Take from Sales B"). A choice that does not apply stays visible and disabled, with a one-line reason.
4. Target-missing row: "Keep target" shows as "Do not add (keep target)". "Remove from target" and "Take properties from source" are disabled with a reason.
5. Immediate save: each committed change calls `merge_choice_set` with `base_revision`. Radio and Select commit on change. Text fields commit on Enter or blur. On `stale_revision` the pane loads the row again and shows a notice. No undo button in the pane.
6. Property picker: one checkbox for each property that counts for the type (technical design 4.2). Different properties show their phrase and short values, and are preselected. Same properties are disabled with "Same". At least one is necessary.
7. New name: required for "Add as new name", filled from `POST name-propose`. For "Take from", it is hidden behind "Change name". Default: the target name, else the donor name. "Propose name" is always next to the field.
8. Rule marks for a typed name: backend change request (extend `name-propose` with `candidate`). The check runs 300 ms after the last key. A rule break is a warning. A clash is an error that makes the plan blocking, with "Use proposed name".
9. Display folder: Combobox with the groups "In target" and "In <source>", typeahead, and `Use new folder "<text>"`. Backend change request (`GET display-folders`). Shown only for types that have a display folder.
10. Match actions: a possible rename notice with "Confirm rename" and "Reject rename"; "Break match" with a confirm dialog; a "Match with" dialog with a search Combobox. All call `alignment_override`.
11. Break match removes the Merge Choice of the row (backend clarification request). The UI moves the selection to the row that keeps the target object.
12. Removal policy: after "Remove from target", the UI calls `GET impact/removal/{object}`. 0 dependents: one line. Dependents: a summary in the pane and "Select removal policy", which opens a modal dialog (max 640 px). No automatic open.
13. Dialog: Block, Cascade (table of dependents with the effect for each; destructive confirm), Repoint (Combobox of same-kind candidates with a data type warning). All call `removal_policy_set`.
14. Source marks: a warn notice with "Confirm row" (`row_confirm`). A change of the Merge Choice does not confirm the row.
15. Agent proposal: the ticket 06 card (see "Agent proposal card").
16. Report measure rows: two more radio choices under the group label "Report measure": "Promote to target model" and "Copy into target report". Backend change request (`merge_choice_set` values).
17. Many selected rows: the pane shows "<N> rows selected" and points to the ticket 03 bulk bar.
18. Read-only session: all change controls are disabled. One info notice. Code diff and impact links stay active.

### Row detail layout

The pane is the ticket 02 side pane: a 360 px column at 1280 px and wider, a `min(400px, 92vw)` sheet below 1280 px (measured, see below). The pane header stays fixed. The pane body scrolls in its own region.

```
+-------------------------------------------+
| [Net Margin]                  [^] [v] [x] |  h2, Previous row, Next row, Close
| (sigma) Measure  in Sales  (!) Different  |  type, table, row state (icon + text)
+-------------------------------------------+
| (!) Sales B changed since the last check. |  Row notices: source mark, then
|     Examine this row, then confirm it.    |  blocking items (bad), then warnings
|     [Confirm row]                         |  (warn), from GET plan for this row
+-------------------------------------------+
| (bot) Proposed by agent  Claude Code 10:31|  Agent proposal card (ticket 06 spec)
| Take from Sales B                         |
| Confidence 94%   Reason ...               |
| Your choice  Keep target                  |
| [Replace with agent choice] [Reject]      |
+-------------------------------------------+
| Merge Choice                              |  radio group (fieldset + legend)
| ( ) Keep target                           |
| (o) Take from source   (bot) Proposed     |
|     Source [Sales B            v]         |  Select (2+ donors only)
|     [Change name]                         |  name field hidden until clicked
|     Display folder [Margin          ]     |  Combobox
| ( ) Take properties from source           |
| ( ) Add as new name                       |
| ( ) Remove from target                    |
| ( ) Skip                                  |
|     No change now. The row stays open.    |
|  Report measure  (group label, only on    |
|  report measure rows)                     |
| ( ) Promote to target model               |
| ( ) Copy into target report               |
+-------------------------------------------+
| > Match                                   |  collapsed (open for a possible rename)
| > Sources                                 |  state + phrases per source,
|                                           |  [Show code diff]
+-------------------------------------------+
| -> Show impact of this row                |  opens the Impact tab for this row
+-------------------------------------------+
```

The fields of the selected choice show inside its radio item, below the label. Only the selected choice shows its fields. This keeps one column and no second panel.

### Merge Choice control

| Choice | API value | Label | Fields when selected | Disabled when (reason text) |
|---|---|---|---|---|
| Keep target | keep target | "Keep target"; on a target-missing row "Do not add (keep target)" with "The target stays without this object." | none | never |
| Take from | take from | "Take from <source>" (1 donor) or "Take from source" (2+ donors) | Source Select (2+ donors), "Change name" (shows the name field), Display folder | no donor has the object: "No source has this object." |
| Take properties from | take properties | "Take properties from <source>" or "Take properties from source" | Source Select (2+ donors), property picker | target missing: "The target does not have this object. Nothing to change." Type is not a measure, column, or relationship: "Only for measures, columns, and relationships." |
| Add as new name | add as new name | "Add as new name" | Name (required), Display folder | no donor has the object: "No source has this object." |
| Remove from target | remove | "Remove from target" | Removal policy summary | target missing: "The target does not have this object." |
| Skip | skip | "Skip" with "No change now. The row stays open." | none | never |
| Promote (report measure rows) | `promote` (change request) | "Promote to target model" with "Creates a model measure and moves the visuals of the target report to it." | Name, Display folder (clash check against model objects) | never; a name clash shows as the clash error |
| Copy into target report (report measure rows) | `copy_to_report` (change request) | "Copy into target report" with "Adds this report measure to the target report." | Name | the source report is the target report: "This measure is already in the target report." |

Source Select options: each donor in session order, with its cell state as a second line ("Different: expression, format string"). A donor where the object is Missing is a disabled option with "Missing. Cannot take from this source." Default: the donor of the agent proposal if one exists, else the first donor with the state Different.

Save behavior: each commit calls `merge_choice_set` one time (row key, choice, source, properties, new name, display folder, `base_revision`). While the call runs, the selected radio has `aria-busy` and the status "Saving" with a spinner. The other radios stay usable; a new commit waits for the running call. On success, the grid row updates from the returned row. For errors, see "Blocking and warning states".

### Property picker

- One checkbox for each property that counts for the type (technical design 4.2). Measure: Expression, Format string, Display folder, Description, Hidden, Data category. Data column and calculated column: their 4.2 lists. Relationship: Cardinality, Cross-filter direction, Active, Security filter direction, Assume referential integrity.
- Second line of each item: "Different: <phrase>" with the short old and new value from the compare row (for example `Different: "0.0%" to "0.00%"`), or "Same".
- When the user selects the choice, the different properties are preselected. Same properties are disabled.
- The legend is "Properties to take from <source>". When the source changes, the list is computed again and the preselection resets.
- Zero checked: the fieldset gets `aria-invalid="true"` and the error "Select at least one property." The UI does not call `merge_choice_set` until one property is checked.
- If the user checks "Display folder", the Display folder field shows below the list.

### Name field, rule marks, and the proposer

- Label "New name". For "Add as new name" the field is required (`aria-required`). On selection, the UI calls `POST name-propose` and fills the field. Hint (ok icon): "Proposed from naming rules: <rule names>."
- For "Take from" the field is hidden behind "Change name". Default value: the target name if the target has the object, else the donor name.
- "Propose name" is an icon button (wand icon, `aria-label="Propose name"`) next to the field. It replaces the field value with the proposer result.
- After each key, the UI waits 300 ms, then calls `POST name-propose` with `candidate` (change request). Hint while the call runs: spinner and "Checking the name".
- Rule break (warning, save permitted): `This name breaks 1 naming rule: <rule text>. You can keep it.` For more breaks: "This name breaks <N> naming rules:" and a list.
- Clash (error, save permitted, plan blocking): `The target already has a <type> "<name>" in <table>. Use a different name. The plan stays not valid until you change it.` Action: `Use proposed name "<proposed>"`.
- Empty required name: `Type a name. "Add as new name" needs a new name.` No call until the field has text.
- Commit: Enter or blur. Escape puts back the last saved value.

### Display folder field

- Combobox: an input with `role="combobox"` and a listbox with `role="group"` children. Groups: "In target", then "In <selected source>". Values show in the code font, with the backslash as the folder separator.
- Typeahead filters both groups. Text that matches no folder adds the first option `Use new folder "<text>"`.
- Default: the folder of the selected source for "Take from"; the folder of the donor for "Add as new name".
- Shown only for measures, columns, hierarchies, and report measures.
- Data: `GET display-folders?source=<id>` (change request). While it loads, the list shows "Loading folders". If it fails, the field still accepts free text, and the list shows "Cannot load the folder list. You can type a folder."

### Alignment override actions

| Situation | Where | Action | Call | Result |
|---|---|---|---|---|
| Possible rename | Info notice at the top of the pane; Match section open | "Confirm rename", "Reject rename" | `alignment_override` (confirm or reject) | The row state becomes Renamed, or the row splits |
| Any matched row | Match section | "Break match" opens the confirm dialog | `alignment_override` (break) | The row splits; the Merge Choice of the row is removed (change request); the selection moves to the row that keeps the target object |
| Any row | Match section | "Match with" opens a dialog with a search Combobox of unmatched objects of the same type in one source (from `GET compare-rows` with type filter and target state Missing) | `alignment_override` (manual) | The rows join; the selection stays on the joined row |

Match section content: "Matched by" (Same lineage tag; Same name and type; Same name, different table; Same expression, different name (not confirmed); Confirmed by you; Matched by you), and the name in each source when the names are not equal.

### Removal policy

Pane states after "Remove from target":

| State | Look | Copy |
|---|---|---|
| Dependents load | spinner hint | "Finding objects that use this" |
| 0 dependents | ok hint | "No object uses this. It is removed with no other change." |
| Block (default), dependents | bad notice (full border) inside the choice | "**Removal policy: Block.** 7 objects use this measure. The plan is not valid until you resolve each one." / "Select removal policy" |
| Cascade set | warn notice | "**Removal policy: Cascade.** 7 other objects are removed with it." / "Change removal policy" |
| Repoint set | info notice | "**Removal policy: Repoint.** 7 references go to [Net Margin]." / "Change removal policy" |
| Repoint with type warning | warn notice | "**Removal policy: Repoint.** 7 references go to [Margin Count]. The data type is different." / "Change removal policy" |
| Load failed | bad hint | "Cannot find the objects that use this. Try again." / "Try again" |

Dialog: modal, `role="dialog"`, `aria-modal`, max 640 px, focus trap, Escape closes, focus goes back to "Select removal policy".

- Title: "Removal policy for <object>". Text: "<N> objects use this <type>. Select what happens to them when you remove it."
- Radio group "Policy":
  - Block: "Keep the plan not valid until you resolve each object yourself." Confirm "Use Block" (primary).
  - Cascade: "Remove the objects that use it too." Below: "These objects are also removed or changed:" and a table (Object, Kind, Effect) in its own scroll region (max 240 px high). Effects: "Removed", "Field removed from visual", "Visual removed (no field stays)", "Filter removed", "Keeps its own Merge Choice: <choice>". Confirm "Use Cascade (remove <N> objects)" (destructive fill).
  - Repoint: "Replace each reference with one other measure." Below: the Combobox "Replace each reference with" (same-kind candidates; second line the data type; a type mismatch shows a warn icon and "Data type is different: <candidate type>, not <object type>"). Confirm "Use Repoint" (primary), disabled until the user selects a candidate.
- Cancel keeps the old policy. Confirm calls `removal_policy_set` and closes the dialog. Then the pane summary updates.

### Source marks

A warn notice at the top of the pane. "Confirm row" calls `row_confirm`. A change of the Merge Choice does not confirm the row.

| Mark | Copy |
|---|---|
| source changed | "<source> changed since the last check. Examine this row, then confirm it." |
| source object missing | "<object> is no longer in <source>. Examine this row, then confirm it." |
| new since start | "<object> is new in <source> since the session started. Examine this row, then confirm it." |

After the confirm, the notice goes away and the toast "Row confirmed." shows.

### Agent proposal card (ticket 06 spec)

- Badge "Proposed by agent" (bot icon plus text), the MCP client and the time ("Claude Code, today 10:31").
- The change in plain words as the card title ("Take from Sales B").
- "Confidence" as a percent ("94%"). "Reason": the full text, not cut.
- "Your choice: <choice>" when the row has a Merge Choice. Then the accept button is "Replace with agent choice". With no Merge Choice it is "Accept". Second button: "Reject". Calls: `proposal_accept`, `proposal_reject`.
- The radio of the proposed choice shows the badge "Proposed" (bot icon plus text).
- On a marked row, the card adds the warn hint "The source changed after the agent made this proposal. Examine the row before you accept."
- Card: `brand-line` border on all sides, `brand-soft` fill. Badge text uses `brand-strong`, not `brand` (see measurements).

### Blocking and warning states with copy draft

| State | Kind | Where | Copy draft |
|---|---|---|---|
| Blocking items of the row | blocking | Notice (bad, `role="alert"`) at the top | "<N> blocking item(s) for this row." + list from GET plan |
| Warnings of the row | warning | Notice (warn) at the top | "<N> warning(s) for this row." + list |
| Name clash | blocking | Name field error | see "Name field" |
| Rule break | warning | Name field hint | see "Name field" |
| Empty required name | error (no save) | Name field | `Type a name. "Add as new name" needs a new name.` |
| No property selected | error (no save) | Property picker | "Select at least one property." |
| Removal Block with dependents | blocking | Removal policy summary | see "Removal policy" |
| Repoint type mismatch | warning | Dialog option and pane summary | "Data type is different: Whole number, not Decimal number" |
| Source mark | blocks Apply | Notice (warn) | see "Source marks" |
| Proposal on a marked row | warning | Proposal card | see "Agent proposal card" |
| `stale_revision` | error | Notice (warn, `role="alert"`); the row loads again | "This row changed in another place. Examine it, then set your Merge Choice again." |
| `source_changed` on accept | error | Proposal card hint | "The source changed. Confirm the row first, then accept." |
| `invalid_payload` or `action_not_allowed` | error | Notice (bad) | "PBIBrain cannot save this Merge Choice. Load the row again and try again." / "Load row again" |
| Row load failed | error | Pane body | "Cannot load this row. The local API did not answer. Make sure PBIBrain is running, then try again." / "Try again" |
| Read-only session | info | Notice (info, lock icon) | "This session is read-only. Another PBIBrain window has it open." |
| Many selected rows | info | Pane body | "<N> rows selected" / "Use the bar above the grid to set one Merge Choice for all selected rows." / "Name, display folder, properties, and removal policy are set on one row at a time." / "Clear selection" |
| Break match confirm | destructive confirm | Alert dialog | "Break the match of <object>?" / "The row splits into one row for each object. The Merge Choice of this row is removed." / "Break match" / "Cancel" |
| Policy save failed | error | Dialog body notice (bad) | "PBIBrain cannot save this policy. Try again." |

`user_choice_exists` does not show here (agent side, ticket 06). Ticket 09 takes these strings into the copy catalog. No em dash or en dash (measured).

### Component specs (8 states)

All parts use `theme.css` tokens. Each control border uses `control-border` (ticket 01). Focus is a 2 px `ring` outline with 2 px offset. Disabled is opacity 0.55 (inputs 0.5), `cursor: not-allowed`, and the reason text. Each status shows icon plus text.

**1. RowDetailPane** (organism, new). Anatomy: header (h2 name, meta line, nav buttons), scroll body of sections. Variants: one row, many rows, load, error. Sizes: column 360 px (1280 px and wider), sheet `min(400px, 92vw)` (below 1280 px). ARIA: `aside` with `aria-labelledby` the h2. As a sheet it is a Radix Dialog (modal, focus trap, Escape, focus goes back to the grid row).

| State | Look |
|---|---|
| default | `surface` fill, `line` border, sections divided by `line` |
| hover | n/a (container); the nav buttons use the ghost hover `surface-hover` |
| focus | focus moves to the h2 (`tabindex="-1"`) when the pane opens from the keyboard |
| active | n/a |
| disabled | read-only session: all child change controls disabled, info notice |
| loading | body `aria-busy="true"`, spinner "Loading row", 4 skeleton lines (`surface-3`) |
| error | bad notice with "Try again" |
| selected | the grid row of the open pane has `aria-selected="true"` and `brand-soft` fill |

**2. MergeChoiceGroup and ChoiceRadio** (molecule, new, Radix RadioGroup). Anatomy: fieldset, legend "Merge Choice", items (radio dot, label, optional badge, optional reason line, optional sub-fields), optional group label "Report measure". Variants: normal, target missing, report measure. Size: one; 16 px dot; item min height 34 px. Keyboard: Tab goes into the group; arrows move and select (Radix); Space selects.

| State | Look |
|---|---|
| default | 16 px circle, 1.5 px `control-border`, `surface` fill |
| hover | item fill `surface-hover` |
| focus | `ring` outline on the dot |
| active | item fill `surface-3` while pressed |
| disabled | dot opacity 0.5, label `text-3`, reason line `text-2`, `aria-describedby` the reason |
| loading | dot `aria-busy`, dashed border, status "Saving" with spinner |
| error | the sub-field of the item shows the error (name, properties); the item stays selected |
| selected | `brand` dot and border, item fill `surface-3`, sub-fields show |

**3. SourceSelect** (molecule, new Radix Select, map decision 4). Anatomy: label, trigger (value, chevron with 8 px inner padding), listbox (options with check, name, state line). Keyboard: Enter, Space, or arrows open; typeahead; Home, End; Escape closes and puts focus back on the trigger.

| State | Look |
|---|---|
| default | trigger `surface`, `control-border` |
| hover | trigger `surface-hover` |
| focus | `ring` outline |
| active (open) | trigger border `brand`, `aria-expanded="true"`; listbox `surface-2`, `line-strong` border, `shadow-md` |
| disabled | trigger opacity 0.55; an option with `aria-disabled` uses `text-3` and a reason |
| loading | n/a (the data comes with the row) |
| error | n/a |
| selected | `brand` check icon on the selected option; the active option has `surface-hover` |

**4. FolderCombobox and CandidateCombobox** (molecule, new Radix-based Combobox, map decision 4). Anatomy: label, input `role="combobox"` with `aria-autocomplete="list"`, listbox with groups (header, options), optional first option "Use new folder" and a separator, optional warn line on an option. Keyboard: type to filter; Down opens; arrows move; Enter selects; Escape closes, a second Escape clears.

| State | Look |
|---|---|
| default | input `surface`, `control-border` |
| hover | border `text-3` |
| focus | `ring` outline, border `brand` |
| active (open) | listbox as in SourceSelect |
| disabled | opacity 0.55 |
| loading | listbox line "Loading folders" with spinner |
| error | listbox line "Cannot load the folder list. You can type a folder." |
| selected | check icon on the option; an option with a type mismatch shows a warn icon plus text |

**5. PropertyPicker and PropertyCheckbox** (molecule, new, house checkbox pattern: real input, drawn box with `pointer-events: none`, one svg check). Anatomy: fieldset, legend, items (box, label, phrase line), error line.

| State | Look |
|---|---|
| default | 16 px box, 1.5 px `control-border`, radius 4 px |
| hover | item fill `surface-hover` |
| focus | `ring` outline on the box |
| active | item fill `surface-3` |
| disabled | box opacity 0.5, label `text-3`, phrase "Same" |
| loading | n/a (saved with the Merge Choice; the radio shows "Saving") |
| error | fieldset `aria-invalid`, 1 px `bad` border, error line with x icon |
| selected | `brand` box fill, `brand-ink` check |

**6. NameField** (molecule, new composition of the existing `Input`). Anatomy: label, input, "Propose name" icon button, hint line (ok, warn, bad, check in progress), optional action "Use proposed name".

| State | Look |
|---|---|
| default | input `surface`, `control-border` |
| hover | border `text-3` |
| focus | `ring` outline, border `brand` |
| active | n/a |
| disabled | opacity 0.55 |
| loading | hint spinner "Checking the name"; the proposer button shows a spinner |
| error | `aria-invalid`, `bad` border, hint with x icon in `bad`, `aria-describedby` the hint |
| selected | n/a; the "proposed" variant shows the ok hint with the rule names |

**7. Notice** (molecule, new, shared with the ticket 02 banner). Anatomy: icon, body text, optional list, optional actions. Variants: info, warn, bad, brand. A 1 px `line-strong` border on all sides; the icon carries the color. `role="status"` for info and warn, `role="alert"` for blocking items and errors.

| State | Look |
|---|---|
| default | `surface-2` fill, icon in the status color |
| hover, focus, active | only on its action buttons (standard button states) |
| disabled | actions disabled in a read-only session |
| loading | the action button shows a spinner ("Confirm row" while `row_confirm` runs) |
| error | bad variant |
| selected | n/a |

**8. ProposalCard** (molecule; ticket 06 owns the spec; used here). States: default; hover and focus on its buttons; disabled in a read-only session; loading on the accept button while `proposal_accept` runs; error hint for `source_changed`; selected n/a.

**9. RemovalPolicyDialog** (organism, new, Radix Dialog). Anatomy: title, description, policy radio group (ChoiceRadio), Cascade table in its own scroll region, Repoint Combobox, footer (Cancel, confirm). States: default; focus trap and focus return; confirm disabled until valid (Repoint with no candidate); loading on confirm while `removal_policy_set` runs; error notice in the body when the call fails; the selected radio shows its sub-content. The Cascade confirm uses the destructive fill (`bad` with `text-inverse`) in the dialog, and the Remove choice is the trigger (token by intent).

**10. BreakMatchDialog** (Radix AlertDialog). Title, text, "Cancel", "Break match". Focus starts on "Cancel".

### Measurements (2026-10-31, Chrome 156.0.8078.49, playwright 1.63.0, axe-core 4.10.2)

- Page overflow (`measure.mjs`): 22 screens x 6 sizes (1024 x 640, then 1152, 1279, 1280, 1366, 1440 at 900 high) x 2 themes = 264 measurements. On all 264: page horizontal overflow 0 px, elements past the right edge 0, pane body horizontal overflow 0 px, and the dialog is inside the window.
- Pane mode: sheet 400 px at 1024, 1152, 1279; column 360 px at 1280, 1366, 1440.
- Dialog: 640 px wide and inside the window at all 6 sizes, also at 1024 x 640.
- axe (the rule tags of ticket 01), 22 screens at 1440 x 900, dark and light: 0 violations on all 44 (after 2 fixes, see below).
- Click test: a click on the label of each of 4 enabled radios selects that radio. A click on a property checkbox label toggles it. All pass.
- Kit `verify_states.mjs` (default, hover, focus), through the gate wrapper with `DS_REQUIRE_BROWSER=1`, on a static snapshot of each of the 22 screens in dark and in light: pass on all 44 (45 to 82 element-states for each snapshot, exit 0). The status badges use soft tints with alpha, but the gate reported no failure on them, so no opaque tint was necessary.
- Kit `measure_render.mjs` on 6 snapshots x 2 themes: every text element meets AA.
- Kit `verify_target_size.mjs`: pass at 1280 px on all checked dark snapshots. At 414 px it reports the dialog radio inputs at 20.3 px high. 414 px is a phone width, and the app has no phone layout (map decision 5), so this is not a defect here.
- Kit `slop_tells.mjs --strict`: no tells on the pane screens. The dialog snapshots give MED "only one distinct shadow" and LOW "near-duplicate neutrals" (`surface-3` and `surface-hover`, both existing tokens). These are heuristic; no change.
- Kit `check_no_emoji.py` on the prototype: no emoji, no em dash or en dash.
- Raw results: `prototypes/04/shots/result.json`.

Fixes that the gates found:

1. axe `aria-required-children` and `aria-required-parent` on the folder Combobox: the groups were nested `ul` and `li`. Fix: the listbox holds `role="group"` elements directly, with `aria-labelledby` the group header. The separator is `aria-hidden`.
2. axe `color-contrast` in light: the "Proposed" badge (`brand` on `brand-soft`, on the `brand-soft` card) was 4.32:1 and 4.29:1. Fix: the badge text uses `brand-strong`. Fact for ticket 09: a `brand` text badge on a `brand-soft` card fails AA in light.
3. `verify_states` on the Cascade confirm: the generic `.btn:hover` replaced the `bad` fill with `surface-hover` (1.17:1 dark, 1.13:1 light). Fix: the destructive fill keeps `bad` on hover and changes the border to `text`. Fact for ticket 09: the theme has no hover token for a destructive fill. Add one (for example `bad-strong`) or keep this rule.

UNMEASURED: the real Radix focus trap and focus return (the prototype is static markup; ticket 09 runs `verify_focustrap`). Keyboard paths in the radio group and the Combobox (static markup). The 300 ms name check timing. Screen reader output.

### Screenshots

`prototypes/04/shots/<screen>-<theme>-<width>.png`, dark and light, at 1440 and 1024 wide. The repo `.gitignore` excludes `*.png`, so git does not keep them. Screens: `take`, `take-source-open`, `take-folder-open`, `props`, `props-none`, `newname-warn`, `newname-clash`, `rename`, `target-missing-saving`, `remove-block`, `remove-none`, `remove-cascade`, `dlg-block`, `dlg-cascade`, `dlg-repoint`, `dlg-break`, `report-measure`, `locked`, `multi`, `loading`, `error`, `stale`.

### Backend change requests

1. `POST name-propose`: optional input `candidate` (name). The reply adds `breaks` (rule ID and rule text for each broken confirmed or user rule) and `clash` (the object with the same name, case-insensitive, or null). Reason: no contract checks a name that the user types (Q8).
2. `GET display-folders?source=<id>`: the display folder paths of one source (target or donor), optionally for one object type. Reason: the folder Combobox needs the folders of the target and of the selected source (spec 7.2, Q9).
3. `alignment_override` (break): state that it removes the Merge Choice of the row, and return the new row keys. Reason: the UI must move the selection and tell the user that the choice is removed (Q11).
4. `merge_choice_set`: accept the values `promote` and `copy_to_report` for report measure rows (with new name and display folder). Reason: spec 7.4 and technical design 6.2 make them plan steps, but section 14.2 has no call for them (Q16).

### Inputs for later tickets

- 03: Enter or a click on a row opens the pane. The grid row of the open pane is `aria-selected`. Many selected rows show the "rows selected" pane. "Previous row" and "Next row" follow the grid order and the active filter.
- 05: "Show impact of this row" opens the Impact tab with the row filter. The removal dialog uses `GET impact/removal/{object}`, not `GET impact`.
- 06: the card in the pane uses the ticket 06 spec. The "Proposed" badge text uses `brand-strong`.
- 09: new parts ChoiceRadio group, SourceSelect, Combobox (groups, "use new" option, warn line), PropertyCheckbox, NameField, Notice, RemovalPolicyDialog; a hover token for the destructive fill; the copy rows above.
