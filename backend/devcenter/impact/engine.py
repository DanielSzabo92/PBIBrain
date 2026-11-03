"""Core impact analysis engine (technical design section 7, AC1-AC5, AC13, AC14).

Implements dual-direction graph traversal:
1. Breaks walk (downstream): identifies impacted dependents in target model
   and reports from deleted, renamed, replaced, or modified objects using
   `backend.impact.analyzer.analyze_impact`.
2. Needs walk (upstream): identifies missing prerequisites from added donor
   objects, translated through alignment keys and session overrides.
3. Classifies certainty (certain vs possible) and strictly enforces AC3:
   possible items never block.
4. Deterministic stable item IDs (AC2).
5. Sibling reports bound to target model carry "not changed by this plan" (AC5).
"""

from __future__ import annotations

from collections import defaultdict, deque
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.devcenter.alignment.keys import fold
from backend.devcenter.compare.extract import CompareObject
from backend.devcenter.plan.fields import field_locations
from backend.devcenter.plan.refs import ModelIndex
from backend.impact.analyzer import analyze_impact

PHRASES_PATH = Path(__file__).resolve().parents[1] / "contracts" / "phrases.json"


def _load_phrases() -> dict[str, dict[str, str]]:
    if PHRASES_PATH.is_file():
        try:
            return json.loads(PHRASES_PATH.read_text(encoding="utf-8")).get("phrases", {})
        except Exception:
            pass
    return {}


PHRASES = _load_phrases()


def _get_phrase(phrase_id: str, fallback_text: str = "") -> tuple[str, str]:
    if phrase_id in PHRASES:
        return phrase_id, PHRASES[phrase_id]["text"]
    # Fallback lookup without group prefix
    clean = phrase_id.split(".")[-1]
    if clean in PHRASES:
        return clean, PHRASES[clean]["text"]
    return phrase_id, fallback_text or phrase_id.replace("_", " ")


def deterministic_item_id(
    direction: str,
    impacted_object_id: str,
    root_cause_id: str,
    rule_id: str,
    path_summary: str = "",
) -> str:
    """AC2: Compute stable, deterministic item ID across runs."""
    seed = f"{direction}:{impacted_object_id}:{root_cause_id}:{rule_id}:{path_summary}"
    return "imp-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def build_graph_from_objects(
    objects: Sequence[CompareObject],
    *,
    model_id: str = "model",
    report_id: str = "report",
) -> dict[str, Any]:
    """Convert CompareObjects into a canonical graph representation for analyze_impact."""
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    edge_idx = 0

    model_objs = [obj for obj in objects if obj.domain == "model"]
    report_objs = [obj for obj in objects if obj.domain == "report"]

    # 1. Model Root Node
    nodes[model_id] = {
        "id": model_id,
        "type": "MODEL",
        "name": model_id,
        "model_id": model_id,
        "properties": {},
    }

    # 2. Add Tables, Columns, Measures, Relationships
    for obj in model_objs:
        k = obj.kind.upper()
        nid = obj.source_key
        props = dict(obj.props)
        if obj.table:
            props["table_id"] = f"table:{obj.table}"

        nodes[nid] = {
            "id": nid,
            "type": k,
            "name": obj.name,
            "model_id": model_id,
            "properties": props,
        }

        # Parent-child CONTAINS edges
        if k == "TABLE":
            edge_idx += 1
            edges.append({
                "id": f"e-{edge_idx}",
                "from_id": model_id,
                "to_id": nid,
                "type": "CONTAINS",
                "evidence_class": "FACT",
                "properties": {},
            })
        elif k in {"COLUMN", "MEASURE", "PARTITION", "HIERARCHY"} and obj.table:
            table_nid = f"table:{obj.table}"
            edge_idx += 1
            edges.append({
                "id": f"e-{edge_idx}",
                "from_id": table_nid,
                "to_id": nid,
                "type": "CONTAINS",
                "evidence_class": "FACT",
                "properties": {},
            })

    # 3. Add Report Objects (Pages, Visuals, Report Measures)
    nodes[report_id] = {
        "id": report_id,
        "type": "REPORT",
        "name": report_id,
        "model_id": model_id,
        "report_id": report_id,
        "properties": {},
    }

    for obj in report_objs:
        k = obj.kind.upper()
        nid = obj.source_key
        props = dict(obj.props)
        if obj.table:
            props["page_id"] = f"page:{obj.table}"

        nodes[nid] = {
            "id": nid,
            "type": k,
            "name": obj.name,
            "model_id": model_id,
            "report_id": report_id,
            "properties": props,
        }

        if k == "PAGE":
            edge_idx += 1
            edges.append({
                "id": f"e-{edge_idx}",
                "from_id": report_id,
                "to_id": nid,
                "type": "CONTAINS",
                "evidence_class": "FACT",
                "properties": {},
            })
        elif k == "VISUAL" and obj.table:
            page_nid = f"page:{obj.table}"
            edge_idx += 1
            edges.append({
                "id": f"e-{edge_idx}",
                "from_id": page_nid,
                "to_id": nid,
                "type": "CONTAINS",
                "evidence_class": "FACT",
                "properties": {},
            })

    # 4. Resolve DAX references (MEASURE / COLUMN -> DEPENDS_ON)
    model_index = ModelIndex.build(model_objs, report_objs)
    for obj in model_objs + report_objs:
        expr = obj.props.get("expression")
        if isinstance(expr, str) and expr.strip():
            refs, _ = model_index.references(expr, obj.table)
            for ref in refs:
                if ref.key and ref.key in nodes:
                    edge_idx += 1
                    edges.append({
                        "id": f"e-{edge_idx}",
                        "from_id": obj.source_key,
                        "to_id": ref.key,
                        "type": "DEPENDS_ON",
                        "evidence_class": "FACT",
                        "properties": {},
                    })

    # 5. Resolve Visual field bindings (VISUAL -> USES / FILTERS)
    for obj in report_objs:
        if obj.kind == "visual":
            locs = field_locations(obj)
            for loc in locs:
                # Find matching column or measure
                target_key = f"{loc.kind}:{loc.entity}/{loc.property}"
                if target_key not in nodes:
                    # Try simple measure key
                    target_key = f"measure:{loc.entity}/{loc.property}"
                if target_key not in nodes:
                    # Match by name
                    target_key = next((n for n in nodes if nodes[n].get("name") == loc.property), None)

                if target_key and target_key in nodes:
                    edge_idx += 1
                    edge_type = "USES" if loc.projection else "FILTERS"
                    edges.append({
                        "id": f"e-{edge_idx}",
                        "from_id": obj.source_key,
                        "to_id": target_key,
                        "type": edge_type,
                        "evidence_class": "FACT",
                        "properties": {},
                    })

    return {"nodes": list(nodes.values()), "edges": edges}


