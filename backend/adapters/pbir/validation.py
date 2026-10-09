from __future__ import annotations
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any
from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

SCHEMA_ROOT = Path(__file__).parent / "schemas"
PREFIX = "https://developer.microsoft.com/json-schemas/fabric/item/report/"


@lru_cache(maxsize=1)
def _catalog():
    manifest = json.loads((SCHEMA_ROOT / "manifest.json").read_text(encoding="utf-8"))
    registry, documents = Registry(), {}
    for relative, record in sorted(manifest["files"].items()):
        path = SCHEMA_ROOT / relative
        if not path.resolve().is_relative_to(SCHEMA_ROOT.resolve()) or path.is_symlink():
            raise ValueError("Unsafe schema catalog path")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != record["sha256"]:
            raise ValueError("Schema catalog integrity mismatch")
        schema = json.loads(content)
        Draft7Validator.check_schema(schema)
        documents[record["uri"]] = schema
        registry = registry.with_resource(record["uri"], Resource.from_contents(schema, default_specification=DRAFT7))
    # Registry has no network retrieval callback. Missing references fail closed.
    return documents, registry, manifest["revision"]


def validate_report_documents(documents: dict[str, Any]) -> dict[str, Any]:
    schemas, registry, revision = _catalog()
    issues, coverage = [], []
    names = {"report.json": "report", "page.json": "page", "visual.json": "visualContainer", "pages.json": "pagesMetadata", "definition.pbir": "definitionProperties"}
    report_roots = sorted({Path(path).parts[0] for path in documents if Path(path).parts[0].casefold().endswith(".report")})
    for root in report_roots:
        for required in ("definition.pbir", "definition/report.json", "definition/pages/pages.json"):
            if root + "/" + required not in documents:
                issues.append({"code": "PBIR_REQUIRED_ARTIFACT_MISSING", "source_file": root + "/" + required})
        page_documents = {path: value for path, value in documents.items() if path.startswith(root + "/definition/pages/") and path.endswith("/page.json")}
        page_names = [value.get("name") for value in page_documents.values() if isinstance(value, dict)]
        pages_path = root + "/definition/pages/pages.json"
        metadata = documents.get(pages_path, {})
        order = metadata.get("pageOrder", []) if isinstance(metadata, dict) else []
        if len(order) != len(set(order)) or len(page_names) != len(set(page_names)) or set(order) != set(page_names):
            issues.append({"code": "PBIR_PAGE_COVERAGE_MISMATCH", "source_file": pages_path})
        if isinstance(metadata, dict) and metadata.get("activePageName") not in set(page_names):
            issues.append({"code": "PBIR_ACTIVE_PAGE_UNRESOLVED", "source_file": pages_path})
        for path, value in page_documents.items():
            if value.get("name") != Path(path).parent.name:
                issues.append({"code": "PBIR_PAGE_ID_PATH_MISMATCH", "source_file": path})
    for relative, document in sorted(documents.items()):
        path = Path(relative)
        if path.parts[0] not in report_roots or path.name == ".platform": continue
        expected = names.get(path.name)
        if expected is None:
            # Bookmarks, report extensions and custom semantic resources require
            # their own usage/schema rules; opaque JSON cannot be certified.
            if "StaticResources" not in path.parts:
                issues.append({"code": "PBIR_UNSUPPORTED_ARTIFACT", "source_file": relative})
            continue
        uri = document.get("$schema") if isinstance(document, dict) else None
        if not isinstance(uri, str) or uri not in schemas or ("/" + expected + "/") not in uri:
            issues.append({"code": "PBIR_SCHEMA_UNSUPPORTED", "source_file": relative, "schema": uri})
            continue
        errors = sorted(Draft7Validator(schemas[uri], registry=registry).iter_errors(document), key=lambda error: str(list(error.absolute_path)))
        issues.extend({"code": "PBIR_SCHEMA_INVALID", "source_file": relative, "property_path": list(error.absolute_path), "validator": error.validator} for error in errors)
        coverage.append({"source_file": relative, "schema": uri, "validated": not errors})
        # Broad schema validity is independent of extraction coverage. Unsupported
        # dynamic contexts must still block complete dependency certification.
        def visit(value, location=()):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {"NativeVisualCalculation", "VisualCalculation", "Parameter", "SelectRef", "pageBinding", "visualInteractions", "bookmarks", "Extension", "ResourcePackageItem", "SemanticQuery"}:
                        issues.append({"code": "PBIR_DYNAMIC_CONTEXT_UNSUPPORTED", "source_file": relative, "property_path": list((*location, key))})
                    if isinstance(child, (dict, list)): visit(child, (*location, key))
            elif isinstance(value, list):
                for index, child in enumerate(value): visit(child, (*location, index))
        visit(document)
    return {"status": "COMPLETE" if not issues else "INCOMPLETE", "issues": issues, "coverage": coverage, "schema_revision": revision}
