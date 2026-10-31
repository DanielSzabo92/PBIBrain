# How does the app store a merge session?

Type: grilling
Status: open
Blocked by: 07

## Question

File format and location of a session. What does it store (sources and their snapshots, alignment, merge choices, agent proposals and reasons, log)? How does the app find that a source changed after the session started? How does a session move between PCs through git without secrets?

## Context

- From "What are the match and compare rules?": the session must store the compare mode (default or strict), the alignments that the user confirmed or broke by hand, and the rename proposals that the user rejected.
