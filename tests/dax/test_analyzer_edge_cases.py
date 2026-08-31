"""Regression tests for Phase 2 resolver and DAX syntax edge cases."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.dax.analyzer import DaxAnalyzer, analyze_dax
from backend.dax.parser import parse_dax
from backend.graph.repository import GraphRepository
from backend.scanner.pipeline import Scanner

from tests.dax._helpers import ast_kinds, item_target, item_type, walk
from tests.fixtures.dax_edge_cases import (
    BARE_TABLE_FILTER_DAX,
    CURRENCY_VALUE,
    DATE_NAME,
    FIELD_PARAMETER_DAX,
    MEASURE_A,
    MEASURE_PROFIT,
    MEASURE_X,
    MODEL_A,
    MODEL_B,
    MODEL_B_MEASURE_X,
    PRODUCT_NAME,
    SALES_AMOUNT,
    SALES_CURRENCY,
    SALES_TABLE,
    TREATAS_DAX,
    base_nodes,
    dynamic_format_model_source,
    node,
)


def _source(expression: str, *, model_id: str = MODEL_A):
    table_id = f"{model_id}/table:sales"
    source_id = f"{model_id}/measure:source"
    return node(
        source_id,
        "MEASURE",
        "Source",
        model_id=model_id,
        properties={"expression": expression, "table_id": table_id},
    )


def _edge_targets(analysis, edge_type: str) -> set[str]:
    return {
        item_target(edge)
        for edge in analysis.edges
        if item_type(edge) == edge_type
    }


class DaxResolverEdgeCaseTests(unittest.TestCase):
    def test_measure_resolution_never_crosses_model_boundary(self):
        source = _source("[X]")
        nodes = [item for item in base_nodes() if item.id != MEASURE_X] + [
            source,
            node(
                MODEL_B_MEASURE_X,
                "MEASURE",
                "X",
                model_id=MODEL_B,
                properties={"table_id": f"{MODEL_B}/table:other"},
            ),
        ]

        analysis = analyze_dax(source, "[X]", nodes=nodes)

        self.assertIn("unresolved_reference", {item["code"] for item in analysis.diagnostics})
        self.assertNotIn(MODEL_B_MEASURE_X, _edge_targets(analysis, "DEPENDS_ON"))

    def test_missing_qualified_column_does_not_fall_back_to_unqualified_name(self):
        source = _source("SUM('Missing'[Amount])")
        nodes = base_nodes() + [source]

        analysis = analyze_dax(source, "SUM('Missing'[Amount])", nodes=nodes)

        self.assertIn("unresolved_reference", {item["code"] for item in analysis.diagnostics})
        self.assertNotIn(SALES_AMOUNT, _edge_targets(analysis, "REFERENCES"))

    def test_bare_table_references_are_preserved_in_filter_and_all(self):
        source = _source(BARE_TABLE_FILTER_DAX)
        nodes = base_nodes() + [source]

        analysis = analyze_dax(source, BARE_TABLE_FILTER_DAX, nodes=nodes)

        self.assertFalse(analysis.diagnostics)
        self.assertIn(SALES_TABLE, _edge_targets(analysis, "REFERENCES"))
        self.assertIn(SALES_TABLE, _edge_targets(analysis, "MODIFIES_FILTER"))
        behavior_names = {
            str(item.get("function", "")).upper()
            for item in analysis.behaviors
        }
        self.assertTrue({"FILTER", "ALL"} <= behavior_names)

    def test_exponent_operator_is_parsed_and_measure_dependency_survives(self):
        source = _source("[A]^2")
        nodes = base_nodes() + [source]

        parsed = parse_dax("[A]^2")
        operators = {
            str(item.get("operator"))
            for item in walk(parsed.root)
            if item.get("operator") is not None
        }
        self.assertIn("^", operators)

        analysis = analyze_dax(source, "[A]^2", nodes=nodes)
        self.assertFalse(analysis.diagnostics)
        self.assertIn(MEASURE_A, _edge_targets(analysis, "DEPENDS_ON"))

    def test_dax_operator_precedence_matches_official_order(self):
        parsed = parse_dax("1 & 2 + 3")
        root = parsed.root.to_dict()
        self.assertEqual(root.get("operator"), "&")
        self.assertEqual(root["left"].get("value"), 1)
        self.assertEqual(root["right"].get("operator"), "+")

        signed = parse_dax("-2^2").root.to_dict()
        self.assertEqual(signed.get("operator"), "-")
        self.assertEqual(signed["operand"].get("operator"), "^")

    def test_field_parameter_rows_parse_as_nested_source_preserving_values(self):
        parsed = parse_dax(FIELD_PARAMETER_DAX)
        data = json.dumps(parsed.root.to_dict(), sort_keys=True)
        kinds = ast_kinds(parsed.root)
        self.assertIn("table_constructor", kinds)
        self.assertIn('"Product"', data)
        self.assertIn('"Date"', data)
        self.assertIn("NAMEOF", data)
        row_texts = {
            str(item.get("text", "")).strip()
            for item in walk(parsed.root)
            if "," in str(item.get("text", ""))
            and str(item.get("text", "")).strip().startswith("(")
        }
        self.assertGreaterEqual(len(row_texts), 2)

        source = _source(FIELD_PARAMETER_DAX)
        analysis = analyze_dax(source, FIELD_PARAMETER_DAX, nodes=base_nodes() + [source])
        self.assertFalse(analysis.diagnostics)
        self.assertTrue({DATE_NAME, PRODUCT_NAME} <= _edge_targets(analysis, "REFERENCES"))

    def test_bracketed_measure_reference_is_not_shadowed_by_var_name(self):
        expression = "VAR x = 1 RETURN [x] + x"
        source = _source(expression)
        target = node(
            MEASURE_X,
            "MEASURE",
            "x",
            properties={"table_id": SALES_TABLE},
        )
        nodes = [item for item in base_nodes() if item.id != MEASURE_X] + [target, source]

        analysis = analyze_dax(source, expression, nodes=nodes)

        self.assertFalse(analysis.diagnostics)
        self.assertIn(MEASURE_X, _edge_targets(analysis, "DEPENDS_ON"))
        bracketed = [
            item
            for item in analysis.references
            if str(item.get("name", "")).casefold() == "x"
            and item.get("target") == MEASURE_X
        ]
        self.assertTrue(bracketed)
        self.assertNotEqual(bracketed[0].get("scope"), "variable")

    def test_treatas_reads_source_but_modifies_only_target_column(self):
        source = _source(TREATAS_DAX)
        analysis = analyze_dax(source, TREATAS_DAX, nodes=base_nodes() + [source])

        self.assertFalse(analysis.diagnostics)
        self.assertIn(CURRENCY_VALUE, _edge_targets(analysis, "REFERENCES"))
        self.assertIn(SALES_CURRENCY, _edge_targets(analysis, "REFERENCES"))
        self.assertEqual(_edge_targets(analysis, "MODIFIES_FILTER"), {SALES_CURRENCY})
        treatas = [
            item
            for item in analysis.behaviors
            if str(item.get("function", "")).upper() == "TREATAS"
        ]
        self.assertEqual(len(treatas), 1)
        self.assertEqual(treatas[0].get("target_ids"), [SALES_CURRENCY])

    def test_measure_format_expression_is_parsed_with_ast_and_evidence(self):
        source = _source("[X]")
        source.properties["format_expression"] = "SELECTEDMEASUREFORMATSTRING()"
        analyzer = DaxAnalyzer(base_nodes() + [source])
        analysis = analyzer.analyze_object(source)

        self.assertIn("format_expression", source.properties.get("dax_asts", {}))
        format_ast = source.properties["dax_asts"]["format_expression"]
        self.assertIn("SELECTEDMEASUREFORMATSTRING", json.dumps(format_ast))
        self.assertTrue(
            any(
                str(item.get("function", "")).upper() == "SELECTEDMEASUREFORMATSTRING"
                for item in analysis.behaviors
            )
        )
        self.assertTrue(analysis.evidence)

    def test_measure_format_string_expression_is_canonicalized_and_analyzed(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = GraphRepository(Path(directory) / "brain.json", use_native=False)
            graph = Scanner(repository, identity_path=Path(directory) / "identity.json").scan(
                dynamic_format_model_source()
            )
            measure = next(
                item
                for item in graph.nodes
                if item.type == "MEASURE" and item.source_id == "measure-sales"
            )
            self.assertEqual(
                measure.properties.get("format_expression"),
                "SELECTEDMEASUREFORMATSTRING()",
            )
            self.assertIn("format_expression", measure.properties.get("dax_asts", {}))
            self.assertTrue(
                any(
                    str(item.get("function", "")).upper()
                    == "SELECTEDMEASUREFORMATSTRING"
                    for item in measure.properties.get("dax_behaviors", [])
                )
            )
            self.assertTrue(measure.properties.get("dax_evidence"))
            repository.close()

    def test_table_qualified_measure_resolves_as_measure_dependency(self):
        source = _source("Sales[Profit]")
        nodes = base_nodes() + [source]

        analysis = analyze_dax(source, "Sales[Profit]", nodes=nodes)

        self.assertFalse(analysis.diagnostics)
        self.assertIn(MEASURE_PROFIT, _edge_targets(analysis, "DEPENDS_ON"))
        self.assertNotIn(MEASURE_PROFIT, _edge_targets(analysis, "REFERENCES"))

    def test_datetime_literal_preserves_source_and_location(self):
        literal = 'dt"2020-12-15T12:30:59"'
        parsed = parse_dax(literal)
        candidates = [
            item
            for item in walk(parsed.root)
            if item.get("kind") == "literal"
        ]
        self.assertTrue(candidates)
        value = next(item for item in candidates if item.get("text") == literal)
        self.assertIn(str(value.get("literal_type", "")).upper(), {"DATE", "DATETIME"})
        location = value["location"]
        self.assertEqual(literal, literal[location["start_offset"] : location["end_offset"]])


if __name__ == "__main__":
    unittest.main()
