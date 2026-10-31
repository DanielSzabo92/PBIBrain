# How does the app find and store naming rules?

Type: grilling
Status: resolved
Blocked by: 

## Question

Which patterns does the app detect (prefix, suffix, letter case, separators, unit words, folder by type)? How sure must a pattern be before the app offers it? Where are the rules stored for each target model? How does a rule check a new name, and how does the agent use the rules to propose a name?

## Context

- From "How does the Change Plan engine work?": a name clash row is a blocking item. The app proposes a new name from the naming rules.

## Answer

Resolved 2026-10-31. The user (through the orchestrator session) accepted all recommendations.

1. Term and shape. One term: "Naming Rule" (added to `CONTEXT.md`). The UI can call a proposed detected rule a "naming pattern". Each rule has:
   - a stable rule ID,
   - a scope: object type, plus an optional table filter or display folder filter,
   - one check kind from a fixed list: prefix, suffix, letter case (Title Case, camelCase, PascalCase, snake_case, UPPER, lower), separator (space, underscore, none), unit word, folder by type, and regular expression (user rules only),
   - an origin: detected or user,
   - a status: proposed, confirmed, or rejected.
2. Object types in scope (first version): tables, data columns, calculated columns, calculated tables, measures, hierarchies, calculation groups, and report measures. Report measures use the measure rules of the target model. Roles, perspectives, partitions, and calculation items are not in scope.
3. Detection. The app detects from the target model only. It detects when the user opens the rules screen, or when the first session for that target starts. It offers a rule only when the scope has at least 5 objects and at least 80% of them obey the rule. The app shows the support, for example "37 of 40 measures". Both limits are settings, not fixed code.
4. Status. A proposed rule is only a hint. Only a confirmed rule or a user rule marks a name. When the user deletes a detected rule, the app keeps it as "rejected". The next detection does not offer a rejected rule again.
5. Unit words and folder by type.
   - A unit-word rule links a word to a format kind. Examples: percent-format measures end with `%`; currency measures end with `Amt`.
   - A folder-by-type rule tells where an object type lives. Examples: all measures are in the table `_Measures`; measures with the prefix `KPI` are in the display folder `KPIs`.
   - The app does not detect folder rules for columns.
6. Storage.
   - Local PBIP target: `<project root>/.pbibrain/naming-rules/<model folder name>.json`. The file is outside the model `definition` folder. The TOM serializer does not delete non-`.tmdl` files. The file is outside the change guard scope, because it is app configuration, not a model change. It moves through git with the project.
   - Cloud target with no local project: `%APPDATA%/PBIBrain/naming-rules/<workspace ID>/<model ID>.json`.
   - Not a model annotation: that changes the model and needs a guarded write for each rule edit.
   - The session stores the rule file path and a hash of the rule set that it used.
7. Check.
   - The app checks only the names that the plan creates or changes: "Add", "Add as new name", rename, and promote. It does not mark existing target names in the merge rows.
   - The rules screen shows, for each rule, the count of existing target names that break it.
   - A rule break is a warning (plan status "Valid with warnings"), never a blocking item.
   - The name clash check is separate and built in. It is a blocking item. It compares names case-insensitively.
8. Name proposal.
   - The backend has a deterministic name proposer. Input: a candidate name (normally the donor name). It applies the confirmed rules in a fixed order: letter case, separator, prefix, suffix and unit word, folder.
   - For a name clash, it adds the donor source name in parentheses, for example `Total Sales (Model B)`, and checks the result again.
   - Output: the proposed name and the list of rule IDs that it used. This fills the spec rule "the agent MUST give the rule that it used".
   - The agent gets the proposer through a tool. When the agent proposes a different name, the tool checks it. The tool rejects a name that breaks a confirmed rule, and returns the rule ID. The agent cannot override a confirmed rule. It must ask the user a question.
9. Empty target and copy. A new empty target gives no detected rules. The user can copy the rule set of a different model (for example a donor) into the target. The copied rules arrive as "proposed", and the user confirms them.

Build items: name tokenizer (separators and case changes), detector with support counts, rule file read and write, rule checker, deterministic name proposer, rules screen data (rules, status, support, break counts), copy rule set.

No ADR: the storage location is easy to move later (one small file for each model), and it has no real trade-off against the model data.
