"""Power BI semantic-model source adapter.

Only source-shape handling belongs here.  The rest of the Brain consumes the
plain mapping returned by this reader.
"""

from __future__ import annotations

from typing import Any, Mapping

from .metadata_reader import collection, load_metadata, pick


class ModelReader:
    def read(self, source: Any) -> dict[str, Any]:
        value = load_metadata(source)
        if isinstance(value, list):
            if len(value) != 1 or not isinstance(value[0], Mapping):
                raise TypeError("ModelReader.read expects one model object")
            value = value[0]
        nested = pick(value, "model", "semantic_model", "semanticModel", "dataset")
        if isinstance(nested, Mapping):
            return dict(nested)
        models = collection(value, "models", "semanticModels", "semantic_models")
        if len(models) == 1 and isinstance(models[0], Mapping):
            return dict(models[0])
        values = pick(value, "value")
        if isinstance(values, list) and len(values) == 1 and isinstance(values[0], Mapping):
            return dict(values[0])
        return value

    def read_many(self, source: Any) -> list[dict[str, Any]]:
        value = load_metadata(source)
        if isinstance(value, list):
            return [self.read(item) for item in value if isinstance(item, Mapping)]
        models = collection(value, "models", "semanticModels", "semantic_models")
        if not models and isinstance(pick(value, "value"), list):
            models = pick(value, "value")
        if models:
            return [self.read(item) for item in models if isinstance(item, Mapping)]
        return [self.read(value)]


def read_model(source: Any) -> dict[str, Any]:
    return ModelReader().read(source)
