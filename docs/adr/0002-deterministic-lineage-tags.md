# Deterministic UUIDv5 lineageTags for new objects

Status: accepted (2026-10-31)

When the Change Plan needs a new lineageTag (a copy that the target already has, "Add as new name", or a duplicate donor tag), it makes a UUIDv5 from the session ID and the row key, not a random UUID. Reason: the plan is derived again on each change, and the guard contract must know the IDs of new objects before the write; random tags would change the plan hash and the contract each time. The tags stay in the user's models after apply, so a later change of the rule is hard to reverse.

## Considered options

- Random UUIDv4 at plan time, stored in the session: rejected, because the session stores only user state, and stored tags go stale when the plan changes.
- No tag (let Power BI Desktop add it): rejected, because the guard identity map needs the ID before the write.
