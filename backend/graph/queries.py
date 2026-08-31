"""Stable basic graph operations for API and CLI callers."""

from __future__ import annotations

from typing import Sequence

from .repository import GraphRepository


def search_objects(repository: GraphRepository, query: str):
    return repository.search_objects(query)


def get_object(repository: GraphRepository, object_id: str):
    return repository.get_object(object_id)


def get_neighbors(repository: GraphRepository, object_id: str, edge_types: Sequence[str] | None = None):
    return repository.get_neighbors(object_id, edge_types)


def get_dependencies(repository: GraphRepository, object_id: str):
    return repository.get_dependencies(object_id)


def get_dependents(repository: GraphRepository, object_id: str):
    return repository.get_dependents(object_id)


def get_usage(repository: GraphRepository, object_id: str):
    return repository.get_usage(object_id)
