"""Optional MCP adapter registration contract."""

from __future__ import annotations

import importlib.util
import unittest

from backend.mcp_server import create_server


@unittest.skipUnless(importlib.util.find_spec("mcp"), "optional MCP SDK is not installed")
class MCPAdapterTests(unittest.TestCase):
    def test_all_read_only_tools_register_with_installed_sdk(self) -> None:
        server = create_server("http://127.0.0.1:8766")
        tools = server._tool_manager.list_tools()
        self.assertEqual(
            {tool.name for tool in tools},
            {"brain_overview", "brain_search", "brain_object", "brain_context", "brain_graph", "brain_impact", "brain_compare", "brain_commonality", "brain_pending_changes",
             "session_get", "compare_rows_list", "impact_get", "naming_rules_get", "name_propose", "proposal_submit",
             "question_ask", "plan_validate"},
        )


class _Client:
    def __init__(self, app_url):
        self.app_url = app_url

    def get(self, path, **params):
        return {"object": {"id": "measure:Sales/Net Sales", "name": "Net Sales"}}


class ObjectLinkTests(unittest.TestCase):
    """Finding 10: an object reply links to the object's page in the open app."""

    def tool(self, client):
        from backend.tool_registry import brain_tools

        return {tool.__name__: tool for tool in brain_tools(client, lambda: {"source": "app"})}["brain_object"]

    def test_object_reply_links_to_its_page_while_the_app_is_open(self) -> None:
        reply = self.tool(_Client("http://127.0.0.1:8000"))("measure:Sales/Net Sales")
        self.assertEqual(reply["app_link"], "http://127.0.0.1:8000/#/inspector/measure%3ASales%2FNet%20Sales")

    def test_no_link_without_an_open_app(self) -> None:
        self.assertNotIn("app_link", self.tool(_Client(None))("measure:Sales/Net Sales"))


if __name__ == "__main__":
    unittest.main()
