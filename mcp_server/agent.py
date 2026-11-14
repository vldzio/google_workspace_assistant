"""ADK entrypoint for a local Google Workspace MCP-backed agent.

This package expects a local `workspace-mcp` server to be available at the
configured Streamable HTTP endpoint, typically `http://localhost:8080/mcp`.
For the local flow documented in this repo, the MCP server should run with
`MCP_ENABLE_OAUTH21=false`.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)


PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
DEFAULT_PUBLIC_MCP_PORT = "8080"
DEFAULT_MCP_SERVER_URL = f"http://localhost:{DEFAULT_PUBLIC_MCP_PORT}/mcp"


def _load_env() -> None:
    if load_dotenv is None:
        return

    # Prefer the repo root because `adk web` is typically started from there.
    for candidate in (REPO_ROOT / ".env", PACKAGE_DIR / ".env"):
        if candidate.exists():
            load_dotenv(dotenv_path=candidate)
            break


def _normalize_mcp_url(base_url: str, port: str) -> str:
    parsed = urlsplit(base_url)
    hostname = parsed.hostname or "localhost"
    scheme = parsed.scheme or "http"
    path = parsed.path or "/mcp"
    if not path.startswith("/"):
        path = f"/{path}"
    netloc = f"{hostname}:{port}" if port else hostname
    return urlunsplit((scheme, netloc, path, "", ""))


def _get_mcp_server_url() -> str:
    explicit_url = os.getenv("MCP_SERVER_URL", "").strip()
    if explicit_url:
        return explicit_url

    base_uri = os.getenv("WORKSPACE_MCP_BASE_URI", "http://localhost").strip()
    public_port = os.getenv("WORKSPACE_MCP_PUBLIC_PORT", "").strip()
    port = public_port or os.getenv("WORKSPACE_MCP_PORT", DEFAULT_PUBLIC_MCP_PORT).strip()
    return _normalize_mcp_url(base_uri, port)


def _mcp_headers() -> dict[str, str]:
    token = os.getenv("MCP_AUTH_TOKEN", "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


INSTRUCTION = (
    "You are a Google Workspace assistant using MCP tools exposed by a "
    "local workspace-mcp server. Help the user with Gmail, Calendar, "
    "Drive, Docs, Sheets, Tasks, Contacts, and related Google Workspace "
    "operations only when those tools are available. Use MCP tools to "
    "inspect or modify user data instead of guessing. If a tool call "
    "fails because authentication is missing or expired, tell the user "
    "that the MCP server needs to be authenticated first. If a tool is "
    "not available, say so clearly rather than inventing capabilities."
)


def _build_model(base_url: str = "", api_key: str = ""):
    """Gemini by default. With LLM_BASE_URL (or an explicit base_url) the agent talks to any
    OpenAI-compatible endpoint through LiteLLM, e.g. a FreeLLMAPI gateway."""
    base_url = base_url or os.getenv("LLM_BASE_URL", "").strip()
    if not base_url:
        return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    from google.adk.models.lite_llm import LiteLlm

    return LiteLlm(
        model=f"openai/{os.getenv('LLM_MODEL_ID', 'auto')}",
        api_base=base_url,
        api_key=api_key or os.getenv("LLM_API_KEY", "not-needed"),
    )


def build_agent(model=None, mcp_url: str = "", extra_headers: dict[str, str] | None = None) -> LlmAgent:
    """Build the workspace agent. ``root_agent`` below is ``build_agent()`` with env-based defaults;
    the web demo builds one per request to inject a visitor-supplied model/key and session header."""
    headers = {**_mcp_headers(), **(extra_headers or {})}
    return LlmAgent(
        name="workspace_mcp_agent",
        model=model if model is not None else _build_model(),
        instruction=INSTRUCTION,
        tools=[
            McpToolset(
                connection_params=StreamableHTTPConnectionParams(
                    url=mcp_url or MCP_SERVER_URL,
                    headers=headers,
                )
            )
        ],
    )


_load_env()
MCP_SERVER_URL = _get_mcp_server_url()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

root_agent = build_agent()
