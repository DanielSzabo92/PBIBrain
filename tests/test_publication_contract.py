"""Publication contracts for the repository's public documentation and license."""

from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_REPOSITORY = "DanielSzabo92/PBIBrain"
STALE_REPOSITORY = "DanielSzabo92/" + "powerbi-brain"


def _publication_files() -> list[Path]:
    github = ROOT / ".github"
    return [
        ROOT / "README.md",
        ROOT / "LICENSE",
        ROOT / "pyproject.toml",
        ROOT / "frontend" / "package.json",
        ROOT / "frontend" / "package-lock.json",
        *sorted((ROOT / "docs").rglob("*.md")),
        *(sorted(github.rglob("*.md")) if github.is_dir() else []),
    ]


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

    def test_public_references_use_pbibrain_repository_identity(self):
        readme = self.readme.casefold()
        self.assertIn(
            f"github.com/{CANONICAL_REPOSITORY}".casefold(),
            readme,
            "README must link to the renamed PBIBrain repository",
        )

        stale = f"github.com/{STALE_REPOSITORY}".casefold()
        stale_refs = [
            path.relative_to(ROOT)
            for path in _publication_files()
            if path.is_file() and stale in path.read_text(encoding="utf-8").casefold()
        ]
        self.assertFalse(stale_refs, f"stale public repository references: {stale_refs}")

        # The import/distribution slug may remain powerbi-brain; only the public
        # repository identity is being renamed.
        self.assertIn('name = "powerbi-brain"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_git_origin_uses_pbibrain_repository_when_configured(self):
        try:
            result = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            self.skipTest(f"git unavailable: {exc}")
        remote = result.stdout.strip()
        if not remote:
            self.skipTest("no origin remote configured")
        normalized = remote.removesuffix("/").removesuffix(".git").casefold()
        expected = f"https://github.com/{CANONICAL_REPOSITORY}".casefold()
        self.assertEqual(normalized, expected)


if __name__ == "__main__":
    unittest.main()
