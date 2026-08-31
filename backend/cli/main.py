"""Minimal Phase 1 ``brain`` command."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Sequence

from backend.graph.repository import GraphRepository
from backend.scanner.pipeline import Scanner


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brain", description="Power BI Brain factual graph")
    parser.add_argument("--db", default="data/brain.lbug", help="Ladybug database path")
    parser.add_argument("--identity", default="config/identity.json", help="generated identity map path")
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    with GraphRepository(args.db) as repository:
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
