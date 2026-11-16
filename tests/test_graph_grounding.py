"""Graph-first answers: one-call dependencies, names resolved before the model starts, the grounding
rules every agent gets, and the Copilot / Antigravity workspace bundle (``brain agent-setup``)."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import urlencode

from backend.agent_rules import GROUNDING_RULES
from backend.agent_setup import MARKER, setup
from backend.api.app import create_app
from backend.api.dependencies import mention_block
from backend.chat.credentials import MemoryStore
from backend.chat.service import ChatService
from backend.graph.loader import build_fact_graph
from backend.graph.repository import GraphRepository
from backend.graph.schema import Node
from backend.sample_project import sample_source
from tests.test_chat import json_post, wait_for_run

SALES_PER_CUSTOMER = "model:sample-retail/table:sample-customers/measure:sample-m-sales-per-customer"
ACTIVE_CUSTOMERS = "model:sample-retail/table:sample-customers/measure:sample-m-active-customers"


def sample_repository(*, twin: bool = False) -> GraphRepository:
    source = sample_source()
    graph = build_fact_graph(source["models"], source["reports"], analyze_dax=True)
    nodes = list(graph.nodes.values()) if isinstance(graph.nodes, dict) else list(graph.nodes)
    edges = list(graph.edges.values()) if isinstance(graph.edges, dict) else list(graph.edges)
    if twin:  # the same measure name in a second model
        nodes.append(Node(id="model:other/table:t/measure:active", type="MEASURE", name="Active Customers", model_id="model:other"))
    repository = GraphRepository(use_native=False)
    repository.replace(nodes, edges)
    return repository


class DependencyRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(sample_repository(), use_native=False)

    def tearDown(self) -> None:
        self.app.close()

    def get(self, **query) -> dict:
        status, reply = self.app.handle("GET", "/api/dependencies?" + urlencode(query))
        self.assertEqual(200, status, reply)
        return reply

    def test_a_name_is_answered_in_one_call(self):
        answer = self.get(target="Sales per Customer", depth=2)
        self.assertEqual("OK", answer["status"])
        self.assertEqual(SALES_PER_CUSTOMER, answer["object"]["id"])
        self.assertEqual("DIVIDE([Sales Amount], [Active Customers])", answer["object"]["expression"])
        names = {(item["name"], item["depth"]) for item in answer["upstream"]}
        self.assertIn(("Active Customers", 1), names)
        self.assertIn(("Customer Key", 2), names)  # read by Active Customers, one level down
        self.assertEqual(["Customers"], [page["name"] for page in answer["report_usage"]])
        self.assertEqual("Retail Performance (sample)", answer["report_usage"][0]["report"])

    def test_brackets_and_direction(self):
        answer = self.get(target="[Active Customers]", direction="downstream")
        self.assertNotIn("upstream", answer)
        self.assertEqual(["Sales per Customer"], [item["name"] for item in answer["downstream"]])
        column = self.get(target="Sales[Customer Key]", direction="downstream")
        self.assertEqual("COLUMN", column["object"]["type"])
        self.assertIn("Active Customers", [item["name"] for item in column["downstream"]])

    def test_unknown_names_are_not_guessed(self):
        answer = self.get(target="Net Promoter Score")
        self.assertEqual("NOT_FOUND", answer["status"])
        self.assertNotIn("upstream", answer)

    def test_a_shared_name_is_ambiguous(self):
        self.app.close()
        self.app = create_app(sample_repository(twin=True), use_native=False)
        answer = self.get(target="Active Customers")
        self.assertEqual("AMBIGUOUS", answer["status"])
        self.assertEqual(2, len(answer["candidates"]))
        scoped = self.get(target="Active Customers", model_id="model:sample-retail")
        self.assertEqual(ACTIVE_CUSTOMERS, scoped["object"]["id"])

    def test_the_tool_wraps_the_route_with_budget_and_freshness(self):
        from backend.chat.service import InProcessClient
        from backend.tool_registry import build_tools

        tools = build_tools(InProcessClient(self.app, self.app.request_lock))
        self.assertEqual("brain_dependencies", next(iter(tools)))
        answer = tools["brain_dependencies"](object="Active Customers")
        self.assertEqual(ACTIVE_CUSTOMERS, answer["object"]["id"])
        self.assertIn("budget", answer)
        self.assertIn("freshness", answer)


class MentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = sample_repository()

    def test_named_objects_come_with_their_dependencies(self):
        block = mention_block(self.repository, "what does sales per customer depend on?")
        self.assertIn(SALES_PER_CUSTOMER, block)
        self.assertIn("Built from: Active Customers (MEASURE), Sales Amount (MEASURE)", block)

    def test_plain_lowercase_words_are_not_objects(self):
        self.assertEqual("", mention_block(self.repository, "show me the sales by customers please"))
        self.assertIn("TABLE Sales", mention_block(self.repository, "Which measures live in Sales?"))

    def test_a_shared_name_is_flagged(self):
        block = mention_block(sample_repository(twin=True), "Where is [Active Customers] used?")
        self.assertIn("AMBIGUOUS", block)


class GroundedProvider:
    """Answers from the <graph> block when it is there; otherwise calls brain_dependencies once."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def test(self):
        return {"ok": True, "message": "ok"}

    def stream(self, *, system, messages, tools, should_stop):
        self.calls.append({"system": system, "messages": json.loads(json.dumps(messages))})
        texts = [block.get("text", "") for block in messages[-1]["content"] if block.get("type") == "text"]
        graph = next((text for text in texts if text.startswith("<graph>")), "")
        if graph:
            answer = "From the graph: " + graph.splitlines()[2][:80]
            yield {"type": "text", "text": answer}
            yield {"type": "message", "content": [{"type": "text", "text": answer}], "stop_reason": "end_turn"}
            return
        yield {"type": "message", "content": [{"type": "tool_use", "id": "d1", "name": "brain_dependencies",
                                               "input": {"object": "Active Customers"}}], "stop_reason": "tool_use"}


class ChatGroundingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(sample_repository(), use_native=False)
        self.provider = GroundedProvider()
        self.app.chat = ChatService(self.app, store=MemoryStore(), provider_factory=lambda settings, key: self.provider,
                                    lock=self.app.request_lock, use_settings_file=False)
        json_post(self.app, "/api/chat/settings", {"enabled": True, "provider": "local", "model": "fake"})

    def tearDown(self) -> None:
        self.app.close()

    def test_a_named_measure_is_answered_without_a_tool_call(self):
        status, reply = json_post(self.app, "/api/chat/start", {"text": "What does Sales per Customer depend on?"})
        self.assertEqual(200, status, reply)
        events = wait_for_run(self.app, reply["run_id"])
        self.assertEqual([], [event for event in events if event["type"] == "tool_call"])
        self.assertIn("Sales per Customer", "".join(event.get("text", "") for event in events))
        system = self.provider.calls[0]["system"]
        self.assertIn(GROUNDING_RULES, system)
        self.assertIn("never read, grep or list project files", system)

    def test_the_mcp_instructions_carry_the_same_rules(self):
        from backend.mcp_server import INSTRUCTIONS

        self.assertTrue(INSTRUCTIONS.startswith(GROUNDING_RULES))
        self.assertIn("brain_dependencies", INSTRUCTIONS)


class AgentSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "Finance"
        (self.root / ".pbibrain").mkdir(parents=True)
        self.config = self.root / ".pbibrain" / "brain.json"
        self.config.write_text('{"version": 1, "sources": []}', encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def read(self, relative: str):
        text = (self.root / relative).read_text(encoding="utf-8")
        return json.loads(text) if relative.endswith(".json") else text

    def test_both_editors_get_the_server_the_agent_and_the_rule(self):
        report = setup(self.config)
        self.assertEqual(str(self.root.resolve()), report["folder"])
        self.assertEqual({"written"}, {item["result"] for item in report["files"]})
        vscode = self.read(".vscode/mcp.json")["servers"]["pbibrain"]
        self.assertEqual("stdio", vscode["type"])
        self.assertIn(str(self.config.resolve()), vscode["args"])
        self.assertEqual(vscode["args"], self.read(".mcp.json")["mcpServers"]["pbibrain"]["args"])
        self.assertEqual(vscode["args"], self.read(".agents/mcp_config.json")["mcpServers"]["pbibrain"]["args"])
        agent = self.read(".github/agents/pbibrain.agent.md")
        self.assertIn("tools: ['pbibrain/*']", agent)
        self.assertIn(GROUNDING_RULES, agent)
        rule = self.read(".agents/rules/pbibrain.md")
        self.assertTrue(rule.startswith("---\ntrigger: always_on\n"))
        self.assertIn(GROUNDING_RULES, rule)

    def test_other_servers_and_hand_edits_are_kept(self):
        (self.root / ".vscode").mkdir()
        (self.root / ".vscode" / "mcp.json").write_text('{"servers": {"github": {"type": "http", "url": "https://x"}}}', encoding="utf-8")
        (self.root / ".mcp.json").write_text("{not json", encoding="utf-8")
        (self.root / ".github" / "agents").mkdir(parents=True)
        (self.root / ".github" / "agents" / "pbibrain.agent.md").write_text("my own agent", encoding="utf-8")
        results = {item["path"]: item["result"] for item in setup(self.config, clients=("copilot",))["files"]}
        self.assertEqual({"github", "pbibrain"}, set(self.read(".vscode/mcp.json")["servers"]))
        self.assertTrue(results[".mcp.json"].startswith("skipped"))
        self.assertEqual("{not json", (self.root / ".mcp.json").read_text(encoding="utf-8"))
        self.assertTrue(results[".github/agents/pbibrain.agent.md"].startswith("skipped"))
        self.assertFalse((self.root / ".agents").exists(), "only the chosen client is written")
        setup(self.config, clients=("copilot",), force=True)
        self.assertIn(MARKER, self.read(".github/agents/pbibrain.agent.md"))

    def test_running_again_updates_in_place(self):
        setup(self.config)
        again = {item["path"]: item["result"] for item in setup(self.config)["files"]}
        self.assertEqual("updated", again[".vscode/mcp.json"])
        self.assertEqual("unchanged", again[".agents/rules/pbibrain.md"])

    def test_the_command_line(self):
        from backend.agent import main

        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["--project", str(self.root), "agent-setup", "--client", "antigravity"])
        self.assertEqual(0, code)
        self.assertEqual({".agents/mcp_config.json", ".agents/rules/pbibrain.md"},
                         {item["path"] for item in json.loads(out.getvalue())["files"]})


if __name__ == "__main__":
    unittest.main()
