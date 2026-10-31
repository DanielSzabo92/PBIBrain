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
