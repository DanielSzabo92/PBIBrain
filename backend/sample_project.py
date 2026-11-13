"""A small sample project, so every view has content before a user connects their own files.

The sample is built in code: nothing has to be packaged beside the Python modules, and the file
written into the project folder is an ordinary model JSON source that a scan reads like any other.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SAMPLE_FILE = "retail-sales-sample.json"

_TABLES: dict[str, list[tuple[str, str]]] = {
    "Sales": [("Order ID", "String"), ("Order Date", "DateTime"), ("Customer Key", "Int64"), ("Product Key", "Int64"),
              ("Store Key", "Int64"), ("Quantity", "Int64"), ("Unit Price", "Decimal"), ("Unit Cost", "Decimal"), ("Discount", "Decimal")],
    "Customers": [("Customer Key", "Int64"), ("Customer", "String"), ("Segment", "String"), ("City", "String"), ("Country", "String")],
    "Products": [("Product Key", "Int64"), ("Product", "String"), ("Category", "String"), ("Subcategory", "String"), ("Brand", "String")],
    "Stores": [("Store Key", "Int64"), ("Store", "String"), ("Region", "String"), ("Opened", "DateTime")],
    "Calendar": [("Date", "DateTime"), ("Year", "Int64"), ("Quarter", "String"), ("Month", "String"), ("Month Number", "Int64")],
    "Targets": [("Month", "String"), ("Region", "String"), ("Target Amount", "Decimal")],
}

_MEASURES: list[tuple[str, str, str, str]] = [
    ("Sales", "Sales Amount", "Revenue after discount.", "SUMX('Sales', 'Sales'[Quantity] * 'Sales'[Unit Price] * (1 - 'Sales'[Discount]))"),
    ("Sales", "Cost Amount", "Cost of the goods sold.", "SUMX('Sales', 'Sales'[Quantity] * 'Sales'[Unit Cost])"),
    ("Sales", "Gross Margin", "Sales less cost.", "[Sales Amount] - [Cost Amount]"),
    ("Sales", "Gross Margin %", "Margin as a share of sales.", "DIVIDE([Gross Margin], [Sales Amount])"),
    ("Sales", "Units Sold", "Number of units.", "SUM('Sales'[Quantity])"),
    ("Sales", "Orders", "Number of distinct orders.", "DISTINCTCOUNT('Sales'[Order ID])"),
    ("Sales", "Average Order Value", "Sales per order.", "DIVIDE([Sales Amount], [Orders])"),
    ("Sales", "Sales YTD", "Sales from the start of the year.", "TOTALYTD([Sales Amount], 'Calendar'[Date])"),
    ("Sales", "Sales PY", "Sales in the same period last year.", "CALCULATE([Sales Amount], SAMEPERIODLASTYEAR('Calendar'[Date]))"),
    ("Sales", "Sales YoY %", "Growth against last year.", "DIVIDE([Sales Amount] - [Sales PY], [Sales PY])"),
    ("Customers", "Active Customers", "Customers with at least one order.", "DISTINCTCOUNT('Sales'[Customer Key])"),
    ("Customers", "Sales per Customer", "", "DIVIDE([Sales Amount], [Active Customers])"),
    ("Targets", "Target", "Monthly sales target.", "SUM('Targets'[Target Amount])"),
    ("Targets", "Target Attainment %", "Sales against target.", "DIVIDE([Sales Amount], [Target])"),
    ("Sales", "Discount Amount", "", "SUMX('Sales', 'Sales'[Quantity] * 'Sales'[Unit Price] * 'Sales'[Discount])"),
    ("Sales", "Margin (old)", "Kept for an old report; not used any more.", "SUM('Sales'[Unit Price]) - SUM('Sales'[Unit Cost])"),
]

_RELATIONSHIPS = [("Sales", "Customer Key", "Customers", "Customer Key"), ("Sales", "Product Key", "Products", "Product Key"),
                  ("Sales", "Store Key", "Stores", "Store Key"), ("Sales", "Order Date", "Calendar", "Date")]

# page, visual title, visual type, columns as (table, column), measures
_PAGES: list[tuple[str, list[tuple[str, str, list[tuple[str, str]], list[str]]]]] = [
    ("Overview", [
        ("Sales", "card", [], ["Sales Amount"]),
        ("Margin %", "card", [], ["Gross Margin %"]),
        ("Sales against last year", "lineChart", [("Calendar", "Month")], ["Sales Amount", "Sales PY"]),
        ("Sales by category", "barChart", [("Products", "Category")], ["Sales Amount", "Gross Margin"]),
        ("Year", "slicer", [("Calendar", "Year")], []),
    ]),
    ("Customers", [
        ("Customers by segment", "donutChart", [("Customers", "Segment")], ["Active Customers"]),
        ("Top customers", "tableEx", [("Customers", "Customer"), ("Customers", "Country")], ["Sales Amount", "Orders", "Average Order Value"]),
        ("Sales per customer", "card", [], ["Sales per Customer"]),
    ]),
    ("Targets", [
        ("Attainment by region", "barChart", [("Stores", "Region")], ["Target Attainment %"]),
        ("Sales and target", "lineChart", [("Calendar", "Month")], ["Sales Amount", "Target"]),
        ("Growth", "card", [], ["Sales YoY %"]),
    ]),
]


def _slug(text: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in text.replace("%", "pct")).strip("-")


def sample_source() -> dict[str, Any]:
    """The sample as one model JSON source: a retail model and the report built on it."""
    column_id = {(table, column): f"sample-{_slug(table)}-c-{_slug(column)}" for table, columns in _TABLES.items() for column, _ in columns}
    measure_id = {name: f"sample-m-{_slug(name)}" for _, name, _, _ in _MEASURES}
    tables = [{
        "id": f"sample-{_slug(table)}",
        "name": table,
        "columns": [{"id": column_id[(table, column)], "name": column, "dataType": data_type} for column, data_type in columns],
        "measures": [{"id": measure_id[name], "name": name, "description": description, "expression": expression}
                     for owner, name, description, expression in _MEASURES if owner == table],
    } for table, columns in _TABLES.items()]
    relationships = [{"id": f"sample-rel-{index}", "name": f"{from_table} to {to_table}", "fromTable": from_table, "fromColumn": from_column, "toTable": to_table, "toColumn": to_column}
                     for index, (from_table, from_column, to_table, to_column) in enumerate(_RELATIONSHIPS)]
    sections = [{
        "id": f"sample-page-{_slug(page)}",
        "name": page,
        "visualContainers": [{
            "id": f"sample-{_slug(page)}-v{index}",
            "name": title,
            "title": title,
            "visualType": visual_type,
            "fields": [{"objectId": column_id[field], "kind": "column"} for field in fields],
            "measures": [{"objectId": measure_id[name]} for name in measures],
        } for index, (title, visual_type, fields, measures) in enumerate(visuals)],
    } for page, visuals in _PAGES]
    return {
        "models": [{"id": "sample-retail", "name": "Retail Sales (sample)", "tables": tables, "relationships": relationships}],
        "reports": [{"id": "sample-retail-report", "name": "Retail Performance (sample)", "modelId": "sample-retail", "sections": sections}],
    }


def write_sample(folder: Path) -> Path:
    """Write the sample source into ``folder`` and return its path. Writing it again replaces it."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / SAMPLE_FILE
    path.write_text(json.dumps(sample_source(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
