# How does the user set a Merge Choice on one row, with a new name, a display folder, and a removal policy?

Type: grilling
Status: open
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
