# Local Google Workspace MCP Server with ADK Web

This folder contains:

- a Docker image wrapper for `workspace-mcp`
- a basic ADK agent in [agent.py](hackathon_client/mcp_server/agent.py)
- local configuration in [.env](hackathon_client/.env)

The app runs in two parts:

1. A local MCP server in Docker, exposed at `http://localhost:8080/mcp`
2. An ADK Web app on `http://127.0.0.1:8000` that connects to that MCP server

Google Cloud is still required because Google OAuth validates:

- your OAuth client ID and secret
- the allowed redirect URI
- the OAuth consent screen
- whether the account is allowed to use the app

## Architecture

1. `docker run` starts `workspace-mcp` in Docker
2. The container listens on its internal port `8000`
3. Docker maps host `localhost:8080` to the container's `8000`
4. `adk web` serves the dev UI on `127.0.0.1:8000`
5. `adk web` loads [agent.py](hackathon_client/mcp_server/agent.py)
6. The agent connects to `http://localhost:8080/mcp`
7. When auth is needed, the MCP server sends you to Google OAuth
8. Google redirects back to `http://localhost:8080/oauth2callback`
9. The MCP server stores credentials and future tool calls can use them

## Prerequisites

- Docker Desktop running
- Python installed
- `pip` available
- A Google Cloud project you control
- A Google OAuth client created in that project

Install the ADK packages:

```powershell
pip install -r requirements.txt
```

## Step 1: Configure Google Cloud

Open your Google Cloud project and configure the OAuth app before starting the local server.

### OAuth consent screen

In Google Cloud Console:

1. Open `Google Auth Platform` or `APIs & Services` -> `OAuth consent screen`
2. Configure the app name and support email
3. Decide whether the app is `Testing` or `Production`

If the app is in `Testing`:

- add your Google account as a test user

If the app is in `Production`:

- Google may still block some sensitive scopes until verification is complete
- for local testing, use a reduced tool set to reduce requested scopes

### OAuth client

In `APIs & Services` -> `Credentials`:

1. Open your OAuth 2.0 Client ID
2. Confirm it is active and not deleted
3. Add this redirect URI exactly:

```text
http://localhost:8080/oauth2callback
```

If you downloaded a client secret JSON file, copy the `client_id` and `client_secret` from it into `.env`.

### Enable required Google APIs

Enable the Google APIs you actually plan to use. For example:

- Gmail API
- Google Drive API
- Google Calendar API
- Google Docs API
- Google Sheets API

For first-time setup, start with fewer APIs and fewer tools.

## Step 2: Configure `.env`

Start by copying [.env.example](/d:/GoogleGenAI/hackathon_client/.env.example) to `.env`, then edit the values for your project.

```powershell
Copy-Item .env.example .env
```

Edit [.env](hackathon_client/.env) and ensure these values are correct.

Important rules:

- do not put spaces around `=`
- do not wrap the OAuth values in quotes
- keep the public MCP endpoint pointed at `http://localhost:8080/mcp`
- keep `WORKSPACE_MCP_BASE_URI` host-only, without `:8080`

Example:

```text
PROJECT_ID=your-project-id
PROJECT_NUMBER=your-project-number
SA_NAME=your-service-account-name
SERVICE_ACCOUNT=your-service-account@your-project.iam.gserviceaccount.com

GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
GOOGLE_API_KEY=your-google-api-key

MCP_SERVER_URL=http://localhost:8080/mcp
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8080/oauth2callback
WORKSPACE_MCP_BASE_URI=http://localhost
WORKSPACE_MCP_PORT=8000
WORKSPACE_MCP_PUBLIC_PORT=8080
MCP_ENABLE_OAUTH21=false
OAUTHLIB_INSECURE_TRANSPORT=1
USER_GOOGLE_EMAIL=you@example.com

# Optional: reduce requested scopes for easier local auth
# TOOLS=calendar
```

Recommended for first successful auth:

```text
TOOLS=calendar
```

Once auth works, expand to:

```text
TOOLS=gmail calendar drive
```

or remove `TOOLS` to enable everything.

### Environment variable reference

