# Retrieval review

## Goal

Give agents a deterministic way to find one canonical Power BI object across many models and reports, with enough evidence to verify the match.

## Current weaknesses

1. `GraphRepository.search_objects()` is an unranked substring scan. It searches serialized arbitrary properties, so incidental metadata can outrank nothing and every hit looks equally reliable.
2. `backend.api.objects.search_objects()` filters only after the full scan. It returns no match reason, ambiguity signal, total count, or bounded page metadata.
3. Duplicate names across models are indistinguishable unless a caller already knows the canonical model ID. Picking the first result is unsafe for agents.
4. Empty queries can return the entire graph. There is no API-level limit or offset validation.
5. Context scope is derived only from `model_id` and `report_id` fields. A target `MODEL` or `REPORT` can therefore omit its own canonical ID from scope.
6. Context evidence is detached from the node or edge that supplied it, which makes downstream claims harder to audit.

## Decision

Add a small read-only retrieval module above the canonical repository. It will:

- rank controlled identity and descriptive fields with deterministic lexical rules;
- apply strict model, report, object-type, and status scope before ranking;
- return an exact total plus validated bounded pagination;
- attach compact match evidence to every hit;
- report tied top matches and duplicate exact names as ambiguity;
- resolve only canonical IDs or unique exact source/name references;
- leave the existing list-returning search API compatible.

Context will include canonical `MODEL` and `REPORT` target IDs in scope and wrap evidence with its source object or edge ID. No embeddings, vector database, model-specific scoring, fuzzy guessing, or query engine is needed.
