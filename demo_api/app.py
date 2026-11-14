"""Google Workspace Assistant demo API.

POST /chat runs the repo's real ADK agent (``mcp_server.agent.build_agent``) with:
  * its model routed through the private FreeLLMAPI gateway (LiteLLM, OpenAI-compatible), and
  * its MCP tools served by the bundled MOCK Workspace MCP server (``mock_workspace_mcp``) on sample data.
Each request returns the reply plus the tool calls the agent made, so the UI can show what happened.
LLM calls are traced to LangSmith (guarded() trace + LiteLLM callback).
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DEMO_PROJECT", "workspace")
os.environ.setdefault("LANGSMITH_PROJECT", "workspace-demo")

from fastapi import Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from . import guard, llm  # noqa: E402
from .base import create_app, guarded  # noqa: E402

MOCK_PORT = int(os.environ.get("MOCK_MCP_PORT", "8081"))
MOCK_URL = os.environ.get("MOCK_MCP_URL", f"http://127.0.0.1:{MOCK_PORT}/mcp")
APP_NAME = "workspace_demo"
MAX_MESSAGE = 500
MAX_TURNS_PER_SESSION = 30
MAX_LLM_CALLS = 8

_mock_proc: subprocess.Popen | None = None
_session_service = None
_turns: dict[str, int] = {}


def _start_mock() -> None:
    global _mock_proc
    if os.environ.get("MOCK_MCP_EXTERNAL") == "1":
        return
    env = {**os.environ, "MOCK_MCP_PORT": str(MOCK_PORT)}
    _mock_proc = subprocess.Popen([sys.executable, "-m", "demo_api.mock_workspace_mcp"], cwd=str(ROOT), env=env)


def _enable_litellm_tracing() -> None:
    if llm.tracing_enabled():
        try:
            import litellm

            litellm.success_callback = ["langsmith"]
            litellm.failure_callback = ["langsmith"]
        except Exception:  # noqa: BLE001 - tracing must never block startup
            pass


def _on_startup() -> None:
    _start_mock()
    _enable_litellm_tracing()


app = create_app("Google Workspace Assistant demo API", on_startup=_on_startup)


def _sessions():
    global _session_service
    if _session_service is None:
        from google.adk.sessions import InMemorySessionService

        _session_service = InMemorySessionService()
    return _session_service


def _model_for_request():
    """Gateway by default; a visitor-supplied key/base URL (validated in guarded()) via llm.byo()."""
    from mcp_server.agent import _build_model

    base = llm._byo_url.get() or os.environ.get("LLM_BASE_URL", "")
    key = llm._byo_key.get() or os.environ.get("LLM_API_KEY", "")
    if not base:
        raise llm.LLMUnavailable("The LLM gateway is not ready yet. Try again in a few seconds.")
    return _build_model(base_url=base, api_key=key)


def _short(value: Any, n: int = 700) -> str:
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= n else text[:n] + "..."


async def _chat(session_id: str, message: str) -> dict[str, Any]:
    from google.adk.agents.run_config import RunConfig
    from google.adk.runners import Runner
    from google.genai import types

    from mcp_server.agent import build_agent

    agent = build_agent(model=_model_for_request(), mcp_url=MOCK_URL, extra_headers={"X-Demo-Session": session_id})
    service = _sessions()
    user_id = session_id
    if await service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id) is None:
        await service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=service)

    steps: list[dict[str, Any]] = []
    reply = ""
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
            run_config=RunConfig(max_llm_calls=MAX_LLM_CALLS),
        ):
            for call in event.get_function_calls() or []:
                steps.append({"type": "tool_call", "name": call.name, "args": dict(call.args or {})})
            for resp in event.get_function_responses() or []:
                out = resp.response
                if isinstance(out, dict) and "result" in out:
                    out = out["result"]
                steps.append({"type": "tool_result", "name": resp.name, "output": _short(out)})
            if event.is_final_response() and event.content and event.content.parts:
                reply = "".join(p.text or "" for p in event.content.parts if getattr(p, "text", None)).strip()
    finally:
        for tool in agent.tools:
            close = getattr(tool, "close", None)
            if close:
                try:
                    await close()
                except Exception:  # noqa: BLE001
                    pass
    if not reply:
        raise llm.LLMUnavailable("The model returned no answer. Try rephrasing or try again in a minute.")
    return {"reply": reply, "steps": steps}


@app.post("/chat")
async def chat(req: Request):
    try:
        body = await req.json()
    except Exception:  # noqa: BLE001
        body = {}
    message = str((body or {}).get("message") or "").strip()[:MAX_MESSAGE]
    if not message:
        return JSONResponse({"error": "Type a message for the assistant."}, status_code=400)
    sid = (body or {}).get("sessionId")
    session_id = sid if isinstance(sid, str) and 8 <= len(sid) <= 64 and sid.isalnum() else uuid.uuid4().hex
    if len(_turns) > 5000:  # bound memory
        _turns.clear()
    if _turns.get(session_id, 0) >= MAX_TURNS_PER_SESSION:
        return JSONResponse({"error": "Demo conversation limit reached. Start a new session (reload the page).", "sessionId": session_id}, status_code=429)
    _turns[session_id] = _turns.get(session_id, 0) + 1

    def run():
        out = asyncio.run(_chat(session_id, message))
        out["sessionId"] = session_id
        return out

    return await guarded(req, 3, run, name="workspace.chat")
