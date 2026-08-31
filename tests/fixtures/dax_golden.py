"""Reusable Phase 2 DAX corpus.

Cases describe observable parser/analyzer behaviour, not a parser-specific AST
class.  Production tests can reuse the same corpus as the grammar grows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MODEL_ID = "model:dax-fixture"
SALES_TABLE = "model:dax-fixture/table:sales"
DATE_TABLE = "model:dax-fixture/table:date"
CURRENCY_TABLE = "model:dax-fixture/table:currency"
PRODUCT_TABLE = "model:dax-fixture/table:product"
CUSTOMER_TABLE = "model:dax-fixture/table:customer"
SALES_TABLE_QUOTED = "model:dax-fixture/table:sales-table"
OBRIEN_TABLE = "model:dax-fixture/table:o-brien"


@dataclass(frozen=True)
class DaxGoldenCase:
    name: str
    dax: str
    ast: dict[str, Any]
    references: tuple[dict[str, Any], ...] = ()
    dependencies: tuple[str, ...] = ()
    behaviors: tuple[str, ...] = ()
    semantic_candidates: tuple[dict[str, Any], ...] = ()
    error: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly fixture for tools outside unittest."""

        return {
            "name": self.name,
            "dax": self.dax,
            "ast": self.ast,
            "references": list(self.references),
            "dependencies": list(self.dependencies),
            "behaviors": list(self.behaviors),
            "semantic_candidates": list(self.semantic_candidates),
            "error": self.error,
        }


def _column(table: str, column: str) -> dict[str, Any]:
    return {"kind": "column", "table": table, "name": column}


def _measure(name: str) -> dict[str, Any]:
    return {"kind": "measure", "name": name}


GOLDEN_DAX: tuple[DaxGoldenCase, ...] = (
    DaxGoldenCase(
        name="literals_and_operator_precedence",
        dax="1 + 2 * 3 = 7 && NOT(FALSE)",
        ast={"root_kind": "expression", "contains": ["binary", "unary", "literal"], "preserves_precedence": True},
    ),
    DaxGoldenCase(
        name="quoted_tables_and_escaped_identifiers",
        dax="'Sales Table'[Net Amount] + 'O''Brien'[Value]",
        ast={"root_kind": "expression", "contains": ["column_reference"], "preserves_quoted_identifiers": True},
        references=(
            _column("Sales Table", "Net Amount"),
            _column("O'Brien", "Value"),
        ),
    ),
    DaxGoldenCase(
        name="measure_and_column_references",
        dax="[Base Sales] + SUM('Sales'[Amount])",
        ast={"root_kind": "expression", "contains": ["measure_reference", "function_call", "column_reference"]},
        references=(_column("Sales", "Amount"), _measure("Base Sales")),
        dependencies=("Base Sales",),
    ),
    DaxGoldenCase(
        name="var_return",
        dax="VAR Amount = SUM('Sales'[Amount]) VAR Rate = 1.2 RETURN Amount * Rate",
        ast={"root_kind": "expression", "contains": ["var", "return", "variable_reference", "function_call"]},
        references=(_column("Sales", "Amount"),),
    ),
    DaxGoldenCase(
        name="nested_if_and_switch",
        dax='IF([Base Sales] > 0, SWITCH(TRUE(), [Base Sales] > 1000, "Large", "Small"), "None")',
        ast={"root_kind": "expression", "contains": ["function_call", "if", "switch", "measure_reference"]},
        dependencies=("Base Sales",),
    ),
    DaxGoldenCase(
        name="selectedvalue_with_default",
        dax='SELECTEDVALUE(\'Currency Selector\'[Currency], "LOCAL")',
        ast={"root_kind": "expression", "contains": ["function_call", "column_reference", "literal"]},
        references=(_column("Currency Selector", "Currency"),),
        behaviors=("SELECTEDVALUE",),
    ),
    DaxGoldenCase(
        name="value_filter_predicates",
        dax='IF(HASONEVALUE(\'Date\'[Year]), VALUES(\'Date\'[Year]), "All") & IF(ISFILTERED(\'Product\'[Category]), "Filtered", "All")',
        ast={"root_kind": "expression", "contains": ["function_call", "if", "column_reference"]},
        references=(_column("Date", "Year"), _column("Product", "Category")),
        behaviors=("VALUES", "HASONEVALUE", "ISFILTERED"),
    ),
    DaxGoldenCase(
        name="filter_context_functions",
        dax='CALCULATE([Net Sales], FILTER(ALL(\'Date\'), \'Date\'[Year] >= 2020), TREATAS(VALUES(\'Currency\'[Currency]), \'Sales\'[Currency]), REMOVEFILTERS(\'Product\'), ALLSELECTED(\'Date\'), KEEPFILTERS(\'Product\'[Category] = "A"))',
        ast={"root_kind": "expression", "contains": ["calculate", "filter", "function_call", "column_reference", "table_reference"]},
        references=(
            _column("Date", "Year"),
            _column("Currency", "Currency"),
            _column("Sales", "Currency"),
            _column("Product", "Category"),
        ),
        dependencies=("Net Sales",),
        behaviors=("CALCULATE", "FILTER", "TREATAS", "REMOVEFILTERS", "ALL", "ALLSELECTED", "KEEPFILTERS"),
    ),
    DaxGoldenCase(
        name="relationship_modifiers",
        dax="CALCULATE([Net Sales], USERELATIONSHIP('Sales'[ShipDate], 'Date'[Date]), CROSSFILTER('Sales'[CustomerId], 'Customer'[Id], BOTH))",
        ast={"root_kind": "expression", "contains": ["calculate", "function_call", "column_reference"]},
        references=(
            _column("Sales", "ShipDate"),
            _column("Date", "Date"),
            _column("Sales", "CustomerId"),
            _column("Customer", "Id"),
        ),
        dependencies=("Net Sales",),
        behaviors=("USERELATIONSHIP", "CROSSFILTER"),
    ),
    DaxGoldenCase(
        name="nested_measure_chain",
        dax="[Gross Margin] / [Net Sales]",
        ast={"root_kind": "expression", "contains": ["measure_reference", "binary"]},
        dependencies=("Gross Margin", "Net Sales"),
    ),
    DaxGoldenCase(
        name="udf_and_generic_calls",
        dax='FormatAmount(COALESCE([Net Sales], 0), "#,##0")',
        ast={"root_kind": "expression", "contains": ["function_call", "measure_reference", "literal"]},
        dependencies=("Net Sales", "FormatAmount"),
        behaviors=("UDF_CALL",),
    ),
    DaxGoldenCase(
        name="dynamic_format_expression",
        dax='SWITCH(SELECTEDVALUE(\'Currency Selector\'[Currency], "LOCAL"), "USD", "$#,##0", SELECTEDMEASUREFORMATSTRING())',
        ast={"root_kind": "expression", "contains": ["switch", "function_call", "column_reference", "literal"]},
        references=(_column("Currency Selector", "Currency"),),
        behaviors=("FORMAT_CONSTRUCT", "SELECTEDVALUE"),
    ),
    DaxGoldenCase(
        name="syntax_error_location",
        dax="CALCULATE([Net Sales],",
        ast={"root_kind": "expression"},
        error={"line": 1, "column": 23},
    ),
    DaxGoldenCase(
        name="unresolved_references",
        dax="[Missing Measure] + SUM('Sales'[Unknown])",
        ast={"root_kind": "expression", "contains": ["measure_reference", "column_reference"]},
        references=(_column("Sales", "Unknown"), _measure("Missing Measure")),
        error={"kind": "unresolved_reference"},
    ),
    DaxGoldenCase(
        name="ambiguous_measure_reference",
        dax="[Sales]",
        ast={"root_kind": "expression", "contains": ["measure_reference"]},
        references=(_measure("Sales"),),
        error={"kind": "ambiguous_reference"},
    ),
)


