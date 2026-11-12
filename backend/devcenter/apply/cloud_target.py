"""Cloud targets of an apply (issue #16, spec sections 4.2 and 9.3).

A cloud model target (connected with ``Read/Write`` access) goes through the
same guard as a local target. The guard works on a local working copy:

1. Read the model (and the cloud report target) from the service again. When the
   objects differ from the baseline of the last source check, someone changed the
   model in the service: stop.
2. Copy the export into a backup folder of the apply (``apply/cloud/<apply id>/backup``)
   and into a PBIP-like working copy (``tmp/cloud-work/<item id>``). The guard,
   the canonical check and the journaled promotion run on the working copy.
3. After the promotion: the delta deploy of the working copy's TMDL through XMLA
   (bridge ``cloud-deploy``, with the LastSchemaUpdate of step 1 as a guard against
   a concurrent change), then Fabric ``updateDefinition`` for a cloud report target.
4. The rescan reads the model from the service again and compares it with the plan.

Undo deploys the backup again, when the model in the service is still the one
that the apply wrote (its LastSchemaUpdate is the one recorded after the deploy).
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from typing import Any
from collections.abc import Mapping

from backend.devcenter.apply.steps import ApplyFailure
from backend.devcenter.errors import DevCenterError
from backend.devcenter.sources.cloud import (
    CLOUD_KINDS,
    RESULT_FAILED,
    CloudReadFailed,
    _file_name,
)
from backend.devcenter.sources.kinds import CLOUD_MODEL, CLOUD_REPORT, LocalSource
from backend.devcenter.sources.objects import object_index

CLOUD_APPLY_FOLDER = "apply/cloud"
WORK_FOLDER = "tmp/cloud-work"
CLOUD_WRITE = "CLOUD_WRITE"
WARNING_PBIX = "pbix_download_blocked"
WARNING_REPORT = "report_replaced_in_service"
NOTICE_CLOUD_WRITTEN = "cloud_written"


def is_cloud(record: Mapping[str, Any] | None) -> bool:
    return bool(record) and record["kind"] in CLOUD_KINDS


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def _deploy_failure(step: str, exc: CloudReadFailed) -> ApplyFailure:
    if exc.code == "target_changed":
        return ApplyFailure(step, "target_changed_in_service",
                            "The model in the service changed after the app read it. Nothing was written. Open the Apply dialog again.",
                            check="write")
    if exc.code in {"connect_failed", "bridge_missing"}:
        return ApplyFailure(step, "xmla_not_available", "PBIBrain cannot connect to the workspace through XMLA read/write.",
                            check="write", code_detail=exc.code)
    return ApplyFailure(step, "cloud_write_failed", "The Power BI service did not take the model change.", check="write",
                        code_detail=exc.code)


class CloudTargets:
    """The cloud part of ``ApplyService``. ``devcenter`` is the session owner."""

    def __init__(self, devcenter: Any) -> None:
        self.devcenter = devcenter

    @property
    def cloud(self) -> Any:
        return self.devcenter.cloud_service()

    def _work(self, item_id: str) -> Path:
        return Path(self.devcenter.session_folder()) / WORK_FOLDER / item_id

    def _apply_folder(self, apply_id: str) -> Path:
        return Path(self.devcenter.session_folder()) / CLOUD_APPLY_FOLDER / apply_id

    # Target --------------------------------------------------------------------------

    def target(self, document: Mapping[str, Any], model: Mapping[str, Any], report: Mapping[str, Any] | None,
               step: str, *, fresh: bool) -> SimpleNamespace:
        """The working copy of a cloud target. ``fresh`` reads the service again (apply, undo)."""

        if model["kind"] != CLOUD_MODEL:
            raise ApplyFailure(step, "target_not_tmdl", "The app can write a target model in TMDL format only.")
        if report is not None and not is_cloud(report):
            raise ApplyFailure(step, "mixed_target", "A cloud model target needs a cloud report target or a new empty report.")
        if report is not None:
            if report["kind"] != CLOUD_REPORT:
                raise ApplyFailure(step, "target_report_missing", "The target report is not available.")
            bound = str((report.get("cloud") or {}).get("dataset_id") or "").casefold()
            if bound != str(model["cloud"]["item_id"]).casefold():
                raise ApplyFailure(step, "target_report_other_model", "The cloud report target must use the cloud model target.")
        stamp = None
        if fresh:
            try:
                source, stamp = self.cloud._fresh(self.devcenter, model)
                report_source = self.cloud._fresh(self.devcenter, report)[0] if report is not None else None
            except (DevCenterError, CloudReadFailed) as exc:
                raise ApplyFailure(step, "cloud_read_failed", "PBIBrain cannot read the cloud target again.", check="write") from exc
            for record, loaded in ((model, source), (report, report_source)):
                if record is None:
                    continue
                baseline = document["row_hashes"].get(record["source_id"])
                if baseline is not None and object_index(loaded) != baseline:
                    raise ApplyFailure(step, "target_changed_in_service",
                                       "The cloud target changed in the service after the last source check. Open the Apply dialog again.")
        else:
            source = self.devcenter._load(model)
            report_source = self.devcenter._load(report) if report is not None else None
        assert source.model_dir is not None
        name = _file_name(model.get("display_name") or "Model")
        work = self._work(model["cloud"]["item_id"])
        _remove(work)
        model_dir = work / f"{name}.SemanticModel"
        _copy(source.model_dir / "definition", model_dir / "definition")
        (model_dir / "definition.pbism").write_text(json.dumps({"version": "4.2", "settings": {}}, indent=2), encoding="utf-8")
        report_path = None
        if report_source is not None:
            assert report_source.report_dir is not None
            _copy(report_source.report_dir, work / f"{name}.Report")
            report_path = f"{name}.Report"
            # In the service the report binds byConnection. The guard checks the report against the model of the
            # working copy, so the copy binds byPath; the upload sends the original definition.pbir again.
            pbir = work / report_path / "definition.pbir"
            original_pbir = pbir.read_bytes()
            document_pbir = json.loads(original_pbir.decode("utf-8-sig"))
            document_pbir["datasetReference"] = {"byPath": {"path": f"../{name}.SemanticModel"}}
            pbir.write_text(json.dumps(document_pbir, indent=2), encoding="utf-8")
        else:
            original_pbir = None
        # The guard scans a PBIP project: one .pbip file at the root (the model is found by its folder name).
        artifacts = [{"report": {"path": report_path}}] if report_path else []
        (work / f"{name}.pbip").write_text(json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
            "version": "1.0", "artifacts": artifacts, "settings": {"enableAutoRecovery": False}}, indent=2), encoding="utf-8")
        return SimpleNamespace(model=dict(model), report=dict(report) if report is not None else None, source=source,
                               report_source=report_source, root=work.resolve(), model_path=f"{name}.SemanticModel/definition",
                               report_path=report_path, stamp=stamp, original_pbir=original_pbir)

    # Preview -------------------------------------------------------------------------

    def preview(self, cloud: SimpleNamespace) -> dict[str, Any]:
        try:
            checks = self.cloud.write_checks(cloud.model)
            if cloud.report is not None:
                checks += [dict(item, check_id="report_" + item["check_id"]) for item in self.cloud.write_checks(cloud.report)]
        except DevCenterError as exc:
            checks = [{"check_id": "sign_in", "result": RESULT_FAILED, "reason": exc.details.get("reason") or exc.code, "values": {}}]
        warnings = [WARNING_PBIX] + ([WARNING_REPORT] if cloud.report is not None else [])
        return {"workspace_name": cloud.model["cloud"]["workspace_name"], "model_name": cloud.model.get("display_name") or "",
                "report_name": cloud.report.get("display_name") if cloud.report is not None else None,
                "checks": checks, "warnings": warnings}

    def require_writable(self, cloud: SimpleNamespace, step: str) -> None:
        for record in (cloud.model, cloud.report):
            if record is None:
                continue
            try:
                checks = self.cloud.write_checks(record)
            except DevCenterError as exc:
                raise ApplyFailure(step, exc.details.get("reason") or exc.code, exc.message) from exc
            failed = [item for item in checks if item["result"] == RESULT_FAILED]
            if failed:
                raise ApplyFailure(step, "cloud_write_not_possible", "The cloud target cannot be written.",
                                   check_id=failed[0]["check_id"], check_reason=failed[0]["reason"])

    # Write ---------------------------------------------------------------------------

    def backup(self, apply_id: str, cloud: SimpleNamespace) -> None:
        folder = self._apply_folder(apply_id)
        _remove(folder)
        _copy(cloud.source.model_dir / "definition", folder / "backup" / "model" / "definition")
        if cloud.report_source is not None:
            _copy(cloud.report_source.report_dir, folder / "backup" / "report")

    def deploy(self, apply_id: str, cloud: SimpleNamespace, step: str) -> dict[str, Any]:
        """Write the promoted working copy to the service. Give the record part of the apply."""

        model = cloud.model["cloud"]
        try:
            written = self.cloud.deploy_model(model["workspace_name"], model["item_id"], cloud.root / cloud.model_path, cloud.stamp)
        except CloudReadFailed as exc:
            raise _deploy_failure(step, exc) from exc
        reply = {"item_id": model["item_id"], "last_schema_update_before": written.last_schema_update_before,
                 "last_schema_update": written.last_schema_update, "report_item_id": None}
        if cloud.report is not None:
            report = cloud.report["cloud"]
            upload = self._apply_folder(apply_id) / "upload"
            _remove(upload)
            _copy(cloud.root / cloud.report_path, upload)
            (upload / "definition.pbir").write_bytes(cloud.original_pbir)
            try:
                self.cloud.update_report(report["workspace_id"], report["item_id"], upload)
            except DevCenterError as exc:
                # The model is in the service already: restore it, so that model and report stay one change.
                self._restore_model(apply_id, cloud.model, written.last_schema_update, step)
                raise ApplyFailure(step, "cloud_report_write_failed",
                                   "The Power BI service did not take the report. The model change was undone.",
                                   check="write", recovered=True) from exc
            reply["report_item_id"] = report["item_id"]
        return reply

    def _restore_model(self, apply_id: str, model: Mapping[str, Any], expected: str | None, step: str) -> str:
        cloud = model["cloud"]
        try:
            return self.cloud.deploy_model(cloud["workspace_name"], cloud["item_id"],
                                           self._apply_folder(apply_id) / "backup" / "model" / "definition", expected).last_schema_update
        except CloudReadFailed as exc:
            raise _deploy_failure(step, exc) from exc

    @staticmethod
    def index(model: LocalSource, report: LocalSource | None) -> dict[str, Any]:
        """The object index of a cloud target: the model rows and the report rows (two sources in the service)."""

        index = dict(object_index(model))
        if report is not None:
            index.update(object_index(report))
        return index

    def reread(self, cloud: SimpleNamespace) -> dict[str, Any]:
        """The rescan: read the model and the report from the service again."""

        model = self.cloud._fresh(self.devcenter, cloud.model)[0]
        report = self.cloud._fresh(self.devcenter, cloud.report)[0] if cloud.report is not None else None
        return self.index(model, report)

    # Undo ----------------------------------------------------------------------------

    def backup_present(self, record: Mapping[str, Any]) -> bool:
        return (self._apply_folder(record["apply_id"]) / "backup" / "model" / "definition").is_dir()

    def undo(self, record: Mapping[str, Any], cloud: SimpleNamespace, step: str) -> list[str]:
        """Deploy the backup again. Stop when the model in the service changed after the apply."""

        written = record["cloud"]
        if cloud.stamp is not None and cloud.stamp != written["last_schema_update"]:
            raise ApplyFailure(step, "target_changed", "The model in the service changed after the apply. The app cannot undo it.",
                               check="write")
        self._restore_model(record["apply_id"], cloud.model, written["last_schema_update"], step)
        restored = ["model"]
        if written.get("report_item_id") and cloud.report is not None:
            report = cloud.report["cloud"]
            try:
                self.cloud.update_report(report["workspace_id"], report["item_id"], self._apply_folder(record["apply_id"]) / "backup" / "report")
            except DevCenterError as exc:
                raise ApplyFailure(step, "cloud_report_write_failed", "The Power BI service did not take the report backup.",
                                   check="write") from exc
            restored.append("report")
        return restored
