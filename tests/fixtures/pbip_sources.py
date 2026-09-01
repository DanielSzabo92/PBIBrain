"""Self-contained file-backed PBIP/PBIR fixtures.

The fixture intentionally uses the on-disk PBIP layout instead of the
canonical JSON mappings used by the lower-level scanner tests.  It gives the
direct-project reader a small TMDL model and PBIR report to discover.
"""

from __future__ import annotations

import json
from pathlib import Path


MODEL_NAME = "Finance.SemanticModel"
REPORT_NAME = "Finance.Report"
PROJECT_NAME = "Finance"

TABLE_SALES = "Sales"
TABLE_DATE = "Date"
MEASURE_NET = "Net Sales"
MEASURE_GROSS = "Gross Sales"
PAGE_OVERVIEW = "Overview"
VISUAL_SALES = "SalesByDate"
VISUAL_GROSS = "GrossSalesCard"

# TMDL lineage tags are the stable source identities used by the fixture.
MODEL_LINEAGE = "11111111-1111-1111-1111-111111111111"
SALES_LINEAGE = "22222222-2222-2222-2222-222222222222"
DATE_LINEAGE = "33333333-3333-3333-3333-333333333333"
AMOUNT_LINEAGE = "44444444-4444-4444-4444-444444444444"
SALES_DATE_LINEAGE = "55555555-5555-5555-5555-555555555555"
DATE_KEY_LINEAGE = "66666666-6666-6666-6666-666666666666"
NET_LINEAGE = "77777777-7777-7777-7777-777777777777"
GROSS_LINEAGE = "88888888-8888-8888-8888-888888888888"
RELATIONSHIP_LINEAGE = "99999999-9999-9999-9999-999999999999"


def _write(path: Path, value: str | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, dict):
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    else:
        path.write_text(value, encoding="utf-8")


def _project_file(*, model_name: str = MODEL_NAME, dataset_artifact: bool = False) -> dict:
    model_artifact = (
        {"type": "dataset", "path": model_name}
        if dataset_artifact
        else {"semanticModel": {"path": model_name}}
    )
    return {
        "version": "1.0.0",
        "artifacts": [
            {"report": {"path": REPORT_NAME}},
            model_artifact,
        ],
    }


def _model_tmdl() -> str:
    return (
        "model FinanceModel\n"
        "    culture: en-US\n"
        "    defaultPowerBIDataSourceVersion: powerBI_V3\n"
        f"    lineageTag: {MODEL_LINEAGE}\n"
    )


def _sales_tmdl(*, include_gross: bool) -> str:
    value = (
        "table Sales\n"
        f"    lineageTag: {SALES_LINEAGE}\n"
        "\n"
        "    column Amount\n"
        "        dataType: decimal\n"
        f"        lineageTag: {AMOUNT_LINEAGE}\n"
        "        sourceColumn: Amount\n"
        "\n"
        "    column DateKey\n"
        "        dataType: int64\n"
        f"        lineageTag: {SALES_DATE_LINEAGE}\n"
        "        sourceColumn: DateKey\n"
        "\n"
        "    measure 'Net Sales' = SUM(Sales[Amount])\n"
        f"        lineageTag: {NET_LINEAGE}\n"
        "        formatString: #,##0\n"
    )
    if include_gross:
        value += (
            "\n"
            "    measure 'Gross Sales' = [Net Sales] * 1.1\n"
            f"        lineageTag: {GROSS_LINEAGE}\n"
            "        formatString: #,##0\n"
        )
    return value


def _date_tmdl() -> str:
    return (
        "table Date\n"
        f"    lineageTag: {DATE_LINEAGE}\n"
        "\n"
        "    column DateKey\n"
        "        dataType: int64\n"
        f"        lineageTag: {DATE_KEY_LINEAGE}\n"
        "        sourceColumn: DateKey\n"
    )


