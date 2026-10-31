# What are the exact agent tools?

Type: grilling
Status: open
Blocked by: 07, 10

## Question

Define each MCP tool (inputs, outputs, errors): session read, compare rows, impact, naming rules, propose a merge choice with confidence and reason, ask a question, validate. Do they live in the existing Brain MCP server or in a new server? How does the design make sure that the agent never reaches the write path?

## Context

- From "What are the match and compare rules?": a compare row has one state for each source (Type conflict, Missing, Renamed, Moved, Different, Same), a "changed" mark, notes such as "same after rename" or "name clash", and a list of property phrases. The compare tool returns this shape.
- From "What are the match and compare rules?": a "possible rename" and an agent alignment are proposals only. The user must confirm them.
- From "How does the Change Plan engine work?": the engine derives the plan from the session state, and nobody edits it by hand. Thus the agent changes the plan only through proposed Merge Choices and removal policies that the user accepts. The validate tool returns the plan status, the blocking items, and the warnings.
- From "Which impact data does the backend give to the UI?": the impact tool returns Impact items (direction, severity, certain or possible, reason phrase ID and text, shortest path with path count, blocking flag, allowed action IDs), a completeness block, and Offer records. The agent can propose an action ID. The action changes the session state only after the user accepts it.
- From "How does the app find and store naming rules?": `naming_rules_get` returns the Naming Rules of the target (ID, scope, check kind, origin, status, support). Add a name-proposal tool: input a candidate name and the object type; output the proposed name and the rule IDs that it used (deterministic). When the agent proposes a name in a Merge Choice, the tool checks it and rejects a name that breaks a confirmed rule, with the rule ID. The agent cannot override a confirmed rule; it must ask the user a question.
