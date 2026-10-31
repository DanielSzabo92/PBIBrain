# How does the Change Plan engine work?

Type: grilling
Status: open
Blocked by: 01, 04, 07

## Question

Which operation types exist? How does the engine sort them by dependency? How do the removal policies (block, cascade, repoint) behave? How does the engine rewrite references after a rename (DAX, field parameters, RLS, report bindings)? When does a copied object get a new lineageTag? How does a model change carry over to report operations?

## Context

- From "What are the match and compare rules?": the alignment can hold a "name clash" row (a donor object with the same name as a renamed target object). The plan must solve the name before it adds that object.
- From "What are the match and compare rules?": the compare reads references through the alignment. The reference rewrite after a rename must use the same alignment map.
- From "What must change so that the change guard accepts create, delete, and rename?": the plan must set the new lineageTag of each created object before the write, so that the guard contract knows the new object IDs.
- From the same ticket: write each reference rewrite as a separate expression operation with the exact old text and the exact new text. The guard accepts no wildcard and no "update all references" operation.
- From the same ticket: write the rename of an object with no lineageTag (role, partition, calculation item, report page) as one linked delete-and-create pair. The guard accepts the pair only when all properties except the name are equal.
- From the same ticket: the write step must produce TMDL files that are byte-equal to the TOM serialization. If a target file is not in that format, the plan needs a separate "format only" apply first.
