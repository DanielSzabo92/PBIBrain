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


if __name__ == "__main__":
    unittest.main()
