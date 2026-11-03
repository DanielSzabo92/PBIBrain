"""PBIR report writer for Development Center merge operations (technical design sections 8, 9.2, and 16 S7)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import shutil
from typing import Any, Iterable, Mapping, Sequence

from backend.adapters.pbir.validation import validate_report_documents
from backend.devcenter.alignment.keys import fold
from backend.devcenter.plan.fields import new_native_query_ref, new_query_ref

_REPORT_EXTENSION_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/reportExtension/1.0.0/schema.json"
)
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,50}$")
_NON_ID_CHARS = re.compile(r"[^A-Za-z0-9_-]+")

REFUSED_REASONS: dict[str, str] = {
    "bookmark_copy_not_supported": "The PBIR writer does not copy bookmarks in version 1.",
    "sync_slicer_group_not_supported": "The PBIR writer does not copy sync slicer groups in version 1.",
    "custom_visual_not_supported": "The PBIR writer does not copy custom visuals in version 1.",
    "static_resource_not_supported": "The PBIR writer does not copy static resources in version 1.",
    "destination_is_source_folder": "The destination path cannot be the baseline report folder.",
    "pbir_legacy_not_supported": "The PBIR writer does not write PBIR-Legacy reports.",
    "invalid_operation": "The report operation is not valid.",
    "schema_validation_failed": "The candidate PBIR report failed schema validation.",
}

_DATA_TYPES: dict[str, str] = {
    "binary": "Binary",
    "boolean": "Boolean",
    "bool": "Boolean",
    "date": "Date",
    "datetime": "DateTime",
    "datetimezone": "DateTimeZone",
    "decimal": "Decimal",
    "currency": "Decimal",
    "double": "Double",
    "float": "Double",
    "number": "Double",
    "duration": "Duration",
    "integer": "Integer",
    "int64": "Integer",
    "int": "Integer",
    "json": "Json",
    "none": "None",
    "null": "Null",
    "text": "Text",
    "string": "Text",
    "time": "Time",
    "variant": "Variant",
}

_STRUCTURAL_VALIDATION_CODES = {
    "PBIR_REQUIRED_ARTIFACT_MISSING",
    "PBIR_PAGE_COVERAGE_MISMATCH",
    "PBIR_ACTIVE_PAGE_UNRESOLVED",
    "PBIR_PAGE_ID_PATH_MISMATCH",
    "PBIR_UNSUPPORTED_ARTIFACT",
    "PBIR_SCHEMA_UNSUPPORTED",
    "PBIR_SCHEMA_INVALID",
}


class PBIRWriteError(ValueError):
    """Raised when the PBIR writer refuses an item or fails validation."""

    def __init__(self, code: str, message: str | None = None, details: Mapping[str, Any] | None = None) -> None:
        self.code = code
        self.message = message or REFUSED_REASONS.get(code, code)
        self.details = dict(details or {})
        super().__init__(f"{self.code}: {self.message}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise PBIRWriteError("invalid_operation", f"The file {path.name} is not valid JSON.", {"path": path.name}) from exc
    if not isinstance(data, dict):
        raise PBIRWriteError("invalid_operation", f"The file {path.name} is not a JSON object.", {"path": path.name})
    return data


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(content)


def _strip_bom_tree(root: Path) -> None:
    for file_path in root.rglob("*.json"):
        raw = file_path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            file_path.write_bytes(raw[3:])
    pbir_file = root / "definition.pbir"
    if pbir_file.is_file():
        raw = pbir_file.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            pbir_file.write_bytes(raw[3:])


def _resolve_report_dir(raw_path: str | Path) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if path.is_file() and path.name.casefold() == "definition.pbir":
        return path.parent
    if path.name == "definition" and ((path / "report.json").is_file() or (path.parent / "definition.pbir").is_file()):
        return path.parent
    return path


def _sanitize_id(raw: str, fallback: str = "item") -> str:
    cleaned = _NON_ID_CHARS.sub("_", str(raw or "").strip()).strip("_")
    if not cleaned:
        cleaned = fallback
    return cleaned[:50]


def _allocate_id(preferred: str, used_folded: set[str], fallback: str = "item") -> str:
    base = _sanitize_id(preferred, fallback=fallback)
    if fold(base) not in used_folded and _ID_PATTERN.fullmatch(base):
        used_folded.add(fold(base))
        return base
    counter = 2
    while True:
        suffix = f"_{counter}"
        stem = base[: max(1, 50 - len(suffix))]
        candidate = f"{stem}{suffix}"
        if fold(candidate) not in used_folded and _ID_PATTERN.fullmatch(candidate):
            used_folded.add(fold(candidate))
            return candidate
        counter += 1


def _unescape_pointer(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _pointer_parts(pointer: str) -> list[str]:
    if not pointer or pointer == "/":
        return []
    if not pointer.startswith("/"):
        return [_unescape_pointer(part) for part in pointer.split("/") if part]
    return [_unescape_pointer(part) for part in pointer.lstrip("/").split("/")]


def _resolve_pointer(document: Any, parts: Sequence[str]) -> Any:
    current = document
    for part in parts:
        if isinstance(current, Mapping):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, list):
            try:
                index = int(part)
            except ValueError:
                return None
            if index < 0 or index >= len(current):
                return None
            current = current[index]
        else:
            return None
    return current


def _normalize_data_type(value: Any) -> str:
    if isinstance(value, str):
        mapped = _DATA_TYPES.get(value.strip().casefold())
        if mapped is not None:
            return mapped
        if value in _DATA_TYPES.values():
            return value
    return "Double"


def _donor_custom_visuals(donor_dir: Path | None) -> set[str]:
    if donor_dir is None:
        return set()
    custom: set[str] = set()
    report_path = donor_dir / "definition" / "report.json"
    if report_path.is_file():
        report_doc = _read_json(report_path)
        for key in ("publicCustomVisuals", "organizationCustomVisuals"):
            values = report_doc.get(key)
            if isinstance(values, list):
                custom.update(str(item) for item in values if isinstance(item, str) and item)
        for pkg in report_doc.get("resourcePackages") or []:
            if not isinstance(pkg, Mapping):
                continue
            pkg_type = str(pkg.get("type") or "")
            if pkg_type in {"CustomVisual", "OrganizationalStoreCustomVisual"} or "CustomVisual" in pkg_type:
                if isinstance(pkg.get("name"), str) and pkg["name"]:
                    custom.add(pkg["name"])
                for item in pkg.get("items") or []:
                    if isinstance(item, Mapping):
                        if isinstance(item.get("name"), str) and item["name"]:
                            custom.add(item["name"])
                        if isinstance(item.get("path"), str) and item["path"]:
                            custom.add(Path(item["path"]).parts[0])
    for rel in ("StaticResources/CustomVisuals", "definition/StaticResources/CustomVisuals"):
        cv_root = donor_dir / rel
        if cv_root.is_dir():
            for child in cv_root.iterdir():
                if child.is_dir():
                    custom.add(child.name)
    return custom


def _has_static_resource(node: Any) -> bool:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == "ResourcePackageItem":
                if isinstance(value, Mapping):
                    pkg_name = str(value.get("PackageName") or "")
                    if pkg_name and pkg_name != "SharedResources":
                        return True
                    if not pkg_name:
                        return True
                else:
                    return True
            if key in {"registeredResources", "staticResources"} and value:
                return True
            if key == "type" and value in {"RegisteredResources", "StaticResources"}:
                return True
            if _has_static_resource(value):
                return True
    elif isinstance(node, list):
        return any(_has_static_resource(item) for item in node)
    return False


def _check_refused_operation(operation: Mapping[str, Any]) -> None:
    op = str(operation.get("op") or "").upper()
    obj_type = str(operation.get("object_type") or "").lower()
    subtype = str(operation.get("subtype") or "").lower()
    key = str(operation.get("source_key") or operation.get("row_key") or "").lower()

    if (
        op in {"COPY_BOOKMARK", "CREATE_BOOKMARK", "REPLACE_BOOKMARK"}
        or obj_type == "bookmark"
        or subtype == "bookmark"
        or key.startswith("bookmark:")
        or bool(operation.get("copy_bookmarks"))
    ):
        raise PBIRWriteError("bookmark_copy_not_supported", details={"op": op, "row_key": operation.get("row_key")})

    if (
        op in {"COPY_SYNC_GROUP", "SET_SYNC_GROUP"}
        or obj_type in {"sync_slicer_group", "sync_group"}
        or subtype in {"sync_slicer_group", "sync_group"}
        or bool(operation.get("sync_group"))
    ):
        raise PBIRWriteError("sync_slicer_group_not_supported", details={"op": op, "row_key": operation.get("row_key")})

    if (
        op in {"COPY_CUSTOM_VISUAL", "CREATE_CUSTOM_VISUAL"}
        or obj_type == "custom_visual"
        or subtype == "custom_visual"
        or bool(operation.get("custom_visual"))
    ):
        raise PBIRWriteError("custom_visual_not_supported", details={"op": op, "row_key": operation.get("row_key")})

    if (
        op in {"COPY_STATIC_RESOURCE", "COPY_RESOURCE", "CREATE_STATIC_RESOURCE"}
        or obj_type in {"static_resource", "resource_package"}
        or subtype in {"static_resource", "resource_package"}
        or bool(operation.get("static_resource"))
    ):
        raise PBIRWriteError("static_resource_not_supported", details={"op": op, "row_key": operation.get("row_key")})


def _check_refused_page(page_doc: Mapping[str, Any]) -> None:
    if _has_static_resource(page_doc):
        raise PBIRWriteError("static_resource_not_supported", details={"page": page_doc.get("name")})


def _check_refused_visual(
    visual_doc: Mapping[str, Any],
    donor_dir: Path | None,
    custom_visuals: set[str],
) -> None:
    visual_inner = visual_doc.get("visual") if isinstance(visual_doc.get("visual"), Mapping) else {}
    if visual_inner.get("syncGroup") is not None or visual_doc.get("syncGroup") is not None:
        raise PBIRWriteError("sync_slicer_group_not_supported", details={"visual": visual_doc.get("name")})

    visual_type = visual_inner.get("visualType") or visual_doc.get("visualType")
    if visual_doc.get("isCustomVisual") is True or visual_inner.get("isCustomVisual") is True:
        raise PBIRWriteError("custom_visual_not_supported", details={"visual": visual_doc.get("name"), "visual_type": visual_type})
    if isinstance(visual_type, str) and visual_type in custom_visuals:
        raise PBIRWriteError("custom_visual_not_supported", details={"visual": visual_doc.get("name"), "visual_type": visual_type})

    if _has_static_resource(visual_doc):
        raise PBIRWriteError("static_resource_not_supported", details={"visual": visual_doc.get("name")})


class PBIRWriter:
    """Applies report operations to a baseline PBIR folder and writes a validated candidate folder."""

    def __init__(
        self,
        baseline_path: str | Path,
        candidate_path: str | Path,
        *,
        donor_paths: Mapping[str, str | Path] | str | Path | None = None,
    ) -> None:
        self.baseline_dir = _resolve_report_dir(baseline_path)
        self.candidate_dir = Path(candidate_path).expanduser().resolve()
        if (
            self.candidate_dir == self.baseline_dir
            or self.candidate_dir.is_relative_to(self.baseline_dir)
            or self.baseline_dir.is_relative_to(self.candidate_dir)
        ):
            raise PBIRWriteError(
                "destination_is_source_folder",
                REFUSED_REASONS["destination_is_source_folder"],
                {"reason": "destination_is_definition_folder"},
            )
        if (self.baseline_dir / "report.json").is_file() and not (self.baseline_dir / "definition" / "report.json").is_file():
            raise PBIRWriteError("pbir_legacy_not_supported")
        if not (self.baseline_dir / "definition" / "report.json").is_file():
            raise PBIRWriteError(
                "invalid_operation",
                "The baseline report folder does not contain definition/report.json.",
            )

        self.donors: dict[str, Path] = {}
        self.default_donor: Path | None = None
        if isinstance(donor_paths, (str, Path)):
            resolved = _resolve_report_dir(donor_paths)
            self._check_donor_format(resolved)
            self.default_donor = resolved
        elif isinstance(donor_paths, Mapping):
            for source_id, raw in donor_paths.items():
                if raw is None:
                    continue
                resolved = _resolve_report_dir(raw)
                self._check_donor_format(resolved)
                self.donors[str(source_id)] = resolved
                if self.default_donor is None:
                    self.default_donor = resolved

        self.page_name_map: dict[str, str] = {}
        self.visual_name_map: dict[str, str] = {}
        self.visual_page_map: dict[tuple[str, str], str] = {}
        self.binding_name_map: dict[str, str] = {}
        self._page_row_map: dict[str, str] = {}
        self._visual_row_map: dict[str, tuple[str, str]] = {}
        self._copied_page_visuals: dict[tuple[str | None, str, str], tuple[str, str]] = {}
        self._touched_pages: set[str] = set()
        self._page_visual_maps: dict[str, dict[str, str]] = {}

    @staticmethod
    def _check_donor_format(donor_dir: Path) -> None:
        if (donor_dir / "report.json").is_file() and not (donor_dir / "definition" / "report.json").is_file():
            raise PBIRWriteError("pbir_legacy_not_supported")

    def _donor_for(self, operation: Mapping[str, Any]) -> Path:
        raw_path = operation.get("donor_path") or operation.get("source_path")
        if isinstance(raw_path, (str, Path)):
            resolved = _resolve_report_dir(raw_path)
            self._check_donor_format(resolved)
            return resolved
        source_id = str(operation.get("source_id") or "")
        if source_id and source_id in self.donors:
            return self.donors[source_id]
        if self.default_donor is not None:
            return self.default_donor
        return self.baseline_dir

    def _prepare_candidate(self) -> None:
        if self.candidate_dir.exists():
            shutil.rmtree(self.candidate_dir)
        self.candidate_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            self.baseline_dir,
            self.candidate_dir,
            ignore=shutil.ignore_patterns(".pbi", ".pbibrain", "mobile.json", "mobileState.json"),
        )
        _strip_bom_tree(self.candidate_dir)

    def _existing_page_ids(self) -> set[str]:
        pages_dir = self.candidate_dir / "definition" / "pages"
        ids: set[str] = set()
        if pages_dir.is_dir():
            for page_file in pages_dir.glob("*/page.json"):
                ids.add(fold(page_file.parent.name))
                doc = _read_json(page_file)
                if isinstance(doc.get("name"), str):
                    ids.add(fold(doc["name"]))
        pages_meta = pages_dir / "pages.json"
        if pages_meta.is_file():
            meta = _read_json(pages_meta)
            for item in meta.get("pageOrder") or []:
                if isinstance(item, str):
                    ids.add(fold(item))
        return ids

    def _existing_visual_ids(self, *, exclude_page: str | None = None) -> set[str]:
        pages_dir = self.candidate_dir / "definition" / "pages"
        ids: set[str] = set()
        if not pages_dir.is_dir():
            return ids
        for visual_file in pages_dir.glob("*/visuals/*/visual.json"):
            page_name = visual_file.parent.parent.parent.name
            if exclude_page is not None and fold(page_name) == fold(exclude_page):
                continue
            ids.add(fold(visual_file.parent.name))
            doc = _read_json(visual_file)
            if isinstance(doc.get("name"), str):
                ids.add(fold(doc["name"]))
        return ids

    def _existing_binding_metadata(self, *, exclude_page: str | None = None) -> tuple[set[str], set[str], set[str]]:
        pages_dir = self.candidate_dir / "definition" / "pages"
        binding_names: set[str] = set()
        param_names: set[str] = set()
        filter_names: set[str] = set()
        if not pages_dir.is_dir():
            return binding_names, param_names, filter_names
        for page_file in pages_dir.glob("*/page.json"):
            if exclude_page is not None and fold(page_file.parent.name) == fold(exclude_page):
                continue
            doc = _read_json(page_file)
            binding = doc.get("pageBinding")
            if isinstance(binding, Mapping):
                if isinstance(binding.get("name"), str):
                    binding_names.add(fold(binding["name"]))
                for param in binding.get("parameters") or []:
                    if isinstance(param, Mapping) and isinstance(param.get("name"), str):
                        param_names.add(fold(param["name"]))
            filter_config = doc.get("filterConfig")
            if isinstance(filter_config, Mapping):
                for item in filter_config.get("filters") or []:
                    if isinstance(item, Mapping) and isinstance(item.get("name"), str):
                        filter_names.add(fold(item["name"]))
        return binding_names, param_names, filter_names

    # Operations ---------------------------------------------------------------------

    def write(self, operations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        for operation in operations:
            _check_refused_operation(operation)

        self._prepare_candidate()

        for operation in operations:
            domain = operation.get("domain")
            if domain is not None and str(domain).lower() != "report":
                continue
            self._apply_operation(operation)

        self._finalize_touched_pages()
        validation = self._validate_candidate()
        changed, added, removed = self._diff_files()

        return {
            "status": "ok",
            "baseline_path": str(self.baseline_dir),
            "candidate_path": str(self.candidate_dir),
            "changed_files": changed,
            "added_files": added,
            "removed_files": removed,
            "page_name_map": dict(self.page_name_map),
            "visual_name_map": dict(self.visual_name_map),
            "visual_page_map": {f"{page}/{old}": new for (page, old), new in self.visual_page_map.items()},
            "binding_name_map": dict(self.binding_name_map),
            "validation": validation,
        }

    def _apply_operation(self, operation: Mapping[str, Any]) -> None:
        op = str(operation.get("op") or "").upper()
        if op == "COPY_PAGE":
            self._op_copy_page(operation)
        elif op == "COPY_VISUAL":
            self._op_copy_visual(operation)
        elif op == "DELETE_PAGE":
            self._op_delete_page(operation)
        elif op == "DELETE_VISUAL":
            self._op_delete_visual(operation)
        elif op == "REBIND_FIELD":
            self._op_rebind_field(operation)
        elif op == "REMOVE_FIELD":
            self._op_remove_field(operation)
        elif op in {"CREATE_REPORT_MEASURE", "REPLACE_REPORT_MEASURE"}:
            self._op_upsert_report_measure(operation, create_only=(op == "CREATE_REPORT_MEASURE"))
        elif op == "DELETE_REPORT_MEASURE":
            self._op_delete_report_measure(operation)
        elif op == "REWRITE_EXPRESSION":
            self._op_rewrite_expression(operation)
        elif op in {"RENAME", "RENAME_PAIR"}:
            self._op_rename_report_object(operation)
        elif op in {"SET_PROPERTIES", "REPLACE"}:
            self._op_set_properties(operation)
        elif op in {"REBIND_REPORT", "SET_DATASET_REFERENCE"}:
            self._op_rebind_dataset(operation)
        else:
            raise PBIRWriteError("invalid_operation", f"Unsupported report operation: {op}.", {"op": op})

    def _op_copy_page(self, operation: Mapping[str, Any]) -> None:
        donor_dir = self._donor_for(operation)
        custom_visuals = _donor_custom_visuals(donor_dir)
        source_key = str(operation.get("source_key") or "")
        donor_page_id = (
            source_key.split(":", 1)[1]
            if source_key.startswith("page:")
            else str(operation.get("donor_page_id") or operation.get("page_id") or operation.get("name") or "")
        )
        if not donor_page_id:
            raise PBIRWriteError("invalid_operation", "COPY_PAGE requires a donor page identifier.")

        donor_page_dir = donor_dir / "definition" / "pages" / donor_page_id
        donor_page_file = donor_page_dir / "page.json"
        if not donor_page_file.is_file():
            raise PBIRWriteError(
                "invalid_operation",
                f"The donor page {donor_page_id} does not exist.",
                {"page_id": donor_page_id},
            )

        page_doc = copy.deepcopy(_read_json(donor_page_file))
        _check_refused_page(page_doc)

        donor_visuals: list[tuple[str, dict[str, Any]]] = []
        for visual_file in sorted(donor_page_dir.glob("visuals/*/visual.json")):
            v_doc = copy.deepcopy(_read_json(visual_file))
            _check_refused_visual(v_doc, donor_dir, custom_visuals)
            old_v_id = str(v_doc.get("name") or visual_file.parent.name)
            donor_visuals.append((old_v_id, v_doc))

        replace = bool(operation.get("replace"))
        requested_page_id = str(operation.get("new_page_id") or operation.get("target_page_id") or "")
        if replace:
            target_page_id = str(operation.get("target_page_id") or operation.get("page_id") or donor_page_id)
            final_page_id = target_page_id
            existing_target_dir = self.candidate_dir / "definition" / "pages" / final_page_id
            if existing_target_dir.is_dir():
                shutil.rmtree(existing_target_dir)
            used_visual_ids = self._existing_visual_ids(exclude_page=final_page_id)
            binding_names, param_names, filter_names = self._existing_binding_metadata(exclude_page=final_page_id)
        else:
            used_page_ids = self._existing_page_ids()
            preferred_id = requested_page_id or donor_page_id
            final_page_id = _allocate_id(preferred_id, used_page_ids, fallback="page")
            used_visual_ids = self._existing_visual_ids()
            binding_names, param_names, filter_names = self._existing_binding_metadata()

        self.page_name_map[donor_page_id] = final_page_id
        row_key = str(operation.get("row_key") or "")
        if row_key:
            self._page_row_map[row_key] = final_page_id
            self._page_row_map[row_key.split("@", 1)[0]] = final_page_id
        self._page_row_map[f"page:{donor_page_id}"] = final_page_id

        page_doc["name"] = final_page_id
        new_display_name = operation.get("new_name") or operation.get("display_name")
        if isinstance(new_display_name, str) and new_display_name.strip():
            page_doc["displayName"] = new_display_name.strip()
        elif isinstance(operation.get("name"), str) and operation["name"].strip():
            op_name = operation["name"].strip()
            if op_name != donor_page_id:
                page_doc["displayName"] = op_name

        self._fix_page_binding_and_filters(
            page_doc,
            old_page_id=donor_page_id,
            final_page_id=final_page_id,
            binding_names=binding_names,
            param_names=param_names,
            filter_names=filter_names,
        )

        page_visual_map: dict[str, str] = {}
        prepared_visuals: list[tuple[str, dict[str, Any]]] = []
        source_id = str(operation.get("source_id") or "") or None
        for old_v_id, v_doc in donor_visuals:
            final_v_id = _allocate_id(old_v_id, used_visual_ids, fallback="visual")
            page_visual_map[old_v_id] = final_v_id
            self.visual_name_map[old_v_id] = final_v_id
            self.visual_page_map[(final_page_id, old_v_id)] = final_v_id
            self._copied_page_visuals[(source_id, donor_page_id, old_v_id)] = (final_page_id, final_v_id)
            self._copied_page_visuals[(None, donor_page_id, old_v_id)] = (final_page_id, final_v_id)
            self._visual_row_map[f"visual:{donor_page_id}/{old_v_id}"] = (final_page_id, final_v_id)
            v_doc["name"] = final_v_id
            prepared_visuals.append((final_v_id, v_doc))

        self._page_visual_maps.setdefault(final_page_id, {}).update(page_visual_map)
        self._touched_pages.add(final_page_id)

        target_page_dir = self.candidate_dir / "definition" / "pages" / final_page_id
        _write_json(target_page_dir / "page.json", page_doc)
        for final_v_id, v_doc in prepared_visuals:
            _write_json(target_page_dir / "visuals" / final_v_id / "visual.json", v_doc)

        self._add_page_to_pages_json(final_page_id)

    def _fix_page_binding_and_filters(
        self,
        page_doc: dict[str, Any],
        *,
        old_page_id: str,
        final_page_id: str,
        binding_names: set[str],
        param_names: set[str],
        filter_names: set[str],
    ) -> None:
        filter_map: dict[str, str] = {}
        filter_config = page_doc.get("filterConfig")
        if isinstance(filter_config, Mapping) and isinstance(filter_config.get("filters"), list):
            for filter_item in filter_config["filters"]:
                if not isinstance(filter_item, dict):
                    continue
                old_f_name = filter_item.get("name")
                if isinstance(old_f_name, str) and old_f_name:
                    preferred_f = final_page_id if old_f_name == old_page_id else old_f_name
                    new_f_name = _allocate_id(preferred_f, filter_names, fallback="filter")
                    filter_map[old_f_name] = new_f_name
                    filter_item["name"] = new_f_name

        binding = page_doc.get("pageBinding")
        if not isinstance(binding, dict):
            return

        old_b_name = str(binding.get("name") or old_page_id)
        preferred_b = final_page_id if old_b_name == old_page_id else old_b_name
        new_b_name = _allocate_id(preferred_b, binding_names, fallback="binding")
        self.binding_name_map[old_b_name] = new_b_name
        binding["name"] = new_b_name

        params = binding.get("parameters")
        if isinstance(params, list):
            for param in params:
                if not isinstance(param, dict):
                    continue
                old_p_name = str(param.get("name") or "param")
                new_p_name = _allocate_id(old_p_name, param_names, fallback="param")
                param["name"] = new_p_name
                bound = param.get("boundFilter")
                if isinstance(bound, str) and bound:
                    if bound in filter_map:
                        param["boundFilter"] = filter_map[bound]
                    elif isinstance(filter_config, Mapping) and isinstance(filter_config.get("filters"), list):
                        matching = self._find_matching_filter_name(param.get("fieldExpr"), filter_config["filters"])
                        if matching is not None:
                            param["boundFilter"] = matching

    @staticmethod
    def _find_matching_filter_name(field_expr: Any, filters: Sequence[Any]) -> str | None:
        if not isinstance(field_expr, Mapping):
            return None
        for item in filters:
            if isinstance(item, Mapping) and item.get("field") == field_expr and isinstance(item.get("name"), str):
                return item["name"]
        return None

    def _add_page_to_pages_json(self, page_id: str) -> None:
        pages_meta_path = self.candidate_dir / "definition" / "pages" / "pages.json"
        meta = _read_json(pages_meta_path)
        order = list(meta.get("pageOrder") or [])
        if page_id not in order:
            order.append(page_id)
        meta["pageOrder"] = order
        if not meta.get("activePageName") or meta.get("activePageName") not in order:
            meta["activePageName"] = order[0]
        _write_json(pages_meta_path, meta)

    def _op_copy_visual(self, operation: Mapping[str, Any]) -> None:
        donor_dir = self._donor_for(operation)
        custom_visuals = _donor_custom_visuals(donor_dir)
        source_key = str(operation.get("source_key") or "")
        donor_page_id = ""
        donor_visual_id = ""
        if source_key.startswith("visual:") and "/" in source_key:
            rest = source_key.split(":", 1)[1]
            donor_page_id, donor_visual_id = rest.split("/", 1)
        if not donor_page_id:
            donor_page_id = str(operation.get("donor_page_id") or operation.get("page_id") or "")
        if not donor_visual_id:
            donor_visual_id = str(operation.get("visual_id") or operation.get("name") or "")

        row_key = str(operation.get("row_key") or "")
        source_id = str(operation.get("source_id") or "") or None

        target_page_raw = str(operation.get("target_page_id") or operation.get("page_id") or donor_page_id)
        target_page_id = (
            self._page_row_map.get(target_page_raw)
            or self.page_name_map.get(target_page_raw)
            or target_page_raw
        )

        already = (
            self._copied_page_visuals.get((source_id, donor_page_id, donor_visual_id))
            or self._copied_page_visuals.get((None, donor_page_id, donor_visual_id))
        )
        if already is not None and already[0] == target_page_id and not row_key.endswith("#new"):
            if row_key:
                self._visual_row_map[row_key] = already
                self._visual_row_map[row_key.split("@", 1)[0]] = already
            return

        donor_visual_file = donor_dir / "definition" / "pages" / donor_page_id / "visuals" / donor_visual_id / "visual.json"
        if not donor_visual_file.is_file():
            raise PBIRWriteError(
                "invalid_operation",
                f"The donor visual {donor_page_id}/{donor_visual_id} does not exist.",
                {"page_id": donor_page_id, "visual_id": donor_visual_id},
            )

        target_page_dir = self.candidate_dir / "definition" / "pages" / target_page_id
        if not (target_page_dir / "page.json").is_file():
            raise PBIRWriteError(
                "invalid_operation",
                f"The target page {target_page_id} does not exist.",
                {"page_id": target_page_id},
            )

        v_doc = copy.deepcopy(_read_json(donor_visual_file))
        _check_refused_visual(v_doc, donor_dir, custom_visuals)

        preferred_v_id = str(operation.get("new_visual_id") or operation.get("new_name") or donor_visual_id)
        used_visual_ids = self._existing_visual_ids()
        final_v_id = _allocate_id(preferred_v_id, used_visual_ids, fallback="visual")

        v_doc["name"] = final_v_id
        self.visual_name_map[donor_visual_id] = final_v_id
        self.visual_page_map[(target_page_id, donor_visual_id)] = final_v_id
        self._page_visual_maps.setdefault(target_page_id, {})[donor_visual_id] = final_v_id
        if row_key:
            self._visual_row_map[row_key] = (target_page_id, final_v_id)
            self._visual_row_map[row_key.split("@", 1)[0]] = (target_page_id, final_v_id)
        self._visual_row_map[f"visual:{donor_page_id}/{donor_visual_id}"] = (target_page_id, final_v_id)
        self._visual_row_map[f"visual:{target_page_id}/{final_v_id}"] = (target_page_id, final_v_id)

        _write_json(target_page_dir / "visuals" / final_v_id / "visual.json", v_doc)
        self._touched_pages.add(target_page_id)

    def _op_delete_page(self, operation: Mapping[str, Any]) -> None:
        row_key = str(operation.get("row_key") or "")
        page_id = str(operation.get("page_id") or "")
        if not page_id and row_key.startswith("page:"):
            page_id = row_key.split(":", 1)[1].split("@", 1)[0]
        if not page_id:
            page_id = self._find_page_by_name_or_id(str(operation.get("name") or ""))
        if not page_id:
            raise PBIRWriteError("invalid_operation", "DELETE_PAGE could not resolve the target page.")

        page_dir = self.candidate_dir / "definition" / "pages" / page_id
        if page_dir.is_dir():
            shutil.rmtree(page_dir)
        self._touched_pages.discard(page_id)

        pages_meta_path = self.candidate_dir / "definition" / "pages" / "pages.json"
        if pages_meta_path.is_file():
            meta = _read_json(pages_meta_path)
            order = [item for item in (meta.get("pageOrder") or []) if item != page_id]
            meta["pageOrder"] = order
            if meta.get("activePageName") == page_id:
                meta["activePageName"] = order[0] if order else ""
            _write_json(pages_meta_path, meta)

    def _find_page_by_name_or_id(self, name: str) -> str:
        if not name:
            return ""
        pages_dir = self.candidate_dir / "definition" / "pages"
        if (pages_dir / name / "page.json").is_file():
            return name
        for page_file in sorted(pages_dir.glob("*/page.json")):
            doc = _read_json(page_file)
            if fold(str(doc.get("name") or "")) == fold(name) or fold(str(doc.get("displayName") or "")) == fold(name):
                return page_file.parent.name
        return ""

    def _op_delete_visual(self, operation: Mapping[str, Any]) -> None:
        page_id, visual_id = self._resolve_visual_target(operation)
        visual_dir = self.candidate_dir / "definition" / "pages" / page_id / "visuals" / visual_id
        if visual_dir.is_dir():
            shutil.rmtree(visual_dir)
        self._touched_pages.add(page_id)

    def _resolve_visual_target(self, operation: Mapping[str, Any]) -> tuple[str, str]:
        row_key = str(operation.get("row_key") or "")
        if row_key in self._visual_row_map:
            return self._visual_row_map[row_key]
        stripped_key = row_key.split("@", 1)[0].split("#", 1)[0]
        if stripped_key in self._visual_row_map:
            return self._visual_row_map[stripped_key]

        page_id = str(operation.get("page_id") or "")
        visual_id = str(operation.get("visual_id") or "")
        if stripped_key.startswith("visual:") and "/" in stripped_key:
            rest = stripped_key.split(":", 1)[1]
            key_page, key_visual = rest.split("/", 1)
            page_id = page_id or key_page
            visual_id = visual_id or key_visual
        if not visual_id and isinstance(operation.get("name"), str):
            visual_id = operation["name"]

        mapped_page = self._page_row_map.get(page_id) or self.page_name_map.get(page_id) or page_id
        mapped_visual = self.visual_page_map.get((mapped_page, visual_id)) or visual_id
        if mapped_page and mapped_visual:
            candidate_file = self.candidate_dir / "definition" / "pages" / mapped_page / "visuals" / mapped_visual / "visual.json"
            if candidate_file.is_file():
                return mapped_page, mapped_visual
            orig_file = self.candidate_dir / "definition" / "pages" / page_id / "visuals" / visual_id / "visual.json"
            if orig_file.is_file():
                return page_id, visual_id

        if visual_id:
            pages_dir = self.candidate_dir / "definition" / "pages"
            for v_file in sorted(pages_dir.glob(f"*/visuals/{visual_id}/visual.json")):
                return v_file.parent.parent.parent.name, visual_id

        raise PBIRWriteError(
            "invalid_operation",
            "Could not resolve the target visual for the report operation.",
            {"row_key": row_key, "page_id": page_id, "visual_id": visual_id},
        )

    def _resolve_page_target(self, operation: Mapping[str, Any]) -> str:
        row_key = str(operation.get("row_key") or "")
        if row_key in self._page_row_map:
            return self._page_row_map[row_key]
        stripped = row_key.split("@", 1)[0].split("#", 1)[0]
        if stripped in self._page_row_map:
            return self._page_row_map[stripped]
        page_id = str(operation.get("page_id") or "")
        if not page_id and stripped.startswith("page:"):
            page_id = stripped.split(":", 1)[1]
        if not page_id and isinstance(operation.get("name"), str):
            page_id = self._find_page_by_name_or_id(operation["name"])
        page_id = self.page_name_map.get(page_id, page_id)
        if page_id and (self.candidate_dir / "definition" / "pages" / page_id / "page.json").is_file():
            return page_id
        raise PBIRWriteError("invalid_operation", "Could not resolve the target page for the report operation.", {"row_key": row_key})

    # Field Rebinding and Removal ----------------------------------------------------

    def _op_rebind_field(self, operation: Mapping[str, Any]) -> None:
        old_spec = operation.get("old") if isinstance(operation.get("old"), Mapping) else {}
        new_spec = operation.get("new") if isinstance(operation.get("new"), Mapping) else {}
        old_entity = str(old_spec.get("entity") or operation.get("old_entity") or "")
        old_prop = str(old_spec.get("property") or operation.get("old_property") or "")
        new_entity = str(new_spec.get("entity") or operation.get("new_entity") or old_entity)
        new_prop = str(new_spec.get("property") or operation.get("new_property") or old_prop)
        old_kind = str(old_spec.get("kind") or operation.get("old_kind") or "").lower()
        new_kind = str(new_spec.get("kind") or operation.get("new_kind") or old_kind).lower()
        old_level = old_spec.get("level")
        new_level = new_spec.get("level")

        pointer = operation.get("pointer")
        row_key = str(operation.get("row_key") or "")
        obj_type = str(operation.get("object_type") or "").lower()

        target_files = self._rebind_target_files(operation, row_key, obj_type)
        if isinstance(pointer, str) and pointer:
            if len(target_files) != 1:
                raise PBIRWriteError("invalid_operation", "Pointer-based REBIND_FIELD requires a single target file.")
            target_file = target_files[0]
            doc = _read_json(target_file)
            self._rebind_at_pointer(
                doc,
                pointer=pointer,
                old_entity=old_entity,
                old_prop=old_prop,
                new_entity=new_entity,
                new_prop=new_prop,
                old_kind=old_kind,
                new_kind=new_kind,
                old_level=old_level,
                new_level=new_level,
                query_ref_spec=operation.get("query_ref"),
                native_query_ref_spec=operation.get("native_query_ref"),
            )
            _write_json(target_file, doc)
            return

        for target_file in target_files:
            doc = _read_json(target_file)
            if self._rebind_document_tree(
                doc,
                old_entity=old_entity,
                old_prop=old_prop,
                new_entity=new_entity,
                new_prop=new_prop,
                old_kind=old_kind,
                new_kind=new_kind,
                old_level=old_level,
                new_level=new_level,
            ):
                _write_json(target_file, doc)

        ext_path = self.candidate_dir / "definition" / "reportExtensions.json"
        if ext_path.is_file() and (not row_key or obj_type in {"", "report", "report_measure"}):
            ext_doc = _read_json(ext_path)
            if self._rebind_report_extensions(ext_doc, old_entity, old_prop, new_entity, new_prop):
                _write_json(ext_path, ext_doc)

    def _rebind_target_files(self, operation: Mapping[str, Any], row_key: str, obj_type: str) -> list[Path]:
        if obj_type == "visual" or row_key.startswith("visual:") or operation.get("visual_id"):
            page_id, visual_id = self._resolve_visual_target(operation)
            return [self.candidate_dir / "definition" / "pages" / page_id / "visuals" / visual_id / "visual.json"]
        if obj_type == "page" or row_key.startswith("page:") or (operation.get("page_id") and not operation.get("visual_id")):
            page_id = self._resolve_page_target(operation)
            page_dir = self.candidate_dir / "definition" / "pages" / page_id
            if isinstance(operation.get("pointer"), str) and operation.get("pointer"):
                return [page_dir / "page.json"]
            return [page_dir / "page.json", *sorted(page_dir.glob("visuals/*/visual.json"))]
        if obj_type == "report" or row_key == "report:report":
            if isinstance(operation.get("pointer"), str) and operation.get("pointer"):
                return [self.candidate_dir / "definition" / "report.json"]
        pages_dir = self.candidate_dir / "definition" / "pages"
        files = [self.candidate_dir / "definition" / "report.json"]
        files.extend(sorted(pages_dir.glob("*/page.json")))
        files.extend(sorted(pages_dir.glob("*/visuals/*/visual.json")))
        return [f for f in files if f.is_file()]

    def _rebind_at_pointer(
        self,
        doc: dict[str, Any],
        *,
        pointer: str,
        old_entity: str,
        old_prop: str,
        new_entity: str,
        new_prop: str,
        old_kind: str,
        new_kind: str,
        old_level: Any,
        new_level: Any,
        query_ref_spec: Any,
        native_query_ref_spec: Any,
    ) -> None:
        parts = _pointer_parts(pointer)
        target = _resolve_pointer(doc, parts)
        if not isinstance(target, dict):
            raise PBIRWriteError("invalid_operation", f"Pointer {pointer} did not resolve to a JSON object.", {"pointer": pointer})

        self._update_binding_dict(
            target,
            old_entity=old_entity,
            old_prop=old_prop,
            new_entity=new_entity,
            new_prop=new_prop,
            old_kind=old_kind,
            new_kind=new_kind,
            old_level=old_level,
            new_level=new_level,
        )

        for depth in range(len(parts) - 1, -1, -1):
            ancestor = _resolve_pointer(doc, parts[:depth])
            if isinstance(ancestor, dict) and ("queryRef" in ancestor or "nativeQueryRef" in ancestor):
                self._update_projection_refs(
                    ancestor,
                    old_entity=old_entity,
                    old_prop=old_prop,
                    new_entity=new_entity,
                    new_prop=new_prop,
                    old_level=old_level,
                    new_level=new_level,
                    query_ref_spec=query_ref_spec,
                    native_query_ref_spec=native_query_ref_spec,
                )
                break

        if len(parts) >= 3 and parts[0] == "filterConfig" and parts[1] == "filters":
            filter_item = _resolve_pointer(doc, parts[:3])
            if isinstance(filter_item, dict):
                self._update_semantic_filter(
                    filter_item,
                    old_entity=old_entity,
                    old_prop=old_prop,
                    new_entity=new_entity,
                    new_prop=new_prop,
                    old_kind=old_kind,
                    new_kind=new_kind,
                )

    def _update_projection_refs(
        self,
        holder: dict[str, Any],
        *,
        old_entity: str,
        old_prop: str,
        new_entity: str,
        new_prop: str,
        old_level: Any = None,
        new_level: Any = None,
        query_ref_spec: Any = None,
        native_query_ref_spec: Any = None,
    ) -> None:
        if "queryRef" in holder and isinstance(holder["queryRef"], str):
            if isinstance(query_ref_spec, Mapping) and isinstance(query_ref_spec.get("new"), str):
                holder["queryRef"] = query_ref_spec["new"]
            else:
                updated = new_query_ref(holder["queryRef"], old_entity, old_prop, new_entity, new_prop) or holder["queryRef"]
                if isinstance(old_level, str) and isinstance(new_level, str) and old_level != new_level:
                    updated = updated.replace(f".{old_level}", f".{new_level}")
                holder["queryRef"] = updated

        if "nativeQueryRef" in holder and isinstance(holder["nativeQueryRef"], str):
            if isinstance(native_query_ref_spec, Mapping) and isinstance(native_query_ref_spec.get("new"), str):
                holder["nativeQueryRef"] = native_query_ref_spec["new"]
            else:
                holder["nativeQueryRef"] = (
                    new_native_query_ref(holder["nativeQueryRef"], old_prop, new_prop) or holder["nativeQueryRef"]
                )

    def _update_binding_dict(
        self,
        node: dict[str, Any],
        *,
        old_entity: str,
        old_prop: str,
        new_entity: str,
        new_prop: str,
        old_kind: str,
        new_kind: str,
        old_level: Any = None,
        new_level: Any = None,
    ) -> bool:
        changed = False
        for key in ("Column", "Measure"):
            binding = node.get(key)
            if not isinstance(binding, dict):
                continue
            expr = binding.get("Expression") if isinstance(binding.get("Expression"), dict) else {}
            source_ref = expr.get("SourceRef") if isinstance(expr.get("SourceRef"), dict) else {}
            entity = source_ref.get("Entity")
            prop = binding.get("Property")
            if isinstance(entity, str) and isinstance(prop, str):
                if (not old_entity or fold(entity) == fold(old_entity)) and (not old_prop or fold(prop) == fold(old_prop)):
                    source_ref["Entity"] = new_entity
                    binding["Property"] = new_prop
                    target_key = self._binding_key_for_kind(new_kind, default=key)
                    if target_key != key:
                        node[target_key] = node.pop(key)
                    changed = True
                    return changed

        if "HierarchyLevel" in node and isinstance(node["HierarchyLevel"], dict):
            hl = node["HierarchyLevel"]
            h_expr = hl.get("Expression") if isinstance(hl.get("Expression"), dict) else {}
            hierarchy = h_expr.get("Hierarchy") if isinstance(h_expr.get("Hierarchy"), dict) else {}
            inner_expr = hierarchy.get("Expression") if isinstance(hierarchy.get("Expression"), dict) else {}
            source_ref = inner_expr.get("SourceRef") if isinstance(inner_expr.get("SourceRef"), dict) else {}
            entity = source_ref.get("Entity")
            h_name = hierarchy.get("Hierarchy")
            level = hl.get("Level")
            if isinstance(entity, str) and (not old_entity or fold(entity) == fold(old_entity)):
                if not old_prop or (isinstance(h_name, str) and fold(h_name) == fold(old_prop)):
                    source_ref["Entity"] = new_entity
                    if isinstance(h_name, str) and new_prop:
                        hierarchy["Hierarchy"] = new_prop
                    if isinstance(new_level, str) and new_level:
                        hl["Level"] = new_level
                    changed = True
                elif isinstance(level, str) and fold(level) == fold(old_prop):
                    source_ref["Entity"] = new_entity
                    hl["Level"] = new_prop
                    changed = True
            return changed

        if "Hierarchy" in node and isinstance(node["Hierarchy"], dict):
            hierarchy = node["Hierarchy"]
            inner_expr = hierarchy.get("Expression") if isinstance(hierarchy.get("Expression"), dict) else {}
            source_ref = inner_expr.get("SourceRef") if isinstance(inner_expr.get("SourceRef"), dict) else {}
            entity = source_ref.get("Entity")
            h_name = hierarchy.get("Hierarchy")
            if isinstance(entity, str) and isinstance(h_name, str):
                if (not old_entity or fold(entity) == fold(old_entity)) and (not old_prop or fold(h_name) == fold(old_prop)):
                    source_ref["Entity"] = new_entity
                    hierarchy["Hierarchy"] = new_prop
                    changed = True
            return changed

        if "Aggregation" in node and isinstance(node["Aggregation"], dict):
            agg_expr = node["Aggregation"].get("Expression")
            if isinstance(agg_expr, dict):
                return self._update_binding_dict(
                    agg_expr,
                    old_entity=old_entity,
                    old_prop=old_prop,
                    new_entity=new_entity,
                    new_prop=new_prop,
                    old_kind=old_kind,
                    new_kind=new_kind,
                    old_level=old_level,
                    new_level=new_level,
                )
        return changed

    @staticmethod
    def _binding_key_for_kind(kind: str, *, default: str) -> str:
        norm = kind.strip().lower()
        if norm == "column":
            return "Column"
        if norm in {"measure", "report_measure"}:
            return "Measure"
        return default

    def _rebind_document_tree(
        self,
        node: Any,
        *,
        old_entity: str,
        old_prop: str,
        new_entity: str,
        new_prop: str,
        old_kind: str,
        new_kind: str,
        old_level: Any = None,
        new_level: Any = None,
    ) -> bool:
        changed = False
        if isinstance(node, dict):
            if self._update_binding_dict(
                node,
                old_entity=old_entity,
                old_prop=old_prop,
                new_entity=new_entity,
                new_prop=new_prop,
                old_kind=old_kind,
                new_kind=new_kind,
                old_level=old_level,
                new_level=new_level,
            ):
                changed = True

            if "field" in node and isinstance(node["field"], dict):
                if self._rebind_document_tree(
                    node["field"],
                    old_entity=old_entity,
                    old_prop=old_prop,
                    new_entity=new_entity,
                    new_prop=new_prop,
                    old_kind=old_kind,
                    new_kind=new_kind,
                    old_level=old_level,
                    new_level=new_level,
                ):
                    changed = True
                    self._update_projection_refs(
                        node,
                        old_entity=old_entity,
                        old_prop=old_prop,
                        new_entity=new_entity,
                        new_prop=new_prop,
                        old_level=old_level,
                        new_level=new_level,
                    )

            if "filter" in node and isinstance(node["filter"], dict) and "field" in node:
                if self._update_semantic_filter(
                    node,
                    old_entity=old_entity,
                    old_prop=old_prop,
                    new_entity=new_entity,
                    new_prop=new_prop,
                    old_kind=old_kind,
                    new_kind=new_kind,
                ):
                    changed = True

            for key, child in list(node.items()):
                if key == "field":
                    continue
                if isinstance(child, (dict, list)):
                    if self._rebind_document_tree(
                        child,
                        old_entity=old_entity,
                        old_prop=old_prop,
                        new_entity=new_entity,
                        new_prop=new_prop,
                        old_kind=old_kind,
                        new_kind=new_kind,
                        old_level=old_level,
                        new_level=new_level,
                    ):
                        changed = True
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    if self._rebind_document_tree(
                        item,
                        old_entity=old_entity,
                        old_prop=old_prop,
                        new_entity=new_entity,
                        new_prop=new_prop,
                        old_kind=old_kind,
                        new_kind=new_kind,
                        old_level=old_level,
                        new_level=new_level,
                    ):
                        changed = True
        return changed

    def _update_semantic_filter(
        self,
        filter_item: dict[str, Any],
        *,
        old_entity: str,
        old_prop: str,
        new_entity: str,
        new_prop: str,
        old_kind: str,
        new_kind: str,
    ) -> bool:
        semantic = filter_item.get("filter")
        if not isinstance(semantic, dict):
            return False
        from_list = semantic.get("From")
        if not isinstance(from_list, list):
            return False
        matching_aliases = {
            str(entry.get("Name"))
            for entry in from_list
            if isinstance(entry, dict) and isinstance(entry.get("Entity"), str) and fold(entry["Entity"]) == fold(old_entity)
        }
        if not matching_aliases:
            return False

        changed = False

        def walk_where(sub: Any) -> None:
            nonlocal changed
            if isinstance(sub, dict):
                for key in ("Column", "Measure"):
                    binding = sub.get(key)
                    if isinstance(binding, dict):
                        expr = binding.get("Expression") if isinstance(binding.get("Expression"), dict) else {}
                        sref = expr.get("SourceRef") if isinstance(expr.get("SourceRef"), dict) else {}
                        src = sref.get("Source")
                        ent = sref.get("Entity")
                        prop = binding.get("Property")
                        if (src in matching_aliases or (isinstance(ent, str) and fold(ent) == fold(old_entity))) and (
                            isinstance(prop, str) and fold(prop) == fold(old_prop)
                        ):
                            binding["Property"] = new_prop
                            if isinstance(ent, str):
                                sref["Entity"] = new_entity
                            target_key = self._binding_key_for_kind(new_kind, default=key)
                            if target_key != key:
                                sub[target_key] = sub.pop(key)
                            changed = True
                for val in sub.values():
                    if isinstance(val, (dict, list)):
                        walk_where(val)
            elif isinstance(sub, list):
                for item in sub:
                    walk_where(item)

        walk_where(semantic.get("Where"))
        if fold(old_entity) != fold(new_entity):
            for entry in from_list:
                if isinstance(entry, dict) and entry.get("Name") in matching_aliases:
                    entry["Entity"] = new_entity
                    changed = True
        return changed

    @staticmethod
    def _rebind_report_extensions(
        ext_doc: dict[str, Any],
        old_entity: str,
        old_prop: str,
        new_entity: str,
        new_prop: str,
    ) -> bool:
        changed = False
        for entity in ext_doc.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            for measure in entity.get("measures") or []:
                if not isinstance(measure, dict):
                    continue
                refs = measure.get("references")
                if isinstance(refs, dict) and isinstance(refs.get("measures"), list):
                    for ref in refs["measures"]:
                        if not isinstance(ref, dict):
                            continue
                        if fold(str(ref.get("entity") or "")) == fold(old_entity) and fold(str(ref.get("name") or "")) == fold(old_prop):
                            ref["entity"] = new_entity
                            ref["name"] = new_prop
                            changed = True
        return changed

    def _op_remove_field(self, operation: Mapping[str, Any]) -> None:
        pointer = str(operation.get("pointer") or "")
        if not pointer:
            raise PBIRWriteError("invalid_operation", "REMOVE_FIELD requires a JSON Pointer.")
        row_key = str(operation.get("row_key") or "")
        obj_type = str(operation.get("object_type") or "").lower()
        target_files = self._rebind_target_files(operation, row_key, obj_type)
        if len(target_files) != 1:
            raise PBIRWriteError("invalid_operation", "REMOVE_FIELD requires a single target file.")

        target_file = target_files[0]
        doc = _read_json(target_file)
        parts = _pointer_parts(pointer)
        field_spec = operation.get("field") if isinstance(operation.get("field"), Mapping) else {}

        list_depth: int | None = None
        for idx in range(len(parts) - 1, -1, -1):
            container = _resolve_pointer(doc, parts[:idx])
            if isinstance(container, list):
                list_depth = idx
                break

        if list_depth is None:
            parent = _resolve_pointer(doc, parts[:-1])
            if isinstance(parent, dict) and parts:
                parent.pop(parts[-1], None)
                _write_json(target_file, doc)
            return

        items_list = _resolve_pointer(doc, parts[:list_depth])
        assert isinstance(items_list, list)
        raw_index = parts[list_depth]
        target_index: int | None = None
        try:
            candidate_idx = int(raw_index)
            if 0 <= candidate_idx < len(items_list) and self._item_matches_field(items_list[candidate_idx], field_spec):
                target_index = candidate_idx
        except ValueError:
            target_index = None

        if target_index is None and field_spec:
            for idx, item in enumerate(items_list):
                if self._item_matches_field(item, field_spec):
                    target_index = idx
                    break

        if target_index is None:
            try:
                candidate_idx = int(raw_index)
                if 0 <= candidate_idx < len(items_list):
                    target_index = candidate_idx
            except ValueError:
                pass

        if target_index is not None:
            items_list.pop(target_index)

        if not items_list and list_depth >= 2 and parts[list_depth - 1] == "projections":
            query_state = _resolve_pointer(doc, parts[: list_depth - 2])
            role_name = parts[list_depth - 2]
            if isinstance(query_state, dict):
                query_state.pop(role_name, None)

        _write_json(target_file, doc)

    @staticmethod
    def _item_matches_field(item: Any, field_spec: Mapping[str, Any]) -> bool:
        if not field_spec:
            return True
        want_entity = str(field_spec.get("entity") or "")
        want_prop = str(field_spec.get("property") or "")
        if not want_entity and not want_prop:
            return True

        def check(node: Any) -> bool:
            if isinstance(node, Mapping):
                for key in ("Column", "Measure"):
                    binding = node.get(key)
                    if isinstance(binding, Mapping):
                        expr = binding.get("Expression") if isinstance(binding.get("Expression"), Mapping) else {}
                        sref = expr.get("SourceRef") if isinstance(expr.get("SourceRef"), Mapping) else {}
                        if fold(str(sref.get("Entity") or "")) == fold(want_entity) and fold(str(binding.get("Property") or "")) == fold(want_prop):
                            return True
                return any(check(child) for child in node.values())
            if isinstance(node, list):
                return any(check(child) for child in node)
            return False

        return check(item)

    # Report Measures (reportExtensions.json) ----------------------------------------

    def _load_or_init_extensions(self, operation: Mapping[str, Any]) -> dict[str, Any]:
        ext_path = self.candidate_dir / "definition" / "reportExtensions.json"
        if ext_path.is_file():
            return _read_json(ext_path)
        schema = _REPORT_EXTENSION_SCHEMA
        donor_dir = self._donor_for(operation)
        donor_ext = donor_dir / "definition" / "reportExtensions.json"
        if donor_ext.is_file():
            donor_doc = _read_json(donor_ext)
            if isinstance(donor_doc.get("$schema"), str):
                schema = donor_doc["$schema"]
        return {
            "$schema": schema,
            "name": "extension",
            "entities": [],
        }

    def _find_donor_report_measure(self, operation: Mapping[str, Any]) -> dict[str, Any] | None:
        donor_dir = self._donor_for(operation)
        donor_ext = donor_dir / "definition" / "reportExtensions.json"
        if not donor_ext.is_file():
            return None
        source_key = str(operation.get("source_key") or operation.get("row_key") or "")
        if source_key.startswith("report_measure:") and "/" in source_key:
            rest = source_key.split(":", 1)[1].split("@", 1)[0].split("#", 1)[0]
            entity_name, measure_name = rest.split("/", 1)
        else:
            entity_name = str(operation.get("table") or "")
            measure_name = str(operation.get("name") or "")
        doc = _read_json(donor_ext)
        for entity in doc.get("entities") or []:
            if not isinstance(entity, Mapping) or fold(str(entity.get("name") or "")) != fold(entity_name):
                continue
            for measure in entity.get("measures") or []:
                if isinstance(measure, dict) and fold(str(measure.get("name") or "")) == fold(measure_name):
                    return copy.deepcopy(measure)
        return None

    def _op_upsert_report_measure(self, operation: Mapping[str, Any], *, create_only: bool) -> None:
        table = str(operation.get("table") or "")
        name = str(operation.get("name") or "")
        row_key = str(operation.get("row_key") or "")
        if (not table or not name) and row_key.startswith("report_measure:") and "/" in row_key:
            rest = row_key.split(":", 1)[1].split("@", 1)[0].split("#", 1)[0]
            r_table, r_name = rest.split("/", 1)
            table = table or r_table
            name = name or r_name
        if not table or not name:
            raise PBIRWriteError("invalid_operation", "Report measure operation requires table and name.")

        props = operation.get("properties") if isinstance(operation.get("properties"), Mapping) else {}
        donor_measure = self._find_donor_report_measure(operation) or {}

        doc = self._load_or_init_extensions(operation)
        entities = doc.setdefault("entities", [])
        target_entity = next(
            (ent for ent in entities if isinstance(ent, dict) and fold(str(ent.get("name") or "")) == fold(table)),
            None,
        )
        if target_entity is None:
            target_entity = {"name": table, "measures": []}
            entities.append(target_entity)
        measures = target_entity.setdefault("measures", [])

        existing = next(
            (m for m in measures if isinstance(m, dict) and fold(str(m.get("name") or "")) == fold(name)),
            None,
        )
        if existing is None and not create_only and row_key.startswith("report_measure:") and "/" in row_key:
            orig_rest = row_key.split(":", 1)[1].split("@", 1)[0].split("#", 1)[0]
            orig_table, orig_name = orig_rest.split("/", 1)
            if fold(orig_table) != fold(table) or fold(orig_name) != fold(name):
                self._remove_measure_from_extensions(doc, orig_table, orig_name)

        base_measure: dict[str, Any] = copy.deepcopy(existing or donor_measure)
        base_measure["name"] = name
        base_measure["dataType"] = _normalize_data_type(
            props.get("data_type") or props.get("dataType") or base_measure.get("dataType")
        )
        expression = props.get("expression")
        if expression is None:
            expression = operation.get("expression") or base_measure.get("expression") or ""
        base_measure["expression"] = str(expression)

        for prop_key, json_key in (
            ("format_string", "formatString"),
            ("formatString", "formatString"),
            ("display_folder", "displayFolder"),
            ("displayFolder", "displayFolder"),
            ("description", "description"),
            ("data_category", "dataCategory"),
            ("dataCategory", "dataCategory"),
            ("hidden", "hidden"),
            ("references", "references"),
        ):
            if prop_key in props:
                val = props[prop_key]
                if val is None or val == "":
                    base_measure.pop(json_key, None)
                else:
                    base_measure[json_key] = val

        if existing is not None:
            idx = measures.index(existing)
            measures[idx] = base_measure
        else:
            measures.append(base_measure)

        _write_json(self.candidate_dir / "definition" / "reportExtensions.json", doc)

    def _op_delete_report_measure(self, operation: Mapping[str, Any]) -> None:
        ext_path = self.candidate_dir / "definition" / "reportExtensions.json"
        if not ext_path.is_file():
            return
        table = str(operation.get("table") or "")
        name = str(operation.get("name") or "")
        row_key = str(operation.get("row_key") or "")
        if (not table or not name) and row_key.startswith("report_measure:") and "/" in row_key:
            rest = row_key.split(":", 1)[1].split("@", 1)[0].split("#", 1)[0]
            table, name = rest.split("/", 1)
        doc = _read_json(ext_path)
        self._remove_measure_from_extensions(doc, table, name)
        _write_json(ext_path, doc)

    @staticmethod
    def _remove_measure_from_extensions(doc: dict[str, Any], table: str, name: str) -> None:
        entities = doc.get("entities")
        if not isinstance(entities, list):
            return
        kept_entities = []
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            if fold(str(entity.get("name") or "")) == fold(table):
                measures = [
                    m
                    for m in (entity.get("measures") or [])
                    if not (isinstance(m, dict) and fold(str(m.get("name") or "")) == fold(name))
                ]
                if measures:
                    entity["measures"] = measures
                    kept_entities.append(entity)
            else:
                kept_entities.append(entity)
        doc["entities"] = kept_entities

    def _op_rewrite_expression(self, operation: Mapping[str, Any]) -> None:
        ext_path = self.candidate_dir / "definition" / "reportExtensions.json"
        if not ext_path.is_file():
            return
        table = str(operation.get("table") or "")
        name = str(operation.get("name") or "")
        row_key = str(operation.get("row_key") or "")
        if (not table or not name) and row_key.startswith("report_measure:") and "/" in row_key:
            rest = row_key.split(":", 1)[1].split("@", 1)[0].split("#", 1)[0]
            table, name = rest.split("/", 1)
        new_text = operation.get("new_text")
        if not isinstance(new_text, str):
            return
        doc = _read_json(ext_path)
        for entity in doc.get("entities") or []:
            if not isinstance(entity, dict) or fold(str(entity.get("name") or "")) != fold(table):
                continue
            for measure in entity.get("measures") or []:
                if isinstance(measure, dict) and fold(str(measure.get("name") or "")) == fold(name):
                    measure["expression"] = new_text
        _write_json(ext_path, doc)

    def _op_rename_report_object(self, operation: Mapping[str, Any]) -> None:
        obj_type = str(operation.get("object_type") or "").lower()
        new_name = str(operation.get("new_name") or "").strip()
        if not new_name:
            return
        if obj_type == "report_measure":
            ext_path = self.candidate_dir / "definition" / "reportExtensions.json"
            if not ext_path.is_file():
                return
            table = str(operation.get("table") or "")
            old_name = str(operation.get("old_name") or operation.get("name") or "")
            doc = _read_json(ext_path)
            for entity in doc.get("entities") or []:
                if not isinstance(entity, dict) or fold(str(entity.get("name") or "")) != fold(table):
                    continue
                for measure in entity.get("measures") or []:
                    if isinstance(measure, dict) and fold(str(measure.get("name") or "")) == fold(old_name):
                        measure["name"] = new_name
            _write_json(ext_path, doc)
        elif obj_type == "page":
            page_id = self._resolve_page_target(operation)
            page_file = self.candidate_dir / "definition" / "pages" / page_id / "page.json"
            doc = _read_json(page_file)
            doc["displayName"] = new_name
            _write_json(page_file, doc)

    def _op_set_properties(self, operation: Mapping[str, Any]) -> None:
        obj_type = str(operation.get("object_type") or "").lower()
        if obj_type == "report_measure":
            self._op_upsert_report_measure(operation, create_only=False)
        elif obj_type == "page":
            page_id = self._resolve_page_target(operation)
            page_file = self.candidate_dir / "definition" / "pages" / page_id / "page.json"
            doc = _read_json(page_file)
            props = operation.get("properties") if isinstance(operation.get("properties"), Mapping) else {}
            if isinstance(props.get("display_name"), str):
                doc["displayName"] = props["display_name"]
            if isinstance(props.get("page_size"), Mapping):
                for key in ("height", "width", "displayOption"):
                    if key in props["page_size"]:
                        doc[key] = props["page_size"][key]
            _write_json(page_file, doc)

    def _op_rebind_dataset(self, operation: Mapping[str, Any]) -> None:
        pbir_path = self.candidate_dir / "definition.pbir"
        if not pbir_path.is_file():
            return
        doc = _read_json(pbir_path)
        dataset_ref = operation.get("dataset_reference") or operation.get("datasetReference")
        if isinstance(dataset_ref, Mapping):
            doc["datasetReference"] = copy.deepcopy(dict(dataset_ref))
        elif isinstance(operation.get("by_path"), str):
            doc["datasetReference"] = {"byPath": {"path": operation["by_path"]}}
        _write_json(pbir_path, doc)

    # Finalize pages (groups & interactions) -----------------------------------------

    def _finalize_touched_pages(self) -> None:
        for page_id in sorted(self._touched_pages):
            page_dir = self.candidate_dir / "definition" / "pages" / page_id
            page_file = page_dir / "page.json"
            if not page_file.is_file():
                continue
            visual_map = self._page_visual_maps.get(page_id, {})
            visual_files = sorted(page_dir.glob("visuals/*/visual.json"))
            present_visuals: set[str] = set()
            group_visuals: set[str] = set()
            loaded_visuals: list[tuple[Path, dict[str, Any]]] = []

            for v_file in visual_files:
                v_doc = _read_json(v_file)
                v_name = str(v_doc.get("name") or v_file.parent.name)
                present_visuals.add(v_name)
                if "visualGroup" in v_doc:
                    group_visuals.add(v_name)
                loaded_visuals.append((v_file, v_doc))

            for v_file, v_doc in loaded_visuals:
                parent_group = v_doc.get("parentGroupName")
                if isinstance(parent_group, str):
                    mapped_group = visual_map.get(parent_group, parent_group)
                    if mapped_group in group_visuals or mapped_group in present_visuals:
                        if mapped_group != parent_group:
                            v_doc["parentGroupName"] = mapped_group
                            _write_json(v_file, v_doc)
                    else:
                        v_doc.pop("parentGroupName", None)
                        _write_json(v_file, v_doc)

            page_doc = _read_json(page_file)
            page_changed = False
            interactions = page_doc.get("visualInteractions")
            if isinstance(interactions, list):
                cleaned_interactions: list[dict[str, Any]] = []
                seen_pairs: set[tuple[str, str]] = set()
                for entry in interactions:
                    if not isinstance(entry, dict):
                        continue
                    src = str(entry.get("source") or "")
                    tgt = str(entry.get("target") or "")
                    mapped_src = visual_map.get(src, src)
                    mapped_tgt = visual_map.get(tgt, tgt)
                    if mapped_src in present_visuals and mapped_tgt in present_visuals and (mapped_src, mapped_tgt) not in seen_pairs:
                        seen_pairs.add((mapped_src, mapped_tgt))
                        updated_entry = dict(entry)
                        updated_entry["source"] = mapped_src
                        updated_entry["target"] = mapped_tgt
                        cleaned_interactions.append(updated_entry)
                if cleaned_interactions != interactions:
                    page_doc["visualInteractions"] = cleaned_interactions
                    page_changed = True

            auto_cfg = page_doc.get("autoPageGenerationConfig")
            if isinstance(auto_cfg, dict):
                v_configs = auto_cfg.get("visualContainerConfigurations")
                if isinstance(v_configs, list):
                    for item in v_configs:
                        if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"] in visual_map:
                            item["name"] = visual_map[item["name"]]
                            page_changed = True
                layout = auto_cfg.get("layout")
                if isinstance(layout, dict):
                    for l_key in ("related", "combination"):
                        sub = layout.get(l_key)
                        if isinstance(sub, dict) and isinstance(sub.get("dataTableName"), str) and sub["dataTableName"] in visual_map:
                            sub["dataTableName"] = visual_map[sub["dataTableName"]]
                            page_changed = True

            if page_changed:
                _write_json(page_file, page_doc)

    # Validation and file diff -------------------------------------------------------

    def _validate_candidate(self) -> dict[str, Any]:
        root_name = self.candidate_dir.name
        if not root_name.casefold().endswith(".report"):
            root_name = (
                self.baseline_dir.name
                if self.baseline_dir.name.casefold().endswith(".report")
                else f"{root_name}.Report"
            )
        documents: dict[str, Any] = {}
        for file_path in sorted(self.candidate_dir.rglob("*")):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(self.candidate_dir).as_posix()
            if file_path.name == ".platform":
                continue
            if file_path.suffix.casefold() in {".json", ".pbir"}:
                documents[f"{root_name}/{rel}"] = _read_json(file_path)

        result = validate_report_documents(documents)
        structural_errors = [
            issue for issue in result.get("issues", []) if issue.get("code") in _STRUCTURAL_VALIDATION_CODES
        ]
        if structural_errors:
            raise PBIRWriteError(
                "schema_validation_failed",
                REFUSED_REASONS["schema_validation_failed"],
                {"issues": structural_errors},
            )
        return result

    def _diff_files(self) -> tuple[list[str], list[str], list[str]]:
        base_files = {
            p.relative_to(self.baseline_dir).as_posix(): p.read_bytes()
            for p in self.baseline_dir.rglob("*")
            if p.is_file() and ".pbi" not in p.parts and ".pbibrain" not in p.parts
        }
        cand_files = {
            p.relative_to(self.candidate_dir).as_posix(): p.read_bytes()
            for p in self.candidate_dir.rglob("*")
            if p.is_file()
        }
        added = sorted(rel for rel in cand_files if rel not in base_files)
        removed = sorted(rel for rel in base_files if rel not in cand_files)
        changed = sorted(rel for rel in cand_files if rel in base_files and cand_files[rel] != base_files[rel])
        return changed, added, removed


def write_report(
    baseline_path: str | Path,
    candidate_path: str | Path,
    operations: Sequence[Mapping[str, Any]],
    *,
    donor_paths: Mapping[str, str | Path] | str | Path | None = None,
) -> dict[str, Any]:
    """Apply report operations to a baseline PBIR report and write the candidate folder."""
    writer = PBIRWriter(baseline_path, candidate_path, donor_paths=donor_paths)
    return writer.write(operations)
