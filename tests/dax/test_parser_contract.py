"""Phase 2 parser contract tests backed by the reusable golden corpus."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.dax._helpers import ast_functions, ast_kinds, locations, mapping, parse_ast, walk
from tests.fixtures.dax_golden import GOLDEN_DAX


class DaxParserContractTests(unittest.TestCase):
    def test_antlr_grammar_assets_exist_and_cover_required_surface(self):
        grammar = Path(__file__).parents[2] / "backend" / "dax" / "grammar"
        lexer = grammar / "DAXLexer.g4"
        parser = grammar / "DAXParser.g4"
        self.assertTrue(lexer.exists(), lexer)
        self.assertTrue(parser.exists(), parser)
        source = f"{lexer.read_text(encoding='utf-8')}\n{parser.read_text(encoding='utf-8')}".upper()
        # Function names intentionally remain identifiers: this lets the
        # grammar accept new DAX functions without regenerating the lexer.
        for token in ("VAR", "RETURN", "FUNCTIONCALL", "QUALIFIEDREFERENCE", "TABLECONSTRUCTOR"):
            self.assertIn(token, source)

    def test_every_non_error_golden_case_has_a_source_preserving_ast(self):
        for case in GOLDEN_DAX:
            if case.error and case.error.get("kind") is None:
                continue
            with self.subTest(case=case.name):
                ast = parse_ast(case.dax)
                self.assertIsNotNone(ast)
                self.assertTrue(mapping(ast), case.name)
                self.assertTrue(locations(ast), f"no source span: {case.name}")

    def test_ast_contains_expected_structural_characteristics(self):
        aliases = {
            "binary": {"binary", "binary_operator"},
            "unary": {"unary", "unary_operator"},
            "literal": {"literal"},
            "function_call": {"function_call", "call", "function"},
            "column_reference": {"column_reference", "column_ref", "reference"},
            "measure_reference": {"measure_reference", "measure_ref", "reference"},
            "table_reference": {"table_reference", "table_ref", "reference"},
            "variable_reference": {"variable_reference", "variable_ref", "identifier"},
            "var": {"var", "var_block", "var_declaration"},
            "return": {"return", "var_block"},
            "if": {"if", "function_call", "call"},
            "switch": {"switch", "function_call", "call"},
            "calculate": {"calculate", "function_call", "call"},
            "filter": {"filter", "function_call", "call"},
            "table_reference": {"table_reference", "table_ref", "reference"},
        }
        for case in GOLDEN_DAX:
            if case.error:
                continue
            with self.subTest(case=case.name):
                ast = parse_ast(case.dax)
                kinds = ast_kinds(ast)
                functions = ast_functions(ast)
                for expected in case.ast.get("contains", ()):
                    if expected.upper() in {name.upper() for name in functions}:
                        continue
                    accepted = aliases.get(expected, {expected})
                    self.assertTrue(kinds & accepted, f"{case.name}: missing {expected}; got {sorted(kinds)} / {sorted(functions)}")

    def test_operator_precedence_is_a_nested_tree(self):
        case = next(item for item in GOLDEN_DAX if item.name == "literals_and_operator_precedence")
        ast = parse_ast(case.dax)
        nodes = list(walk(ast))
        operators = [str(item.get("operator", "")).upper() for item in nodes if item.get("operator")]
        self.assertIn("*", operators)
        self.assertIn("+", operators)
        self.assertIn("=", operators)
        self.assertIn("&&", operators)
        # A flat token list cannot preserve precedence.  The expression must
        # contain at least one operator node below another operator node.
        nested = False
        for item in nodes:
            children = item.get("children", ())
            if not isinstance(children, (list, tuple)):
                children = [children]
            if str(item.get("kind", "")).casefold() in {"binary", "binary_operator", "unary", "unary_operator"}:
                if any(str(mapping(child).get("kind", "")).casefold() in {"binary", "binary_operator", "unary", "unary_operator"} for child in children if child is not None):
                    nested = True
                    break
        self.assertTrue(nested, "operator precedence was flattened")

    def test_references_keep_table_column_measure_kinds_and_escaped_names(self):
        ast = parse_ast(next(item for item in GOLDEN_DAX if item.name == "quoted_tables_and_escaped_identifiers").dax)
        refs = [item for item in walk(ast) if item.get("kind") == "reference"]
        self.assertGreaterEqual(len(refs), 2)
        values = {(str(item.get("table")), str(item.get("column"))) for item in refs}
        self.assertIn(("Sales Table", "Net Amount"), values)
        self.assertIn(("O'Brien", "Value"), values)

    def test_parser_does_not_emit_semantic_inference(self):
        for case in GOLDEN_DAX:
            if case.error:
                continue
            with self.subTest(case=case.name):
                serialized = list(walk(parse_ast(case.dax)))
                for node in serialized:
                    self.assertNotIn("business_concept", node)
                    self.assertNotIn("semantic_candidates", node)
                    self.assertNotIn("confidence", node)

    def test_same_expression_has_deterministic_ast(self):
        for case in GOLDEN_DAX:
            if case.error:
                continue
            with self.subTest(case=case.name):
                first = mapping(parse_ast(case.dax))
                second = mapping(parse_ast(case.dax))
                self.assertEqual(
                    json.dumps(first, sort_keys=True, default=str),
                    json.dumps(second, sort_keys=True, default=str),
                )

    def test_syntax_error_reports_line_and_column(self):
        case = next(item for item in GOLDEN_DAX if item.name == "syntax_error_location")
        from backend.dax.parser import DaxSyntaxError, parse_dax

        with self.assertRaises(DaxSyntaxError) as context:
            parse_dax(case.dax)
        error = context.exception
        data = mapping(error)
        line = getattr(error, "line", None) or data.get("line") or data.get("start_line")
        column = getattr(error, "column", None) or data.get("column") or data.get("start_column")
        self.assertEqual(int(line), case.error["line"])
        self.assertEqual(int(column), case.error["column"])


if __name__ == "__main__":
    unittest.main()
