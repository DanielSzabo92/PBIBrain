"""Packaged agent entry point: discover a project and share its live desktop API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote

from backend.cli.main import _parser, _write_stdout_utf8
from backend.mcp_server import BrainClient


def project_arguments(argv: list[str]) -> list[str]:
    selector = argparse.ArgumentParser(add_help=False)
    selector.add_argument("--project", help="Power BI project folder")
    selected, remaining = selector.parse_known_args(argv)
    explicit_config = any(value == "--config" or value.startswith("--config=") for value in remaining)
    if selected.project and explicit_config:
        selector.error("Use either --project or --config")
    if explicit_config:
        return remaining
    if selected.project:
        config = Path(selected.project).resolve() / ".pbibrain" / "brain.json"
        return ["--config", str(config), *remaining]
    current = Path.cwd()
    for folder in (current, *current.parents):
        config = folder / ".pbibrain" / "brain.json"
        if config.is_file():
            return ["--config", str(config), *remaining]
    return remaining


def live_client(config_path: Path) -> BrainClient | None:
    marker = config_path.parent / "connection.json"
    if not marker.exists():
        return None
    try:
        connection = json.loads(marker.read_text(encoding="utf-8"))
        if Path(connection["config_path"]).resolve() != config_path.resolve():
            raise ValueError("Project connection points to another configuration")
        client = BrainClient(connection["url"])
        # The process may have crashed and its port may now belong to another
        # project. A generation check prevents silently reading the wrong graph.
        with client.opener.open(client.url + "/desktop/session", timeout=3) as response:
            session = json.load(response)
        if (session.get("session_id") != connection["session_id"]
                or not connection["session_id"]
                or Path(session["project"]["config_path"]).resolve() != config_path.resolve()):
            raise ValueError("Project connection is stale")
        client.session_id = connection["session_id"]
        return client
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("The saved app connection is unavailable. Reopen this project in PBIBrain, then retry.") from exc


def main(argv: list[str] | None = None) -> int:
    arguments = project_arguments(list(sys.argv[1:] if argv is None else argv))
    parser = _parser()
    parser.description += "; --project FOLDER selects a desktop project (otherwise discovered from the current folder)"
    args = parser.parse_args(arguments)
    try:
        client = live_client(Path(args.config).resolve())
        if client is None:
            from backend.cli.main import main as cli_main
            return cli_main(arguments)
        if args.db or args.identity:
            raise ValueError("Storage overrides cannot be used while this project is open in PBIBrain")
        if args.command == "mcp":
            from backend.mcp_server import run
            run(client.url, session_id=client.session_id)
            return 0
        if args.command == "status":
            overview = client.get("overview")
            payload = {**overview["counts"], "storage": overview["storage"]}
            if not args.as_json:
                _write_stdout_utf8(f"nodes={payload['nodes']} edges={payload['edges']}\n")
                return 0
        elif args.command == "config":
            payload = client.get("config")
        elif args.command == "search":
            payload = client.get("objects", query=args.query)
        elif args.command == "retrieve":
            payload = client.get("search", q=args.query, model_id=args.model_id,
                                 report_id=args.report_id, object_type=args.object_type,
                                 limit=args.limit, offset=args.offset)
        elif args.command == "object":
            payload = client.get("objects/" + quote(args.object_id, safe=""))
        elif args.command == "context":
            payload = client.get("context", target=args.target, task=args.task)
        else:
            raise ValueError("Close this project in PBIBrain before running this direct database command")
        _write_stdout_utf8(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