| Variable | Required | Purpose | Where to get it |
| --- | --- | --- | --- |
| `PROJECT_ID` | No for local runtime | Google Cloud project ID. Useful for identifying the project and keeping config consistent. | Google Cloud Console -> project selector |
| `PROJECT_NUMBER` | No for local runtime | Numeric project identifier. Informational in this local setup. | Google Cloud Console -> project dashboard |
| `SA_NAME` | No for local runtime | Service account name used in the earlier cloud deployment. Informational here unless you extend the setup. | Google Cloud Console -> IAM & Admin -> Service Accounts |
| `SERVICE_ACCOUNT` | No for local runtime | Full service account email from the cloud setup. Informational here unless you extend the setup. | Google Cloud Console -> IAM & Admin -> Service Accounts |
| `GOOGLE_OAUTH_CLIENT_ID` | Yes | OAuth client ID used for Google sign-in. | Google Cloud Console -> APIs & Services -> Credentials -> OAuth 2.0 Client ID, or the downloaded client secret JSON file |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Yes | OAuth client secret paired with the client ID. | Same OAuth client in Google Cloud Console or the downloaded client secret JSON file |
| `GOOGLE_API_KEY` | Usually no for basic auth flow | Google API key. Keep it only if your wider app or future tools need it. It is not the main credential for the OAuth sign-in flow. | Google Cloud Console -> APIs & Services -> Credentials -> API keys |
| `MCP_SERVER_URL` | Recommended | Explicit MCP endpoint used by the ADK agent. | Set manually in `.env` |
| `GOOGLE_OAUTH_REDIRECT_URI` | Recommended | Explicit OAuth callback URL exposed by Docker on the host. | Set manually in `.env` |
| `WORKSPACE_MCP_BASE_URI` | Yes | Base host used by the MCP server to construct callback URLs. Must be `http://localhost` for this setup. | Set manually in `.env` |
| `WORKSPACE_MCP_PORT` | Yes | Internal port used by `workspace-mcp` inside the container. Use `8000` unless you intentionally override the container entrypoint. | Set manually in `.env` |
| `WORKSPACE_MCP_PUBLIC_PORT` | Recommended | Host port exposed by Docker and used by ADK Web. This repo uses `8080`. | Set manually in `.env` |
| `MCP_ENABLE_OAUTH21` | Yes | Must be `false` for the simpler local auth flow described in this README. | Set manually in `.env` |
| `OAUTHLIB_INSECURE_TRANSPORT` | Yes for localhost HTTP auth | Allows OAuth callbacks over `http://localhost` during local development. | Set manually to `1` in `.env` |
| `USER_GOOGLE_EMAIL` | Recommended | Preferred Google account for the auth flow. Makes the local experience more predictable. | Your own Google account email |
| `TOOLS` | Optional but strongly recommended at first | Restricts enabled MCP tools, which also reduces requested scopes during OAuth. | Set manually based on what you want to test, for example `calendar` or `gmail calendar drive` |

Notes:

- The documented local flow relies on `MCP_SERVER_URL=http://localhost:8080/mcp` as the ADK-side source of truth.
- `WORKSPACE_MCP_PORT=8000` is the container's internal port, not the host port you enter in the browser.
- `WORKSPACE_MCP_PUBLIC_PORT=8080` documents the host-side Docker mapping used by this repo.
- `USER_GOOGLE_EMAIL` is not strictly required, but it is helpful.
- `TOOLS` is optional, but using a smaller tool set is the easiest way to get the first successful auth.
- `PROJECT_ID`, `PROJECT_NUMBER`, `SA_NAME`, and `SERVICE_ACCOUNT` are not driving the local Docker auth flow in the current repo, but they can remain in `.env` for consistency with the original cloud-hosted setup.

## Step 3: Build the Docker image

From this folder:

```powershell
docker build -t local-workspace-mcp .
```

## Step 4: Start the MCP server

Use a named Docker volume so credentials persist across restarts:

```powershell
docker run --rm --name local-workspace-mcp-test --env-file .env -p 8080:8000 -v workspace_mcp_creds:/root/.google_workspace_mcp local-workspace-mcp
```

Leave this terminal open while using the app.

What this does:

- loads config from `.env`
- exposes the MCP server on `localhost:8080`
- maps host port `8080` to the container's internal `8000`
- stores Google credentials in the Docker volume `workspace_mcp_creds`

## Step 5: Preflight checks

Before opening ADK Web, confirm the MCP server is reachable.

### Verify Docker container is running

```powershell
docker ps
```

You should see `local-workspace-mcp-test` with a port mapping like `0.0.0.0:8080->8000/tcp`.

### Verify server logs

```powershell
docker logs -f local-workspace-mcp-test
```

Healthy startup should show:

- `Transport: streamable-http`
- `Starting MCP server`
- `http://0.0.0.0:8000/mcp`

This is correct because it is the container's internal port. Docker maps it to host `localhost:8080`.

### Verify the MCP endpoint is reachable from the host

```powershell
try {
  Invoke-WebRequest http://localhost:8080/mcp -Method Get
} catch {
  $_.Exception.Response.StatusCode.value__
}
```

A reachable endpoint typically returns `200`, `404`, or `405`. A connection-refused error means ADK Web will fail to create the MCP session.

### Verify the OAuth callback target

Confirm your OAuth client and `.env` both use:

```text
http://localhost:8080/oauth2callback
```

## Step 6: Start ADK Web

Open a second terminal and run from the parent directory of this folder:

```powershell
cd ..
adk web --no-reload
```

Why `--no-reload`:

- it is usually more stable on Windows
- it avoids extra child processes while debugging MCP connections

In the ADK UI:

