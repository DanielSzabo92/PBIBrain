"""Small deterministic sources for Phase 3 semantic inference tests."""

from __future__ import annotations

import copy


MODEL_ID = "semantic-model-001"
TABLE_SALES = "table-sales"
TABLE_DATE = "table-date"
TABLE_CONTROL = "table-display-controls"
TABLE_NAMING_ONLY = "table-selector-name-only"
TABLE_CONFLICT = "table-conflict"
COL_AMOUNT = "column-amount"
COL_SALES_DATE = "column-sales-date"
COL_DATE = "column-date"
COL_CHOICE = "column-choice"
COL_CONTROL_UNRELATED = "column-control-unrelated"
COL_NAMING_ONLY = "column-naming-only"
COL_CONFLICT = "column-conflict"
MEASURE_BASE = "measure-base-amount"
MEASURE_NET = "measure-net-revenue"
MEASURE_CONFLICT = "measure-conflict-probe"


def semantic_model_source() -> dict:
    """Return a model with positive, negative, and conflicting semantics.

    The control table is deliberately not named ``selector``.  The naming-only
    table is deliberately named like one but has no behavioral use.
    """

    return {
        "id": MODEL_ID,
        "name": "Semantic Test Model",
        "description": "Deterministic semantic-inference fixture.",
        "tables": [
            {
                "id": TABLE_SALES,
                "name": "Sales",
                "description": "Invoice fact table.",
                "columns": [
                    {
                        "id": COL_AMOUNT,
                        "name": "Amount",
                        "description": "Invoice amount.",
                        "dataType": "Double",
                    },
                    {
                        "id": COL_SALES_DATE,
                        "name": "DateKey",
                        "description": "Invoice date key.",
                        "dataType": "Int64",
                    },
                ],
                "measures": [
                    {
                        "id": MEASURE_BASE,
                        "name": "Amount Summary",
                        "description": "Invoice amount before currency conversion.",
                        "expression": "SUM('Sales'[Amount])",
                    },
                    {
                        "id": MEASURE_NET,
                        "name": "Value",
                        "description": (
                            "Net invoiced revenue after discounts. "
                            "Also called booked revenue."
                        ),
                        "expression": (
                            "VAR Chosen = SELECTEDVALUE('Display Controls'[Choice], \"LOCAL\") "
                            "RETURN IF(Chosen = \"USD\", [Amount Summary], [Amount Summary])"
                        ),
                    },
                    {
                        "id": MEASURE_CONFLICT,
                        "name": "Revenue Probe",
                        "description": "Revenue fact amount.",
                        "expression": (
                            "IF(SELECTEDVALUE('Unrelated Options'[Mode], \"A\") = \"B\", "
                            "[Amount Summary], [Amount Summary])"
                        ),
                    },
                ],
            },
            {
                "id": TABLE_DATE,
                "name": "Date",
                "description": "Calendar dimension.",
                "columns": [
                    {
                        "id": COL_DATE,
                        "name": "Date",
                        "description": "Calendar date.",
                        "dataType": "DateTime",
                    },
                ],
            },
            {
                "id": TABLE_CONTROL,
                "name": "Display Controls",
                "description": "Display choices used by report measures.",
                "columns": [
                    {
                        "id": COL_CHOICE,
                        "name": "Choice",
                        "description": "Display currency choice.",
                        "dataType": "String",
                        "values": ["LOCAL", "USD"],
                        "distinctValues": ["LOCAL", "USD"],
                    },
                    {
                        "id": COL_CONTROL_UNRELATED,
                        "name": "Internal Label",
                        "description": "Unrelated control metadata.",
                        "dataType": "String",
                        "values": ["INTERNAL", "PUBLIC"],
                        "distinctValues": ["INTERNAL", "PUBLIC"],
                    },
                ],
            },
            {
                "id": TABLE_NAMING_ONLY,
                "name": "Selector Name Only",
                "description": "Disconnected table not consumed by any expression.",
                "columns": [
                    {
                        "id": COL_NAMING_ONLY,
                        "name": "Value",
                        "dataType": "String",
                        "values": ["A", "B"],
                    },
                ],
            },
            {
                "id": TABLE_CONFLICT,
                "name": "Unrelated Options",
                "description": "Sales revenue fact table containing transaction amounts.",
                "columns": [
                    {
                        "id": COL_CONFLICT,
                        "name": "Mode",
                        "description": "Mode used by a display control.",
                        "dataType": "String",
                        "values": ["A", "B"],
                    },
                ],
            },
        ],
        "relationships": [
            {
                "id": "relationship-date",
                "fromTable": TABLE_SALES,
                "fromColumn": COL_SALES_DATE,
                "toTable": TABLE_DATE,
                "toColumn": COL_DATE,
                "cardinality": "ManyToOne",
                "isActive": True,
            },
        ],
    }


