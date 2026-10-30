# What must change so that the change guard accepts create, delete, and rename?

Type: grilling
Status: open
Blocked by: 01

## Question

The guard now accepts only property edits and fails closed on create and delete. The merge reuses only its safety checks (no Docker). What must the contract, the scope check, and the file coverage check learn so that they accept a Change Plan with create, delete, rename, and reference rewrite, and still reject changes outside the plan?
