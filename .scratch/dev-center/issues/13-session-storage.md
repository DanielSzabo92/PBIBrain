# How does the app store a merge session?

Type: grilling
Status: open
Blocked by: 07

## Question

File format and location of a session. What does it store (sources and their snapshots, alignment, merge choices, agent proposals and reasons, log)? How does the app find that a source changed after the session started? How does a session move between PCs through git without secrets?

## Context

- From "What are the match and compare rules?": the session must store the compare mode (default or strict), the alignments that the user confirmed or broke by hand, and the rename proposals that the user rejected.
- From "How does the Change Plan engine work?": the session stores the removal policy for each removed object, the accepted or mapped prerequisites, and a stable session ID. The session does not store the plan as the source of truth: the engine computes it again. New lineageTags come from the session ID and the row key (UUIDv5), so the session ID must never change.
