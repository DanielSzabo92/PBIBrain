"""Isolated native project + real HTTP API with a realistic-sized model for UI audits.

Run from the repository root: python -m tests.ui_audit_server --port 8765
Then start Vite with BRAIN_API_URL=http://127.0.0.1:8765 (cd frontend && npx vite --port 5173)
and run lintapple / screenshots against http://localhost:5173.

Same shape as tests/graph_ui_server.py, but with several tables, ~40 measures,
relationships and two reports so dense pages render the way a real project does.
All data stays in a temporary directory, never the user's project.
"""

import argparse
import json
import tempfile
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

from backend.api.app import create_app
from backend.graph.repository import GraphRepository
from backend.projects import ProjectService


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *_args):
        pass


TABLES = {
    "Sales": [("Amount", "Double"), ("Quantity", "Int64"), ("Unit Price", "Double"), ("Discount", "Double"), ("Order Date", "DateTime"), ("Customer Key", "Int64"), ("Product Key", "Int64"), ("Region Key", "Int64")],
    "Customer": [("Customer Key", "Int64"), ("Customer Name", "String"), ("Segment", "String"), ("Country", "String")],
    "Product": [("Product Key", "Int64"), ("Product Name", "String"), ("Category", "String"), ("Subcategory", "String"), ("List Price", "Double")],
    "Region": [("Region Key", "Int64"), ("Region", "String"), ("Territory", "String")],
    "Date": [("Date", "DateTime"), ("Year", "Int64"), ("Quarter", "String"), ("Month", "String"), ("Fiscal Year", "String")],
    "Budget": [("Budget Amount", "Double"), ("Region Key", "Int64"), ("Month", "String")],
}

MEASURES = [
    ("Net Sales", "Total invoiced sales after discounts.", "SUMX('Sales', 'Sales'[Amount] - 'Sales'[Discount])"),
    ("Gross Sales", "Invoiced sales before discounts.", "SUM('Sales'[Amount])"),
    ("Total Discount", "Sum of line discounts.", "SUM('Sales'[Discount])"),
    ("Discount %", "Discount as a share of gross sales.", "DIVIDE([Total Discount], [Gross Sales])"),
    ("Units Sold", "Total quantity sold.", "SUM('Sales'[Quantity])"),
    ("Average Price", "Average realised unit price.", "DIVIDE([Net Sales], [Units Sold])"),
    ("Order Count", "Distinct orders.", "COUNTROWS('Sales')"),
    ("Customers", "Distinct buying customers.", "DISTINCTCOUNT('Sales'[Customer Key])"),
    ("Sales per Customer", "Net sales divided by buying customers.", "DIVIDE([Net Sales], [Customers])"),
    ("Sales LY", "Net sales for the same period last year.", "CALCULATE([Net Sales], SAMEPERIODLASTYEAR('Date'[Date]))"),
    ("Sales YoY", "Change in net sales versus last year.", "[Net Sales] - [Sales LY]"),
    ("Sales YoY %", "Relative change versus last year.", "DIVIDE([Sales YoY], [Sales LY])"),
    ("Sales YTD", "Year-to-date net sales.", "TOTALYTD([Net Sales], 'Date'[Date])"),
    ("Sales QTD", "Quarter-to-date net sales.", "TOTALQTD([Net Sales], 'Date'[Date])"),
    ("Sales MTD", "Month-to-date net sales.", "TOTALMTD([Net Sales], 'Date'[Date])"),
    ("Budget", "Planned sales.", "SUM('Budget'[Budget Amount])"),
    ("Budget Variance", "Net sales minus budget.", "[Net Sales] - [Budget]"),
    ("Budget Attainment %", "Net sales as a share of budget.", "DIVIDE([Net Sales], [Budget])"),
    ("Sales Target", "Twice the current sales.", "[Net Sales] * 2"),
    ("Top Product Sales", "Sales of the best-selling product.", "MAXX(VALUES('Product'[Product Name]), [Net Sales])"),
    ("Category Share", "Share of net sales within the category.", "DIVIDE([Net Sales], CALCULATE([Net Sales], ALL('Product'[Product Name])))"),
    ("Region Share", "Share of net sales within all regions.", "DIVIDE([Net Sales], CALCULATE([Net Sales], ALL('Region')))"),
    ("Rolling 12M Sales", "Net sales over the trailing twelve months.", "CALCULATE([Net Sales], DATESINPERIOD('Date'[Date], MAX('Date'[Date]), -12, MONTH))"),
    ("New Customers", "", "COUNTROWS(FILTER(VALUES('Sales'[Customer Key]), CALCULATE(MIN('Sales'[Order Date])) >= MIN('Date'[Date])))"),
    ("Returning Customers", "", "[Customers] - [New Customers]"),
    ("Margin Placeholder", "", "BLANK()"),
]

