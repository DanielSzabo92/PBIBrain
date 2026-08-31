"""Guards against grammar edits without regenerated ANTLR Python sources."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from backend.dax.generated.DAXLexer import DAXLexer
from backend.dax.generated.DAXParser import DAXParser
from backend.dax.parser import parse_dax
from backend.dax.visitors import iter_references


ROOT = Path(__file__).parents[2]
GRAMMAR = ROOT / "backend" / "dax" / "grammar"


def _lexer_rules() -> list[str]:
    source = (GRAMMAR / "DAXLexer.g4").read_text(encoding="utf-8")
    return re.findall(r"(?m)^\s*(?!fragment\b)([A-Z][A-Z0-9_]*)\s*:", source)


def _parser_rules() -> list[str]:
    source = (GRAMMAR / "DAXParser.g4").read_text(encoding="utf-8")
    return re.findall(r"(?m)^\s*([a-z][A-Za-z0-9_]*)\s*(?::|\n\s*:)", source)


class AntlrGenerationContractTests(unittest.TestCase):
    def test_every_grammar_token_exists_in_both_generated_modules(self):
        lexer_names = set(DAXLexer.symbolicNames)
        parser_names = set(DAXParser.symbolicNames)
        lexer_names.discard(None)
        parser_names.discard(None)
        for name in _lexer_rules():
            with self.subTest(token=name):
                self.assertIn(name, lexer_names)
                self.assertIn(name, parser_names)
                self.assertTrue(hasattr(DAXLexer, name), name)
                self.assertTrue(hasattr(DAXParser, name), name)
                self.assertEqual(getattr(DAXLexer, name), getattr(DAXParser, name), name)

    def test_every_grammar_rule_exists_in_generated_parser(self):
        generated = set(DAXParser.ruleNames)
        for name in _parser_rules():
            with self.subTest(rule=name):
                self.assertIn(name, generated)
                self.assertTrue(hasattr(DAXParser, name), name)

    def test_generated_parser_facade_exposes_all_rules_used_by_ast_builder(self):
        for name in _parser_rules():
            context_name = f"{name[0].upper()}{name[1:]}Context"
            with self.subTest(rule=name):
                self.assertTrue(hasattr(DAXParser, context_name), context_name)

    def test_new_power_and_concat_operators_parse_from_regenerated_grammar(self):
        power = parse_dax("2 ^ 3 ^ 2").root
        self.assertEqual(power.kind, "binary_operator")
        self.assertEqual(power.operator, "^")
        self.assertEqual(power.left.operator, "^")

        concat = parse_dax('"a" & "b"').root
        self.assertEqual(concat.kind, "binary_operator")
        self.assertEqual(concat.operator, "&")

    def test_datetime_literal_parses_when_grammar_declares_it(self):
        if "DATETIME_LITERAL" not in _lexer_rules():
            self.skipTest("grammar does not declare DATETIME_LITERAL")
        literal = parse_dax('dt"2024-01-02T03:04:05"').root
        self.assertEqual(literal.kind, "literal")
        self.assertEqual(literal.literal_type, "DATETIME")
        self.assertEqual(literal.value, "2024-01-02T03:04:05")

    def test_bare_table_tuple_and_in_constructs_parse(self):
        bare_table = parse_dax("FILTER(Sales, Sales[Amount] > 0)").root
        references = list(iter_references(bare_table))
        self.assertIn(("TABLE", "Sales", None), {(info.kind, info.name, info.table) for _, info in references})
        self.assertIn(("COLUMN", "Amount", "Sales"), {(info.kind, info.name, info.table) for _, info in references})

        membership = parse_dax("('Date'[Year], 'Date'[Month]) IN {(2024, 1), (2025, 2)}").root
        self.assertEqual(membership.kind, "binary_operator")
        self.assertEqual(membership.operator, "IN")
        self.assertEqual(membership.left.kind, "tuple")
        self.assertEqual(membership.right.kind, "table_constructor")
        self.assertEqual(len(membership.left.values), 2)
        self.assertEqual(len(membership.right.values), 2)


if __name__ == "__main__":
    unittest.main()
