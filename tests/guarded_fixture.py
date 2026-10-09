"""Valid TOM reference scenario; fixture values are not live runtime evidence."""
from pathlib import Path
import json


def reference_project(root: Path, *, report: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    model = root / "Sales.SemanticModel"
    model.mkdir()
    def write(path: Path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    write(model / ".platform", {"metadata": {"displayName": "Sales", "type": "SemanticModel"}, "config": {"logicalId": "model-sales"}})
    database = {"name": "Sales", "id": "Sales", "compatibilityLevel": 1600, "model": {"culture": "en-US", "tables": [
        {"name": "Date", "lineageTag": "table-date", "columns": [{"name": "DateKey", "dataType": "int64", "sourceColumn": "DateKey", "lineageTag": "column-date"},
            {"name": "Date", "dataType": "dateTime", "sourceColumn": "Date", "lineageTag": "column-calendar-date"},
            {"name": "CalendarMonth", "dataType": "string", "sourceColumn": "CalendarMonth", "lineageTag": "column-month"}]},
        {"name": "FactSales", "lineageTag": "table-fact", "columns": [
            {"name": "OrderDateKey", "dataType": "int64", "sourceColumn": "OrderDateKey", "lineageTag": "column-order"},
            {"name": "ShipDateKey", "dataType": "int64", "sourceColumn": "ShipDateKey", "lineageTag": "column-ship"},
            {"name": "SalesAmount", "dataType": "decimal", "sourceColumn": "SalesAmount", "lineageTag": "column-amount"}],
         "measures": [{"name": "Sales Amount", "expression": "SUM(FactSales[SalesAmount])", "lineageTag": "measure-sales"},
                      {"name": "Sales YTD", "expression": "TOTALYTD([Sales Amount], 'Date'[Date])", "lineageTag": "measure-ytd"}]}],
        "relationships": [{"name": "relationship-sales", "fromTable": "FactSales", "fromColumn": "OrderDateKey", "toTable": "Date", "toColumn": "DateKey", "isActive": True}]}}
    write(model / "model.bim", database)
    artifacts = [{"semanticModel": {"path": model.name}}]
    if report:
        report_dir = root / "Sales.Report"
        write(report_dir / ".platform", {"metadata": {"displayName": "Sales report"}, "config": {"logicalId": "report-sales"}})
        write(report_dir / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": "../Sales.SemanticModel"}}})
        write(report_dir / "definition/pages/month/page.json", {"name": "month", "displayName": "Monthly"})
        write(report_dir / "definition/pages/month/visuals/sales/visual.json", {"name": "sales", "visual": {"visualType": "lineChart", "query": {"queryState": {"Category": {"projections": [{"field": {"Column": {"Expression": {"SourceRef": {"Entity": "Date"}}, "Property": "CalendarMonth"}}}]}, "Values": {"projections": [{"field": {"Measure": {"Expression": {"SourceRef": {"Entity": "FactSales"}}, "Property": "Sales Amount"}}}]}}}}})
        artifacts.append({"report": {"path": report_dir.name}})
    project = root / "Sales.pbip"
    write(project, {"version": "1.0", "artifacts": artifacts})
    return project
