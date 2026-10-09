"""Trusted human/controller CLI. Every result is machine-readable JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence
from backend.snapshots.manifest import canonical_json
from .orchestrator import ChangeGuard
from .workspace import DockerIsolation

EXIT_CODES = {"SUCCESS": 0, "INVALID_INPUT": 2, "UNAUTHORIZED_MUTATION": 3, "SOURCE_INTEGRITY_FAILURE": 4,
              "USER_REJECTED": 3, "REVIEW_STALE": 7,
              "STRUCTURAL_VALIDATION_FAILURE": 4, "REQUIRED_RUNTIME_NOT_VERIFIED": 5, "MISSING_APPROVAL": 6,
              "INCONCLUSIVE": 7, "BASELINE_STALE": 8, "PROMOTION_RECOVERY_REQUIRED": 9}


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(canonical_json({"guard_api_version": 1, "ok": False, "error": {"code": "INVALID_INPUT", "message": message}}))
        raise SystemExit(2)


def main(argv: Sequence[str] | None = None) -> int:
    parser = JSONArgumentParser(prog="pbi-guard")
    parser.add_argument("--source", required=True, help="Dedicated Power BI project root")
    parser.add_argument("--state", required=True, help="Trusted state directory outside sources")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--identity-file", help="Existing authoritative identity mapping, read only")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("snapshot")
    prepare = commands.add_parser("prepare")
    prepare.add_argument("contract")
    for name in ("verify", "report", "promote", "recover", "retry"):
        command = commands.add_parser(name)
        command.add_argument("operation_id")
        if name == "promote": command.add_argument("--mode", choices=["local", "git"], default="local")
    authorize = commands.add_parser("authorize")
    authorize.add_argument("operation_id")
    authorize.add_argument("--purpose", required=True, choices=["CONTRACT", "HIGH_RISK_PROMOTION", "UNEXPECTED_BEHAVIOR", "PROMOTE"])
    for name in ("accept", "reject"):
        decision = commands.add_parser(name)
        decision.add_argument("operation_id")
        decision.add_argument("--binding", required=True, help="Saved review_binding JSON from the reviewed proposal")
        if name == "accept":
            decision.add_argument("--approval", action="append", required=True, choices=["HIGH_RISK_PROMOTION", "UNEXPECTED_BEHAVIOR", "PROMOTE"])
            decision.add_argument("--mode", choices=["local", "git"], default="local")
    agent = commands.add_parser("run-agent")
    agent.add_argument("operation_id")
    agent.add_argument("--backend", choices=["docker", "windows"], default="docker")
    agent.add_argument("--image")
    agent.add_argument("--runtime-root", action="append", default=[])
    agent.add_argument("agent_command", nargs=argparse.REMAINDER)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8051)
    args = parser.parse_args(argv)
    try:
        guard = ChangeGuard(args.source, args.state, args.project_id, identity_path=args.identity_file)
        if args.command == "snapshot":
            result = guard.capture_baseline().to_dict()
        elif args.command == "prepare":
            result = guard.prepare_change(json.loads(Path(args.contract).read_text(encoding="utf-8-sig")))
        elif args.command == "verify":
            result = guard.validate_candidate(args.operation_id)
        elif args.command == "report":
            result = guard.review(args.operation_id)
        elif args.command == "authorize":
            result = guard.authorize(args.operation_id, args.purpose)
        elif args.command == "accept":
            binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
            guard.accept_candidate(args.operation_id, binding, args.approval)
            result = guard.promote_candidate(args.operation_id, mode=args.mode, binding=binding)
        elif args.command == "reject":
            result = guard.reject_change(args.operation_id, json.loads(Path(args.binding).read_text(encoding="utf-8-sig")))
        elif args.command == "promote":
            result = guard.promote_candidate(args.operation_id, mode=args.mode)
        elif args.command == "recover":
            result = guard.recover_promotion(args.operation_id)
        elif args.command == "retry":
            result = guard.retry(args.operation_id)
        elif args.command == "serve":
            from .service import serve_guard
            serve_guard(guard, port=args.port)
            return 0
        else:
            command = args.agent_command[1:] if args.agent_command[:1] == ["--"] else args.agent_command
            if args.backend == "windows":
                from .workspace.windows import WindowsAppContainer
                if args.image or not args.runtime_root:
                    raise ValueError("Windows isolation requires read-only runtime roots and no image")
                isolation = WindowsAppContainer(tuple(args.runtime_root))
            else:
                if not args.image or args.runtime_root:
                    raise ValueError("Docker isolation requires a pinned image and no runtime roots")
                isolation = DockerIsolation(args.image)
            result = guard.run_agent(args.operation_id, isolation, command)
        print(canonical_json({"guard_api_version": 1, "ok": True, "result": result}))
        if args.command == "reject":
            return 0
        decision = result.get("decision", {})
        if isinstance(decision, dict):
            if decision.get("decision") == "REJECT":
                return EXIT_CODES.get(decision["blocking_reasons"][0]["code"], 4)
            if decision.get("decision") == "INCONCLUSIVE":
                return 7
            if decision.get("decision") == "APPROVAL_REQUIRED":
                return 6
        return 0
    except Exception as error:
        code = getattr(error, "code", "INVALID_INPUT")
        print(canonical_json({"guard_api_version": 1, "ok": False, "error": {"code": code, "message": str(error)}}))
        return EXIT_CODES.get(code, 2)


if __name__ == "__main__":
    raise SystemExit(main())
