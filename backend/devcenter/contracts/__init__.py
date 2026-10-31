"""JSON Schema contracts of the Development Center (technical design section 14, UC4).

Each file in this folder has an ``$id`` of the form ``<base>/<relative path>``.
A schema can refer to another file with a relative ``$ref`` (for example
``"../error.json"``).
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

CONTRACTS_DIR = Path(__file__).resolve().parent
BASE_ID = "https://pbibrain.local/devcenter/contracts/"


@lru_cache(maxsize=1)
def _registry() -> tuple[Registry, dict[str, dict[str, Any]]]:
    schemas: dict[str, dict[str, Any]] = {}
    resources = []
    for path in sorted(CONTRACTS_DIR.rglob("*.json")):
        relative = path.relative_to(CONTRACTS_DIR).as_posix()
        schema = json.loads(path.read_text(encoding="utf-8"))
        if schema.get("$id") != BASE_ID + relative:
            raise ValueError(f"Contract {relative} must have $id {BASE_ID + relative}")
        Draft202012Validator.check_schema(schema)
        schemas[relative] = schema
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources), schemas


def names() -> list[str]:
    return sorted(_registry()[1])


def schema(name: str) -> dict[str, Any]:
    return _registry()[1][name]


def validator(name: str) -> Draft202012Validator:
    registry, schemas = _registry()
    return Draft202012Validator(schemas[name], registry=registry)


def errors(name: str, value: Any) -> list[str]:
    """Give one line for each contract error (empty when the value is valid)."""

    found = sorted(validator(name).iter_errors(value), key=lambda item: list(item.absolute_path))
    return [f"/{'/'.join(str(part) for part in item.absolute_path)}: {item.message}" for item in found]


def jsapi_request(method: str) -> str:
    return f"jsapi/{method}.request.json"


def jsapi_reply(method: str) -> str:
    return f"jsapi/{method}.reply.json"


ERROR = "error.json"
