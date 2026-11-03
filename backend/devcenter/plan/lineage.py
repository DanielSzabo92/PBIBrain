"""Deterministic lineageTags of new objects (technical design section 6.6, ADR 0002).

A new tag is a UUIDv5 of the session ID and the row key in a fixed name
space. Thus the same session state gives the same tags, the same plan hash,
and the same guard contract.
"""

from __future__ import annotations

import uuid

# Fixed name space of PBIBrain lineageTags. Do not change it: tags stay in the user's models.
LINEAGE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://pbibrain.local/devcenter/lineage-tag")

# The object types that have a lineageTag.
TAGGED_KINDS = frozenset({"table", "column", "measure", "hierarchy", "expression", "function"})


def new_lineage_tag(session_id: str, row_key: str) -> str:
    return str(uuid.uuid5(LINEAGE_NAMESPACE, f"{session_id}\n{row_key}"))
