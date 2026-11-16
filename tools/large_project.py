"""Generate a large synthetic PBIBrain project: the enterprise-size fixture of the product review.

The defaults give 8 models, 24 reports and 13,731 objects (41,942 relationships, 11,528 review
items): six different subject areas stamped from one template, plus "v2" copies of the first two
with drifted formulas, so version folding, search folding and the review patterns all have work.

    python -m tools.large_project --dir bigdata            # write the sources and brain.json
    python -m tools.large_project --dir bigdata --serve    # also scan and serve it on port 8801

The output is deterministic for a given set of sizes. ``tests/test_scale_budgets_large.py`` scans
it and holds the screens' first requests to their budgets.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

DOMAINS = ["Sales", "Finance", "Supply Chain", "HR", "Marketing", "Customer Service"]
ENTITIES = [
    "Orders", "Order Lines", "Customers", "Products", "Stores", "Calendar", "Budget", "Forecast", "Inventory", "Shipments",
    "Returns", "Employees", "Campaigns", "Tickets", "Suppliers", "GL Entries", "Cost Centers", "Currencies", "Territories",
    "Promotions", "Price Lists", "Contracts", "Invoices", "Payments", "Accounts", "Channels", "Segments", "Warehouses",
    "Routes", "Carriers",
]
COLUMNS = [
    "Key", "Code", "Name", "Description", "Amount", "Quantity", "Unit Price", "Discount %", "Created Date", "Modified Date",
    "Status", "Region", "Country", "Category", "Sub Category", "Owner", "Currency Code",
    "Net Amount (Local Currency, Excluding Tax And Freight)",
]
AGGREGATES = ["Total", "Average", "YTD", "PY", "YoY %", "MTD", "Rolling 12M", "Budget Variance", "Share of Total", "Rank by"]
PAGES = ["Executive Summary", "Trends", "Detail", "Drillthrough", "Regional Breakdown", "Customer 360", "Product Mix", "Variance Analysis"]
REPORTS = ["Executive Dashboard", "Operational Report", "Monthly Business Review", "Self-Service Explorer"]
VISUAL_TYPES = ["columnChart", "card", "tableEx", "lineChart", "slicer", "pivotTable"]
NUMERIC = {"Quantity", "Unit Price", "Discount %"}


def build(models: int = 8, tables: int = 30, measures: int = 300, reports: int = 3, pages: int = 6, visuals: int = 10, seed: int = 7) -> tuple[list[dict], list[dict]]:
    """Return ``(models, reports)`` in the JSON source format."""

    rnd = random.Random(seed)
    out_models: list[dict] = []
    out_reports: list[dict] = []
    for m in range(models):
        domain = DOMAINS[m % len(DOMAINS)]
        version = m // len(DOMAINS)
        suffix = "" if version == 0 else f" v{version + 1}"
        model_id = f"model-{m}"
        table_list: list[dict] = []
        measure_ids: list[str] = []
        column_ids: list[str] = []
        for t in range(tables):
            base = ENTITIES[t % len(ENTITIES)] + ("" if t < len(ENTITIES) else f" {t // len(ENTITIES) + 1}")
            table_id = f"{model_id}-t{t}"
            columns = []
            for c, column in enumerate(COLUMNS):
                column_id = f"{table_id}-c{c}"
                columns.append({"id": column_id, "name": column, "dataType": "Double" if "Amount" in column or column in NUMERIC else "String"})
                column_ids.append(column_id)
            table_measures: list[dict] = []
            for k in range(measures // tables):
                aggregate = AGGREGATES[k % len(AGGREGATES)]
                name = f"{aggregate} {base} Amount" + ("" if k < len(AGGREGATES) else f" {k // len(AGGREGATES) + 1}")
                if k == 0 or not measure_ids:
                    expression = f"SUM('{base}'[Amount])"
                else:
                    dependency = rnd.choice(table_measures)["name"]
                    expression = f"CALCULATE([{dependency}], DATESYTD('Calendar'[Created Date]))"
                    if version and k % 7 == 0:  # the copies drift from the original
                        expression = f"DIVIDE({expression}, 2)"
                measure_id = f"{table_id}-m{k}"
                table_measures.append({"id": measure_id, "name": name, "description": f"{aggregate} of {base.lower()} amount.", "expression": expression})
                measure_ids.append(measure_id)
            table_list.append({"id": table_id, "name": base, "columns": columns, "measures": table_measures})
        out_models.append({"id": model_id, "name": f"{domain} Analytics{suffix}", "tables": table_list})
        for r in range(reports):
            report_id = f"{model_id}-r{r}"
            sections = []
            for p in range(pages):
                containers = []
                for v in range(visuals):
                    title = f"{rnd.choice(AGGREGATES)} by {rnd.choice(COLUMNS)}"
                    containers.append({
                        "id": f"{report_id}-p{p}-v{v}", "name": title, "title": f"{rnd.choice(AGGREGATES)} by {rnd.choice(COLUMNS)}",
                        "visualType": rnd.choice(VISUAL_TYPES),
                        "fields": [{"objectId": rnd.choice(column_ids), "kind": "column"} for _ in range(rnd.randint(1, 3))],
                        "measures": [{"objectId": rnd.choice(measure_ids)} for _ in range(rnd.randint(1, 3))],
                    })
                sections.append({"id": f"{report_id}-p{p}", "name": PAGES[p % len(PAGES)] + ("" if p < len(PAGES) else f" {p // len(PAGES) + 1}"), "visualContainers": containers})
            out_reports.append({"id": report_id, "name": f"{domain} {REPORTS[r % len(REPORTS)]}{suffix}", "modelId": model_id, "sections": sections})
    return out_models, out_reports


def write_project(folder: str | Path, **sizes: int) -> Path:
    """Write one source file per model and a ``brain.json`` that lists them. Returns the config path."""

    from backend.projects import ProjectService

    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    models, reports = build(**sizes)
    sources = []
    for index, model in enumerate(models):
        source = folder / f"source{index}.json"
        source.write_text(json.dumps({"models": [model], "reports": [report for report in reports if report["modelId"] == model["id"]]}), encoding="utf-8")
        sources.append(source.name)
    config = folder / "brain.json"
    ProjectService(config).save_config({"version": 1, "name": "Contoso Enterprise BI", "sources": sources, "database": "brain.sqlite", "identity_map": "identity.json"})
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.large_project", description=__doc__.split("\n")[0])
    parser.add_argument("--dir", default="bigdata", help="folder to write the project to")
    for name, default in (("models", 8), ("tables", 30), ("measures", 300), ("reports", 3), ("pages", 6), ("visuals", 10)):
        parser.add_argument(f"--{name}", type=int, default=default)
    parser.add_argument("--serve", action="store_true", help="scan the project and serve it with the built UI")
    parser.add_argument("--port", type=int, default=8801)
    args = parser.parse_args(argv)
    config = write_project(args.dir, **{name: getattr(args, name) for name in ("models", "tables", "measures", "reports", "pages", "visuals")})
    print(f"wrote {config}", flush=True)
    if not args.serve:
        return 0

    import time

    from backend.api.app import serve
    from backend.graph.repository import GraphRepository
    from backend.projects import ProjectService

    database = config.parent / "brain.sqlite"
    if not database.exists():
        started = time.perf_counter()
        with GraphRepository(database, use_sqlite=False) as repository:
            ProjectService(config).scan(repository)
        print(f"scanned in {time.perf_counter() - started:.1f} s", flush=True)
    serve(port=args.port, database_path=database, overrides_path=config.parent / "overrides.json", use_sqlite=False,
          config_path=config, static_dir=Path(__file__).resolve().parents[1] / "frontend" / "dist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
