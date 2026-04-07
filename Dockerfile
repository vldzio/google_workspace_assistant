FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

RUN uv pip install --system workspace-mcp

EXPOSE 8000

CMD ["uvx", "workspace-mcp", "--transport", "streamable-http"]
