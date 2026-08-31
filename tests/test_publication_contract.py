"""Publication contracts for the repository's public documentation and license."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.license = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.gitignore = {
            line.strip()
            for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

    def test_readme_covers_the_publication_surface(self):
        required_sections = {
            "architecture": ("Power BI metadata / PBIP files", "canonical nodes", "Brain is infrastructure"),
            "trust model": ("## Trust model", "`FACT`", "`INFERRED`", "`OBSERVED`", "overrides"),
            "setup": ("## Requirements", "python -m pip install -e .", "LBUG_C_API_LIB_PATH"),
            "direct PBIP": (".pbip", "TMDL", "PBIR", "brain scan"),
            "CLI": ("brain status", "brain search", "brain object"),
            "API": ("BrainAPI", "search_objects(query)", "get_context(target, task=None)", "/api/brain"),
            "GUI": ("## Brain Inspector", "React Flow", "npm run dev"),
            "testing": ("## Verification", "unittest discover", "compileall", "npm run build"),
            "security": ("## Security and limits", "read-only", "loopback", "Credentials"),
            "license": ("## License", "MIT", "LICENSE"),
        }
        for area, phrases in required_sections.items():
            with self.subTest(area=area):
                missing = [phrase for phrase in phrases if phrase not in self.readme]
                self.assertFalse(missing, f"README missing {area} coverage: {missing}")

    def test_license_is_canonical_mit_with_project_copyright(self):
        self.assertTrue(self.license.startswith("MIT License"))
        self.assertIn("Copyright (c) 2026 Daniel", self.license)
        for phrase in (
            "Permission is hereby granted, free of charge",
            "The above copyright notice and this permission notice shall be included",
            'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND',
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.license)

    def test_gitignore_protects_local_runtime_and_private_artifacts(self):
        protected_patterns = {
            "native database": "*.lbug",
            "identity state": "config/identity.json",
            "frontend dependencies": "frontend/node_modules/",
            "frontend build": "frontend/dist/",
            "Power BI project": "*.pbip",
            "Power BI binary": "*.pbix",
            "image output": "*.png",
            "native binary": "*.dll",
            "executable": "*.exe",
        }
        for kind, pattern in protected_patterns.items():
            with self.subTest(kind=kind):
                self.assertIn(pattern, self.gitignore)


if __name__ == "__main__":
    unittest.main()
