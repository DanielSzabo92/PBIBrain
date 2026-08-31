"""Small source-shaped model/report fixtures for Phase 1.

The fixture deliberately uses source keys that differ from canonical keys.  A
normalizer must translate these data without leaking adapter-specific shapes
into the graph.
"""

import json

MODEL_ID = "model-001"
REPORT_A_ID = "report-a"
REPORT_B_ID = "report-b"


def model_source(*, measure_name: str = "Sales", include_measure: bool = True) -> dict:
    """Return one compact model with every V1 model object type."""

    measures = [
        {
            "id": "measure-sales",
            "name": measure_name,
            "description": "Net invoiced sales.",
            "expression": "SUM('Sales'[Amount])",
            "formatString": "#,##0",
            "isHidden": False,
        },
    ] if include_measure else []

    return {
        "id": MODEL_ID,
        "name": "Revenue Model",
        "description": "Synthetic model for canonical graph acceptance tests.",
        "database": {
            "id": MODEL_ID,
            "name": "Revenue Model",
            "description": "Synthetic model for canonical graph acceptance tests.",
        },
        "tables": [
            {
                "id": "table-sales",
                "name": "Sales",
                "description": "Invoice facts.",
                "isHidden": False,
                "columns": [
                    {
                        "id": "column-amount",
                        "name": "Amount",
                        "description": "Invoice amount.",
                        "dataType": "Double",
                        "isHidden": False,
                    },
                    {
                        "id": "column-date",
                        "name": "DateKey",
                        "description": "Invoice date key.",
                        "dataType": "Int64",
                        "isHidden": False,
                    },
                ],
                "measures": measures,
            },
            {
                "id": "table-date",
                "name": "Date",
                "description": "Calendar dimension.",
                "isHidden": False,
                "columns": [
                    {
                        "id": "column-date-key",
                        "name": "DateKey",
                        "description": "Calendar key.",
                        "dataType": "Int64",
                        "isHidden": False,
                    },
                ],
                "measures": [],
            },
            {
                "id": "table-switch",
                "name": "Display Switch",
                "description": "Disconnected display selector.",
                "isHidden": False,
                "columns": [
                    {
                        "id": "column-switch-value",
                        "name": "Value",
                        "description": "Display option.",
                        "dataType": "String",
                        "isHidden": False,
                    },
                ],
                "measures": [],
            },
        ],
        "relationships": [
            {
                "id": "relationship-date",
                "fromTable": "table-sales",
                "fromColumn": "column-date",
                "toTable": "table-date",
                "toColumn": "column-date-key",
                "cardinality": "ManyToOne",
                "crossFilteringBehavior": "OneDirection",
                "isActive": True,
            },
        ],
        "fieldParameters": [
            {
                "id": "field-parameter-sales",
                "name": "Sales Fields",
                "description": "Fields users may place in the visual.",
                "entries": [
                    {"name": "Amount", "order": 0, "objectId": "column-amount"},
                ],
            },
        ],
        "sharedExpressions": [
            {
                "id": "shared-expression-calendar",
                "name": "Calendar Filter",
                "description": "Reusable calendar expression.",
                "expression": "FILTER('Date', 'Date'[DateKey] > 0)",
            },
        ],
        "userDefinedFunctions": [
            {
                "id": "udf-format-amount",
                "name": "FormatAmount",
                "description": "Formats a numeric amount.",
                "parameters": [{"name": "value", "dataType": "Double"}],
                "expression": "FORMAT(value, \"#,##0\")",
            },
        ],
        "calculationGroups": [
            {
                "id": "calc-group-time",
                "name": "Time Intelligence",
                "description": "Time calculations.",
                "precedence": 10,
                "calculationItems": [
                    {
                        "id": "calc-item-ytd",
                        "name": "YTD",
                        "description": "Year to date.",
                        "expression": "TOTALYTD([Sales], 'Date'[DateKey])",
                        "formatStringExpression": "SELECTEDMEASUREFORMATSTRING()",
                        "ordinal": 0,
                    },
                ],
            },
        ],
    }