class ImpactEngine:
    """Evaluates breaks and needs across models and reports."""

    def __init__(
        self,
        *,
        target_model_id: str | None,
        target_report_id: str | None,
        target_objects: Sequence[CompareObject],
        donor_objects: Mapping[str, Sequence[CompareObject]],
        plan: Mapping[str, Any],
        removal_policies: Mapping[str, Any] | None = None,
        need_mappings: Mapping[str, Any] | None = None,
        item_actions: Mapping[str, Any] | None = None,
        sibling_report_objects: Mapping[str, Sequence[CompareObject]] | None = None,
        alignment_index: Mapping[str, Mapping[str, str]] | None = None,
    ) -> None:
        self.target_model_id = target_model_id
        self.target_report_id = target_report_id
        self.target_objects = list(target_objects)
        self.donor_objects = {k: list(v) for k, v in donor_objects.items()}
        self.plan = dict(plan)
        self.removal_policies = dict(removal_policies or {})
        self.need_mappings = dict(need_mappings or {})
        self.item_actions = dict(item_actions or {})
        self.sibling_report_objects = {k: list(v) for k, v in (sibling_report_objects or {}).items()}
        self.alignment_index = dict(alignment_index or {})

        # Build primary target graph
        self.target_graph = build_graph_from_objects(self.target_objects)
        self.target_node_map = {n["id"]: n for n in self.target_graph["nodes"]}

    def evaluate_all(self, *, single_row_key: str | None = None) -> list[dict[str, Any]]:
        """Run Breaks walk and Needs walk, returning unified list of ImpactItem records."""
        items: list[dict[str, Any]] = []

        # 1. Downstream Breaks Walk
        breaks_items = self._run_breaks_walk(single_row_key=single_row_key)
        items.extend(breaks_items)

        # 2. Upstream Needs Walk
        needs_items = self._run_needs_walk(single_row_key=single_row_key)
        items.extend(needs_items)

        # 3. Sibling Reports (AC5: "not changed by this plan")
        sibling_items = self._run_sibling_reports_walk()
        items.extend(sibling_items)

        # Deterministic sorting
        return sorted(items, key=lambda it: (it["direction"], it["impacted_object"]["object_id"], it["id"]))

    def _run_breaks_walk(self, *, single_row_key: str | None = None) -> list[dict[str, Any]]:
        """Breaks walk downstream from deleted, renamed, replaced, or modified objects."""
        # Determine seed objects from Change Plan
        seeds: list[dict[str, Any]] = []
        ops_by_step = defaultdict(list)
        for op in self.plan.get("operations", []):
            ops_by_step[op.get("step_id")].append(op)

        steps = self.plan.get("steps", [])
        for step in steps:
            row_key = step.get("row_key", "")
            if single_row_key and row_key != single_row_key:
                continue

            step_id = step.get("step_id")
            ops = ops_by_step.get(step_id, [])
            if not ops:
                ch = step.get("change")
                target_key = row_key
                if ch == "deleted":
                    seeds.append({"object_id": target_key, "change_type": "deleted", "trigger": "deletion", "row_key": row_key})
                elif ch == "renamed":
                    seeds.append({"object_id": target_key, "change_type": "renamed", "trigger": "rename", "row_key": row_key})
                elif ch == "modified":
                    seeds.append({"object_id": target_key, "change_type": "modified", "trigger": "modified", "row_key": row_key})
            else:
                for op in ops:
                    op_type = op.get("op", "")
                    target_key = op.get("row_key") or op.get("target") or row_key
                    if op_type in {"DELETE", "DELETE_OBJECT", "DELETE_REPORT_MEASURE", "DELETE_PAGE", "DELETE_VISUAL"}:
                        seeds.append({"object_id": target_key, "change_type": "deleted", "trigger": "deletion", "row_key": row_key})
                    elif op_type in {"RENAME", "RENAME_OBJECT", "RENAME_PAIR"}:
                        seeds.append({"object_id": target_key, "change_type": "renamed", "trigger": "rename", "row_key": row_key})
                    elif op_type in {"REPLACE", "SET_PROPERTIES", "REWRITE_EXPRESSION", "REBIND_FIELD"}:
                        seeds.append({"object_id": target_key, "change_type": "modified", "trigger": "modified", "row_key": row_key})

        # Also support single row preview even if plan has no operations for it yet
        if single_row_key and not seeds:
            seeds.append({
                "object_id": single_row_key,
                "change_type": "modified",
                "trigger": "preview",
                "row_key": single_row_key,
            })

        if not seeds:
            return []

        # Run analyzer.py for each seed present in target graph
        items: list[dict[str, Any]] = []
        valid_seed_ids = [s["object_id"] for s in seeds if s["object_id"] in self.target_node_map]

        if not valid_seed_ids:
            return []

        try:
            analysis = analyze_impact(
                self.target_graph,
                valid_seed_ids,
                proposed_changes=None,
                include_report_usage=True,
            )
        except Exception:
            analysis = {"direct_impacts": [], "potential_impacts": []}

        all_records = analysis.get("direct_impacts", []) + analysis.get("potential_impacts", [])

        # Map seeds by object_id
        seed_meta = {s["object_id"]: s for s in seeds}

        for rec in all_records:
            obj_id = rec["object_id"]
            root_id = rec["root_modified_object"]
            sm = seed_meta.get(root_id, {})
            ch_type = sm.get("change_type", "modified")
            row_key = sm.get("row_key", root_id)

            # Skip self-seed if it's the deletion target itself
            if obj_id == root_id and rec.get("analyzer_rule_id") == "seed":
                continue

            node = self.target_node_map.get(obj_id, {})
            node_type = str(node.get("type") or rec.get("object_type") or "object").lower()
            node_name = node.get("name") or obj_id

            # Determine certainty (AC3): DIRECT/STRUCTURAL + FACT edges only = certain; else possible
            cat = rec.get("impact_category", "STRUCTURAL")
            ev_class = rec.get("evidence_class", "FACT")
            is_certain = (cat in {"DIRECT", "STRUCTURAL"}) and (ev_class == "FACT")
            certainty = "certain" if is_certain else "possible"

            # Determine severity
            if not is_certain:
                severity = "needs_review"
            elif ch_type == "deleted":
                severity = "breaks"
            elif ch_type == "renamed":
                severity = "breaks"
            else:
                severity = "changes_value"

            # Reason resolution
            if ch_type == "deleted":
                reason_id = "deleted_object"
            elif ch_type == "renamed":
                reason_id = "renamed_object"
            elif not is_certain:
                reason_id = "filter_context_may_change"
            else:
                reason_id = "modified_object"
            _, reason_text = _get_phrase(reason_id)

            # Path formatting
            path_steps: list[dict[str, Any]] = []
            for step in rec.get("path", []):
                s_to = step.get("to_id", "")
                s_node = self.target_node_map.get(s_to, {})
                edge_t = step.get("edge_type", "CONSUMER").lower()
                edge_phrase_id, edge_phrase = _get_phrase(edge_t, edge_t)
                path_steps.append({
                    "object_id": s_to,
                    "name": s_node.get("name") or s_to,
                    "type": str(s_node.get("type") or "object").lower(),
                    "edge_phrase_id": edge_phrase_id,
                    "edge_phrase": edge_phrase,
                })

            path_summary = ">".join(s["object_id"] for s in path_steps)
            item_id = deterministic_item_id("breaks", obj_id, root_id, rec.get("analyzer_rule_id", "break"), path_summary)

            # Blocking evaluation
            # INVARIANT AC3: Any item evaluated with certainty "possible" MUST have blocking: false.
            if not is_certain:
                blocking = False
            else:
                # Rule 1: Certain breaks caused by deleted object with removal policy Block
                policy = (self.removal_policies.get(row_key) or {}).get("policy", "block")
                if ch_type == "deleted" and policy == "block":
                    blocking = True
                # Rule 2: Unselected dependent of a renamed target object
                elif ch_type == "renamed":
                    action = (self.item_actions.get(item_id) or {}).get("action")
                    blocking = (action != "include_in_rewrite")
                else:
                    blocking = False

            # Allowed actions
            allowed: list[str] = []
            if ch_type == "deleted":
                allowed.extend(["set_policy_block", "set_policy_cascade", "set_policy_repoint"])
            elif ch_type == "renamed":
                allowed.append("include_in_rewrite")
            if node_type == "visual":
                allowed.append("remove_field")

            items.append({
                "id": item_id,
                "direction": "breaks",
                "cause": row_key,
                "impacted_object": {
                    "source_id": self.target_report_id if node_type in {"visual", "page", "report"} else self.target_model_id,
                    "object_id": obj_id,
                    "object_type": node_type,
                    "name": node_name,
                    "domain": "report" if node_type in {"visual", "page", "report_measure", "bookmark"} else "model",
                },
                "severity": severity,
                "certainty": certainty,
                "reason_id": reason_id,
                "reason_text": reason_text,
                "path": path_steps,
                "other_paths_count": 0,
                "blocking": blocking,
                "allowed_actions": allowed,
            })

        return items

    def _run_needs_walk(self, *, single_row_key: str | None = None) -> list[dict[str, Any]]:
        """Upstream Needs walk from added objects in donor graph through alignment (AC4)."""
        needs: list[dict[str, Any]] = []
        def _step_source(s: Mapping[str, Any]) -> str | None:
            if s.get("source_id"):
                return str(s["source_id"])
            ch = s.get("choice")
            if isinstance(ch, dict) and ch.get("source_id"):
                return str(ch["source_id"])
            return None

        added_steps = [s for s in self.plan.get("steps", []) if _step_source(s)]
        target_keys = {obj.source_key for obj in self.target_objects}
        target_names = {fold(obj.name): obj for obj in self.target_objects}

        for step in added_steps:
            source_id = _step_source(step)
            donor_objs = self.donor_objects.get(source_id, [])
            donor_map = {obj.source_key: obj for obj in donor_objs}
            donor_index = ModelIndex.build([o for o in donor_objs if o.domain == "model"], [o for o in donor_objs if o.domain == "report"])

            row_key = step.get("row_key", "")
            if single_row_key and row_key != single_row_key:
                continue

            donor_obj = donor_map.get(row_key)
            if not donor_obj:
                continue

            # Upstream walk: find all outgoing references from this donor object
            queue = deque([donor_obj])
            seen = {donor_obj.source_key}

            while queue:
                curr = queue.popleft()
                refs: list[str] = []

                # From DAX expressions
                expr = curr.props.get("expression")
                if isinstance(expr, str) and expr.strip():
                    resolved_refs, _ = donor_index.references(expr, curr.table)
                    refs.extend(r.key for r in resolved_refs if r.key)

                # From visual field bindings
                if curr.kind == "visual":
                    for loc in field_locations(curr):
                        expected_key = f"{loc.kind}:{loc.entity}/{loc.property}"
                        if expected_key in donor_map:
                            refs.append(expected_key)

                for ref_key in sorted(set(refs)):
                    ref_obj = donor_map.get(ref_key)
                    if not ref_obj:
                        continue

                    # Translate through alignment
                    aligned_target_key = self.alignment_index.get(source_id, {}).get(ref_key)
                    is_satisfied = False

                    if aligned_target_key and aligned_target_key in target_keys:
                        is_satisfied = True
                    elif ref_key in target_keys:
                        is_satisfied = True

                    if not is_satisfied:
                        # Need discovered!
                        ref_name = ref_obj.name
                        ref_folded = fold(ref_name)

                        # Check if target already has an object with same name (name clash)
                        is_clash = ref_folded in target_names
                        # Check if another step adds this prerequisite
                        is_will_add = any(s.get("row_key") == ref_key for s in self.plan.get("steps", []))

                        if is_clash:
                            severity = "name_clash"
                            reason_id = "need_clash"
                            blocking = True
                        elif is_will_add:
                            severity = "will_be_added"
                            reason_id = "need_will_be_added"
                            blocking = False
                        else:
                            severity = "missing"
                            reason_id = "need_missing"
                            blocking = True

                        # Check if user already set a need mapping
                        mapping = self.need_mappings.get(ref_key)
                        if mapping:
                            if mapping.get("action") == "map_to_target":
                                severity = "mapped"
                                reason_id = "need_mapped"
                                blocking = False
                            elif mapping.get("action") == "add_from_donor":
                                severity = "will_be_added"
                                reason_id = "need_will_be_added"
                                blocking = False
                            elif mapping.get("action") == "drop_added_object":
                                blocking = False

                        _, reason_text = _get_phrase(reason_id)
                        item_id = deterministic_item_id("needs", ref_key, row_key, "upstream_need", ref_name)

                        edge_phrase_id, edge_phrase = _get_phrase("depends_on", "depends on")
                        needs.append({
                            "id": item_id,
                            "direction": "needs",
                            "cause": row_key,
                            "impacted_object": {
                                "source_id": source_id,
                                "object_id": ref_key,
                                "object_type": ref_obj.kind,
                                "name": ref_name,
                                "domain": ref_obj.domain,
                            },
                            "severity": severity,
                            "certainty": "certain",
                            "reason_id": reason_id,
                            "reason_text": reason_text,
                            "path": [{
                                "object_id": ref_key,
                                "name": ref_name,
                                "type": ref_obj.kind,
                                "edge_phrase_id": edge_phrase_id,
                                "edge_phrase": edge_phrase,
                            }],
                            "other_paths_count": 0,
                            "blocking": blocking,
                            "allowed_actions": ["add_from_donor", "map_to_target", "drop_added_object"],
                        })

                    # Transitive walk: continue exploring upstream dependencies
                    if ref_key not in seen:
                        seen.add(ref_key)
                        queue.append(ref_obj)

        return needs

    def _run_sibling_reports_walk(self) -> list[dict[str, Any]]:
        """AC5: Reports bound to target model join as report-only graphs; carry 'not changed by this plan'."""
        sibling_items: list[dict[str, Any]] = []
        deleted_model_keys = {
            op.get("row_key") or op.get("target")
            for op in self.plan.get("operations", [])
            if op.get("op") in {"DELETE", "DELETE_OBJECT", "DELETE_REPORT_MEASURE"}
        }

        if not deleted_model_keys:
            return []

        for sibling_id, sib_objects in self.sibling_report_objects.items():
            visuals = [obj for obj in sib_objects if obj.kind == "visual"]
            for vis in visuals:
                referenced_keys = {f"{loc.kind}:{loc.entity}/{loc.property}" for loc in field_locations(vis)}
                if isinstance(vis.extra.get("fields"), list):
                    referenced_keys.update(str(f) for f in vis.extra["fields"])
                for field_key in sorted(referenced_keys):
                    if field_key in deleted_model_keys or any(k.endswith(f"/{field_key.split('/')[-1]}") for k in deleted_model_keys):
                        item_id = deterministic_item_id("breaks", vis.source_key, field_key, "sibling_report_impact")
                        reason_id = "not_changed_by_this_plan"
                        _, reason_text = _get_phrase(reason_id, "Not changed by this plan")
                        edge_phrase_id, edge_phrase = _get_phrase("uses", "uses")

                        sibling_items.append({
                            "id": item_id,
                            "direction": "breaks",
                            "cause": field_key,
                            "impacted_object": {
                                "source_id": sibling_id,
                                "object_id": vis.source_key,
                                "object_type": "visual",
                                "name": vis.name,
                                "domain": "report",
                            },
                            "severity": "not_changed_by_this_plan",
                            "certainty": "certain",
                            "reason_id": reason_id,
                            "reason_text": reason_text,
                            "path": [{
                                "object_id": vis.source_key,
                                "name": vis.name,
                                "type": "visual",
                                "edge_phrase_id": edge_phrase_id,
                                "edge_phrase": edge_phrase,
                            }],
                            "other_paths_count": 0,
                            "blocking": False,  # Sibling reports never block apply
                            "allowed_actions": [],
                        })

        return sibling_items