def _model_bim(*, include_gross: bool) -> dict:
    sales = {
        "id": SALES_LINEAGE,
        "name": TABLE_SALES,
        "columns": [
            {
                "id": AMOUNT_LINEAGE,
                "name": "Amount",
                "dataType": "decimal",
                "sourceColumn": "Amount",
            },
            {
                "id": SALES_DATE_LINEAGE,
                "name": "DateKey",
                "dataType": "int64",
                "sourceColumn": "DateKey",
            },
        ],
        "measures": [
            {
                "id": NET_LINEAGE,
                "name": MEASURE_NET,
                "expression": "SUM(Sales[Amount])",
                "formatString": "#,##0",
            }
        ],
    }
    if include_gross:
        sales["measures"].append(
            {
                "id": GROSS_LINEAGE,
                "name": MEASURE_GROSS,
                "expression": "[Net Sales] * 1.1",
                "formatString": "#,##0",
            }
        )
    return {
        "id": MODEL_LINEAGE,
        "name": "FinanceModel",
        "compatibilityLevel": 1567,
        "model": {
            "culture": "en-US",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "tables": [
                sales,
                {
                    "id": DATE_LINEAGE,
                    "name": TABLE_DATE,
                    "columns": [
                        {
                            "id": DATE_KEY_LINEAGE,
                            "name": "DateKey",
                            "dataType": "int64",
                            "sourceColumn": "DateKey",
                        }
                    ],
                },
            ],
            "relationships": [
                {
                    "id": RELATIONSHIP_LINEAGE,
                    "fromTable": TABLE_SALES,
                    "fromColumn": "DateKey",
                    "toTable": TABLE_DATE,
                    "toColumn": "DateKey",
                }
            ],
        },
    }


def _relationships_tmdl() -> str:
    return (
        f"relationship {RELATIONSHIP_LINEAGE}\n"
        "    fromColumn: Sales.DateKey\n"
        "    toColumn: Date.DateKey\n"
    )


def _visual_file(*, name: str, visual_type: str, title: str, measure: str) -> dict:
    return {
        "name": name,
        "position": {"x": 0, "y": 0, "z": 0, "width": 320, "height": 240},
        "visual": {
            "visualType": visual_type,
            "objects": {
                "title": [
                    {"properties": {"text": {"expr": {"Literal": {"Value": f"'{title}'"}}}}}
                ]
            },
            "query": {
                "queryState": {
                    "Category": {
                        "projections": [
                            {
                                "queryRef": "Date.DateKey",
                                "field": {
                                    "Column": {
                                        "Expression": {"SourceRef": {"Entity": "Date"}},
                                        "Property": "DateKey",
                                    }
                                },
                            }
                        ]
                    },
                    "Y": {
                        "projections": [
                            {
                                "queryRef": f"Sales.{measure}",
                                "field": {
                                    "Measure": {
                                        "Expression": {"SourceRef": {"Entity": "Sales"}},
                                        "Property": measure,
                                    }
                                },
                            }
                        ]
                    },
                }
            },
        },
    }


def _legacy_visual(*, name: str, visual_type: str, title: str, measure: str) -> dict:
    config = {
        "name": name,
        "singleVisual": {
            "visualType": visual_type,
            "vcObjects": {
                "title": [
                    {"properties": {"text": {"expr": {"Literal": {"Value": f"'{title}'"}}}}}
                ]
            },
        },
    }
    query = {
        "Commands": [
            {
                "SemanticQueryDataShapeCommand": {
                    "Query": {
                        "Version": 2,
                        "From": [
                            {"Name": "d", "Entity": "Date", "Type": 0},
                            {"Name": "s", "Entity": "Sales", "Type": 0},
                        ],
                        "Select": [
                            {
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "d"}},
                                    "Property": "DateKey",
                                },
                                "Name": "Date.DateKey",
                            },
                            {
                                "Measure": {
                                    "Expression": {"SourceRef": {"Source": "s"}},
                                    "Property": measure,
                                },
                                "Name": f"Sales.{measure}",
                            },
                        ],
                    }
                }
            }
        ]
    }
    return {
        "id": name,
        "config": json.dumps(config),
        "query": json.dumps(query),
        "filters": json.dumps([]),
    }


def _legacy_report(*, include_extra: bool) -> dict:
    visuals = [
        _legacy_visual(
            name=VISUAL_SALES,
            visual_type="columnChart",
            title="Sales by date",
            measure=MEASURE_NET,
        )
    ]
    if include_extra:
        visuals.append(
            _legacy_visual(
                name=VISUAL_GROSS,
                visual_type="card",
                title="Gross sales",
                measure=MEASURE_GROSS,
            )
        )
    return {
        "name": "Finance Legacy Report",
        "sections": [
            {
                "id": PAGE_OVERVIEW,
                "name": PAGE_OVERVIEW,
                "displayName": PAGE_OVERVIEW,
                "ordinal": 0,
                "visualContainers": visuals,
            }
        ],
    }


