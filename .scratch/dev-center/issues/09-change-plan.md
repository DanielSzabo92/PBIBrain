# How does the Change Plan engine work?

Type: grilling
Status: open
Blocked by: 01, 04, 07

## Question

Which operation types exist? How does the engine sort them by dependency? How do the removal policies (block, cascade, repoint) behave? How does the engine rewrite references after a rename (DAX, field parameters, RLS, report bindings)? When does a copied object get a new lineageTag? How does a model change carry over to report operations?

## Context

- From "What are the match and compare rules?": the alignment can hold a "name clash" row (a donor object with the same name as a renamed target object). The plan must solve the name before it adds that object.
- From "What are the match and compare rules?": the compare reads references through the alignment. The reference rewrite after a rename must use the same alignment map.
