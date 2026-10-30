# What are the match and compare rules?

Type: grilling
Status: open
Blocked by: 06

## Question

For each object type: which properties count when the app says "same" or "different"? What does the default normalization ignore, and what does "strict" keep? How does the app show a property difference in plain words? How do the match steps (lineageTag, name, moved, possible rename, manual) rank, and what happens when two steps give different answers?

## Context

- From "Which new object types must the graph learn first?": this ticket owns the property list for each object type in the first version.
- From "How can the app write TMDL safely?": relationships, roles, perspectives, cultures, calculation items, and partitions have no lineageTag. They need a different match key.
