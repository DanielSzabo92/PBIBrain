"""Phase 2 analyzer contract tests.

These tests feed canonical ``Node`` values to the analyzer.  No Power BI
adapter structures are used here: resolution and graph facts are tested at
the Brain boundary.
"""

from __future__ import annotations

import json
import unittest

from backend.dax.analyzer import DaxAnalyzer, analyze_dax, analyze_nodes
from backend.dax.parser import parse_dax
from backend.graph.schema import Node

from tests.dax._helpers import (
    all_strings,
    analysis_edges,
    item_mapping,
    item_target,
    item_type,
    mapping,
    result_mapping,
)
from tests.fixtures.dax_golden import CANONICAL_SYMBOLS, GOLDEN_BY_NAME, GOLDEN_DAX, MODEL_ID


SOURCE_ID = f"{MODEL_ID}/measure:dax-fixture-source"


def _node(node_id: str, node_type: str, name: str, *, properties: dict | None = None) -> Node:
    return Node(
        id=node_id,
        type=node_type,
        name=name,
        model_id=MODEL_ID,
        source_id=node_id.rsplit(":", 1)[-1],
        properties=properties or {},
    )


def canonical_nodes(*, source_expression: str | None = None, ambiguous_sales: bool = False) -> list[Node]:
    """Make a compact canonical symbol table for the golden DAX cases."""

    nodes = [
        _node(MODEL_ID, "MODEL", "DAX Fixture Model"),
        *(
            _node(table_id, "TABLE", table_name)
            for table_name, table_id in CANONICAL_SYMBOLS["tables"].items()
        ),
    ]
    for (table_name, column_name), column_id in CANONICAL_SYMBOLS["columns"].items():
        if column_id is None:
            continue
        table_id = CANONICAL_SYMBOLS["tables"][table_name]
        nodes.append(
            _node(
                column_id,
                "COLUMN",
                column_name,
                properties={"table_id": table_id},
            )
        )
    for measure_name, measure_id in CANONICAL_SYMBOLS["measures"].items():
        if measure_id is None:
            continue
        table_id = CANONICAL_SYMBOLS["tables"]["Sales"]
        nodes.append(
            _node(
                measure_id,
                "MEASURE",
                measure_name,
                properties={"table_id": table_id},
            )
        )
    nodes.extend(
        [
            _node(
                f"{MODEL_ID}/relationship:ship-date",
                "RELATIONSHIP",
                "Ship Date",
                properties={
                    "from_column_id": CANONICAL_SYMBOLS["columns"][("Sales", "ShipDate")],
                    "to_column_id": CANONICAL_SYMBOLS["columns"][("Date", "Date")],
                },
            ),
            _node(
                f"{MODEL_ID}/relationship:customer",
                "RELATIONSHIP",
                "Customer",
                properties={
                    "from_column_id": CANONICAL_SYMBOLS["columns"][("Sales", "CustomerId")],
                    "to_column_id": CANONICAL_SYMBOLS["columns"][("Customer", "Id")],
                },
            ),
            _node(
                f"{MODEL_ID}/udf:format-amount",
                "USER_DEFINED_FUNCTION",
                "FormatAmount",
            ),
        ]
    )
    if ambiguous_sales:
        nodes.append(_node(f"{MODEL_ID}/table:other/measure:sales", "MEASURE", "Sales"))
        nodes.append(_node(f"{MODEL_ID}/table:third/measure:sales", "MEASURE", "Sales"))
    if source_expression is not None:
        nodes.append(_node(SOURCE_ID, "MEASURE", "Fixture Expression", properties={"expression": source_expression}))
    return nodes


def _case(name: str):
    return GOLDEN_BY_NAME[name]


def _target_names(nodes: list[Node]) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in nodes:
        result[node.id] = node.name
    return result


