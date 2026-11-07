"""A large synthetic project for MCP reply budget tests (issue #18): 500 measures, 50 pages."""

from __future__ import annotations

import json
import os
from pathlib import Path

MODEL_ID = "large-model"
REPORT_ID = "large-report"
TABLES = 10
MEASURES_PER_TABLE = 50
PAGES = 50
VISUALS_PER_PAGE = 6


def measure_id(table: int, index: int) -> str:
    return f"{MODEL_ID}-t{table}-m{index}"


def _model() -> dict:
    tables = []
    for table in range(TABLES):
        name = f"Fact {table}"
        measures = []
        for index in range(MEASURES_PER_TABLE):
            # A long, realistic DAX body: budgets must hold when expressions are big.
            previous = f"[Measure {table}-{index - 1}]" if index else f"SUM('{name}'[Amount])"
            expression = (
                f"VAR Base = CALCULATE({previous}, FILTER(ALL('{name}'), '{name}'[Amount] > {index}))\n"
                f"VAR Prior = CALCULATE(Base, DATEADD('{name}'[Date], -1, YEAR))\n"
                f"RETURN DIVIDE(Base - Prior, Prior) * 100 + [Measure {table}-0]"
            )
            measures.append({"id": measure_id(table, index), "name": f"Measure {table}-{index}", "expression": expression,
                             "description": f"Growth of measure {index} in table {table}. " * 4,
                             "displayFolder": f"Folder {index % 5}"})
        tables.append({
            "id": f"{MODEL_ID}-t{table}", "name": name,
            "columns": [{"id": f"{MODEL_ID}-t{table}-{column}", "name": column, "dataType": kind}
                        for column, kind in (("Amount", "Double"), ("Date", "DateTime"), ("Key", "Int64"))],
            "measures": measures,
        })
    return {"id": MODEL_ID, "name": "Large Model", "tables": tables}


def _report() -> dict:
    sections = []
    for page in range(PAGES):
        visuals = []
        for visual in range(VISUALS_PER_PAGE):
            table, index = (page + visual) % TABLES, (page * VISUALS_PER_PAGE + visual) % MEASURES_PER_TABLE
            visuals.append({"id": f"{REPORT_ID}-p{page}-v{visual}", "visualType": "card",
                            "measures": [{"objectId": measure_id(table, index)}, {"objectId": measure_id(table, 0)}]})
        sections.append({"id": f"{REPORT_ID}-p{page}", "name": f"Page {page}", "visualContainers": visuals})
    return {"id": REPORT_ID, "name": "Large Report", "modelId": MODEL_ID, "sections": sections}


def write_large_project(root: Path) -> Path:
    """Write the source JSON and a project config under ``root``; return the config path."""

    source = root / "sources" / "large.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(json.dumps({"models": [_model()], "reports": [_report()]}), encoding="utf-8")
    config = root / ".pbibrain" / "brain.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({
        "version": 1, "name": "Large", "sources": [os.path.relpath(source, config.parent)],
        "database": "brain.lbug", "identity_map": "identity.json",
    }), encoding="utf-8")
    return config
