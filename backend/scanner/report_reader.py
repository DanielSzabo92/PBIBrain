"""Power BI report source adapter."""

from __future__ import annotations

from typing import Any, Mapping

from .metadata_reader import collection, load_metadata, pick


class ReportReader:
    def read(self, source: Any) -> dict[str, Any]:
        value = load_metadata(source)
        if isinstance(value, list):
            if len(value) != 1 or not isinstance(value[0], Mapping):
                raise TypeError("ReportReader.read expects one report object")
            value = value[0]
        nested = pick(value, "report", "definition", "reportDefinition")
        if isinstance(nested, Mapping):
            return dict(nested)
        reports = collection(value, "reports")
        if len(reports) == 1 and isinstance(reports[0], Mapping):
            return dict(reports[0])
        values = pick(value, "value")
        if isinstance(values, list) and len(values) == 1 and isinstance(values[0], Mapping):
            return dict(values[0])
        return value

    def read_many(self, source: Any) -> list[dict[str, Any]]:
        value = load_metadata(source)
        if isinstance(value, list):
            return [self.read(item) for item in value if isinstance(item, Mapping)]
        reports = collection(value, "reports")
        if not reports and isinstance(pick(value, "value"), list):
            reports = pick(value, "value")
        if reports:
            return [self.read(item) for item in reports if isinstance(item, Mapping)]
        return [self.read(value)]


def read_report(source: Any) -> dict[str, Any]:
    return ReportReader().read(source)
