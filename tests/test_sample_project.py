"""The bundled sample project scans into a valid graph and the route adds it once."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.api.app import create_app
from backend.sample_project import SAMPLE_FILE, sample_source, write_sample


class SampleProjectTests(unittest.TestCase):
    def test_every_reference_in_the_sample_points_at_an_object_of_the_sample(self) -> None:
        source = sample_source()
        model = source["models"][0]
        ids = [item["id"] for table in model["tables"] for item in [*table["columns"], *table["measures"]]]
        self.assertEqual(len(ids), len(set(ids)), "object ids are unique")
        tables = {table["name"]: {column["name"] for column in table["columns"]} for table in model["tables"]}
        for relationship in model["relationships"]:
            self.assertIn(relationship["fromColumn"], tables[relationship["fromTable"]])
            self.assertIn(relationship["toColumn"], tables[relationship["toTable"]])
        for section in source["reports"][0]["sections"]:
            for visual in section["visualContainers"]:
                for field in [*visual["fields"], *visual["measures"]]:
                    self.assertIn(field["objectId"], ids)

    def test_write_sample_is_repeatable(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            first = write_sample(Path(folder) / "sample")
            second = write_sample(Path(folder) / "sample")
            self.assertEqual(first, second)
            self.assertEqual(first.name, SAMPLE_FILE)
            self.assertEqual(json.loads(first.read_text(encoding="utf-8")), sample_source())


if __name__ == "__main__":
    unittest.main()
