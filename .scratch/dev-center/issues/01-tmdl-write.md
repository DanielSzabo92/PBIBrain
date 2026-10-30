# How can the app write TMDL safely?

Type: research
Status: open
Blocked by: 

## Question

How can the app create, delete, rename, and replace model objects (tables, columns, measures, relationships, hierarchies, calculation groups, field parameters, functions, roles, perspectives, translations) and save them as TMDL with Microsoft's own library (TOM / Microsoft.AnalysisServices), through the existing .NET bridge? How stable is the output format (file layout, ordering, lineageTag, whitespace), so that a diff shows only the real changes? What does the library not support?
