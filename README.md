# Google Workspace Assistant — Google ADK × MCP

A compact tool-using assistant that connects a Google ADK agent to a local **Google Workspace MCP server** over Streamable HTTP. The agent can ask the MCP server for available Workspace tools and use them for user-authorized Gmail, Calendar, Drive, Docs, Sheets, and related tasks, depending on the server's enabled tools and OAuth scopes.

This repository owns the **ADK agent, configuration, small Docker wrapper, and configuration tests**. The underlying `workspace-mcp` implementation is an external dependency installed by the Dockerfile; this project does not implement Google Workspace integrations from scratch.

```text
Browser → ADK Web → mcp_server/agent.py (Gemini LlmAgent)
                            ↓ Streamable HTTP
                Dockerized workspace-mcp :8080/mcp
                            ↓ OAuth and Google APIs
                       User's Workspace account
```

## Highlights

- `mcp_server/agent.py` defines an `LlmAgent` with a `McpToolset`, an environment-selectable Gemini model (default `gemini-2.5-flash`), and an explicit instruction not to invent unavailable tools or data.
- The MCP endpoint may be set directly with `MCP_SERVER_URL`, or assembled from `WORKSPACE_MCP_BASE_URI` and the configured public port. An optional `MCP_AUTH_TOKEN` is sent as a bearer header when set.
- `tests/test_agent_config.py` checks environment-file selection and endpoint configuration. These are **configuration unit tests**, not live Google API or end-to-end OAuth tests.

## Run locally

You need Python, Docker, a Gemini API key for ADK, and a Google Cloud OAuth client with the APIs/scopes you plan to use. Configure the OAuth consent screen; add your account as a test user if the app is in testing mode. Add **exactly** `http://localhost:8080/oauth2callback` as an allowed redirect URI for this example.

From the **repository root** (the directory containing `mcp_server/`):

```bash
python -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                  # Windows PowerShell: Copy-Item .env.example .env
```

Edit `.env`: fill in `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_API_KEY` (for ADK/Gemini), and an appropriate `USER_GOOGLE_EMAIL`. Keep `MCP_SERVER_URL=http://localhost:8080/mcp` and `GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8080/oauth2callback` for the Docker command below. The example starts with `TOOLS=calendar` to limit requested OAuth scopes; enable more tools only as needed. `GOOGLE_API_KEY` is read by the Google ADK runtime, not directly by `agent.py`. Project/service-account fields in `.env.example` are context from an earlier cloud setup and are not read directly by the local agent.

Build and start the external MCP server in one terminal:

```bash
docker build -t local-workspace-mcp .
docker run --rm --name local-workspace-mcp --env-file .env \
  -p 8080:8000 -v workspace_mcp_creds:/root/.google_workspace_mcp \
  local-workspace-mcp
```

Then, in another terminal from the **same repository root** with the virtual environment activated:

```bash
adk web --no-reload
```

Open the local URL printed by ADK Web, select the `mcp_server` app, follow the Google OAuth flow if prompted, and try a small read-only request such as “What events are on my calendar today?” The `mcp_server/` folder is the ADK agent package; do **not** run `cd ..` from the repository root. OAuth behavior and tool availability are controlled by the external MCP server and your Google Cloud configuration.

### Configuration and checks

| Setting | Purpose |
| --- | --- |
| `MCP_SERVER_URL` | Explicit Streamable HTTP endpoint; takes precedence over derived settings |
| `WORKSPACE_MCP_BASE_URI`, `WORKSPACE_MCP_PUBLIC_PORT` | Fallback endpoint construction when `MCP_SERVER_URL` is unset |
| `MCP_AUTH_TOKEN` | Optional bearer token header for the ADK-to-MCP connection |
| `GEMINI_MODEL` | ADK model name; defaults to `gemini-2.5-flash` |
| `TOOLS` | Optional restriction on MCP tools / OAuth scopes, consumed by `workspace-mcp` |

```bash
python -m unittest discover -s tests -v
# If the agent cannot connect, check: docker ps; docker logs local-workspace-mcp
```

A GET to `/mcp` is not a full functionality check: the MCP transport may require POST/session negotiation. Confirm connectivity and OAuth through an actual agent tool call.

## Security and status

Keep `.env`, OAuth credentials, saved Docker credentials, and any Workspace data out of version control. This is a **local integration prototype**, not a hosted multi-user app; it has no application-level approval UI for write actions. Restrict OAuth scopes, confirm changes before granting broad access, and review the external `workspace-mcp` package before use. Never expose the unauthenticated MCP port publicly. There is no claim here that live Workspace operations were run during this code review.
