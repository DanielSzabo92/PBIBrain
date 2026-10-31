# 08: S4 naming rules

Status: open. Lane: backend. Design step: S4 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): [04](04-s2-session-store.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: S4. Naming rules

- Goal: detect, store, check, and propose names.
- Code areas: `backend/devcenter/naming/`, `backend/api/app.py` (`naming-rules`, `name-propose`), JS API rule methods.
- Depends on: S2 (S3 for break counts on new names in the plan, later).
- Acceptance tests:
  - The tokenizer splits separators and case changes for a fixed name list.
  - Detection offers a rule at 5 objects and 80%, not at 4 objects or 79%; the limits come from settings.
  - A rejected rule is not offered again.
  - The proposer applies the fixed order and returns the rule IDs; a clash adds "(<donor source>)".
  - A user regular-expression rule checks a name.
  - The rule file is in `.pbibrain/naming-rules/` and outside `definition/`; a bridge TMDL write leaves it.
  - Copy of a rule set gives "proposed" rules.
  - UC16: reject of a user rule removes it; reject of a detected rule keeps it as rejected; edit with no rule ID creates a confirmed user rule; edit of a proposed rule confirms it.
  - UC18: `GET naming-rules` gives the rule count for each session source model.
  - UC19: `name-propose` with `candidate` returns `breaks` for a name that breaks a confirmed rule, and `clash` for a name that exists (case-insensitive).
  - UC34: `naming_rule_edit` of a duplicate rule returns `action_not_allowed` with `details.existing_rule_id`.