1. open the app for this package
2. select `workspace_mcp_agent`
3. ask it to authenticate your Google account

Example prompt:

```text
Authenticate my Google account for the MCP server.
```

## Step 7: Complete Google authentication

The agent should provide an OAuth link.

1. Open the link in your browser
2. Sign in with the intended Google account
3. Approve the requested scopes
4. Let Google redirect back to:

```text
http://localhost:8080/oauth2callback
```

Once complete, test with a small request, for example:

```text
List my next 5 calendar events.
```

## Common Issues

### `port is already allocated`

Something is already using host port `8080`.

Check:

```powershell
docker ps
Get-NetTCPConnection -LocalPort 8080 -State Listen
```

If the MCP container is running, stop it:

```powershell
docker rm -f local-workspace-mcp-test
```

### `invalid env file (.env)`

Docker rejected the `.env` format.

Typical causes:

- spaces around `=`
- invalid variable names
- stray quotes or malformed lines

Valid:

```text
GOOGLE_API_KEY=abc123
```

Invalid:

```text
GOOGLE_API_KEY = abc123
```

### `Error 401: invalid_client`

Google does not recognize the client ID.

Check:

- `GOOGLE_OAUTH_CLIENT_ID` is correct
- `GOOGLE_OAUTH_CLIENT_SECRET` is correct
- the client still exists in Google Cloud Console
- the values are not wrapped in quotes in `.env`

### `Error 401: deleted_client`

The OAuth client was deleted from Google Cloud Console.

Fix:

- create or recover a valid OAuth client
- update `.env`
- restart the Docker container

### `Error 400: redirect_uri_mismatch`

The OAuth client does not allow:

```text
http://localhost:8080/oauth2callback
```

Fix:

1. Open the OAuth client in Google Cloud Console
2. Add the exact redirect URI above
3. Save
4. restart the container

### `Error 403: access_denied`

Common causes:

- the app is in `Testing` and your account is not a test user
- the app requests sensitive scopes that are not approved
- the app is in `Production` but verification is incomplete for the requested scopes

Fixes:

- add your account as a test user if using testing mode
- reduce requested scopes by limiting `TOOLS`
- start with `TOOLS=calendar`

After editing `.env`, restart the container.

### ADK error: `Failed to create MCP session`

Usually means ADK could not connect to the MCP server or the MCP server returned auth errors.

Check:

- Docker container is running
- host `localhost:8080` maps to container `8000`
- the MCP endpoint is reachable at `http://localhost:8080/mcp`
- the container was restarted after `.env` changes
- `MCP_SERVER_URL` still points to `http://localhost:8080/mcp`

If the browser console also shows `lazyLoadMessages: Not implemented`, treat that as a secondary UI symptom. The primary issue is usually that the MCP session could not be created because the endpoint was unreachable or misconfigured.

### The agent still asks for auth after I already logged in

Possible causes:

- the credentials were not saved
- you started the container without the Docker volume
- you restarted with a fresh anonymous container filesystem

Use the volume-backed run command:

```powershell
docker run --rm --name local-workspace-mcp-test --env-file .env -p 8080:8000 -v workspace_mcp_creds:/root/.google_workspace_mcp local-workspace-mcp
```

### Optional local-run diagnostics

The files `mcp_server/workspace-mcp.local.log` and `mcp_server/workspace-mcp.local.err.log` are optional diagnostics from ad hoc local runs. They are not used by the documented Docker flow.

## Restart after changing `.env`

The container does not reload `.env` automatically.

Every time you change `.env`, restart the container:

```powershell
docker rm -f local-workspace-mcp-test
docker run --rm --name local-workspace-mcp-test --env-file .env -p 8080:8000 -v workspace_mcp_creds:/root/.google_workspace_mcp local-workspace-mcp
```

## Cleanup

### Stop the MCP server

```powershell
docker rm -f local-workspace-mcp-test
```

### Remove saved Google credentials

This deletes the Docker volume that stores MCP auth state:

```powershell
docker volume rm workspace_mcp_creds
```

### Remove the Docker image

```powershell
docker rmi local-workspace-mcp
```

### Stop ADK Web

Press `Ctrl+C` in the terminal running `adk web`.

## Security Notes

- `.env` contains secrets
- do not commit `.env` to source control
- rotate OAuth client secrets and API keys if they were shared
- for public or production use, review Google verification requirements before requesting broad scopes

## Quick Start Summary

1. Configure Google Cloud OAuth client and redirect URI
2. Update [.env](/d:/GoogleGenAI/hackathon_client/.env) with valid credentials plus `MCP_SERVER_URL`
3. Optionally set `TOOLS=calendar` for first auth
4. Run `docker build -t local-workspace-mcp .`
5. Run the Docker container with `-p 8080:8000`
6. Confirm `http://localhost:8080/mcp` is reachable
7. Run `adk web --no-reload` from the parent directory
8. Authenticate through the browser
9. Test a simple tool call
