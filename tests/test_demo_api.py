"""Integration tests for the web demo.

Real: FastAPI app, the repo's ADK agent, LiteLLM, the MCP transport and the mock Workspace MCP server.
Stubbed: only the LLM endpoint (a tiny OpenAI-compatible server that issues one tool call, then answers
from the tool result), so no provider key is needed.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from demo_api import guard  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _LLM(BaseHTTPRequestHandler):
    tool_name = "get_events"
    tool_args: dict = {}
    seen: list = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        type(self).seen.append(self.headers.get("authorization", ""))
        msgs = body.get("messages", [])
        last = msgs[-1] if msgs else {}
        if last.get("role") == "tool":
            content = last.get("content")
            text = content if isinstance(content, str) else json.dumps(content)
            message = {"role": "assistant", "content": f"Here is what I found: {text[:400]}"}
            finish = "stop"
        elif body.get("tools"):
            names = [t["function"]["name"] for t in body["tools"]]
            assert type(self).tool_name in names, names
            message = {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "call_1", "type": "function",
                                "function": {"name": type(self).tool_name, "arguments": json.dumps(type(self).tool_args)}}],
            }
            finish = "tool_calls"
        else:
            message = {"role": "assistant", "content": "ok"}
            finish = "stop"
        payload = {"id": "x", "object": "chat.completion", "created": 0, "model": body.get("model", "auto"),
                   "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                   "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def mock_mcp():
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "demo_api.mock_workspace_mcp"], cwd=str(ROOT),
                            env={**__import__("os").environ, "MOCK_MCP_PORT": str(port)})
    deadline = time.time() + 40
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            break
        except OSError:
            time.sleep(0.4)
    else:
        proc.kill()
        pytest.fail("mock MCP server did not start")
    yield f"http://127.0.0.1:{port}/mcp"
    proc.kill()


@pytest.fixture()
def stub_llm():
    server = HTTPServer(("127.0.0.1", 0), _LLM)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _LLM.tool_name, _LLM.tool_args, _LLM.seen = "get_events", {}, []
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


@pytest.fixture()
def client(monkeypatch, mock_mcp, stub_llm):
    monkeypatch.setattr(guard, "UPSTASH_URL", "")
    guard._mem.clear()
    monkeypatch.setenv("LLM_BASE_URL", stub_llm)
    monkeypatch.setenv("LLM_API_KEY", "gateway-key")
    monkeypatch.setenv("MOCK_MCP_EXTERNAL", "1")
    from demo_api import app as app_module

    monkeypatch.setattr(app_module, "MOCK_URL", mock_mcp)
    app_module._turns.clear()
    return TestClient(app_module.app)


def test_agent_calls_mock_tools_end_to_end(client):
    r = client.post("/chat", json={"message": "What is on my calendar this week?"})
    assert r.status_code == 200, r.text
    data = r.json()
    names = [s["name"] for s in data["steps"]]
    assert "get_events" in names
    result = next(s for s in data["steps"] if s["type"] == "tool_result")
    assert "Weekly planning" in result["output"]
    assert "Weekly planning" in data["reply"]
    assert data["sessionId"]
    assert _LLM.seen and _LLM.seen[0] == "Bearer gateway-key"


def test_message_is_validated_and_limits_apply(client, monkeypatch):
    assert client.post("/chat", json={"message": "  "}).status_code == 400
    monkeypatch.setattr(guard, "PER_IP_DAILY", 3)
    assert client.post("/chat", json={"message": "calendar?"}).status_code == 200
    assert client.post("/chat", json={"message": "calendar?"}).status_code == 429


def test_turn_cap_per_session(client):
    from demo_api import app as app_module

    sid = "abcdef123456abcdef123456"
    app_module._turns[sid] = app_module.MAX_TURNS_PER_SESSION
    r = client.post("/chat", json={"message": "hi", "sessionId": sid})
    assert r.status_code == 429


def test_mock_server_isolates_sessions_and_never_sends():
    from demo_api import mock_workspace_mcp as m

    def ctx(sid):
        return SimpleNamespace(headers={"x-demo-session": sid})

    a, b = ctx("session-a"), ctx("session-b")
    assert "Created" not in m.get_events(b, query="Launch party")
    m.create_event(a, "Launch party", "2099-01-01T10:00:00Z", "2099-01-01T11:00:00Z")
    assert "Launch party" in m.get_events(a, time_max="2100-01-01T00:00:00Z", query="Launch party")
    assert "No events" in m.get_events(b, time_max="2100-01-01T00:00:00Z", query="Launch party")
    out = m.send_gmail_message(a, "x@y.example", "Hi", "body")
    assert "not actually sent" in out
    assert m.snapshot_outbox("session-a")[0]["to"] == "x@y.example" and m.snapshot_outbox("session-b") == []


def test_existing_agent_config_still_builds_gemini_by_default(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    from mcp_server import agent

    assert agent._build_model() == "gemini-2.5-flash"
