"""Write the "merge lab" fixture set into tests/fixtures/merge_lab/.

Development tool only. The set has 3 TMDL models, 2 PBIR reports, 1 TMSL
model, and 1 PBIR-Legacy report. The cases that later steps must find are
in tests/fixtures/merge_lab/EXPECTED.json.

The TOM bridge writes the TMDL files, thus they are TOM-canonical. One file
(Finance budget table) is non-canonical on purpose. Build the bridge first:
dotnet build -c Release backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.adapters.tabular_metadata import TabularMetadataAdapter  # noqa: E402

LAB = ROOT / "tests" / "fixtures" / "merge_lab"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/"
PLATFORM = "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json"


def column(name, data_type, source=None, tag=None, **extra):
    value = {"name": name, "dataType": data_type, "sourceColumn": source or name, **extra}
    if tag:
        value["lineageTag"] = tag
    return value


def measure(name, expression, tag=None, **extra):
    value = {"name": name, "expression": expression, **extra}
    if tag:
        value["lineageTag"] = tag
    return value


def m_partition(name, columns):
    # A literal M table keeps the fixture free of data source connections.
    header = ", ".join(columns)
    return {"name": name, "mode": "import", "source": {"type": "m", "expression": f"let\n    Source = #table({{{', '.join(chr(34) + item + chr(34) for item in columns)}}}, {{}})\nin\n    Source"}, "annotations": [{"name": "Columns", "value": header}]}


def date_table(*, hierarchy=None):
    table = {"name": "Date", "lineageTag": "t-date", "columns": [
        column("Date", "dateTime", tag="c-date-date"),
        column("Year", "int64", tag="c-date-year", summarizeBy="none"),
        column("Month", "string", tag="c-date-month", sortByColumn="Month Number"),
        column("Month Number", "int64", tag="c-date-month-number", summarizeBy="none", isHidden=True)],
        "partitions": [m_partition("Date", ["Date", "Year", "Month", "Month Number"])]}
    if hierarchy:
        table["hierarchies"] = [{"name": hierarchy, "lineageTag": "h-date-" + hierarchy.casefold(), "levels": [
            {"name": "Year", "ordinal": 0, "column": "Year", "lineageTag": "l-year-" + hierarchy.casefold()},
            {"name": "Month", "ordinal": 1, "column": "Month", "lineageTag": "l-month-" + hierarchy.casefold()}]}]
    return table


def sales_columns():
    return [column("Order Date", "dateTime", "OrderDate", "c-sales-order-date"),
            column("Store Key", "int64", "StoreKey", "c-sales-store-key", summarizeBy="none"),
            column("Amount", "decimal", tag="c-sales-amount"),
            column("Cost", "decimal", tag="c-sales-cost")]


def relationships(*, store=True):
    items = [{"name": "r-sales-date", "fromTable": "Sales", "fromColumn": "Order Date", "toTable": "Date", "toColumn": "Date"}]
    if store:
        items.append({"name": "r-sales-store", "fromTable": "Sales", "fromColumn": "Store Key", "toTable": "Store", "toColumn": "Store Key"})
    return items


def sales_a():
    return {"name": "SalesA", "compatibilityLevel": 1702, "model": {
        "culture": "en-US", "discourageImplicitMeasures": True,
        "tables": [
            date_table(hierarchy="Calendar"),
            {"name": "Sales", "lineageTag": "t-sales", "columns": sales_columns(), "partitions": [m_partition("Sales", ["OrderDate", "StoreKey", "Amount", "Cost"])],
             "measures": [measure("Total Sales", "SUM(Sales[Amount])", "m-total-sales", formatString="#,0"),
                          measure("Total Cost", "SUM(Sales[Cost])", "m-total-cost", formatString="#,0"),
                          measure("Margin", "[Total Sales] - [Total Cost]", "m-margin-a"),
                          measure("Sales With Tax", "AddTax([Total Sales])", "m-sales-with-tax")]},
            {"name": "Store", "lineageTag": "t-store", "columns": [
                column("Store Key", "int64", "StoreKey", "c-store-key", summarizeBy="none"),
                column("Store Name", "string", "StoreName", "c-store-name"),
                column("Region", "string", tag="c-store-region"),
                column("Manager Email", "string", "ManagerEmail", "c-store-manager-email")],
             "partitions": [m_partition("Store", ["StoreKey", "StoreName", "Region", "ManagerEmail"])]},
            {"name": "Time Intelligence", "lineageTag": "t-time-intelligence", "calculationGroup": {"precedence": 1, "calculationItems": [
                {"name": "Current", "expression": "SELECTEDMEASURE()", "ordinal": 0},
                {"name": "YTD", "expression": "CALCULATE(SELECTEDMEASURE(), DATESYTD('Date'[Date]))", "ordinal": 1},
                {"name": "Prior Year", "expression": "CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR('Date'[Date]))", "ordinal": 2}]},
             "columns": [column("Time Calculation", "string", "Name", "c-time-calculation"),
                         column("Ordinal", "int64", "Ordinal", "c-time-ordinal", isHidden=True, summarizeBy="none")],
             "partitions": [{"name": "Time Intelligence", "mode": "import", "source": {"type": "calculationGroup"}}]},
            {"name": "Metric Selector", "lineageTag": "t-metric-selector", "columns": [
                {"type": "calculatedTableColumn", "name": "Metric Selector", "dataType": "string", "sourceColumn": "[Value1]",
                 "isNameInferred": False, "lineageTag": "c-metric-selector", "sortByColumn": "Metric Selector Order", "summarizeBy": "none"},
                {"type": "calculatedTableColumn", "name": "Metric Selector Fields", "dataType": "string", "sourceColumn": "[Value2]",
                 "isNameInferred": False, "isHidden": True, "lineageTag": "c-metric-selector-fields", "summarizeBy": "none",
                 "extendedProperties": [{"type": "json", "name": "ParameterMetadata", "value": {"version": 3, "kind": 2}}]},
                {"type": "calculatedTableColumn", "name": "Metric Selector Order", "dataType": "int64", "sourceColumn": "[Value3]",
                 "isNameInferred": False, "isHidden": True, "lineageTag": "c-metric-selector-order", "summarizeBy": "none"}],
             "partitions": [{"name": "Metric Selector", "mode": "import", "source": {"type": "calculated", "expression":
                 "{\n    (\"Total Sales\", NAMEOF('Sales'[Total Sales]), 0),\n    (\"Margin\", NAMEOF('Sales'[Margin]), 1)\n}"}}]}],
        "relationships": relationships(),
        "functions": [{"name": "AddTax", "expression": "(amount : NUMERIC) => amount * 1.2", "lineageTag": "f-add-tax"}],
        "roles": [{"name": "West Region", "modelPermission": "read", "tablePermissions": [
            {"name": "Store", "filterExpression": "[Region] = \"West\"", "columnPermissions": [{"name": "Manager Email", "metadataPermission": "none"}]}]}]}}


def sales_b():
    return {"name": "SalesB", "compatibilityLevel": 1601, "model": {
        "culture": "en-US",
        "tables": [
            date_table(),
            {"name": "Sales", "lineageTag": "t-sales", "columns": sales_columns(), "partitions": [m_partition("Sales", ["OrderDate", "StoreKey", "Amount", "Cost"])],
             "measures": [measure("Sales Amount", "SUM(Sales[Amount])", "m-total-sales", formatString="#,0"),
                          measure("Margin", "DIVIDE([Sales Amount] - [Total Cost], [Sales Amount])", "m-margin-b", formatString="0.0%"),
                          measure("Orders Count", "COUNTROWS(Sales)"),
                          measure("Average Sale", "AVERAGE(Sales[Amount])", "m-duplicate-tag")]},
            {"name": "Store", "lineageTag": "t-store", "columns": [
                column("Store Key", "int64", "StoreKey", "c-store-key", summarizeBy="none"),
                column("Store Label", "string", "StoreName"),
                column("Region", "string", tag="c-store-region")],
             "partitions": [m_partition("Store", ["StoreKey", "StoreName", "Region"])]},
            {"name": "Measures", "lineageTag": "t-measures-b", "columns": [column("Placeholder", "string", tag="c-measures-placeholder", isHidden=True)],
             "partitions": [m_partition("Measures", ["Placeholder"])],
             "measures": [measure("Total Cost", "SUM(Sales[Cost])", "m-total-cost", formatString="#,0"),
                          measure("Discount Rate", "0.1", "m-duplicate-tag", formatString="0%")]}],
        "relationships": relationships()}}


def finance():
    return {"name": "Finance", "compatibilityLevel": 1600, "model": {
        "culture": "en-US",
        "tables": [
            date_table(hierarchy="Fiscal"),
            {"name": "Sales", "lineageTag": "t-sales", "columns": [column("Order Date", "dateTime", "OrderDate", "c-sales-order-date"), column("Amount", "decimal", tag="c-sales-amount")],
             # The partition uses the shared expression SalesRows (a partition to shared expression link).
             "partitions": [{"name": "Sales", "mode": "import", "source": {"type": "m", "expression": "let\n    Source = SalesRows\nin\n    Source"}}],
             "measures": [measure("Revenue", "SUM(Sales[Amount])", "m-revenue-finance", formatString="#,0"),
                          measure("Margin", "[Revenue] - [Budget]")]},
            {"name": "Budget", "lineageTag": "t-budget", "columns": [column("Month", "string", tag="c-budget-month"), column("Budget Amount", "decimal", "BudgetAmount", "c-budget-amount")],
             "partitions": [m_partition("Budget", ["Month", "BudgetAmount"])],
             "measures": [measure("Budget", "SUM(Budget[Budget Amount])", "m-budget", formatString="#,0")]}],
        "expressions": [{"name": "SalesRows", "kind": "m", "lineageTag": "e-sales-rows",
                         "expression": "let\n    Source = #table({\"OrderDate\", \"Amount\"}, {})\nin\n    Source"}],
        "relationships": relationships(store=False)}}


def legacy():
    return {"name": "Legacy", "id": "Legacy", "compatibilityLevel": 1550, "model": {
        "culture": "en-US",
        "tables": [
            date_table(),
            {"name": "Sales", "lineageTag": "t-sales", "columns": [column("Order Date", "dateTime", "OrderDate", "c-sales-order-date"), column("Amount", "decimal", tag="c-sales-amount")],
             "measures": [measure("Total Sales", "SUM(Sales[Amount])", "m-total-sales", formatString="#,0"),
                          measure("Legacy KPI", "[Total Sales] * 2", "m-legacy-kpi")]}],
        "relationships": relationships(store=False)}}


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def platform(path: Path, kind: str, name: str, logical_id: str) -> None:
    write_json(path / ".platform", {"$schema": PLATFORM, "metadata": {"type": kind, "displayName": name}, "config": {"version": "2.0", "logicalId": logical_id}})


def semantic_model(project: Path, name: str, database: dict, logical_id: str, *, tmdl: bool) -> Path:
    folder = project / (name + ".SemanticModel")
    platform(folder, "SemanticModel", name, logical_id)
    write_json(folder / "definition.pbism", {"version": "4.2", "settings": {}})
    if not tmdl:
        write_json(folder / "model.bim", database)
        return folder
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "model.bim"
        source.write_text(json.dumps(database), encoding="utf-8")
        documents = TabularMetadataAdapter().read(source, include_documents=True)["tmdl_documents"]
    for relative, text in documents.items():
        target = folder / "definition" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # The bridge returns the TOM text. Keep its line ends; write no BOM.
        target.write_bytes(text.encode("utf-8"))
    return folder


def field(kind, entity, prop):
    return {kind: {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def projection(kind, entity, prop, **extra):
    return {"field": field(kind, entity, prop), "queryRef": entity + "." + prop, "nativeQueryRef": prop, **extra}


def visual(folder: Path, version: str, name: str, visual_type: str, roles: dict, *, x: int, y: int) -> None:
    write_json(folder / name / "visual.json", {
        "$schema": SCHEMA + f"definition/visualContainer/{version}/schema.json", "name": name,
        "position": {"x": x, "y": y, "z": 0, "width": 400, "height": 240, "tabOrder": 0},
        "visual": {"visualType": visual_type, "query": {"queryState": {role: {"projections": items} for role, items in roles.items()}}, "drillFilterOtherVisuals": True}})


def report_a(project: Path) -> None:
    folder = project / "SalesA.Report"
    platform(folder, "Report", "SalesA", "00000000-0000-4000-8000-00000000a002")
    write_json(folder / "definition.pbir", {"$schema": SCHEMA + "definitionProperties/2.0.0/schema.json", "version": "4.0", "datasetReference": {"byPath": {"path": "../SalesA.SemanticModel"}}})
    definition = folder / "definition"
    write_json(definition / "version.json", {"$schema": SCHEMA + "definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    write_json(definition / "report.json", {"$schema": SCHEMA + "definition/report/3.3.0/schema.json",
        "themeCollection": {"baseTheme": {"name": "CY24SU10", "reportVersionAtImport": {"visual": "1.8.50", "report": "2.0.50", "page": "1.3.50"}, "type": "SharedResources"}}})
    write_json(definition / "reportExtensions.json", {"$schema": SCHEMA + "definition/reportExtension/1.0.0/schema.json", "name": "extension", "entities": [
        {"name": "Sales", "measures": [{"name": "Sales Target", "dataType": "Double", "expression": "[Total Sales] * 1.1",
                                        "references": {"measures": [{"entity": "Sales", "name": "Total Sales"}]}}]}]})
    write_json(definition / "pages" / "pages.json", {"$schema": SCHEMA + "definition/pagesMetadata/1.1.0/schema.json", "pageOrder": ["overview", "detail"], "activePageName": "overview"})
    for page, display in (("overview", "Overview"), ("detail", "Detail")):
        write_json(definition / "pages" / page / "page.json", {"$schema": SCHEMA + "definition/page/2.1.0/schema.json", "name": page, "displayName": display,
                                                              "displayOption": "FitToPage", "height": 720, "width": 1280})
    visuals = definition / "pages" / "overview" / "visuals"
    visual(visuals, "2.13.0", "totalsales", "card", {"Values": [projection("Measure", "Sales", "Total Sales")]}, x=0, y=0)
    visual(visuals, "2.13.0", "marginbymonth", "clusteredColumnChart",
           {"Category": [projection("Column", "Date", "Month", active=True)], "Y": [projection("Measure", "Sales", "Margin")]}, x=420, y=0)
    visual(visuals, "2.13.0", "timeslicer", "slicer", {"Values": [projection("Column", "Time Intelligence", "Time Calculation", active=True)]}, x=0, y=260)
    visual(visuals, "2.13.0", "metrictable", "tableEx",
           {"Values": [projection("Column", "Store", "Store Name"), projection("Column", "Metric Selector", "Metric Selector")]}, x=420, y=260)
    detail = definition / "pages" / "detail" / "visuals"
    visual(detail, "2.13.0", "target", "card", {"Values": [projection("Measure", "Sales", "Sales Target")]}, x=0, y=0)
    # The target card is in a visual group.
    target = json.loads((detail / "target" / "visual.json").read_text(encoding="utf-8"))
    target["parentGroupName"] = "targetgroup"
    write_json(detail / "target" / "visual.json", target)
    write_json(detail / "targetgroup" / "visual.json", {"$schema": SCHEMA + "definition/visualContainer/2.13.0/schema.json", "name": "targetgroup",
                                                        "position": {"x": 0, "y": 0, "z": 1000, "width": 400, "height": 240, "tabOrder": 1000},
                                                        "visualGroup": {"displayName": "Target group", "groupMode": "ScaleMode"}})
    # A matrix that uses the Calendar hierarchy (a visual to hierarchy link).
    level = {"HierarchyLevel": {"Expression": {"Hierarchy": {"Expression": {"SourceRef": {"Entity": "Date"}}, "Hierarchy": "Calendar"}}, "Level": "Year"}}
    visual(detail, "2.13.0", "calendarmatrix", "pivotTable",
           {"Rows": [{"field": level, "queryRef": "Date.Calendar.Year", "nativeQueryRef": "Calendar Year", "active": True}],
            "Values": [projection("Measure", "Sales", "Total Sales")]}, x=420, y=0)
    bookmarks = definition / "bookmarks"
    write_json(bookmarks / "bookmarks.json", {"$schema": SCHEMA + "definition/bookmarksMetadata/1.0.0/schema.json", "items": [{"name": "ytdview"}]})
    write_json(bookmarks / "ytdview.bookmark.json", {"$schema": SCHEMA + "definition/bookmark/2.1.0/schema.json", "name": "ytdview", "displayName": "YTD view",
                                                     "explorationState": {"version": "1.3", "activeSection": "overview",
                                                                          "filters": {"byExpr": [{"name": "regionfilter", "type": "Categorical",
                                                                                                  "expression": {"Column": {"Expression": {"SourceRef": {"Entity": "Store"}}, "Property": "Region"}}}]},
                                                                          "sections": {"overview": {"visualContainers": {"timeslicer": {}}}}},
                                                     "options": {"targetVisualNames": ["timeslicer"]}})


def report_b(project: Path) -> None:
    folder = project / "SalesB.Report"
    platform(folder, "Report", "SalesB", "00000000-0000-4000-8000-00000000b002")
    write_json(folder / "definition.pbir", {"$schema": SCHEMA + "definitionProperties/1.0.0/schema.json", "version": "4.0", "datasetReference": {"byPath": {"path": "../SalesB.SemanticModel"}}})
    definition = folder / "definition"
    write_json(definition / "version.json", {"$schema": SCHEMA + "definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    write_json(definition / "report.json", {"$schema": SCHEMA + "definition/report/2.0.0/schema.json",
        "themeCollection": {"baseTheme": {"name": "CY24SU10", "reportVersionAtImport": "5.59", "type": "SharedResources"}}})
    write_json(definition / "pages" / "pages.json", {"$schema": SCHEMA + "definition/pagesMetadata/1.0.0/schema.json", "pageOrder": ["summary"], "activePageName": "summary"})
    write_json(definition / "pages" / "summary" / "page.json", {"$schema": SCHEMA + "definition/page/2.0.0/schema.json", "name": "summary", "displayName": "Summary",
                                                               "displayOption": "FitToPage", "height": 720, "width": 1280})
    visuals = definition / "pages" / "summary" / "visuals"
    visual(visuals, "2.0.0", "salesamount", "card", {"Values": [projection("Measure", "Sales", "Sales Amount")]}, x=0, y=0)
    visual(visuals, "2.0.0", "costbystore", "clusteredBarChart",
           {"Category": [projection("Column", "Store", "Store Label", active=True)], "Y": [projection("Measure", "Measures", "Total Cost")]}, x=420, y=0)


def legacy_report(project: Path) -> None:
    folder = project / "Legacy.Report"
    platform(folder, "Report", "Legacy", "00000000-0000-4000-8000-00000000d002")
    write_json(folder / "definition.pbir", {"version": "1.0", "datasetReference": {"byPath": {"path": "../Legacy.SemanticModel"}}})
    config = {"name": "legacycard", "singleVisual": {"visualType": "card", "projections": {"Values": [{"queryRef": "Sales.Total Sales"}]},
              "prototypeQuery": {"Version": 2, "From": [{"Name": "s", "Entity": "Sales", "Type": 0}],
                                 "Select": [{"Measure": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": "Total Sales"}, "Name": "Sales.Total Sales"}]}}}
    write_json(folder / "report.json", {"config": json.dumps({"version": "5.59", "themeCollection": {"baseTheme": {"name": "CY24SU10"}}}),
        "layoutOptimization": 0, "resourcePackages": [], "sections": [{"name": "legacypage", "displayName": "Legacy page", "displayOption": 1, "ordinal": 0,
        "height": 720, "width": 1280, "config": "{}", "filters": "[]",
        "visualContainers": [{"x": 0, "y": 0, "z": 0, "width": 400, "height": 240, "config": json.dumps(config), "filters": "[]"}]}]})


def pbip(project: Path, name: str, artifacts: list[dict]) -> None:
    write_json(project / (name + ".pbip"), {"$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
                                            "version": "1.0", "artifacts": artifacts, "settings": {"enableAutoRecovery": True}})


def non_canonical(path: Path) -> None:
    # Keep the same model, but use LF line ends, a quoted name that TOM does
    # not quote, a blank line, and another property order.
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    lines = text.split("\n")
    lines[0] = lines[0].replace("table Budget", "table 'Budget'")
    tag = next(index for index, line in enumerate(lines) if line.strip().startswith("lineageTag:"))
    lines.insert(tag, "")
    path.write_bytes("\n".join(lines).encode("utf-8"))


def field_parameter_grouping(folder: Path) -> None:
    # The TOM JSON reader refuses "relatedColumnDetails", but the TMDL reader
    # accepts it. Thus add the grouping to the TMDL text and make sure that
    # the result is still TOM-canonical.
    path = folder / "definition" / "tables" / "Metric Selector.tmdl"
    anchor = "\t\tsortByColumn: 'Metric Selector Order'\r\n"
    text = path.read_bytes().decode("utf-8")
    if anchor not in text:
        raise RuntimeError("TOM changed the field parameter text")
    path.write_bytes(text.replace(anchor, anchor + "\r\n\t\trelatedColumnDetails\r\n\t\t\tgroupByColumn: 'Metric Selector Fields'\r\n").encode("utf-8"))
    canonical = TabularMetadataAdapter().read(folder / "definition", include_documents=True)["tmdl_documents"]["tables/Metric Selector.tmdl"]
    if canonical.encode("utf-8") != path.read_bytes():
        raise RuntimeError("The field parameter grouping is not TOM-canonical")


EXPECTED = {
    "schema_version": 1,
    "description": "Known merge cases in the merge lab. Model and table names are the names in each source.",
    "projects": {
        "SalesA": {"pbip": "SalesA/SalesA.pbip", "models": {"SalesA": {"path": "SalesA/SalesA.SemanticModel", "format": "TMDL"}},
                   "reports": {"SalesA": {"path": "SalesA/SalesA.Report", "format": "PBIR", "schema_versions": "current"}}},
        "SalesB": {"pbip": "SalesB/SalesB.pbip", "models": {"SalesB": {"path": "SalesB/SalesB.SemanticModel", "format": "TMDL"}},
                   "reports": {"SalesB": {"path": "SalesB/SalesB.Report", "format": "PBIR", "schema_versions": "older"}}},
        "Finance": {"pbip": "Finance/Finance.pbip", "models": {"Finance": {"path": "Finance/Finance.SemanticModel", "format": "TMDL"}}, "reports": {}},
        "Legacy": {"pbip": "Legacy/Legacy.pbip", "models": {"Legacy": {"path": "Legacy/Legacy.SemanticModel", "format": "TMSL"}},
                   "reports": {"Legacy": {"path": "Legacy/Legacy.Report", "format": "PBIR-Legacy"}}},
    },
    "known_renames": [
        {"object_type": "MEASURE", "lineage_tag": "m-total-sales",
         "from": {"model": "SalesA", "table": "Sales", "name": "Total Sales"}, "to": {"model": "SalesB", "table": "Sales", "name": "Sales Amount"}}],
    "name_clashes": [
        {"object_type": "MEASURE", "table": "Sales", "name": "Margin", "lineage_tags": {"SalesA": "m-margin-a", "SalesB": "m-margin-b", "Finance": None}}],
    "moved_measures": [
        {"lineage_tag": "m-total-cost", "name": "Total Cost", "from": {"model": "SalesA", "table": "Sales"}, "to": {"model": "SalesB", "table": "Measures"}}],
    "possible_renames": [
        {"object_type": "COLUMN", "from": {"model": "SalesA", "table": "Store", "name": "Store Name", "lineage_tag": "c-store-name"},
         "to": {"model": "SalesB", "table": "Store", "name": "Store Label", "lineage_tag": None}, "evidence": "same sourceColumn and dataType, no lineageTag on one side"},
        {"object_type": "MEASURE", "from": {"model": "SalesA", "table": "Sales", "name": "Total Sales", "lineage_tag": "m-total-sales"},
         "to": {"model": "Finance", "table": "Sales", "name": "Revenue", "lineage_tag": "m-revenue-finance"}, "evidence": "same expression, different lineageTag"}],
    "duplicate_lineage_tags": [
        {"model": "SalesB", "lineage_tag": "m-duplicate-tag", "objects": [{"table": "Sales", "name": "Average Sale"}, {"table": "Measures", "name": "Discount Rate"}]}],
    "no_lineage_tag": [
        {"model": "SalesB", "object_type": "MEASURE", "table": "Sales", "name": "Orders Count"},
        {"model": "SalesB", "object_type": "COLUMN", "table": "Store", "name": "Store Label"},
        {"model": "Finance", "object_type": "MEASURE", "table": "Sales", "name": "Margin"},
        {"model": "SalesA", "object_type": "CALCULATION_ITEM", "table": "Time Intelligence", "name": "YTD"},
        {"model": "SalesA", "object_type": "ROLE", "name": "West Region"}],
    "field_parameters": [{"model": "SalesA", "table": "Metric Selector", "fields": ["'Sales'[Total Sales]", "'Sales'[Margin]"]}],
    "calculation_groups": [{"model": "SalesA", "table": "Time Intelligence", "items": ["Current", "YTD", "Prior Year"]}],
    "functions": [{"model": "SalesA", "name": "AddTax", "lineage_tag": "f-add-tax", "used_by": [{"table": "Sales", "name": "Sales With Tax"}]}],
    "roles": [{"model": "SalesA", "name": "West Region", "rls": [{"table": "Store", "filter": "[Region] = \"West\""}],
               "ols": [{"table": "Store", "column": "Manager Email", "permission": "none"}]}],
    "hierarchies": [{"model": "SalesA", "table": "Date", "name": "Calendar", "levels": ["Year", "Month"]},
                    {"model": "Finance", "table": "Date", "name": "Fiscal", "levels": ["Year", "Month"]}],
    "bookmarks": [{"report": "SalesA", "name": "ytdview", "display_name": "YTD view", "page": "overview", "visuals": ["timeslicer"],
                   "filter_fields": [{"table": "Store", "column": "Region"}]}],
    "shared_expressions": [{"model": "Finance", "name": "SalesRows", "lineage_tag": "e-sales-rows", "used_by_partitions": [{"table": "Sales", "partition": "Sales"}]}],
    "visual_hierarchies": [{"report": "SalesA", "page": "detail", "visual": "calendarmatrix", "table": "Date", "hierarchy": "Calendar"}],
    "visual_groups": [{"report": "SalesA", "page": "detail", "group": "targetgroup", "visuals": ["target"]}],
    "report_measures": [{"report": "SalesA", "entity": "Sales", "name": "Sales Target"}],
    "non_canonical_tmdl": [{"path": "Finance/Finance.SemanticModel/definition/tables/Budget.tmdl",
                            "differences": ["LF line ends", "quoted table name", "blank line before lineageTag"]}],
    # The guarded snapshot scan reads each project without a failure. These
    # blocking items stay after S1. Each item has a reason below. When a later
    # step closes an item, remove it here.
    "guarded_scan_gaps": {
        "SalesA": ["RLS_OLS_RUNTIME_VERIFICATION_REQUIRED"],
        "SalesB": [],
        "Finance": [],
        "Legacy": ["PBIR_ACTIVE_PAGE_UNRESOLVED:Legacy.Report/definition/pages/pages.json", "PBIR_REQUIRED_ARTIFACT_MISSING:Legacy.Report/definition/pages/pages.json",
                   "PBIR_REQUIRED_ARTIFACT_MISSING:Legacy.Report/definition/report.json", "PBIR_SCHEMA_UNSUPPORTED:Legacy.Report/definition.pbir",
                   "PBIR_SCHEMA_UNSUPPORTED:Legacy.Report/report.json"],
    },
    "guarded_scan_gap_reasons": {
        "RLS_OLS_RUNTIME_VERIFICATION_REQUIRED": "The graph holds the role, its table filter, and its OLS permission. But only a query that runs as the role can prove the effect of a change on the visible data. Thus a model with roles stays blocked for the guard.",
        "Legacy": "The guarded scan certifies PBIR only. A PBIR-Legacy report fails closed.",
    },
}


def main() -> None:
    if LAB.exists():
        shutil.rmtree(LAB)
    project = LAB / "SalesA"
    folder = semantic_model(project, "SalesA", sales_a(), "00000000-0000-4000-8000-00000000a001", tmdl=True)
    field_parameter_grouping(folder)
    report_a(project)
    pbip(project, "SalesA", [{"report": {"path": "SalesA.Report"}}])
    project = LAB / "SalesB"
    semantic_model(project, "SalesB", sales_b(), "00000000-0000-4000-8000-00000000b001", tmdl=True)
    report_b(project)
    pbip(project, "SalesB", [{"report": {"path": "SalesB.Report"}}])
    project = LAB / "Finance"
    folder = semantic_model(project, "Finance", finance(), "00000000-0000-4000-8000-00000000c001", tmdl=True)
    non_canonical(folder / "definition" / "tables" / "Budget.tmdl")
    pbip(project, "Finance", [{"semanticModel": {"path": "Finance.SemanticModel"}}])
    project = LAB / "Legacy"
    semantic_model(project, "Legacy", legacy(), "00000000-0000-4000-8000-00000000d001", tmdl=False)
    legacy_report(project)
    pbip(project, "Legacy", [{"report": {"path": "Legacy.Report"}}])
    write_json(LAB / "EXPECTED.json", EXPECTED)
    print(json.dumps({"files": sum(1 for item in LAB.rglob("*") if item.is_file())}))


if __name__ == "__main__":
    main()
