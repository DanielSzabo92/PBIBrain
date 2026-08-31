"""Small TMSL-shaped model fixtures for semantic-resolution regressions."""

from __future__ import annotations


def calculated_column_source() -> dict:
    """Return a TMSL-shaped model with an unqualified calculated-column DAX expression."""

    return {
        "name": "TMSL calculated-column fixture",
        "id": "tmsl-calculated-column-model",
        "tables": [
            {
                "name": "Date",
                "columns": [
                    {"name": "Date", "dataType": "dateTime", "sourceColumn": "Date"},
                    {"name": "MonthNo", "dataType": "int64", "sourceColumn": "MonthNo"},
                    {
                        "name": "MonthLabel",
                        "type": "calculated",
                        "dataType": "string",
                        "expression": "IF([Date] = DATE(2024, 1, 1), [MonthNo], 0)",
                    },
                ],
            }
        ],
    }


def measure_expression_lines_source() -> dict:
    """Return a TMSL-shaped model whose measure DAX arrives as source lines."""

    return {
        "name": "TMSL measure-lines fixture",
        "id": "tmsl-measure-lines-model",
        "tables": [
            {
                "name": "Sales",
                "columns": [{"name": "Amount", "dataType": "double"}],
                "measures": [
                    {
                        "name": "Total Sales",
                        "expression": ["SUM(", "'Sales'[Amount]", ")"],
                    }
                ],
            }
        ],
    }


def m_shared_expression_source() -> dict:
    """Return a TMSL-shaped model with a model-level M shared expression."""

    return {
        "name": "TMSL M-expression fixture",
        "id": "tmsl-m-expression-model",
        "expressions": [
            {
                "name": "Date Query",
                "kind": "m",
                "expression": 'let Source = #table({"Date"}, {{#date(2024, 1, 1)}}) in Source meta [IsParameterQuery=true]',
            }
        ],
    }
