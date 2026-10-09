"""Owned local Analysis Services test instance and query-only evaluator.

The loader never contacts an existing Desktop model. Its private instance is
loopback-bound, uses temporary storage and dies with the controller process.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
from dataclasses import replace
from xml.sax.saxutils import escape
from backend.snapshots.manifest import content_hash, source_manifest
from backend.adapters.tabular_metadata import TabularMetadataAdapter
from .adapters import Capabilities, RuntimeBinding


class LocalTestInstance:
    def __init__(self, executable: str | Path, *, startup_timeout: int = 30):
        self.executable = Path(executable).resolve(strict=True)
        self.startup_timeout = startup_timeout

    def __enter__(self):
        if os.name != "nt": raise RuntimeError("Installed Windows engine required")
        self.temporary = tempfile.TemporaryDirectory(prefix="pbi-guard-evaluator-")
        root = Path(self.temporary.name)
        directories = {name: root / name for name in ("Data", "Temp", "Log", "Backup")}
        for directory in directories.values(): directory.mkdir()
        configuration = "<ConfigurationSettings>" + "".join(f"<{name}Dir>{escape(str(directory))}</{name}Dir>" for name, directory in directories.items())
        configuration += f"<DeploymentMode>2</DeploymentMode><PrivateProcess>{os.getpid()}</PrivateProcess><InstanceVisible>0</InstanceVisible><Language>1033</Language><Port>0</Port><Network><ListenOnlyOnLocalConnections>1</ListenOnlyOnLocalConnections></Network><Security><RequireClientAuthentication>1</RequireClientAuthentication></Security></ConfigurationSettings>"
        (root / "msmdsrv.ini").write_text(configuration, encoding="utf-8")
        self.process = subprocess.Popen([str(self.executable), "-c", "-s", str(root)], cwd=self.executable.parent,
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            until = time.monotonic() + self.startup_timeout
            while time.monotonic() < until:
                if self.process.poll() is not None: raise RuntimeError("Owned engine exited during startup")
                ports = list(root.rglob("msmdsrv.port.txt"))
                if ports:
                    try:
                        port = int(ports[0].read_bytes().decode("utf-16-le").strip("\0\r\n "))
                        if 1 <= port <= 65535:
                            self.port = port
                            return self
                    except (ValueError, UnicodeError): pass
                time.sleep(0.1)
            raise RuntimeError("Owned engine startup timed out")
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        if self.process.poll() is None:
            # Only this Popen-owned private engine and its descendants are stopped.
            subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], capture_output=True, check=False)
            self.process.wait(timeout=15)
        if self.process.stdin: self.process.stdin.close()
        self.temporary.cleanup()


class LocalAnalysisServices:
    """Bound to one freshly loaded isolated database and enforced reader role."""
    def __init__(self, instance: LocalTestInstance, source: str | Path, snapshot, context, *, evaluator: str | Path | None = None):
        self.instance, self.context = instance, context
        self.evaluator = Path(evaluator) if evaluator else Path(__file__).parent / "dotnet/bin/Release/net8.0/RuntimeEvaluator.dll"
        if not self.evaluator.is_file(): raise RuntimeError("Build trusted runtime evaluator")
        if context.role is not None or context.culture != "en-US" or any(json.loads(value) for value in (context.parameters_json, context.filter_context_json, context.calculation_configuration_json)) or context.evaluation_time is not None:
            raise ValueError("Local adapter currently supports parameter-free en-US reader context only")
        self.database_id = "guard_" + uuid.uuid4().hex
        root = Path(source).resolve(strict=True)
        snapshot_value = snapshot.to_dict() if hasattr(snapshot, "to_dict") else snapshot
        if source_manifest(root) != snapshot_value["source_manifest"]: raise ValueError("Loader source differs from pinned snapshot")
        metadata = snapshot_value["analysis"]["tabular_metadata"]
        if len(metadata) != 1: raise ValueError("One isolated semantic model required per local adapter")
        relative, record = next(iter(metadata.items()))
        model_path = root / relative
        model_path = model_path / "definition" if (model_path / "definition").is_dir() else model_path / "model.bim"
        current = TabularMetadataAdapter().read(model_path)
        if current["database"] != record["database"]: raise ValueError("Loader metadata differs from pinned snapshot")
        self.model = current["database"]["model"]
        from backend.snapshots.literal_tables import literal_table
        if self.model.get("dataSources") or self.model.get("roles"):
            raise ValueError("Local literal backend cannot process external data or source roles")
        for table in self.model.get("tables", []):
            partitions = table.get("partitions", [])
            if len(partitions) != 1 or partitions[0].get("source", {}).get("type") != "calculated" or not literal_table(partitions[0]["source"].get("expression", "")):
                raise ValueError("Untrusted nonliteral processing is unavailable in this backend")
        self.source_root, self.source_manifest = root, snapshot_value["source_manifest"]
        self.load_evidence = self._request("load", model_path=str(model_path))
        if source_manifest(root) != snapshot_value["source_manifest"]: raise ValueError("Source changed during loading")
        permission = self._request("permission_probe")
        # The actual engine response must say permission/authorization failed.
        # A bad query, unavailable transport or absent role is not read-only proof.
        error = permission.get("error", "").casefold()
        denied = any(word in error for word in ("permission", "authoriz", "privilege", "access", "jogosults")) or any(item.get("code") == -1055784777 for item in permission.get("errors", []))
        if permission.get("status") != "DENIED" or not permission.get("read_probe") or permission.get("administrator_control") != "PASSED" or permission.get("model_permission") != "Read" or not denied:
            raise RuntimeError("Engine did not prove enforced read-only permissions: " + json.dumps(permission))
        self.permission_evidence = permission
        self.capabilities = Capabilities("LOCAL_ANALYSIS_SERVICES", True, False, False, True, True)
        self.binding = RuntimeBinding(snapshot_value["snapshot_id"], self.database_id, context.context_hash,
                                      content_hash(self.load_evidence), content_hash(permission))

    def _literal_data(self):
        from backend.snapshots.literal_tables import literal_table
        from .comparison import canonical_result
        from backend.snapshots.manifest import canonical_json
        if source_manifest(self.source_root) != self.source_manifest:
            raise ValueError("Pinned runtime source changed")
        if self.model.get("dataSources") or self.model.get("roles"):
            raise ValueError("Literal freeze does not certify external data or security roles")
        definitions, processed = {}, {}
        for table in self.model.get("tables", []):
            partitions = table.get("partitions", [])
            if len(partitions) != 1 or partitions[0].get("source", {}).get("type") != "calculated":
                raise ValueError("Literal data freeze requires one constant partition per table")
            expression = partitions[0]["source"].get("expression", "")
            literal = literal_table(expression)
            if not literal or set(literal["columns"]) != {column["name"] for column in table.get("columns", [])}:
                raise ValueError("Unproven calculated-table source")
            name = table["name"].replace("'", "''")
            columns = sorted(literal["columns"])
            projection = ",".join(json.dumps(column) + ", '" + name + "'[" + column.replace("]", "]]") + "]" for column in columns)
            result = canonical_result(self.execute_readonly("EVALUATE SELECTCOLUMNS(ALLNOBLANKROW('" + name + "')," + projection + ")"))
            if len(result["rows"]) != literal["row_count"]:
                raise ValueError("Processed data differs from literal row count")
            result["rows"] = sorted(result["rows"], key=canonical_json)
            definitions[table["name"]] = {"expression": expression, "columns": table["columns"]}
            processed[table["name"]] = content_hash(result)
        if not definitions:
            raise ValueError("No literal data to certify")
        return {"rule": "SEALED_LITERAL_DATA_V1", "definition_hash": content_hash(definitions), "processed_hash": content_hash(processed), "table_hashes": processed}

    @staticmethod
    def freeze_literal_pair(before, after):
        if before.context != after.context:
            raise ValueError("Execution contexts differ")
        records = [adapter._literal_data() for adapter in (before, after)]
        if records[0] != records[1]:
            raise ValueError("Processed data or literal definitions differ")
        context = replace(before.context, data_snapshot_id=records[0]["definition_hash"], processed_state_id=records[0]["processed_hash"], data_frozen=True)
        for adapter, evidence in zip((before, after), records):
            adapter.freeze_evidence = evidence
            adapter.context = context
            adapter.capabilities = replace(adapter.capabilities, frozen_data=True)
            adapter.binding = replace(adapter.binding, context_hash=context.context_hash,
                load_evidence_hash=content_hash({"load": adapter.load_evidence, "data": evidence}))
        return context

    def verify_frozen_data(self):
        return hasattr(self, "freeze_evidence") and self._literal_data() == self.freeze_evidence

    def _request(self, operation, **payload):
        request = {"operation": operation, "port": self.instance.port, "database_id": self.database_id, **payload}
        result = subprocess.run(["dotnet", str(self.evaluator.resolve())], input=json.dumps(request), capture_output=True, text=True, encoding="utf-8", timeout=90, check=False)
        value = json.loads(result.stdout)
        if result.returncode or value.get("status") not in {"PASSED", "DENIED"}: raise RuntimeError(value.get("error", "Runtime evaluator failed"))
        return value

    def execute_readonly(self, query, params=None):
        if params: raise ValueError("Local query parameters unsupported")
        from .query_coverage import query_targets
        # The independent AST validation precedes the query-only engine call.
        # Server reader permissions remain the mutation security boundary.
        from backend.validation.powerbi import ValidationQuery
        ValidationQuery(query, self.database_id)
        from decimal import Decimal
        from datetime import datetime
        result = self._request("query", query=query)["result"]
        for row in result["rows"]:
            for index, column in enumerate(result["columns"]):
                if row[index] is not None and column["type"] == "Decimal": row[index] = Decimal(row[index])
                if row[index] is not None and column["type"] == "DateTime": row[index] = datetime.fromisoformat(row[index])
        return result
