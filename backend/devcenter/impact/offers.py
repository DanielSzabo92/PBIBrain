"""Carry-over offers catalog for Dev Center impact (technical design section 7, AC8).

Discovers donor pages, visuals, and filters that utilize model objects added
to the target by the Change Plan. Bookmarks referencing added objects are
flagged as information-only (no copy action).
"""

from __future__ import annotations

import hashlib
from typing import Any
from collections.abc import Mapping, Sequence

from backend.devcenter.compare.extract import CompareObject
from backend.devcenter.plan.fields import field_locations


def _offer_id(source_id: str, kind: str, name: str, page_name: str | None = None) -> str:
    seed = f"{source_id}:{kind}:{page_name or ''}:{name}"
    return "off-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def extract_offers(
    *,
    donor_sources: Mapping[str, Sequence[CompareObject]],
    source_names: Mapping[str, str],
    added_model_keys: set[str],
    target_existing_keys: set[str],
    selected_offers: Sequence[str] = (),
    donor_bookmarks: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Catalog carry-over offers from donor reports for added model objects."""
    offers: list[dict[str, Any]] = []
    selected_set = set(selected_offers)

    # Normalized lookup for added model objects (e.g. "sales/newm", "newm")
    added_names = {key.split(":")[-1].casefold() for key in added_model_keys}
    target_names = {key.split(":")[-1].casefold() for key in target_existing_keys} | added_names

    for source_id, objects in donor_sources.items():
        src_name = source_names.get(source_id, source_id)
        pages = {obj.name: obj for obj in objects if obj.kind == "page"}
        visuals = [obj for obj in objects if obj.kind == "visual"]

        # 1. Visual offers
        for vis in visuals:
            locs = field_locations(vis)
            used_added: list[str] = []
            missing_fields: list[str] = []

            for loc in locs:
                ref_key = f"{loc.entity}/{loc.property}".casefold()
                simple_prop = loc.property.casefold()
                if ref_key in added_names or simple_prop in added_names:
                    used_added.append(f"{loc.entity}[{loc.property}]")
                elif ref_key not in target_names and simple_prop not in target_names:
                    missing_fields.append(f"{loc.entity}[{loc.property}]")

            if used_added:
                page_name = vis.table  # in CompareObject, table holds page_id / page folder
                page_obj = pages.get(page_name)
                display_page = page_obj.name if page_obj else page_name
                oid = _offer_id(source_id, "visual", vis.name, display_page)
                offers.append({
                    "id": oid,
                    "source_id": source_id,
                    "source_name": src_name,
                    "kind": "visual",
                    "name": vis.name,
                    "page_name": display_page,
                    "references": sorted(set(used_added)),
                    "missing_fields": sorted(set(missing_fields)),
                    "information_only": False,
                    "selected": oid in selected_set,
                })

        # 2. Page offers (pages containing visuals referencing added objects)
        for page_name, page_obj in pages.items():
            page_visuals = [v for v in visuals if v.table == page_name]
            page_added: set[str] = set()
            for v in page_visuals:
                for loc in field_locations(v):
                    ref_key = f"{loc.entity}/{loc.property}".casefold()
                    simple_prop = loc.property.casefold()
                    if ref_key in added_names or simple_prop in added_names:
                        page_added.add(f"{loc.entity}[{loc.property}]")
            if page_added:
                oid = _offer_id(source_id, "page", page_obj.name)
                offers.append({
                    "id": oid,
                    "source_id": source_id,
                    "source_name": src_name,
                    "kind": "page",
                    "name": page_obj.name,
                    "page_name": None,
                    "references": sorted(page_added),
                    "missing_fields": [],
                    "information_only": False,
                    "selected": oid in selected_set,
                })

    # 3. Bookmark offers (information only per AC8)
    for bm in donor_bookmarks:
        source_id = bm.get("source_id", "")
        src_name = source_names.get(source_id, source_id)
        name = bm.get("display_name") or bm.get("name") or "Bookmark"
        refs = bm.get("references") or []
        # Check if bookmark references any added object
        has_added_ref = any(str(r).casefold() in added_names for r in refs)
        if has_added_ref or not refs:
            oid = _offer_id(source_id, "bookmark", name)
            offers.append({
                "id": oid,
                "source_id": source_id,
                "source_name": src_name,
                "kind": "bookmark",
                "name": name,
                "page_name": bm.get("page_name"),
                "references": sorted(set(refs)),
                "missing_fields": [],
                "information_only": True,
                "selected": False,
            })

    # Stable sort by source, kind, name
    return sorted(offers, key=lambda item: (item["source_id"], item["kind"], item["name"]))