def semantic_report_source(report_id: str = "semantic-report-001") -> dict:
    """Return repeated co-occurrence evidence without compatibility claims."""

    return {
        "id": report_id,
        "name": "Semantic Test Report",
        "description": "Report usage fixture.",
        "modelId": MODEL_ID,
        "sections": [
            {
                "id": f"{report_id}-page",
                "name": "Overview",
                "displayName": "Overview",
                "order": 0,
                "visualContainers": [
                    {
                        "id": f"{report_id}-visual-1",
                        "visualType": "columnChart",
                        "fields": [
                            {"objectId": COL_DATE, "kind": "column"},
                            {"objectId": MEASURE_NET, "kind": "measure"},
                        ],
                    },
                    {
                        "id": f"{report_id}-visual-2",
                        "visualType": "lineChart",
                        "fields": [
                            {"objectId": COL_DATE, "kind": "column"},
                            {"objectId": MEASURE_NET, "kind": "measure"},
                        ],
                    },
                ],
            },
        ],
    }


def conflicting_model_source() -> dict:
    """Independent copy used when a conflict must be isolated."""

    return copy.deepcopy(semantic_model_source())


def fallback_values_model_source(option_table_name: str = "Option Set") -> dict:
    """Minimal disconnected table consumed through table-level ``VALUES``."""

    return {
        "id": "fallback-values-model-001",
        "name": "Fallback Values Model",
        "tables": [
            {
                "id": "fallback-sales",
                "name": "Sales",
                "columns": [{"id": "fallback-amount", "name": "Amount"}],
                "measures": [
                    {
                        "id": "fallback-base",
                        "name": "Base",
                        "expression": "SUM('Sales'[Amount])",
                    },
                    {
                        "id": "fallback-consumer",
                        "name": "Consumer",
                        "expression": (
                            f"IF(COUNTROWS(VALUES('{option_table_name}'[Value])) > 0, "
                            "[Base], [Base])"
                        ),
                    },
                ],
            },
            {
                "id": "fallback-options",
                "name": option_table_name,
                "columns": [
                    {
                        "id": "fallback-option-value",
                        "name": "Value",
                        "dataType": "String",
                        "values": ["A", "B"],
                    },
                ],
            },
        ],
    }


__all__ = [
    "MODEL_ID",
    "TABLE_SALES",
    "TABLE_DATE",
    "TABLE_CONTROL",
    "TABLE_NAMING_ONLY",
    "TABLE_CONFLICT",
    "COL_AMOUNT",
    "COL_SALES_DATE",
    "COL_DATE",
    "COL_CHOICE",
    "COL_CONTROL_UNRELATED",
    "COL_NAMING_ONLY",
    "COL_CONFLICT",
    "MEASURE_BASE",
    "MEASURE_NET",
    "MEASURE_CONFLICT",
    "semantic_model_source",
    "semantic_report_source",
    "conflicting_model_source",
    "fallback_values_model_source",
]
