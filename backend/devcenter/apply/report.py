"""Markdown change report of an apply (technical design section 13 step 12).

The report is for a commit message or a pull request. The app never commits or pushes.
"""

from __future__ import annotations

from typing import Any, Mapping

_CHANGES = (("created", "Added"), ("modified", "Changed"), ("renamed", "Renamed"), ("deleted", "Removed"))


def _counts(part: Mapping[str, Any]) -> str:
    values = []
    for change, label in _CHANGES:
        block = part.get(change) or {}
        total = int(block.get("total") or 0)
        if total:
            kinds = ", ".join(f"{count} {kind}" for kind, count in sorted((block.get("by_type") or {}).items()))
            values.append(f"{label}: {total} ({kinds})")
    return "; ".join(values) or "No change"


def change_report(record: Mapping[str, Any], plan: Mapping[str, Any], *, target_name: str, sources: Mapping[str, str]) -> str:
    """Give the Markdown text: the plan summary, the plan steps, the approvals, the files, and the rescan result."""

    summary = plan.get("summary") or {}
    lines = [f"# Merge into {target_name}", ""]
    if record.get("kind") == "format_only":
        lines += ["Format only apply: the model files now have the canonical TMDL format. No object changed.", ""]
    lines += [
        "## Plan summary", "",
        f"- Plan hash: `{plan.get('plan_hash') or record.get('plan_hash')}`",
        f"- Plan steps: {int(summary.get('steps') or 0)}",
        f"- Model: {_counts(summary.get('model') or {})}",
        f"- Report: {_counts(summary.get('report') or {})}",
        "",
    ]
    steps = list(plan.get("steps") or [])
    if steps:
        lines += ["## Plan steps", ""]
        for step in steps:
            source = sources.get(str(step.get("source_id")), step.get("source_id") or "target")
            lines.append(f"- {step.get('change')} {step.get('object_type')} `{step.get('name')}` (from {source})")
        lines.append("")
    approvals = list(record.get("approvals") or [])
    lines += ["## Approvals", "", *(f"- {item}" for item in approvals)] if approvals else ["## Approvals", "", "- No approval was necessary."]
    lines += ["", "## Changed files", "", *(f"- `{path}`" for path in record.get("files") or [])]
    differences = list(record.get("rescan_differences") or [])
    lines += ["", "## Rescan", ""]
    if differences:
        lines += [f"- `{item['object']}`: expected {item['expected']}, found {item['found']}" for item in differences]
    else:
        lines.append("- The rescan of the target agrees with the plan.")
    lines += ["", f"Apply ID: `{record.get('apply_id')}`. Finished (UTC): {record.get('finished_utc')}.", ""]
    return "\n".join(lines)
