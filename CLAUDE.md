# Google Workspace Assistant - project context

## What this is
A Google ADK `LlmAgent` that uses MCP tools from an external `workspace-mcp` server (needs the user's Google OAuth). A public demo cannot use someone's account, so the `demo-ready` branch adds a web demo that runs the SAME agent against a bundled MOCK Workspace MCP server with fictional data:

```text
Browser (Vercel, static `demo/`) -> POST /chat -> Hugging Face Space `demo_api/` (limits, BYO key, LangSmith)
   -> mcp_server.agent.build_agent() -> LiteLLM -> private FreeLLMAPI gateway (127.0.0.1:3001) -> free-tier LLMs
   -> MCP over Streamable HTTP -> demo_api/mock_workspace_mcp.py (subprocess on 127.0.0.1:8081, per-session sample data)
```

## Layout
- `mcp_server/agent.py` - original agent, refactored into `build_agent(model, mcp_url, extra_headers)` and `_build_model()` (Gemini by default; `LiteLlm` when `LLM_BASE_URL` is set). `root_agent` still exists for `adk web`. Original file uses CRLF; keep it. Existing tests: `tests/test_agent_config.py`.
- `demo_api/app.py` - `POST /chat` runs the ADK `Runner` and returns reply + tool-call trace; spawns the mock MCP server at startup. `demo_api/mock_workspace_mcp.py` - tools: calendar, Gmail, Drive; state isolated per `X-Demo-Session`; sending mail/creating events only mutates the in-memory session. Shared plumbing: `llm.py`, `base.py`, `guard.py`, `gateway.py`.
- `demo/index.html` (+ `byo.js`, `base.css`, `config.js`, `write-config.mjs`) - chat UI; it states clearly that the data is simulated. `deploy/space/` - HF Space recipe.

## Run and test
- `python -m venv .venv && .venv\Scripts\pip install -r demo_api/requirements.txt pytest && .venv\Scripts\pytest tests/test_demo_api.py` and `python -m unittest discover -s tests` (5 + 4 tests; only the LLM endpoint is stubbed - ADK, LiteLLM, MCP transport and mock server are real).
- Local UI: set `API_URL` in `demo/config.js` to a local `uvicorn demo_api.app:app --port 8180`, serve `demo/` with `python -m http.server`. Restore `API_URL` to `""` before committing.

## Rules and gotchas
- MCP SDK must be 2.x (`mcp>=2,<3`): the mock server uses `mcp.server.mcpserver.MCPServer` and `ctx.headers`; with mcp 1.x the ADK/LiteLLM path failed in testing (`CacheableResult` import error). Do not "fix" it back to `FastMCP`.
- Keep the demo labelled as simulated. Never hard-code LLM output. Cap per-session turns and LLM calls (see `MAX_*` in `app.py`).
- Client IP for limits = LAST `X-Forwarded-For` entry. Never log API keys.

## Deploy facts
- Space `workspace-demo-api`, LangSmith project `workspace-demo` (also a LiteLLM callback), Vercel dir `demo/`, env var `DEMO_API_URL`.
- Space secrets: `ENCRYPTION_KEY` (64 hex), `FREEAPI_CONFIG_JSON`, `LANGSMITH_API_KEY`, `UPSTASH_REDIS_REST_URL/TOKEN`; optional `CORS_ORIGINS`, `RL_PER_IP_DAILY`, `RL_GLOBAL_DAILY`. The Space clones branch `demo-ready`.
- Steps: `hf auth login`, `vercel login`, create the Space from `deploy/space/`, set secrets, then `vercel deploy --prod --yes --build-env DEMO_API_URL=<space url>` from the repo root.

## Status
Verified: all tests pass; real startup spawns the mock MCP server; UI checked in a browser. NOT verified: Space Docker build, tool-calling quality of free models through LiteLLM (some may not support tools well), live deploy.
