---
title: Google Workspace Assistant Demo API
emoji: 🚀
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Demo API for Google Workspace Assistant with a private FreeLLMAPI gateway
---

# Google Workspace Assistant demo API (Hugging Face Space)

Live LLM answers through a **private** [FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi)
gateway in the same container; every call is traced to LangSmith project `workspace-demo`.
Source: <https://github.com/vldzio/google_workspace_assistant>.

## Space secrets (Settings → Variables and secrets)

| Name | Value |
| --- | --- |
| `ENCRYPTION_KEY` | 64 hex chars (`openssl rand -hex 32`); required by the gateway |
| `FREEAPI_CONFIG_JSON` | gateway config with your free-tier provider keys, see `freellmapi.config.example.json` |
| `LANGSMITH_API_KEY` | LangSmith key (tracing switches on automatically) |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | per-IP and global daily limits |
| `CORS_ORIGINS` | the frontend origin, e.g. `https://workspace-demo.vercel.app` |
| `RL_PER_IP_DAILY` / `RL_GLOBAL_DAILY` | optional, default 20 / 1000 credits per UTC day |

