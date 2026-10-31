"""The CI workflow runs the 5 gates of the UI design section 10 on a Windows runner (step U0)."""

import re
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"

GATES = (
    ("Gate 1: Python unittest", "python -m unittest discover -s tests"),
    ("Gate 2: npm test", "npm test"),
    ("Gate 3: npm run build", "npm run build"),
    ("Gate 4: Playwright e2e", "npx playwright test"),
    ("Gate 5: Development Center lint", "node --test test/devcenter-lint.test.js"),
)


class CiWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_the_workflow_runs_on_each_push_and_pull_request_on_windows(self) -> None:
        self.assertRegex(self.text, r"(?m)^on:\n  push:\n  pull_request:\n")
        self.assertRegex(self.text, r"(?m)^    runs-on: windows-latest$")
        self.assertNotIn("\t", self.text)

    def test_each_gate_is_a_step_with_its_command_in_order(self) -> None:
        positions = []
        for name, command in GATES:
            with self.subTest(gate=name):
                match = re.search(rf'- name: "{re.escape(name)}"\n(?:        .*\n)*?        run: \|?\n?\s*{re.escape(command)}', self.text)
                self.assertIsNotNone(match, f"{name} must run {command}")
                positions.append(match.start())
        self.assertEqual(positions, sorted(positions))

    def test_the_e2e_gate_also_runs_the_guarded_development_spec(self) -> None:
        self.assertIn("npx playwright test -c playwright.guard.config.js", self.text)
        self.assertIn("GUARD_PYTHON: python", self.text)

    def test_the_production_build_gate_refuses_the_shim_tag(self) -> None:
        self.assertIn('Select-String -Path dist/index.html -Pattern "pywebview-shim"', self.text)

    def test_the_setup_has_the_native_runtime_and_the_bridge(self) -> None:
        for needed in ("scripts/prepare-native-runtime.ps1", "LBUG_C_API_LIB_PATH", "TabularMetadata.csproj", "npm ci", "npx playwright install chromium"):
            with self.subTest(needed=needed):
                self.assertIn(needed, self.text)


if __name__ == "__main__":
    unittest.main()
