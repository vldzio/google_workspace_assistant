"""Google Workspace Assistant demo API.

POST /chat runs the repo's real ADK agent (``mcp_server.agent.build_agent``) with:
  * its model routed through the private FreeLLMAPI gateway (LiteLLM, OpenAI-compatible), and
  * its MCP tools served by the bundled MOCK Workspace MCP server (``mock_workspace_mcp``) on sample data.
Each request returns the reply plus the tool calls the agent made, so the UI can show what happened.
LLM calls are traced to LangSmith (guarded() trace + LiteLLM callback).
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("demo_api")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DEMO_PROJECT", "workspace")
os.environ.setdefault("LANGSMITH_PROJECT", "workspace-demo")

from fastapi import Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from . import guard, llm  # noqa: E402
from .base import create_app, guarded  # noqa: E402
from .reply import clean_reply  # noqa: E402

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


# The gateway routes the virtual model "auto"; a visitor's own provider needs a real tool-calling model name.
BYO_DEFAULT_MODELS = {
    "api.openai.com": "gpt-4o-mini",
    "api.groq.com": "llama-3.3-70b-versatile",
    "openrouter.ai": "meta-llama/llama-3.3-70b-instruct:free",
    "generativelanguage.googleapis.com": "gemini-2.5-flash",
    "api.mistral.ai": "mistral-small-latest",
    "api.cerebras.ai": "gpt-oss-120b",
}


def _model_for_request():
    """Gateway by default; a visitor-supplied key/base URL (validated in guarded()) via llm.byo()."""
    from urllib.parse import urlparse

    from mcp_server.agent import _build_model

    byo_url = llm._byo_url.get()
    base = byo_url or os.environ.get("LLM_BASE_URL", "")
    key = llm._byo_key.get() or os.environ.get("LLM_API_KEY", "")
    if not base:
        raise llm.LLMUnavailable("The LLM gateway is not ready yet. Try again in a few seconds.")
    model_id = ""
    if byo_url:  # own provider: pick a real model there (env BYO_MODEL_ID overrides for any host)
        model_id = os.environ.get("BYO_MODEL_ID") or BYO_DEFAULT_MODELS.get(urlparse(byo_url).hostname or "", "")
    return _build_model(base_url=base, api_key=key, model_id=model_id)


def _short(value: Any, n: int = 700) -> str:
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= n else text[:n] + "..."


async def _chat(session_id: str, message: str) -> dict[str, Any]:
    from google.adk.agents.run_config import RunConfig
    from google.adk.runners import Runner
    from google.genai import types

    from mcp_server.agent import build_agent

    agent = build_agent(model=_model_for_request(), mcp_url=MOCK_URL, extra_headers={"X-Demo-Session": session_id})
    # models do not know today's date; the sample events are relative to it, so tell the agent
    now = datetime.now(timezone.utc)
    agent.instruction = f"{agent.instruction} Today is {now:%A %Y-%m-%d}, the time is {now:%H:%M} UTC. Use UTC for all times."
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
    except llm.LLMUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - upstream model/gateway failure, not a server bug
        log.exception("agent run failed")
        name = type(exc).__name__.lower()
        if "authentication" in name or "permissiondenied" in name:
            msg = "Your API key was rejected by the provider. Check the key and the provider you selected."
        elif "notfound" in name:
            msg = "The provider does not offer the model this demo picked. Try another provider, or ask the maintainer to set BYO_MODEL_ID."
        elif "ratelimit" in name or "rate" in str(exc).lower()[:200]:
            msg = "The free models are busy right now. Try again in a few minutes, or add your own API key."
        else:
            msg = "The model call failed. Try again in a minute."
        raise llm.LLMUnavailable(msg) from exc
    finally:
        for tool in agent.tools:
            close = getattr(tool, "close", None)
            if close:
                try:
                    await close()
                except Exception:  # noqa: BLE001
                    pass
    reply = clean_reply(reply)
    if not reply:
        raise llm.LLMUnavailable("The model returned no answer. Try rephrasing or try again in a minute.")
    return {"reply": reply, "steps": steps}


@app.get("/sample-data")
def sample_data() -> dict[str, Any]:
    """The fictional starting data every visitor session is seeded with, so the UI can show what can be asked."""
    from .mock_workspace_mcp import seed

    data = seed()
    data.pop("outbox", None)
    return data


@app.get("/session-data")
async def session_data(sessionId: str = "") -> JSONResponse:
    """Current state of this visitor's sample data, including anything the agent created or sent."""
    import httpx

    if not (sessionId.isalnum() and 8 <= len(sessionId) <= 64):
        return JSONResponse(sample_data())
    base = MOCK_URL.rsplit("/mcp", 1)[0]
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{base}/state/{sessionId}")
            r.raise_for_status()
            return JSONResponse(r.json())
    except Exception:  # noqa: BLE001 - the panel is informational; never fail the page over it
        return JSONResponse(sample_data())


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