GOLDEN_BY_NAME = {case.name: case for case in GOLDEN_DAX}


CANONICAL_SYMBOLS = {
    "model": MODEL_ID,
    "tables": {
        "Sales": SALES_TABLE,
        "Sales Table": SALES_TABLE_QUOTED,
        "Date": DATE_TABLE,
        "Currency Selector": CURRENCY_TABLE,
        "Product": PRODUCT_TABLE,
        "Customer": CUSTOMER_TABLE,
        "O'Brien": OBRIEN_TABLE,
    },
    "columns": {
        ("Sales", "Amount"): f"{SALES_TABLE}/column:amount",
        ("Sales", "Currency"): f"{SALES_TABLE}/column:currency",
        ("Sales", "ShipDate"): f"{SALES_TABLE}/column:ship-date",
        ("Sales", "CustomerId"): f"{SALES_TABLE}/column:customer-id",
        ("Sales", "Unknown"): None,
        ("Sales Table", "Net Amount"): f"{SALES_TABLE_QUOTED}/column:net-amount",
        ("O'Brien", "Value"): f"{OBRIEN_TABLE}/column:value",
        ("Date", "Year"): f"{DATE_TABLE}/column:year",
        ("Date", "Date"): f"{DATE_TABLE}/column:date",
        ("Currency Selector", "Currency"): f"{CURRENCY_TABLE}/column:currency",
        ("Product", "Category"): f"{PRODUCT_TABLE}/column:category",
        ("Customer", "Id"): f"{CUSTOMER_TABLE}/column:id",
    },
    "measures": {
        "Base Sales": f"{SALES_TABLE}/measure:base-sales",
        "Net Sales": f"{SALES_TABLE}/measure:net-sales",
        "Gross Margin": f"{SALES_TABLE}/measure:gross-margin",
        "Missing Measure": None,
        "Sales": None,
    },
}


__all__ = ["CANONICAL_SYMBOLS", "DaxGoldenCase", "GOLDEN_BY_NAME", "GOLDEN_DAX"]
