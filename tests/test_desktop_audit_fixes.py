"""Regression checks for the verified desktop graph/overview defects."""
import tempfile
import unittest
from pathlib import Path

from backend.api.app import get_overview
from backend.graph.repository import GraphRepository
from backend.scanner.pipeline import Scanner
from backend.validation import ValidationIssue, ValidationResult
from tests.fixtures.pbip_sources import write_pbip_project


class DesktopAuditFixes(unittest.TestCase):
    def test_standard_pbip_has_model_reference_without_invalid_containment(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            write_pbip_project(project, include_extra=True)
            with GraphRepository(use_native=False) as repository:
                for _ in range(2):
                    Scanner(repository).scan(project / "Finance.pbip")
                    nodes = {node.id: node for node in repository.all_nodes()}
                    self.assertTrue(any(edge.type == "USES_MODEL" for edge in repository.all_edges()))
                    self.assertFalse(any(edge.type == "CONTAINS" and nodes[edge.from_id].type == "MODEL"
                                         and nodes[edge.to_id].type == "REPORT" for edge in repository.all_edges()))
                    self.assertNotEqual(get_overview(repository)["validation_state"], "invalid")

    def test_overview_preserves_actionable_validation_issues_separately(self):
        with GraphRepository(use_native=False) as repository:
            repository.validation_result = ValidationResult([
                ValidationIssue("invalid_containment", "ERROR", "MODEL cannot contain REPORT",
                                object_id="report:finance", edge_id="edge:invalid")])
            overview = get_overview(repository)
            self.assertEqual(overview["validation_state"], "invalid")
            self.assertEqual(overview["validation_issues"][0]["object_id"], "report:finance")
            self.assertEqual(overview["warning_count"], 0)


if __name__ == "__main__":
    unittest.main()
