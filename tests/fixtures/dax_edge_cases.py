"""Small canonical symbols and DAX strings for Phase 2 edge regressions."""

from __future__ import annotations

import copy

from backend.graph.schema import Node


MODEL_A = "model:dax-edge-a"
MODEL_B = "model:dax-edge-b"
SALES_TABLE = f"{MODEL_A}/table:sales"
DATE_TABLE = f"{MODEL_A}/table:date"
PRODUCT_TABLE = f"{MODEL_A}/table:product"
SALES_CURRENCY = f"{SALES_TABLE}/column:currency"
CURRENCY_TABLE = f"{MODEL_A}/table:currency"
CURRENCY_VALUE = f"{CURRENCY_TABLE}/column:currency"
SALES_AMOUNT = f"{SALES_TABLE}/column:amount"
DATE_NAME = f"{DATE_TABLE}/column:name"
PRODUCT_NAME = f"{PRODUCT_TABLE}/column:name"
MEASURE_X = f"{SALES_TABLE}/measure:x"
MEASURE_A = f"{SALES_TABLE}/measure:a"
MEASURE_PROFIT = f"{SALES_TABLE}/measure:profit"
MODEL_B_MEASURE_X = f"{MODEL_B}/table:other/measure:x"

BARE_TABLE_FILTER_DAX = "CALCULATE([X], FILTER(Sales, Sales[Amount] > 0), ALL(Sales))"
TREATAS_DAX = "TREATAS(VALUES('Currency'[Currency]), 'Sales'[Currency])"
FIELD_PARAMETER_DAX = (
    '{("Product", NAMEOF(\'Product\'[Name]), 0), '
    '("Date", NAMEOF(\'Date\'[Name]), 1)}'
)


def node(
    node_id: str,
    node_type: str,
    name: str,
    *,
    model_id: str = MODEL_A,
    properties: dict | None = None,
) -> Node:
    """Build a compact canonical node for analyzer/parser regressions."""

    return Node(
        id=node_id,
        type=node_type,
        name=name,
        model_id=model_id,
        source_id=node_id.rsplit(":", 1)[-1],
        properties=properties or {},
    )


def base_nodes(*, source_expression: str | None = None) -> list[Node]:
    """Return one model's symbols plus an expression source object."""

    table_sales = node(SALES_TABLE, "TABLE", "Sales")
    table_date = node(DATE_TABLE, "TABLE", "Date")
    table_product = node(PRODUCT_TABLE, "TABLE", "Product")
    table_currency = node(CURRENCY_TABLE, "TABLE", "Currency")
    values = [
        node(MODEL_A, "MODEL", "DAX edge model"),
        table_sales,
        table_date,
        table_product,
        table_currency,
        node(
            SALES_CURRENCY,
            "COLUMN",
            "Currency",
            properties={"table_id": table_sales.id},
        ),
        node(
            CURRENCY_VALUE,
            "COLUMN",
            "Currency",
            properties={"table_id": table_currency.id},
        ),
        node(
            SALES_AMOUNT,
            "COLUMN",
            "Amount",
            properties={"table_id": table_sales.id},
        ),
        node(
            DATE_NAME,
            "COLUMN",
            "Name",
            properties={"table_id": table_date.id},
        ),
        node(
            PRODUCT_NAME,
            "COLUMN",
            "Name",
            properties={"table_id": table_product.id},
        ),
        node(MEASURE_X, "MEASURE", "X", properties={"table_id": table_sales.id}),
        node(MEASURE_A, "MEASURE", "A", properties={"table_id": table_sales.id}),
        node(
            MEASURE_PROFIT,
            "MEASURE",
            "Profit",
            properties={"table_id": table_sales.id},
        ),
    ]
    if source_expression is not None:
        values.append(
            node(
                f"{MODEL_A}/measure:source",
                "MEASURE",
                "Source",
                properties={"expression": source_expression, "table_id": table_sales.id},
            )
        )
    return values


def dynamic_format_model_source() -> dict:
    """Return a source fixture with a measure format expression alias."""

    from .phase2_sources import dax_model_source

    source = copy.deepcopy(dax_model_source())
    source["tables"][0]["measures"][0]["formatStringExpression"] = (
        "SELECTEDMEASUREFORMATSTRING()"
    )
    return source


__all__ = [
    "BARE_TABLE_FILTER_DAX",
    "CURRENCY_TABLE",
    "CURRENCY_VALUE",
    "DATE_NAME",
    "FIELD_PARAMETER_DAX",
    "MEASURE_A",
    "MEASURE_PROFIT",
    "MEASURE_X",
    "MODEL_A",
    "MODEL_B",
    "MODEL_B_MEASURE_X",
    "PRODUCT_NAME",
    "SALES_AMOUNT",
    "SALES_CURRENCY",
    "SALES_TABLE",
    "TREATAS_DAX",
    "base_nodes",
    "dynamic_format_model_source",
    "node",
]
