# Google Workspace Assistant — Google ADK × MCP

A tool-using assistant that connects a **Google ADK agent** to a **Google Workspace MCP server** over Streamable HTTP. The agent discovers the Workspace tools the server exposes and uses them for Gmail, Calendar, Drive, Docs, Sheets, and related tasks on your authorized account.

**Live demo:** [googleworkspaceassistant.vercel.app](https://googleworkspaceassistant.vercel.app). It runs the same agent on fictional sample data and shows every tool call.

This repository contains the ADK agent, its configuration, a Docker wrapper for the [`workspace-mcp`](https://pypi.org/project/workspace-mcp/) server, and configuration tests.

```text
Browser → ADK Web → mcp_server/agent.py (Gemini LlmAgent)
                            ↓ Streamable HTTP
                Dockerized workspace-mcp :8080/mcp
                            ↓ OAuth and Google APIs
                       Your Workspace account
```

## Highlights

- `mcp_server/agent.py` builds an `LlmAgent` with a `McpToolset` (`build_agent()`). It uses Gemini by default (`gemini-2.5-flash`), or any OpenAI-compatible model through LiteLLM when `LLM_BASE_URL` is set. The agent is instructed to use only the tools and data it actually has.
- The MCP endpoint is set with `MCP_SERVER_URL`, or built from `WORKSPACE_MCP_BASE_URI` and the public port. An optional `MCP_AUTH_TOKEN` is sent as a bearer header.
- `TOOLS` restricts which Workspace services, and therefore which OAuth scopes, the server requests.
- `tests/` covers environment and endpoint configuration and the demo API end to end (only the LLM endpoint is stubbed).

## Setup

You need Python, Docker, a Gemini API key, and a Google Cloud OAuth client for the APIs you plan to use. On the OAuth consent screen, add your account as a test user, and add `http://localhost:8080/oauth2callback` as an authorized redirect URI.

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                  # Windows PowerShell: Copy-Item .env.example .env
```

Fill in `.env` (it is git-ignored):

- `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`: your OAuth client
- `GOOGLE_API_KEY`: Gemini key used by ADK
- `USER_GOOGLE_EMAIL`: the account to act on
- `MCP_SERVER_URL=http://localhost:8080/mcp`
- `GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8080/oauth2callback`
- `TOOLS=calendar` to start with Calendar only; add more services as needed

## Run

Start the MCP server:

```bash
docker build -t local-workspace-mcp .
docker run --rm --name local-workspace-mcp --env-file .env \
  -p 8080:8000 -v workspace_mcp_creds:/root/.google_workspace_mcp \
  local-workspace-mcp
```

In a second terminal, from the repository root with the virtual environment active:

```bash
adk web --no-reload
```

Open the URL ADK Web prints, select the `mcp_server` app, complete the Google sign-in when prompted, and try a request such as “What events are on my calendar today?”

## Live demo

```text
Browser (Vercel, demo/) ──► POST /chat ──► demo_api/ (FastAPI)
                                              ├─ the same ADK agent (build_agent) ──► LiteLLM ──► free-tier LLM gateway
                                              └─ MCP over Streamable HTTP ──► bundled mock Workspace MCP server
```

- The agent, tool selection and model reasoning are the real thing; the page shows every tool call and its result.
- `demo_api/mock_workspace_mcp.py` serves fictional calendar, Gmail and Drive data, isolated per visitor, so nobody has to connect a Google account. Sending mail or creating events only changes that visitor's in-memory copy.
- Visitors get a daily allowance or can bring their own key; model calls are traced in LangSmith.

Run it locally:

```bash
pip install -r demo_api/requirements.txt pytest
pytest tests
uvicorn demo_api.app:app --port 8180
```

Set `API_URL` in `demo/config.js` to `http://localhost:8180` and serve `demo/` with `python -m http.server`. Deployment recipes: `deploy/space/` and `vercel.json`.

## Configuration

| Setting | Purpose |
| --- | --- |
| `MCP_SERVER_URL` | Streamable HTTP endpoint; takes precedence over derived settings |
| `WORKSPACE_MCP_BASE_URI`, `WORKSPACE_MCP_PUBLIC_PORT` | Used to build the endpoint when `MCP_SERVER_URL` is unset |
| `MCP_AUTH_TOKEN` | Optional bearer token for the ADK-to-MCP connection |
| `GEMINI_MODEL` | ADK model name; defaults to `gemini-2.5-flash` |
| `LLM_BASE_URL`, `LLM_API_KEY` | Use an OpenAI-compatible model through LiteLLM instead of Gemini |
| `TOOLS` | Workspace services (and OAuth scopes) enabled on the MCP server |

## Tests and troubleshooting

```bash
python -m unittest discover -s tests -v    # agent configuration tests
pytest tests                                # all tests, including the demo API
```

If the agent can't reach the server, check `docker ps` and `docker logs local-workspace-mcp`.
