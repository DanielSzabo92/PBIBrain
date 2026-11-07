"""JS API methods of issue #16 (migration): the TMDL conversion of a model.bim target and the merge templates.

They exist in the pywebview JS API only, like the other state changes (ADR 0003).
"""

from __future__ import annotations

from typing import Any, Mapping

from backend.devcenter.jsapi import register
from backend.devcenter.session import templates
from backend.devcenter.sources.convert import convert_to_tmdl

MIGRATION_METHODS = ("target_convert_tmdl", "merge_template_save", "merge_template_list", "merge_template_apply")


@register("target_convert_tmdl", long=True)
def target_convert_tmdl(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return convert_to_tmdl(devcenter, request)


@register("merge_template_save")
def merge_template_save(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return templates.template_save(devcenter, request)


@register("merge_template_list")
def merge_template_list(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return templates.templates_list(devcenter)


@register("merge_template_apply")
def merge_template_apply(devcenter: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
    return templates.template_apply(devcenter, request)