VISUALS = [
    ("Sales by region", "columnChart", [("Region", "Region")], ["Net Sales"]),
    ("Target card", "card", [], ["Sales Target"]),
    ("Sales trend", "lineChart", [("Date", "Month")], ["Net Sales", "Sales LY"]),
    ("YoY KPI", "kpi", [], ["Sales YoY %"]),
    ("Category matrix", "pivotTable", [("Product", "Category"), ("Product", "Subcategory")], ["Net Sales", "Category Share", "Units Sold"]),
    ("Customer table", "tableEx", [("Customer", "Customer Name"), ("Customer", "Segment")], ["Net Sales", "Sales per Customer"]),
    ("Budget gauge", "gauge", [], ["Budget Attainment %"]),
    ("Discount scatter", "scatterChart", [("Product", "Product Name")], ["Discount %", "Units Sold"]),
]


def slug(text):
    return "".join(ch.lower() if ch.isalnum() else "pct" if ch == "%" else "-" for ch in text).strip("-")


def build_source():
    tables = []
    for table, columns in TABLES.items():
        entry = {"id": f"{slug(table)}-table", "name": table, "columns": [
            {"id": f"{slug(table)}-{slug(name)}", "name": name, "dataType": kind} for name, kind in columns
        ], "measures": []}
        tables.append(entry)
    sales = tables[0]
    for name, description, expression in MEASURES:
        sales["measures"].append({"id": f"m-{slug(name)}", "name": name, "description": description, "expression": expression})
    relationships = [
        {"id": f"rel-{slug(dim)}", "fromTable": "Sales", "fromColumn": key, "toTable": dim, "toColumn": key, "cardinality": "manyToOne", "isActive": True}
        for dim, key in (("Customer", "Customer Key"), ("Product", "Product Key"), ("Region", "Region Key"))
    ] + [{"id": "rel-date", "fromTable": "Sales", "fromColumn": "Order Date", "toTable": "Date", "toColumn": "Date", "cardinality": "manyToOne", "isActive": True}]

    def visual(index, name, kind, fields, measures, page):
        return {
            "id": f"{page}-v{index}", "name": name, "title": name, "visualType": kind,
            "fields": [{"objectId": f"{slug(t)}-{slug(c)}", "kind": "column"} for t, c in fields],
            "measures": [{"objectId": f"m-{slug(m)}"} for m in measures],
        }

    reports = [
        {"id": "sales-report", "name": "Sales report", "modelId": "finance-model", "sections": [
            {"id": "overview-page", "name": "Overview page", "visualContainers": [visual(i, *v, "overview") for i, v in enumerate(VISUALS[:5])]},
            {"id": "detail-page", "name": "Customer detail", "visualContainers": [visual(i, *v, "detail") for i, v in enumerate(VISUALS[4:])]},
        ]},
        {"id": "exec-report", "name": "Executive summary", "modelId": "finance-model", "sections": [
            {"id": "exec-page", "name": "Scorecard", "visualContainers": [visual(i, *v, "exec") for i, v in enumerate([VISUALS[1], VISUALS[3], VISUALS[6]])]},
        ]},
    ]
    return {"models": [{"id": "finance-model", "name": "Finance model", "tables": tables, "relationships": relationships}], "reports": reports}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="pbibrain-ui-audit-") as temporary:
        folder = Path(temporary)
        source = folder / "source.json"
        source.write_text(json.dumps(build_source()), encoding="utf-8")
        project = ProjectService(folder / "brain.json")
        project.save_config({"version": 1, "name": "Contoso Finance", "sources": [str(source)], "database": "brain.lbug", "identity_map": "identity.json"})
        with GraphRepository(folder / "brain.lbug") as repository:
            project.scan(repository)
        app = create_app(database_path=folder / "brain.lbug", overrides_path=folder / "overrides.json")
        app.project = project
        app.static_dir = root / "frontend" / "dist"
        try:
            with make_server("127.0.0.1", args.port, app, handler_class=QuietHandler) as server:
                print(f"UI audit API ready at http://127.0.0.1:{args.port}", flush=True)
                server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            app.close()


if __name__ == "__main__":
    main()
