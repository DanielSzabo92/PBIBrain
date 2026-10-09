"""Bounded, derived in-memory cache; never another persistent graph."""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from backend.snapshots import Snapshot, content_hash
from .analyzer import analyze_impact


class SnapshotImpactCache:
    def __init__(self, maximum_entries: int = 16):
        if type(maximum_entries) is not int or maximum_entries < 1:
            raise ValueError("Positive cache bound required")
        self.maximum_entries = maximum_entries
        self._reports = OrderedDict()
        self._lock = RLock()

    def analyze(self, snapshot: Snapshot, target_ids: list[str], changes: list[dict] | None = None, *, include_report_usage: bool = True) -> dict:
        value = snapshot.to_dict()
        graph, completeness = value["analysis"]["graph"], value["completeness"]
        key = content_hash({"snapshot_id": snapshot.snapshot_id, "graph": graph, "completeness": completeness,
                            "targets": sorted(set(target_ids)), "changes": sorted(changes or [], key=content_hash), "reports": include_report_usage})
        with self._lock:
            if key in self._reports:
                self._reports.move_to_end(key)
                return deepcopy(self._reports[key])
        report = analyze_impact(graph, target_ids, changes, baseline_snapshot_id=snapshot.snapshot_id,
                                completeness=completeness, include_report_usage=include_report_usage)
        with self._lock:
            self._reports[key] = deepcopy(report)
            self._reports.move_to_end(key)
            while len(self._reports) > self.maximum_entries:
                self._reports.popitem(last=False)
        return report
