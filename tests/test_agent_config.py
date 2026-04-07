import importlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch


class AgentConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent_module = importlib.import_module("mcp_server.agent")

    def test_repo_root_env_is_preferred(self) -> None:
        candidates = [
            self.agent_module.REPO_ROOT / ".env",
            self.agent_module.PACKAGE_DIR / ".env",
        ]
        calls = []

        def fake_load_dotenv(*, dotenv_path):
            calls.append(Path(dotenv_path))

        with patch.object(self.agent_module, "load_dotenv", fake_load_dotenv):
            with patch.object(Path, "exists", autospec=True, side_effect=lambda p: p == candidates[0]):
                self.agent_module._load_env()

        self.assertEqual(calls, [candidates[0]])

    def test_package_env_is_used_as_fallback(self) -> None:
        candidates = [
            self.agent_module.REPO_ROOT / ".env",
            self.agent_module.PACKAGE_DIR / ".env",
        ]
        calls = []

        def fake_load_dotenv(*, dotenv_path):
            calls.append(Path(dotenv_path))

        with patch.object(self.agent_module, "load_dotenv", fake_load_dotenv):
            with patch.object(Path, "exists", autospec=True, side_effect=lambda p: p == candidates[1]):
                self.agent_module._load_env()

        self.assertEqual(calls, [candidates[1]])

    def test_explicit_mcp_server_url_wins(self) -> None:
        env = {
            "MCP_SERVER_URL": "http://example.test:9090/custom",
            "WORKSPACE_MCP_BASE_URI": "http://localhost",
            "WORKSPACE_MCP_PUBLIC_PORT": "8080",
            "WORKSPACE_MCP_PORT": "8000",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                self.agent_module._get_mcp_server_url(),
                "http://example.test:9090/custom",
            )

    def test_derived_mcp_server_url_uses_public_port(self) -> None:
        env = {
            "WORKSPACE_MCP_BASE_URI": "http://localhost",
            "WORKSPACE_MCP_PUBLIC_PORT": "8080",
            "WORKSPACE_MCP_PORT": "8000",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                self.agent_module._get_mcp_server_url(),
                "http://localhost:8080/mcp",
            )


if __name__ == "__main__":
    unittest.main()
