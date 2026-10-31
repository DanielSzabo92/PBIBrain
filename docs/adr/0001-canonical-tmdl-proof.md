# The guard proves model writes by a canonical TMDL check and a full tree compare

Status: accepted (2026-10-31)

A merge creates, deletes, and renames objects, and the guard's line-by-line TMDL accounting accepts only same-length line replacements. We did not extend that line accounting. Each changed `.tmdl` file must be byte-equal to the TOM serialization of the candidate model, and the guard then compares the full baseline and candidate TOM trees, where each difference must match a plan operation. Reason: block-level line accounting for added and removed text is complex and easy to break, while the TOM output is deterministic and the tree compare also covers object types that the graph does not model.

## Consequences

- A baseline file that is not in TOM format (comments, hand edits, other order) blocks the apply. The app offers a separate "format only" apply, which the guard accepts only when the tree compare is empty.
- An update of the TOM package can change the canonical bytes. Golden files must change with it.
