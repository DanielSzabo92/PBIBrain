"""A visual's fields are listed by the well they sit in, in the order of the report file."""

from __future__ import annotations

import unittest

from backend.api.objects import field_wells
from backend.graph.repository import GraphRepository
from backend.graph.schema import Node


class FieldWellTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = GraphRepository(use_native=False)
        for node in (Node(id="c:category", type="COLUMN", name="Category"), Node(id="m:sales", type="MEASURE", name="Sales"),
                     Node(id="c:price", type="COLUMN", name="Price")):
            self.repository.upsert_node(node)

    def _visual(self, roles) -> Node:
        return Node(id="v:1", type="VISUAL", name="Sales by category", properties={"field_roles": roles})

    def test_fields_group_by_role_with_aggregation(self) -> None:
        wells = field_wells(self.repository, self._visual([
            {"object_id": "c:category", "usage": "projection", "role": "category"},
            {"object_id": "m:sales", "usage": "projection", "role": "value"},
            {"object_id": "c:price", "usage": "projection", "role": "value", "aggregation": "Avg", "display_name": "Average price"},
            {"object_id": "m:sales", "usage": "sort", "role": "sort"},
            {"object_id": "c:gone", "usage": "projection", "role": "legend"},
        ]), None)
        self.assertEqual([(well["label"], [field["name"] for field in well["fields"]]) for well in wells],
                         [("Axis", ["Category"]), ("Values", ["Sales", "Price"])])
        self.assertEqual(wells[1]["fields"][1]["aggregation"], "Avg")
        self.assertEqual(wells[1]["fields"][1]["shown_as"], "Average price")

    def test_no_recorded_roles_gives_no_wells(self) -> None:
        self.assertEqual(field_wells(self.repository, self._visual([]), None), [])
        self.assertEqual(field_wells(self.repository, Node(id="v:2", type="VISUAL", name="V"), None), [])


if __name__ == "__main__":
    unittest.main()
