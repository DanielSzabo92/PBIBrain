"""Markdown change report generation for local apply (section 13 step 12)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.devcenter.session.store import write_atomic

DEFAULT_REPORT_FILENAME = "change-report.md"


def build_change_report(
    *,
    session: Mapping[str, Any],
    plan: Mapping[str, Any],
    last_apply: Mapping[str, Any] | None = None,
    approvals: Sequence[str] = (),
    warnings: Sequence[str] = (),
) -> str:
    """Format a deterministic Markdown change report summarizing the plan and latest apply."""
    display_name = str(session.get("display_name") or "Merge session")
    session_id = str(session.get("session_id") or "")
    plan_hash = str(plan.get("plan_hash") or (last_apply or {}).get("plan_hash") or "")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines: list[str] = [
        "# Merge Change Report",
        "",
        f"- **Session:** {display_name} (`{session_id}`)",
        f"- **Generated (UTC):** {generated}",
        f"- **Plan hash:** `{plan_hash}`",
        f"- **Plan status:** `{plan.get('status', 'valid')}`",
    ]

    if last_apply and last_apply.get("apply_id"):
        lines.extend([
            f"- **Last apply ID:** `{last_apply['apply_id']}` (`{last_apply.get('kind', 'apply')}`)",
            f"- **Files written:** {int(last_apply.get('file_count', 0))}",
        ])

    lines.extend(["", "## Plan Summary", ""])
    summary = plan.get("summary") or {}
    lines.append(f"- **Total steps:** {int(summary.get('steps', len(plan.get('steps') or ())))}")
    for domain in ("model", "report"):
        part = summary.get(domain) or {}
        if not isinstance(part, Mapping):
            continue
        created = int((part.get("created") or {}).get("total", 0))
        modified = int((part.get("modified") or {}).get("total", 0))
        deleted = int((part.get("deleted") or {}).get("total", 0))
        renamed = int((part.get("renamed") or {}).get("total", 0))
        lines.append(
            f"- **{domain.capitalize()}:** {int(part.get('steps', 0))} steps "
            f"(+{created} added, ~{modified} modified, ->{renamed} renamed, -{deleted} removed)"
        )

    steps = list(plan.get("steps") or ())
    if steps:
        lines.extend(["", "## Changes", ""])
        for step in steps:
            domain = step.get("domain", "model")
            change = step.get("change", "modified")
            otype = step.get("object_type", "object")
            name = step.get("name") or step.get("row_key")
            source_id = step.get("source_id")
            src_note = f" from `{source_id}`" if source_id else ""
            lines.append(f"- [{domain}] **{change}** {otype} `{name}`{src_note}")

    changed_files = list((last_apply or {}).get("changed_files") or ())
    if changed_files:
        lines.extend(["", "## Changed Files", ""])
        for path_str in changed_files:
            lines.append(f"- `{path_str}`")

    if approvals:
        lines.extend(["", "## Approvals", ""])
        for item in approvals:
            lines.append(f"- `{item}`")

    all_warnings = list(warnings)
    for w in plan.get("warnings") or ():
        msg = w.get("message") if isinstance(w, Mapping) else str(w)
        if msg and msg not in all_warnings:
            all_warnings.append(msg)
    if all_warnings:
        lines.extend(["", "## Warnings", ""])
        for w in all_warnings:
            lines.append(f"- {w}")

    rescan_diffs = list((last_apply or {}).get("rescan_differences") or ())
    lines.extend(["", "## Rescan Verification", ""])
    if rescan_diffs:
        for diff in rescan_diffs:
            lines.append(
                f"- `{diff.get('object')}`: expected `{diff.get('expected')}`, found `{diff.get('found')}`"
            )
    else:
        lines.append("- Target rescan matches plan with 0 differences.")

    lines.extend([
        "",
        "---",
        "Generated locally by PBIBrain. No Git commit or push was performed.",
        "",
    ])
    return "\n".join(lines)


def write_change_report(
    session_folder: Path,
    markdown: str,
    *,
    output_path: str | Path | None = None,
) -> Path:
    """Write the Markdown change report atomically to the session folder or requested output path."""
    target = Path(output_path) if output_path else (session_folder / DEFAULT_REPORT_FILENAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(target, markdown.encode("utf-8"))
    return target