class DaxAnalyzerContractTests(unittest.TestCase):
    def test_references_and_dependencies_resolve_to_canonical_ids(self):
        cases = [case for case in GOLDEN_DAX if case.references or case.dependencies]
        for case in cases:
            if case.error and case.error.get("kind") in {"unresolved_reference", "ambiguous_reference"}:
                continue
            with self.subTest(case=case.name):
                source = _node(SOURCE_ID, "MEASURE", "Fixture Expression")
                nodes = canonical_nodes()
                nodes.append(source)
                analysis = analyze_dax(source, case.dax, nodes=nodes)
                edges = analysis_edges(analysis)
                targets = _target_names(canonical_nodes())
                for reference in case.references:
                    expected_type = "DEPENDS_ON" if reference["kind"] == "measure" else "REFERENCES"
                    name = reference["name"]
                    matching = [
                        edge
                        for edge in edges
                        if item_type(edge) == expected_type
                        and targets.get(item_target(edge)) == name
                    ]
                    self.assertTrue(matching, f"{case.name}: missing {expected_type} for {name}")
                for dependency in case.dependencies:
                    matching = [
                        edge
                        for edge in edges
                        if item_type(edge) == "DEPENDS_ON"
                        and targets.get(item_target(edge)) == dependency
                    ]
                    self.assertTrue(matching, f"{case.name}: missing DEPENDS_ON for {dependency}")

    def test_every_fact_edge_has_dax_provenance_and_ast_location(self):
        for case in GOLDEN_DAX:
            if case.error:
                continue
            with self.subTest(case=case.name):
                source = _node(SOURCE_ID, "MEASURE", "Fixture Expression")
                nodes = canonical_nodes()
                nodes.append(source)
                analysis = analyze_dax(source, case.dax, nodes=nodes)
                for edge in analysis_edges(analysis):
                    data = item_mapping(edge)
                    self.assertEqual(str(data.get("status", "")).lower(), "factual")
                    self.assertEqual(str(data.get("evidence_class", "")).upper(), "FACT")
                    self.assertIn(str(data.get("source", "")), {"dax_analysis", "dax_ast"})
                    evidence = data.get("evidence") or []
                    self.assertTrue(evidence, f"{case.name}: edge has no evidence")
                    evidence_values = evidence if isinstance(evidence, list) else [evidence]
                    for item in evidence_values:
                        evidence_data = item_mapping(item)
                        self.assertTrue(evidence_data.get("extractor"), item)
                        self.assertTrue(evidence_data.get("ast_location"), item)

    def test_behavior_annotations_cover_selector_filter_relationship_and_udf_calls(self):
        for case in GOLDEN_DAX:
            if not case.behaviors:
                continue
            with self.subTest(case=case.name):
                source = _node(SOURCE_ID, "MEASURE", "Fixture Expression")
                result = analyze_dax(source, case.dax, nodes=canonical_nodes())
                data = result_mapping(result)
                behaviors = data.get("behaviors", [])
                text = " ".join(all_strings(behaviors)).upper()
                for expected in case.behaviors:
                    self.assertIn(expected.upper(), text, f"{case.name}: missing behavior {expected}")

    def test_filter_and_relationship_constructs_emit_targeted_fact_edges(self):
        source = _node(SOURCE_ID, "MEASURE", "Fixture Expression")
        nodes = canonical_nodes()
        nodes.append(source)
        filter_analysis = analyze_dax(source, _case("filter_context_functions").dax, nodes=nodes)
        filter_edges = {item_type(edge): edge for edge in analysis_edges(filter_analysis)}
        self.assertIn("MODIFIES_FILTER", filter_edges)

        relationship_analysis = analyze_dax(source, _case("relationship_modifiers").dax, nodes=nodes)
        relationship_types = {item_type(edge) for edge in analysis_edges(relationship_analysis)}
        self.assertIn("ACTIVATES_RELATIONSHIP", relationship_types)
        self.assertIn("MODIFIES_RELATIONSHIP", relationship_types)
        for edge in analysis_edges(relationship_analysis):
            if item_type(edge) not in {"ACTIVATES_RELATIONSHIP", "MODIFIES_RELATIONSHIP"}:
                continue
            self.assertTrue(item_mapping(edge).get("evidence"))

    def test_unresolved_and_ambiguous_references_are_diagnostics_not_guesses(self):
        unresolved = _case("unresolved_references")
        ambiguous = _case("ambiguous_measure_reference")
        unresolved_analysis = analyze_dax(
            _node(SOURCE_ID, "MEASURE", "Fixture Expression"),
            unresolved.dax,
            nodes=canonical_nodes() + [_node(SOURCE_ID, "MEASURE", "Fixture Expression")],
        )
        ambiguous_analysis = analyze_dax(
            _node(SOURCE_ID, "MEASURE", "Fixture Expression"),
            ambiguous.dax,
            nodes=canonical_nodes(ambiguous_sales=True) + [_node(SOURCE_ID, "MEASURE", "Fixture Expression")],
        )
        unresolved_codes = {item_mapping(item).get("code") for item in unresolved_analysis.diagnostics}
        ambiguous_codes = {item_mapping(item).get("code") for item in ambiguous_analysis.diagnostics}
        self.assertIn("unresolved_reference", unresolved_codes)
        self.assertIn("ambiguous_reference", ambiguous_codes)
        for result in (unresolved_analysis, ambiguous_analysis):
            for edge in analysis_edges(result):
                self.assertNotEqual(item_target(edge), "None")

    def test_preparsed_ast_is_accepted_without_reparsing(self):
        case = _case("measure_and_column_references")
        ast = parse_dax(case.dax).root

        class FailingParser:
            def __call__(self, expression):
                raise AssertionError("preparsed AST was reparsed")

        source = _node(SOURCE_ID, "MEASURE", "Fixture Expression")
        result = DaxAnalyzer(canonical_nodes() + [source], parser=FailingParser()).analyze_object(
            source,
            case.dax,
            ast=ast,
        )
        self.assertTrue(analysis_edges(result))

    def test_duplicate_expression_is_parsed_once(self):
        case = _case("measure_and_column_references")
        calls = []

        def parser(expression):
            calls.append(expression)
            return parse_dax(expression)

        first = _node(f"{MODEL_ID}/measure:first", "MEASURE", "First", properties={"expression": case.dax})
        second = _node(f"{MODEL_ID}/measure:second", "MEASURE", "Second", properties={"expression": case.dax})
        nodes = canonical_nodes()
        nodes.extend((first, second))
        batch = DaxAnalyzer(nodes, parser=parser).analyze((first, second))
        self.assertEqual(calls, [case.dax])
        self.assertEqual(set(batch.analyses), {first.id, second.id})

    def test_analysis_is_deterministic_and_phase2_has_no_semantic_candidates(self):
        case = _case("filter_context_functions")
        first = analyze_nodes(canonical_nodes(source_expression=case.dax))
        second = analyze_nodes(canonical_nodes(source_expression=case.dax))
        self.assertEqual(
            json.dumps(first.to_dict(), sort_keys=True, default=str),
            json.dumps(second.to_dict(), sort_keys=True, default=str),
        )
        for result in (first.to_dict(), second.to_dict()):
            self.assertNotIn("semantic_candidates", result)
            self.assertNotIn("business_concept", json.dumps(result, sort_keys=True).casefold())


if __name__ == "__main__":
    unittest.main()
