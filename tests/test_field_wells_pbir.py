"""Field wells on a real PBIR report: the visual page lists fields by where they sit in the visual.

The bundled sample records no roles, so this reads the PBIP project of the merge lab
(``tests/fixtures/merge_lab/SalesA``), whose ``visual.json`` files carry ``queryState`` roles.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from backend.api.app import create_app
from backend.projects import ProjectService

SOURCE = Path(__file__).resolve().parent / "fixtures" / "merge_lab" / "SalesA" / "SalesA.pbip"


class FieldWellsOnPbirTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        config = root / "brain.json"
        config.write_text(json.dumps({"version": 1, "name": "T", "sources": [str(SOURCE)], "database": "brain.lbug", "identity_map": "identity.json"}), encoding="utf-8")
        cls.app = create_app(database_path=root / "brain.db", overrides_path=root / "overrides.json", use_native=False)
        cls.app.project = ProjectService(config)
        status, reply = cls.app.handle("POST", "/api/scan")
        assert status == 200, reply
        _, lineage = cls.app.handle("GET", "/api/lineage")
        cls.visuals = {node["name"]: node for node in lineage["nodes"] if node["type"] == "VISUAL"}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.close()
        cls.temporary.cleanup()

    def wells(self, name: str) -> dict[str, list[str]]:
        status, reply = self.app.handle("GET", "/api/object/" + quote(self.visuals[name]["id"], safe=""))
        self.assertEqual(status, 200)
        details = reply.get("details", reply)
        return {well["label"]: [field["name"] for field in well["fields"]] for well in details["field_wells"]}

    def test_each_visual_type_names_its_wells(self) -> None:
        self.assertEqual(self.wells("marginbymonth"), {"Axis": ["Month"], "Values": ["Margin"]})
        self.assertEqual(self.wells("calendarmatrix"), {"Rows": ["Calendar"], "Values": ["Total Sales"]})
        self.assertEqual(self.wells("metrictable"), {"Values": ["Store Name", "Metric Selector"]})
        self.assertEqual(self.wells("timeslicer"), {"Slicer field": ["Time Calculation"]})
        self.assertEqual(self.wells("totalsales"), {"Values": ["Total Sales"]})

    def test_a_report_measure_counts_with_the_bound_measures(self) -> None:
        status, reply = self.app.handle("GET", "/api/object/" + quote(self.visuals["target"]["id"], safe=""))
        self.assertEqual(status, 200)
        bindings = reply.get("details", reply)["visual_bindings"]
        self.assertEqual([measure["name"] for measure in bindings["measures"]], ["Sales Target"])

    def test_a_visual_without_fields_has_no_wells(self) -> None:
        self.assertEqual(self.wells("targetgroup"), {})


if __name__ == "__main__":
    unittest.main()
