"""Canonical Power BI-shaped source used by Phase 2 scan tests."""

from __future__ import annotations

import copy

from .phase1_sources import MODEL_ID, model_source


def dax_model_source() -> dict:
    """Return one model with every supported expression-bearing object type."""

    source = copy.deepcopy(model_source(include_measure=False))
    sales = source["tables"][0]
    sales["columns"].append(
        {
            "id": "column-cost",
            "name": "Cost",
            "description": "Invoice cost.",
            "dataType": "Double",
            "isHidden": False,
        }
    )
    sales["columns"].append(
        {
            "id": "column-profit",
            "name": "Profit",
            "description": "Calculated invoice profit.",
            "dataType": "Double",
            "isHidden": False,
            "expression": "'Sales'[Amount] - 'Sales'[Cost]",
        }
    )
    sales["measures"] = [
        {
            "id": "measure-sales",
            "name": "Sales",
            "description": "Base sales amount.",
            "expression": "SUM('Sales'[Amount])",
            "formatString": "#,##0",
            "isHidden": False,
        },
        {
            "id": "measure-net-sales",
            "name": "Net Sales",
            "description": "Sales after discounts.",
            "expression": "[Sales]",
            "formatString": "#,##0",
            "isHidden": False,
        },
        {
            "id": "measure-gross-margin",
            "name": "Gross Margin",
            "description": "Net sales less cost.",
            "expression": "[Net Sales] - SUM('Sales'[Cost])",
            "formatString": "#,##0",
            "isHidden": False,
        },
        {
            "id": "measure-formatted-sales",
            "name": "Formatted Sales",
            "description": "Formatted net sales.",
            "expression": "FormatAmount([Net Sales], \"#,##0\")",
            "formatString": "#,##0",
            "isHidden": False,
        },
    ]
    source["calculationGroups"][0]["calculationItems"][0]["expression"] = "[Net Sales]"
    source["calculationGroups"][0]["calculationItems"][0]["formatStringExpression"] = "SELECTEDMEASUREFORMATSTRING()"
    return source


__all__ = ["MODEL_ID", "dax_model_source"]
