"""Local project, retrieval, and inspection commands."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Sequence

from backend.graph.repository import GraphRepository
from backend.scanner.pipeline import Scanner


def _write_stdout_utf8(value: str) -> None:
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(value.encode("utf-8"))
        buffer.flush()
        return
    sys.stdout.write(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brain", description="Power BI Brain factual graph")
    parser.add_argument("--config", default="config/brain.json", help="Brain project configuration file")
    parser.add_argument("--db", default=None, help="override Ladybug database path")
    parser.add_argument("--identity", default=None, help="override generated identity map path")
    parser.add_argument("--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="scan model JSON and optional report JSON")
    scan.add_argument("source", help="model metadata JSON path or JSON text")
    scan.add_argument("--report", action="append", default=None, help="report metadata JSON path or JSON text")

    build = commands.add_parser("build", help="alias for scan")
    build.add_argument("source", help="model metadata JSON path or JSON text")
    build.add_argument("--report", action="append", default=None)

    status = commands.add_parser("status", help="show graph counts")
    status.add_argument("--json", action="store_true", dest="as_json")

    obj = commands.add_parser("object", help="show one canonical object")
    obj.add_argument("object_id")

    search = commands.add_parser("search", help="search canonical objects")
    search.add_argument("query")
    retrieve = commands.add_parser("retrieve", help="ranked, scoped, paginated agent search")
    retrieve.add_argument("query")
    retrieve.add_argument("--model-id")
    retrieve.add_argument("--report-id")
    retrieve.add_argument("--type", dest="object_type")
    retrieve.add_argument("--limit", type=int, default=50)
    retrieve.add_argument("--offset", type=int, default=0)
    context = commands.add_parser("context", help="retrieve evidence for an exact object ID")
    context.add_argument("target")
    context.add_argument("--task", default=None)
    export_markdown = commands.add_parser("export-markdown", help="export the canonical project snapshot as Markdown")
    export_markdown.add_argument("--output", help="create a new Markdown file; stdout when omitted")
    commands.add_parser("project-scan", help="scan all sources in the configured Brain project")
    commands.add_parser("config", help="show resolved project configuration")
    server = commands.add_parser("serve", help="serve the local config, graph UI, and agent API")
    server.add_argument("--port", type=int, default=8000)
    server.add_argument("--ui", default=str(Path(__file__).resolve().parents[2] / "frontend" / "dist"), help="built Inspector directory")
    mcp = commands.add_parser("mcp", help="run optional read-only MCP adapter for a running local server")
    mcp.add_argument("--url", default="http://127.0.0.1:8000")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    if args.command == "mcp":
        from backend.mcp_server import run
        run(args.url)
        return 0
    from backend.projects import ProjectService
    project = ProjectService(args.config)
    config = project.get_config()
    project_paths = project.paths()
    args.db = args.db or str(project_paths["database"])
    args.identity = args.identity or str(project_paths["identity_map"])
    if args.command in {"project-scan", "serve"} and (
        Path(args.db).resolve() != project_paths["database"]
        or Path(args.identity).resolve() != project_paths["identity_map"]
    ):
        parser.error(f"{args.command} uses storage paths from --config; remove --db/--identity overrides")
    if args.command == "config":
        print(json.dumps(config, ensure_ascii=False, indent=2))
        return 0
    if args.command == "serve":
        from backend.api.app import serve
        serve(port=args.port, database_path=args.db, overrides_path=Path(args.identity).with_name("overrides.json"), config_path=args.config, static_dir=args.ui)
        return 0
    export_output = None
    if args.command == "export-markdown" and args.output:
        from backend.documentation_export import UnsafeExportPathError, validate_output_path

        try:
            export_output = validate_output_path(
                args.output,
                config_path=project.config_path,
                database_paths=(project_paths["database"], args.db),
                identity_paths=(project_paths["identity_map"], args.identity),
                source_paths=project.source_paths(),
            )
        except UnsafeExportPathError as exc:
            parser.error(str(exc))
    with GraphRepository(args.db) as repository:
        if args.command == "project-scan":
            result = project.scan(repository)
            print(json.dumps({"nodes": len(result.graph.nodes), "edges": len(result.graph.edges), "sources": result.source_count}, sort_keys=True))
            return 0
        if args.command in {"retrieve", "context"}:
            from backend.api.review import OverrideStore
            store = OverrideStore(Path(args.identity).with_name("overrides.json"))
            if args.command == "retrieve":
                from backend.api.retrieval import retrieve_objects
                payload = retrieve_objects(repository, args.query, model_id=args.model_id, report_id=args.report_id, object_type=args.object_type, limit=args.limit, offset=args.offset, store=store)
            else:
                from backend.context import get_context
                payload = get_context(repository, args.target, args.task, store=store)
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "export-markdown":
            from backend.documentation_export import render_markdown, write_markdown

            markdown = render_markdown(repository, project_name=config["name"])
            if export_output is None:
                _write_stdout_utf8(markdown)
                return 0
            try:
                write_markdown(export_output, markdown)
            except FileExistsError:
                parser.error(f"Export output already exists: {export_output}")
            except OSError as exc:
                parser.error(f"Cannot create export output {export_output}: {exc}")
            print(str(export_output))
            return 0
        if args.command in {"scan", "build"}:
            graph = Scanner(repository, identity_path=args.identity).scan(args.source, args.report)
            print(json.dumps({"nodes": len(graph.nodes), "edges": len(graph.edges), "database": args.db}, sort_keys=True))
            return 0
        if args.command == "status":
            payload = {"nodes": len(repository.nodes), "edges": len(repository.edges), "storage": repository.storage}
            print(json.dumps(payload, sort_keys=True) if args.as_json else f"nodes={payload['nodes']} edges={payload['edges']}")
            return 0
        if args.command == "object":
            value = repository.get_object(args.object_id)
            if value is None:
                parser.error(f"object not found: {args.object_id}")
            print(json.dumps(value.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "search":
            print(json.dumps([value.to_dict() for value in repository.search_objects(args.query)], ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        parser.error("unknown command")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
