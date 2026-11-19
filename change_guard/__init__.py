"""Independent trusted change-control runtime. Never exposed by Brain MCP."""

from change_guard.merge import MergeGuard, MergeGuardError, build_merge_contract, build_write_record

__all__ = ["MergeGuard", "MergeGuardError", "build_merge_contract", "build_write_record"]