def report_source(report_id: str, *, title: str = "Sales report") -> dict:
    """Return a report that binds to the model without duplicating model data."""

    return {
        "id": report_id,
        "name": title,
        "description": "Synthetic report.",
        "modelId": MODEL_ID,
        "sections": [
            {
                "id": f"{report_id}-page-overview",
                "name": "Overview",
                "displayName": "Overview",
                "order": 0,
                "visualContainers": [
                    {
                        "id": f"{report_id}-visual-sales",
                        "visualType": "columnChart",
                        "title": "Sales by date",
                        "fields": [
                            {"objectId": "column-date-key", "kind": "column"},
                        ],
                        "measures": [{"objectId": "measure-sales"}],
                        "filters": [
                            {
                                "id": f"{report_id}-visual-filter-date",
                                "scope": "visual",
                                "target": {"objectId": "column-date-key"},
                                "condition": "In",
                                "value": ["2026-01-01"],
                            },
                        ],
                    },
                ],
                "filters": [
                    {
                        "id": f"{report_id}-page-filter-date",
                        "scope": "page",
                        "target": {"objectId": "column-date-key"},
                        "condition": "NotBlank",
                        "value": None,
                    },
                ],
            },
        ],
        "filters": [
            {
                "id": f"{report_id}-report-filter-date",
                "scope": "report",
                "target": {"objectId": "column-date-key"},
                "condition": "In",
                "value": ["2026-01-01"],
            },
        ],
    }


def json_visual_report_source(report_id: str = "report-json-visual") -> dict:
    """Return a report using Power BI's JSON-string visual-container fields."""

    config = {
        "name": f"{report_id}-visual-sales",
        "singleVisual": {
            "visualType": "columnChart",
            "projections": {
                "Category": [{"queryRef": "Date.DateKey"}],
                "Y": [{"queryRef": "Sales.Sales"}],
            },
            "prototypeQuery": {
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
                            "Property": "Sales",
                        },
                        "Name": "Sales.Sales",
                    },
                ],
            },
            "vcObjects": {
                "title": [
                    {
                        "properties": {
                            "text": {
                                "expr": {"Literal": {"Value": "'Sales by date'"}}
                            }
                        }
                    }
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
                                    "Property": "Sales",
                                },
                                "Name": "Sales.Sales",
                            },
                        ],
                    },
                    "Binding": {"DataReduction": {"DataVolume": 3}},
                }
            }
        ]
    }
    filters = [
        {
            "name": f"{report_id}-visual-filter-date",
            "expression": {
                "Column": {
                    "Expression": {"SourceRef": {"Entity": "Date", "Source": "d"}},
                    "Property": "DateKey",
                }
            },
            "filter": {
                "Version": 2,
                "From": [{"Name": "d", "Entity": "Date", "Type": 0}],
                "Where": [
                    {
                        "Condition": {
                            "In": {
                                "Expressions": [
                                    {
                                        "Column": {
                                            "Expression": {"SourceRef": {"Source": "d"}},
                                            "Property": "DateKey",
                                        }
                                    }
                                ],
                                "Values": [[{"Literal": {"Value": "'2026-01-01'"}}]],
                            }
                        }
                    }
                ],
            },
        }
    ]
    pbir_visual = {
        "id": f"{report_id}-visual-pbir",
        "visual": {
            "visualType": "lineChart",
            "objects": {
                "title": [
                    {
                        "properties": {
                            "text": {
                                "expr": {"Literal": {"Value": "'Sales trend (PBIR)'"}}
                            }
                        }
                    }
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
                                "queryRef": "Sales.Sales",
                                "field": {
                                    "Measure": {
                                        "Expression": {"SourceRef": {"Entity": "Sales"}},
                                        "Property": "Sales",
                                    }
                                },
                            }
                        ]
                    },
                }
            },
        },
    }
    return {
        "id": report_id,
        "name": "JSON visual report",
        "description": "Synthetic report with native visual-container JSON strings.",
        "modelId": MODEL_ID,
        "sections": [
            {
                "id": f"{report_id}-page-overview",
                "displayName": "Overview",
                "order": 0,
                "visualContainers": [
                    {
                        "id": f"{report_id}-visual-sales",
                        "config": json.dumps(config),
                        "query": json.dumps(query),
                        "filters": json.dumps(filters),
                    },
                    pbir_visual,
                ],
            }
        ],
    }


def renamed_model_source() -> dict:
    """Same source identity, changed display name."""

    return model_source(measure_name="Net Sales")