def write_pbip_project(
    root: Path,
    *,
    include_extra: bool = False,
    model_format: str = "tmdl",
    report_format: str = "pbir",
    model_kind: str = "semanticmodel",
    dataset_reference: str = "byPath",
    include_ignored: bool = False,
) -> Path:
    """Write a tiny standard PBIP project and return its ``.pbip`` path."""

    root.mkdir(parents=True, exist_ok=True)
    project = root / f"{PROJECT_NAME}.pbip"
    model_name = f"{PROJECT_NAME}.Dataset" if model_kind == "dataset" else MODEL_NAME
    model_root = root / model_name
    model_definition = model_root / "definition"
    report_root = root / REPORT_NAME
    report_definition = report_root / "definition"
    page_root = report_definition / "pages" / PAGE_OVERVIEW

    _write(project, _project_file(model_name=model_name, dataset_artifact=model_kind == "dataset"))
    if model_format == "tmsl":
        _write(model_root / "definition.pbism", {"version": "1.0"})
        _write(model_root / "model.bim", _model_bim(include_gross=include_extra))
    else:
        _write(model_root / "definition.pbism", {"version": "4.0.0"})
        _write(model_definition / "model.tmdl", _model_tmdl())
        _write(model_definition / "tables" / "Sales.tmdl", _sales_tmdl(include_gross=include_extra))
        _write(model_definition / "tables" / "Date.tmdl", _date_tmdl())
        _write(model_definition / "relationships.tmdl", _relationships_tmdl())

    reference = (
        {"byConnection": {"connectionString": "semanticmodelid=remote-finance-model"}}
        if dataset_reference == "byConnection"
        else {"byPath": {"path": f"../{model_name}"}}
    )
    if report_format == "legacy":
        _write(
            report_root / "definition.pbir",
            {
                "version": "1.0",
                "datasetReference": reference,
            },
        )
        _write(report_root / "report.json", _legacy_report(include_extra=include_extra))
    else:
        _write(
            report_root / "definition.pbir",
            {
                "version": "4.0",
                "datasetReference": reference,
            },
        )
        _write(report_definition / "report.json", {"name": "Finance Report"})
        _write(page_root / "page.json", {"name": PAGE_OVERVIEW, "displayName": "Overview", "ordinal": 0})
        _write(
            page_root / "visuals" / VISUAL_SALES / "visual.json",
            _visual_file(name=VISUAL_SALES, visual_type="columnChart", title="Sales by date", measure=MEASURE_NET),
        )
        if include_extra:
            _write(
                page_root / "visuals" / VISUAL_GROSS / "visual.json",
                _visual_file(
                    name=VISUAL_GROSS,
                    visual_type="card",
                    title="Gross sales",
                    measure=MEASURE_GROSS,
                ),
            )
    if include_ignored:
        _write(model_root / ".pbi" / "localSettings.json", {"name": "Ignored semantic settings"})
        _write(model_root / ".pbi" / "cache.abf", "ignored semantic cache")
        _write(model_root / "TMDLScripts" / "Ignored.tmdl", "table IgnoredSemanticScript\n")
        _write(model_root / "DAXQueries" / "Ignored.dax", "EVALUATE ROW(\"ignored\", 1)\n")
        _write(model_root / "diagramLayout.json", {"name": "Ignored semantic diagram"})
        _write(report_root / ".pbi" / "localSettings.json", {"name": "Ignored report settings"})
        _write(report_root / "mobileState.json", {"name": "Ignored mobile state"})
        _write(report_root / "semanticModelDiagramLayout.json", {"name": "Ignored report diagram"})
        _write(
            report_root / "StaticResources" / "RegisteredResources" / "Ignored.json",
            {"name": "Ignored report resource"},
        )
    return project


__all__ = [
    "AMOUNT_LINEAGE",
    "DATE_KEY_LINEAGE",
    "DATE_LINEAGE",
    "GROSS_LINEAGE",
    "MEASURE_GROSS",
    "MEASURE_NET",
    "MODEL_LINEAGE",
    "NET_LINEAGE",
    "PAGE_OVERVIEW",
    "PROJECT_NAME",
    "RELATIONSHIP_LINEAGE",
    "REPORT_NAME",
    "SALES_DATE_LINEAGE",
    "SALES_LINEAGE",
    "TABLE_DATE",
    "TABLE_SALES",
    "VISUAL_GROSS",
    "VISUAL_SALES",
    "write_pbip_project",
]
