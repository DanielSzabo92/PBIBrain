"""Deterministic model variants for Phase 5 sync and validation tests."""

from __future__ import annotations

import copy


MODEL_ID = "phase5-model-001"
TABLE_SALES = "phase5-table-sales"
TABLE_DATE = "phase5-table-date"
TABLE_OPTIONS = "phase5-table-options"
COL_AMOUNT = "phase5-column-amount"
COL_DATE = "phase5-column-date"
COL_OPTION = "phase5-column-option"
MEASURE_BASE = "phase5-measure-base"
MEASURE_NET = "phase5-measure-net"
MEASURE_LEGACY = "phase5-measure-legacy"
MEASURE_FORECAST = "phase5-measure-forecast"


def phase5_model_source(
    *,
    net_expression: str = "[Base Sales]",
    net_name: str = "Net Sales",
    include_legacy: bool = True,
    include_forecast: bool = False,
) -> dict:
    """Return one source with stable IDs and controlled deltas."""

    measures = [
        {
            "id": MEASURE_BASE,
            "name": "Base Sales",
            "description": "Base invoiced sales.",
            "expression": "SUM('Sales'[Amount])",
        },
        {
            "id": MEASURE_NET,
            "name": net_name,
            "description": "Net invoiced sales after discounts.",
            "expression": net_expression,
        },
    ]
    if include_legacy:
        measures.append(
            {
                "id": MEASURE_LEGACY,
                "name": "Legacy Sales",
                "description": "Retained measure for deletion checks.",
                "expression": "[Base Sales]",
            }
        )
    if include_forecast:
        measures.append(
            {
                "id": MEASURE_FORECAST,
                "name": "Forecast Sales",
                "description": "Forecast sales candidate.",
                "expression": "[Net Sales] * 1.1",
            }
        )
    return {
        "id": MODEL_ID,
        "name": "Phase 5 Model",
        "description": "Incremental synchronization fixture.",
        "tables": [
            {
                "id": TABLE_SALES,
                "name": "Sales",
                "description": "Invoice facts.",
                "columns": [
                    {"id": COL_AMOUNT, "name": "Amount", "dataType": "Double"},
                    {"id": COL_DATE, "name": "DateKey", "dataType": "Int64"},
                ],
                "measures": measures,
            },
            {
                "id": TABLE_DATE,
                "name": "Date",
                "description": "Calendar dimension.",
                "columns": [{"id": "phase5-column-date-key", "name": "DateKey", "dataType": "Int64"}],
                "measures": [],
            },
            {
                "id": TABLE_OPTIONS,
                "name": "Display Options",
                "description": "Disconnected display options.",
                "columns": [
                    {
                        "id": COL_OPTION,
                        "name": "Option",
                        "dataType": "String",
                        "values": ["LOCAL", "USD"],
                    }
                ],
                "measures": [],
            },
        ],
        "relationships": [
            {
                "id": "phase5-relationship-date",
                "fromTable": TABLE_SALES,
                "fromColumn": COL_DATE,
                "toTable": TABLE_DATE,
                "toColumn": "phase5-column-date-key",
                "cardinality": "ManyToOne",
                "isActive": True,
            }
        ],
    }


def phase5_changed_source() -> dict:
    source = phase5_model_source(net_expression="[Base Sales] * 0.95")
    source["description"] = "Incremental synchronization fixture, revised."
    return source


def phase5_renamed_source() -> dict:
    return phase5_model_source(net_name="Revenue After Discounts")


def phase5_new_source() -> dict:
    return phase5_model_source(include_forecast=True)


def phase5_deleted_source() -> dict:
    return phase5_model_source(include_legacy=False)


def phase5_broken_reference_source() -> dict:
    source = phase5_model_source()
    for table in source["tables"]:
        for measure in table.get("measures", []):
            if measure["id"] == MEASURE_NET:
                measure["expression"] = "[Missing Measure]"
                return source
    raise AssertionError("fixture measure missing")


def phase5_copy(source: dict) -> dict:
    return copy.deepcopy(source)


__all__ = [
    "MODEL_ID",
    "TABLE_SALES",
    "TABLE_DATE",
    "TABLE_OPTIONS",
    "COL_AMOUNT",
    "COL_DATE",
    "COL_OPTION",
    "MEASURE_BASE",
    "MEASURE_NET",
    "MEASURE_LEGACY",
    "MEASURE_FORECAST",
    "phase5_model_source",
    "phase5_changed_source",
    "phase5_renamed_source",
    "phase5_new_source",
    "phase5_deleted_source",
    "phase5_broken_reference_source",
    "phase5_copy",
]
