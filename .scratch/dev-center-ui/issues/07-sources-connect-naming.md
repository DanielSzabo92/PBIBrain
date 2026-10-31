# How does the user add cloud sources and manage naming rules?

Type: grilling
Status: open
Blocked by: 02

## Question

Design the cloud connect dialog (sign-in, access type, connect test result), the "Pull to local PBIP" flow, and the naming rules screen.

## Context

- Cloud (version 1 read only, technical design section 10): interactive Microsoft sign-in (`cloud_sign_in`), connect (`cloud_connect`) with access type `Read` (default) or `Read/Write` (spec 4.2; `Read/Write` is recorded in version 1 but no cloud source is a write target until 1.1). `pull_to_local` exports a cloud model as TMDL into a local folder with a PBIP skeleton.
- Connect test result: show the conditions that the app can check, and say what it cannot check. Reports that the app cannot read show as "not checked: report not readable" with the fix "export the report to a local PBIP" (section 10.3). Reports in other workspaces are "not checked".
- No XMLA write warning dialog in version 1 (out of scope, map).
- Naming rules (section 5): rules with status (proposed, confirmed, rejected), origin (detected, user), support ("37 of 40 measures"), break counts. Actions: `naming_rule_confirm`, `naming_rule_reject`, `naming_rule_edit`, `naming_rules_copy`. User rules include a regular expression kind.
- Skills: `design-doctrine`, `design-component` for the dialog parts.

## Done when

The answer gives: the connect dialog steps and states (signed out, signing in, sign-in failed, connected, test result), the access type control and its copy, the Pull to local flow, the naming rules screen layout and its actions, the rule editor, and the copy for each error and refusal.
