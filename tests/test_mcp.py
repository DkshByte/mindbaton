"""Unit tests for Mindbaton's MCP server implementation."""
import os
import unittest

os.environ["MINDBATON_AI"] = "0"
import server


class TestMCPServer(unittest.TestCase):
    def test_mcp_versions(self):
        self.assertIn("2025-11-25", server.MCP_VERSIONS)
        self.assertIn("2025-06-18", server.MCP_VERSIONS)

    def test_tool_count_and_declaration(self):
        expected_tools = {
            "context", "recall", "remember", "profile",
            "handoff", "sessions", "save_conversation", "forget"
        }
        declared_names = {t["name"] for t in server.MCP_TOOLS}
        self.assertEqual(declared_names, expected_tools)
        self.assertEqual(len(server.MCP_TOOLS), 8)

    def test_all_tools_have_complete_hints(self):
        required_hints = {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"}
        for tool in server.MCP_TOOLS:
            annotations = tool.get("annotations", {})
            self.assertEqual(
                set(annotations.keys()),
                required_hints,
                f"Tool {tool['name']} does not have all 4 required hints: {annotations}"
            )
            for hint, val in annotations.items():
                self.assertIsInstance(val, bool, f"Tool {tool['name']} hint {hint} must be bool, got {type(val)}")

    def test_destructive_hints_are_accurate(self):
        destructive = {t["name"] for t in server.MCP_TOOLS if t["annotations"]["destructiveHint"]}
        self.assertEqual(destructive, {"forget", "save_conversation"})

    def test_open_world_hints_are_accurate(self):
        open_world = {t["name"] for t in server.MCP_TOOLS if t["annotations"]["openWorldHint"]}
        self.assertEqual(open_world, {"handoff"})

    def test_mcp_handle_initialize(self):
        g = server.Graph(":memory:")
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "clientInfo": {"name": "test-client", "version": "1.0"}}
        }
        res = server.mcp_handle(g, req)
        self.assertEqual(res["id"], 1)
        self.assertEqual(res["result"]["protocolVersion"], "2025-11-25")
        self.assertIn("serverInfo", res["result"])
        self.assertEqual(res["result"]["serverInfo"]["name"], "mindbaton")

    def test_mcp_handle_tools_list(self):
        g = server.Graph(":memory:")
        req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        res = server.mcp_handle(g, req)
        self.assertEqual(res["id"], 2)
        tools = res["result"]["tools"]
        self.assertEqual(len(tools), 8)

    def test_mcp_connector_denies_forget(self):
        g = server.Graph(":memory:")
        req = {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}
        res = server.mcp_handle(g, req, connector=True)
        self.assertEqual(res["id"], 3)
        tools = res["result"]["tools"]
        tool_names = {t["name"] for t in tools}
        self.assertNotIn("forget", tool_names)
        self.assertEqual(len(tools), 7)


if __name__ == "__main__":
    unittest.main()
